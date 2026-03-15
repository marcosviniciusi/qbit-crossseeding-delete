#!/usr/bin/env python3
# modulos/tracker_list.py — Gera lista de trackers com contagem de torrents
#
# Chamado pelo qbit-manager.py com --tracker-list

from collections import defaultdict
from modulos.helpers import extrair_dominio_tracker


def gerar_lista_trackers(client):
    """
    Varre todos os torrents do qBittorrent e gera o bloco TRACKER_RULES
    pronto para colar no config.py.

    Recebe um client qbittorrentapi ja autenticado.
    """
    torrents = client.torrents_info()
    print(f"📦 Total de torrents: {len(torrents)}\n")

    tracker_count = defaultdict(int)

    for i, torrent in enumerate(torrents, 1):
        if i % 100 == 0:
            print(f"   Processando... {i}/{len(torrents)}")

        try:
            trackers = client.torrents_trackers(torrent.hash)
        except:
            continue

        for tracker in trackers:
            url = getattr(tracker, 'url', '')
            if url.startswith("**"):
                continue
            domain = extrair_dominio_tracker(url)
            if domain and domain != "unknown":
                tracker_count[domain] += 1

    # Tabela resumo
    print(f"\n{'TRACKER':<50} {'TORRENTS':>8}")
    print("-" * 60)
    for tracker, count in sorted(tracker_count.items(), key=lambda x: -x[1]):
        print(f"{tracker:<50} {count:>8}")

    print(f"\nTotal de trackers únicos: {len(tracker_count)}")

    # Gera bloco pronto para config.py
    print("\n" + "=" * 60)
    print("# Cole no TRACKER_RULES do seu config.py:")
    print("=" * 60)
    print("TRACKER_RULES = {")
    print("    # Tracker                                    Dias mínimos de seeding")
    for tracker, count in sorted(tracker_count.items(), key=lambda x: -x[1]):
        padding = " " * max(1, 44 - len(tracker) - 2)
        print(f'    "{tracker}":{padding}0,  # {count} torrents')
    print("}")
    print("=" * 60)
    print("\n⚠️  Substitua os 0 pelo número de dias mínimos de seeding de cada tracker.")
