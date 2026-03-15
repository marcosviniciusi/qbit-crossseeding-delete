#!/usr/bin/env python3
# modulos/db.py — Operacoes de banco de dados (SQLite)

import os
import sqlite3
import json
from datetime import datetime


def init_db(db_dir, db_path):
    os.makedirs(db_dir, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS runs (
            id                 INTEGER PRIMARY KEY AUTOINCREMENT,
            started_at         TEXT    NOT NULL,
            status             TEXT    NOT NULL,
            checking           INTEGER NOT NULL DEFAULT 0,
            moving             INTEGER NOT NULL DEFAULT 0,
            disk_spaces        TEXT,
            paused_count       INTEGER NOT NULL DEFAULT 0,
            forcados_checking  INTEGER NOT NULL DEFAULT 0,
            tracker_forcados   INTEGER NOT NULL DEFAULT 0,
            tracker_ativados   INTEGER NOT NULL DEFAULT 0,
            seeding_deletados  INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS torrent_snapshots (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id      INTEGER NOT NULL REFERENCES runs(id),
            recorded_at TEXT    NOT NULL,
            hash        TEXT    NOT NULL,
            name        TEXT    NOT NULL,
            state       TEXT    NOT NULL,
            progress    REAL    NOT NULL DEFAULT 0,
            dlspeed     INTEGER NOT NULL DEFAULT 0,
            upspeed     INTEGER NOT NULL DEFAULT 0,
            size        INTEGER NOT NULL DEFAULT 0,
            tracker     TEXT,
            force_start INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS pause_events (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id           INTEGER NOT NULL REFERENCES runs(id),
            event_at         TEXT    NOT NULL,
            event_type       TEXT    NOT NULL,
            reason           TEXT,
            disk_spaces      TEXT,
            discos_criticos  TEXT,
            torrent_hashes   TEXT,
            torrents_count   INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS seed_deletions (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id       INTEGER NOT NULL REFERENCES runs(id),
            deleted_at   TEXT    NOT NULL,
            hash         TEXT    NOT NULL,
            name         TEXT    NOT NULL,
            tracker      TEXT,
            seeding_days REAL    NOT NULL DEFAULT 0,
            rule_days    INTEGER NOT NULL DEFAULT 0,
            size_bytes   INTEGER NOT NULL DEFAULT 0,
            dry_run      INTEGER NOT NULL DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS notifications (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id      INTEGER NOT NULL REFERENCES runs(id),
            sent_at     TEXT    NOT NULL,
            event_type  TEXT    NOT NULL,
            title       TEXT    NOT NULL,
            message     TEXT    NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_snapshots_run      ON torrent_snapshots(run_id);
        CREATE INDEX IF NOT EXISTS idx_snapshots_hash     ON torrent_snapshots(hash);
        CREATE INDEX IF NOT EXISTS idx_snapshots_state    ON torrent_snapshots(state);
        CREATE INDEX IF NOT EXISTS idx_pause_events_run   ON pause_events(run_id);
        CREATE INDEX IF NOT EXISTS idx_pause_events_type  ON pause_events(event_type);
        CREATE INDEX IF NOT EXISTS idx_seed_deletions_run ON seed_deletions(run_id);
        CREATE INDEX IF NOT EXISTS idx_notifications_type ON notifications(event_type);
    """)

    # Migracao: adicionar coluna discos_criticos se nao existir
    try:
        conn.execute("ALTER TABLE pause_events ADD COLUMN discos_criticos TEXT")
        conn.commit()
    except sqlite3.OperationalError:
        pass
    conn.commit()
    return conn


def ler_ultimo_estado(conn):
    cur        = conn.execute("SELECT id, status FROM runs ORDER BY id DESC LIMIT 1")
    ultimo_run = cur.fetchone()

    torrents_pausados = ler_torrents_pausados(conn)
    motivo_pausa      = ler_motivo_pausa(conn)

    discos_criticos = None
    last_pause = conn.execute(
        "SELECT id, discos_criticos FROM pause_events WHERE event_type='pause' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    if last_pause:
        last_restore = conn.execute(
            "SELECT id FROM pause_events WHERE event_type='restore' AND id > ?",
            (last_pause["id"],)
        ).fetchone()
        if not last_restore and last_pause["discos_criticos"]:
            discos_criticos = json.loads(last_pause["discos_criticos"])

    return {
        "run_status":        ultimo_run["status"] if ultimo_run else "active",
        "torrents_pausados": torrents_pausados,
        "motivo_pausa":      motivo_pausa,
        "discos_criticos":   discos_criticos,
        "ultimo_run_id":     ultimo_run["id"] if ultimo_run else None
    }


def criar_run(conn, status, checking, moving, espacos, paused_count=0):
    disk_json = json.dumps({
        nome: {
            "livre":      round(d["livre"], 2),
            "critico":    d["critico"],
            "ok":         d["ok"],
            "limite_min": d["limite_min"],
            "limite_max": d["limite_max"]
        }
        for nome, d in espacos.items()
    })
    cur = conn.execute("""
        INSERT INTO runs (started_at, status, checking, moving, disk_spaces, paused_count)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (datetime.now().isoformat(), status, checking, moving, disk_json, paused_count))
    conn.commit()
    return cur.lastrowid


def atualizar_run(conn, run_id, **kwargs):
    if not kwargs:
        return
    sets = ", ".join(f"{k} = ?" for k in kwargs)
    conn.execute(f"UPDATE runs SET {sets} WHERE id = ?", list(kwargs.values()) + [run_id])
    conn.commit()


def salvar_snapshots(conn, run_id, todos_torrents, tracker_map):
    agora = datetime.now().isoformat()
    rows  = [(
        run_id, agora, t.hash, t.name, t.state,
        round(getattr(t, 'progress', 0), 4),
        getattr(t, 'dlspeed', 0),
        getattr(t, 'upspeed', 0),
        getattr(t, 'size', 0),
        tracker_map.get(t.hash, 'unknown'),
        1 if getattr(t, 'force_start', False) else 0
    ) for t in todos_torrents]
    conn.executemany("""
        INSERT INTO torrent_snapshots
            (run_id, recorded_at, hash, name, state, progress,
             dlspeed, upspeed, size, tracker, force_start)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, rows)
    conn.commit()
    return len(rows)


def registrar_pause_event(conn, run_id, event_type, reason=None, espacos=None,
                          hashes=None, discos_criticos=None):
    disk_json     = json.dumps({
        n: {"livre": round(d["livre"], 2), "critico": d["critico"]}
        for n, d in espacos.items()
    }) if espacos else None
    hashes_json   = json.dumps(list(hashes)) if hashes else "[]"
    criticos_json = json.dumps(discos_criticos) if discos_criticos else None
    conn.execute("""
        INSERT INTO pause_events
            (run_id, event_at, event_type, reason, disk_spaces,
             discos_criticos, torrent_hashes, torrents_count)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (run_id, datetime.now().isoformat(), event_type, reason,
          disk_json, criticos_json, hashes_json, len(hashes) if hashes else 0))
    conn.commit()


def salvar_seed_deletions(conn, run_id, deletados, dry_run):
    agora = datetime.now().isoformat()
    conn.executemany("""
        INSERT INTO seed_deletions
            (run_id, deleted_at, hash, name, tracker, seeding_days, rule_days, size_bytes, dry_run)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, [(
        run_id, agora,
        t["hash"], t["name"], t["tracker"],
        t["days"], t["rule"], t.get("size", 0),
        1 if dry_run else 0
    ) for t in deletados])
    conn.commit()


def ler_torrents_pausados(conn):
    last_pause = conn.execute(
        "SELECT id, torrent_hashes FROM pause_events WHERE event_type='pause' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    if not last_pause:
        return set()
    last_restore = conn.execute(
        "SELECT id FROM pause_events WHERE event_type='restore' AND id > ?",
        (last_pause["id"],)
    ).fetchone()
    if last_restore:
        return set()
    hashes = json.loads(last_pause["torrent_hashes"] or "[]")
    return set(hashes)


def ler_motivo_pausa(conn):
    last_pause = conn.execute(
        "SELECT id, reason FROM pause_events WHERE event_type='pause' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    if not last_pause:
        return []
    last_restore = conn.execute(
        "SELECT id FROM pause_events WHERE event_type='restore' AND id > ?",
        (last_pause["id"],)
    ).fetchone()
    if last_restore:
        return []
    return last_pause["reason"].split(',') if last_pause["reason"] else []


def registrar_notificacao(conn, run_id, event_type, title, message):
    conn.execute("""
        INSERT INTO notifications (run_id, sent_at, event_type, title, message)
        VALUES (?, ?, ?, ?, ?)
    """, (run_id, datetime.now().isoformat(), event_type, title, message))
    conn.commit()


def minutos_desde_ultima_notificacao(conn, event_type):
    row = conn.execute("""
        SELECT sent_at FROM notifications
        WHERE event_type = ?
        ORDER BY id DESC LIMIT 1
    """, (event_type,)).fetchone()
    if not row:
        return None
    ultima = datetime.fromisoformat(row["sent_at"])
    delta  = datetime.now() - ultima
    return delta.total_seconds() / 60
