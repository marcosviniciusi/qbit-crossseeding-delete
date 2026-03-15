#!/usr/bin/env python3
# modulos/helpers.py — Utilitarios compartilhados

import shutil
from urllib.parse import urlparse
from modulos.db import (
    minutos_desde_ultima_notificacao,
    registrar_notificacao,
)


def extrair_dominio_tracker(url):
    try:
        domain = urlparse(url).netloc.lower().split(':')[0]
        parts  = domain.split('.')
        return '.'.join(parts[-2:]) if len(parts) >= 2 else domain
    except:
        return "unknown"


def verificar_espacos(paths_config):
    resultados = {}
    for nome, config in paths_config.items():
        paths = config["path"] if isinstance(config["path"], list) else [config["path"]]

        livre_gb = None
        for path in paths:
            try:
                _, _, free = shutil.disk_usage(path)
                gb = free / (1024 ** 3)
            except FileNotFoundError:
                gb = 0
            if livre_gb is None or gb < livre_gb:
                livre_gb = gb

        if livre_gb is None:
            livre_gb = 0

        resultados[nome] = {
            "livre":         livre_gb,
            "paths":         paths,
            "limite_min":    config["limite_min"],
            "limite_max":    config["limite_max"],
            "critico":       livre_gb <= config["limite_min"],
            "ok":            livre_gb >= config["limite_max"],
            "seed_cleaner":  config.get("seed_cleaner", False),
            "pause_trigger": config.get("pause_trigger", True)
        }
    return resultados


def imprimir_espacos(espacos):
    for nome, info in espacos.items():
        icon = "🔴" if info["critico"] else "🟢" if info["ok"] else "🟡"
        print(f"   {icon} {nome}: {info['livre']:.1f} GB "
              f"(min: {info['limite_min']}, max: {info['limite_max']})")


def obter_contagem_checking_moving(client):
    todos    = client.torrents_info()
    checking = [t for t in todos if t.state in ('checkingDL', 'checkingUP', 'checkingResumeData')]
    moving   = [t for t in todos if t.state == 'moving']
    return len(checking), len(moving), checking, moving


def obter_downloads_ativos(client):
    return [
        t for t in client.torrents_info()
        if t.state == 'forcedDL'
    ]


def construir_tracker_map(client, todos_torrents):
    tracker_map = {}
    for t in todos_torrents:
        try:
            for tr in client.torrents_trackers(t.hash):
                if tr.url and not tr.url.startswith('**'):
                    tracker_map[t.hash] = extrair_dominio_tracker(tr.url)
                    break
        except:
            pass
        if t.hash not in tracker_map:
            tracker_map[t.hash] = 'unknown'
    return tracker_map


def notificar_se_necessario(conn, run_id, event_type, enviar_notificacao_fn,
                             intervalo_minutos=60):
    NOTIFICACOES = {
        'paused':         ("Torrents Status",          "Downloads Pausados",     1),
        'restored':       ("Torrents Status",          "Download em andamento",  0),
        'waiting_paused': ("Downloads Ainda Pausados", "Verificar sistema.",     1),
    }

    if event_type not in NOTIFICACOES:
        return

    titulo, mensagem, priority = NOTIFICACOES[event_type]
    minutos = minutos_desde_ultima_notificacao(conn, event_type)

    if event_type == 'restored':
        pass
    elif event_type == 'paused':
        ultima_restored = minutos_desde_ultima_notificacao(conn, 'restored')
        ultima_paused   = minutos_desde_ultima_notificacao(conn, 'paused')
        if ultima_paused is not None:
            if ultima_restored is None or ultima_paused < ultima_restored:
                print(f"   📵 Notificação '{event_type}' já enviada — pulando")
                return
    elif event_type == 'waiting_paused':
        if minutos is not None and minutos < intervalo_minutos:
            print(f"   📵 Notificação '{event_type}' enviada há {minutos:.0f} min "
                  f"(intervalo: {intervalo_minutos} min) — pulando")
            return

    enviar_notificacao_fn(titulo, mensagem, priority, event_type)
    registrar_notificacao(conn, run_id, event_type, titulo, mensagem)
    print(f"   📲 Notificação '{event_type}' enviada — {titulo}: {mensagem}")
