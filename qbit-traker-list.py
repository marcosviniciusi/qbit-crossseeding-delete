#!/usr/bin/env python3
# =============================================================================
# qbit-traker-list.py
# Gera a lista de trackers com contagem de torrents para uso no config.py
#
# Uso:
#   python3 qbit-traker-list.py
#
# Le as credenciais do config.py e usa os modulos compartilhados.
# =============================================================================

import os
import sys
import qbittorrentapi
from collections import defaultdict

# ── Carregar config.py ───────────────────────────────────────────────────────
CONFIG_DIR = "/etc/qbit-manager"

if CONFIG_DIR not in sys.path:
    sys.path.insert(0, CONFIG_DIR)

try:
    from config import QB_URL, QB_USER, QB_PASS
    print(f"✅ Configurações carregadas de {CONFIG_DIR}/config.py")
except ImportError:
    print(f"❌ Não foi possível carregar config.py de {CONFIG_DIR}")
    print(f"   Ajuste CONFIG_DIR no topo deste script.")
    sys.exit(1)

# ── Resolver INSTALL_DIR para encontrar modulos/ ────────────────────────────
try:
    from config import INSTALL_DIR
except ImportError:
    INSTALL_DIR = os.path.dirname(os.path.abspath(__file__))

if INSTALL_DIR not in sys.path:
    sys.path.insert(0, INSTALL_DIR)

from modulos.helpers import extrair_dominio_tracker


def gerar_lista_trackers():
    # Conectar via qbittorrent-api (mesmo que o manager)
    client = qbittorrentapi.Client(host=QB_URL, username=QB_USER, password=QB_PASS)
    try:
        client.auth_log_in()
        print("✅ Conectado ao qBittorrent\n")
    except qbittorrentapi.LoginFailed:
        print("❌ Falha ao autenticar")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Erro ao conectar: {e}")
        sys.exit(1)

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

    # Gera bloco pronto para config.py / tracker_rules.py
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


if __name__ == "__main__":
    gerar_lista_trackers()
