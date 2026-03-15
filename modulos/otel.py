#!/usr/bin/env python3
# modulos/otel.py — OpenTelemetry Logging (batch)
#
# Acumula todos os logs durante a execucao e envia um unico registro
# para o OTEL Collector via OTLP/HTTP no final (flush).
#
# Configuracao no config.py:
#   OTEL_ENDPOINT     = "http://localhost:4318"
#   OTEL_SERVICE_NAME = "qbit-manager"
#   OTEL_ENVIRONMENT  = "production"
#   OTEL_ENABLED      = True

import json
import time

try:
    import requests as _requests
except ImportError:
    _requests = None

# Config — sobrescritos por configurar_otel()
_config = {
    "endpoint":     None,
    "service_name": "qbit-manager",
    "environment":  "production",
    "enabled":      False,
}

# Buffer de logs acumulados durante o run
_buffer = []

# Severity mais alta encontrada no run (para o registro final)
_max_severity = {"level": "info", "number": 9}

_SEVERITY_MAP = {
    "debug": 5,
    "info":  9,
    "warn":  13,
    "error": 17,
}


def configurar_otel(endpoint=None, service_name=None, environment=None, enabled=None):
    if endpoint is not None:
        _config["endpoint"] = endpoint.rstrip("/")
    if service_name is not None:
        _config["service_name"] = service_name
    if environment is not None:
        _config["environment"] = environment
    if enabled is not None:
        _config["enabled"] = enabled
    # Limpar buffer a cada configuracao (novo run)
    _buffer.clear()
    _max_severity["level"]  = "info"
    _max_severity["number"] = 9


def log(mensagem, level="info", **attrs):
    """
    Acumula um log no buffer e imprime no console.
    Nao envia nada pro OTEL — use flush() no final do run.

    Uso:
        log("Disco critico detectado", level="warn", disco="p2p", livre_gb=42.3)
        log("Seed cleaner deletou 5 torrents", deletados=5, liberado_gb=120.5)
    """
    severity = _SEVERITY_MAP.get(level, 9)
    if severity > _max_severity["number"]:
        _max_severity["level"]  = level
        _max_severity["number"] = severity

    entry = {
        "ts":    time.time(),
        "level": level,
        "msg":   mensagem,
        "attrs": attrs,
    }
    _buffer.append(entry)


def log_disco(espacos):
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
    log(
        f"Evento: {event_type}",
        level="warn" if event_type != "restore" else "info",
        event_type=event_type,
        torrents_afetados=hashes_count,
        discos_criticos=json.dumps(discos_criticos or []),
    )


def log_seed_cleaner(acao, total, liberado_gb=0, dry_run=True):
    log(
        f"Seed cleaner: {acao}",
        level="info",
        acao=acao,
        total=total,
        liberado_gb=round(liberado_gb, 2),
        dry_run=dry_run,
    )


def log_tracker(tracker, ativo, fila, forcados, ativados):
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
    log(
        f"Run #{run_id} finalizado: {status}",
        level="info",
        run_id=run_id,
        status=status,
        **resumo,
    )


def flush():
    """
    Envia todos os logs acumulados como logRecords individuais para o OTEL Collector.
    Cada entry do buffer vira um logRecord separado com seus proprios atributos.
    Limpa o buffer apos o envio.

    Retorna True se enviou com sucesso, False se nao.
    """
    if not _buffer:
        return False

    if not _config["enabled"] or not _config["endpoint"] or not _requests:
        _buffer.clear()
        return False

    # Cada entry vira um logRecord individual
    log_records = []
    for entry in _buffer:
        severity = _SEVERITY_MAP.get(entry["level"], 9)
        ts_ns = str(int(entry["ts"] * 1e9))

        attributes = [
            {"key": k, "value": {"stringValue": str(v)}}
            for k, v in entry["attrs"].items()
        ]

        log_records.append({
            "timeUnixNano":   ts_ns,
            "severityNumber": severity,
            "severityText":   entry["level"].upper(),
            "body":           {"stringValue": entry["msg"]},
            "attributes":     attributes,
        })

    payload = {
        "resourceLogs": [{
            "resource": {
                "attributes": [
                    {"key": "service.name",
                     "value": {"stringValue": _config["service_name"]}},
                    {"key": "deployment.environment",
                     "value": {"stringValue": _config["environment"]}}
                ]
            },
            "scopeLogs": [{
                "scope": {"name": "qbit-manager"},
                "logRecords": log_records,
            }]
        }]
    }

    sucesso = False
    try:
        resp = _requests.post(
            f"{_config['endpoint']}/v1/logs",
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=10,
        )
        sucesso = resp.status_code < 300
        if sucesso:
            print(f"   ✅ [OTEL] Log enviado ({len(_buffer)} entradas)")
        else:
            print(f"   ⚠️  [OTEL] Falha ao enviar: HTTP {resp.status_code}")
    except Exception as e:
        print(f"   ❌ [OTEL] Erro ao enviar: {e}")

    _buffer.clear()
    return sucesso
