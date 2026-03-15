#!/usr/bin/env python3
# modulos/limpeza.py — Seed Cleaner (limpeza de torrents por tempo de seeding)

import time
from collections import defaultdict
from modulos.helpers import extrair_dominio_tracker
from modulos.db import salvar_seed_deletions
from modulos.otel import log, log_seed_cleaner


def get_tracker_rules_for_torrent(trackers, tracker_rules):
    rules = []
    for tracker in trackers:
        url = tracker.get("url", "") if isinstance(tracker, dict) else getattr(tracker, 'url', '')
        if url.startswith("**"):
            continue
        domain = extrair_dominio_tracker(url)
        for rule_domain, days in tracker_rules.items():
            if rule_domain in domain:
                rules.append((rule_domain, days))
                break
    return rules


def executar_seed_cleaner(client, conn, run_id, espacos, tracker_rules, dry_run):
    """
    Limpa torrents elegiveis por tempo de seeding.
    - So executa se disco estiver critico
    - Respeita cross-seed: so deleta quando TODOS os trackers do grupo
      (mesmo nome) satisfizerem o minimo de dias configurado em TRACKER_RULES

    Retorna: quantidade de torrents deletados (ou elegiveis em dry_run)
    """
    print("\n" + "=" * 70)
    print(f"🌱 Seed Cleaner {'[DRY RUN]' if dry_run else '[DELETANDO DE VERDADE]'}")
    print("=" * 70)

    discos_criticos = [nome for nome, d in espacos.items() if d["critico"] and d["seed_cleaner"]]
    if not discos_criticos:
        print("   ✅ Disco p2p com espaço suficiente — seed cleaner não necessário")
        log_seed_cleaner("nao_necessario", 0)
        return 0

    print(f"   🔴 Disco crítico: {', '.join(discos_criticos)} — iniciando limpeza...")
    log("Seed cleaner iniciado", level="warn", discos_criticos=", ".join(discos_criticos))

    if not tracker_rules:
        print("   ⚠️  TRACKER_RULES vazio — pulando seed cleaner")
        log_seed_cleaner("sem_regras", 0)
        return 0

    # Coletar torrents com regras aplicaveis
    torrent_data = []
    for t in client.torrents_info():
        seeding_days = getattr(t, 'seeding_time', 0) / 86400
        try:
            trackers = client.torrents_trackers(t.hash)
        except:
            trackers = []

        rules = get_tracker_rules_for_torrent(trackers, tracker_rules)
        if not rules:
            continue

        torrent_data.append({
            "hash":         t.hash,
            "name":         t.name,
            "seeding_days": seeding_days,
            "size":         getattr(t, 'size', 0),
            "rules":        rules,
        })

    # Agrupar por nome para detectar cross-seeds
    groups = defaultdict(list)
    for t in torrent_data:
        groups[t["name"]].append(t)

    to_delete      = []
    kept_crossseed = []

    for name, group in groups.items():
        all_satisfied = True
        details       = []

        for t in group:
            for domain, required_days in t["rules"]:
                satisfied = t["seeding_days"] >= required_days
                details.append({
                    "torrent":   t,
                    "domain":    domain,
                    "required":  required_days,
                    "actual":    t["seeding_days"],
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
                    "size":       t["size"],
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

    print(f"\n   📋 Elegíveis para deleção: {len(to_delete)}")

    if to_delete:
        print(f"\n   {'TRACKER':<35} {'SEED':>7} {'REGRA':>6}  NOME")
        print("   " + "-" * 100)
        for t in sorted(to_delete, key=lambda x: x["tracker"]):
            cross   = f" [x{t['group_size']}]" if t["group_size"] > 1 else ""
            size_gb = t["size"] / (1024 ** 3)
            print(f"   {t['tracker']:<35} {t['days']:>6.1f}d {t['rule']:>5}d{cross}  "
                  f"{t['name'][:50]}  ({size_gb:.1f} GB)")

    if kept_crossseed:
        print(f"\n   ⏳ Mantidos por cross-seed ({len(kept_crossseed)}):")
        print(f"   {'TRACKER':<35} {'SEED':>7}  NOME")
        print("   " + "-" * 100)
        for t in sorted(kept_crossseed, key=lambda x: x["tracker"]):
            print(f"   {t['tracker']:<35} {t['days']:>6.1f}d  "
                  f"{t['name'][:50]}  | aguardando: {', '.join(t['blocking'])}")

    if dry_run:
        if to_delete:
            salvar_seed_deletions(conn, run_id, to_delete, dry_run=True)
            print(f"\n   ℹ️  DRY RUN — mude SEED_CLEANER_DRY_RUN = False no config.py para apagar de verdade")
        log_seed_cleaner("dry_run", len(to_delete), dry_run=True)
        return len(to_delete) if to_delete else 0

    # Delecao real
    if not to_delete:
        log_seed_cleaner("sem_elegiveis", 0, dry_run=False)
        return 0

    print(f"\n   🗑️  Deletando {len(to_delete)} torrents...")
    deletados_confirmados = []
    falhas = []

    for t in to_delete:
        try:
            client.torrents_delete(delete_files=True, torrent_hashes=t["hash"])
            salvar_seed_deletions(conn, run_id, [t], dry_run=False)
            size_gb = t["size"] / (1024 ** 3)
            print(f"   ✅ {t['name'][:55]}  ({size_gb:.1f} GB)")
            deletados_confirmados.append(t)
        except Exception as e:
            print(f"   ❌ {t['name'][:50]}: {e}")
            falhas.append(t)
        time.sleep(0.5)

    total_gb = sum(t["size"] for t in deletados_confirmados) / (1024 ** 3)
    print(f"\n   ✅ {len(deletados_confirmados)} deletados ({total_gb:.1f} GB liberados)")
    if falhas:
        print(f"   ❌ {len(falhas)} falhas — verifique o log acima")

    log_seed_cleaner("deletados", len(deletados_confirmados),
                     liberado_gb=total_gb, dry_run=False)

    if deletados_confirmados:
        print(f"\n   ⏳ Aguardando 2 minutos para o sistema processar as deleções...")
        time.sleep(120)

    return len(deletados_confirmados)
