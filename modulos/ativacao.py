#!/usr/bin/env python3
# modulos/ativacao.py — Ativacao de downloads, restauracao e gerenciamento de trackers

import time
from collections import defaultdict
from modulos.db import (
    ler_torrents_pausados,
    registrar_pause_event,
)
from modulos.helpers import (
    extrair_dominio_tracker,
    obter_downloads_ativos,
    notificar_se_necessario,
)
from modulos.otel import log, log_pausa, log_tracker


def forcar_start_checking(client, checking_torrents):
    """Aplica force_start em torrents em estado checking/checkingResumeData"""
    if not checking_torrents:
        return 0
    forcados = 0
    print(f"\n⚡ Force start em {len(checking_torrents)} torrents em checking...")
    for t in checking_torrents:
        try:
            client.torrents_set_force_start(torrent_hashes=t.hash, enable=True)
            print(f"   ⚡ {t.name[:55]} [{t.state}]")
            forcados += 1
            time.sleep(0.1)
        except Exception as e:
            print(f"   ❌ {t.name[:30]}: {e}")
    print(f"   ✅ {forcados} torrents com force start aplicado")
    log(f"Force start checking: {forcados} torrents", forcados=forcados)
    return forcados


def executar_pausa(client, conn, run_id, espacos, moving_count, moving_torrents,
                   enviar_notificacao_fn):
    """Pausa downloads ativos quando disco esta critico"""
    downloads_ativos      = obter_downloads_ativos(client)
    torrents_pausados_ant = ler_torrents_pausados(conn)

    print(f"\n⚠️  DISCO CRÍTICO — pausando downloads")
    for nome, d in espacos.items():
        if d["critico"]:
            print(f"   🔴 {nome}: {d['livre']:.1f} GB (mín: {d['limite_min']} GB)")

    novos_pausados = []
    if downloads_ativos:
        print(f"\n⏸️  Pausando {len(downloads_ativos)} downloads ativos...")
        for t in downloads_ativos:
            try:
                try:
                    client.torrents_set_force_start(torrent_hashes=t.hash, enable=False)
                    time.sleep(0.1)
                except:
                    pass
                client.torrents_pause(torrent_hashes=t.hash)
                novos_pausados.append(t.hash)
                print(f"   ⏸️  {t.name[:55]}")
            except Exception as e:
                print(f"   ❌ {t.name[:30]}: {e}")
    else:
        print(f"   ℹ️  Nenhum download em forcedDL para pausar")

    todos_pausados = torrents_pausados_ant | set(novos_pausados)
    discos_criticos = [n for n, d in espacos.items() if d["critico"]]
    registrar_pause_event(conn, run_id, 'pause', reason='disk_space',
                          espacos=espacos, hashes=todos_pausados,
                          discos_criticos=discos_criticos)

    print(f"\n   Total pausados: {len(todos_pausados)} "
          f"(anteriores: {len(torrents_pausados_ant)}, novos: {len(novos_pausados)})")

    log_pausa("pause", espacos, len(todos_pausados), discos_criticos)

    if moving_count > 0:
        print(f"\n   🔍 Recheck em {moving_count} torrents MOVING...")
        for t in moving_torrents:
            try:
                client.torrents_recheck(torrent_hashes=t.hash)
                time.sleep(0.1)
            except:
                pass

    notificar_se_necessario(conn, run_id, 'paused', enviar_notificacao_fn)


def executar_restauracao(client, conn, run_id, espacos, enviar_notificacao_fn):
    """Restaura downloads pausados quando condicoes normalizam"""
    torrents_pausados = ler_torrents_pausados(conn)
    if not torrents_pausados:
        return

    print(f"\n✅ Condições normalizadas — restaurando {len(torrents_pausados)} downloads...")
    restored = failed = 0

    for h in torrents_pausados:
        try:
            info = client.torrents_info(torrent_hashes=h)
            if not info:
                failed += 1
                continue
            client.torrents_resume(torrent_hashes=h)
            time.sleep(0.1)
            try:
                client.torrents_set_force_start(torrent_hashes=h, enable=True)
                print(f"   ▶️  {info[0].name[:55]} [FORCE]")
            except:
                print(f"   ▶️  {info[0].name[:55]}")
            restored += 1
        except Exception as e:
            print(f"   ❌ {h[:16]}: {e}")
            failed += 1

    registrar_pause_event(conn, run_id, 'restore', espacos=espacos, hashes=torrents_pausados)

    print(f"\n   ✅ Restaurados: {restored}" + (f"  ❌ Falhas: {failed}" if failed else ""))
    log_pausa("restore", espacos, len(torrents_pausados))
    notificar_se_necessario(conn, run_id, 'restored', enviar_notificacao_fn)


