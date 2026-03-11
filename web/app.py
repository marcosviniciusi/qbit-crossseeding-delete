#!/usr/bin/env python3
"""
qBit Manager Web — Interface web para o qBit Manager.

Uso:
    python web/app.py
    # ou
    flask --app web/app run --host 0.0.0.0 --port 5000
"""

import json
import os
import sqlite3
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

from flask import Flask, jsonify, render_template, request

# ---------------------------------------------------------------------------
# Configuração
# ---------------------------------------------------------------------------

CONFIG_DIR = os.environ.get("QBIT_MANAGER_CONFIG_DIR", "/etc/qbit-manager")

# Adicionar CONFIG_DIR ao path para importar config.py
if CONFIG_DIR not in sys.path:
    sys.path.insert(0, CONFIG_DIR)

# Tentar carregar configurações
try:
    from config import DB_DIR, DB_PATH  # type: ignore[import-untyped]
except ImportError:
    DB_DIR = os.environ.get("QBIT_MANAGER_DB_DIR", "/var/lib/qbit-manager")
    DB_PATH = os.environ.get("QBIT_MANAGER_DB_PATH", f"{DB_DIR}/qbit.db")

SERVICE_NAME = os.environ.get("QBIT_MANAGER_SERVICE", "qbit-manager")
LOG_FILE = os.environ.get("QBIT_MANAGER_LOG", "/var/log/qbit-manager.log")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.py")
TRACKER_RULES_FILE = os.path.join(CONFIG_DIR, "tracker_rules.py")

# ---------------------------------------------------------------------------
# Flask App
# ---------------------------------------------------------------------------

app = Flask(__name__)
app.config["JSON_SORT_KEYS"] = False


