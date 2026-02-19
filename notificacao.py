#!/usr/bin/env python3
# =============================================================================
# notificacao.py
# Implementação do canal de notificação para o qb_unified_manager.
#
# Copie este arquivo para /etc/qbit-manager/notificacao.py e descomente
# o canal de sua preferência. A função deve se chamar enviar_notificacao()
# e aceitar os parâmetros: titulo (str), mensagem (str), priority (int).
# priority: 0 = informativo, 1 = crítico
# =============================================================================

import requests


# -----------------------------------------------------------------------------
# Telegram
# Crie um bot via @BotFather e obtenha o BOT_TOKEN.
# Para obter o CHAT_ID: envie uma mensagem ao bot e acesse
# https://api.telegram.org/bot<TOKEN>/getUpdates
# -----------------------------------------------------------------------------
# def enviar_notificacao(titulo, mensagem, priority=0, event_type=None):
#     BOT_TOKEN = "123456:ABC-seu-token-aqui"
#     CHAT_ID   = "123456789"
#     requests.post(
#         f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
#         json={
#             "chat_id":    CHAT_ID,
#             "text":       f"*{titulo}*\n\n{mensagem}",
#             "parse_mode": "Markdown"
#         }
#     )


# -----------------------------------------------------------------------------
# Discord
# Crie um Webhook em: Configurações do Servidor → Integrações → Webhooks
# -----------------------------------------------------------------------------
# def enviar_notificacao(titulo, mensagem, priority=0, event_type=None):
#     WEBHOOK_URL = "https://discord.com/api/webhooks/SEU_WEBHOOK_AQUI"
#     cor = {0: 0x2ecc71, 1: 0xe74c3c}.get(priority, 0xf39c12)
#     requests.post(WEBHOOK_URL, json={
#         "embeds": [{"title": titulo, "description": mensagem, "color": cor}]
#     })


# -----------------------------------------------------------------------------
# Slack
# Crie um app em api.slack.com/apps, ative Incoming Webhooks e copie a URL.
# -----------------------------------------------------------------------------
# def enviar_notificacao(titulo, mensagem, priority=0, event_type=None):
#     WEBHOOK_URL = "https://hooks.slack.com/services/SEU/WEBHOOK/AQUI"
#     requests.post(WEBHOOK_URL, json={"text": f"*{titulo}*\n{mensagem}"})


# -----------------------------------------------------------------------------
# Ntfy — self-hosted ou público (ntfy.sh)
# -----------------------------------------------------------------------------
# def enviar_notificacao(titulo, mensagem, priority=0, event_type=None):
#     NTFY_URL   = "https://ntfy.sh/seu-topico-aqui"
#     PRIORIDADE = {0: "default", 1: "high"}.get(priority, "default")
#     requests.post(NTFY_URL, data=mensagem.encode("utf-8"), headers={
#         "Title":    titulo,
#         "Priority": PRIORIDADE
#     })


# -----------------------------------------------------------------------------
# Gotify — self-hosted
# -----------------------------------------------------------------------------
# def enviar_notificacao(titulo, mensagem, priority=0, event_type=None):
#     GOTIFY_URL   = "https://gotify.seu-servidor.com"
#     GOTIFY_TOKEN = "seu-app-token-aqui"
#     requests.post(f"{GOTIFY_URL}/message", json={
#         "title":    titulo,
#         "message":  mensagem,
#         "priority": priority
#     }, headers={"X-Gotify-Key": GOTIFY_TOKEN})


# -----------------------------------------------------------------------------
# Pushover
# -----------------------------------------------------------------------------
# def enviar_notificacao(titulo, mensagem, priority=0, event_type=None):
#     requests.post("https://api.pushover.net/1/messages.json", data={
#         "token":    "seu-app-token",
#         "user":     "sua-user-key",
#         "title":    titulo,
#         "message":  mensagem,
#         "priority": priority
#     })