def analisar_torrents_por_tracker(client):
    """Classifica torrents por tracker e estado"""
    tracker_analise = defaultdict(lambda: {
        'downloading_ativo': [], 'downloading_fila': [],
        'paused': [], 'seeding': [], 'outros': []
    })
    for t in client.torrents_info():
        tracker_principal = "no_tracker"
        try:
            for tr in client.torrents_trackers(t.hash):
                if tr.url and not tr.url.startswith('**'):
                    tracker_principal = extrair_dominio_tracker(tr.url)
                    break
        except:
            pass

        info    = {
            'nome':        t.name[:50] + ('...' if len(t.name) > 50 else ''),
            'hash':        t.hash,
            'state':       t.state,
            'dlspeed':     getattr(t, 'dlspeed', 0),
            'force_start': getattr(t, 'force_start', False)
        }
        state   = t.state
        dlspeed = info['dlspeed']

        if state == 'forcedDL':
            tracker_analise[tracker_principal]['downloading_ativo'].append(info)
        elif state == 'downloading' and dlspeed > 0:
            tracker_analise[tracker_principal]['downloading_ativo'].append(info)
        elif state in ('downloading', 'stalledDL', 'queuedDL', 'checkingDL'):
            tracker_analise[tracker_principal]['downloading_fila'].append(info)
        elif state in ('pausedDL', 'pausedUP'):
            tracker_analise[tracker_principal]['paused'].append(info)
        elif state in ('uploading', 'stalledUP', 'queuedUP', 'checkingUP', 'forcedUP'):
            tracker_analise[tracker_principal]['seeding'].append(info)
        else:
            tracker_analise[tracker_principal]['outros'].append(info)

    return dict(tracker_analise)


def gerenciar_trackers(client, min_downloads, min_torrents):
    """Garante minimo de downloads ativos por tracker"""
    print("\n" + "=" * 70)
    print("🎯 Gerenciamento de Trackers")
    print("=" * 70)

    total_forcados = total_ativados = 0

    for tracker, dados in sorted(analisar_torrents_por_tracker(client).items()):
        ativo_count  = len(dados['downloading_ativo'])
        fila_count   = len(dados['downloading_fila'])
        paused_count = len(dados['paused'])
        total_count  = (ativo_count + fila_count + paused_count +
                        len(dados['seeding']) + len(dados['outros']))

        print(f"\n🌐 {tracker}:")
        print(f"  📥 Ativo: {ativo_count}  ⏳ Fila: {fila_count}  "
              f"⏸️  Pausados: {paused_count}  📤 Seeding: {len(dados['seeding'])}  📊 Total: {total_count}")

        if ativo_count >= min_downloads:
            print(f"  ✅ OK ({ativo_count} >= {min_downloads})")
            continue

        if total_count < min_torrents and ativo_count > 0:
            print(f"  ⚠️  Tracker pequeno com {ativo_count} ativo(s) — IGNORANDO")
            continue

        if total_count < min_torrents and ativo_count == 0:
            print(f"  ⚠️  Tracker pequeno sem ativos — ATIVANDO")

        necessarios = min_downloads - ativo_count
        print(f"  🎯 PRECISA: +{necessarios}")

        forcados_tracker = ativados_tracker = 0

        for info in dados['downloading_fila'][:necessarios]:
            try:
                client.torrents_set_force_start(torrent_hashes=info['hash'], enable=True)
                print(f"    ▶️  FORCE: {info['nome']}")
                total_forcados   += 1
                forcados_tracker += 1
                necessarios      -= 1
            except Exception as e:
                print(f"    ❌ {e}")
            if necessarios <= 0:
                break

        for info in dados['paused'][:necessarios]:
            try:
                client.torrents_resume(torrent_hashes=info['hash'])
                try:
                    client.torrents_set_force_start(torrent_hashes=info['hash'], enable=True)
                    print(f"    ▶️  ATIVAR+FORCE: {info['nome']}")
                except:
                    print(f"    ▶️  ATIVAR: {info['nome']}")
                total_ativados   += 1
                ativados_tracker += 1
                necessarios      -= 1
            except Exception as e:
                print(f"    ❌ {e}")
            if necessarios <= 0:
                break

        if forcados_tracker or ativados_tracker:
            log_tracker(tracker, ativo_count, fila_count,
                        forcados_tracker, ativados_tracker)

    print(f"\n📊 Trackers — Forçados: {total_forcados}  Ativados: {total_ativados}")
    return total_forcados, total_ativados
