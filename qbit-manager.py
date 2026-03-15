#!/usr/bin/env python3

# qbit-manager.py — Entry point
# Gerenciamento modular: checagem de disco -> limpeza -> ativacao
#
# Diretorios:
#   CONFIG_DIR  → /etc/qbit-manager           (config.py, tracker_rules.py)
#   INSTALL_DIR → /usr/local/lib/qbit-manager  (este script + pasta modulos/)
#   DB_DIR      → /var/lib/qbit-manager        (qbit.db)
#
# Todos configuraveis via config.py

import os
import sys
import qbittorrentapi

# ── 1. Carregar config.py ────────────────────────────────────────────────────
# CONFIG_DIR: onde fica o config.py (credenciais, discos, regras)
CONFIG_DIR = "/etc/qbit-manager"

if CONFIG_DIR not in sys.path:
    sys.path.insert(0, CONFIG_DIR)

try:
    from config import *
except ImportError:
    print(f"⚠️  Crie um arquivo config.py em {CONFIG_DIR}!")
    print(f"   Copie o template: sudo cp config.py {CONFIG_DIR}/config.py")
    QB_URL                    = 'https://torrent.exemplo.com'
    QB_USER                   = 'admin'
    QB_PASS                   = 'senha'
    PUSHOVER_TOKEN            = 'token'
    PUSHOVER_USER             = 'user'
    MIN_DOWNLOADS_PER_TRACKER = 4
    MIN_TORRENTS_PER_TRACKER  = 4
    SEED_CLEANER_DRY_RUN      = True
    INSTALL_DIR               = os.path.dirname(os.path.abspath(__file__))
    PATHS = {
        "p2p": {
            "path":        "/mnt/p2p/",
            "limite_min":  100,
            "limite_max":  150,
            "seed_cleaner": True,
            "pause_trigger": True
        },
        "videos": {
            "path":        "/mnt/videos/",
            "limite_min":  200,
            "limite_max":  250,
            "seed_cleaner": False,
            "pause_trigger": True
        }
    }
    TRACKER_RULES = {}

# ── 2. Resolver INSTALL_DIR (onde estao os modulos) ──────────────────────────
# Se definido no config.py, usa esse valor. Senao, usa o diretorio deste script.
try:
    INSTALL_DIR
except NameError:
    INSTALL_DIR = os.path.dirname(os.path.abspath(__file__))

# Adicionar INSTALL_DIR ao path para encontrar a pasta modulos/
if INSTALL_DIR not in sys.path:
    sys.path.insert(0, INSTALL_DIR)

# ── 3. Importar tracker_rules.py separado (opcional, sobrescreve config) ─────
try:
    from tracker_rules import TRACKER_RULES
    print("✅ Regras de tracker carregadas de tracker_rules.py")
except ImportError:
    pass

# ── 4. Fallback para DB_DIR/DB_PATH ─────────────────────────────────────────
try:
    DB_DIR
except NameError:
    DB_DIR = "/var/lib/qbit-manager"
try:
    DB_PATH
except NameError:
    DB_PATH = f"{DB_DIR}/qbit.db"

# ── 5. Importar modulos internos (de INSTALL_DIR/modulos/) ──────────────────
from modulos.db import init_db
from modulos.otel import configurar_otel
from modulos.checagem_disco import executar_checagem
from modulos.notificacao import criar_notificador

# ── 6. Criar notificador a partir do config ─────────────────────────────────
try:
    _notif_tipo = NOTIFICACAO_TIPO
except NameError:
    _notif_tipo = "nenhum"
try:
    _notif_config = NOTIFICACAO_CONFIG
except NameError:
    _notif_config = {}

enviar_notificacao = criar_notificador(_notif_tipo, _notif_config)


def main():
    print("🚀 qBittorrent Manager (Modular)")
    print("=" * 70)

    # Configurar OTEL (se definido no config.py)
    otel_endpoint = getattr(sys.modules.get('config'), 'OTEL_ENDPOINT', None)
    otel_service  = getattr(sys.modules.get('config'), 'OTEL_SERVICE_NAME', 'qbit-manager')
    otel_enabled  = getattr(sys.modules.get('config'), 'OTEL_ENABLED', False)

    # Tambem aceita variaveis globais importadas via `from config import *`
    if otel_endpoint is None:
        otel_endpoint = globals().get('OTEL_ENDPOINT')
    if otel_enabled is False:
        otel_enabled = globals().get('OTEL_ENABLED', False)

    configurar_otel(
        endpoint=otel_endpoint,
        service_name=otel_service,
        enabled=otel_enabled,
    )

    # Inicializar banco
    conn = init_db(DB_DIR, DB_PATH)
    print(f"✅ Banco: {DB_PATH}")

    # Conectar ao qBittorrent
    client = qbittorrentapi.Client(host=QB_URL, username=QB_USER, password=QB_PASS)
    try:
        client.auth_log_in()
        print("✅ Conectado ao qBittorrent")
    except qbittorrentapi.LoginFailed:
        print("❌ Falha ao autenticar")
        enviar_notificacao("❌ qBittorrent - Erro de Autenticação", f"Falha em {QB_URL}", priority=1)
        conn.close()
        sys.exit(1)
    except Exception as e:
        print(f"❌ Erro ao conectar: {e}")
        enviar_notificacao("❌ qBittorrent - Erro de Conexão", f"{QB_URL}\n\n{e}", priority=1)
        conn.close()
        sys.exit(1)

    # Executar checagem de disco (orquestrador principal)
    run_id = executar_checagem(
        client=client,
        conn=conn,
        paths_config=PATHS,
        tracker_rules=TRACKER_RULES,
        seed_cleaner_dry_run=SEED_CLEANER_DRY_RUN,
        min_downloads_per_tracker=MIN_DOWNLOADS_PER_TRACKER,
        min_torrents_per_tracker=MIN_TORRENTS_PER_TRACKER,
        enviar_notificacao_fn=enviar_notificacao,
    )

    print(f"🗄️  {DB_PATH}")
    print("=" * 70)
    conn.close()


if __name__ == "__main__":
    main()
