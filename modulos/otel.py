#!/usr/bin/env python3
# modulos/otel.py — OpenTelemetry Logging
#
# Envia logs estruturados para um OpenTelemetry Collector via OTLP/HTTP.
# Se o collector nao estiver disponivel, faz fallback silencioso para print.
#
# Configuracao no config.py:
#   OTEL_ENDPOINT = "http://localhost:4318"  # OTLP HTTP endpoint
#   OTEL_SERVICE_NAME = "qbit-manager"       # nome do servico
#   OTEL_ENABLED = True                      # ativar/desativar

import json
import time
from datetime import datetime

try:
    import requests as _requests
except ImportError:
    _requests = None

# Defaults — sobrescritos pelo config.py se existirem
_config = {
    "endpoint":     None,
    "service_name": "qbit-manager",
    "enabled":      False,
}


def configurar_otel(endpoint=None, service_name=None, enabled=None):
    if endpoint is not None:
        _config["endpoint"] = endpoint.rstrip("/")
    if service_name is not None:
        _config["service_name"] = service_name
    if enabled is not None:
        _config["enabled"] = enabled


def _severity_number(level):
    return {
        "debug": 5,
        "info":  9,
        "warn":  13,
        "error": 17,
    }.get(level, 9)


def _enviar_log_otlp(body, level, attributes):
    if not _config["enabled"] or not _config["endpoint"] or not _requests:
        return False

    now_ns = int(time.time() * 1e9)

    log_record = {
        "timeUnixNano":   str(now_ns),
        "severityNumber": _severity_number(level),
        "severityText":   level.upper(),
        "body":           {"stringValue": body},
        "attributes":     [
            {"key": k, "value": {"stringValue": str(v)}}
            for k, v in attributes.items()
        ],
    }

    payload = {
        "resourceLogs": [{
            "resource": {
                "attributes": [
                    {"key": "service.name",
                     "value": {"stringValue": _config["service_name"]}}
                ]
            },
            "scopeLogs": [{
                "scope": {"name": "qbit-manager"},
                "logRecords": [log_record],
            }]
        }]
    }

    try:
        resp = _requests.post(
            f"{_config['endpoint']}/v1/logs",
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=5,
        )
        return resp.status_code < 300
    except Exception:
        return False


def log(mensagem, level="info", **attrs):
    """
    Envia um log para o OTEL Collector e imprime no console.

    Uso:
        from modulos.otel import log
        log("Disco critico detectado", level="warn", disco="p2p", livre_gb=42.3)
        log("Seed cleaner deletou 5 torrents", deletados=5, liberado_gb=120.5)
    """
    # Sempre imprime no console
    icons = {"debug": "🔍", "info": "ℹ️", "warn": "⚠️", "error": "❌"}
    icon  = icons.get(level, "ℹ️")
    extra = f" | {json.dumps(attrs, ensure_ascii=False)}" if attrs else ""
    print(f"   {icon} [OTEL] {mensagem}{extra}")

    # Envia para OTEL se configurado
    _enviar_log_otlp(mensagem, level, attrs)


def log_disco(espacos):
    """Envia metricas de disco para o OTEL."""
    for nome, info in espacos.items():
        level = "warn" if info["critico"] else "info"
        log(
            f"Disco {nome}: {info['livre']:.1f} GB",
            level=level,
            disco=nome,
            livre_gb=round(info["livre"], 2),
            limite_min=info["limite_min"],
            limite_max=info["limite_max"],
            critico=info["critico"],
            ok=info["ok"],
        )


def log_pausa(event_type, espacos, hashes_count, discos_criticos=None):
    """Log de evento de pausa/restauracao."""
    log(
        f"Evento: {event_type}",
        level="warn" if event_type != "restore" else "info",
        event_type=event_type,
        torrents_afetados=hashes_count,
        discos_criticos=json.dumps(discos_criticos or []),
    )


def log_seed_cleaner(acao, total, liberado_gb=0, dry_run=True):
    """Log de acao do seed cleaner."""
    log(
        f"Seed cleaner: {acao}",
        level="info",
        acao=acao,
        total=total,
        liberado_gb=round(liberado_gb, 2),
        dry_run=dry_run,
    )


def log_tracker(tracker, ativo, fila, forcados, ativados):
    """Log de gerenciamento de tracker."""
    log(
        f"Tracker {tracker}: ativo={ativo} fila={fila}",
        level="info",
        tracker=tracker,
        ativo=ativo,
        fila=fila,
        forcados=forcados,
        ativados=ativados,
    )


def log_run(run_id, status, resumo):
    """Log de finalizacao do run."""
    log(
        f"Run #{run_id} finalizado: {status}",
        level="info",
        run_id=run_id,
        status=status,
        **resumo,
    )
