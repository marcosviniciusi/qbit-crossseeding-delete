#!/usr/bin/env python3

# qbit-manager.py — Entry point unico
#
# Uso:
#   python3 qbit-manager.py                         # execucao normal (cron)
#   python3 qbit-manager.py --check-disk            # verificar espaco em disco
#   python3 qbit-manager.py --check-torrent         # listar torrents elegiveis a remocao
#   python3 qbit-manager.py --erase-torrent         # executar seed cleaner (respeita seed/cross-seed)
#   python3 qbit-manager.py --tracker-list          # gerar bloco TRACKER_RULES
#   python3 qbit-manager.py --test-notification     # testar envio de notificacao
#   python3 qbit-manager.py --check-send-log        # testar envio de log ao OTEL
#   python3 qbit-manager.py --check-config          # validar configuracao
#
# Flags globais:
#   --config PATH     # caminho do diretorio de configuracao (padrao: /etc/qbit-manager)
#   --modules PATH    # caminho do diretorio dos modulos (sobrescreve INSTALL_DIR do config)

import os
import sys
import argparse


def _parse_args():
    parser = argparse.ArgumentParser(
        prog="qbit-manager",
        description="qBittorrent Manager — gerenciamento automatizado via cron",
    )
    parser.add_argument(
        "--config", metavar="PATH", default=None,
        help="Caminho do diretório de configuração (padrão: /etc/qbit-manager)"
    )
    parser.add_argument(
        "--modules", metavar="PATH", default=None,
        help="Caminho do diretório dos módulos (sobrescreve INSTALL_DIR do config)"
    )

    # Subcomandos (mutuamente exclusivos)
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--check-disk", action="store_true",
        help="Verificar espaço em disco sem executar nenhuma ação"
    )
    group.add_argument(
        "--check-torrent", action="store_true",
        help="Listar torrents elegíveis para remoção (dry run)"
    )
    group.add_argument(
        "--erase-torrent", action="store_true",
        help="Executar seed cleaner (respeita tempo de seed e cross-seed)"
    )
    group.add_argument(
        "--tracker-list", action="store_true",
        help="Gerar bloco TRACKER_RULES a partir dos torrents atuais"
    )
    group.add_argument(
        "--test-notification", action="store_true",
        help="Enviar notificação de teste"
    )
    group.add_argument(
        "--check-send-log", action="store_true",
        help="Testar envio de log ao OTEL Collector"
    )
    group.add_argument(
        "--check-config", action="store_true",
        help="Validar se a configuração está correta"
    )

    return parser.parse_args()


def _carregar_config(config_dir):
    """Carrega config.py e tracker_rules.py do diretorio especificado."""
    if config_dir not in sys.path:
        sys.path.insert(0, config_dir)

    cfg = {}
    try:
        import config as _cfg_mod
        for attr in dir(_cfg_mod):
            if not attr.startswith("_"):
                cfg[attr] = getattr(_cfg_mod, attr)
    except ImportError:
        print(f"⚠️  config.py não encontrado em {config_dir}")
        print(f"   Copie o template: sudo cp config.py {config_dir}/config.py")

    # Defaults
    cfg.setdefault("QB_URL",                    "https://torrent.exemplo.com")
    cfg.setdefault("QB_USER",                   "admin")
    cfg.setdefault("QB_PASS",                   "senha")
    cfg.setdefault("MIN_DOWNLOADS_PER_TRACKER", 4)
    cfg.setdefault("MIN_TORRENTS_PER_TRACKER",  4)
    cfg.setdefault("SEED_CLEANER_DRY_RUN",      True)
    cfg.setdefault("INSTALL_DIR",               os.path.dirname(os.path.abspath(__file__)))
    cfg.setdefault("DB_DIR",                    "/var/lib/qbit-manager")
    cfg.setdefault("DB_PATH",                   f"{cfg['DB_DIR']}/qbit.db")
    cfg.setdefault("NOTIFICACAO_TIPO",          "nenhum")
    cfg.setdefault("NOTIFICACAO_CONFIG",        {})
    cfg.setdefault("OTEL_ENDPOINT",             None)
    cfg.setdefault("OTEL_SERVICE_NAME",         "qbit-manager")
    cfg.setdefault("OTEL_ENABLED",              False)
    cfg.setdefault("PATHS", {
        "p2p": {
            "path": "/mnt/p2p/", "limite_min": 100, "limite_max": 150,
            "seed_cleaner": True, "pause_trigger": True
        },
        "videos": {
            "path": "/mnt/videos/", "limite_min": 200, "limite_max": 250,
            "seed_cleaner": False, "pause_trigger": True
        }
    })
    cfg.setdefault("TRACKER_RULES", {})

    # Importar tracker_rules.py separado (sobrescreve config se existir)
    try:
        from tracker_rules import TRACKER_RULES
        cfg["TRACKER_RULES"] = TRACKER_RULES
    except ImportError:
        pass

    return cfg


