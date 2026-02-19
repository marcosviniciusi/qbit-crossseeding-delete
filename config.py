#!/usr/bin/env python3

# =============================================================================
# config.py — Configurações do qBittorrent Unified Manager
# Copie este arquivo para config.py e preencha com seus valores reais
# =============================================================================

# -----------------------------------------------------------------------------
# Banco de dados
# -----------------------------------------------------------------------------
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
# Implemente enviar_notificacao() no script principal com o canal de sua preferência.
# Exemplos: Telegram, Discord webhook, Slack, e-mail, Gotify, Ntfy, etc.
# -----------------------------------------------------------------------------

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
