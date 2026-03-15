#!/usr/bin/env python3

# =============================================================================
# config.py — Configurações do qBittorrent Manager
# Copie este arquivo para /etc/qbit-manager/config.py e preencha seus valores
# =============================================================================

# -----------------------------------------------------------------------------
# Diretórios do sistema
# -----------------------------------------------------------------------------
# INSTALL_DIR → onde estão os scripts e a pasta modulos/
#   O script principal (qbit-manager.py) e a pasta modulos/ devem estar aqui.
#   Altere se instalou em outro local.
INSTALL_DIR = "/usr/local/lib/qbit-manager"

# DB_DIR → onde o banco SQLite será criado
DB_DIR  = "/var/lib/qbit-manager"
DB_PATH = f"{DB_DIR}/qbit.db"

# -----------------------------------------------------------------------------
# qBittorrent
# -----------------------------------------------------------------------------
QB_URL  = "http://torrent.seudominio.com:PORTA"   # URL do qBittorrent (com porta se necessário)
QB_USER = "admin"
QB_PASS = "sua_senha_aqui"

# -----------------------------------------------------------------------------
# Notificações
# -----------------------------------------------------------------------------
# Escolha o tipo de notificação e preencha as credenciais.
# Tipos disponíveis: "telegram", "discord", "slack", "ntfy", "gotify", "pushover", "nenhum"
#
# Para desativar notificações, use:
#   NOTIFICACAO_TIPO = "nenhum"

NOTIFICACAO_TIPO = "nenhum"
NOTIFICACAO_CONFIG = {}

# ── Telegram ──────────────────────────────────────────────────────────────────
# Crie um bot via @BotFather e obtenha o BOT_TOKEN.
# Para obter o CHAT_ID: envie uma mensagem ao bot e acesse
# https://api.telegram.org/bot<TOKEN>/getUpdates
#
# NOTIFICACAO_TIPO = "telegram"
# NOTIFICACAO_CONFIG = {
#     "bot_token": "123456:ABC-seu-token-aqui",
#     "chat_id":   "123456789",
# }

# ── Discord ───────────────────────────────────────────────────────────────────
# Crie um Webhook em: Configurações do Servidor → Integrações → Webhooks
#
# NOTIFICACAO_TIPO = "discord"
# NOTIFICACAO_CONFIG = {
#     "webhook_url": "https://discord.com/api/webhooks/SEU_WEBHOOK_AQUI",
# }

# ── Slack ─────────────────────────────────────────────────────────────────────
# Crie um app em api.slack.com/apps, ative Incoming Webhooks e copie a URL.
#
# NOTIFICACAO_TIPO = "slack"
# NOTIFICACAO_CONFIG = {
#     "webhook_url": "https://hooks.slack.com/services/SEU/WEBHOOK/AQUI",
# }

# ── Ntfy ──────────────────────────────────────────────────────────────────────
# Self-hosted ou público (ntfy.sh). Token é opcional.
#
# NOTIFICACAO_TIPO = "ntfy"
# NOTIFICACAO_CONFIG = {
#     "url":   "https://ntfy.sh/seu-topico-aqui",
#     "token": "",   # opcional — deixe vazio se não usar autenticação
# }

# ── Gotify ────────────────────────────────────────────────────────────────────
# Self-hosted. Crie um Application no painel e copie o token.
#
# NOTIFICACAO_TIPO = "gotify"
# NOTIFICACAO_CONFIG = {
#     "url":   "https://gotify.seu-servidor.com",
#     "token": "seu-app-token-aqui",
# }

# ── Pushover ──────────────────────────────────────────────────────────────────
# Crie uma Application em pushover.net e copie o token.
#
# NOTIFICACAO_TIPO = "pushover"
# NOTIFICACAO_CONFIG = {
#     "app_token": "seu-app-token",
#     "user_key":  "sua-user-key",
# }

# -----------------------------------------------------------------------------
# Gerenciamento de trackers (mínimo de downloads ativos por tracker)
# -----------------------------------------------------------------------------
MIN_DOWNLOADS_PER_TRACKER = 4   # Mínimo de downloads ativos simultâneos por tracker
MIN_TORRENTS_PER_TRACKER  = 4   # Ignorar tracker se tiver menos torrents que isso
                                 # (exceto se não houver nenhum ativo)

# -----------------------------------------------------------------------------
# Discos monitorados
# Cada entrada define um ponto de montagem e seus limites de espaço livre em GB:
#   limite_min → abaixo disso, pausa os downloads (disco crítico)
#   limite_max → acima disso, libera para retomar downloads
# -----------------------------------------------------------------------------
PATHS = {
    "p2p": {
        "path":          "/mnt/disco-p2p/",        # string única ou lista de paths
        "limite_min":    100,     # GB — pausa downloads abaixo deste valor
        "limite_max":    150,     # GB — retoma downloads acima deste valor
        "seed_cleaner":  True,    # seed cleaner monitora este disco (onde os torrents ficam)
        "pause_trigger": True     # disco crítico aqui pausa os downloads
    },
    "videos": {
        "path": [                                  # múltiplos discos de destino
            "/mnt/disco-videos-1/",
            "/mnt/disco-videos-2/",
        ],
        "limite_min":    200,     # pausa se QUALQUER disco da lista ficar abaixo deste valor
        "limite_max":    250,
        "seed_cleaner":  False,   # seed cleaner NÃO monitora este disco (destino Radarr/Sonarr)
        "pause_trigger": True     # disco crítico aqui pausa os downloads
    },
}

# -----------------------------------------------------------------------------
# Limpeza por tempo de seeding (integração com seed cleaner)
# SEED_CLEANER_DRY_RUN = True  → apenas simula, não apaga nada
# SEED_CLEANER_DRY_RUN = False → apaga de verdade
# -----------------------------------------------------------------------------
SEED_CLEANER_DRY_RUN = True

# Regras por tracker: domínio -> dias mínimos de seeding para elegível à deleção
# O script agrupa cross-seeds pelo nome do torrent: só deleta quando TODOS os
# trackers do grupo satisfizerem o mínimo de dias configurado.
TRACKER_RULES = {
    "tracker1.example.com":   30,   # deleta após 30 dias de seed
    "tracker2.example.com":   45,
    "tracker3.example.com":   60,
    "privatetorrent.net":     90,
    "anotherprivate.org":    120,
}

# -----------------------------------------------------------------------------
# OpenTelemetry (opcional)
# Para enviar logs estruturados a um OTEL Collector, descomente abaixo:
# -----------------------------------------------------------------------------
# OTEL_ENDPOINT     = "http://localhost:4318"
# OTEL_SERVICE_NAME = "qbit-manager"
# OTEL_ENVIRONMENT  = "production"
# OTEL_ENABLED      = True
