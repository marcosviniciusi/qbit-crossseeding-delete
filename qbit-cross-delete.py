#!/usr/bin/env python3
import requests
from urllib.parse import urlparse
from collections import defaultdict

QB_URL = "http://QBITTORRENTADDRESS:PORT"
QB_USER = "admin"
QB_PASS = "PASSWORD"

DRY_RUN = True

################ Substitua aqui a lista Gerada ################
TRACKER_RULES = {
    "trake1.example.com":                        X,  # 169 torrents
    "tracker.cc":                                X,  # 159 torrents
    "anothertracker.com":                        X,  # 150 torrents
    ...
}
################ Fim da subistituição ################
def get_domain(url):
    try:
        return urlparse(url).netloc or url
    except:
        return url

def get_tracker_rules(trackers):
    """Retorna lista de (domain, required_days) para os trackers com regra."""
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

def normalize_name(name):
    """Normaliza nome para comparação de cross-seeding."""
    import re
    # Remove extensão
    name = re.sub(r'\.[a-zA-Z0-9]{2,4}$', '', name)
    # Lowercase e remove caracteres especiais
    name = name.lower()
    name = re.sub(r'[\s\.\-_]+', ' ', name).strip()
    return name

def main():
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

    # Monta estrutura: normalized_name -> lista de torrents
    # Cada entrada: {hash, name, seeding_days, tracker_rules: [(domain, days)]}
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
            continue  # sem tracker com regra, ignora

        torrent_data.append({
            "hash":         hash_,
            "name":         name,
            "norm_name":    normalize_name(name),
            "seeding_days": seeding_days,
            "rules":        rules,  # [(domain, required_days), ...]
        })


    # Agrupa por nome normalizado (cross-seeds ficam juntos)
    groups = defaultdict(list)
    for t in torrent_data:
        groups[t["name"]].append(t)

    to_delete = []
    kept_crossseed = []

    for norm_name, group in groups.items():
        # Para cada torrent do grupo, verifica se TODOS os torrents do grupo
        # com regra de tracker já cumpriram o seedtime mínimo

        # Coleta todos os requisitos do grupo inteiro
        all_satisfied = True
        details = []

        for t in group:
            for domain, required_days in t["rules"]:
                satisfied = t["seeding_days"] >= required_days
                details.append({
                    "torrent": t,
                    "domain": domain,
                    "required": required_days,
                    "actual": t["seeding_days"],
                    "satisfied": satisfied,
                })
                if not satisfied:
                    all_satisfied = False

        if all_satisfied:
            # Todos os trackers de todos os cross-seeds satisfeitos -> pode apagar
            for t in group:
                # Pega a regra mais alta do torrent para exibir
                max_rule = max(d for _, d in t["rules"])
                to_delete.append({
                    "hash":    t["hash"],
                    "name":    t["name"],
                    "days":    t["seeding_days"],
                    "rule":    max_rule,
                    "tracker": ", ".join(set(d for d, _ in t["rules"])),
                    "group_size": len(group),
                })
        else:
            # Algum tracker ainda não satisfeito, mantém todos do grupo
            # Mostra quais estão sendo mantidos por causa de cross-seed
            unsatisfied = [d for d in details if not d["satisfied"]]
            for t in group:
                max_rule = max(d for _, d in t["rules"])
                if t["seeding_days"] >= max_rule:
                    # Este já cumpriu o requisito mas está sendo mantido por outro
                    kept_crossseed.append({
                        "name":    t["name"],
                        "days":    t["seeding_days"],
                        "rule":    max_rule,
                        "tracker": ", ".join(set(d for d, _ in t["rules"])),
                        "blocking": [
                            f"{d['domain']}({d['actual']:.1f}d/{d['required']}d)"
                            for d in unsatisfied
                        ],
                    })

    # Exibe torrents prontos para deletar
    print(f"Torrents elegíveis para deleção: {len(to_delete)}\n")
    print(f"{'TRACKER':<40} {'SEED DAYS':>10} {'RULE':>6}  NOME")
    print("-" * 120)
    for t in sorted(to_delete, key=lambda x: x["tracker"]):
        cross = f" [x{t['group_size']}]" if t["group_size"] > 1 else ""
        print(f"{t['tracker']:<40} {t['days']:>9.1f}d {t['rule']:>5}d{cross}  {t['name']}")

    # Exibe torrents mantidos por cross-seed
    if kept_crossseed:
        print(f"\n--- Mantidos por cross-seed (já cumpriram requisito próprio mas aguardando outro tracker) ---")
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
