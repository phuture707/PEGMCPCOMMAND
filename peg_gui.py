#!/usr/bin/env python3
"""
Pegasus Galaxy MCP GUI Dashboard & Command Hub
A complete interactive web-based GUI for Pegasus Galaxy MCP.
"""

import argparse
import datetime
import json
import os
import sys
import signal
import subprocess
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from socketserver import ThreadingMixIn
from typing import Any, Dict, Optional

# Ensure UTF-8 output on Windows consoles
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass

from peg_client import PegasusMCPClient, PegasusMCPError

DEFAULT_PORT = 7890
BASE_DIR = Path(__file__).parent.resolve()

# Global client and bot process references
mcp_client: Optional[PegasusMCPClient] = None
cached_tools: Optional[list] = None
cached_ships: Optional[list] = None
bot_process: Optional[subprocess.Popen] = None


def get_bot_status() -> Dict[str, Any]:
    global bot_process
    state_file = BASE_DIR / "bot_state.json"
    saved_state = {}
    if state_file.exists():
        try:
            with open(state_file, "r", encoding="utf-8") as f:
                saved_state = json.load(f)
        except Exception:
            pass

    is_running = False
    pid = None
    if bot_process and bot_process.poll() is None:
        is_running = True
        pid = bot_process.pid
    elif "pid" in saved_state and saved_state.get("status") == "RUNNING":
        saved_pid = saved_state["pid"]
        try:
            os.kill(saved_pid, 0)
            is_running = True
            pid = saved_pid
        except (OSError, ProcessLookupError):
            is_running = False

    return {
        "running": is_running,
        "pid": pid,
        "state": saved_state,
    }


def start_bot_process() -> Dict[str, Any]:
    global bot_process
    status = get_bot_status()
    if status["running"]:
        return {"success": True, "alreadyRunning": True, "pid": status["pid"]}

    script_path = BASE_DIR / "peg_bot.py"
    if sys.platform == "win32":
        bot_process = subprocess.Popen(
            [sys.executable, str(script_path)],
            cwd=str(BASE_DIR),
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
        )
    else:
        bot_process = subprocess.Popen(
            [sys.executable, str(script_path)],
            cwd=str(BASE_DIR),
            start_new_session=True
        )

    return {"success": True, "pid": bot_process.pid}


def stop_bot_process() -> Dict[str, Any]:
    global bot_process
    status = get_bot_status()
    if not status["running"]:
        return {"success": True, "alreadyStopped": True}

    pid = status["pid"]
    if bot_process and bot_process.poll() is None:
        bot_process.terminate()
        try:
            bot_process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            bot_process.kill()
        bot_process = None

    if pid:
        try:
            os.kill(pid, signal.SIGTERM)
        except (OSError, ProcessLookupError):
            pass

    state_file = BASE_DIR / "bot_state.json"
    if state_file.exists():
        try:
            with open(state_file, "r+", encoding="utf-8") as f:
                d = json.load(f)
                d["status"] = "STOPPED"
                f.seek(0)
                json.dump(d, f, indent=2)
                f.truncate()
        except Exception:
            pass

    return {"success": True}


def step_bot_once() -> Dict[str, Any]:
    script_path = BASE_DIR / "peg_bot.py"
    res = subprocess.run(
        [sys.executable, str(script_path), "--once"],
        cwd=str(BASE_DIR),
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=45
    )
    return {
        "success": res.returncode == 0,
        "stdout": res.stdout,
        "stderr": res.stderr
    }


def reset_bot_state_and_logs() -> Dict[str, Any]:
    stop_bot_process()
    state_file = BASE_DIR / "bot_state.json"
    if state_file.exists():
        try:
            state_file.unlink()
        except Exception:
            pass
    log_file = BASE_DIR / "bot.log"
    try:
        with open(log_file, "w", encoding="utf-8") as f:
            now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            f.write(f"[{now_str}] Bot state and logs reset by user.\n")
    except Exception:
        pass
    return {"success": True}



def get_bot_logs(max_lines: int = 100) -> str:
    log_file = BASE_DIR / "bot.log"
    if not log_file.exists():
        return "No log file found yet. Start the bot or run a test step to generate logs."
    try:
        with open(log_file, "r", encoding="utf-8") as f:
            lines = f.readlines()
            return "".join(lines[-max_lines:])
    except Exception as e:
        return f"Error reading logs: {e}"


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    """Handle requests in separate threads for snappy UI."""
    daemon_threads = True


class PegasusHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Silence routine 200 GET logs to keep console clean
        if "GET /api/" in format % args or "GET / HTTP" in format % args:
            return
        super().log_message(format, *args)

    def _send_json(self, data: Any, status: int = 200):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()

    def do_GET(self):
        global mcp_client, cached_tools, cached_ships

        url_path = self.path.split("?")[0]

        if url_path == "/" or url_path == "/index.html":
            body = HTML_CONTENT.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if url_path == "/api/state":
            try:
                summary = mcp_client.get_game_state_summary()
                planet = mcp_client.get_planet_status()
                tick = mcp_client.get_tick_info()
                rank = mcp_client.get_player_rank()
                self._send_json({
                    "success": True,
                    "summary": summary,
                    "planet": planet,
                    "tick": tick,
                    "rank": rank,
                })
            except Exception as e:
                self._send_json({"success": False, "error": str(e)}, status=500)
            return

        if url_path == "/api/tools":
            try:
                if not cached_tools:
                    cached_tools = mcp_client.list_tools()
                self._send_json({"success": True, "tools": cached_tools})
            except Exception as e:
                self._send_json({"success": False, "error": str(e)}, status=500)
            return

        if url_path == "/api/missions":
            try:
                missions = mcp_client.list_missions()
                self._send_json(missions)
            except Exception as e:
                self._send_json({"success": False, "error": str(e)}, status=500)
            return

        if url_path == "/api/ships":
            try:
                if not cached_ships:
                    cached_ships = mcp_client.read_resource("pegasus://ship/definitions")
                self._send_json({"success": True, "ships": cached_ships})
            except Exception as e:
                self._send_json({"success": False, "error": str(e)}, status=500)
            return

        if url_path == "/api/pds":
            try:
                constructions = mcp_client.read_resource("pegasus://construction/definitions")
                defence_defs = [c for c in constructions if c.get("category") in ("Defence", "DEFENSE", "Defense")]
                pds_live = mcp_client.call_tool("list_pds")
                live_list = pds_live.get("data", []) if isinstance(pds_live, dict) else []
                live_map = {item.get("constructionId"): item for item in live_list if isinstance(item, dict)}

                merged = []
                for d in defence_defs:
                    entry = dict(d)
                    entry["playerStatus"] = live_map.get(d.get("id"))
                    merged.append(entry)
                self._send_json({"success": True, "pds": merged})
            except Exception as e:
                self._send_json({"success": False, "error": str(e)}, status=500)
            return

        if url_path == "/api/resources":
            try:
                res = mcp_client.list_resources()
                self._send_json({"success": True, "resources": res})
            except Exception as e:
                self._send_json({"success": False, "error": str(e)}, status=500)
            return

        if url_path == "/api/memory":
            try:
                keys = mcp_client.list_memory_keys()
                self._send_json(keys)
            except Exception as e:
                self._send_json({"success": False, "error": str(e)}, status=500)
            return

        # Bot Engine Endpoints (GET)
        if url_path == "/api/bot/status":
            self._send_json({"success": True, **get_bot_status()})
            return

        if url_path == "/api/bot/config":
            cfg_file = BASE_DIR / "bot_config.json"
            cfg = {}
            if cfg_file.exists():
                with open(cfg_file, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
            self._send_json({"success": True, "config": cfg})
            return

        if url_path == "/api/bot/strategy":
            strat_file = BASE_DIR / "bot_strategy.py"
            code = ""
            if strat_file.exists():
                with open(strat_file, "r", encoding="utf-8") as f:
                    code = f.read()
            self._send_json({"success": True, "code": code})
            return

        if url_path == "/api/bot/logs":
            self._send_json({"success": True, "logs": get_bot_logs()})
            return

        if url_path == "/api/bot/queue":
            cfg_file = BASE_DIR / "bot_config.json"
            cfg = {}
            if cfg_file.exists():
                try:
                    with open(cfg_file, "r", encoding="utf-8") as f:
                        cfg = json.load(f)
                except Exception:
                    pass
            self._send_json({"success": True, "queue": cfg.get("queued_actions", [])})
            return

        if url_path == "/api/bot/schedules":
            cfg_file = BASE_DIR / "bot_config.json"
            cfg = {}
            if cfg_file.exists():
                try:
                    with open(cfg_file, "r", encoding="utf-8") as f:
                        cfg = json.load(f)
                except Exception:
                    pass
            self._send_json({"success": True, "schedules": cfg.get("scheduled_tasks", [])})
            return

        if url_path == "/api/bot/profiles":
            profiles_dir = BASE_DIR / "config_profiles"
            profiles_dir.mkdir(exist_ok=True)
            profiles = [f.stem for f in sorted(profiles_dir.glob("*.json"))]
            cfg_file = BASE_DIR / "bot_config.json"
            active_profile = "Custom"
            if cfg_file.exists():
                try:
                    with open(cfg_file, "r", encoding="utf-8") as fp:
                        active_profile = json.load(fp).get("profile_name", "Custom")
                except Exception:
                    pass
            self._send_json({
                "success": True,
                "profiles": profiles,
                "active_profile": active_profile,
                "active_path": str(cfg_file),
                "profiles_dir": str(profiles_dir),
            })
            return

        if url_path == "/api/bot/strategies_list":
            strat_dir = BASE_DIR / "custom_strategies"
            strat_dir.mkdir(exist_ok=True)
            strategies = [f.name for f in sorted(strat_dir.glob("*.py"))]
            strat_file = BASE_DIR / "bot_strategy.py"
            self._send_json({
                "success": True,
                "strategies": strategies,
                "active_path": str(strat_file),
                "strategies_dir": str(strat_dir),
            })
            return

        self.send_error(404, "Endpoint not found")

    def do_POST(self):
        global mcp_client
        url_path = self.path.split("?")[0]

        content_len = int(self.headers.get("Content-Length", 0))
        post_body = self.rfile.read(content_len).decode("utf-8") if content_len > 0 else "{}"
        try:
            payload = json.loads(post_body)
        except json.JSONDecodeError:
            self._send_json({"success": False, "error": "Invalid JSON in request body"}, status=400)
            return

        if url_path == "/api/call":
            tool_name = payload.get("tool")
            args = payload.get("arguments", {})
            if not tool_name:
                self._send_json({"success": False, "error": "Missing 'tool' parameter"}, status=400)
                return

            try:
                result = mcp_client.call_tool(tool_name, args)
                self._send_json({"success": True, "result": result})
            except PegasusMCPError as e:
                self._send_json({"success": False, "error": str(e), "code": e.code, "data": e.data}, status=400)
            except Exception as e:
                self._send_json({"success": False, "error": str(e)}, status=500)
            return

        if url_path == "/api/read_resource":
            uri = payload.get("uri")
            if not uri:
                self._send_json({"success": False, "error": "Missing 'uri' parameter"}, status=400)
                return
            try:
                content = mcp_client.read_resource(uri)
                self._send_json({"success": True, "content": content})
            except Exception as e:
                self._send_json({"success": False, "error": str(e)}, status=500)
            return

        # Bot Engine Endpoints (POST)
        if url_path == "/api/bot/start":
            self._send_json(start_bot_process())
            return

        if url_path == "/api/bot/stop":
            self._send_json(stop_bot_process())
            return

        if url_path == "/api/bot/step":
            self._send_json(step_bot_once())
            return

        if url_path == "/api/bot/config":
            cfg = payload.get("config", {})
            cfg_file = BASE_DIR / "bot_config.json"
            existing_cfg = {}
            if cfg_file.exists():
                try:
                    with open(cfg_file, "r", encoding="utf-8") as f:
                        existing_cfg = json.load(f)
                except Exception:
                    pass
            if "queued_actions" not in cfg:
                cfg["queued_actions"] = existing_cfg.get("queued_actions", [])
            if "scheduled_tasks" not in cfg:
                cfg["scheduled_tasks"] = existing_cfg.get("scheduled_tasks", [])
            with open(cfg_file, "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=2)
            self._send_json({"success": True, "config": cfg})
            return

        if url_path == "/api/bot/strategy":
            code = payload.get("code", "")
            strat_file = BASE_DIR / "bot_strategy.py"
            with open(strat_file, "w", encoding="utf-8") as f:
                f.write(code)
            self._send_json({"success": True})
            return

        if url_path == "/api/bot/reset":
            self._send_json(reset_bot_state_and_logs())
            return

        if url_path == "/api/bot/queue_action":
            tool_name = payload.get("tool")
            args = payload.get("arguments", {})
            cfg_file = BASE_DIR / "bot_config.json"
            cfg = {}
            if cfg_file.exists():
                try:
                    with open(cfg_file, "r", encoding="utf-8") as f:
                        cfg = json.load(f)
                except Exception:
                    pass
            q = cfg.get("queued_actions", [])
            q.append({
                "tool": tool_name,
                "arguments": args,
                "queued_at": datetime.datetime.now().strftime("%H:%M:%S")
            })
            cfg["queued_actions"] = q
            with open(cfg_file, "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=2)
            self._send_json({"success": True, "queue": q})
            return

        if url_path == "/api/bot/queue_clear":
            cfg_file = BASE_DIR / "bot_config.json"
            cfg = {}
            if cfg_file.exists():
                try:
                    with open(cfg_file, "r", encoding="utf-8") as f:
                        cfg = json.load(f)
                except Exception:
                    pass
            cfg["queued_actions"] = []
            with open(cfg_file, "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=2)
            self._send_json({"success": True, "queue": []})
            return

        if url_path == "/api/bot/schedule_task":
            task = payload.get("task", {})
            cfg_file = BASE_DIR / "bot_config.json"
            cfg = {}
            if cfg_file.exists():
                try:
                    with open(cfg_file, "r", encoding="utf-8") as f:
                        cfg = json.load(f)
                except Exception:
                    pass
            scheds = cfg.get("scheduled_tasks", [])
            existing_idx = next((i for i, t in enumerate(scheds) if t.get("id") == task.get("id")), None)
            if existing_idx is not None:
                scheds[existing_idx] = task
            else:
                scheds.append(task)
            cfg["scheduled_tasks"] = scheds
            with open(cfg_file, "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=2)
            self._send_json({"success": True, "schedules": scheds})
            return

        if url_path == "/api/bot/schedule_delete":
            task_id = payload.get("id")
            cfg_file = BASE_DIR / "bot_config.json"
            cfg = {}
            if cfg_file.exists():
                try:
                    with open(cfg_file, "r", encoding="utf-8") as f:
                        cfg = json.load(f)
                except Exception:
                    pass
            scheds = [t for t in cfg.get("scheduled_tasks", []) if t.get("id") != task_id]
            cfg["scheduled_tasks"] = scheds
            with open(cfg_file, "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=2)
            self._send_json({"success": True, "schedules": scheds})
            return

        if url_path == "/api/bot/schedule_toggle":
            task_id = payload.get("id")
            cfg_file = BASE_DIR / "bot_config.json"
            cfg = {}
            if cfg_file.exists():
                try:
                    with open(cfg_file, "r", encoding="utf-8") as f:
                        cfg = json.load(f)
                except Exception:
                    pass
            scheds = cfg.get("scheduled_tasks", [])
            for t in scheds:
                if t.get("id") == task_id:
                    t["enabled"] = not t.get("enabled", True)
                    break
            cfg["scheduled_tasks"] = scheds
            with open(cfg_file, "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=2)
            self._send_json({"success": True, "schedules": scheds})
            return

        if url_path == "/api/bot/profile_save":
            name = payload.get("name", "").strip() or "Custom Profile"
            cfg = payload.get("config", {})
            cfg["profile_name"] = name
            profiles_dir = BASE_DIR / "config_profiles"
            profiles_dir.mkdir(exist_ok=True)
            profile_file = profiles_dir / f"{name}.json"
            with open(profile_file, "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=2)

            cfg_file = BASE_DIR / "bot_config.json"
            existing_cfg = {}
            if cfg_file.exists():
                try:
                    with open(cfg_file, "r", encoding="utf-8") as f:
                        existing_cfg = json.load(f)
                except Exception:
                    pass
            active_cfg = dict(cfg)
            active_cfg["queued_actions"] = existing_cfg.get("queued_actions", [])
            active_cfg["scheduled_tasks"] = existing_cfg.get("scheduled_tasks", [])
            with open(cfg_file, "w", encoding="utf-8") as f:
                json.dump(active_cfg, f, indent=2)
            self._send_json({
                "success": True,
                "name": name,
                "saved_file": str(profile_file),
                "active_file": str(cfg_file),
            })
            return

        if url_path == "/api/bot/profile_load":
            name = payload.get("name", "").strip()
            profile_file = BASE_DIR / "config_profiles" / f"{name}.json"
            if not profile_file.exists():
                self._send_json({"success": False, "error": f"Profile '{name}' not found"}, status=404)
                return
            with open(profile_file, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            cfg["profile_name"] = name
            cfg_file = BASE_DIR / "bot_config.json"
            existing_cfg = {}
            if cfg_file.exists():
                try:
                    with open(cfg_file, "r", encoding="utf-8") as f:
                        existing_cfg = json.load(f)
                except Exception:
                    pass
            cfg["queued_actions"] = existing_cfg.get("queued_actions", [])
            cfg["scheduled_tasks"] = existing_cfg.get("scheduled_tasks", [])
            with open(cfg_file, "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=2)
            self._send_json({
                "success": True,
                "name": name,
                "config": cfg,
                "saved_file": str(profile_file),
                "active_file": str(cfg_file),
            })
            return

        if url_path == "/api/bot/profile_delete":
            name = payload.get("name", "").strip()
            profile_file = BASE_DIR / "config_profiles" / f"{name}.json"
            if profile_file.exists():
                profile_file.unlink()
            self._send_json({"success": True})
            return

        if url_path == "/api/bot/strategy_save":
            name = payload.get("name", "").strip() or "my_strategy"
            if not name.endswith(".py"):
                name += ".py"
            code = payload.get("code", "")
            set_active = payload.get("set_active", True)
            strat_dir = BASE_DIR / "custom_strategies"
            strat_dir.mkdir(exist_ok=True)
            script_file = strat_dir / name
            with open(script_file, "w", encoding="utf-8") as f:
                f.write(code)
            active_path = None
            if set_active:
                strat_file = BASE_DIR / "bot_strategy.py"
                with open(strat_file, "w", encoding="utf-8") as f:
                    f.write(code)
                active_path = str(strat_file)
            self._send_json({
                "success": True,
                "name": name,
                "saved_file": str(script_file),
                "active_file": active_path,
            })
            return

        if url_path == "/api/bot/strategy_load":
            name = payload.get("name", "").strip()
            if not name.endswith(".py"):
                name += ".py"
            script_file = BASE_DIR / "custom_strategies" / name
            if not script_file.exists():
                self._send_json({"success": False, "error": f"Script '{name}' not found"}, status=404)
                return
            with open(script_file, "r", encoding="utf-8") as f:
                code = f.read()
            self._send_json({
                "success": True,
                "name": name,
                "code": code,
                "file_path": str(script_file),
            })
            return

        if url_path == "/api/bot/strategy_delete":
            name = payload.get("name", "").strip()
            if not name.endswith(".py"):
                name += ".py"
            script_file = BASE_DIR / "custom_strategies" / name
            if script_file.exists():
                script_file.unlink()
            self._send_json({"success": True})
            return

        self.send_error(404, "Endpoint not found")


HTML_CONTENT = r"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Pegasus Galaxy • MCP Control Hub</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Orbitron:wght@400;600;800;900&family=Rajdhani:wght@500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
  <style>
    :root {
      --bg-space: #050b14;
      --bg-panel: rgba(10, 20, 36, 0.75);
      --bg-panel-hover: rgba(16, 32, 58, 0.85);
      --bg-card: rgba(15, 28, 48, 0.6);
      --border-glow: rgba(0, 229, 255, 0.25);
      --border-accent: rgba(77, 157, 224, 0.3);
      --cyan: #00e5ff;
      --cyan-dim: rgba(0, 229, 255, 0.15);
      --blue: #4d9de0;
      --purple: #a855f7;
      --yellow: #f59e0b;
      --green: #10b981;
      --red: #ef4444;
      --text-main: #e2e8f0;
      --text-dim: #94a3b8;
      --text-bright: #ffffff;
      --font-display: 'Orbitron', sans-serif;
      --font-body: 'Rajdhani', sans-serif;
      --font-mono: 'JetBrains Mono', monospace;
    }

    * { box-sizing: border-box; margin: 0; padding: 0; }

    body {
      background-color: var(--bg-space);
      background-image: 
        radial-gradient(circle at 15% 20%, rgba(0, 229, 255, 0.08) 0%, transparent 40%),
        radial-gradient(circle at 85% 80%, rgba(168, 85, 247, 0.08) 0%, transparent 40%),
        linear-gradient(rgba(5, 11, 20, 0.85), rgba(5, 11, 20, 0.95));
      color: var(--text-main);
      font-family: var(--font-body);
      font-size: 16px;
      line-height: 1.5;
      min-height: 100vh;
      overflow-x: hidden;
    }

    /* Grid overlay effect */
    body::before {
      content: '';
      position: fixed;
      top: 0; left: 0; width: 100%; height: 100%;
      background-image: linear-gradient(rgba(255,255,255,0.02) 1px, transparent 1px),
                        linear-gradient(90deg, rgba(255,255,255,0.02) 1px, transparent 1px);
      background-size: 40px 40px;
      pointer-events: none;
      z-index: 0;
    }

    .container {
      max-width: 1440px;
      margin: 0 auto;
      padding: 1.5rem 2rem;
      position: relative;
      z-index: 1;
    }

    /* Top Navigation Header */
    header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 1rem 1.5rem;
      background: var(--bg-panel);
      backdrop-filter: blur(12px);
      border: 1px solid var(--border-glow);
      border-radius: 12px;
      margin-bottom: 1.5rem;
      box-shadow: 0 8px 32px rgba(0,0,0,0.5), inset 0 0 16px var(--cyan-dim);
    }

    .brand {
      display: flex;
      align-items: center;
      gap: 1rem;
    }

    .logo-icon {
      font-size: 2rem;
      filter: drop-shadow(0 0 10px var(--cyan));
      animation: pulse 4s infinite ease-in-out;
    }

    @keyframes pulse {
      0%, 100% { transform: scale(1); filter: drop-shadow(0 0 10px var(--cyan)); }
      50% { transform: scale(1.05); filter: drop-shadow(0 0 18px var(--cyan)); }
    }

    .brand h1 {
      font-family: var(--font-display);
      font-size: 1.4rem;
      font-weight: 900;
      letter-spacing: 0.15em;
      color: var(--text-bright);
      text-transform: uppercase;
      text-shadow: 0 0 12px rgba(0, 229, 255, 0.4);
    }

    .brand .subtitle {
      font-family: var(--font-mono);
      font-size: 0.75rem;
      color: var(--cyan);
      letter-spacing: 0.1em;
    }

    .header-status {
      display: flex;
      align-items: center;
      gap: 1.5rem;
    }

    .tick-badge {
      display: flex;
      align-items: center;
      gap: 0.6rem;
      padding: 0.5rem 1rem;
      background: rgba(0, 229, 255, 0.1);
      border: 1px solid var(--cyan);
      border-radius: 8px;
      font-family: var(--font-mono);
      font-size: 0.85rem;
    }

    .tick-badge .pulse-dot {
      width: 8px; height: 8px;
      background: var(--cyan);
      border-radius: 50%;
      box-shadow: 0 0 8px var(--cyan);
      animation: blink 1.5s infinite;
    }

    @keyframes blink {
      0%, 100% { opacity: 1; }
      50% { opacity: 0.3; }
    }

    .btn-refresh {
      background: linear-gradient(135deg, rgba(0,229,255,0.2), rgba(77,157,224,0.2));
      border: 1px solid var(--cyan);
      color: var(--cyan);
      padding: 0.5rem 1.2rem;
      border-radius: 8px;
      font-family: var(--font-mono);
      font-weight: 600;
      cursor: pointer;
      display: flex;
      align-items: center;
      gap: 0.5rem;
      transition: all 0.2s;
    }

    .btn-refresh:hover {
      background: var(--cyan);
      color: var(--bg-space);
      box-shadow: 0 0 16px var(--cyan);
      transform: translateY(-1px);
    }

    /* Main Navigation Tabs */
    .tabs {
      display: flex;
      gap: 0.75rem;
      margin-bottom: 1.5rem;
      border-bottom: 1px solid var(--border-accent);
      padding-bottom: 0.5rem;
    }

    .tab-btn {
      font-family: var(--font-display);
      font-size: 0.95rem;
      letter-spacing: 0.05em;
      padding: 0.65rem 1.4rem;
      background: transparent;
      border: 1px solid transparent;
      border-radius: 8px 8px 0 0;
      color: var(--text-dim);
      cursor: pointer;
      transition: all 0.2s;
      display: flex;
      align-items: center;
      gap: 0.5rem;
    }

    .tab-btn:hover {
      color: var(--cyan);
      background: rgba(0, 229, 255, 0.05);
    }

    .tab-btn.active {
      color: var(--cyan);
      border-color: var(--border-glow);
      border-bottom-color: transparent;
      background: var(--bg-panel);
      box-shadow: inset 0 2px 0 var(--cyan);
    }

    .tab-content { display: none; }
    .tab-content.active { display: block; }

    /* Cards & Panels */
    .grid-dashboard {
      display: grid;
      grid-template-columns: repeat(12, 1fr);
      gap: 1.25rem;
    }

    .panel {
      background: var(--bg-panel);
      backdrop-filter: blur(12px);
      border: 1px solid var(--border-accent);
      border-radius: 12px;
      padding: 1.25rem;
      box-shadow: 0 4px 20px rgba(0,0,0,0.3);
      position: relative;
    }

    .panel-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 1rem;
      border-bottom: 1px solid rgba(255,255,255,0.08);
      padding-bottom: 0.6rem;
    }

    .panel-title {
      font-family: var(--font-display);
      font-size: 1.05rem;
      font-weight: 700;
      letter-spacing: 0.08em;
      color: var(--text-bright);
      display: flex;
      align-items: center;
      gap: 0.5rem;
    }

    /* Overview Stat Banner */
    .colony-banner {
      grid-column: span 12;
      display: grid;
      grid-template-columns: repeat(6, 1fr);
      gap: 1rem;
      background: linear-gradient(135deg, rgba(16, 32, 58, 0.8), rgba(10, 20, 36, 0.9));
      border: 1px solid var(--border-glow);
      border-radius: 12px;
      padding: 1.25rem;
    }

    .stat-item {
      text-align: center;
      padding: 0.5rem;
      border-right: 1px solid rgba(255,255,255,0.06);
    }
    .stat-item:last-child { border-right: none; }

    .stat-label {
      font-family: var(--font-mono);
      font-size: 0.75rem;
      color: var(--text-dim);
      text-transform: uppercase;
      letter-spacing: 0.05em;
      margin-bottom: 0.25rem;
    }

    .stat-value {
      font-family: var(--font-display);
      font-size: 1.35rem;
      font-weight: 700;
      color: var(--text-bright);
    }

    /* Resources Row */
    .resources-panel {
      grid-column: span 4;
    }

    .res-row {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 0.75rem 0.5rem;
      border-bottom: 1px solid rgba(255,255,255,0.05);
    }
    .res-row:last-child { border-bottom: none; }

    .res-name {
      display: flex;
      align-items: center;
      gap: 0.6rem;
      font-weight: 600;
    }

    .res-val {
      font-family: var(--font-mono);
      font-size: 1.15rem;
      font-weight: 700;
    }

    /* Population Panel */
    .population-panel {
      grid-column: span 4;
    }

    .pop-bar-group {
      margin-bottom: 0.7rem;
    }

    .pop-bar-header {
      display: flex;
      justify-content: space-between;
      font-size: 0.85rem;
      margin-bottom: 0.2rem;
      font-family: var(--font-mono);
    }

    .progress-track {
      height: 8px;
      background: rgba(255,255,255,0.08);
      border-radius: 4px;
      overflow: hidden;
    }

    .progress-fill {
      height: 100%;
      border-radius: 4px;
      transition: width 0.4s ease;
    }

    /* Development Queues Panel */
    .dev-panel {
      grid-column: span 4;
    }

    .dev-card {
      background: rgba(255,255,255,0.03);
      border: 1px solid rgba(255,255,255,0.06);
      border-radius: 8px;
      padding: 0.85rem;
      margin-bottom: 0.75rem;
    }

    .dev-card-title {
      font-family: var(--font-display);
      font-size: 0.95rem;
      font-weight: 700;
      margin-bottom: 0.4rem;
      display: flex;
      justify-content: space-between;
    }

    /* Fleet Command Panel */
    .fleets-panel {
      grid-column: span 8;
    }

    .fleet-table {
      width: 100%;
      border-collapse: collapse;
      font-family: var(--font-mono);
      font-size: 0.85rem;
    }

    .fleet-table th, .fleet-table td {
      padding: 0.65rem 0.85rem;
      text-align: left;
      border-bottom: 1px solid rgba(255,255,255,0.06);
    }

    .fleet-table th {
      color: var(--text-dim);
      font-size: 0.75rem;
      text-transform: uppercase;
    }

    .badge {
      display: inline-block;
      padding: 0.2rem 0.5rem;
      border-radius: 4px;
      font-size: 0.75rem;
      font-weight: 700;
      text-transform: uppercase;
      font-family: var(--font-mono);
    }

    .badge-read { background: rgba(16, 185, 129, 0.15); color: var(--green); border: 1px solid var(--green); }
    .badge-action { background: rgba(239, 68, 68, 0.15); color: var(--red); border: 1px solid var(--red); }
    .badge-quota { background: rgba(245, 158, 11, 0.15); color: var(--yellow); border: 1px solid var(--yellow); }
    .badge-info { background: rgba(0, 229, 255, 0.15); color: var(--cyan); border: 1px solid var(--cyan); }

    /* Action Quota Panel */
    .quota-panel {
      grid-column: span 4;
    }

    .quota-item {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 0.6rem 0.4rem;
      border-bottom: 1px solid rgba(255,255,255,0.05);
      font-family: var(--font-mono);
      font-size: 0.85rem;
    }

    /* Command Hub Tab */
    .command-hub-grid {
      display: grid;
      grid-template-columns: 360px 1fr;
      gap: 1.5rem;
    }

    .tool-sidebar {
      background: var(--bg-panel);
      border: 1px solid var(--border-accent);
      border-radius: 12px;
      padding: 1rem;
      height: 720px;
      display: flex;
      flex-direction: column;
    }

    .search-input {
      width: 100%;
      padding: 0.65rem 1rem;
      background: rgba(255,255,255,0.05);
      border: 1px solid rgba(255,255,255,0.1);
      border-radius: 8px;
      color: var(--text-bright);
      font-family: var(--font-mono);
      font-size: 0.85rem;
      margin-bottom: 0.75rem;
    }
    .search-input:focus { outline: none; border-color: var(--cyan); box-shadow: 0 0 8px var(--cyan-dim); }

    .category-filter {
      display: flex;
      flex-wrap: wrap;
      gap: 0.35rem;
      margin-bottom: 0.75rem;
    }

    .cat-pill {
      font-size: 0.7rem;
      font-family: var(--font-mono);
      padding: 0.2rem 0.5rem;
      background: rgba(255,255,255,0.05);
      border: 1px solid rgba(255,255,255,0.1);
      border-radius: 4px;
      cursor: pointer;
      color: var(--text-dim);
    }
    .cat-pill.active, .cat-pill:hover {
      background: rgba(0,229,255,0.15);
      border-color: var(--cyan);
      color: var(--cyan);
    }

    .tool-list {
      flex: 1;
      overflow-y: auto;
      display: flex;
      flex-direction: column;
      gap: 0.4rem;
      padding-right: 0.25rem;
    }

    .tool-item {
      padding: 0.6rem 0.8rem;
      background: rgba(255,255,255,0.02);
      border: 1px solid transparent;
      border-radius: 6px;
      cursor: pointer;
      display: flex;
      justify-content: space-between;
      align-items: center;
      transition: all 0.15s;
    }
    .tool-item:hover {
      background: rgba(0, 229, 255, 0.06);
      border-color: var(--border-glow);
    }
    .tool-item.selected {
      background: rgba(0, 229, 255, 0.12);
      border-color: var(--cyan);
      box-shadow: inset 2px 0 0 var(--cyan);
    }

    .tool-item-name {
      font-family: var(--font-mono);
      font-size: 0.82rem;
      font-weight: 600;
      color: var(--text-bright);
    }

    /* Tool Runner Workspace */
    .tool-workspace {
      display: flex;
      flex-direction: column;
      gap: 1.25rem;
    }

    .form-group {
      margin-bottom: 0.9rem;
    }

    .form-label {
      display: block;
      font-family: var(--font-mono);
      font-size: 0.8rem;
      color: var(--text-dim);
      margin-bottom: 0.35rem;
    }

    .form-control {
      width: 100%;
      padding: 0.6rem 0.85rem;
      background: rgba(255,255,255,0.04);
      border: 1px solid rgba(255,255,255,0.12);
      border-radius: 6px;
      color: var(--text-bright);
      font-family: var(--font-mono);
      font-size: 0.85rem;
    }
    .form-control:focus { outline: none; border-color: var(--cyan); }
    select.form-control, select.form-control option {
      background-color: #0d1a2d !important;
      color: #e2e8f0 !important;
    }
    select.form-control optgroup {
      background-color: #08111e !important;
      color: var(--cyan) !important;
    }

    .btn-primary {
      background: linear-gradient(135deg, var(--cyan), var(--blue));
      color: #050b14;
      font-family: var(--font-display);
      font-size: 0.9rem;
      font-weight: 800;
      letter-spacing: 0.08em;
      border: none;
      border-radius: 8px;
      padding: 0.75rem 1.6rem;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      gap: 0.5rem;
      transition: all 0.2s;
    }
    .btn-primary:hover {
      box-shadow: 0 0 20px var(--cyan);
      transform: translateY(-2px);
    }

    .result-box {
      background: #030712;
      border: 1px solid rgba(255,255,255,0.1);
      border-radius: 8px;
      padding: 1rem;
      font-family: var(--font-mono);
      font-size: 0.85rem;
      color: #38bdf8;
      max-height: 380px;
      overflow-y: auto;
      white-space: pre-wrap;
      word-break: break-all;
    }

    /* Shipyard Codex Cards */
    .ships-grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
      gap: 1.25rem;
    }

    /* Shipyard & Hangar Codex */
    .codex-controls {
      background: var(--bg-panel);
      border: 1px solid var(--border-accent);
      border-radius: 12px;
      padding: 1rem 1.25rem;
      margin-bottom: 1.5rem;
      display: flex;
      flex-direction: column;
      gap: 0.75rem;
    }

    .race-columns-container {
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 1.5rem;
      align-items: start;
      margin-bottom: 2.5rem;
    }
    @media (max-width: 1200px) {
      .race-columns-container { grid-template-columns: 1fr; }
    }

    .race-column {
      background: rgba(10, 20, 36, 0.6);
      border: 1px solid var(--border-accent);
      border-radius: 14px;
      padding: 1.25rem;
      display: flex;
      flex-direction: column;
      gap: 1.25rem;
      box-shadow: 0 4px 20px rgba(0,0,0,0.3);
    }
    .race-column.vanguard { border-top: 4px solid var(--blue); }
    .race-column.synthara { border-top: 4px solid var(--purple); }
    .race-column.ashkari { border-top: 4px solid var(--red); }

    .race-col-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding-bottom: 0.75rem;
      border-bottom: 1px solid rgba(255,255,255,0.08);
    }

    .race-col-title {
      font-family: var(--font-display);
      font-size: 1.25rem;
      font-weight: 800;
      letter-spacing: 0.08em;
      display: flex;
      align-items: center;
      gap: 0.5rem;
    }

    .class-section {
      display: flex;
      flex-direction: column;
      gap: 0.85rem;
    }

    .class-section-title {
      font-family: var(--font-display);
      font-size: 0.85rem;
      font-weight: 700;
      color: var(--text-dim);
      text-transform: uppercase;
      letter-spacing: 0.1em;
      padding-left: 0.5rem;
      border-left: 3px solid var(--cyan);
      display: flex;
      justify-content: space-between;
      align-items: center;
    }

    .ship-card {
      background: rgba(15, 28, 48, 0.75);
      border: 1px solid rgba(255,255,255,0.08);
      border-radius: 10px;
      padding: 1rem;
      transition: all 0.2s;
      position: relative;
    }
    .ship-card:hover {
      border-color: var(--cyan);
      transform: translateY(-2px);
      box-shadow: 0 6px 20px rgba(0, 229, 255, 0.12);
    }

    .ship-card-header {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      margin-bottom: 0.6rem;
      border-bottom: 1px solid rgba(255,255,255,0.06);
      padding-bottom: 0.4rem;
    }

    .ship-name {
      font-family: var(--font-display);
      font-size: 1.05rem;
      font-weight: 700;
      color: var(--text-bright);
    }

    .ship-stats-grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 0.4rem 0.6rem;
      font-family: var(--font-mono);
      font-size: 0.78rem;
      margin-bottom: 0.6rem;
    }

    /* PDS Defense Grid */
    .pds-section-title {
      font-family: var(--font-display);
      font-size: 1.3rem;
      font-weight: 800;
      letter-spacing: 0.08em;
      color: var(--text-bright);
      margin-bottom: 1rem;
      display: flex;
      align-items: center;
      gap: 0.6rem;
    }

    .pds-grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(350px, 1fr));
      gap: 1.25rem;
      margin-bottom: 2rem;
    }

    .pds-card {
      background: var(--bg-panel);
      border: 1px solid var(--border-accent);
      border-radius: 12px;
      padding: 1.25rem;
      position: relative;
      transition: all 0.2s;
    }
    .pds-card:hover {
      border-color: var(--cyan);
      transform: translateY(-2px);
      box-shadow: 0 6px 24px rgba(0, 229, 255, 0.15);
    }
    .pds-card.built {
      border-left: 4px solid var(--green);
      background: rgba(16, 185, 129, 0.04);
    }

    .pds-header {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      margin-bottom: 0.6rem;
      border-bottom: 1px solid rgba(255,255,255,0.06);
      padding-bottom: 0.5rem;
    }

    .pds-name {
      font-family: var(--font-display);
      font-size: 1.1rem;
      font-weight: 700;
      color: var(--text-bright);
    }

    .target-badge {
      display: inline-block;
      padding: 0.15rem 0.4rem;
      border-radius: 4px;
      font-size: 0.7rem;
      font-family: var(--font-mono);
      background: rgba(255,255,255,0.05);
      border: 1px solid rgba(255,255,255,0.1);
      margin-right: 0.3rem;
    }

    /* Missions Tab */
    .missions-list {
      display: flex;
      flex-direction: column;
      gap: 0.75rem;
    }

    .mission-card {
      display: flex;
      justify-content: space-between;
      align-items: center;
      background: var(--bg-panel);
      border: 1px solid rgba(255,255,255,0.08);
      border-radius: 10px;
      padding: 1rem 1.25rem;
    }
    .mission-card.completed {
      border-color: var(--green);
      background: rgba(16, 185, 129, 0.08);
    }

    .btn-claim-banner {
      background: linear-gradient(135deg, #10b981, #059669);
      color: white;
      padding: 1rem;
      border-radius: 10px;
      margin-bottom: 1.5rem;
      display: flex;
      justify-content: space-between;
      align-items: center;
      font-weight: 700;
      box-shadow: 0 4px 20px rgba(16, 185, 129, 0.3);
    }

    /* Toast Notification */
    #toast {
      position: fixed;
      bottom: 2rem;
      right: 2rem;
      padding: 0.85rem 1.5rem;
      background: #0f172a;
      border: 1px solid var(--cyan);
      border-radius: 8px;
      color: var(--text-bright);
      font-family: var(--font-mono);
      font-size: 0.85rem;
      box-shadow: 0 8px 30px rgba(0,0,0,0.8);
      transform: translateY(100px);
      opacity: 0;
      transition: all 0.3s;
      z-index: 1000;
    }
    #toast.show {
      transform: translateY(0);
      opacity: 1;
    }
  </style>
</head>
<body>

<div class="container">
  <!-- Header -->
  <header>
    <div class="brand">
      <div class="logo-icon">🪐</div>
      <div>
        <h1>Pegasus Galaxy</h1>
        <div class="subtitle">Autonomous AI Agent & Human Command Hub</div>
      </div>
    </div>
    <div class="header-status">
      <div class="tick-badge">
        <span class="pulse-dot"></span>
        <span>Tick: <strong id="header-tick">---</strong></span>
        <span style="color: var(--cyan);">(In: <span id="header-countdown">---</span>)</span>
      </div>
      <button class="btn-refresh" onclick="refreshDashboard()">
        <span>🔄</span> Refresh Telemetry
      </button>
    </div>
  </header>

  <!-- Navigation Tabs -->
  <div class="tabs">
    <button class="tab-btn active" onclick="switchTab('dashboard')">📊 Mission Control</button>
    <button class="tab-btn" onclick="switchTab('commands')">🛠️ Command Hub (67 Tools)</button>
    <button class="tab-btn" onclick="switchTab('missions')">🎯 Quests & Missions</button>
    <button class="tab-btn" onclick="switchTab('ships')">🚀 Hangar & Ship Codex</button>
    <button class="tab-btn" onclick="switchTab('bot')">🤖 Bot Studio</button>
    <button class="tab-btn" onclick="switchTab('memory')">🧠 Bot Memory</button>
  </div>

  <!-- TAB 1: Mission Control Dashboard -->
  <div id="tab-dashboard" class="tab-content active">
    <div class="grid-dashboard">
      <!-- Colony Stat Banner -->
      <div class="colony-banner">
        <div class="stat-item">
          <div class="stat-label">Colony Name</div>
          <div class="stat-value" id="stat-colony" style="color: var(--cyan);">---</div>
        </div>
        <div class="stat-item">
          <div class="stat-label">Coordinates</div>
          <div class="stat-value" id="stat-coords">---</div>
        </div>
        <div class="stat-item">
          <div class="stat-label">Score</div>
          <div class="stat-value" id="stat-score" style="color: var(--green);">---</div>
        </div>
        <div class="stat-item">
          <div class="stat-label">Galaxy Rank</div>
          <div class="stat-value" id="stat-rank" style="color: var(--yellow);">---</div>
        </div>
        <div class="stat-item">
          <div class="stat-label">Happiness</div>
          <div class="stat-value" id="stat-happiness">---</div>
        </div>
        <div class="stat-item">
          <div class="stat-label">Asteroids</div>
          <div class="stat-value" id="stat-asteroids" style="color: var(--purple);">---</div>
        </div>
      </div>

      <!-- Resources Panel -->
      <div class="panel resources-panel">
        <div class="panel-header">
          <div class="panel-title">📦 Resources</div>
          <span class="badge badge-info">Production Active</span>
        </div>
        <div class="res-row">
          <div class="res-name">🔩 Metal</div>
          <div class="res-val" id="res-metal" style="color: #cbd5e1;">---</div>
        </div>
        <div class="res-row">
          <div class="res-name">💎 Crystal</div>
          <div class="res-val" id="res-crystal" style="color: var(--cyan);">---</div>
        </div>
        <div class="res-row">
          <div class="res-name">⚡ Eonium (Fuel)</div>
          <div class="res-val" id="res-eonium" style="color: var(--yellow);">---</div>
        </div>
        <div class="res-row">
          <div class="res-name">☄️ Asteroid Field</div>
          <div class="res-val" id="res-asteroids" style="color: var(--purple);">---</div>
        </div>
      </div>

      <!-- Population Allocation Panel -->
      <div class="panel population-panel">
        <div class="panel-header">
          <div class="panel-title">👥 Population (<span id="pop-total">0</span>)</div>
          <span class="badge badge-read">100% Employed</span>
        </div>
        <div class="pop-bar-group">
          <div class="pop-bar-header">
            <span>⛏️ Miners</span>
            <span id="pop-miners-val">0</span>
          </div>
          <div class="progress-track">
            <div class="progress-fill" id="pop-miners-bar" style="background: var(--blue); width: 0%;"></div>
          </div>
        </div>
        <div class="pop-bar-group">
          <div class="pop-bar-header">
            <span>🔬 Researchers</span>
            <span id="pop-researchers-val">0</span>
          </div>
          <div class="progress-track">
            <div class="progress-fill" id="pop-researchers-bar" style="background: var(--purple); width: 0%;"></div>
          </div>
        </div>
        <div class="pop-bar-group">
          <div class="pop-bar-header">
            <span>🔨 Builders</span>
            <span id="pop-builders-val">0</span>
          </div>
          <div class="progress-track">
            <div class="progress-fill" id="pop-builders-bar" style="background: var(--yellow); width: 0%;"></div>
          </div>
        </div>
        <div class="pop-bar-group">
          <div class="pop-bar-header">
            <span>🚀 Shipwrights</span>
            <span id="pop-shipwrights-val">0</span>
          </div>
          <div class="progress-track">
            <div class="progress-fill" id="pop-shipwrights-bar" style="background: var(--cyan); width: 0%;"></div>
          </div>
        </div>
      </div>

      <!-- Active Queues Panel -->
      <div class="panel dev-panel">
        <div class="panel-header">
          <div class="panel-title">🏗️ Development Queues</div>
        </div>
        <div class="dev-card">
          <div class="dev-card-title">
            <span id="build-name">🔨 Construction: None</span>
            <span id="build-pct" style="color: var(--yellow);">0%</span>
          </div>
          <div class="progress-track" style="margin-bottom: 0.4rem;">
            <div class="progress-fill" id="build-bar" style="background: var(--yellow); width: 0%;"></div>
          </div>
          <div style="font-family: var(--font-mono); font-size: 0.75rem; color: var(--text-dim);" id="build-pts">
            0 / 0 points
          </div>
        </div>
        <div class="dev-card">
          <div class="dev-card-title">
            <span id="research-name">🔬 Research: None</span>
            <span id="research-pct" style="color: var(--purple);">0%</span>
          </div>
          <div class="progress-track" style="margin-bottom: 0.4rem;">
            <div class="progress-fill" id="research-bar" style="background: var(--purple); width: 0%;"></div>
          </div>
          <div style="font-family: var(--font-mono); font-size: 0.75rem; color: var(--text-dim);" id="research-pts">
            0 / 0 points
          </div>
        </div>
      </div>

      <!-- Fleet Command Panel -->
      <div class="panel fleets-panel">
        <div class="panel-header">
          <div class="panel-title">⚔️ Fleet Command & Defense</div>
        </div>
        <table class="fleet-table">
          <thead>
            <tr>
              <th>Fleet ID / Unit</th>
              <th>Status</th>
              <th>Mission</th>
              <th>Composition</th>
              <th>Arrival Tick</th>
            </tr>
          </thead>
          <tbody id="fleet-rows">
            <tr><td colspan="5" style="text-align: center; color: var(--text-dim);">Loading fleets...</td></tr>
          </tbody>
        </table>
      </div>

      <!-- Action Quotas Panel -->
      <div class="panel quota-panel">
        <div class="panel-header">
          <div class="panel-title">⚡ Agent Action Quotas</div>
          <span class="badge badge-info" id="quota-tick-badge">Tick ---</span>
        </div>
        <div style="margin-bottom: 0.85rem;">
          <div style="display: flex; justify-content: space-between; font-size: 0.85rem; margin-bottom: 0.25rem; font-family: var(--font-mono);">
            <span>Modifying Actions</span>
            <span id="quota-actions-text" style="font-weight: 700; color: var(--yellow);">0 / 10 used</span>
          </div>
          <div class="progress-track">
            <div class="progress-fill" id="quota-actions-bar" style="background: var(--yellow); width: 0%;"></div>
          </div>
        </div>

        <div style="margin-bottom: 0.85rem;">
          <div style="display: flex; justify-content: space-between; font-size: 0.85rem; margin-bottom: 0.25rem; font-family: var(--font-mono);">
            <span>Fleet Launches</span>
            <span id="quota-launches-text" style="font-weight: 700; color: var(--red);">0 / 3 used</span>
          </div>
          <div class="progress-track">
            <div class="progress-fill" id="quota-launches-bar" style="background: var(--red); width: 0%;"></div>
          </div>
        </div>

        <div style="margin-bottom: 0.85rem;">
          <div style="display: flex; justify-content: space-between; font-size: 0.85rem; margin-bottom: 0.25rem; font-family: var(--font-mono);">
            <span>Planet Scans</span>
            <span id="quota-scans-text" style="font-weight: 700; color: var(--cyan);">0 / 2 used</span>
          </div>
          <div class="progress-track">
            <div class="progress-fill" id="quota-scans-bar" style="background: var(--cyan); width: 0%;"></div>
          </div>
        </div>

        <div class="quota-item" style="padding-top: 0.25rem;">
          <span>Telemetry & Queries</span>
          <span class="badge badge-read">UNLIMITED</span>
        </div>
        <div style="margin-top: 0.85rem; display: flex; justify-content: space-between; align-items: center;">
          <span style="font-size: 0.75rem; color: var(--text-dim);">Resets every 30m game tick</span>
          <button class="btn-refresh" style="padding: 0.2rem 0.6rem; font-size: 0.7rem;" onclick="resetQuotaTracker()">Reset Counter</button>
        </div>
      </div>
    </div>
  </div>

  <!-- TAB 2: Interactive Command Hub -->
  <div id="tab-commands" class="tab-content">
    <div class="command-hub-grid">
      <!-- Tool Sidebar -->
      <div class="tool-sidebar">
        <input type="text" id="tool-search" class="search-input" placeholder="Search 67 MCP tools..." oninput="filterTools()">
        <div class="category-filter">
          <span class="cat-pill active" onclick="setCategory('ALL')">All</span>
          <span class="cat-pill" onclick="setCategory('PLANET')">Planet</span>
          <span class="cat-pill" onclick="setCategory('MILITARY')">Military</span>
          <span class="cat-pill" onclick="setCategory('SOCIAL')">Social</span>
          <span class="cat-pill" onclick="setCategory('META')">Meta</span>
          <span class="cat-pill" onclick="setCategory('MEMORY')">Memory</span>
        </div>
        <div class="tool-list" id="tool-list-container">
          <!-- Tools populated dynamically -->
        </div>
      </div>

      <!-- Tool Workspace -->
      <div class="tool-workspace">
        <div class="panel">
          <div class="panel-header">
            <div>
              <div class="panel-title" id="selected-tool-name">Select a Tool</div>
              <div style="font-size: 0.85rem; color: var(--text-dim); margin-top: 0.2rem;" id="selected-tool-desc">
                Choose an MCP command from the left sidebar to inspect parameters and invoke it.
              </div>
            </div>
            <div id="selected-tool-badge"></div>
          </div>

          <!-- Dynamic Form Container -->
          <div id="tool-form-container">
            <p style="color: var(--text-dim); font-style: italic;">No tool selected.</p>
          </div>

          <div style="margin-top: 1.5rem; display: flex; gap: 1rem;">
            <button id="btn-run-tool" class="btn-primary" onclick="executeSelectedTool()">
              <span>⚡</span> Run Command
            </button>
            <button class="btn-refresh" onclick="clearResults()">
              Clear Output
            </button>
          </div>
        </div>

        <!-- Output Result Panel -->
        <div class="panel">
          <div class="panel-header">
            <div class="panel-title">📡 Server Response Output</div>
            <button class="btn-refresh" style="padding: 0.25rem 0.6rem; font-size: 0.75rem;" onclick="copyOutput()">
              Copy JSON
            </button>
          </div>
          <div class="result-box" id="output-box">// Response data will appear here...</div>
        </div>
      </div>
    </div>
  </div>

  <!-- TAB 3: Missions & Quests -->
  <div id="tab-missions" class="tab-content">
    <div id="claim-banner-area"></div>
    <div class="missions-list" id="missions-list-container">
      <div class="panel" style="text-align: center; color: var(--text-dim);">Loading missions...</div>
    </div>
  </div>

  <!-- TAB 4: Hangar & Ship Codex -->
  <div id="tab-ships" class="tab-content">
    <div class="codex-controls">
      <div style="display: flex; gap: 1rem; flex-wrap: wrap; justify-content: space-between; align-items: center;">
        <input type="text" id="codex-search" class="search-input" style="max-width: 420px; margin-bottom: 0;" placeholder="Search ships or defenses (e.g. Centurion, Ion Cannon, Cruiser)..." oninput="renderCodex()">
        <div style="display: flex; gap: 0.4rem; flex-wrap: wrap; align-items: center;">
          <span style="font-family: var(--font-mono); font-size: 0.8rem; color: var(--text-dim); margin-right: 0.25rem;">Faction:</span>
          <span class="cat-pill active" id="f-pill-ALL" onclick="setCodexFaction('ALL')">All</span>
          <span class="cat-pill" id="f-pill-VANGUARD" onclick="setCodexFaction('VANGUARD')">🛡️ Vanguard</span>
          <span class="cat-pill" id="f-pill-SYNTHARA" onclick="setCodexFaction('SYNTHARA')">⚡ Synthara</span>
          <span class="cat-pill" id="f-pill-ASHKARI" onclick="setCodexFaction('ASHKARI')">⚔️ Ashkari</span>
          <span class="cat-pill" id="f-pill-PDS" onclick="setCodexFaction('PDS')">🏰 PDS Defenses</span>
        </div>
        <div style="display: flex; gap: 0.4rem; flex-wrap: wrap; align-items: center;">
          <span style="font-family: var(--font-mono); font-size: 0.8rem; color: var(--text-dim); margin-right: 0.25rem;">Class:</span>
          <span class="cat-pill active" id="c-pill-ALL" onclick="setCodexClass('ALL')">All</span>
          <span class="cat-pill" id="c-pill-LIGHT" onclick="setCodexClass('LIGHT')">Light</span>
          <span class="cat-pill" id="c-pill-MEDIUM" onclick="setCodexClass('MEDIUM')">Medium</span>
          <span class="cat-pill" id="c-pill-HEAVY" onclick="setCodexClass('HEAVY')">Heavy</span>
          <span class="cat-pill" id="c-pill-SPECIAL" onclick="setCodexClass('SPECIAL')">Special</span>
        </div>
      </div>
    </div>

    <!-- Race Columns Container for Ships -->
    <div id="race-columns-wrapper" class="race-columns-container">
      <!-- Vanguard Column -->
      <div class="race-column vanguard" id="col-vanguard">
        <div class="race-col-header">
          <div class="race-col-title" style="color: var(--blue);">🛡️ VANGUARD</div>
          <span class="badge badge-info">Industrial Navy</span>
        </div>
        <div id="vanguard-ships-container" class="class-section"></div>
      </div>

      <!-- Synthara Column -->
      <div class="race-column synthara" id="col-synthara">
        <div class="race-col-header">
          <div class="race-col-title" style="color: var(--purple);">⚡ SYNTHARA</div>
          <span class="badge" style="background: rgba(168, 85, 247, 0.15); color: var(--purple); border: 1px solid var(--purple);">Cybernetic EMP</span>
        </div>
        <div id="synthara-ships-container" class="class-section"></div>
      </div>

      <!-- Ashkari Column -->
      <div class="race-column ashkari" id="col-ashkari">
        <div class="race-col-header">
          <div class="race-col-title" style="color: var(--red);">⚔️ ASHKARI</div>
          <span class="badge badge-action">Swarm Armada</span>
        </div>
        <div id="ashkari-ships-container" class="class-section"></div>
      </div>
    </div>

    <!-- Planetary Defense Structures Section -->
    <div id="pds-section-wrapper">
      <div class="pds-section-title">
        <span>🏰 Planetary Defense Structures (PDS)</span>
        <span class="badge badge-info" style="font-size: 0.75rem;">Colony Defense Grid</span>
      </div>
      <div class="pds-grid" id="pds-grid-container">
        <div class="panel" style="text-align: center; color: var(--text-dim);">Loading planetary defense systems...</div>
      </div>
    </div>
  </div>

  <!-- TAB: Bot Studio -->
  <div id="tab-bot" class="tab-content">
    <!-- Top Control Bar -->
    <div class="panel" style="margin-bottom: 1.5rem;">
      <div class="panel-header">
        <div>
          <div class="panel-title">🤖 Autonomous Bot Process Controller</div>
          <div style="font-size: 0.85rem; color: var(--text-dim); margin-top: 0.2rem;">
            Runs 24/7 on Windows, Linux VPS, or locally. Syncs to the 30-minute game ticks.
          </div>
        </div>
        <div style="display: flex; align-items: center; gap: 1rem;">
          <span id="bot-status-badge" class="badge badge-quota" style="font-size: 0.85rem; padding: 0.4rem 0.8rem;">○ CHECKING STATUS</span>
          <span id="bot-status-desc" style="font-family: var(--font-mono); font-size: 0.8rem; color: var(--text-dim);"></span>
        </div>
      </div>
      <div style="display: flex; gap: 1rem; flex-wrap: wrap; align-items: center;">
        <button id="btn-bot-start" class="btn-primary" style="background: linear-gradient(135deg, #10b981, #059669);" onclick="startBot()">
          <span>▶️</span> Start Bot Process
        </button>
        <button id="btn-bot-stop" class="btn-primary" style="background: linear-gradient(135deg, #ef4444, #b91c1c);" onclick="stopBot()">
          <span>⏹️</span> Stop Bot
        </button>
        <button class="btn-primary" onclick="stepBot()">
          <span>⚡</span> Step 1 Tick Cycle (Test Run)
        </button>
        <button class="btn-refresh" onclick="refreshBotStatus()">
          <span>🔄</span> Sync Status
        </button>
        <button class="btn-primary" style="background: rgba(239, 68, 68, 0.2); border: 1px solid var(--red); color: #f87171;" onclick="resetBotState()">
          <span>🗑️</span> Reset State & Logs
        </button>
      </div>
    </div>

    <!-- VPS Remote Settings & Operations Guide -->
    <div class="panel" style="margin-bottom: 1.5rem; border-color: rgba(168, 85, 247, 0.35); background: rgba(15, 23, 42, 0.75);">
      <div class="panel-header" style="cursor: pointer;" onclick="toggleVpsGuide()">
        <div style="display: flex; align-items: center; gap: 0.6rem;">
          <span style="font-size: 1.25rem;">🌐</span>
          <div>
            <div class="panel-title" style="color: #c084fc;">VPS Remote Settings, Resetting & Operation Modes</div>
            <div style="font-size: 0.8rem; color: var(--text-dim); margin-top: 0.15rem;">Everything you need to know about changing strategies, resetting state, or running 24/7 on a cloud VPS</div>
          </div>
        </div>
        <span id="vps-guide-toggle-icon" style="font-family: var(--font-mono); font-size: 0.85rem; color: var(--purple);">[ Click to Expand ▼ ]</span>
      </div>
      <div id="vps-guide-content" style="display: none; margin-top: 1rem; border-top: 1px solid rgba(255,255,255,0.06); padding-top: 1rem;">
        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 1.25rem; margin-bottom: 1rem;">
          <!-- Option A: Access Web GUI on VPS -->
          <div style="background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.08); border-radius: 8px; padding: 1rem;">
            <div style="font-family: var(--font-display); font-weight: 700; color: var(--cyan); margin-bottom: 0.4rem;">
              Option 1: Access This Exact Web GUI on VPS (Recommended)
            </div>
            <p style="font-size: 0.82rem; color: var(--text-dim); line-height: 1.4; margin-bottom: 0.6rem;">
              If you run <code>peg_gui.py</code> on your VPS, you can open this exact control center from your phone, laptop, or desktop browser. Any edits you make in Bot Studio directly control the VPS bot!
            </p>
            <div style="background: #030712; padding: 0.6rem; border-radius: 6px; font-family: var(--font-mono); font-size: 0.75rem; color: #a5f3fc; line-height: 1.4;">
              # Start GUI accessible remotely on VPS port 7890:<br>
              python peg_gui.py --host 0.0.0.0 --port 7890 --no-browser<br><br>
              # Or run as a permanent 24/7 background service:<br>
              sudo systemctl start pegasus-gui
            </div>
            <div style="font-size: 0.78rem; color: var(--green); margin-top: 0.5rem;">
              Then open <strong>http://YOUR_VPS_IP:7890</strong> in any browser!
            </div>
          </div>

          <!-- Option B: Secure SSH Tunnel -->
          <div style="background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.08); border-radius: 8px; padding: 1rem;">
            <div style="font-family: var(--font-display); font-weight: 700; color: var(--purple); margin-bottom: 0.4rem;">
              Option 2: Encrypted SSH Tunnel (No Open Ports Needed)
            </div>
            <p style="font-size: 0.82rem; color: var(--text-dim); line-height: 1.4; margin-bottom: 0.6rem;">
              Keep port 7890 closed on your VPS firewall for maximum security, and forward it securely to your Windows PC with a single command:
            </p>
            <div style="background: #030712; padding: 0.6rem; border-radius: 6px; font-family: var(--font-mono); font-size: 0.75rem; color: #f0abfc; line-height: 1.4;">
              # Run in Windows PowerShell / Terminal:<br>
              ssh -L 7890:localhost:7890 root@YOUR_VPS_IP
            </div>
            <div style="font-size: 0.78rem; color: var(--text-dim); margin-top: 0.5rem;">
              Then open <strong>http://localhost:7890</strong> on your PC. It connects directly to your VPS!
            </div>
          </div>
        </div>

        <!-- Changing Settings & Resetting on VPS -->
        <div style="background: rgba(255,255,255,0.02); border-radius: 8px; padding: 0.9rem; border-left: 3px solid var(--yellow); font-size: 0.82rem; line-height: 1.5;">
          <strong style="color: var(--yellow);">⚙️ How Resetting and Live Changes Work on VPS:</strong>
          <ul style="margin: 0.4rem 0 0 1.2rem; color: var(--text-dim);">
            <li><strong>Reset State & Logs:</strong> Click the red <span style="color: #f87171;">[Reset State & Logs]</span> button above, or run <code>sudo systemctl restart pegasus-bot &amp;&amp; sudo rm -f /opt/peg-mcp/bot_state.json</code> on the VPS.</li>
            <li><strong>Changing Rules & Priorities:</strong> Adjust the sliders/inputs in the visual configurator and click <em>Save Strategy Config</em>, or edit <code>/opt/peg-mcp/bot_config.json</code> on the VPS.</li>
            <li><strong>Changing Custom Logic:</strong> Edit the Python code in the Strategy Code editor and click <em>Save &amp; Live-Reload</em>. The engine detects file modifications and <strong>automatically re-imports the new strategy on the next tick</strong> without interrupting the bot!</li>
          </ul>
        </div>
      </div>
    </div>

    <!-- Strategy Architecture & Active Status Banner -->
    <div style="background: linear-gradient(135deg, rgba(16, 185, 129, 0.08), rgba(0, 229, 255, 0.08)); border: 1px solid rgba(0, 229, 255, 0.25); border-radius: 10px; padding: 1.1rem 1.25rem; margin-bottom: 1.5rem;">
      <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 0.75rem; margin-bottom: 0.75rem;">
        <div style="display: flex; align-items: center; gap: 0.6rem;">
          <span style="font-size: 1.3rem;">🧠</span>
          <div>
            <div style="font-family: var(--font-display); font-size: 0.95rem; font-weight: 800; color: var(--text-bright); letter-spacing: 0.5px;">
              Active Bot Strategy Architecture
            </div>
            <div style="font-size: 0.78rem; color: var(--text-dim);">
              How the bot makes decisions every tick: <strong>Layer 1 Rules</strong> execute first, followed by your <strong>Layer 2 Python Hook</strong>. Both work together!
            </div>
          </div>
        </div>
        <div style="display: flex; gap: 0.5rem; font-family: var(--font-mono); font-size: 0.75rem;">
          <div style="background: rgba(0, 229, 255, 0.1); border: 1px solid rgba(0, 229, 255, 0.3); border-radius: 6px; padding: 0.35rem 0.65rem; color: #a5f3fc;">
            Active Rules: <strong id="banner-active-profile" style="color: #fff;">Default Economy</strong>
          </div>
          <div style="background: rgba(16, 185, 129, 0.1); border: 1px solid rgba(16, 185, 129, 0.3); border-radius: 6px; padding: 0.35rem 0.65rem; color: #86efac;">
            Active Script: <strong id="banner-active-script" style="color: #fff;">bot_strategy.py</strong>
          </div>
        </div>
      </div>

      <!-- Flow Pipeline -->
      <div style="display: grid; grid-template-columns: 1fr auto 1fr; gap: 0.75rem; align-items: center; background: rgba(0,0,0,0.3); border-radius: 8px; padding: 0.75rem 1rem;">
        <div style="font-size: 0.8rem; line-height: 1.4;">
          <strong style="color: var(--cyan);">1️⃣ Layer 1: Core Automation Rules (Declarative)</strong><br>
          <span style="font-size: 0.74rem; color: var(--text-dim);">
            Configured via checkboxes &amp; priority lists (left panel). Automatically claims rewards, repairs defenses, and queues builds. No coding needed!
          </span>
        </div>
        <div style="color: var(--text-dim); font-size: 1.2rem; font-weight: bold; text-align: center;">➔</div>
        <div style="font-size: 0.8rem; line-height: 1.4;">
          <strong style="color: #10b981;">2️⃣ Layer 2: Custom Python Hook (Optional Code)</strong><br>
          <span style="font-size: 0.74rem; color: var(--text-dim);">
            Written in Python code (right panel). Executes custom logic (fleet orders, scans, market trades) on top of the rules.
          </span>
        </div>
      </div>
    </div>

    <!-- Strategy Studio Split Layout -->
    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 1.5rem; margin-bottom: 1.5rem;">
      <!-- Left: Visual Strategy Configurator with Named Profiles -->
      <div class="panel">
        <div class="panel-header">
          <div>
            <div class="panel-title">⚙️ Layer 1: Automation Rules &amp; Config</div>
            <div style="font-size: 0.72rem; color: var(--text-dim); font-family: var(--font-mono); margin-top: 0.15rem;">
              Active File: <span id="cfg-active-filepath" style="color: var(--cyan);">bot_config.json</span>
            </div>
          </div>
          <span class="badge badge-info" id="cfg-active-badge">Active Profile</span>
        </div>

        <!-- Profile Selector & Name Input -->
        <div style="background: rgba(0,0,0,0.25); border: 1px solid rgba(255,255,255,0.08); border-radius: 8px; padding: 0.75rem; margin-bottom: 1rem;">
          <div style="display: grid; grid-template-columns: 1.2fr 1.2fr auto; gap: 0.5rem; align-items: flex-end;">
            <div class="form-group" style="margin-bottom: 0;">
              <label class="form-label" style="font-size: 0.75rem;">Load Named Profile:</label>
              <select id="cfg-profile-select" class="form-control" onchange="onProfileSelectChange(this.value)">
                <option value="">Choose Profile...</option>
              </select>
            </div>
            <div class="form-group" style="margin-bottom: 0;">
              <label class="form-label" style="font-size: 0.75rem;">Profile Name:</label>
              <input type="text" id="cfg-profile-name" class="form-control" placeholder="e.g. Economy Boom, Night Defense">
            </div>
            <div style="display: flex; gap: 0.35rem;">
              <button class="btn-primary" style="padding: 0.55rem 0.9rem; font-size: 0.78rem;" onclick="saveNamedProfile()">
                <span>💾</span> Save
              </button>
              <button class="btn-refresh" style="padding: 0.55rem 0.7rem; font-size: 0.78rem; color: #f87171; border-color: rgba(239,68,68,0.3);" onclick="deleteCurrentProfile()" title="Delete selected profile">
                🗑️
              </button>
            </div>
          </div>
          <div id="cfg-save-location-info" style="font-size: 0.72rem; color: var(--text-dim); margin-top: 0.45rem; font-family: var(--font-mono);">
            💾 Saved to: <span style="color: #cbd5e1;">config_profiles/&lt;name&gt;.json</span> &amp; activated in <span style="color: var(--cyan);">bot_config.json</span>
          </div>
        </div>

        <div style="display: flex; flex-direction: column; gap: 0.75rem; margin-bottom: 1.25rem;">
          <label style="display: flex; align-items: center; gap: 0.6rem; cursor: pointer;">
            <input type="checkbox" id="cfg-auto-claim" style="width: 18px; height: 18px; accent-color: var(--cyan);">
            <span>🎁 <strong>Auto-Claim Missions</strong> (Claims completed quests every tick)</span>
          </label>
          <label style="display: flex; align-items: center; gap: 0.6rem; cursor: pointer;">
            <input type="checkbox" id="cfg-auto-repair" style="width: 18px; height: 18px; accent-color: var(--cyan);">
            <span>🛡️ <strong>Auto-Repair PDS Defenses</strong> (Emergency repairs if damaged)</span>
          </label>
          <label style="display: flex; align-items: center; gap: 0.6rem; cursor: pointer;">
            <input type="checkbox" id="cfg-auto-construct" style="width: 18px; height: 18px; accent-color: var(--cyan);">
            <span>🔨 <strong>Auto-Construct Buildings</strong> (Upgrades highest affordable priority)</span>
          </label>
          <label style="display: flex; align-items: center; gap: 0.6rem; cursor: pointer;">
            <input type="checkbox" id="cfg-auto-research" style="width: 18px; height: 18px; accent-color: var(--cyan);">
            <span>🔬 <strong>Auto-Research Technologies</strong> (Researches prioritized tech tree)</span>
          </label>
          <label style="display: flex; align-items: center; gap: 0.6rem; cursor: pointer;">
            <input type="checkbox" id="cfg-dry-run" style="width: 18px; height: 18px; accent-color: var(--yellow);">
            <span style="color: var(--yellow);">🔍 <strong>Dry-Run Mode</strong> (Simulate decisions without spending quota)</span>
          </label>
        </div>

        <div class="form-group">
          <label class="form-label">Max Modifying Actions Per Tick (Safety Cap, 1 - 10):</label>
          <input type="number" id="cfg-max-actions" class="form-control" min="1" max="10" value="8">
        </div>

        <div class="form-group">
          <label class="form-label">Construction Priorities (IDs in build order):</label>
          <textarea id="cfg-construction-prio" class="form-control" rows="3" style="font-family: var(--font-mono); font-size: 0.8rem;"></textarea>
          <div style="font-size: 0.72rem; color: var(--text-dim); margin-top: 0.2rem;">Comma-separated IDs, e.g. main-shipyard, main-metal-mine, main-shield-generator</div>
        </div>

        <div class="form-group">
          <label class="form-label">Research Priorities (Tech IDs in research order):</label>
          <textarea id="cfg-research-prio" class="form-control" rows="2" style="font-family: var(--font-mono); font-size: 0.8rem;"></textarea>
          <div style="font-size: 0.72rem; color: var(--text-dim); margin-top: 0.2rem;">E.g. main-constructions, main-hyperspace-travel, main-intelligence</div>
        </div>

        <div style="display: flex; justify-content: space-between; align-items: center; margin-top: 0.5rem;">
          <button class="btn-primary" onclick="saveBotConfig()">
            <span>💾</span> Save to Active Config
          </button>
          <span style="font-size: 0.72rem; color: var(--text-dim); font-family: var(--font-mono);">
            File: <code>bot_config.json</code>
          </span>
        </div>
      </div>

      <!-- Right: Interactive Python Strategy Script Editor & Library -->
      <div class="panel" style="display: flex; flex-direction: column;">
        <div class="panel-header">
          <div>
            <div class="panel-title">📜 Layer 2: Custom Python Code Hook (Advanced Logic)</div>
            <div style="font-size: 0.72rem; color: var(--text-dim); font-family: var(--font-mono); margin-top: 0.15rem;">
              Active File: <span id="strat-active-filepath" style="color: #a5f3fc;">bot_strategy.py</span> (Runs alongside Layer 1 rules)
            </div>
          </div>
          <span class="badge badge-info">Live-Reloads on Save</span>
        </div>

        <!-- Explanation Tip -->
        <div style="background: rgba(0, 229, 255, 0.05); border: 1px dashed rgba(0, 229, 255, 0.25); border-radius: 6px; padding: 0.55rem 0.75rem; margin-bottom: 0.75rem; font-size: 0.75rem; color: var(--text-dim); line-height: 1.4;">
          💡 <strong>Why doesn't saving Layer 1 rules change this code?</strong> The Layer 1 rules (left) are declarative checkboxes executed automatically by the engine. This hook (right) is pure Python code for custom logic. The engine passes your active rules directly into the <code>config</code> parameter: <code>def on_tick(client, state, config, logger):</code>.
        </div>

        <!-- Script Selector & Name Input -->
        <div style="background: rgba(0,0,0,0.25); border: 1px solid rgba(255,255,255,0.08); border-radius: 8px; padding: 0.75rem; margin-bottom: 0.85rem;">
          <div style="display: grid; grid-template-columns: 1.2fr 1.2fr auto; gap: 0.5rem; align-items: flex-end;">
            <div class="form-group" style="margin-bottom: 0;">
              <label class="form-label" style="font-size: 0.75rem;">Load Strategy Script:</label>
              <select id="strategy-script-select" class="form-control" onchange="onStrategyScriptChange(this.value)">
                <option value="">Select Script / Template...</option>
              </select>
            </div>
            <div class="form-group" style="margin-bottom: 0;">
              <label class="form-label" style="font-size: 0.75rem;">Script File Name:</label>
              <input type="text" id="strategy-script-name" class="form-control" placeholder="e.g. my_custom_strategy.py">
            </div>
            <div style="display: flex; gap: 0.35rem;">
              <button class="btn-primary" style="padding: 0.55rem 0.9rem; font-size: 0.78rem;" onclick="saveNamedStrategyScript(false)">
                <span>💾</span> Save
              </button>
              <button class="btn-refresh" style="padding: 0.55rem 0.7rem; font-size: 0.78rem; color: #f87171; border-color: rgba(239,68,68,0.3);" onclick="deleteCurrentStrategyScript()" title="Delete custom script">
                🗑️
              </button>
            </div>
          </div>
          <div id="strat-save-location-info" style="font-size: 0.72rem; color: var(--text-dim); margin-top: 0.45rem; font-family: var(--font-mono);">
            💾 Saved to: <span style="color: #cbd5e1;">custom_strategies/&lt;name&gt;.py</span>
          </div>
        </div>

        <textarea id="bot-strategy-code" class="form-control" rows="15" style="flex: 1; font-family: var(--font-mono); font-size: 0.82rem; line-height: 1.45; background: #030712; color: #a5f3fc; border: 1px solid rgba(0, 229, 255, 0.2); resize: vertical;"></textarea>

        <div style="margin-top: 0.85rem; display: flex; justify-content: space-between; align-items: center;">
          <button class="btn-primary" style="background: linear-gradient(135deg, #10b981, #059669);" onclick="saveNamedStrategyScript(true)">
            <span>🚀</span> Save & Set as Active Bot Strategy
          </button>
          <span style="font-size: 0.72rem; color: var(--text-dim); font-family: var(--font-mono);">
            Writes to <code>bot_strategy.py</code> • Dynamically reloads
          </span>
        </div>
      </div>
    </div>

    <!-- Specific Command Dispatcher & Task Interval Scheduler -->
    <div class="panel" style="margin-bottom: 1.5rem; border-color: rgba(0, 229, 255, 0.35);">
      <div class="panel-header">
        <div style="display: flex; align-items: center; gap: 0.6rem;">
          <span style="font-size: 1.25rem;">🎯</span>
          <div>
            <div class="panel-title" style="color: var(--cyan);">Specific Command Dispatcher & Interval Task Scheduler</div>
            <div style="font-size: 0.8rem; color: var(--text-dim); margin-top: 0.15rem;">
              Run any of the 67 commands immediately, on the next tick, or on recurring intervals (e.g. every tick, every 2 ticks / 1 hr, every 4 ticks, etc.)
            </div>
          </div>
        </div>
        <span class="badge badge-info">All 67 Tools Supported</span>
      </div>

      <!-- Controls Row 1: Command & Schedule Interval Selection -->
      <div style="display: grid; grid-template-columns: 2fr 2fr 1fr; gap: 1rem; margin-bottom: 0.85rem; align-items: flex-end;">
        <div class="form-group" style="margin-bottom: 0;">
          <label class="form-label">1. Select Game Command (67 Tools):</label>
          <select id="bot-dispatch-tool" class="form-control" onchange="onDispatchToolChange(this.value)">
            <option value="">Choose a command...</option>
          </select>
        </div>

        <div class="form-group" style="margin-bottom: 0;">
          <label class="form-label">2. Execution Interval / Schedule:</label>
          <select id="bot-dispatch-schedule" class="form-control" onchange="onDispatchScheduleChange(this.value)">
            <option value="run_now">⚡ Run Now (Immediate execution via bot)</option>
            <option value="next_tick" selected>🎯 Next Game Tick Only (One-off)</option>
            <option value="every_tick">⏱️ Every Tick (Every 30 minutes)</option>
            <option value="interval_2">⏱️ Every 2 Ticks (Every 1 hour)</option>
            <option value="interval_4">⏱️ Every 4 Ticks (Every 2 hours)</option>
            <option value="interval_6">⏱️ Every 6 Ticks (Every 3 hours)</option>
            <option value="interval_12">⏱️ Every 12 Ticks (Every 6 hours)</option>
            <option value="interval_24">⏱️ Every 24 Ticks (Every 12 hours)</option>
            <option value="custom_interval">⏱️ Custom Interval (Every N Ticks)</option>
            <option value="specific_tick">📅 At Specific Game Tick (Once)</option>
          </select>
        </div>

        <div class="form-group" id="bot-custom-tick-group" style="margin-bottom: 0; display: none;">
          <label class="form-label" id="bot-custom-tick-label">Tick Value:</label>
          <input type="number" id="bot-custom-tick-val" class="form-control" placeholder="e.g. 2" value="2" min="1">
        </div>
      </div>

      <!-- Controls Row 2: Full-Width Arguments Box -->
      <div class="form-group" style="margin-bottom: 0.6rem;">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.35rem;">
          <label class="form-label" style="margin-bottom: 0;">3. Command Arguments (JSON format — Full Width):</label>
          <div style="display: flex; gap: 0.4rem; font-size: 0.72rem;">
            <span style="color: var(--text-dim);">Quick Presets:</span>
            <a href="javascript:void(0)" onclick="setQuickArgs('produce_ships')" style="color: var(--cyan); text-decoration: none;">[Centurions]</a>
            <a href="javascript:void(0)" onclick="setQuickArgs('search_asteroids')" style="color: var(--cyan); text-decoration: none;">[Asteroid Scan]</a>
            <a href="javascript:void(0)" onclick="setQuickArgs('change_tax_rate')" style="color: var(--cyan); text-decoration: none;">[Tax 10%]</a>
            <a href="javascript:void(0)" onclick="setQuickArgs('repair_pds')" style="color: var(--cyan); text-decoration: none;">[Repair PDS]</a>
            <a href="javascript:void(0)" onclick="setQuickArgs('empty')" style="color: var(--text-dim); text-decoration: none;">[Empty {}]</a>
          </div>
        </div>
        <textarea id="bot-dispatch-args" class="form-control" rows="3" style="width: 100%; box-sizing: border-box; font-family: var(--font-mono); font-size: 0.82rem; line-height: 1.4; background: #030712; color: #a5f3fc; border: 1px solid rgba(0, 229, 255, 0.25); resize: vertical;" placeholder='{"shipId": "main-centurion", "quantity": 10}'>{}</textarea>
      </div>

      <!-- Controls Row 3: Action Buttons -->
      <div style="display: flex; gap: 0.75rem; margin-bottom: 1.25rem;">
        <button class="btn-primary" style="background: linear-gradient(135deg, #0284c7, #0369a1);" onclick="dispatchBotAction()">
          <span id="btn-dispatch-icon">🚀</span> <span id="btn-dispatch-text">Submit Action / Schedule Order</span>
        </button>
        <button class="btn-refresh" onclick="loadBotSchedules(); loadBotQueue();">
          <span>🔄</span> Refresh Active Schedules
        </button>
      </div>

      <!-- Schedules & Queues Grid -->
      <div style="display: grid; grid-template-columns: 1.4fr 1fr; gap: 1rem;">
        <!-- Recurring / Interval Schedules Table -->
        <div style="background: rgba(0,0,0,0.25); border: 1px solid rgba(255,255,255,0.08); border-radius: 8px; padding: 0.85rem;">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.6rem;">
            <span style="font-family: var(--font-display); font-size: 0.85rem; font-weight: 700; color: #c084fc;">
              ⏰ Recurring & Interval Scheduled Tasks
            </span>
            <span class="badge" style="background: rgba(168, 85, 247, 0.15); color: #c084fc; border: 1px solid #c084fc; font-size: 0.7rem;">Auto-Evaluated Every Tick</span>
          </div>
          <div id="bot-schedules-list" style="font-family: var(--font-mono); font-size: 0.78rem; max-height: 220px; overflow-y: auto;">
            Loading recurring schedules...
          </div>
        </div>

        <!-- Next-Tick Staged Orders List -->
        <div style="background: rgba(0,0,0,0.25); border: 1px solid rgba(255,255,255,0.08); border-radius: 8px; padding: 0.85rem;">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.6rem;">
            <span style="font-family: var(--font-display); font-size: 0.85rem; font-weight: 700; color: var(--cyan);">
              🎯 Next-Tick Staged Orders (One-Off)
            </span>
            <button class="btn-refresh" style="font-size: 0.7rem; padding: 0.2rem 0.5rem;" onclick="clearBotQueue()">Clear Staged</button>
          </div>
          <div id="bot-queued-orders-list" style="font-family: var(--font-mono); font-size: 0.78rem; max-height: 220px; overflow-y: auto;">
            Loading staged orders...
          </div>
        </div>
      </div>
    </div>

    <!-- Live Execution Console Stream -->
    <div class="panel">
      <div class="panel-header">
        <div class="panel-title">📟 Live Bot Decision Stream & Telemetry Logs</div>
        <div style="display: flex; align-items: center; gap: 1rem;">
          <label style="display: flex; align-items: center; gap: 0.4rem; font-family: var(--font-mono); font-size: 0.75rem; color: var(--text-dim); cursor: pointer;">
            <input type="checkbox" id="bot-log-auto-scroll" checked> Auto-Scroll
          </label>
          <button class="btn-refresh" style="padding: 0.25rem 0.6rem; font-size: 0.75rem;" onclick="fetchBotLogs()">
            Refresh Logs
          </button>
        </div>
      </div>
      <div class="result-box" id="bot-logs-box" style="height: 240px; color: #4ade80;">Loading bot logs...</div>
    </div>
  </div>

  <!-- TAB 5: Bot Memory -->
  <div id="tab-memory" class="tab-content">
    <div class="panel" style="margin-bottom: 1.5rem;">
      <div class="panel-header">
        <div class="panel-title">🧠 Agent Memory Scratchpad</div>
        <span class="badge badge-info">Persists Between Sessions</span>
      </div>
      <p style="color: var(--text-dim); margin-bottom: 1rem; font-size: 0.9rem;">
        Store strategy states, waypoint targets, defense plans, or tick schedules for your autonomous bot.
      </p>
      <div style="display: grid; grid-template-columns: 1fr 2fr auto; gap: 0.75rem;">
        <input type="text" id="mem-key-input" class="form-control" placeholder="Key (e.g. current_target)">
        <input type="text" id="mem-val-input" class="form-control" placeholder="Value (string or JSON)">
        <button class="btn-primary" onclick="saveMemoryEntry()">Save Entry</button>
      </div>
    </div>

    <div class="panel">
      <div class="panel-header">
        <div class="panel-title">Stored Memory Keys</div>
      </div>
      <div id="memory-keys-list" style="font-family: var(--font-mono); font-size: 0.9rem;">
        <div style="color: var(--text-dim);">Loading keys...</div>
      </div>
    </div>
  </div>
</div>

<!-- Toast notification -->
<div id="toast"></div>

<script>
  let allTools = [];
  let selectedTool = null;
  let currentCategory = 'ALL';
  let currentTick = 0;

  function formatNum(val) {
    if (typeof val === 'number') {
      return val.toLocaleString();
    }
    return val || '0';
  }

  function escapeHtml(str) {
    return str
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  function showToast(msg) {
    const t = document.getElementById('toast');
    t.textContent = msg;
    t.classList.add('show');
    setTimeout(() => t.classList.remove('show'), 3500);
  }

  function getQuotaState() {
    const key = 'pegasus_quota_' + currentTick;
    try {
      return JSON.parse(localStorage.getItem(key)) || { actions: 0, launches: 0, scans: 0 };
    } catch (e) {
      return { actions: 0, launches: 0, scans: 0 };
    }
  }

  function saveQuotaState(state) {
    const key = 'pegasus_quota_' + currentTick;
    localStorage.setItem(key, JSON.stringify(state));
    renderQuotaMeters();
  }

  function recordQuotaUsage(toolName) {
    const isLaunch = toolName === 'launch_fleet';
    const isScan = toolName.includes('scan') && (toolName.includes('perform') || toolName.includes('wave'));
    const isAction = /build|start|cancel|produce|assign|change|trade|search|initiate|repair|launch|recall|perform|send|create|join|leave|accept|invite|kick|declare|decline|claim|set|delete/.test(toolName);

    if (!isAction) return;

    const state = getQuotaState();
    state.actions = Math.min(10, (state.actions || 0) + 1);
    if (isLaunch) state.launches = Math.min(3, (state.launches || 0) + 1);
    if (isScan) state.scans = Math.min(2, (state.scans || 0) + 1);
    saveQuotaState(state);
  }

  function renderQuotaMeters() {
    const state = getQuotaState();
    const badge = document.getElementById('quota-tick-badge');
    if (badge) badge.textContent = `Tick ${currentTick || '---'}`;

    const actUsed = state.actions || 0;
    const actPct = (actUsed / 10) * 100;
    const actText = document.getElementById('quota-actions-text');
    const actBar = document.getElementById('quota-actions-bar');
    if (actText) actText.textContent = `${actUsed} / 10 used (${10 - actUsed} left)`;
    if (actBar) {
      actBar.style.width = actPct + '%';
      actBar.style.background = actUsed >= 9 ? 'var(--red)' : (actUsed >= 6 ? 'var(--yellow)' : 'var(--green)');
    }

    const flUsed = state.launches || 0;
    const flPct = (flUsed / 3) * 100;
    const flText = document.getElementById('quota-launches-text');
    const flBar = document.getElementById('quota-launches-bar');
    if (flText) flText.textContent = `${flUsed} / 3 used (${3 - flUsed} left)`;
    if (flBar) {
      flBar.style.width = flPct + '%';
      flBar.style.background = flUsed >= 3 ? 'var(--red)' : 'var(--yellow)';
    }

    const scUsed = state.scans || 0;
    const scPct = (scUsed / 2) * 100;
    const scText = document.getElementById('quota-scans-text');
    const scBar = document.getElementById('quota-scans-bar');
    if (scText) scText.textContent = `${scUsed} / 2 used (${2 - scUsed} left)`;
    if (scBar) {
      scBar.style.width = scPct + '%';
      scBar.style.background = scUsed >= 2 ? 'var(--red)' : 'var(--cyan)';
    }
  }

  function resetQuotaTracker() {
    saveQuotaState({ actions: 0, launches: 0, scans: 0 });
    showToast("Quota tracker reset to 0 for current tick");
  }

  function switchTab(tabId) {
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
    
    event.currentTarget.classList.add('active');
    document.getElementById('tab-' + tabId).classList.add('active');

    // Auto-refresh when switching back to Mission Control!
    if (tabId === 'dashboard') refreshDashboard();
    if (tabId === 'commands' && allTools.length === 0) loadTools();
    if (tabId === 'missions') loadMissions();
    if (tabId === 'ships') loadShipsAndPds();
    if (tabId === 'bot') loadBotStudio();
    if (tabId === 'memory') loadMemory();
  }

  // --- Telemetry & Dashboard ---
  async function refreshDashboard() {
    try {
      const res = await fetch('/api/state');
      const json = await res.json();
      if (!json.success) throw new Error(json.error);

      const summary = json.summary?.data || {};
      const planet = json.planet?.data || summary.planet || {};
      const tick = json.tick?.data || {};
      const rank = json.rank?.data || {};

      // Header tick
      currentTick = tick.tick || summary.tick || currentTick;
      document.getElementById('header-tick').textContent = currentTick || '---';
      document.getElementById('header-countdown').textContent = tick.nextTickIn || summary.nextTickIn || '---';
      renderQuotaMeters();

      // Colony banner
      document.getElementById('stat-colony').textContent = planet.name || 'Unknown';
      document.getElementById('stat-coords').textContent = planet.coords || '---';
      document.getElementById('stat-score').textContent = formatNum(planet.score);
      document.getElementById('stat-rank').textContent = rank.rank ? `#${rank.rank} of ${rank.totalPlayers}` : '---';
      document.getElementById('stat-happiness').textContent = (planet.happiness || 0) + '%';
      document.getElementById('stat-asteroids').textContent = formatNum(planet.asteroidCount);

      // Resources
      document.getElementById('res-metal').textContent = formatNum(planet.metal);
      document.getElementById('res-crystal').textContent = formatNum(planet.crystal);
      document.getElementById('res-eonium').textContent = formatNum(planet.eonium);
      document.getElementById('res-asteroids').textContent = formatNum(planet.asteroidCount);

      // Population
      const totPop = planet.totalPopulation || 1;
      document.getElementById('pop-total').textContent = formatNum(totPop);
      
      const miners = planet.miners || 0;
      const resers = planet.researchers || 0;
      const bldrs = planet.builders || 0;
      const ships = planet.shipwrights || 0;

      document.getElementById('pop-miners-val').textContent = `${formatNum(miners)} (${((miners/totPop)*100).toFixed(1)}%)`;
      document.getElementById('pop-miners-bar').style.width = ((miners/totPop)*100) + '%';

      document.getElementById('pop-researchers-val').textContent = `${formatNum(resers)} (${((resers/totPop)*100).toFixed(1)}%)`;
      document.getElementById('pop-researchers-bar').style.width = ((resers/totPop)*100) + '%';

      document.getElementById('pop-builders-val').textContent = `${formatNum(bldrs)} (${((bldrs/totPop)*100).toFixed(1)}%)`;
      document.getElementById('pop-builders-bar').style.width = ((bldrs/totPop)*100) + '%';

      document.getElementById('pop-shipwrights-val').textContent = `${formatNum(ships)} (${((ships/totPop)*100).toFixed(1)}%)`;
      document.getElementById('pop-shipwrights-bar').style.width = ((ships/totPop)*100) + '%';

      // Queues
      const constructions = summary.constructions || [];
      const researchList = summary.research || [];
      const activeBuild = constructions.find(c => c.currentlyInProgress);
      const activeRes = researchList.find(r => r.currentlyInProgress);

      if (activeBuild) {
        const pct = ((activeBuild.currentPoints / activeBuild.requiredPoints) * 100).toFixed(1);
        document.getElementById('build-name').textContent = `🔨 ${activeBuild.name} (Lvl ${activeBuild.currentLevel})`;
        document.getElementById('build-pct').textContent = pct + '%';
        document.getElementById('build-bar').style.width = pct + '%';
        document.getElementById('build-pts').textContent = `${formatNum(activeBuild.currentPoints)} / ${formatNum(activeBuild.requiredPoints)} pts`;
      } else {
        document.getElementById('build-name').textContent = '🔨 Construction: Idle';
        document.getElementById('build-pct').textContent = '0%';
        document.getElementById('build-bar').style.width = '0%';
        document.getElementById('build-pts').textContent = 'No active construction';
      }

      if (activeRes) {
        const pct = ((activeRes.currentPoints / activeRes.requiredPoints) * 100).toFixed(1);
        document.getElementById('research-name').textContent = `🔬 ${activeRes.name} (Lvl ${activeRes.currentLevel})`;
        document.getElementById('research-pct').textContent = pct + '%';
        document.getElementById('research-bar').style.width = pct + '%';
        document.getElementById('research-pts').textContent = `${formatNum(activeRes.currentPoints)} / ${formatNum(activeRes.requiredPoints)} pts`;
      } else {
        document.getElementById('research-name').textContent = '🔬 Research: Idle';
        document.getElementById('research-pct').textContent = '0%';
        document.getElementById('research-bar').style.width = '0%';
        document.getElementById('research-pts').textContent = 'No active research';
      }

      // Fleets
      const fleetTbody = document.getElementById('fleet-rows');
      fleetTbody.innerHTML = '';
      
      // Base Garrison
      if (planet.shipsBaseFleet) {
        const comp = Object.entries(planet.shipsBaseFleet)
          .map(([k, v]) => `${k.replace('main-vanguard-', '').replace('main-', '')}: ${formatNum(v)}`)
          .join(', ');
        fleetTbody.innerHTML += `
          <tr>
            <td><strong>Stationary Garrison</strong></td>
            <td><span class="badge badge-info">ORBIT</span></td>
            <td>DEFENSE</td>
            <td>${comp || 'None'}</td>
            <td>Home Defense</td>
          </tr>
        `;
      }

      const fleets = summary.fleets || [];
      if (fleets.length === 0 && !planet.shipsBaseFleet) {
        fleetTbody.innerHTML = '<tr><td colspan="5" style="text-align: center; color: var(--text-dim);">No fleets found.</td></tr>';
      } else {
        fleets.forEach(fl => {
          const statusBadge = fl.status === 'TRAVELING' ? 'badge-action' : (fl.status === 'DOCKED' ? 'badge-read' : 'badge-quota');
          const comp = Object.entries(fl.ships || {})
            .map(([k, v]) => `${k.replace('main-vanguard-', '').replace('main-', '')}: ${formatNum(v)}`)
            .join(', ') || '<span style="color: var(--text-dim)">Empty</span>';
          fleetTbody.innerHTML += `
            <tr>
              <td><strong>${fl.name || fl.id.slice(0, 8)}</strong></td>
              <td><span class="badge ${statusBadge}">${fl.status}</span></td>
              <td><strong style="color: var(--yellow);">${fl.mission}</strong></td>
              <td>${comp}</td>
              <td>${fl.arrivesAt ? `Tick ${fl.arrivesAt}` : 'Docked'}</td>
            </tr>
          `;
        });
      }

      showToast("Telemetry synced with game server.");
    } catch (e) {
      showToast("Error updating dashboard: " + e.message);
    }
  }

  // --- Command Hub & Tools ---
  async function loadTools() {
    try {
      const res = await fetch('/api/tools');
      const json = await res.json();
      allTools = json.tools || [];
      filterTools();
      if (allTools.length > 0) selectTool(allTools[0].name);
    } catch (e) {
      showToast("Error loading tools: " + e.message);
    }
  }

  function setCategory(cat) {
    currentCategory = cat;
    document.querySelectorAll('.cat-pill').forEach(p => p.classList.remove('active'));
    event.currentTarget.classList.add('active');
    filterTools();
  }

  function filterTools() {
    const q = document.getElementById('tool-search').value.toLowerCase();
    const container = document.getElementById('tool-list-container');
    container.innerHTML = '';

    const filtered = allTools.filter(t => {
      const name = t.name.toLowerCase();
      const desc = (t.description || '').toLowerCase();
      const matchesSearch = name.includes(q) || desc.includes(q);
      if (!matchesSearch) return false;

      if (currentCategory === 'PLANET') return name.includes('planet') || name.includes('construction') || name.includes('research') || name.includes('trade') || name.includes('population');
      if (currentCategory === 'MILITARY') return name.includes('fleet') || name.includes('scan') || name.includes('battle') || name.includes('pds');
      if (currentCategory === 'SOCIAL') return name.includes('alliance') || name.includes('message') || name.includes('leaderboard') || name.includes('war');
      if (currentCategory === 'META') return name.includes('game') || name.includes('tick') || name.includes('rules');
      if (currentCategory === 'MEMORY') return name.includes('memory');
      return true;
    });

    filtered.forEach(t => {
      const isAction = /build|start|cancel|produce|assign|change|trade|search|initiate|repair|launch|recall|perform|send|create|join|leave|accept|invite|kick|declare|decline|claim|set|delete/.test(t.name);
      const item = document.createElement('div');
      item.className = 'tool-item' + (selectedTool && selectedTool.name === t.name ? ' selected' : '');
      item.onclick = () => selectTool(t.name);
      item.innerHTML = `
        <span class="tool-item-name">${t.name}</span>
        <span class="badge ${isAction ? 'badge-action' : 'badge-read'}" style="font-size: 0.65rem;">
          ${isAction ? 'ACTION' : 'READ'}
        </span>
      `;
      container.appendChild(item);
    });
  }

  function selectTool(toolName) {
    selectedTool = allTools.find(t => t.name === toolName);
    if (!selectedTool) return;

    document.querySelectorAll('.tool-item').forEach(el => {
      el.classList.toggle('selected', el.querySelector('.tool-item-name').textContent === toolName);
    });

    document.getElementById('selected-tool-name').textContent = selectedTool.name;
    document.getElementById('selected-tool-desc').textContent = selectedTool.description || 'No description provided.';
    
    const isAction = /build|start|cancel|produce|assign|change|trade|search|initiate|repair|launch|recall|perform|send|create|join|leave|accept|invite|kick|declare|decline|claim|set|delete/.test(selectedTool.name);
    document.getElementById('selected-tool-badge').innerHTML = `
      <span class="badge ${isAction ? 'badge-action' : 'badge-read'}">
        ${isAction ? '⚠️ ACTION (Consumes Quota)' : '✨ READ (Free)'}
      </span>
    `;

    // Build dynamic form
    const formContainer = document.getElementById('tool-form-container');
    formContainer.innerHTML = '';

    const schema = selectedTool.inputSchema || {};
    const props = schema.properties || {};
    const required = schema.required || [];

    const keys = Object.keys(props);
    if (keys.length === 0) {
      formContainer.innerHTML = '<p style="color: var(--text-dim); font-size: 0.85rem; font-family: var(--font-mono);">This tool takes no parameters. Ready to execute.</p>';
      return;
    }

    keys.forEach(k => {
      const p = props[k];
      const isReq = required.includes(k);
      const fg = document.createElement('div');
      fg.className = 'form-group';
      
      let inputHtml = '';
      if (p.type === 'boolean') {
        inputHtml = `
          <select id="param-${k}" class="form-control">
            <option value="false">false</option>
            <option value="true">true</option>
          </select>
        `;
      } else if (p.type === 'number' || p.type === 'integer') {
        inputHtml = `<input type="number" id="param-${k}" class="form-control" placeholder="${p.description || ''}">`;
      } else {
        inputHtml = `<input type="text" id="param-${k}" class="form-control" placeholder="${p.description || ''}">`;
      }

      fg.innerHTML = `
        <label class="form-label">${k} ${isReq ? '<strong style="color: var(--red);">*</strong>' : ''} <span style="color: var(--cyan);">(${p.type || 'any'})</span></label>
        ${inputHtml}
      `;
      formContainer.appendChild(fg);
    });
  }

  async function executeSelectedTool() {
    if (!selectedTool) return;
    const btn = document.getElementById('btn-run-tool');
    btn.disabled = true;
    btn.innerHTML = '<span>⏳</span> Executing...';

    const args = {};
    const props = (selectedTool.inputSchema && selectedTool.inputSchema.properties) || {};
    for (let k of Object.keys(props)) {
      const el = document.getElementById('param-' + k);
      if (el && el.value !== '') {
        const pType = props[k].type;
        if (pType === 'number' || pType === 'integer') {
          args[k] = Number(el.value);
        } else if (pType === 'boolean') {
          args[k] = el.value === 'true';
        } else {
          // Attempt JSON parse if object/array string
          try {
            args[k] = JSON.parse(el.value);
          } catch(e) {
            args[k] = el.value;
          }
        }
      }
    }

    try {
      const res = await fetch('/api/call', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ tool: selectedTool.name, arguments: args })
      });
      const data = await res.json();
      const outputEl = document.getElementById('output-box');
      const outText = JSON.stringify(data.result || data, null, 2);
      
      if (outText.includes('The table does not have the specified index')) {
        outputEl.innerHTML = `<span style="color: var(--yellow); font-weight: 700;">⚠️ Pegasus Galaxy Server-Side Database Issue:</span>\n` +
          `<span style="color: var(--text-dim);">The game server's AWS DynamoDB database is missing a Global Secondary Index (GSI) for this query on their backend.</span>\n\n` +
          escapeHtml(outText);
        showToast("Server returned DynamoDB index error (game server issue)");
      } else {
        outputEl.textContent = outText;
        if (!data.error && data.result?.success !== false) {
          recordQuotaUsage(selectedTool.name);
        }
        showToast(`Executed ${selectedTool.name} successfully!`);
      }
    } catch (e) {
      document.getElementById('output-box').textContent = "Execution error: " + e.message;
      showToast("Error running command");
    } finally {
      btn.disabled = false;
      btn.innerHTML = '<span>⚡</span> Run Command';
    }
  }

  function clearResults() {
    document.getElementById('output-box').textContent = '// Response data will appear here...';
  }

  function copyOutput() {
    const text = document.getElementById('output-box').textContent;
    navigator.clipboard.writeText(text);
    showToast("JSON copied to clipboard!");
  }

  // --- Missions ---
  async function loadMissions() {
    const container = document.getElementById('missions-list-container');
    const bannerArea = document.getElementById('claim-banner-area');
    container.innerHTML = '<div class="panel" style="text-align: center;">Loading mission data...</div>';

    try {
      const res = await fetch('/api/missions');
      const json = await res.json();
      const missions = json.data?.missions || [];
      const summary = json.data?.summary || {};

      const completedCount = summary.completed || 0;
      if (completedCount > 0) {
        bannerArea.innerHTML = `
          <div class="btn-claim-banner">
            <div>
              <div style="font-size: 1.1rem;">🎁 ${completedCount} Completed Mission(s) Ready to Claim!</div>
              <div style="font-size: 0.85rem; opacity: 0.9;">Claim your resources, score, and XP rewards now.</div>
            </div>
            <button class="btn-primary" style="background: white; color: #065f46;" onclick="claimAllMissions()">
              Claim All Rewards
            </button>
          </div>
        `;
      } else {
        bannerArea.innerHTML = '';
      }

      container.innerHTML = '';
      const order = { 'COMPLETED': 0, 'ACTIVE': 1, 'CLAIMED': 2, 'EXPIRED': 3 };
      missions.sort((a, b) => (order[a.status] || 9) - (order[b.status] || 9));

      missions.forEach(m => {
        const isComp = m.status === 'COMPLETED';
        const card = document.createElement('div');
        card.className = 'mission-card' + (isComp ? ' completed' : '');
        card.innerHTML = `
          <div>
            <div style="font-family: var(--font-display); font-weight: 700; color: var(--text-bright); margin-bottom: 0.2rem;">
              ${m.missionId}
            </div>
            <div style="font-family: var(--font-mono); font-size: 0.8rem; color: var(--text-dim);">
              Progress: ${m.progress?.join('/') || '-'}
            </div>
          </div>
          <div>
            <span class="badge ${isComp ? 'badge-read' : (m.status === 'ACTIVE' ? 'badge-quota' : 'badge-read')}">
              ${m.status}
            </span>
          </div>
        `;
        container.appendChild(card);
      });
    } catch(e) {
      container.innerHTML = `<div class="panel" style="color: var(--red);">Error loading missions: ${e.message}</div>`;
    }
  }

  async function claimAllMissions() {
    try {
      const res = await fetch('/api/call', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ tool: 'claim_missions', arguments: {} })
      });
      const data = await res.json();
      showToast("🎉 Mission rewards claimed successfully!");
      loadMissions();
      refreshDashboard();
    } catch(e) {
      showToast("Error claiming missions: " + e.message);
    }
  }

  // --- Ships & Planetary Defense (PDS) Codex ---
  let allShips = [];
  let allPds = [];
  let codexFaction = 'ALL';
  let codexClass = 'ALL';

  async function loadShipsAndPds() {
    try {
      const [shipsRes, pdsRes] = await Promise.all([
        fetch('/api/ships').then(r => r.json()),
        fetch('/api/pds').then(r => r.json())
      ]);
      allShips = shipsRes.ships || [];
      allPds = pdsRes.pds || [];
      renderCodex();
    } catch(e) {
      document.getElementById('pds-grid-container').innerHTML = `<div class="panel" style="color: var(--red);">Error loading defense data: ${e.message}</div>`;
    }
  }

  function setCodexFaction(fac) {
    codexFaction = fac;
    ['ALL', 'VANGUARD', 'SYNTHARA', 'ASHKARI', 'PDS'].forEach(f => {
      const el = document.getElementById('f-pill-' + f);
      if (el) el.classList.toggle('active', f === fac);
    });
    renderCodex();
  }

  function setCodexClass(cls) {
    codexClass = cls;
    ['ALL', 'LIGHT', 'MEDIUM', 'HEAVY', 'SPECIAL'].forEach(c => {
      const el = document.getElementById('c-pill-' + c);
      if (el) el.classList.toggle('active', c === cls);
    });
    renderCodex();
  }

  function renderCodex() {
    const q = (document.getElementById('codex-search')?.value || '').toLowerCase();
    const raceColsWrapper = document.getElementById('race-columns-wrapper');
    const pdsWrapper = document.getElementById('pds-section-wrapper');

    // Handle PDS-only or Race-only visibility
    if (codexFaction === 'PDS') {
      raceColsWrapper.style.display = 'none';
      pdsWrapper.style.display = 'block';
    } else if (codexFaction === 'ALL') {
      raceColsWrapper.style.display = 'grid';
      pdsWrapper.style.display = 'block';
      ['vanguard', 'synthara', 'ashkari'].forEach(col => {
        document.getElementById('col-' + col).style.display = 'flex';
      });
    } else {
      // Specific faction
      raceColsWrapper.style.display = 'grid';
      pdsWrapper.style.display = 'none';
      ['vanguard', 'synthara', 'ashkari'].forEach(col => {
        document.getElementById('col-' + col).style.display = (col.toUpperCase() === codexFaction) ? 'flex' : 'none';
      });
    }

    // Render Race Columns (Vanguard, Synthara, Ashkari)
    const factions = [
      { id: 'VANGUARD', container: 'vanguard-ships-container' },
      { id: 'SYNTHARA', container: 'synthara-ships-container' },
      { id: 'ASHKARI', container: 'ashkari-ships-container' }
    ];

    factions.forEach(f => {
      const cont = document.getElementById(f.container);
      if (!cont) return;
      cont.innerHTML = '';

      let fShips = allShips.filter(s => s.faction === f.id);
      if (codexClass !== 'ALL') {
        fShips = fShips.filter(s => s.shipClass === codexClass);
      }
      if (q) {
        fShips = fShips.filter(s =>
          (s.name || '').toLowerCase().includes(q) ||
          (s.category || '').toLowerCase().includes(q) ||
          (s.description || '').toLowerCase().includes(q)
        );
      }

      if (fShips.length === 0) {
        cont.innerHTML = '<div style="color: var(--text-dim); font-size: 0.85rem; font-style: italic; padding: 0.5rem;">No matching vessels found.</div>';
        return;
      }

      // Group into classes: LIGHT, MEDIUM, HEAVY, SPECIAL
      const classOrder = ['LIGHT', 'MEDIUM', 'HEAVY', 'SPECIAL'];
      classOrder.forEach(cls => {
        const clsShips = fShips.filter(s => s.shipClass === cls);
        if (clsShips.length === 0) return;

        const sec = document.createElement('div');
        sec.className = 'class-section';
        sec.innerHTML = `
          <div class="class-section-title">
            <span>${cls} CLASS</span>
            <span style="font-size: 0.7rem; color: var(--text-dim);">${clsShips.length} Blueprint${clsShips.length > 1 ? 's' : ''}</span>
          </div>
        `;

        clsShips.forEach(s => {
          const card = document.createElement('div');
          card.className = 'ship-card';

          // Target priorities
          const targets = [s.targetClass1, s.targetClass2, s.targetClass3].filter(Boolean);
          const targetBadges = targets.map((t, idx) => `<span class="target-badge">T${idx+1}: ${t}</span>`).join('');

          // Prerequisites
          const prereqStr = (s.prerequisites || []).map(p => `${p.name || p.id.replace('main-', '').replace('-', ' ')} (Lvl ${p.minLevel})`).join(', ');

          card.innerHTML = `
            <div class="ship-card-header">
              <div>
                <div class="ship-name">${s.name}</div>
                <div style="font-size: 0.75rem; color: var(--cyan); font-family: var(--font-mono);">${s.category}</div>
              </div>
              <span class="badge badge-quota" style="font-size: 0.68rem;">${s.shipClass}</span>
            </div>
            <p style="font-size: 0.8rem; color: var(--text-dim); margin-bottom: 0.6rem; line-height: 1.35;">${s.description || ''}</p>
            
            <div class="ship-stats-grid">
              <div>🛡️ Armor: <strong>${s.armor}</strong></div>
              <div>💥 Damage: <strong style="color: var(--yellow);">${s.damage || 0}</strong> ${s.empDamage ? `+ <span style="color: var(--cyan);">${s.empDamage} EMP</span>` : ''}</div>
              <div>⚡ Speed: <strong>${s.speed}</strong> (Init: ${s.init || 0})</div>
              <div>⛽ Fuel: <strong>${s.fuelConsumptionRate}</strong>/burn (Cap: ${formatNum(s.fuelCapacity || 0)})</div>
              <div>📦 Cargo: <strong>${formatNum(s.resourceCapacity || 0)}</strong></div>
              <div>⏳ Build: <strong>${s.eta} ticks</strong> (${formatNum(s.requiredPoints)} pts)</div>
            </div>

            ${targetBadges ? `<div style="margin-bottom: 0.5rem;"><span style="font-size: 0.7rem; color: var(--text-dim); font-family: var(--font-mono);">Priority: </span>${targetBadges}</div>` : ''}

            <div style="font-family: var(--font-mono); font-size: 0.72rem; color: var(--yellow); border-top: 1px solid rgba(255,255,255,0.06); padding-top: 0.4rem; margin-top: 0.4rem;">
              Cost: ${formatNum(s.requiredMetal)} Metal, ${formatNum(s.requiredCrystal)} Crystal, ${formatNum(s.requiredEonium)} Eonium
            </div>
            ${prereqStr ? `<div style="font-family: var(--font-mono); font-size: 0.7rem; color: var(--text-dim); margin-top: 0.2rem;">Req: ${prereqStr}</div>` : ''}
          `;
          sec.appendChild(card);
        });

        cont.appendChild(sec);
      });
    });

    // Render PDS Grid
    const pdsCont = document.getElementById('pds-grid-container');
    if (!pdsCont) return;
    pdsCont.innerHTML = '';

    let filteredPds = allPds;
    if (q) {
      filteredPds = filteredPds.filter(p =>
        (p.name || '').toLowerCase().includes(q) ||
        (p.description || '').toLowerCase().includes(q)
      );
    }

    if (filteredPds.length === 0) {
      pdsCont.innerHTML = '<div class="panel" style="text-align: center; color: var(--text-dim);">No matching planetary defense structures found.</div>';
      return;
    }

    filteredPds.forEach(p => {
      const card = document.createElement('div');
      const isBuilt = !!p.playerStatus;
      card.className = 'pds-card' + (isBuilt ? ' built' : '');

      const st = p.playerStatus;
      const statusBadge = isBuilt
        ? `<span class="badge badge-read">ACTIVE • LVL ${st.currentLevel}</span>`
        : `<span class="badge" style="background: rgba(255,255,255,0.05); color: var(--text-dim); border: 1px solid rgba(255,255,255,0.1);">UNBUILT</span>`;

      const cs = p.combatStats || {};
      const targets = [cs.targetClass1, cs.targetClass2, cs.targetClass3].filter(Boolean);
      const targetBadges = targets.map((t, idx) => `<span class="target-badge">T${idx+1}: ${t}</span>`).join('');

      let specialInfo = '';
      if (p.specialStats) {
        if (p.specialStats.absorptionPerLevel) {
          specialInfo = `<div>🛡️ Absorption: <strong>${p.specialStats.absorptionPerLevel}%/lvl</strong> (Max: ${p.specialStats.maxAbsorption}%)</div>`;
        } else if (p.specialStats.detectionPerLevel) {
          specialInfo = `<div>📡 Radar: <strong>+${p.specialStats.detectionPerLevel} range/lvl</strong> (Max: ${p.specialStats.maxDetection})</div>`;
        }
      }

      card.innerHTML = `
        <div class="pds-header">
          <div>
            <div class="pds-name">${p.name}</div>
            <div style="font-family: var(--font-mono); font-size: 0.75rem; color: var(--cyan);">Max Level: ${p.maxLevel}</div>
          </div>
          ${statusBadge}
        </div>

        <p style="font-size: 0.82rem; color: var(--text-dim); margin-bottom: 0.75rem; line-height: 1.4;">${p.description || ''}</p>

        ${isBuilt ? `
          <div style="background: rgba(16, 185, 129, 0.08); border: 1px solid rgba(16, 185, 129, 0.2); border-radius: 6px; padding: 0.5rem; margin-bottom: 0.75rem; font-family: var(--font-mono); font-size: 0.8rem;">
            <div style="display: flex; justify-content: space-between;">
              <span>Colony Health:</span>
              <strong style="color: var(--green);">${formatNum(st.healthPoints)} / ${formatNum(st.maxHealthPoints)} HP</strong>
            </div>
            <div style="font-size: 0.72rem; color: var(--text-dim); margin-top: 0.15rem;">
              Status: ${st.damaged ? '<span style="color: var(--red);">Damaged (Needs Repair)</span>' : '<span style="color: var(--green);">Operational</span>'}
            </div>
          </div>
        ` : ''}

        <div class="ship-stats-grid">
          <div>🛡️ Defense Armor: <strong>${cs.armor || 0}</strong></div>
          <div>💥 Weapon Damage: <strong style="color: var(--yellow);">${cs.damage || 0}</strong></div>
          <div>🎯 Gun Rating: <strong>${cs.gun || 0}</strong></div>
          <div>⚡ Initiative: <strong>${cs.initiative || 0}</strong></div>
          ${specialInfo}
          <div>⏳ Build Points: <strong>${formatNum(p.requiredPoints)}</strong></div>
        </div>

        ${targetBadges ? `<div style="margin-bottom: 0.6rem;"><span style="font-size: 0.72rem; color: var(--text-dim); font-family: var(--font-mono);">Target Priority: </span>${targetBadges}</div>` : ''}

        <div style="font-family: var(--font-mono); font-size: 0.75rem; color: var(--yellow); border-top: 1px solid rgba(255,255,255,0.06); padding-top: 0.5rem;">
          Lvl 1 Cost: ${formatNum(p.requiredMetal)} Metal, ${formatNum(p.requiredCrystal)} Crystal, ${formatNum(p.requiredEonium)} Eonium
        </div>
      `;
      pdsCont.appendChild(card);
    });
  }

  // --- Bot Memory ---
  async function loadMemory() {
    const list = document.getElementById('memory-keys-list');
    list.innerHTML = 'Loading memory keys...';

    try {
      const res = await fetch('/api/memory');
      const json = await res.json();
      const keys = json.data || json.keys || [];

      if (!keys || keys.length === 0) {
        list.innerHTML = '<span style="color: var(--text-dim);">No memory keys stored yet. Add one above!</span>';
        return;
      }

      list.innerHTML = '';
      for (let k of keys) {
        const row = document.createElement('div');
        row.style.display = 'flex';
        row.style.justifyContent = 'space-between';
        row.style.padding = '0.5rem';
        row.style.borderBottom = '1px solid rgba(255,255,255,0.05)';
        row.innerHTML = `
          <span>🔑 <strong>${k}</strong></span>
          <button class="btn-refresh" style="padding: 0.2rem 0.6rem; font-size: 0.75rem;" onclick="viewMemoryKey('${k}')">Read</button>
        `;
        list.appendChild(row);
      }
    } catch(e) {
      list.innerHTML = `<span style="color: var(--red);">Error: ${e.message}</span>`;
    }
  }

  async function saveMemoryEntry() {
    const k = document.getElementById('mem-key-input').value.trim();
    const v = document.getElementById('mem-val-input').value.trim();
    if (!k || !v) {
      showToast("Please enter both key and value");
      return;
    }

    try {
      await fetch('/api/call', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ tool: 'set_memory', arguments: { key: k, value: v } })
      });
      showToast(`Saved memory key "${k}"`);
      document.getElementById('mem-key-input').value = '';
      document.getElementById('mem-val-input').value = '';
      loadMemory();
    } catch(e) {
      showToast("Error saving memory: " + e.message);
    }
  }

  async function viewMemoryKey(k) {
    try {
      const res = await fetch('/api/call', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ tool: 'get_memory', arguments: { key: k } })
      });
      const data = await res.json();
      alert(`Memory [${k}]:\n` + JSON.stringify(data.result || data, null, 2));
    } catch(e) {
      showToast("Error reading memory: " + e.message);
    }
  }

  // --- Bot Studio Controls & Configuration ---
  let botPollTimer = null;

  async function loadBotStudio() {
    await Promise.all([
      refreshBotStatus(),
      loadBotConfig(),
      loadProfilesList(),
      loadBotStrategy(),
      loadStrategiesList(),
      fetchBotLogs(),
      loadBotQueue(),
      loadBotSchedules(),
      populateDispatchToolDropdown()
    ]);
    if (!botPollTimer) {
      botPollTimer = setInterval(() => {
        const botTab = document.getElementById('tab-bot');
        if (botTab && botTab.classList.contains('active')) {
          refreshBotStatus();
          fetchBotLogs();
          loadBotQueue();
          loadBotSchedules();
        }
      }, 4000);
    }
  }

  async function populateDispatchToolDropdown() {
    const sel = document.getElementById('bot-dispatch-tool');
    if (!sel || sel.options.length > 1) return;

    if (allTools.length === 0) {
      try {
        const res = await fetch('/api/tools');
        const json = await res.json();
        allTools = json.tools || [];
      } catch(e) {}
    }

    sel.innerHTML = '<option value="">Choose a command...</option>';
    const sorted = [...allTools].sort((a, b) => a.name.localeCompare(b.name));
    for (let t of sorted) {
      const opt = document.createElement('option');
      opt.value = t.name;
      opt.textContent = `${t.name} — ${(t.description || '').substring(0, 48)}...`;
      sel.appendChild(opt);
    }
  }

  const QUICK_TOOL_TEMPLATES = {
    produce_ships: '{\n  "shipId": "main-centurion",\n  "quantity": 10\n}',
    launch_fleet: '{\n  "fleetNumber": 1,\n  "targetCoords": "55:2:9",\n  "mission": "ATTACK",\n  "ships": {"main-centurion": 20}\n}',
    search_asteroids: '{}',
    perform_surface_scan: '{\n  "targetCoords": "55:2:9"\n}',
    perform_deep_scan: '{\n  "targetCoords": "55:2:9"\n}',
    start_construction: '{\n  "constructionId": "main-shield-generator"\n}',
    start_research: '{\n  "researchId": "main-constructions"\n}',
    repair_pds: '{\n  "pdsId": "main-laser-battery"\n}',
    claim_missions: '{}',
    change_tax_rate: '{\n  "taxRate": 10\n}',
    send_message: '{\n  "recipientPlanetId": "...",\n  "subject": "Hello",\n  "message": "Greetings from Pegasus bot"\n}'
  };

  function onDispatchToolChange(toolName) {
    const input = document.getElementById('bot-dispatch-args');
    if (!input) return;
    if (QUICK_TOOL_TEMPLATES[toolName]) {
      input.value = QUICK_TOOL_TEMPLATES[toolName];
      return;
    }
    const t = allTools.find(x => x.name === toolName);
    if (t && t.inputSchema && t.inputSchema.properties) {
      const sample = {};
      for (let k of Object.keys(t.inputSchema.properties)) {
        sample[k] = t.inputSchema.properties[k].type === 'number' ? 1 : "...";
      }
      input.value = JSON.stringify(sample, null, 2);
    } else {
      input.value = '{}';
    }
  }

  function setQuickArgs(preset) {
    const sel = document.getElementById('bot-dispatch-tool');
    const input = document.getElementById('bot-dispatch-args');
    if (preset === 'empty') {
      input.value = '{}';
      return;
    }
    if (QUICK_TOOL_TEMPLATES[preset]) {
      if (sel) sel.value = preset;
      input.value = QUICK_TOOL_TEMPLATES[preset];
      showToast(`Loaded preset template for ${preset}`);
    }
  }

  function onDispatchScheduleChange(val) {
    const customGroup = document.getElementById('bot-custom-tick-group');
    const customLabel = document.getElementById('bot-custom-tick-label');
    const customVal = document.getElementById('bot-custom-tick-val');
    const btnText = document.getElementById('btn-dispatch-text');
    const btnIcon = document.getElementById('btn-dispatch-icon');

    if (val === 'custom_interval') {
      customGroup.style.display = 'block';
      customLabel.textContent = 'Every N Ticks:';
      customVal.value = '3';
      btnIcon.textContent = '⏱️';
      btnText.textContent = 'Save Custom Interval Schedule';
    } else if (val === 'specific_tick') {
      customGroup.style.display = 'block';
      customLabel.textContent = 'Target Tick #:';
      customVal.value = (currentTick ? currentTick + 1 : 600);
      btnIcon.textContent = '📅';
      btnText.textContent = 'Schedule at Specific Tick';
    } else {
      customGroup.style.display = 'none';
      if (val === 'run_now') {
        btnIcon.textContent = '⚡';
        btnText.textContent = 'Run Now via Bot';
      } else if (val === 'next_tick') {
        btnIcon.textContent = '🎯';
        btnText.textContent = 'Queue for Next Tick (One-off)';
      } else {
        btnIcon.textContent = '⏱️';
        btnText.textContent = 'Save Recurring Schedule';
      }
    }
  }

  async function dispatchBotAction() {
    const sched = document.getElementById('bot-dispatch-schedule').value;
    if (sched === 'run_now') {
      await executeBotCommandNow();
    } else if (sched === 'next_tick') {
      await queueBotCommandForTick();
    } else {
      await saveScheduledTask(sched);
    }
  }

  async function executeBotCommandNow() {
    const tool = document.getElementById('bot-dispatch-tool').value;
    const argsRaw = document.getElementById('bot-dispatch-args').value.trim();
    if (!tool) {
      showToast("Please select a command to execute");
      return;
    }
    let args = {};
    try {
      args = argsRaw ? JSON.parse(argsRaw) : {};
    } catch(e) {
      showToast("Invalid JSON in arguments: " + e.message);
      return;
    }

    const box = document.getElementById('bot-logs-box');
    box.textContent += `\n[${new Date().toLocaleTimeString()}] ⚡ Dispatching immediate order: ${tool}(${JSON.stringify(args)})\n`;
    showToast(`Executing ${tool} via bot...`);

    try {
      const res = await fetch('/api/call', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ tool, arguments: args })
      });
      const data = await res.json();
      recordQuotaUsage(tool);
      if (data.success) {
        showToast(`✅ ${tool} executed successfully!`);
        box.textContent += `✅ [Result]: ` + JSON.stringify(data.result, null, 2) + `\n`;
      } else {
        showToast(`❌ Error: ${data.error}`);
        box.textContent += `❌ [Error]: ${data.error}\n`;
      }
      box.scrollTop = box.scrollHeight;
    } catch(e) {
      showToast("Failed to execute: " + e.message);
      box.textContent += `❌ [Exception]: ${e.message}\n`;
    }
  }

  async function queueBotCommandForTick() {
    const tool = document.getElementById('bot-dispatch-tool').value;
    const argsRaw = document.getElementById('bot-dispatch-args').value.trim();
    if (!tool) {
      showToast("Please select a command to queue");
      return;
    }
    let args = {};
    try {
      args = argsRaw ? JSON.parse(argsRaw) : {};
    } catch(e) {
      showToast("Invalid JSON in arguments: " + e.message);
      return;
    }

    try {
      const res = await fetch('/api/bot/queue_action', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ tool, arguments: args })
      });
      const data = await res.json();
      if (data.success) {
        showToast(`📋 Queued ${tool} for next game tick!`);
        renderBotQueue(data.queue || []);
      } else {
        showToast("Error queueing command: " + (data.error || "Unknown"));
      }
    } catch(e) {
      showToast("Failed to queue: " + e.message);
    }
  }

  async function saveScheduledTask(schedMode) {
    const tool = document.getElementById('bot-dispatch-tool').value;
    const argsRaw = document.getElementById('bot-dispatch-args').value.trim();
    if (!tool) {
      showToast("Please select a command to schedule");
      return;
    }
    let args = {};
    try {
      args = argsRaw ? JSON.parse(argsRaw) : {};
    } catch(e) {
      showToast("Invalid JSON in arguments: " + e.message);
      return;
    }

    let schedType = 'interval_ticks';
    let intervalTicks = 1;
    let targetTick = null;

    if (schedMode === 'every_tick') {
      schedType = 'every_tick';
      intervalTicks = 1;
    } else if (schedMode.startsWith('interval_')) {
      schedType = 'interval_ticks';
      intervalTicks = parseInt(schedMode.replace('interval_', '')) || 1;
    } else if (schedMode === 'custom_interval') {
      schedType = 'interval_ticks';
      intervalTicks = parseInt(document.getElementById('bot-custom-tick-val').value) || 2;
    } else if (schedMode === 'specific_tick') {
      schedType = 'specific_tick';
      targetTick = parseInt(document.getElementById('bot-custom-tick-val').value) || (currentTick + 1);
    }

    const task = {
      id: 'task_' + Date.now(),
      tool: tool,
      arguments: args,
      schedule_type: schedType,
      interval_ticks: intervalTicks,
      target_tick: targetTick,
      created_at: new Date().toLocaleTimeString(),
      enabled: true,
      last_executed_tick: -1
    };

    try {
      const res = await fetch('/api/bot/schedule_task', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ task })
      });
      const data = await res.json();
      if (data.success) {
        showToast(`⏰ Scheduled ${tool} (${formatScheduleDescription(task)})`);
        renderBotSchedules(data.schedules || []);
      } else {
        showToast("Error saving schedule: " + (data.error || "Unknown"));
      }
    } catch(e) {
      showToast("Failed to schedule: " + e.message);
    }
  }

  function formatScheduleDescription(task) {
    if (task.schedule_type === 'every_tick') return 'Every Tick (~30m)';
    if (task.schedule_type === 'specific_tick') return `Once at Tick ${task.target_tick}`;
    const n = task.interval_ticks || 1;
    const hours = (n * 0.5);
    return `Every ${n} Tick${n > 1 ? 's' : ''} (${hours}h)`;
  }

  async function loadBotSchedules() {
    try {
      const res = await fetch('/api/bot/schedules');
      const data = await res.json();
      if (data.success) {
        renderBotSchedules(data.schedules || []);
      }
    } catch(e) {}
  }

  function renderBotSchedules(schedules) {
    const list = document.getElementById('bot-schedules-list');
    if (!list) return;
    if (!schedules || schedules.length === 0) {
      list.innerHTML = '<span style="color: var(--text-dim);">No recurring schedules configured. Set an interval above to run tasks automatically.</span>';
      return;
    }
    list.innerHTML = '';
    schedules.forEach(task => {
      const card = document.createElement('div');
      card.style.display = 'flex';
      card.style.justifyContent = 'space-between';
      card.style.alignItems = 'center';
      card.style.padding = '0.5rem 0.6rem';
      card.style.borderBottom = '1px solid rgba(255,255,255,0.06)';
      card.style.gap = '0.5rem';

      const isActive = task.enabled !== false;
      const statusBadge = isActive
        ? '<span style="color: var(--green); font-size: 0.72rem;">● Active</span>'
        : '<span style="color: var(--text-dim); font-size: 0.72rem;">○ Paused</span>';

      const lastRun = task.last_executed_tick > 0 ? `Last: Tick ${task.last_executed_tick}` : 'Not run yet';

      card.innerHTML = `
        <div style="flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">
          <div style="display: flex; align-items: center; gap: 0.5rem;">
            ${statusBadge}
            <strong style="color: ${isActive ? 'var(--cyan)' : 'var(--text-dim)'};">${task.tool}</strong>
            <span class="badge" style="background: rgba(168, 85, 247, 0.15); color: #c084fc; border: 1px solid rgba(168, 85, 247, 0.3); font-size: 0.7rem; padding: 0.1rem 0.4rem;">
              ${formatScheduleDescription(task)}
            </span>
          </div>
          <div style="font-size: 0.72rem; color: var(--text-dim); margin-top: 0.15rem;">
            <span>${lastRun}</span> • <span style="font-family: var(--font-mono);">${JSON.stringify(task.arguments || {})}</span>
          </div>
        </div>
        <div style="display: flex; gap: 0.3rem;">
          <button class="btn-refresh" style="font-size: 0.7rem; padding: 0.2rem 0.5rem;" onclick="toggleBotSchedule('${task.id}')">
            ${isActive ? 'Pause' : 'Resume'}
          </button>
          <button class="btn-refresh" style="font-size: 0.7rem; padding: 0.2rem 0.5rem; color: #f87171; border-color: rgba(239, 68, 68, 0.3);" onclick="deleteBotSchedule('${task.id}')">
            Delete
          </button>
        </div>
      `;
      list.appendChild(card);
    });
  }

  async function toggleBotSchedule(id) {
    try {
      const res = await fetch('/api/bot/schedule_toggle', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id })
      });
      const data = await res.json();
      if (data.success) {
        showToast("Schedule status updated");
        renderBotSchedules(data.schedules || []);
      }
    } catch(e) {
      showToast("Error toggling schedule: " + e.message);
    }
  }

  async function deleteBotSchedule(id) {
    try {
      const res = await fetch('/api/bot/schedule_delete', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id })
      });
      const data = await res.json();
      if (data.success) {
        showToast("Schedule deleted");
        renderBotSchedules(data.schedules || []);
      }
    } catch(e) {
      showToast("Error deleting schedule: " + e.message);
    }
  }

  async function loadBotQueue() {
    try {
      const res = await fetch('/api/bot/queue');
      const data = await res.json();
      if (data.success) {
        renderBotQueue(data.queue || []);
      }
    } catch(e) {}
  }

  function renderBotQueue(queue) {
    const list = document.getElementById('bot-queued-orders-list');
    if (!list) return;
    if (!queue || queue.length === 0) {
      list.innerHTML = '<span style="color: var(--text-dim);">No specific orders queued. Staged orders will execute automatically on the next tick.</span>';
      return;
    }
    list.innerHTML = '';
    queue.forEach((item, idx) => {
      const row = document.createElement('div');
      row.style.display = 'flex';
      row.style.justifyContent = 'space-between';
      row.style.alignItems = 'center';
      row.style.padding = '0.35rem 0.6rem';
      row.style.borderBottom = '1px solid rgba(255,255,255,0.05)';
      row.style.color = '#a5f3fc';
      row.innerHTML = `
        <div>
          <span style="color: var(--yellow);">#${idx + 1}</span>
          <strong style="color: var(--cyan); margin-left: 0.3rem;">${item.tool}</strong>
          <span style="color: var(--text-dim); margin-left: 0.5rem; font-size: 0.75rem;">${JSON.stringify(item.arguments || {})}</span>
        </div>
        <span style="color: var(--text-dim); font-size: 0.72rem;">Queued at ${item.queued_at || 'now'}</span>
      `;
      list.appendChild(row);
    });
  }

  async function clearBotQueue() {
    try {
      const res = await fetch('/api/bot/queue_clear', { method: 'POST' });
      const data = await res.json();
      if (data.success) {
        showToast("Bot tick order queue cleared");
        renderBotQueue([]);
      }
    } catch(e) {
      showToast("Error clearing queue: " + e.message);
    }
  }

  async function refreshBotStatus() {
    try {
      const res = await fetch('/api/bot/status');
      const data = await res.json();
      const badge = document.getElementById('bot-status-badge');
      const desc = document.getElementById('bot-status-desc');
      const btnStart = document.getElementById('btn-bot-start');
      const btnStop = document.getElementById('btn-bot-stop');

      if (data.running) {
        badge.className = 'badge badge-read';
        badge.textContent = `● ACTIVE (PID: ${data.pid})`;
        badge.style.background = 'rgba(16, 185, 129, 0.2)';
        badge.style.borderColor = 'var(--green)';
        badge.style.color = 'var(--green)';
        
        const st = data.state || {};
        const lastTick = st.last_tick ? ` | Last Tick: ${st.last_tick}` : '';
        const acts = st.actions_last_tick !== undefined ? ` (${st.actions_last_tick} acts)` : '';
        desc.textContent = `Engine running autonomously${lastTick}${acts}`;
        
        if (btnStart) btnStart.disabled = true;
        if (btnStop) btnStop.disabled = false;
      } else {
        badge.className = 'badge badge-quota';
        badge.textContent = '○ STOPPED / IDLE';
        badge.style.background = 'rgba(100, 116, 139, 0.2)';
        badge.style.borderColor = 'rgba(255, 255, 255, 0.2)';
        badge.style.color = 'var(--text-dim)';
        desc.textContent = 'Bot process not running. Click Start or Step 1 Tick to execute.';
        
        if (btnStart) btnStart.disabled = false;
        if (btnStop) btnStop.disabled = true;
      }
    } catch(e) {
      console.error("Error fetching bot status:", e);
    }
  }

  async function startBot() {
    try {
      showToast("Starting autonomous bot engine...");
      const res = await fetch('/api/bot/start', { method: 'POST' });
      const json = await res.json();
      if (json.success) {
        showToast(json.alreadyRunning ? "Bot is already running!" : `Bot started (PID: ${json.pid})`);
        refreshBotStatus();
        setTimeout(fetchBotLogs, 1000);
      } else {
        showToast("Error starting bot: " + (json.error || "Unknown"));
      }
    } catch(e) {
      showToast("Failed to start bot: " + e.message);
    }
  }

  async function stopBot() {
    try {
      showToast("Stopping bot engine...");
      const res = await fetch('/api/bot/stop', { method: 'POST' });
      const json = await res.json();
      if (json.success) {
        showToast("Bot stopped successfully");
        refreshBotStatus();
        setTimeout(fetchBotLogs, 500);
      } else {
        showToast("Error stopping bot: " + (json.error || "Unknown"));
      }
    } catch(e) {
      showToast("Failed to stop bot: " + e.message);
    }
  }

  async function resetBotState() {
    if (!confirm("Are you sure you want to reset the bot state and clear logs? This will stop the bot if running and clear bot_state.json.")) {
      return;
    }
    try {
      showToast("Resetting bot state and clearing logs...");
      const res = await fetch('/api/bot/reset', { method: 'POST' });
      const json = await res.json();
      if (json.success) {
        showToast("Bot state and logs reset!");
        refreshBotStatus();
        fetchBotLogs();
      } else {
        showToast("Error resetting bot: " + (json.error || "Unknown"));
      }
    } catch(e) {
      showToast("Failed to reset: " + e.message);
    }
  }

  function toggleVpsGuide() {
    const el = document.getElementById('vps-guide-content');
    const icon = document.getElementById('vps-guide-toggle-icon');
    if (!el) return;
    if (el.style.display === 'none' || !el.style.display) {
      el.style.display = 'block';
      if (icon) icon.textContent = '[ Click to Collapse ▲ ]';
    } else {
      el.style.display = 'none';
      if (icon) icon.textContent = '[ Click to Expand ▼ ]';
    }
  }

  async function stepBot() {
    const box = document.getElementById('bot-logs-box');
    box.textContent = "[Running single tick evaluation cycle... please wait]\n";
    showToast("Executing 1 bot tick cycle...");
    try {
      const res = await fetch('/api/bot/step', { method: 'POST' });
      const json = await res.json();
      if (json.stdout) {
        box.textContent = json.stdout;
        if (json.stderr) box.textContent += "\nSTDERR:\n" + json.stderr;
      } else {
        box.textContent = JSON.stringify(json, null, 2);
      }
      box.scrollTop = box.scrollHeight;
      showToast(json.success ? "Single tick cycle completed!" : "Step completed with warnings/errors");
      refreshBotStatus();
    } catch(e) {
      showToast("Error during step: " + e.message);
      box.textContent = "Error executing step: " + e.message;
    }
  }

  function applyBotConfigToUI(c) {
    if (!c) return;
    document.getElementById('cfg-auto-claim').checked = c.auto_claim_missions ?? true;
    document.getElementById('cfg-auto-repair').checked = c.auto_repair_pds ?? true;
    document.getElementById('cfg-auto-construct').checked = c.auto_construct ?? true;
    document.getElementById('cfg-auto-research').checked = c.auto_research ?? true;
    document.getElementById('cfg-dry-run').checked = c.dry_run ?? false;
    document.getElementById('cfg-max-actions').value = c.max_actions_per_tick || 8;

    const cp = c.construction_priorities || [];
    document.getElementById('cfg-construction-prio').value = Array.isArray(cp) ? cp.join(', ') : cp;

    const rp = c.research_priorities || [];
    document.getElementById('cfg-research-prio').value = Array.isArray(rp) ? rp.join(', ') : rp;

    if (c.profile_name) {
      document.getElementById('cfg-profile-name').value = c.profile_name;
      const badge = document.getElementById('cfg-active-badge');
      if (badge) badge.textContent = `Profile: ${c.profile_name}`;
    }
  }

  async function loadBotConfig() {
    try {
      const res = await fetch('/api/bot/config');
      const json = await res.json();
      if (!json.success || !json.config) return;
      applyBotConfigToUI(json.config);
    } catch(e) {
      console.error("Error loading bot config:", e);
    }
  }

  async function loadProfilesList() {
    try {
      const res = await fetch('/api/bot/profiles');
      const json = await res.json();
      if (!json.success) return;

      const sel = document.getElementById('cfg-profile-select');
      const curVal = sel.value;
      sel.innerHTML = '<option value="">Choose Profile...</option>';
      for (const p of json.profiles || []) {
        const opt = document.createElement('option');
        opt.value = p;
        opt.textContent = p;
        sel.appendChild(opt);
      }

      if (json.active_profile) {
        sel.value = json.active_profile;
        document.getElementById('cfg-profile-name').value = json.active_profile;
        const badge = document.getElementById('cfg-active-badge');
        if (badge) badge.textContent = `Profile: ${json.active_profile}`;
        const bannerP = document.getElementById('banner-active-profile');
        if (bannerP) bannerP.textContent = json.active_profile;
      } else if (curVal) {
        sel.value = curVal;
      }

      const activeFileSpan = document.getElementById('cfg-active-filepath');
      if (activeFileSpan && json.active_path) {
        activeFileSpan.textContent = 'bot_config.json';
        activeFileSpan.title = json.active_path;
      }
      const locInfo = document.getElementById('cfg-save-location-info');
      if (locInfo && json.profiles_dir) {
        locInfo.innerHTML = `💾 Directory: <span style="color:#cbd5e1;">config_profiles/</span> &bull; Active: <span style="color:var(--cyan);">bot_config.json</span>`;
      }
    } catch(e) {
      console.error("Error loading profiles list:", e);
    }
  }

  async function onProfileSelectChange(name) {
    if (!name) return;
    document.getElementById('cfg-profile-name').value = name;
    try {
      const res = await fetch('/api/bot/profile_load', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name })
      });
      const json = await res.json();
      if (json.success && json.config) {
        applyBotConfigToUI(json.config);
        const badge = document.getElementById('cfg-active-badge');
        if (badge) badge.textContent = `Profile: ${name}`;
        const bannerP = document.getElementById('banner-active-profile');
        if (bannerP) bannerP.textContent = name;
        const locInfo = document.getElementById('cfg-save-location-info');
        if (locInfo) {
          locInfo.innerHTML = `✅ Loaded: <span style="color:#10b981;">config_profiles/${name}.json</span> &bull; Active: <span style="color:var(--cyan);">bot_config.json</span>`;
        }
        showToast(`Profile "${name}" loaded and activated!`);
      } else {
        showToast("Error loading profile: " + (json.error || "Unknown"));
      }
    } catch(e) {
      showToast("Error loading profile: " + e.message);
    }
  }

  function getBotConfigFromUI() {
    const cpText = document.getElementById('cfg-construction-prio').value;
    const rpText = document.getElementById('cfg-research-prio').value;
    const cp = cpText.split(',').map(s => s.trim()).filter(Boolean);
    const rp = rpText.split(',').map(s => s.trim()).filter(Boolean);
    const name = document.getElementById('cfg-profile-name').value.trim() || 'Custom Profile';

    return {
      enabled: true,
      profile_name: name,
      auto_claim_missions: document.getElementById('cfg-auto-claim').checked,
      auto_repair_pds: document.getElementById('cfg-auto-repair').checked,
      auto_construct: document.getElementById('cfg-auto-construct').checked,
      auto_research: document.getElementById('cfg-auto-research').checked,
      dry_run: document.getElementById('cfg-dry-run').checked,
      max_actions_per_tick: parseInt(document.getElementById('cfg-max-actions').value) || 8,
      construction_priorities: cp,
      research_priorities: rp
    };
  }

  async function saveNamedProfile() {
    const nameInput = document.getElementById('cfg-profile-name');
    const name = (nameInput.value || '').trim() || 'Custom Profile';
    const cfg = getBotConfigFromUI();
    cfg.profile_name = name;

    try {
      const res = await fetch('/api/bot/profile_save', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, config: cfg })
      });
      const json = await res.json();
      if (json.success) {
        showToast(`Saved & activated profile "${name}"!`);
        const locInfo = document.getElementById('cfg-save-location-info');
        if (locInfo) {
          locInfo.innerHTML = `💾 Saved: <span style="color:#10b981;">config_profiles/${name}.json</span> &bull; Active: <span style="color:var(--cyan);">bot_config.json</span>`;
        }
        await loadProfilesList();
      } else {
        showToast("Error saving profile: " + (json.error || "Unknown"));
      }
    } catch(e) {
      showToast("Error saving profile: " + e.message);
    }
  }

  async function deleteCurrentProfile() {
    const sel = document.getElementById('cfg-profile-select');
    const name = sel.value || document.getElementById('cfg-profile-name').value.trim();
    if (!name) {
      showToast("Please select a profile to delete.");
      return;
    }
    if (!confirm(`Are you sure you want to delete profile "${name}" from config_profiles/?`)) {
      return;
    }
    try {
      const res = await fetch('/api/bot/profile_delete', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name })
      });
      const json = await res.json();
      if (json.success) {
        showToast(`Profile "${name}" deleted.`);
        document.getElementById('cfg-profile-name').value = '';
        await loadProfilesList();
      } else {
        showToast("Error deleting profile: " + (json.error || "Unknown"));
      }
    } catch(e) {
      showToast("Error deleting profile: " + e.message);
    }
  }

  async function saveBotConfig() {
    const cfg = getBotConfigFromUI();
    try {
      const res = await fetch('/api/bot/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ config: cfg })
      });
      const json = await res.json();
      if (json.success) {
        showToast("Active bot configuration (bot_config.json) saved successfully!");
      } else {
        showToast("Error saving config: " + (json.error || "Unknown"));
      }
    } catch(e) {
      showToast("Error saving config: " + e.message);
    }
  }

  async function loadBotStrategy() {
    try {
      const res = await fetch('/api/bot/strategy');
      const json = await res.json();
      if (json.success && json.code !== undefined) {
        document.getElementById('bot-strategy-code').value = json.code;
      }
    } catch(e) {
      console.error("Error loading strategy:", e);
    }
  }

  async function saveBotStrategy() {
    const code = document.getElementById('bot-strategy-code').value;
    try {
      const res = await fetch('/api/bot/strategy', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code: code })
      });
      const json = await res.json();
      if (json.success) {
        showToast("Strategy script saved! Reloads automatically on next tick.");
      } else {
        showToast("Error saving strategy: " + (json.error || "Unknown"));
      }
    } catch(e) {
      showToast("Error saving strategy: " + e.message);
    }
  }

  const STRATEGY_TEMPLATES = {
    economy: `\"\"\"\nEconomic Expansion Strategy Hook\nFocuses on resource mining, prospect scans, and maximizing metal/crystal.\n\"\"\"\n\ndef on_tick(client, state, config, logger):\n    logger("🚀 [Custom Strategy] Running Economic Expansion Strategy...")\n    planet = state.get("planet", {}).get("data", {}) or {}\n    res = planet.get("resources", {}) or {}\n    logger(f"   Current reserves: Metal={res.get('metal', 0):,}, Crystal={res.get('crystal', 0):,}")\n`,
    fortress: `\"\"\"\nFortress Colony Strategy Hook\nPrioritizes planetary defenses (PDS), shield generators, and defense research.\n\"\"\"\n\ndef on_tick(client, state, config, logger):\n    logger("🛡️ [Custom Strategy] Running Fortress Turtle Defense Hook...")\n    pds = state.get("pds", {}).get("data", []) or []\n    built_pds = [p for p in pds if p.get("level", 0) > 0]\n    logger(f"   Active defense emplacements: {len(built_pds)}")\n`,
    armada: `\"\"\"\nArmada Factory Strategy Hook\nPrioritizes Shipyard infrastructure, Light/Medium ship manufacturing, and fleet readiness.\n\"\"\"\n\ndef on_tick(client, state, config, logger):\n    logger("⚔️ [Custom Strategy] Running Armada Factory Hook...")\n    planet = state.get("planet", {}).get("data", {}) or {}\n    ships = planet.get("ships", []) or []\n    logger(f"   Hangar ship count: {len(ships)}")\n`
  };

  async function loadStrategiesList() {
    try {
      const res = await fetch('/api/bot/strategies_list');
      const json = await res.json();
      if (!json.success) return;

      const sel = document.getElementById('strategy-script-select');
      const curVal = sel.value;
      sel.innerHTML = '<option value="">Select Script / Template...</option>';

      // Custom Strategy Scripts group
      const customGroup = document.createElement('optgroup');
      customGroup.label = '📁 Custom Strategy Scripts (custom_strategies/)';
      for (const s of json.strategies || []) {
        const opt = document.createElement('option');
        opt.value = s;
        opt.textContent = s;
        customGroup.appendChild(opt);
      }
      sel.appendChild(customGroup);

      // Starter Templates group
      const tplGroup = document.createElement('optgroup');
      tplGroup.label = '⚡ Starter Templates';
      const tpls = [
        { key: 'tpl:economy', label: 'Economic Expansion Template' },
        { key: 'tpl:fortress', label: 'Fortress Turtle Defense Template' },
        { key: 'tpl:armada', label: 'Armada Factory Template' }
      ];
      for (const t of tpls) {
        const opt = document.createElement('option');
        opt.value = t.key;
        opt.textContent = t.label;
        tplGroup.appendChild(opt);
      }
      sel.appendChild(tplGroup);

      if (curVal) sel.value = curVal;

      const locInfo = document.getElementById('strat-save-location-info');
      if (locInfo && json.strategies_dir) {
        locInfo.innerHTML = `💾 Directory: <span style="color:#cbd5e1;">custom_strategies/</span> &bull; Active: <span style="color:var(--cyan);">bot_strategy.py</span>`;
      }
    } catch(e) {
      console.error("Error loading strategies list:", e);
    }
  }

  async function onStrategyScriptChange(val) {
    if (!val) return;
    if (val.startsWith('tpl:')) {
      const tplKey = val.replace('tpl:', '');
      if (STRATEGY_TEMPLATES[tplKey]) {
        if (confirm(`Load "${tplKey}" starter template into the code editor?`)) {
          document.getElementById('bot-strategy-code').value = STRATEGY_TEMPLATES[tplKey];
          document.getElementById('strategy-script-name').value = `${tplKey}_custom.py`;
          const locInfo = document.getElementById('strat-save-location-info');
          if (locInfo) {
            locInfo.innerHTML = `⚡ Starter template loaded. Give it a name and click <span style="color:var(--cyan);">Save</span> to write to custom_strategies/`;
          }
          showToast(`Loaded ${tplKey} template into editor!`);
        }
      }
      return;
    }

    // It's a custom strategy file
    document.getElementById('strategy-script-name').value = val;
    try {
      const res = await fetch('/api/bot/strategy_load', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: val })
      });
      const json = await res.json();
      if (json.success && json.code !== undefined) {
        document.getElementById('bot-strategy-code').value = json.code;
        const locInfo = document.getElementById('strat-save-location-info');
        if (locInfo) {
          locInfo.innerHTML = `✅ Loaded: <span style="color:#10b981;">custom_strategies/${val}</span> &bull; Click "Save & Set Active" to deploy to bot_strategy.py`;
        }
        showToast(`Loaded strategy "${val}"!`);
      } else {
        showToast("Error loading strategy: " + (json.error || "Unknown"));
      }
    } catch(e) {
      showToast("Error loading strategy: " + e.message);
    }
  }

  async function saveNamedStrategyScript(setActive = false) {
    const nameInput = document.getElementById('strategy-script-name');
    let name = (nameInput.value || '').trim() || 'my_strategy.py';
    if (!name.endsWith('.py')) name += '.py';
    nameInput.value = name;

    const code = document.getElementById('bot-strategy-code').value;

    try {
      const res = await fetch('/api/bot/strategy_save', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, code, set_active: setActive })
      });
      const json = await res.json();
      if (json.success) {
        const locInfo = document.getElementById('strat-save-location-info');
        if (setActive) {
          showToast(`🚀 Strategy "${name}" saved & activated in bot_strategy.py!`);
          const bannerS = document.getElementById('banner-active-script');
          if (bannerS) bannerS.textContent = name;
          if (locInfo) {
            locInfo.innerHTML = `🚀 Active: <span style="color:#10b981;">custom_strategies/${name}</span> ➔ <span style="color:var(--cyan);">bot_strategy.py</span> (Live reloaded)`;
          }
        } else {
          showToast(`💾 Strategy "${name}" saved to custom_strategies/ library!`);
          if (locInfo) {
            locInfo.innerHTML = `💾 Saved: <span style="color:#10b981;">custom_strategies/${name}</span>`;
          }
        }
        await loadStrategiesList();
        document.getElementById('strategy-script-select').value = name;
      } else {
        showToast("Error saving strategy: " + (json.error || "Unknown"));
      }
    } catch(e) {
      showToast("Error saving strategy: " + e.message);
    }
  }

  async function deleteCurrentStrategyScript() {
    const sel = document.getElementById('strategy-script-select');
    const name = sel.value || document.getElementById('strategy-script-name').value.trim();
    if (!name || name.startsWith('tpl:')) {
      showToast("Please select a saved custom script to delete.");
      return;
    }
    if (!confirm(`Are you sure you want to delete "${name}" from custom_strategies/?`)) {
      return;
    }
    try {
      const res = await fetch('/api/bot/strategy_delete', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name })
      });
      const json = await res.json();
      if (json.success) {
        showToast(`Strategy script "${name}" deleted.`);
        document.getElementById('strategy-script-name').value = '';
        await loadStrategiesList();
      } else {
        showToast("Error deleting strategy: " + (json.error || "Unknown"));
      }
    } catch(e) {
      showToast("Error deleting strategy: " + e.message);
    }
  }

  async function fetchBotLogs() {
    try {
      const res = await fetch('/api/bot/logs');
      const json = await res.json();
      if (json.success && json.logs) {
        const box = document.getElementById('bot-logs-box');
        box.textContent = json.logs;
        const autoScroll = document.getElementById('bot-log-auto-scroll');
        if (autoScroll && autoScroll.checked) {
          box.scrollTop = box.scrollHeight;
        }
      }
    } catch(e) {
      console.error("Error fetching bot logs:", e);
    }
  }

  // Initial Load
  window.onload = () => {
    refreshDashboard();
    refreshBotStatus();
    // Auto-refresh telemetry every 30 seconds
    setInterval(refreshDashboard, 30000);
  };
