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

import logging
import os
import sys
from collections import defaultdict
from urllib.parse import urlparse

import requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("qbit-tracker-list")

# Diretório de configuração — deve ser o mesmo do qb_unified_manager.py
CONFIG_DIR = os.environ.get("QBIT_MANAGER_CONFIG_DIR", "/etc/qbit-manager")

if CONFIG_DIR not in sys.path:
    sys.path.insert(0, CONFIG_DIR)

try:
    from config import QB_URL, QB_USER, QB_PASS  # type: ignore[import-untyped]
    logger.info("Configuracoes carregadas de %s/config.py", CONFIG_DIR)
except ImportError:
    logger.error("Nao foi possivel carregar config.py de %s", CONFIG_DIR)
    logger.error("Ajuste CONFIG_DIR no topo deste script.")
    sys.exit(1)
except NameError as e:
    logger.error("Variavel nao encontrada no config.py: %s", e)
    sys.exit(1)

CONNECT_TIMEOUT = 30


def extrair_dominio_tracker(url: str) -> str:
    """Extrai domínio principal de uma URL de tracker."""
    try:
        parsed = urlparse(url)
        netloc = parsed.netloc or url
        return netloc.split(":")[0] if ":" in netloc else netloc
    except Exception:
        return url


def get_all_trackers() -> None:
    """Conecta ao qBittorrent e lista todos os trackers com contagem de torrents."""
    session = requests.Session()

    r = session.post(
        f"{QB_URL}/api/v2/auth/login",
        data={"username": QB_USER, "password": QB_PASS},
        timeout=CONNECT_TIMEOUT,
    )
    if r.text != "Ok.":
        logger.error("Erro no login: %s", r.text)
        return

    logger.info("Conectado ao qBittorrent")

    try:
        torrents = session.get(f"{QB_URL}/api/v2/torrents/info", timeout=CONNECT_TIMEOUT).json()
    except (requests.RequestException, ValueError) as e:
        logger.error("Erro ao obter lista de torrents: %s", e)
        return

    logger.info("Total de torrents: %d", len(torrents))

    tracker_count: dict[str, int] = defaultdict(int)

    for i, torrent in enumerate(torrents, 1):
        if i % 100 == 0:
            logger.info("Processando... %d/%d", i, len(torrents))

        try:
            trackers = session.get(
                f"{QB_URL}/api/v2/torrents/trackers",
                params={"hash": torrent["hash"]},
                timeout=CONNECT_TIMEOUT,
            ).json()
        except (requests.RequestException, ValueError) as e:
            logger.warning("Erro ao obter trackers do torrent %s: %s", torrent.get("name", "?")[:30], e)
            continue

        for tracker in trackers:
            url = tracker.get("url", "")
            if url.startswith("**"):
                continue
            domain = extrair_dominio_tracker(url)
            if domain:
                tracker_count[domain] += 1

    # Tabela resumo
    print(f"\n{'TRACKER':<50} {'TORRENTS':>8}")
    print("-" * 60)
    for tracker, count in sorted(tracker_count.items(), key=lambda x: -x[1]):
        print(f"{tracker:<50} {count:>8}")

    print(f"\nTotal de trackers unicos: {len(tracker_count)}")

    # Gera bloco pronto para tracker_rules.py
    print("\n" + "=" * 60)
    print("# Cole em /etc/qbit-manager/config.py (TRACKER_RULES):")
    print("=" * 60)
    print("TRACKER_RULES = {")
    print("    # Tracker                                    Dias minimos de seeding")
    for tracker, count in sorted(tracker_count.items(), key=lambda x: -x[1]):
        padding = " " * max(1, 44 - len(tracker) - 2)
        print(f'    "{tracker}":{padding}0,  # {count} torrents')
    print("}")
    print("=" * 60)
    print("\nSubstitua os 0 pelo numero de dias minimos de seeding de cada tracker e cole no config.py")


if __name__ == "__main__":
    get_all_trackers()
