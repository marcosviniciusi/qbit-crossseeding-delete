#!/usr/bin/env python3
# modulos/checagem_disco.py — Orquestrador: checagem de disco -> limpeza -> ativacao
#
# Este e o modulo central que verifica o estado dos discos e decide:
#   1. Se precisa chamar limpeza (seed cleaner)
#   2. Se precisa pausar ou restaurar downloads (ativacao)
#   3. Se pode gerenciar trackers normalmente

from modulos.db import (
    ler_ultimo_estado,
    criar_run,
    atualizar_run,
    salvar_snapshots,
    ler_torrents_pausados,
    ler_motivo_pausa,
    registrar_pause_event,
)
from modulos.helpers import (
    verificar_espacos,
    imprimir_espacos,
    obter_contagem_checking_moving,
    construir_tracker_map,
    notificar_se_necessario,
)
from modulos.limpeza import executar_seed_cleaner
from modulos.ativacao import (
    forcar_start_checking,
    executar_pausa,
    executar_restauracao,
    gerenciar_trackers,
)
from modulos.otel import log, log_disco, log_run


def executar_checagem(client, conn, paths_config, tracker_rules,
                      seed_cleaner_dry_run, min_downloads_per_tracker,
                      min_torrents_per_tracker, enviar_notificacao_fn):
    """
    Fluxo principal de checagem de disco.

    Retorna o run_id criado.
    """
    # ------------------------------------------------------------------
    # PASSO 1: Ler ultimo estado do banco
    # ------------------------------------------------------------------
    ultimo_estado = ler_ultimo_estado(conn)
    tinha_pausados = bool(ultimo_estado["torrents_pausados"])

    print(f"\n📋 Último estado: {ultimo_estado['run_status'].upper()}")
    if tinha_pausados:
        print(f"   💤 {len(ultimo_estado['torrents_pausados'])} torrents pausados desde última execução")
        if ultimo_estado["motivo_pausa"]:
            print(f"   Motivo: {', '.join(ultimo_estado['motivo_pausa'])}")

    # ------------------------------------------------------------------
    # PASSO 2: Coletar estado atual
    # ------------------------------------------------------------------
    print(f"\n📊 Estado atual:")
    espacos = verificar_espacos(paths_config)
    imprimir_espacos(espacos)
    log_disco(espacos)

    checking_count, moving_count, checking_torrents, moving_torrents = \
        obter_contagem_checking_moving(client)
    checking_moving_total = checking_count + moving_count
    print(f"\n   🔍 Checking: {checking_count}  🔄 Moving: {moving_count}  📦 Total: {checking_moving_total}")

    qualquer_critico     = any(d["critico"] and d["pause_trigger"] for d in espacos.values())
    todos_ok             = all(d["ok"] for d in espacos.values() if d["pause_trigger"])
    checking_moving_zero = checking_moving_total == 0
    critico_seed_cleaner = any(d["critico"] and d["seed_cleaner"] for d in espacos.values())
    pode_restaurar       = todos_ok and checking_moving_zero

    # ------------------------------------------------------------------
    # PASSO 3: Criar registro do run
    # ------------------------------------------------------------------
    run_status = 'paused' if (tinha_pausados or qualquer_critico) else 'active'
    run_id     = criar_run(conn, run_status, checking_count, moving_count,
                           espacos, len(ultimo_estado["torrents_pausados"]))

    # ------------------------------------------------------------------
    # PASSO 4: Snapshot de torrents
    # ------------------------------------------------------------------
    print(f"\n📸 Salvando snapshot...")
    todos_torrents = client.torrents_info()
    tracker_map    = construir_tracker_map(client, todos_torrents)
    count = salvar_snapshots(conn, run_id, todos_torrents, tracker_map)
    print(f"   💾 {count} torrents salvos no banco")

    # ------------------------------------------------------------------
    # PASSO 5: Logica principal baseada no estado anterior
    # ------------------------------------------------------------------
    forcados_checking      = 0
    seeding_deletados      = 0
    total_forcados         = 0
    total_ativados         = 0
    pode_gerenciar_trackers = False

    if tinha_pausados:
        # ── Havia torrents pausados: verificar se pode restaurar ──
        print(f"\n🔄 Sistema estava pausado — verificando condições para restaurar...")

        discos_criticos_registro = ultimo_estado["discos_criticos"]

        if discos_criticos_registro is None:
            print(f"\n   ⚠️  Sem informação do disco que causou a pausa — verificação manual necessária")
            notificar_se_necessario(conn, run_id, 'waiting_paused', enviar_notificacao_fn)
            registrar_pause_event(conn, run_id, 'waiting',
                                  espacos=espacos,
                                  hashes=ultimo_estado["torrents_pausados"])
            forcados_checking = forcar_start_checking(client, checking_torrents)

        elif pode_restaurar:
            executar_restauracao(client, conn, run_id, espacos, enviar_notificacao_fn)
            forcados_checking       = forcar_start_checking(client, checking_torrents)
            pode_gerenciar_trackers = True

        else:
            print(f"\n   ⚠️  Ainda não é possível restaurar:")
            print(f"      Disco(s) que causaram pausa: {', '.join(discos_criticos_registro)}")

            for nome, d in espacos.items():
                if d["pause_trigger"]:
                    icon = "🔴" if d["critico"] else "🟢"
                    print(f"      {icon} {nome}: {d['livre']:.1f} GB "
                          f"(min: {d['limite_min']}, max: {d['limite_max']})")

            if not checking_moving_zero:
                print(f"      🔴 Checking+Moving ainda ativo ({checking_moving_total})")

            pausa_por_p2p     = any(espacos[n]["seed_cleaner"]
                                    for n in discos_criticos_registro if n in espacos)
            pausa_por_destino = any(not espacos[n]["seed_cleaner"]
                                    for n in discos_criticos_registro if n in espacos)

            if pausa_por_p2p and critico_seed_cleaner:
                # p2p ainda critico — seed cleaner pode ajudar
                print(f"\n   💡 Pausa causada pelo p2p — tentando seed cleaner...")
                seeding_deletados = executar_seed_cleaner(
                    client, conn, run_id, espacos, tracker_rules, seed_cleaner_dry_run)

                if seeding_deletados > 0 and not seed_cleaner_dry_run:
                    print(f"\n🔄 Reavaliando espaço após seed cleaner...")
                    espacos              = verificar_espacos(paths_config)
                    imprimir_espacos(espacos)
                    log_disco(espacos)
                    todos_ok             = all(d["ok"] for d in espacos.values() if d["pause_trigger"])
                    critico_seed_cleaner = any(d["critico"] and d["seed_cleaner"] for d in espacos.values())
                    pode_restaurar       = todos_ok and checking_moving_zero

                    if pode_restaurar:
                        executar_restauracao(client, conn, run_id, espacos, enviar_notificacao_fn)
                        forcados_checking       = forcar_start_checking(client, checking_torrents)
                        pode_gerenciar_trackers = True
                    else:
                        print(f"   ⚠️  Espaço ainda insuficiente — mantendo pausa")
                        registrar_pause_event(conn, run_id, 'waiting',
                                              espacos=espacos,
                                              hashes=ultimo_estado["torrents_pausados"],
                                              discos_criticos=discos_criticos_registro)
                        notificar_se_necessario(conn, run_id, 'waiting_paused', enviar_notificacao_fn)
                else:
                    registrar_pause_event(conn, run_id, 'waiting',
                                          espacos=espacos,
                                          hashes=ultimo_estado["torrents_pausados"],
                                          discos_criticos=discos_criticos_registro)
                    notificar_se_necessario(conn, run_id, 'waiting_paused', enviar_notificacao_fn)

            elif pausa_por_destino and not pausa_por_p2p:
                destinos = [n for n in discos_criticos_registro
                            if n in espacos and not espacos[n]["seed_cleaner"]]
                print(f"\n   ⏳ Pausa causada pelo disco de destino ({', '.join(destinos)}) "
                      f"— aguardando Radarr/Sonarr liberar espaço...")
                registrar_pause_event(conn, run_id, 'waiting',
                                      espacos=espacos,
                                      hashes=ultimo_estado["torrents_pausados"],
                                      discos_criticos=discos_criticos_registro)
                notificar_se_necessario(conn, run_id, 'waiting_paused', enviar_notificacao_fn)

            else:
                print(f"\n   ⏳ Disco normalizado mas checking/moving ainda ativo — aguardando...")
                registrar_pause_event(conn, run_id, 'waiting',
                                      espacos=espacos,
                                      hashes=ultimo_estado["torrents_pausados"],
                                      discos_criticos=discos_criticos_registro)
                notificar_se_necessario(conn, run_id, 'waiting_paused', enviar_notificacao_fn)

            forcados_checking = forcar_start_checking(client, checking_torrents)

    else:
        # ── Sem pausados: fluxo normal ──
        if qualquer_critico:
            seeding_deletados = executar_seed_cleaner(
                client, conn, run_id, espacos, tracker_rules, seed_cleaner_dry_run)

            if seeding_deletados > 0 and not seed_cleaner_dry_run:
                print(f"\n🔄 Reavaliando espaço após seed cleaner...")
                espacos              = verificar_espacos(paths_config)
                imprimir_espacos(espacos)
                log_disco(espacos)
                qualquer_critico     = any(d["critico"] and d["pause_trigger"] for d in espacos.values())

            if qualquer_critico:
                forcados_checking = forcar_start_checking(client, checking_torrents)
                executar_pausa(client, conn, run_id, espacos, moving_count,
                               moving_torrents, enviar_notificacao_fn)
            else:
                print(f"\n✅ Disco normalizado após seed cleaner — sistema ativo")
                forcados_checking       = forcar_start_checking(client, checking_torrents)
                pode_gerenciar_trackers = True

        else:
            forcados_checking       = forcar_start_checking(client, checking_torrents)
            pode_gerenciar_trackers = True

    # ------------------------------------------------------------------
    # PASSO 6: Gerenciar trackers
    # ------------------------------------------------------------------
    if pode_gerenciar_trackers:
        total_forcados, total_ativados = gerenciar_trackers(
            client, min_downloads_per_tracker, min_torrents_per_tracker)
    else:
        print(f"\n⏭️  Gerenciamento de trackers PAUSADO")

    # ------------------------------------------------------------------
    # PASSO 7: Fechar run
    # ------------------------------------------------------------------
    atualizar_run(conn, run_id,
                  status=           'active' if pode_gerenciar_trackers else 'paused',
                  forcados_checking=forcados_checking,
                  tracker_forcados= total_forcados,
                  tracker_ativados= total_ativados,
                  seeding_deletados=seeding_deletados,
                  paused_count=     len(ler_torrents_pausados(conn)))

    # Resumo
    print("\n" + "=" * 70)
    print("📊 RESUMO FINAL:")
    pausados_final = ler_torrents_pausados(conn)
    if pausados_final:
        print(f"🛑 Sistema PAUSADO ({len(pausados_final)} torrents)")
        motivos = ler_motivo_pausa(conn)
        if motivos:
            print(f"   Motivo: {', '.join(motivos)}")
    else:
        print(f"✅ Sistema ATIVO")

    print(f"📦 Checking+Moving: {checking_moving_total}")
    if forcados_checking:
        print(f"⚡ Force start checking: {forcados_checking}")
    if seeding_deletados:
        print(f"🗑️  Seed cleaner: {seeding_deletados} {'(DRY RUN)' if seed_cleaner_dry_run else 'deletados'}")
    if total_forcados or total_ativados:
        print(f"🎯 Trackers — Forçados: {total_forcados}  Ativados: {total_ativados}")

    print(f"\n🗄️  Run #{run_id}")

    # Log OTEL do run finalizado
    log_run(run_id, 'active' if pode_gerenciar_trackers else 'paused', {
        "checking_moving": checking_moving_total,
        "forcados_checking": forcados_checking,
        "seeding_deletados": seeding_deletados,
        "tracker_forcados": total_forcados,
        "tracker_ativados": total_ativados,
        "pausados": len(pausados_final),
    })

    return run_id