</script>

</body>
</html>
"""


DEFAULT_HOST = "127.0.0.1"


def run_server(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT, open_browser: bool = True):
    global mcp_client
    mcp_client = PegasusMCPClient()

    server_address = (host, port)
    httpd = ThreadedHTTPServer(server_address, PegasusHandler)

    display_host = "localhost" if host in ("127.0.0.1", "0.0.0.0") else host
    url = f"http://{display_host}:{port}"
    print("=" * 60)
    print("🌌 PEGASUS GALAXY MCP CONTROL HUB GUI")
    print(f"🚀 Server running at: http://{host}:{port}")
    if host == "0.0.0.0":
        print("🌐 Remote VPS Mode: Accessible from any device with network access to this server")
    print("⚡ Real-time Telemetry • 67 MCP Commands • Ship Codex")
    print("Press Ctrl+C in terminal to stop.")
    print("=" * 60)

    if open_browser and host in ("127.0.0.1", "localhost"):
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping Pegasus MCP GUI server...")
    finally:
        httpd.server_close()
        if mcp_client:
            mcp_client.close()


def main():
    parser = argparse.ArgumentParser(description="Pegasus Galaxy MCP GUI Dashboard")
    parser.add_argument("--host", type=str, default=DEFAULT_HOST, help="Host to bind server (default: 127.0.0.1, use 0.0.0.0 for VPS)")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Port to bind server (default: 7890)")
    parser.add_argument("--no-browser", action="store_true", help="Do not automatically open browser")
    args = parser.parse_args()

    run_server(host=args.host, port=args.port, open_browser=not args.no_browser)


if __name__ == "__main__":
    main()