def get_db() -> sqlite3.Connection:
    """Abre conexão com o banco de dados."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# ---------------------------------------------------------------------------
# Páginas
# ---------------------------------------------------------------------------

@app.route("/")
def index() -> str:
    return render_template("dashboard.html", active="dashboard")


@app.route("/service")
def service_page() -> str:
    return render_template("service.html", active="service")


@app.route("/config")
def config_page() -> str:
    return render_template("config.html", active="config")


@app.route("/logs")
def logs_page() -> str:
    return render_template("logs.html", active="logs")


# ---------------------------------------------------------------------------
# API — Dashboard
# ---------------------------------------------------------------------------

@app.route("/api/stats")
def api_stats() -> Any:
    """Retorna estatísticas gerais para o dashboard."""
    conn = get_db()
    try:
        # Último run
        last_run = conn.execute(
            "SELECT * FROM runs ORDER BY id DESC LIMIT 1"
        ).fetchone()

        # Total de runs
        total_runs = conn.execute("SELECT COUNT(*) as c FROM runs").fetchone()["c"]

        # Runs nas últimas 24h
        since = (datetime.now() - timedelta(hours=24)).isoformat()
        runs_24h = conn.execute(
            "SELECT COUNT(*) as c FROM runs WHERE started_at >= ?", (since,)
        ).fetchone()["c"]

        # Total de deleções
        total_deletions = conn.execute(
            "SELECT COUNT(*) as c FROM seed_deletions"
        ).fetchone()["c"]

        # Total de pause events
        total_pauses = conn.execute(
            "SELECT COUNT(*) as c FROM pause_events WHERE event_type = 'pause'"
        ).fetchone()["c"]

        result = {
            "last_run": dict(last_run) if last_run else None,
            "total_runs": total_runs,
            "runs_24h": runs_24h,
            "total_deletions": total_deletions,
            "total_pauses": total_pauses,
        }
        return jsonify(result)
    finally:
        conn.close()


@app.route("/api/disk-history")
def api_disk_history() -> Any:
    """Retorna histórico de espaço em disco (últimas N execuções)."""
    limit = request.args.get("limit", 50, type=int)
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT started_at, disk_spaces FROM runs WHERE disk_spaces IS NOT NULL "
            "ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()

        history: list[dict[str, Any]] = []
        for row in reversed(rows):
            entry: dict[str, Any] = {"timestamp": row["started_at"]}
            spaces = json.loads(row["disk_spaces"])
            for disk_name, disk_data in spaces.items():
                entry[disk_name] = disk_data.get("livre", 0)
            history.append(entry)

        # Nomes dos discos
        disk_names: list[str] = []
        if history:
            disk_names = [k for k in history[0] if k != "timestamp"]

        return jsonify({"history": history, "disk_names": disk_names})
    finally:
        conn.close()


@app.route("/api/runs-history")
def api_runs_history() -> Any:
    """Retorna histórico de runs com contagens."""
    limit = request.args.get("limit", 50, type=int)
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT id, started_at, status, checking, moving, paused_count, "
            "forcados_checking, tracker_forcados, tracker_ativados, seeding_deletados "
            "FROM runs ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return jsonify([dict(r) for r in reversed(rows)])
    finally:
        conn.close()


@app.route("/api/torrent-states")
def api_torrent_states() -> Any:
    """Retorna distribuição de estados dos torrents do último snapshot."""
    conn = get_db()
    try:
        last_run = conn.execute("SELECT id FROM runs ORDER BY id DESC LIMIT 1").fetchone()
        if not last_run:
            return jsonify({})

        rows = conn.execute(
            "SELECT state, COUNT(*) as count FROM torrent_snapshots "
            "WHERE run_id = ? GROUP BY state ORDER BY count DESC",
            (last_run["id"],)
        ).fetchall()
        return jsonify({r["state"]: r["count"] for r in rows})
    finally:
        conn.close()


@app.route("/api/tracker-distribution")
def api_tracker_distribution() -> Any:
    """Retorna distribuição de torrents por tracker do último snapshot."""
    conn = get_db()
    try:
        last_run = conn.execute("SELECT id FROM runs ORDER BY id DESC LIMIT 1").fetchone()
        if not last_run:
            return jsonify({})

        rows = conn.execute(
            "SELECT tracker, COUNT(*) as count FROM torrent_snapshots "
            "WHERE run_id = ? GROUP BY tracker ORDER BY count DESC LIMIT 15",
            (last_run["id"],)
        ).fetchall()
        return jsonify({r["tracker"]: r["count"] for r in rows})
    finally:
        conn.close()


@app.route("/api/seed-deletions")
def api_seed_deletions() -> Any:
    """Retorna histórico de deleções do seed cleaner."""
    limit = request.args.get("limit", 100, type=int)
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT sd.*, r.started_at as run_date FROM seed_deletions sd "
            "JOIN runs r ON sd.run_id = r.id "
            "ORDER BY sd.id DESC LIMIT ?", (limit,)
        ).fetchall()
        return jsonify([dict(r) for r in rows])
    finally:
        conn.close()


@app.route("/api/pause-events")
def api_pause_events() -> Any:
    """Retorna histórico de eventos de pausa."""
    limit = request.args.get("limit", 50, type=int)
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT * FROM pause_events ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return jsonify([dict(r) for r in rows])
    finally:
        conn.close()


@app.route("/api/notifications")
def api_notifications() -> Any:
    """Retorna histórico de notificações."""
    limit = request.args.get("limit", 50, type=int)
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT * FROM notifications ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return jsonify([dict(r) for r in rows])
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# API — Serviço
# ---------------------------------------------------------------------------

def _run_systemctl(action: str) -> dict[str, Any]:
    """Executa comando systemctl e retorna resultado."""
    try:
        result = subprocess.run(
            ["systemctl", action, SERVICE_NAME],
            capture_output=True, text=True, timeout=30,
        )
        return {
            "success": result.returncode == 0,
            "output": result.stdout.strip(),
            "error": result.stderr.strip(),
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "Timeout ao executar comando"}
    except FileNotFoundError:
        return {"success": False, "error": "systemctl nao encontrado"}


@app.route("/api/service/status")
def api_service_status() -> Any:
    """Retorna status do serviço."""
    try:
        result = subprocess.run(
            ["systemctl", "is-active", SERVICE_NAME],
            capture_output=True, text=True, timeout=10,
        )
        is_active = result.stdout.strip() == "active"

        result_detail = subprocess.run(
            ["systemctl", "status", SERVICE_NAME],
            capture_output=True, text=True, timeout=10,
        )

        return jsonify({
            "active": is_active,
            "status": result.stdout.strip(),
            "detail": result_detail.stdout,
        })
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        return jsonify({"active": False, "status": "unknown", "error": str(e)})


@app.route("/api/service/<action>", methods=["POST"])
def api_service_action(action: str) -> Any:
    """Executa ação no serviço (start, stop, restart)."""
    if action not in ("start", "stop", "restart"):
        return jsonify({"success": False, "error": "Acao invalida"}), 400
    result = _run_systemctl(action)
    return jsonify(result)


@app.route("/api/service/run-now", methods=["POST"])
def api_service_run_now() -> Any:
    """Executa o qbit-manager manualmente uma vez."""
    script = Path(__file__).parent.parent / "qbit-manager.py"
    if not script.exists():
        return jsonify({"success": False, "error": "Script nao encontrado"})

    try:
        result = subprocess.run(
            [sys.executable, str(script)],
            capture_output=True, text=True, timeout=300,
        )
        return jsonify({
            "success": result.returncode == 0,
            "output": result.stdout,
            "error": result.stderr,
        })
    except subprocess.TimeoutExpired:
        return jsonify({"success": False, "error": "Timeout (5 min)"})


# ---------------------------------------------------------------------------
# API — Configuração
# ---------------------------------------------------------------------------

@app.route("/api/config")
def api_config_read() -> Any:
    """Lê o arquivo de configuração."""
    try:
        content = Path(CONFIG_FILE).read_text(encoding="utf-8")
        return jsonify({"content": content, "path": CONFIG_FILE})
    except FileNotFoundError:
        return jsonify({"content": "", "path": CONFIG_FILE, "error": "Arquivo nao encontrado"})


@app.route("/api/config", methods=["POST"])
def api_config_write() -> Any:
    """Salva o arquivo de configuração."""
    data = request.get_json()
    if not data or "content" not in data:
        return jsonify({"success": False, "error": "Conteudo nao fornecido"}), 400

    try:
        # Backup antes de salvar
        config_path = Path(CONFIG_FILE)
        if config_path.exists():
            backup = config_path.with_suffix(".py.bak")
            backup.write_text(config_path.read_text(encoding="utf-8"), encoding="utf-8")

        config_path.write_text(data["content"], encoding="utf-8")
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@app.route("/api/tracker-rules")
def api_tracker_rules_read() -> Any:
    """Lê o arquivo de tracker rules."""
    try:
        content = Path(TRACKER_RULES_FILE).read_text(encoding="utf-8")
        return jsonify({"content": content, "path": TRACKER_RULES_FILE})
    except FileNotFoundError:
        return jsonify({"content": "", "path": TRACKER_RULES_FILE, "error": "Arquivo nao encontrado"})


@app.route("/api/tracker-rules", methods=["POST"])
def api_tracker_rules_write() -> Any:
    """Salva o arquivo de tracker rules."""
    data = request.get_json()
    if not data or "content" not in data:
        return jsonify({"success": False, "error": "Conteudo nao fornecido"}), 400

    try:
        rules_path = Path(TRACKER_RULES_FILE)
        if rules_path.exists():
            backup = rules_path.with_suffix(".py.bak")
            backup.write_text(rules_path.read_text(encoding="utf-8"), encoding="utf-8")

        rules_path.write_text(data["content"], encoding="utf-8")
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


# ---------------------------------------------------------------------------
# API — Logs
# ---------------------------------------------------------------------------

@app.route("/api/logs")
def api_logs() -> Any:
    """Retorna últimas linhas do log."""
    lines = request.args.get("lines", 200, type=int)
    source = request.args.get("source", "journalctl")

    try:
        if source == "file" and os.path.exists(LOG_FILE):
            result = subprocess.run(
                ["tail", "-n", str(lines), LOG_FILE],
                capture_output=True, text=True, timeout=10,
            )
            return jsonify({"logs": result.stdout, "source": "file"})
        else:
            result = subprocess.run(
                ["journalctl", "-u", SERVICE_NAME, "-n", str(lines), "--no-pager"],
                capture_output=True, text=True, timeout=10,
            )
            return jsonify({"logs": result.stdout, "source": "journalctl"})
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        return jsonify({"logs": f"Erro ao ler logs: {e}", "source": "error"})


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    port = int(os.environ.get("QBIT_MANAGER_WEB_PORT", 5000))
    host = os.environ.get("QBIT_MANAGER_WEB_HOST", "0.0.0.0")
    debug = os.environ.get("QBIT_MANAGER_WEB_DEBUG", "false").lower() == "true"

    print(f"qBit Manager Web - http://{host}:{port}")
    print(f"Banco: {DB_PATH}")
    print(f"Config: {CONFIG_FILE}")
    app.run(host=host, port=port, debug=debug)