def _setup_modules(cfg, modules_override=None):
    """Adiciona INSTALL_DIR ao sys.path para encontrar modulos/."""
    install_dir = modules_override or cfg["INSTALL_DIR"]
    if install_dir not in sys.path:
        sys.path.insert(0, install_dir)
    return install_dir


def _conectar_qbittorrent(cfg, enviar_notificacao):
    """Conecta ao qBittorrent e retorna o client autenticado."""
    import qbittorrentapi
    client = qbittorrentapi.Client(
        host=cfg["QB_URL"], username=cfg["QB_USER"], password=cfg["QB_PASS"]
    )
    try:
        client.auth_log_in()
        print("✅ Conectado ao qBittorrent")
        return client
    except qbittorrentapi.LoginFailed:
        print("❌ Falha ao autenticar")
        enviar_notificacao("❌ qBittorrent - Erro de Autenticação",
                           f"Falha em {cfg['QB_URL']}", priority=1)
        sys.exit(1)
    except Exception as e:
        print(f"❌ Erro ao conectar: {e}")
        enviar_notificacao("❌ qBittorrent - Erro de Conexão",
                           f"{cfg['QB_URL']}\n\n{e}", priority=1)
        sys.exit(1)


# ==========================================================================
# SUBCOMANDOS
# ==========================================================================

