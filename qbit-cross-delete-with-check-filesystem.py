#!/usr/bin/env python3
import requests
import shutil
from urllib.parse import urlparse
from collections import defaultdict

QB_URL  = "http://QBITTORRENTADDRESS:PORT"
QB_USER = "admin"
QB_PASS = "PASSWORD"

DRY_RUN = True

# Espaço mínimo livre em GB para executar a deleção
# Se o disco tiver MAIS que este valor livre, o script não apaga nada
MIN_FREE_SPACE_GB = 100

# Caminho a monitorar (ajuste para o mount point do seu storage)
MONITOR_PATH = "/"

################ Substitua aqui a lista Gerada ################
TRACKER_RULES = {
    "trake1.example.com":                        X,  # 169 torrents
    "tracker.cc":                                X,  # 159 torrents
    "anothertracker.com":                        X,  # 150 torrents
}
################ Fim da subistituição ################

def get_free_space_gb(path):
    usage = shutil.disk_usage(path)
    return usage.free / (1024 ** 3)

def get_domain(url):
    try:
        return urlparse(url).netloc or url
    except:
        return url

def get_tracker_rules(trackers):
    rules = []
    for tracker in trackers:
        url = tracker.get("url", "")
        if url.startswith("**"):
            continue
        domain = get_domain(url)
        for rule_domain, days in TRACKER_RULES.items():
            if rule_domain in domain:
                rules.append((rule_domain, days))
                break
    return rules

def main():
    # Verifica espaço em disco antes de qualquer coisa
    free_gb = get_free_space_gb(MONITOR_PATH)
    print(f"Espaço livre em disco ({MONITOR_PATH}): {free_gb:.1f} GB")

    if free_gb >= MIN_FREE_SPACE_GB:
        print(f"Espaço livre ({free_gb:.1f} GB) acima do mínimo ({MIN_FREE_SPACE_GB} GB). Nada a fazer.")
        return

    print(f"Espaço livre abaixo de {MIN_FREE_SPACE_GB} GB! Iniciando verificação de torrents...\n")

    session = requests.Session()

    r = session.post(f"{QB_URL}/api/v2/auth/login", data={
        "username": QB_USER,
        "password": QB_PASS
    })
    if r.text != "Ok.":
        print(f"Erro no login: {r.text}")
        return

    torrents = session.get(f"{QB_URL}/api/v2/torrents/info").json()
    print(f"Total de torrents: {len(torrents)}")
    print(f"Modo: {'DRY RUN (simulação)' if DRY_RUN else '*** DELETANDO DE VERDADE ***'}\n")

    torrent_data = []

    for torrent in torrents:
        hash_        = torrent["hash"]
        name         = torrent["name"]
        seeding_days = torrent.get("seeding_time", 0) / 86400

        trackers = session.get(
            f"{QB_URL}/api/v2/torrents/trackers",
            params={"hash": hash_}
        ).json()

        rules = get_tracker_rules(trackers)
        if not rules:
            continue

        torrent_data.append({
            "hash":         hash_,
            "name":         name,
            "seeding_days": seeding_days,
            "rules":        rules,
        })

    groups = defaultdict(list)
    for t in torrent_data:
        groups[t["name"]].append(t)

    to_delete = []
    kept_crossseed = []

    for name, group in groups.items():
        all_satisfied = True
        details = []

        for t in group:
            for domain, required_days in t["rules"]:
                satisfied = t["seeding_days"] >= required_days
                details.append({
                    "torrent":  t,
                    "domain":   domain,
                    "required": required_days,
                    "actual":   t["seeding_days"],
                    "satisfied": satisfied,
                })
                if not satisfied:
                    all_satisfied = False

        if all_satisfied:
            for t in group:
                max_rule = max(d for _, d in t["rules"])
                to_delete.append({
                    "hash":       t["hash"],
                    "name":       t["name"],
                    "days":       t["seeding_days"],
                    "rule":       max_rule,
                    "tracker":    ", ".join(set(d for d, _ in t["rules"])),
                    "group_size": len(group),
                })
        else:
            unsatisfied = [d for d in details if not d["satisfied"]]
            for t in group:
                max_rule = max(d for _, d in t["rules"])
                if t["seeding_days"] >= max_rule:
                    kept_crossseed.append({
                        "name":     t["name"],
                        "days":     t["seeding_days"],
                        "rule":     max_rule,
                        "tracker":  ", ".join(set(d for d, _ in t["rules"])),
                        "blocking": [
                            f"{d['domain']}({d['actual']:.1f}d/{d['required']}d)"
                            for d in unsatisfied
                        ],
                    })

    print(f"Torrents elegíveis para deleção: {len(to_delete)}\n")
    print(f"{'TRACKER':<40} {'SEED DAYS':>10} {'RULE':>6}  NOME")
    print("-" * 120)
    for t in sorted(to_delete, key=lambda x: x["tracker"]):
        cross = f" [x{t['group_size']}]" if t["group_size"] > 1 else ""
        print(f"{t['tracker']:<40} {t['days']:>9.1f}d {t['rule']:>5}d{cross}  {t['name']}")

    if kept_crossseed:
        print(f"\n--- Mantidos por cross-seed (aguardando outro tracker) ---")
        print(f"{'TRACKER':<40} {'SEED DAYS':>10}  NOME")
        print("-" * 120)
        for t in sorted(kept_crossseed, key=lambda x: x["tracker"]):
            blocking = " | aguardando: " + ", ".join(t["blocking"])
            print(f"{t['tracker']:<40} {t['days']:>9.1f}d  {t['name']}{blocking}")

    if not DRY_RUN and to_delete:
        print("\nDeletando...")
        hashes = "|".join(t["hash"] for t in to_delete)
        r = session.post(f"{QB_URL}/api/v2/torrents/delete", data={
            "hashes": hashes,
            "deleteFiles": True
        })
        print(f"Resposta: {r.status_code} - {r.text}")
        print(f"\n{len(to_delete)} torrents deletados.")
    elif DRY_RUN:
        print(f"\nDRY RUN: mude DRY_RUN = False para apagar.")

if __name__ == "__main__":
    main()