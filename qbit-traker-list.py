#!/usr/bin/env python3
# =============================================================================
# generate_tracker_rules.py
# Gera a lista de trackers com contagem de torrents para uso no tracker_rules.py
#
# Uso:
#   python generate_tracker_rules.py
#
# O script lê as credenciais do qBittorrent do mesmo config.py usado pelo
# qb_unified_manager.py. Ajuste CONFIG_DIR abaixo se necessário.
# =============================================================================

import sys
import requests
from collections import defaultdict
from urllib.parse import urlparse

# Diretório de configuração — deve ser o mesmo do qb_unified_manager.py
CONFIG_DIR = "/etc/qbit-manager"

# Windows: CONFIG_DIR = r"C:\qbit-manager\config"

if CONFIG_DIR not in sys.path:
    sys.path.insert(0, CONFIG_DIR)

try:
    from config import QB_URL, QB_USER, QB_PASS
    print(f"✅ Configurações carregadas de {CONFIG_DIR}/config.py")
except ImportError:
    print(f"❌ Não foi possível carregar config.py de {CONFIG_DIR}")
    print(f"   Ajuste CONFIG_DIR no topo deste script.")
    exit(1)
except NameError as e:
    print(f"❌ Variável não encontrada no config.py: {e}")
    exit(1)


def extrair_dominio(url):
    try:
        parsed = urlparse(url)
        netloc = parsed.netloc or url
        return netloc.split(":")[0] if ":" in netloc else netloc
    except:
        return url


def get_all_trackers():
    session = requests.Session()

    r = session.post(f"{QB_URL}/api/v2/auth/login", data={
        "username": QB_USER,
        "password": QB_PASS
    })
    if r.text != "Ok.":
        print(f"❌ Erro no login: {r.text}")
        return

    print("✅ Conectado ao qBittorrent\n")

    torrents = session.get(f"{QB_URL}/api/v2/torrents/info").json()
    print(f"📦 Total de torrents: {len(torrents)}\n")

    tracker_count = defaultdict(int)

    for i, torrent in enumerate(torrents, 1):
        if i % 100 == 0:
            print(f"   Processando... {i}/{len(torrents)}")

        trackers = session.get(
            f"{QB_URL}/api/v2/torrents/trackers",
            params={"hash": torrent["hash"]}
        ).json()

        for tracker in trackers:
            url = tracker.get("url", "")
            if url.startswith("**"):
                continue
            domain = extrair_dominio(url)
            if domain:
                tracker_count[domain] += 1

    # Tabela resumo
    print(f"\n{'TRACKER':<50} {'TORRENTS':>8}")
    print("-" * 60)
    for tracker, count in sorted(tracker_count.items(), key=lambda x: -x[1]):
        print(f"{tracker:<50} {count:>8}")

    print(f"\nTotal de trackers únicos: {len(tracker_count)}")

    # Gera bloco pronto para tracker_rules.py
    print("\n" + "=" * 60)
    print("# Cole em /etc/qbit-manager/tracker_rules.py:")
    print("=" * 60)
    print("TRACKER_RULES = {")
    print("    # Tracker                                    Dias mínimos de seeding")
    for tracker, count in sorted(tracker_count.items(), key=lambda x: -x[1]):
        padding = " " * max(1, 44 - len(tracker) - 2)
        print(f'    "{tracker}":{padding}0,  # {count} torrents')
    print("}")
    print("=" * 60)
    print("\n⚠️  Substitua os 0 pelo número de dias mínimos de seeding de cada tracker e cole no config.py")


if __name__ == "__main__":
    get_all_trackers()