def cmd_check_config(cfg, config_dir):
    """Valida se a configuração está correta."""
    print("🔍 Verificando configuração...")
    print("=" * 60)
    print(f"   CONFIG_DIR:  {config_dir}")
    print(f"   INSTALL_DIR: {cfg['INSTALL_DIR']}")
    print(f"   DB_DIR:      {cfg['DB_DIR']}")
    print(f"   DB_PATH:     {cfg['DB_PATH']}")
    print()

    erros = []

    # qBittorrent
    print("── qBittorrent ──")
    print(f"   URL:  {cfg['QB_URL']}")
    print(f"   User: {cfg['QB_USER']}")
    print(f"   Pass: {'*' * len(cfg['QB_PASS'])}")
    if cfg["QB_URL"] in ("https://torrent.exemplo.com", "http://torrent.seudominio.com:PORTA"):
        erros.append("QB_URL está com valor de exemplo — ajuste para o endereço real")
    if cfg["QB_PASS"] == "sua_senha_aqui":
        erros.append("QB_PASS está com valor de exemplo — ajuste para a senha real")
    print()

    # Discos
    print("── Discos monitorados ──")
    for nome, disco in cfg["PATHS"].items():
        paths = disco["path"] if isinstance(disco["path"], list) else [disco["path"]]
        for p in paths:
            existe = os.path.isdir(p)
            icon = "✅" if existe else "❌"
            print(f"   {icon} {nome}: {p} (min: {disco['limite_min']} GB, max: {disco['limite_max']} GB)")
            if not existe:
                erros.append(f"Disco '{nome}' path '{p}' não existe")
        flags = []
        if disco.get("seed_cleaner"):
            flags.append("seed_cleaner")
        if disco.get("pause_trigger"):
            flags.append("pause_trigger")
        print(f"      Flags: {', '.join(flags) if flags else 'nenhuma'}")
    print()

    # Tracker Rules
    print("── Tracker Rules ──")
    if cfg["TRACKER_RULES"]:
        for tracker, days in cfg["TRACKER_RULES"].items():
            print(f"   {tracker}: {days} dias")
    else:
        print("   ⚠️  TRACKER_RULES vazio — seed cleaner não terá regras")
    print()

    # Seed Cleaner
    print("── Seed Cleaner ──")
    print(f"   DRY_RUN: {cfg['SEED_CLEANER_DRY_RUN']}")
    print()

    # Notificações
    print("── Notificações ──")
    print(f"   Tipo: {cfg['NOTIFICACAO_TIPO']}")
    if cfg["NOTIFICACAO_TIPO"] != "nenhum":
        for k, v in cfg["NOTIFICACAO_CONFIG"].items():
            valor = str(v)
            if "token" in k.lower() or "key" in k.lower():
                valor = valor[:8] + "..." if len(valor) > 8 else "***"
            print(f"   {k}: {valor}")
    print()

    # OTEL
    print("── OpenTelemetry ──")
    print(f"   Enabled:  {cfg['OTEL_ENABLED']}")
    print(f"   Endpoint: {cfg['OTEL_ENDPOINT'] or '(não configurado)'}")
    print(f"   Service:  {cfg['OTEL_SERVICE_NAME']}")
    print()

    # Modulos
    print("── Módulos ──")
    modulos_dir = os.path.join(cfg["INSTALL_DIR"], "modulos")
    modulos_esperados = [
        "__init__.py", "db.py", "helpers.py", "otel.py", "notificacao.py",
        "limpeza.py", "ativacao.py", "checagem_disco.py", "tracker_list.py"
    ]
    for mod in modulos_esperados:
        caminho = os.path.join(modulos_dir, mod)
        existe = os.path.isfile(caminho)
        icon = "✅" if existe else "❌"
        print(f"   {icon} modulos/{mod}")
        if not existe:
            erros.append(f"Módulo não encontrado: {caminho}")
    print()

    # Resultado
    print("=" * 60)
    if erros:
        print(f"❌ {len(erros)} problema(s) encontrado(s):")
        for e in erros:
            print(f"   • {e}")
    else:
        print("✅ Configuração OK — nenhum problema encontrado")


def cmd_check_disk(cfg):
    """Verifica espaço em disco sem executar nenhuma ação."""
    from modulos.helpers import verificar_espacos, imprimir_espacos

    print("🔍 Verificando espaço em disco...")
    print("=" * 60)
    espacos = verificar_espacos(cfg["PATHS"])
    imprimir_espacos(espacos)

    qualquer_critico = any(d["critico"] and d["pause_trigger"] for d in espacos.values())
    todos_ok         = all(d["ok"] for d in espacos.values() if d["pause_trigger"])

    print()
    if qualquer_critico:
        print("🔴 DISCO CRÍTICO — seed cleaner seria acionado")
    elif todos_ok:
        print("🟢 Todos os discos OK")
    else:
        print("🟡 Discos dentro do limite, mas abaixo do máximo")


def cmd_check_torrent(cfg):
    """Lista torrents elegíveis para remoção (dry run)."""
    from modulos.limpeza import executar_seed_cleaner
    from modulos.db import init_db

    print("🔍 Verificando torrents elegíveis para remoção...")
    print("=" * 60)

    conn   = init_db(cfg["DB_DIR"], cfg["DB_PATH"])
    client = _conectar_qbittorrent(cfg, lambda *a, **kw: None)

    # Forçar dry_run e criar espacos "criticos" pra forçar a execução do seed cleaner
    from modulos.helpers import verificar_espacos
    espacos = verificar_espacos(cfg["PATHS"])

    # Forçar seed_cleaner discos como criticos para listar elegíveis
    espacos_forcar = {}
    for nome, d in espacos.items():
        espacos_forcar[nome] = dict(d)
        if d["seed_cleaner"]:
            espacos_forcar[nome]["critico"] = True

    run_id = 0  # não salva no banco de verdade em check
    executar_seed_cleaner(client, conn, run_id, espacos_forcar,
                          cfg["TRACKER_RULES"], dry_run=True)
    conn.close()


