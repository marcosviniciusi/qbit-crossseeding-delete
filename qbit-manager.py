#!/usr/bin/env python3

# qb_unified_manager.py
# Gerenciamento unificado: espaço em disco + checking/moving + seed cleaner

import logging
import os
import sys
import json
import time
import shutil
import sqlite3
from datetime import datetime
from typing import Any, Optional
from urllib.parse import urlparse
from collections import defaultdict

import qbittorrentapi
import requests

# ============================================================================
# LOGGING
# ============================================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("qbit-manager")

# ============================================================================
# CONSTANTES
# ============================================================================

NOME_TRUNCADO_MAX = 55          # Tamanho máximo do nome de torrent em logs
API_THROTTLE_DELAY = 0.1        # Delay entre chamadas API (segundos)
DELETE_DELAY = 0.5              # Delay entre deleções de torrents (segundos)
POST_DELETE_WAIT = 120          # Espera após deleções para o sistema processar (segundos)
CONNECT_TIMEOUT = 30            # Timeout de conexão com qBittorrent (segundos)

# Colunas válidas para atualizar na tabela 'runs'
ALLOWED_RUN_COLUMNS = frozenset({
    "status", "checking", "moving", "disk_spaces", "paused_count",
    "forcados_checking", "tracker_forcados", "tracker_ativados",
    "seeding_deletados",
})

# ============================================================================
# CONFIGURAÇÃO
# ============================================================================

# Diretório de configuração — ajuste para o caminho real dos seus arquivos
CONFIG_DIR = os.environ.get("QBIT_MANAGER_CONFIG_DIR", "/etc/qbit-manager")

# Adicionar CONFIG_DIR ao path para importar config.py e tracker_rules.py de lá
if CONFIG_DIR not in sys.path:
    sys.path.insert(0, CONFIG_DIR)

# Importar configurações principais (imports explícitos)
try:
    from config import (  # type: ignore[import-untyped]
        QB_URL, QB_USER, QB_PASS,
        MIN_DOWNLOADS_PER_TRACKER, MIN_TORRENTS_PER_TRACKER,
        SEED_CLEANER_DRY_RUN, PATHS, TRACKER_RULES,
    )
    # Variáveis opcionais com fallback
    try:
        from config import DB_DIR, DB_PATH  # type: ignore[import-untyped]
    except ImportError:
        DB_DIR = "/var/lib/qbit-manager"
        DB_PATH = f"{DB_DIR}/qbit.db"

    try:
        from config import PUSHOVER_TOKEN, PUSHOVER_USER  # type: ignore[import-untyped]
    except ImportError:
        PUSHOVER_TOKEN = ""
        PUSHOVER_USER = ""
except ImportError:
    logger.warning("Crie um arquivo config.py em %s!", CONFIG_DIR)
    QB_URL = "https://torrent.exemplo.com"
    QB_USER = "admin"
    QB_PASS = "senha"
    PUSHOVER_TOKEN = "token"
    PUSHOVER_USER = "user"
    MIN_DOWNLOADS_PER_TRACKER = 4
    MIN_TORRENTS_PER_TRACKER = 4
    SEED_CLEANER_DRY_RUN = True
    PATHS: dict[str, dict[str, Any]] = {
        "p2p": {
            "path": "/mnt/p2p/",
            "limite_min": 100,
            "limite_max": 150,
            "seed_cleaner": True,
            "pause_trigger": True,
        },
        "videos": {
            "path": "/mnt/videos/",
            "limite_min": 200,
            "limite_max": 250,
            "seed_cleaner": False,
            "pause_trigger": True,
        },
    }
    TRACKER_RULES: dict[str, int] = {}
    DB_DIR = "/var/lib/qbit-manager"
    DB_PATH = f"{DB_DIR}/qbit.db"

# Importar tracker_rules.py separado (sobrescreve TRACKER_RULES do config se existir)
try:
    from tracker_rules import TRACKER_RULES  # type: ignore[import-untyped]  # noqa: F811
    logger.info("Regras de tracker carregadas de tracker_rules.py")
except ImportError:
    pass  # Usa TRACKER_RULES do config.py ou o dict vazio acima


# ============================================================================
# DATABASE
# ============================================================================

