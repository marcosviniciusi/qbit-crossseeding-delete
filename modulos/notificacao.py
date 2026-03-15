#!/usr/bin/env python3
# modulos/notificacao.py — Sistema de notificacoes plugavel
#
# Le o tipo e credenciais do config.py e despacha para o canal correto.
# Tipos suportados: telegram, discord, slack, ntfy, gotify, pushover, nenhum
#
# Configuracao no config.py:
#   NOTIFICACAO_TIPO = "telegram"
#   NOTIFICACAO_CONFIG = {
#       "bot_token": "123456:ABC...",
#       "chat_id":   "123456789",
#   }

try:
    import requests
except ImportError:
    requests = None


def _enviar_telegram(titulo, mensagem, priority, event_type, config):
    bot_token = config["bot_token"]
    chat_id   = config["chat_id"]
    requests.post(
        f"https://api.telegram.org/bot{bot_token}/sendMessage",
        json={
            "chat_id":    chat_id,
            "text":       f"*{titulo}*\n\n{mensagem}",
            "parse_mode": "Markdown"
        },
        timeout=10,
    )


def _enviar_discord(titulo, mensagem, priority, event_type, config):
    webhook_url = config["webhook_url"]
    cor = {0: 0x2ecc71, 1: 0xe74c3c}.get(priority, 0xf39c12)
    requests.post(webhook_url, json={
        "embeds": [{
            "title":       titulo,
            "description": mensagem,
            "color":       cor
        }]
    }, timeout=10)


def _enviar_slack(titulo, mensagem, priority, event_type, config):
    webhook_url = config["webhook_url"]
    requests.post(webhook_url, json={
        "text": f"*{titulo}*\n{mensagem}"
    }, timeout=10)


def _enviar_ntfy(titulo, mensagem, priority, event_type, config):
    url        = config["url"]
    prioridade = {0: "default", 1: "high"}.get(priority, "default")
    headers    = {"Title": titulo, "Priority": prioridade}
    # Autenticacao opcional
    if config.get("token"):
        headers["Authorization"] = f"Bearer {config['token']}"
    requests.post(url, data=mensagem.encode("utf-8"), headers=headers, timeout=10)


def _enviar_gotify(titulo, mensagem, priority, event_type, config):
    url   = config["url"].rstrip("/")
    token = config["token"]
    requests.post(f"{url}/message", json={
        "title":    titulo,
        "message":  mensagem,
        "priority": priority
    }, headers={"X-Gotify-Key": token}, timeout=10)


def _enviar_pushover(titulo, mensagem, priority, event_type, config):
    requests.post("https://api.pushover.net/1/messages.json", data={
        "token":    config["app_token"],
        "user":     config["user_key"],
        "title":    titulo,
        "message":  mensagem,
        "priority": priority
    }, timeout=10)


# Mapa de tipos suportados
_CANAIS = {
    "telegram": _enviar_telegram,
    "discord":  _enviar_discord,
    "slack":    _enviar_slack,
    "ntfy":     _enviar_ntfy,
    "gotify":   _enviar_gotify,
    "pushover": _enviar_pushover,
}


def criar_notificador(tipo, config):
    """
    Retorna uma funcao enviar_notificacao(titulo, mensagem, priority, event_type)
    configurada para o canal escolhido.

    Uso:
        enviar = criar_notificador("telegram", {"bot_token": "...", "chat_id": "..."})
        enviar("Titulo", "Mensagem", priority=1, event_type="paused")
    """
    if not tipo or tipo == "nenhum":
        def _noop(titulo, mensagem, priority=0, event_type=None):
            pass
        return _noop

    if not requests:
        print(f"⚠️  Módulo 'requests' não instalado — notificações desativadas")
        print(f"   Instale com: pip install requests")
        def _noop(titulo, mensagem, priority=0, event_type=None):
            pass
        return _noop

    fn = _CANAIS.get(tipo)
    if not fn:
        tipos_validos = ", ".join(sorted(_CANAIS.keys()))
        print(f"⚠️  NOTIFICACAO_TIPO '{tipo}' não reconhecido. Válidos: {tipos_validos}, nenhum")
        def _noop(titulo, mensagem, priority=0, event_type=None):
            pass
        return _noop

    def _enviar(titulo, mensagem, priority=0, event_type=None):
        try:
            fn(titulo, mensagem, priority, event_type, config)
        except Exception as e:
            print(f"   ❌ Erro ao enviar notificação ({tipo}): {e}")

    return _enviar