def cmd_erase_torrent(cfg):
    """Executa seed cleaner respeitando tempo de seed e cross-seed."""
    from modulos.limpeza import executar_seed_cleaner
    from modulos.db import init_db
    from modulos.helpers import verificar_espacos

    print("🗑️  Executando seed cleaner...")
    print("=" * 60)

    conn   = init_db(cfg["DB_DIR"], cfg["DB_PATH"])
    client = _conectar_qbittorrent(cfg, lambda *a, **kw: None)
    espacos = verificar_espacos(cfg["PATHS"])

    # Forçar seed_cleaner discos como criticos para executar
    espacos_forcar = {}
    for nome, d in espacos.items():
        espacos_forcar[nome] = dict(d)
        if d["seed_cleaner"]:
            espacos_forcar[nome]["critico"] = True

    from modulos.db import criar_run
    run_id = criar_run(conn, "manual_erase", 0, 0, espacos)

    deletados = executar_seed_cleaner(
        client, conn, run_id, espacos_forcar,
        cfg["TRACKER_RULES"], dry_run=cfg["SEED_CLEANER_DRY_RUN"]
    )

    if cfg["SEED_CLEANER_DRY_RUN"]:
        print(f"\n⚠️  DRY RUN — {deletados} torrents seriam removidos")
        print(f"   Mude SEED_CLEANER_DRY_RUN = False no config.py para apagar de verdade")
    else:
        print(f"\n✅ {deletados} torrents removidos")
    conn.close()


def cmd_tracker_list(cfg):
    """Gera bloco TRACKER_RULES a partir dos torrents atuais."""
    from modulos.tracker_list import gerar_lista_trackers

    print("🔍 Gerando lista de trackers...")
    print("=" * 60)
    client = _conectar_qbittorrent(cfg, lambda *a, **kw: None)
    gerar_lista_trackers(client)


def cmd_test_notification(cfg):
    """Envia notificação de teste."""
    from modulos.notificacao import criar_notificador

    print("📲 Testando notificação...")
    print("=" * 60)
    print(f"   Tipo:   {cfg['NOTIFICACAO_TIPO']}")

    if cfg["NOTIFICACAO_TIPO"] == "nenhum":
        print("   ⚠️  NOTIFICACAO_TIPO = 'nenhum' — nada será enviado")
        print("   Configure um canal no config.py primeiro")
        return

    for k, v in cfg["NOTIFICACAO_CONFIG"].items():
        valor = str(v)
        if "token" in k.lower() or "key" in k.lower():
            valor = valor[:8] + "..." if len(valor) > 8 else "***"
        print(f"   {k}: {valor}")

    enviar = criar_notificador(cfg["NOTIFICACAO_TIPO"], cfg["NOTIFICACAO_CONFIG"])
    print("\n   Enviando mensagem de teste...")
    enviar("qbit-manager — Teste", "Notificação de teste enviada com sucesso!",
           priority=0, event_type="test")
    print("   ✅ Enviado! Verifique seu canal de notificação.")


