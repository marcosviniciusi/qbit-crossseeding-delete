#!/usr/bin/env python3
import requests
from collections import defaultdict
from urllib.parse import urlparse

# Configuração
QB_URL = "http://qbittorrentADDRESS:PORT"
QB_USER = "USER"
QB_PASS = "PASSWORD"

def get_all_trackers():
    session = requests.Session()

    r = session.post(f"{QB_URL}/api/v2/auth/login", data={
        "username": QB_USER,
        "password": QB_PASS
    })
    if r.text != "Ok.":
        print(f"Erro no login: {r.text}")
        return

    torrents = session.get(f"{QB_URL}/api/v2/torrents/info").json()
    print(f"Total de torrents: {len(torrents)}\n")

    tracker_count = defaultdict(int)

    for torrent in torrents:
        hash_ = torrent["hash"]

        trackers = session.get(f"{QB_URL}/api/v2/torrents/trackers", params={"hash": hash_}).json()

        for tracker in trackers:
            url = tracker.get("url", "")
            if url.startswith("**"):
                continue
            try:
                domain = urlparse(url).netloc or url
            except:
                domain = url

            tracker_count[domain] += 1

    # Tabela resumo
    print(f"{'TRACKER':<50} {'TORRENTS':>8}")
    print("-" * 60)
    for tracker, count in sorted(tracker_count.items(), key=lambda x: -x[1]):
        print(f"{tracker:<50} {count:>8}")

    print(f"\nTotal de trackers únicos: {len(tracker_count)}")

    # Gera bloco pronto para o script de deleção
    print("\n# Cole no TRACKER_RULES do script de deleção:")
    print("TRACKER_RULES = {")
    for tracker, count in sorted(tracker_count.items(), key=lambda x: -x[1]):
        padding = " " * max(1, 40 - len(tracker))
        print(f'    "{tracker}":{padding}X,  # {count} torrents')
    print("}")

if __name__ == "__main__":
    get_all_trackers()