def init_db() -> sqlite3.Connection:
    """Inicializa o banco de dados SQLite e retorna a conexão."""
    os.makedirs(DB_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS runs (
            id                 INTEGER PRIMARY KEY AUTOINCREMENT,
            started_at         TEXT    NOT NULL,
            status             TEXT    NOT NULL,
            checking           INTEGER NOT NULL DEFAULT 0,
            moving             INTEGER NOT NULL DEFAULT 0,
            disk_spaces        TEXT,
            paused_count       INTEGER NOT NULL DEFAULT 0,
            forcados_checking  INTEGER NOT NULL DEFAULT 0,
            tracker_forcados   INTEGER NOT NULL DEFAULT 0,
            tracker_ativados   INTEGER NOT NULL DEFAULT 0,
            seeding_deletados  INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS torrent_snapshots (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id      INTEGER NOT NULL REFERENCES runs(id),
            recorded_at TEXT    NOT NULL,
            hash        TEXT    NOT NULL,
            name        TEXT    NOT NULL,
            state       TEXT    NOT NULL,
            progress    REAL    NOT NULL DEFAULT 0,
            dlspeed     INTEGER NOT NULL DEFAULT 0,
            upspeed     INTEGER NOT NULL DEFAULT 0,
            size        INTEGER NOT NULL DEFAULT 0,
            tracker     TEXT,
            force_start INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS pause_events (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id           INTEGER NOT NULL REFERENCES runs(id),
            event_at         TEXT    NOT NULL,
            event_type       TEXT    NOT NULL,
            reason           TEXT,
            disk_spaces      TEXT,
            discos_criticos  TEXT,
            torrent_hashes   TEXT,
            torrents_count   INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS seed_deletions (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id       INTEGER NOT NULL REFERENCES runs(id),
            deleted_at   TEXT    NOT NULL,
            hash         TEXT    NOT NULL,
            name         TEXT    NOT NULL,
            tracker      TEXT,
            seeding_days REAL    NOT NULL DEFAULT 0,
            rule_days    INTEGER NOT NULL DEFAULT 0,
            size_bytes   INTEGER NOT NULL DEFAULT 0,
            dry_run      INTEGER NOT NULL DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS notifications (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id      INTEGER NOT NULL REFERENCES runs(id),
            sent_at     TEXT    NOT NULL,
            event_type  TEXT    NOT NULL,
            title       TEXT    NOT NULL,
            message     TEXT    NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_snapshots_run      ON torrent_snapshots(run_id);
        CREATE INDEX IF NOT EXISTS idx_snapshots_hash     ON torrent_snapshots(hash);
        CREATE INDEX IF NOT EXISTS idx_snapshots_state    ON torrent_snapshots(state);
        CREATE INDEX IF NOT EXISTS idx_pause_events_run   ON pause_events(run_id);
        CREATE INDEX IF NOT EXISTS idx_pause_events_type  ON pause_events(event_type);
        CREATE INDEX IF NOT EXISTS idx_seed_deletions_run ON seed_deletions(run_id);
        CREATE INDEX IF NOT EXISTS idx_notifications_type ON notifications(event_type);
    """)

    # Migração: adicionar coluna discos_criticos se não existir (bancos antigos)
    try:
        conn.execute("ALTER TABLE pause_events ADD COLUMN discos_criticos TEXT")
        conn.commit()
    except sqlite3.OperationalError:
        pass  # Coluna já existe
    conn.commit()
    return conn


def ler_ultimo_estado(conn: sqlite3.Connection) -> dict[str, Any]:
    """
    Retorna o estado da última execução:
    {
      'run_status':        'active' | 'paused' | 'waiting',
      'torrents_pausados': set de hashes,
      'motivo_pausa':      ['disk_space'] ou [],
      'discos_criticos':   ['p2p'] | ['videos'] | ['p2p','videos'] | [] | None,
      'ultimo_run_id':     int ou None
    }
    """
    cur = conn.execute("SELECT id, status FROM runs ORDER BY id DESC LIMIT 1")
    ultimo_run = cur.fetchone()

    torrents_pausados = ler_torrents_pausados(conn)
    motivo_pausa = ler_motivo_pausa(conn)

    # Ler discos_criticos do último pause ativo
    discos_criticos: Optional[list[str]] = None
    last_pause = conn.execute(
        "SELECT id, discos_criticos FROM pause_events WHERE event_type='pause' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    if last_pause:
        last_restore = conn.execute(
            "SELECT id FROM pause_events WHERE event_type='restore' AND id > ?",
            (last_pause["id"],)
        ).fetchone()
        if not last_restore and last_pause["discos_criticos"]:
            discos_criticos = json.loads(last_pause["discos_criticos"])

    return {
        "run_status": ultimo_run["status"] if ultimo_run else "active",
        "torrents_pausados": torrents_pausados,
        "motivo_pausa": motivo_pausa,
        "discos_criticos": discos_criticos,
        "ultimo_run_id": ultimo_run["id"] if ultimo_run else None,
    }


def criar_run(
    conn: sqlite3.Connection,
    status: str,
    checking: int,
    moving: int,
    espacos: dict[str, dict[str, Any]],
    paused_count: int = 0,
) -> int:
    """Cria um novo registro de execução e retorna o run_id."""
    disk_json = json.dumps({
        nome: {
            "livre": round(d["livre"], 2),
            "critico": d["critico"],
            "ok": d["ok"],
            "limite_min": d["limite_min"],
            "limite_max": d["limite_max"],
        }
        for nome, d in espacos.items()
    })
    cur = conn.execute("""
        INSERT INTO runs (started_at, status, checking, moving, disk_spaces, paused_count)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (datetime.now().isoformat(), status, checking, moving, disk_json, paused_count))
    conn.commit()
    return cur.lastrowid  # type: ignore[return-value]


def atualizar_run(conn: sqlite3.Connection, run_id: int, **kwargs: Any) -> None:
    """Atualiza campos do registro de execução (apenas colunas permitidas)."""
    if not kwargs:
        return
    invalid_cols = set(kwargs.keys()) - ALLOWED_RUN_COLUMNS
    if invalid_cols:
        logger.error("Colunas inválidas para atualizar run: %s", invalid_cols)
        return
    sets = ", ".join(f"{k} = ?" for k in kwargs)
    conn.execute(f"UPDATE runs SET {sets} WHERE id = ?", list(kwargs.values()) + [run_id])
    conn.commit()


def salvar_snapshots(
    conn: sqlite3.Connection,
    run_id: int,
    todos_torrents: list[Any],
    tracker_map: dict[str, str],
) -> None:
    """Salva snapshot de todos os torrents no banco."""
    agora = datetime.now().isoformat()
    rows = [(
        run_id, agora, t.hash, t.name, t.state,
        round(getattr(t, "progress", 0), 4),
        getattr(t, "dlspeed", 0),
        getattr(t, "upspeed", 0),
        getattr(t, "size", 0),
        tracker_map.get(t.hash, "unknown"),
        1 if getattr(t, "force_start", False) else 0,
    ) for t in todos_torrents]
    conn.executemany("""
        INSERT INTO torrent_snapshots
            (run_id, recorded_at, hash, name, state, progress,
             dlspeed, upspeed, size, tracker, force_start)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, rows)
    conn.commit()
    logger.info("%d torrents salvos no banco", len(rows))


def registrar_pause_event(
    conn: sqlite3.Connection,
    run_id: int,
    event_type: str,
    reason: Optional[str] = None,
    espacos: Optional[dict[str, dict[str, Any]]] = None,
    hashes: Optional[set[str]] = None,
    discos_criticos: Optional[list[str]] = None,
) -> None:
    """Registra evento de pausa/restauração no banco."""
    disk_json = json.dumps({
        n: {"livre": round(d["livre"], 2), "critico": d["critico"]}
        for n, d in espacos.items()
    }) if espacos else None
    hashes_json = json.dumps(list(hashes)) if hashes else "[]"
    criticos_json = json.dumps(discos_criticos) if discos_criticos else None
    conn.execute("""
        INSERT INTO pause_events
            (run_id, event_at, event_type, reason, disk_spaces,
             discos_criticos, torrent_hashes, torrents_count)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (run_id, datetime.now().isoformat(), event_type, reason,
          disk_json, criticos_json, hashes_json, len(hashes) if hashes else 0))
    conn.commit()


def salvar_seed_deletions(conn: sqlite3.Connection, run_id: int, deletados: list[dict[str, Any]]) -> None:
    """Salva registros de torrents deletados pelo seed cleaner."""
    agora = datetime.now().isoformat()
    conn.executemany("""
        INSERT INTO seed_deletions
            (run_id, deleted_at, hash, name, tracker, seeding_days, rule_days, size_bytes, dry_run)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, [(
        run_id, agora,
        t["hash"], t["name"], t["tracker"],
        t["days"], t["rule"], t.get("size", 0),
        1 if SEED_CLEANER_DRY_RUN else 0,
    ) for t in deletados])
    conn.commit()


def ler_torrents_pausados(conn: sqlite3.Connection) -> set[str]:
    """Retorna hashes pausados ativos (último pause sem restore posterior)."""
    last_pause = conn.execute(
        "SELECT id, torrent_hashes FROM pause_events WHERE event_type='pause' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    if not last_pause:
        return set()
    last_restore = conn.execute(
        "SELECT id FROM pause_events WHERE event_type='restore' AND id > ?",
        (last_pause["id"],)
    ).fetchone()
    if last_restore:
        return set()
    hashes = json.loads(last_pause["torrent_hashes"] or "[]")
    return set(hashes)


def ler_motivo_pausa(conn: sqlite3.Connection) -> list[str]:
    """Retorna motivo da pausa ativa (sem restore posterior)."""
    last_pause = conn.execute(
        "SELECT id, reason FROM pause_events WHERE event_type='pause' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    if not last_pause:
        return []
    last_restore = conn.execute(
        "SELECT id FROM pause_events WHERE event_type='restore' AND id > ?",
        (last_pause["id"],)
    ).fetchone()
    if last_restore:
        return []
    return last_pause["reason"].split(",") if last_pause["reason"] else []


# ============================================================================
# HELPERS
# ============================================================================

# Tentar carregar notificacao.py do CONFIG_DIR
# Se não existir, usa fallback com Pushover (configurado no config.py)
try:
    from notificacao import enviar_notificacao  # type: ignore[import-untyped]
except ImportError:
    def enviar_notificacao(titulo: str, mensagem: str, priority: int = 0, event_type: Optional[str] = None) -> None:
        """Fallback Pushover — crie notificacao.py no CONFIG_DIR para sobrescrever."""
        try:
            requests.post("https://api.pushover.net/1/messages.json", data={
                "token": PUSHOVER_TOKEN,
                "user": PUSHOVER_USER,
                "title": titulo,
                "message": mensagem,
                "priority": priority,
            }, timeout=CONNECT_TIMEOUT)
        except Exception as e:
            logger.error("Erro Pushover: %s", e)


def registrar_notificacao(conn: sqlite3.Connection, run_id: int, event_type: str, title: str, message: str) -> None:
    """Registrar notificação enviada no banco."""
    conn.execute("""
        INSERT INTO notifications (run_id, sent_at, event_type, title, message)
        VALUES (?, ?, ?, ?, ?)
    """, (run_id, datetime.now().isoformat(), event_type, title, message))
    conn.commit()


def minutos_desde_ultima_notificacao(conn: sqlite3.Connection, event_type: str) -> Optional[float]:
    """Retornar quantos minutos desde a última notificação do tipo informado."""
    row = conn.execute("""
        SELECT sent_at FROM notifications
        WHERE event_type = ?
        ORDER BY id DESC LIMIT 1
    """, (event_type,)).fetchone()
    if not row:
        return None  # Nunca enviou
    ultima = datetime.fromisoformat(row["sent_at"])
    delta = datetime.now() - ultima
    return delta.total_seconds() / 60


def notificar_se_necessario(conn: sqlite3.Connection, run_id: int, event_type: str, intervalo_minutos: int = 60) -> None:
    """
    Envia notificação respeitando o intervalo mínimo entre envios do mesmo tipo.
    - event_type 'restored'       -> sempre envia (sem intervalo)
    - event_type 'paused'         -> envia apenas 1x por ocorrência
    - event_type 'waiting_paused' -> envia a cada intervalo_minutos (padrão 60)
    """
    NOTIFICACOES = {
        "paused": ("Torrents Status", "Downloads Pausados", 1),
        "restored": ("Torrents Status", "Download em andamento", 0),
        "waiting_paused": ("Downloads Ainda Pausados", "Verificar sistema.", 1),
    }

    if event_type not in NOTIFICACOES:
        return

    titulo, mensagem, priority = NOTIFICACOES[event_type]
    minutos = minutos_desde_ultima_notificacao(conn, event_type)

    if event_type == "paused":
        # Só envia se nunca enviou ou se houve uma restauração depois
        ultima_restored = minutos_desde_ultima_notificacao(conn, "restored")
        ultima_paused = minutos_desde_ultima_notificacao(conn, "paused")
        if ultima_paused is not None:
            if ultima_restored is None or ultima_paused < ultima_restored:
                logger.info("Notificacao '%s' ja enviada - pulando", event_type)
                return
    elif event_type == "waiting_paused":
        if minutos is not None and minutos < intervalo_minutos:
            logger.info(
                "Notificacao '%s' enviada ha %.0f min (intervalo: %d min) - pulando",
                event_type, minutos, intervalo_minutos,
            )
            return

    enviar_notificacao(titulo, mensagem, priority, event_type)
    registrar_notificacao(conn, run_id, event_type, titulo, mensagem)
    logger.info("Notificacao '%s' enviada: %s - %s", event_type, titulo, mensagem)


def extrair_dominio_tracker(url: str) -> str:
    """Extrai domínio principal de uma URL de tracker."""
    try:
        domain = urlparse(url).netloc.lower().split(":")[0]
        parts = domain.split(".")
        return ".".join(parts[-2:]) if len(parts) >= 2 else domain
    except Exception:
        return "unknown"


def verificar_espacos() -> dict[str, dict[str, Any]]:
    """Verifica espaço livre em disco para todos os paths configurados."""
    resultados: dict[str, dict[str, Any]] = {}
    for nome, config in PATHS.items():
        paths = config["path"] if isinstance(config["path"], list) else [config["path"]]

        livre_gb: Optional[float] = None
        for path in paths:
            try:
                _, _, free = shutil.disk_usage(path)
                gb = free / (1024 ** 3)
            except FileNotFoundError:
                logger.warning("Path nao encontrado: %s", path)
                gb = 0
            # Usa o menor espaço livre entre todos os paths do grupo (pior caso)
            if livre_gb is None or gb < livre_gb:
                livre_gb = gb

        if livre_gb is None:
            livre_gb = 0

        resultados[nome] = {
            "livre": livre_gb,
            "paths": paths,
            "limite_min": config["limite_min"],
            "limite_max": config["limite_max"],
            "critico": livre_gb <= config["limite_min"],
            "ok": livre_gb >= config["limite_max"],
            "seed_cleaner": config.get("seed_cleaner", False),
            "pause_trigger": config.get("pause_trigger", True),
        }
    return resultados


def imprimir_espacos(espacos: dict[str, dict[str, Any]]) -> None:
    """Imprime status de espaço em disco."""
    for nome, info in espacos.items():
        status = "CRITICO" if info["critico"] else "OK" if info["ok"] else "ATENCAO"
        logger.info(
            "[%s] %s: %.1f GB (min: %s, max: %s)",
            status, nome, info["livre"], info["limite_min"], info["limite_max"],
        )


def obter_contagem_checking_moving(client: qbittorrentapi.Client) -> tuple[int, int, list[Any], list[Any]]:
    """Retorna contagem e lista de torrents em checking e moving."""
    todos = client.torrents_info()
    checking = [t for t in todos if t.state in ("checkingDL", "checkingUP", "checkingResumeData")]
    moving = [t for t in todos if t.state == "moving"]
    return len(checking), len(moving), checking, moving


def obter_downloads_ativos(client: qbittorrentapi.Client) -> list[Any]:
    """Retorna apenas torrents com force start ativo (forcedDL)."""
    return [
        t for t in client.torrents_info()
        if t.state == "forcedDL"
    ]


def construir_tracker_map(client: qbittorrentapi.Client, todos_torrents: list[Any]) -> dict[str, str]:
    """Constrói mapa hash -> domínio do tracker principal."""
    tracker_map: dict[str, str] = {}
    for t in todos_torrents:
        try:
            for tr in client.torrents_trackers(t.hash):
                if tr.url and not tr.url.startswith("**"):
                    tracker_map[t.hash] = extrair_dominio_tracker(tr.url)
                    break
        except Exception as e:
            logger.debug("Erro ao obter trackers de %s: %s", t.hash[:16], e)
        if t.hash not in tracker_map:
            tracker_map[t.hash] = "unknown"
    return tracker_map

# ============================================================================
# SEED CLEANER
# ============================================================================

def get_tracker_rules_for_torrent(trackers: list[Any]) -> list[tuple[str, int]]:
    """Retornar regras aplicáveis baseadas nos trackers do torrent."""
    rules: list[tuple[str, int]] = []
    for tracker in trackers:
        url = tracker.get("url", "") if isinstance(tracker, dict) else getattr(tracker, "url", "")
        if url.startswith("**"):
            continue
        domain = extrair_dominio_tracker(url)
        for rule_domain, days in TRACKER_RULES.items():
            if rule_domain in domain:
                rules.append((rule_domain, days))
                break
    return rules


def forcar_start_checking(client: qbittorrentapi.Client, checking_torrents: list[Any]) -> int:
    """Aplica force_start em todos os torrents em estado checking/checkingResumeData."""
    if not checking_torrents:
        return 0
    forcados = 0
    logger.info("Force start em %d torrents em checking...", len(checking_torrents))
    for t in checking_torrents:
        try:
            client.torrents_set_force_start(torrent_hashes=t.hash, enable=True)
            logger.info("  Force start: %s [%s]", t.name[:NOME_TRUNCADO_MAX], t.state)
            forcados += 1
            time.sleep(API_THROTTLE_DELAY)
        except Exception as e:
            logger.error("  Falha force start %s: %s", t.name[:30], e)
    logger.info("%d torrents com force start aplicado", forcados)
    return forcados


# ============================================================================
# PAUSA
# ============================================================================

def executar_pausa(
    client: qbittorrentapi.Client,
    conn: sqlite3.Connection,
    run_id: int,
    espacos: dict[str, dict[str, Any]],
    moving_count: int,
    moving_torrents: list[Any],
) -> None:
    """Pausa downloads ativos quando disco está crítico."""
    downloads_ativos = obter_downloads_ativos(client)
    torrents_pausados_ant = ler_torrents_pausados(conn)

    logger.warning("DISCO CRITICO - pausando downloads")
    for nome, d in espacos.items():
        if d["critico"]:
            logger.warning("  %s: %.1f GB (min: %d GB)", nome, d["livre"], d["limite_min"])

    novos_pausados: list[str] = []
    if downloads_ativos:
        logger.info("Pausando %d downloads ativos...", len(downloads_ativos))
        for t in downloads_ativos:
            try:
                try:
                    client.torrents_set_force_start(torrent_hashes=t.hash, enable=False)
                    time.sleep(API_THROTTLE_DELAY)
                except Exception as e:
                    logger.debug("Falha ao desativar force_start de %s: %s", t.hash[:16], e)
                client.torrents_pause(torrent_hashes=t.hash)
                novos_pausados.append(t.hash)
                logger.info("  Pausado: %s", t.name[:NOME_TRUNCADO_MAX])
            except Exception as e:
                logger.error("  Falha ao pausar %s: %s", t.name[:30], e)
    else:
        logger.info("Nenhum download em forcedDL para pausar")

    todos_pausados = torrents_pausados_ant | set(novos_pausados)
    discos_criticos = [n for n, d in espacos.items() if d["critico"]]
    registrar_pause_event(conn, run_id, "pause", reason="disk_space",
                          espacos=espacos, hashes=todos_pausados,
                          discos_criticos=discos_criticos)

    logger.info(
        "Total pausados: %d (anteriores: %d, novos: %d)",
        len(todos_pausados), len(torrents_pausados_ant), len(novos_pausados),
    )

    if moving_count > 0:
        logger.info("Recheck em %d torrents MOVING...", moving_count)
        for t in moving_torrents:
            try:
                client.torrents_recheck(torrent_hashes=t.hash)
                time.sleep(API_THROTTLE_DELAY)
            except Exception as e:
                logger.debug("Falha recheck de %s: %s", t.hash[:16], e)

    notificar_se_necessario(conn, run_id, "paused")


# ============================================================================
# SEED CLEANER
# ============================================================================

def executar_seed_cleaner(
    client: qbittorrentapi.Client,
    conn: sqlite3.Connection,
    run_id: int,
    espacos: dict[str, dict[str, Any]],
) -> int:
    """
    Limpa torrents elegíveis por tempo de seeding.
    - Só executa se disco estiver crítico
    - Respeita cross-seed: só deleta quando TODOS os trackers do grupo
      (mesmo nome) satisfizerem o mínimo de dias configurado em TRACKER_RULES
    """
    modo = "DRY RUN" if SEED_CLEANER_DRY_RUN else "DELETANDO DE VERDADE"
    logger.info("=" * 70)
    logger.info("Seed Cleaner [%s]", modo)
    logger.info("=" * 70)

    discos_criticos = [nome for nome, d in espacos.items() if d["critico"] and d["seed_cleaner"]]
    if not discos_criticos:
        logger.info("Disco p2p com espaco suficiente - seed cleaner nao necessario")
        return 0

    logger.info("Disco critico: %s - iniciando limpeza...", ", ".join(discos_criticos))

    if not TRACKER_RULES:
        logger.warning("TRACKER_RULES vazio - pulando seed cleaner")
        return 0

    # Coletar torrents com regras aplicáveis
    torrent_data: list[dict[str, Any]] = []
    for t in client.torrents_info():
        seeding_days = getattr(t, "seeding_time", 0) / 86400
        try:
            trackers = client.torrents_trackers(t.hash)
        except Exception as e:
            logger.debug("Falha ao obter trackers de %s: %s", t.hash[:16], e)
            trackers = []

        rules = get_tracker_rules_for_torrent(trackers)
        if not rules:
            continue

        torrent_data.append({
            "hash": t.hash,
            "name": t.name,
            "seeding_days": seeding_days,
            "size": getattr(t, "size", 0),
            "rules": rules,
        })

    # Agrupar por nome para detectar cross-seeds
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for t in torrent_data:
        groups[t["name"]].append(t)

    to_delete: list[dict[str, Any]] = []
    kept_crossseed: list[dict[str, Any]] = []

    for name, group in groups.items():
        all_satisfied = True
        details: list[dict[str, Any]] = []

        for t in group:
            for domain, required_days in t["rules"]:
                satisfied = t["seeding_days"] >= required_days
                details.append({
                    "torrent": t,
                    "domain": domain,
                    "required": required_days,
                    "actual": t["seeding_days"],
                    "satisfied": satisfied,
                })
                if not satisfied:
                    all_satisfied = False

        if all_satisfied and details:
            for t in group:
                rule_days = [d for _, d in t["rules"]]
                max_rule = max(rule_days) if rule_days else 0
                to_delete.append({
                    "hash": t["hash"],
                    "name": t["name"],
                    "days": t["seeding_days"],
                    "rule": max_rule,
                    "size": t["size"],
                    "tracker": ", ".join(set(d for d, _ in t["rules"])),
                    "group_size": len(group),
                })
        else:
            # Cross-seed: marcar os que já satisfazem mas estão bloqueados
            unsatisfied = [d for d in details if not d["satisfied"]]
            for t in group:
                rule_days = [d for _, d in t["rules"]]
                max_rule = max(rule_days) if rule_days else 0
                if t["seeding_days"] >= max_rule:
                    kept_crossseed.append({
                        "name": t["name"],
                        "days": t["seeding_days"],
                        "rule": max_rule,
                        "tracker": ", ".join(set(d for d, _ in t["rules"])),
                        "blocking": [
                            f"{d['domain']}({d['actual']:.1f}d/{d['required']}d)"
                            for d in unsatisfied
                        ],
                    })

    logger.info("Elegiveis para delecao: %d", len(to_delete))

    if to_delete:
        logger.info("%-35s %7s %6s  NOME", "TRACKER", "SEED", "REGRA")
        logger.info("-" * 100)
        for t in sorted(to_delete, key=lambda x: x["tracker"]):
            cross = f" [x{t['group_size']}]" if t["group_size"] > 1 else ""
            size_gb = t["size"] / (1024 ** 3)
            logger.info(
                "%-35s %6.1fd %5dd%s  %s  (%.1f GB)",
                t["tracker"], t["days"], t["rule"], cross,
                t["name"][:NOME_TRUNCADO_MAX], size_gb,
            )

    if kept_crossseed:
        logger.info("Mantidos por cross-seed (%d):", len(kept_crossseed))
        for t in sorted(kept_crossseed, key=lambda x: x["tracker"]):
            logger.info(
                "  %-35s %6.1fd  %s  | aguardando: %s",
                t["tracker"], t["days"],
                t["name"][:NOME_TRUNCADO_MAX], ", ".join(t["blocking"]),
            )

    if SEED_CLEANER_DRY_RUN:
        # Dry run: registra tudo no banco mas não apaga nada
        if to_delete:
            salvar_seed_deletions(conn, run_id, to_delete)
            logger.info("DRY RUN - mude SEED_CLEANER_DRY_RUN = False no config.py para apagar de verdade")
        return len(to_delete)

    # Deleção real: um por um com commit individual no banco
    if not to_delete:
        return 0

    logger.info("Deletando %d torrents...", len(to_delete))
    deletados_confirmados: list[dict[str, Any]] = []
    falhas: list[dict[str, Any]] = []

    for t in to_delete:
        try:
            client.torrents_delete(delete_files=True, torrent_hashes=t["hash"])
            # Só salva no banco após confirmação da API
            salvar_seed_deletions(conn, run_id, [t])
            size_gb = t["size"] / (1024 ** 3)
            logger.info("  Deletado: %s  (%.1f GB)", t["name"][:NOME_TRUNCADO_MAX], size_gb)
            deletados_confirmados.append(t)
        except Exception as e:
            logger.error("  Falha ao deletar %s: %s", t["name"][:NOME_TRUNCADO_MAX], e)
            falhas.append(t)
        time.sleep(DELETE_DELAY)

    total_gb = sum(t["size"] for t in deletados_confirmados) / (1024 ** 3)
    logger.info("%d deletados (%.1f GB liberados)", len(deletados_confirmados), total_gb)
    if falhas:
        logger.error("%d falhas na delecao", len(falhas))

    if deletados_confirmados:
        logger.info("Aguardando %d segundos para o sistema processar as delecoes...", POST_DELETE_WAIT)
        time.sleep(POST_DELETE_WAIT)

    return len(deletados_confirmados)

# ============================================================================
# RESTAURACAO
# ============================================================================

def executar_restauracao(
    client: qbittorrentapi.Client,
    conn: sqlite3.Connection,
    run_id: int,
    espacos: dict[str, dict[str, Any]],
) -> None:
    """Restaura torrents previamente pausados quando condições normalizam."""
    torrents_pausados = ler_torrents_pausados(conn)
    if not torrents_pausados:
        return

    logger.info("Condicoes normalizadas - restaurando %d downloads...", len(torrents_pausados))
    restored = failed = 0

    for h in torrents_pausados:
        try:
            info = client.torrents_info(torrent_hashes=h)
            if not info:
                failed += 1
                continue
            client.torrents_resume(torrent_hashes=h)
            time.sleep(API_THROTTLE_DELAY)
            try:
                client.torrents_set_force_start(torrent_hashes=h, enable=True)
                logger.info("  Restaurado: %s [FORCE]", info[0].name[:NOME_TRUNCADO_MAX])
            except Exception as e:
                logger.debug("Falha force_start ao restaurar %s: %s", h[:16], e)
                logger.info("  Restaurado: %s", info[0].name[:NOME_TRUNCADO_MAX])
            restored += 1
        except Exception as e:
            logger.error("  Falha ao restaurar %s: %s", h[:16], e)
            failed += 1

    registrar_pause_event(conn, run_id, "restore", espacos=espacos, hashes=torrents_pausados)

    logger.info("Restaurados: %d%s", restored, f"  Falhas: {failed}" if failed else "")
    notificar_se_necessario(conn, run_id, "restored")

# ============================================================================
# GERENCIAMENTO DE TRACKERS
# ============================================================================

def analisar_torrents_por_tracker(client: qbittorrentapi.Client) -> dict[str, dict[str, list[dict[str, Any]]]]:
    """Analisa e agrupa torrents por tracker e estado."""
    tracker_analise: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(lambda: {
        "downloading_ativo": [], "downloading_fila": [],
        "paused": [], "seeding": [], "outros": [],
    })
    for t in client.torrents_info():
        tracker_principal = "no_tracker"
        try:
            for tr in client.torrents_trackers(t.hash):
                if tr.url and not tr.url.startswith("**"):
                    tracker_principal = extrair_dominio_tracker(tr.url)
                    break
        except Exception as e:
            logger.debug("Erro ao obter trackers de %s: %s", t.hash[:16], e)

        info: dict[str, Any] = {
            "nome": t.name[:NOME_TRUNCADO_MAX] + ("..." if len(t.name) > NOME_TRUNCADO_MAX else ""),
            "hash": t.hash,
            "state": t.state,
            "dlspeed": getattr(t, "dlspeed", 0),
            "force_start": getattr(t, "force_start", False),
        }
        state = t.state
        dlspeed = info["dlspeed"]

        if state == "forcedDL":
            tracker_analise[tracker_principal]["downloading_ativo"].append(info)
        elif state == "downloading" and dlspeed > 0:
            tracker_analise[tracker_principal]["downloading_ativo"].append(info)
        elif state in ("downloading", "stalledDL", "queuedDL", "checkingDL"):
            tracker_analise[tracker_principal]["downloading_fila"].append(info)
        elif state in ("pausedDL", "pausedUP"):
            tracker_analise[tracker_principal]["paused"].append(info)
        elif state in ("uploading", "stalledUP", "queuedUP", "checkingUP", "forcedUP"):
            tracker_analise[tracker_principal]["seeding"].append(info)
        else:
            tracker_analise[tracker_principal]["outros"].append(info)

    return dict(tracker_analise)


def gerenciar_trackers(client: qbittorrentapi.Client) -> tuple[int, int]:
    """Gerencia downloads mínimos por tracker."""
    logger.info("=" * 70)
    logger.info("Gerenciamento de Trackers")
    logger.info("=" * 70)

    total_forcados = total_ativados = 0

    for tracker, dados in sorted(analisar_torrents_por_tracker(client).items()):
        ativo_count = len(dados["downloading_ativo"])
        fila_count = len(dados["downloading_fila"])
        paused_count = len(dados["paused"])
        total_count = (ativo_count + fila_count + paused_count +
                       len(dados["seeding"]) + len(dados["outros"]))

        logger.info(
            "%s: Ativo=%d  Fila=%d  Pausados=%d  Seeding=%d  Total=%d",
            tracker, ativo_count, fila_count, paused_count, len(dados["seeding"]), total_count,
        )

        if ativo_count >= MIN_DOWNLOADS_PER_TRACKER:
            logger.info("  OK (%d >= %d)", ativo_count, MIN_DOWNLOADS_PER_TRACKER)
            continue

        if total_count < MIN_TORRENTS_PER_TRACKER and ativo_count > 0:
            logger.info("  Tracker pequeno com %d ativo(s) - IGNORANDO", ativo_count)
            continue

        if total_count < MIN_TORRENTS_PER_TRACKER and ativo_count == 0:
            logger.info("  Tracker pequeno sem ativos - ATIVANDO")

        necessarios = MIN_DOWNLOADS_PER_TRACKER - ativo_count
        logger.info("  PRECISA: +%d", necessarios)

        for info in dados["downloading_fila"][:necessarios]:
            try:
                client.torrents_set_force_start(torrent_hashes=info["hash"], enable=True)
                logger.info("    FORCE: %s", info["nome"])
                total_forcados += 1
                necessarios -= 1
            except Exception as e:
                logger.error("    Falha: %s", e)
            if necessarios <= 0:
                break

        for info in dados["paused"][:necessarios]:
            try:
                client.torrents_resume(torrent_hashes=info["hash"])
                try:
                    client.torrents_set_force_start(torrent_hashes=info["hash"], enable=True)
                    logger.info("    ATIVAR+FORCE: %s", info["nome"])
                except Exception as e:
                    logger.debug("Falha force_start ao ativar %s: %s", info["hash"][:16], e)
                    logger.info("    ATIVAR: %s", info["nome"])
                total_ativados += 1
                necessarios -= 1
            except Exception as e:
                logger.error("    Falha: %s", e)
            if necessarios <= 0:
                break

    logger.info("Trackers - Forcados: %d  Ativados: %d", total_forcados, total_ativados)
    return total_forcados, total_ativados

# ============================================================================
# MAIN
# ============================================================================

def main() -> None:
    """Ponto de entrada principal do gerenciador."""
    logger.info("qBittorrent Unified Manager")
    logger.info("=" * 70)

    # Inicializar banco
    conn = init_db()
    logger.info("Banco: %s", DB_PATH)

    # Conectar ao qBittorrent
    client = qbittorrentapi.Client(
        host=QB_URL,
        username=QB_USER,
        password=QB_PASS,
        REQUESTS_ARGS={"timeout": CONNECT_TIMEOUT},
    )
    try:
        client.auth_log_in()
        logger.info("Conectado ao qBittorrent")
    except qbittorrentapi.LoginFailed:
        logger.error("Falha ao autenticar no qBittorrent")
        enviar_notificacao("qBittorrent - Erro de Autenticacao", f"Falha em {QB_URL}", priority=1)
        conn.close()
        sys.exit(1)
    except Exception as e:
        logger.error("Erro ao conectar: %s", e)
        enviar_notificacao("qBittorrent - Erro de Conexao", f"{QB_URL}\n\n{e}", priority=1)
        conn.close()
        sys.exit(1)

    # ------------------------------------------------------------------
    # PASSO 1: Ler último estado do banco
    # ------------------------------------------------------------------
    ultimo_estado = ler_ultimo_estado(conn)
    tinha_pausados = bool(ultimo_estado["torrents_pausados"])

    logger.info("Ultimo estado: %s", ultimo_estado["run_status"].upper())
    if tinha_pausados:
        logger.info(
            "%d torrents pausados desde ultima execucao",
            len(ultimo_estado["torrents_pausados"]),
        )
        if ultimo_estado["motivo_pausa"]:
            logger.info("Motivo: %s", ", ".join(ultimo_estado["motivo_pausa"]))

    # ------------------------------------------------------------------
    # PASSO 2: Coletar estado atual
    # ------------------------------------------------------------------
    logger.info("Estado atual:")
    espacos = verificar_espacos()
    imprimir_espacos(espacos)

    checking_count, moving_count, checking_torrents, moving_torrents = obter_contagem_checking_moving(client)
    checking_moving_total = checking_count + moving_count
    logger.info("Checking: %d  Moving: %d  Total: %d", checking_count, moving_count, checking_moving_total)

    qualquer_critico = any(d["critico"] and d["pause_trigger"] for d in espacos.values())
    todos_ok = all(d["ok"] for d in espacos.values() if d["pause_trigger"])
    checking_moving_zero = checking_moving_total == 0

    # Disco crítico apenas para seed cleaner (p2p)
    critico_seed_cleaner = any(d["critico"] and d["seed_cleaner"] for d in espacos.values())
    pode_restaurar = todos_ok and checking_moving_zero

    # ------------------------------------------------------------------
    # PASSO 3: Criar registro do run
    # ------------------------------------------------------------------
    run_status = "paused" if (tinha_pausados or qualquer_critico) else "active"
    run_id = criar_run(conn, run_status, checking_count, moving_count,
                       espacos, len(ultimo_estado["torrents_pausados"]))

    # ------------------------------------------------------------------
    # PASSO 4: Snapshot de torrents
    # ------------------------------------------------------------------
    logger.info("Salvando snapshot...")
    todos_torrents = client.torrents_info()
    tracker_map = construir_tracker_map(client, todos_torrents)
    salvar_snapshots(conn, run_id, todos_torrents, tracker_map)

    # ------------------------------------------------------------------
    # PASSO 5: Lógica principal baseada no estado anterior
    # ------------------------------------------------------------------
    forcados_checking = 0
    seeding_deletados = 0
    total_forcados = 0
    total_ativados = 0
    pode_gerenciar_trackers = False

    if tinha_pausados:
        # -- Havia torrents pausados: verificar se pode restaurar --
        logger.info("Sistema estava pausado - verificando condicoes para restaurar...")

        # Discos que causaram a pausa (registrado no banco na execução anterior)
        discos_criticos_registro = ultimo_estado["discos_criticos"]

        if discos_criticos_registro is None:
            # Sem informação de qual disco causou a pausa — notificar e aguardar
            logger.warning("Sem informacao do disco que causou a pausa - verificacao manual necessaria")
            notificar_se_necessario(conn, run_id, "waiting_paused")
            registrar_pause_event(conn, run_id, "waiting",
                                  espacos=espacos,
                                  hashes=ultimo_estado["torrents_pausados"])
            forcados_checking = forcar_start_checking(client, checking_torrents)

        elif pode_restaurar:
            # Condições normalizaram: restaurar
            executar_restauracao(client, conn, run_id, espacos)
            forcados_checking = forcar_start_checking(client, checking_torrents)
            pode_gerenciar_trackers = True

        else:
            # Ainda não pode restaurar — decidir com base no disco registrado no banco
            logger.warning("Ainda nao e possivel restaurar:")
            logger.warning("  Disco(s) que causaram pausa: %s", ", ".join(discos_criticos_registro))

            for nome, d in espacos.items():
                if d["pause_trigger"]:
                    status = "CRITICO" if d["critico"] else "OK"
                    logger.info(
                        "  [%s] %s: %.1f GB (min: %s, max: %s)",
                        status, nome, d["livre"], d["limite_min"], d["limite_max"],
                    )

            if not checking_moving_zero:
                logger.warning("  Checking+Moving ainda ativo (%d)", checking_moving_total)

            # Decisão baseada no tipo de disco que causou a pausa
            pausa_por_p2p = any(espacos[n]["seed_cleaner"]
                                for n in discos_criticos_registro if n in espacos)
            pausa_por_destino = any(not espacos[n]["seed_cleaner"]
                                    for n in discos_criticos_registro if n in espacos)

            if pausa_por_p2p and critico_seed_cleaner:
                # p2p ainda crítico — seed cleaner pode ajudar
                logger.info("Pausa causada pelo p2p - tentando seed cleaner...")
                seeding_deletados = executar_seed_cleaner(client, conn, run_id, espacos)

                if seeding_deletados > 0 and not SEED_CLEANER_DRY_RUN:
                    logger.info("Reavaliando espaco apos seed cleaner...")
                    espacos = verificar_espacos()
                    imprimir_espacos(espacos)
                    todos_ok = all(d["ok"] for d in espacos.values() if d["pause_trigger"])
                    critico_seed_cleaner = any(d["critico"] and d["seed_cleaner"] for d in espacos.values())
                    pode_restaurar = todos_ok and checking_moving_zero

                    if pode_restaurar:
                        executar_restauracao(client, conn, run_id, espacos)
                        forcados_checking = forcar_start_checking(client, checking_torrents)
                        pode_gerenciar_trackers = True
                    else:
                        logger.warning("Espaco ainda insuficiente - mantendo pausa")
                        registrar_pause_event(conn, run_id, "waiting",
                                              espacos=espacos,
                                              hashes=ultimo_estado["torrents_pausados"],
                                              discos_criticos=discos_criticos_registro)
                        notificar_se_necessario(conn, run_id, "waiting_paused")
                else:
                    registrar_pause_event(conn, run_id, "waiting",
                                          espacos=espacos,
                                          hashes=ultimo_estado["torrents_pausados"],
                                          discos_criticos=discos_criticos_registro)
                    notificar_se_necessario(conn, run_id, "waiting_paused")

            elif pausa_por_destino and not pausa_por_p2p:
                # Apenas disco de destino — seed cleaner não resolve, aguarda Radarr/Sonarr
                destinos = [n for n in discos_criticos_registro
                            if n in espacos and not espacos[n]["seed_cleaner"]]
                logger.info(
                    "Pausa causada pelo disco de destino (%s) - aguardando Radarr/Sonarr liberar espaco...",
                    ", ".join(destinos),
                )
                registrar_pause_event(conn, run_id, "waiting",
                                      espacos=espacos,
                                      hashes=ultimo_estado["torrents_pausados"],
                                      discos_criticos=discos_criticos_registro)
                notificar_se_necessario(conn, run_id, "waiting_paused")

            else:
                # Disco normalizado mas checking/moving ainda alto — aguarda
                logger.info("Disco normalizado mas checking/moving ainda ativo - aguardando...")
                registrar_pause_event(conn, run_id, "waiting",
                                      espacos=espacos,
                                      hashes=ultimo_estado["torrents_pausados"],
                                      discos_criticos=discos_criticos_registro)
                notificar_se_necessario(conn, run_id, "waiting_paused")

            forcados_checking = forcar_start_checking(client, checking_torrents)

    else:
        # -- Sem pausados: fluxo normal --
        if qualquer_critico:
            # Disco pause_trigger crítico: tentar seed cleaner do p2p antes de pausar
            seeding_deletados = executar_seed_cleaner(client, conn, run_id, espacos)

            if seeding_deletados > 0 and not SEED_CLEANER_DRY_RUN:
                logger.info("Reavaliando espaco apos seed cleaner...")
                espacos = verificar_espacos()
                imprimir_espacos(espacos)
                qualquer_critico = any(d["critico"] and d["pause_trigger"] for d in espacos.values())

            if qualquer_critico:
                # Ainda crítico: pausar
                forcados_checking = forcar_start_checking(client, checking_torrents)
                executar_pausa(client, conn, run_id, espacos, moving_count, moving_torrents)
            else:
                # Seed cleaner resolveu: seguir normal
                logger.info("Disco normalizado apos seed cleaner - sistema ativo")
                forcados_checking = forcar_start_checking(client, checking_torrents)
                pode_gerenciar_trackers = True

        else:
            # Tudo ok: force checking + gerenciar trackers
            forcados_checking = forcar_start_checking(client, checking_torrents)
            pode_gerenciar_trackers = True

    # ------------------------------------------------------------------
    # PASSO 6: Gerenciar trackers
    # ------------------------------------------------------------------
    if pode_gerenciar_trackers:
        total_forcados, total_ativados = gerenciar_trackers(client)
    else:
        logger.info("Gerenciamento de trackers PAUSADO")

    # ------------------------------------------------------------------
    # PASSO 7: Fechar run
    # ------------------------------------------------------------------
    atualizar_run(conn, run_id,
                  status="active" if pode_gerenciar_trackers else "paused",
                  forcados_checking=forcados_checking,
                  tracker_forcados=total_forcados,
                  tracker_ativados=total_ativados,
                  seeding_deletados=seeding_deletados,
                  paused_count=len(ler_torrents_pausados(conn)))

    # Resumo
    logger.info("=" * 70)
    logger.info("RESUMO FINAL:")
    pausados_final = ler_torrents_pausados(conn)
    if pausados_final:
        logger.info("Sistema PAUSADO (%d torrents)", len(pausados_final))
        motivos = ler_motivo_pausa(conn)
        if motivos:
            logger.info("Motivo: %s", ", ".join(motivos))
    else:
        logger.info("Sistema ATIVO")

    logger.info("Checking+Moving: %d", checking_moving_total)
    if forcados_checking:
        logger.info("Force start checking: %d", forcados_checking)
    if seeding_deletados:
        modo = "DRY RUN" if SEED_CLEANER_DRY_RUN else "deletados"
        logger.info("Seed cleaner: %d (%s)", seeding_deletados, modo)
    if total_forcados or total_ativados:
        logger.info("Trackers - Forcados: %d  Ativados: %d", total_forcados, total_ativados)

    logger.info("Run #%d - %s", run_id, DB_PATH)
    logger.info("=" * 70)
    conn.close()


if __name__ == "__main__":
    main()