def cmd_check_send_log(cfg):
    """Testa envio de log ao OTEL Collector."""
    from modulos.otel import configurar_otel, log, flush

    print("📡 Testando envio de log ao OTEL...")
    print("=" * 60)
    print(f"   Enabled:  {cfg['OTEL_ENABLED']}")
    print(f"   Endpoint: {cfg['OTEL_ENDPOINT'] or '(não configurado)'}")
    print(f"   Service:  {cfg['OTEL_SERVICE_NAME']}")

    if not cfg["OTEL_ENABLED"] or not cfg["OTEL_ENDPOINT"]:
        print("\n   ⚠️  OTEL não está habilitado — configure no config.py:")
        print("      OTEL_ENDPOINT = 'http://localhost:4318'")
        print("      OTEL_ENABLED  = True")
        return

    configurar_otel(
        endpoint=cfg["OTEL_ENDPOINT"],
        service_name=cfg["OTEL_SERVICE_NAME"],
        enabled=True,
    )

    print("\n   Acumulando logs de teste no buffer...")
    log("Log de teste 1 — info", level="info", teste=True)
    log("Log de teste 2 — warn", level="warn", teste=True)
    log("Log de teste 3 — completado", level="info", teste=True)

    print("   Enviando bloco para o collector...")
    sucesso = flush()
    if sucesso:
        print("   ✅ Log enviado com sucesso! Verifique seu OTEL Collector.")
    else:
        print("   ❌ Falha ao enviar — verifique o endpoint e conectividade")


# ==========================================================================
# MAIN
# ==========================================================================

def main():
    args = _parse_args()

    # ── Resolver CONFIG_DIR ──────────────────────────────────────────────
    config_dir = args.config or "/etc/qbit-manager"

    # ── Carregar configuração ────────────────────────────────────────────
    cfg = _carregar_config(config_dir)

    # ── Resolver INSTALL_DIR (--modules sobrescreve) ─────────────────────
    _setup_modules(cfg, args.modules)

    # ── Despachar subcomando ─────────────────────────────────────────────
    if args.check_config:
        cmd_check_config(cfg, config_dir)
        return

    if args.check_disk:
        cmd_check_disk(cfg)
        return

    if args.check_torrent:
        cmd_check_torrent(cfg)
        return

    if args.erase_torrent:
        cmd_erase_torrent(cfg)
        return

    if args.tracker_list:
        cmd_tracker_list(cfg)
        return

    if args.test_notification:
        cmd_test_notification(cfg)
        return

    if args.check_send_log:
        cmd_check_send_log(cfg)
        return

    # ── Fluxo principal (execucao normal / cron) ─────────────────────────
    from modulos.db import init_db
    from modulos.otel import configurar_otel, flush as otel_flush
    from modulos.checagem_disco import executar_checagem
    from modulos.notificacao import criar_notificador

    print("🚀 qBittorrent Manager (Modular)")
    print("=" * 70)

    # Configurar OTEL
    configurar_otel(
        endpoint=cfg["OTEL_ENDPOINT"],
        service_name=cfg["OTEL_SERVICE_NAME"],
        enabled=cfg["OTEL_ENABLED"],
    )

    # Notificador
    enviar_notificacao = criar_notificador(
        cfg["NOTIFICACAO_TIPO"], cfg["NOTIFICACAO_CONFIG"]
    )

    # Inicializar banco
    conn = init_db(cfg["DB_DIR"], cfg["DB_PATH"])
    print(f"✅ Banco: {cfg['DB_PATH']}")

    # Conectar ao qBittorrent
    client = _conectar_qbittorrent(cfg, enviar_notificacao)

    # Executar checagem de disco (orquestrador principal)
    run_id = executar_checagem(
        client=client,
        conn=conn,
        paths_config=cfg["PATHS"],
        tracker_rules=cfg["TRACKER_RULES"],
        seed_cleaner_dry_run=cfg["SEED_CLEANER_DRY_RUN"],
        min_downloads_per_tracker=cfg["MIN_DOWNLOADS_PER_TRACKER"],
        min_torrents_per_tracker=cfg["MIN_TORRENTS_PER_TRACKER"],
        enviar_notificacao_fn=enviar_notificacao,
    )

    # Enviar log completo para o OTEL (um unico registro com tudo)
    otel_flush()

    print(f"🗄️  {cfg['DB_PATH']}")
    print("=" * 70)
    conn.close()


if __name__ == "__main__":
    main()
