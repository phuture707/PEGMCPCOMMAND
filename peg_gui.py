#!/usr/bin/env python3
"""
Pegasus Galaxy MCP GUI Dashboard & Command Hub
A complete interactive web-based GUI for Pegasus Galaxy MCP.
"""

import argparse
import datetime
import json
import os
import re
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
import peg_combat

DEFAULT_PORT = 7890
BASE_DIR = Path(__file__).parent.resolve()

# Global client and bot process references
mcp_client: Optional[PegasusMCPClient] = None
cached_tools: Optional[list] = None
cached_ships: Optional[list] = None
cached_constructions: Optional[list] = None
cached_research: Optional[list] = None
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

        if url_path == "/api/reference":
            global cached_constructions, cached_research
            try:
                if not cached_constructions:
                    cached_constructions = mcp_client.read_resource("pegasus://construction/definitions")
                if not cached_research:
                    cached_research = mcp_client.read_resource("pegasus://research/definitions")
                if not cached_ships:
                    cached_ships = mcp_client.read_resource("pegasus://ship/definitions")
                self._send_json({
                    "success": True,
                    "constructions": cached_constructions,
                    "research": cached_research,
                    "ships": cached_ships
                })
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

        # Combat Simulator Endpoints (GET)
        if url_path == "/api/combat/attacker_fleets":
            try:
                active_fleets_resp = mcp_client.call_tool("list_active_fleets") or {}
                planet_ships_resp = mcp_client.call_tool("get_planet_ships") or {}

                fleets = active_fleets_resp.get("data", []) if isinstance(active_fleets_resp, dict) else []
                raw_hangar = planet_ships_resp.get("data", {}) if isinstance(planet_ships_resp, dict) else {}
                hangar = {}
                if isinstance(raw_hangar, dict):
                    hangar = {k: int(v) for k, v in raw_hangar.items() if isinstance(v, (int, float))}
                elif isinstance(raw_hangar, list):
                    for item in raw_hangar:
                        if isinstance(item, dict):
                            sid = item.get("shipDefinitionId") or item.get("id")
                            qty = item.get("quantity") or item.get("count", 1)
                            if sid:
                                hangar[sid] = hangar.get(sid, 0) + int(qty)

                # Query Home Defense info (PDS, research, resources, asteroids)
                home_pds = {}
                try:
                    pds_resp = mcp_client.call_tool("list_pds") or {}
                    pds_list = pds_resp.get("data", []) if isinstance(pds_resp, dict) else []
                    for p in pds_list:
                        name = p.get("name")
                        lvl = p.get("currentLevel", 1)
                        if name:
                            home_pds[name] = lvl
                except Exception:
                    pass

                home_research = {"Hulls": 0, "ShipTechnology": 0, "PDS": 0}
                try:
                    res_resp = mcp_client.call_tool("get_planet_research") or {}
                    res_list = res_resp.get("data", []) if isinstance(res_resp, dict) else []
                    for r in res_list:
                        r_name = r.get("name", "")
                        lvl = r.get("currentLevel", 0)
                        if r_name == "Hulls":
                            home_research["Hulls"] = lvl
                        elif r_name == "Ship Technology":
                            home_research["ShipTechnology"] = lvl
                        elif r_name == "PDS":
                            home_research["PDS"] = lvl
                except Exception:
                    pass

                home_resources = {"metal": 0, "crystal": 0, "eonium": 0}
                home_asteroids = {"metalRoids": 0, "crystalRoids": 0, "eoniumRoids": 0}
                coords = "Unknown"
                try:
                    p_status = mcp_client.get_planet_status() or {}
                    p_data = p_status.get("data", {}) if isinstance(p_status, dict) else {}
                    home_resources["metal"] = p_data.get("metal", 0)
                    home_resources["crystal"] = p_data.get("crystal", 0)
                    home_resources["eonium"] = p_data.get("eonium", 0)
                    coords = p_data.get("coords", "Unknown")
                    ast_cnt = p_data.get("asteroidCount", 0)
                    # Even split if breakdown not given
                    home_asteroids = {
                        "metalRoids": ast_cnt // 3,
                        "crystalRoids": ast_cnt // 3,
                        "eoniumRoids": ast_cnt - (2 * (ast_cnt // 3))
                    }
                except Exception:
                    pass

                home_defense = {
                    "pds": home_pds,
                    "research": home_research,
                    "resources": home_resources,
                    "asteroids": home_asteroids,
                    "coords": coords,
                    "hangarShips": hangar
                }

                self._send_json({
                    "success": True,
                    "namedFleets": fleets,
                    "hangarShips": hangar,
                    "homeDefense": home_defense
                })
            except Exception as e:
                self._send_json({"success": False, "error": str(e)}, status=500)
            return

        if url_path == "/api/combat/scan_targets":
            try:
                scans_resp = mcp_client.call_tool("get_scan_history", {"limit": 100}) or {}
                scans = scans_resp.get("data", []) if isinstance(scans_resp, dict) else []

                # Build planetary metadata lookup from all scans in history
                planet_meta = {}
                for s in scans:
                    pid = s.get("targetPlanetId") or s.get("planetId")
                    if not pid:
                        continue
                    if pid not in planet_meta:
                        planet_meta[pid] = {"coords": "", "owner": "", "pds": {}, "research": {}, "resources": {}, "asteroids": {}}
                    r_raw = s.get("result", {})
                    if isinstance(r_raw, str):
                        try:
                            r = json.loads(r_raw)
                        except Exception:
                            r = {}
                    elif isinstance(r_raw, dict):
                        r = r_raw
                    else:
                        r = {}
                    if r.get("coords") and not planet_meta[pid]["coords"]:
                        planet_meta[pid]["coords"] = r["coords"]
                    if r.get("ownerPlayerId") and not planet_meta[pid]["owner"]:
                        planet_meta[pid]["owner"] = r["ownerPlayerId"]
                    if r.get("constructions") and not planet_meta[pid]["pds"]:
                        pds = {}
                        for cn in r.get("constructions", []):
                            name = cn.get("name", "")
                            if any(k in name.lower() for k in ["laser", "missile", "ion", "shield", "sensor"]):
                                pds[name] = cn.get("level", 0)
                        if pds:
                            planet_meta[pid]["pds"] = pds
                    if r.get("research") and not planet_meta[pid]["research"]:
                        res_tech = {}
                        for res_item in r.get("research", []):
                            rn = res_item.get("name", "")
                            if any(k in rn.lower() for k in ["hull", "pds", "ship tech", "engineering"]):
                                res_tech[rn] = res_item.get("level", 0)
                        if res_tech:
                            planet_meta[pid]["research"] = res_tech
                    if r.get("metal") is not None and not planet_meta[pid]["resources"]:
                        planet_meta[pid]["resources"] = {
                            "metal": int(r.get("metal", 0)),
                            "crystal": int(r.get("crystal", 0)),
                            "eonium": int(r.get("eonium", 0))
                        }
                    if r.get("asteroids") and not planet_meta[pid]["asteroids"]:
                        planet_meta[pid]["asteroids"] = r.get("asteroids")

                # Filter all scans that contain fleet, military, or docked ships data
                fleet_scan_types = {"DEEP_SCAN", "MILITARY_SCAN", "FLEET_COMPOSITION_SCAN", "INCOMING_SCAN"}
                fleet_scans = []
                for s in scans:
                    if s.get("status") != "success":
                        continue
                    st = s.get("scanType", "")
                    if st in fleet_scan_types:
                        fleet_scans.append(s)
                    else:
                        res_str = s.get("result", "")
                        if isinstance(res_str, dict):
                            if "ships" in res_str or "namedFleets" in res_str or "fleets" in res_str:
                                fleet_scans.append(s)
                        elif isinstance(res_str, str) and ('"ships"' in res_str or '"namedFleets"' in res_str or '"fleets"' in res_str):
                            fleet_scans.append(s)

                seen_scans = set()
                targets = []
                for s in fleet_scans:
                    t_id = s.get("targetPlanetId") or s.get("planetId")
                    tick = s.get("tick", 0)
                    st = s.get("scanType", "UNKNOWN")
                    # Deduplicate duplicate entries from the same tick and scan type on the same target
                    scan_key = (t_id, tick, st)
                    if scan_key in seen_scans:
                        continue
                    seen_scans.add(scan_key)

                    parsed = peg_combat.parse_scan_record(s, planet_lookup=planet_meta)
                    if parsed:
                        targets.append(parsed)

                self._send_json({"success": True, "targets": targets})
            except Exception as e:
                self._send_json({"success": False, "error": str(e)}, status=500)
            return

        if url_path == "/api/memory":
            try:
                keys = mcp_client.list_memory_keys()
                self._send_json({"success": True, "keys": keys})
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

        # Combat Simulator Endpoint (POST)
        if url_path == "/api/combat/simulate":
            try:
                atk_fleet = payload.get("attackerFleet", {})
                def_fleet = payload.get("defenderFleet", {})
                atk_fleets = payload.get("attackerFleets")
                def_fleets = payload.get("defenderFleets")
                def_pds = payload.get("defenderPds", {})
                atk_res = payload.get("attackerResearch", {})
                def_res = payload.get("defenderResearch", {})
                def_resources = payload.get("defenderResources", {})
                def_asteroids = payload.get("defenderAsteroids", {})
                max_rounds = int(payload.get("maxRounds", 1))

                sim_result = peg_combat.simulate_combat(
                    attacker_fleet=atk_fleet,
                    defender_fleet=def_fleet,
                    defender_pds=def_pds,
                    attacker_research=atk_res,
                    defender_research=def_res,
                    defender_resources=def_resources,
                    defender_asteroids=def_asteroids,
                    max_rounds=max_rounds,
                    attacker_fleets=atk_fleets,
                    defender_fleets=def_fleets
                )
                self._send_json({"success": True, "result": sim_result})
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

        if url_path == "/api/bot/queue_delete":
            idx = payload.get("index")
            cfg_file = BASE_DIR / "bot_config.json"
            cfg = {}
            if cfg_file.exists():
                try:
                    with open(cfg_file, "r", encoding="utf-8") as f:
                        cfg = json.load(f)
                except Exception:
                    pass
            q = cfg.get("queued_actions", [])
            if isinstance(idx, int) and 0 <= idx < len(q):
                q.pop(idx)
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
            raw_name = payload.get("name", "").strip() or "Custom Profile"
            name = re.sub(r"[^\w\s\-]", "", raw_name).strip() or "Custom Profile"
            cfg = payload.get("config", {})
            cfg["profile_name"] = name
            profiles_dir = BASE_DIR / "config_profiles"
            profiles_dir.mkdir(exist_ok=True)
            profile_file = (profiles_dir / f"{name}.json").resolve()
            if not str(profile_file).startswith(str(profiles_dir.resolve())):
                self._send_json({"success": False, "error": "Invalid profile name"}, status=400)
                return

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
            raw_name = payload.get("name", "").strip()
            name = re.sub(r"[^\w\s\-]", "", raw_name).strip()
            profiles_dir = (BASE_DIR / "config_profiles").resolve()
            profile_file = (profiles_dir / f"{name}.json").resolve()
            if not str(profile_file).startswith(str(profiles_dir)) or not profile_file.exists():
                self._send_json({"success": False, "error": f"Profile '{raw_name}' not found"}, status=404)
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
            raw_name = payload.get("name", "").strip()
            name = re.sub(r"[^\w\s\-]", "", raw_name).strip()
            profiles_dir = (BASE_DIR / "config_profiles").resolve()
            profile_file = (profiles_dir / f"{name}.json").resolve()
            if str(profile_file).startswith(str(profiles_dir)) and profile_file.exists():
                profile_file.unlink()
            self._send_json({"success": True})
            return

        if url_path == "/api/bot/strategy_save":
            raw_name = payload.get("name", "").strip() or "my_strategy"
            if raw_name.endswith(".py"):
                raw_name = raw_name[:-3]
            clean_name = re.sub(r"[^\w\-]", "", raw_name).strip() or "my_strategy"
            name = f"{clean_name}.py"
            code = payload.get("code", "")
            set_active = payload.get("set_active", True)
            strat_dir = (BASE_DIR / "custom_strategies").resolve()
            strat_dir.mkdir(exist_ok=True)
            script_file = (strat_dir / name).resolve()
            if not str(script_file).startswith(str(strat_dir)):
                self._send_json({"success": False, "error": "Invalid strategy file name"}, status=400)
                return

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
            raw_name = payload.get("name", "").strip()
            if raw_name.endswith(".py"):
                raw_name = raw_name[:-3]
            clean_name = re.sub(r"[^\w\-]", "", raw_name).strip()
            name = f"{clean_name}.py"
            strat_dir = (BASE_DIR / "custom_strategies").resolve()
            script_file = (strat_dir / name).resolve()
            if not str(script_file).startswith(str(strat_dir)) or not script_file.exists():
                self._send_json({"success": False, "error": f"Script '{raw_name}' not found"}, status=404)
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
            raw_name = payload.get("name", "").strip()
            if raw_name.endswith(".py"):
                raw_name = raw_name[:-3]
            clean_name = re.sub(r"[^\w\-]", "", raw_name).strip()
            name = f"{clean_name}.py"
            strat_dir = (BASE_DIR / "custom_strategies").resolve()
            script_file = (strat_dir / name).resolve()
            if str(script_file).startswith(str(strat_dir)) and script_file.exists():
                script_file.unlink()
            self._send_json({"success": True})
            return

        self.send_error(404, "Endpoint not found")


HTML_CONTENT = r"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Pegasus Galaxy v0.3 • MCP Control Hub</title>
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

    .sim-mode-btn {
      font-family: var(--font-display);
      font-size: 0.85rem;
      letter-spacing: 0.05em;
      padding: 0.4rem 0.9rem;
      background: rgba(255,255,255,0.05);
      border: 1px solid rgba(255,255,255,0.12);
      border-radius: 6px;
      color: var(--text-dim);
      cursor: pointer;
      transition: all 0.2s;
    }
    .sim-mode-btn:hover {
      color: var(--cyan);
      border-color: var(--cyan);
      background: rgba(0,229,255,0.08);
    }
    .sim-mode-btn.active {
      color: var(--cyan);
      border-color: var(--cyan);
      background: rgba(0,229,255,0.15);
      box-shadow: 0 0 12px rgba(0,229,255,0.25);
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
        <h1>Pegasus Galaxy <span style="font-size: 0.72rem; font-family: var(--font-mono); color: var(--cyan); border: 1px solid rgba(0, 229, 255, 0.45); background: rgba(0, 229, 255, 0.1); border-radius: 4px; padding: 0.15rem 0.45rem; vertical-align: middle; margin-left: 0.4rem; font-weight: 500; letter-spacing: 0.05em;">v0.3</span></h1>
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
    <button class="tab-btn active" onclick="switchTab('dashboard', this)">📊 Mission Control</button>
    <button class="tab-btn" onclick="switchTab('commands', this)">🛠️ Command Hub (67 Tools)</button>
    <button class="tab-btn" onclick="switchTab('missions', this)">🎯 Quests & Missions</button>
    <button class="tab-btn" onclick="switchTab('ships', this)">🚀 Hangar & Ship Codex</button>
    <button class="tab-btn" onclick="switchTab('reference', this)">📚 Game Codex & IDs</button>
    <button class="tab-btn" onclick="switchTab('bot', this)">🤖 Bot Studio</button>
    <button class="tab-btn" onclick="switchTab('memory', this)">🧠 Bot Memory</button>
    <button class="tab-btn" onclick="switchTab('battlecalc', this)">⚔️ Battle Simulator</button>
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
          <label class="form-label">Construction Priorities (click to add, drag to reorder):</label>
          <div id="cfg-construction-prio-selected" style="display: flex; flex-wrap: wrap; gap: 0.35rem; min-height: 32px; padding: 0.5rem; background: #030712; border: 1px solid rgba(0, 229, 255, 0.2); border-radius: 6px; margin-bottom: 0.4rem;"></div>
          <div id="cfg-construction-prio-available" style="display: flex; flex-wrap: wrap; gap: 0.3rem; padding: 0.4rem; background: rgba(0,0,0,0.2); border-radius: 6px;"></div>
          <input type="hidden" id="cfg-construction-prio" value="">
        </div>

        <div class="form-group">
          <label class="form-label">Research Priorities (click to add, drag to reorder):</label>
          <div id="cfg-research-prio-selected" style="display: flex; flex-wrap: wrap; gap: 0.35rem; min-height: 32px; padding: 0.5rem; background: #030712; border: 1px solid rgba(0, 229, 255, 0.2); border-radius: 6px; margin-bottom: 0.4rem;"></div>
          <div id="cfg-research-prio-available" style="display: flex; flex-wrap: wrap; gap: 0.3rem; padding: 0.4rem; background: rgba(0,0,0,0.2); border-radius: 6px;"></div>
          <input type="hidden" id="cfg-research-prio" value="">
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

      <!-- Controls Row 1: Tool Search + Command + Schedule -->
      <div style="display: grid; grid-template-columns: 2fr 2fr 1fr; gap: 1rem; margin-bottom: 0.85rem; align-items: flex-end;">
        <div class="form-group" style="margin-bottom: 0;">
          <label class="form-label">1. Select Game Command:</label>
          <input type="text" id="bot-dispatch-search" class="form-control" placeholder="🔍 Filter tools... (e.g. fleet, build, scan)" oninput="filterDispatchTools(this.value)" style="margin-bottom: 0.4rem; font-size: 0.8rem;">
          <select id="bot-dispatch-tool" class="form-control" onchange="onDispatchToolChange(this.value)">
            <option value="">Choose a command...</option>
          </select>
          <div id="bot-dispatch-tool-badge" style="margin-top: 0.3rem; font-size: 0.75rem;"></div>
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

      <!-- Controls Row 2: Smart Parameter Form -->
      <div class="form-group" style="margin-bottom: 0.6rem;">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.35rem;">
          <label class="form-label" style="margin-bottom: 0;">3. Command Parameters:</label>
          <button id="btn-toggle-raw-json" class="btn-refresh" style="font-size: 0.7rem; padding: 0.2rem 0.6rem;" onclick="toggleRawJsonMode()">
            📝 Switch to Raw JSON
          </button>
        </div>
        <div id="bot-dispatch-form" style="display: flex; flex-direction: column; gap: 0.6rem; padding: 0.75rem; background: rgba(0,0,0,0.25); border: 1px solid rgba(255,255,255,0.08); border-radius: 8px;">
          <span style="color: var(--text-dim); font-size: 0.82rem; font-family: var(--font-mono);">Select a command above to see its parameters...</span>
        </div>
        <textarea id="bot-dispatch-args" class="form-control" rows="4" style="display: none; width: 100%; box-sizing: border-box; font-family: var(--font-mono); font-size: 0.82rem; line-height: 1.4; background: #030712; color: #a5f3fc; border: 1px solid rgba(0, 229, 255, 0.25); resize: vertical;" placeholder='{"shipDefinitionId": "main-centurion", "quantity": 10}'>{}</textarea>
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

  <!-- TAB 6: Game Codex & IDs Reference -->
  <div id="tab-reference" class="tab-content">
    <div class="panel" style="margin-bottom: 1.5rem;">
      <div class="panel-header">
        <div class="panel-title">📚 Official Game Codex & ID Encyclopedia</div>
        <span class="badge badge-info">Exact Server Object IDs</span>
      </div>
      <p style="color: var(--text-dim); margin-bottom: 1rem; font-size: 0.92rem; line-height: 1.5;">
        Every building, research technology, defense battery, and ship in Pegasus Galaxy has a unique identifier required by MCP commands (e.g. <code style="color: var(--cyan);">constructionId</code>, <code style="color: var(--cyan);">researchId</code>, <code style="color: var(--cyan);">shipDefinitionId</code>). Click any ID badge or card button to copy it instantly or inject it into your Bot Studio queue!
      </p>

      <!-- Search and Filter Controls -->
      <div style="display: flex; gap: 0.75rem; flex-wrap: wrap; align-items: center; margin-bottom: 1rem;">
        <input type="text" id="ref-search-input" class="form-control" placeholder="🔍 Search by name, ID, category, or description..." style="flex: 1; min-width: 260px;" oninput="renderReferenceTab()">
        
        <div style="display: flex; gap: 0.35rem;">
          <button class="cat-pill active" id="ref-sub-all" style="padding: 0.35rem 0.8rem; font-size: 0.82rem;" onclick="setRefCategory('ALL')">All (71)</button>
          <button class="cat-pill" id="ref-sub-constructions" style="padding: 0.35rem 0.8rem; font-size: 0.82rem;" onclick="setRefCategory('CONSTRUCTIONS')">🏗️ Constructions (24)</button>
          <button class="cat-pill" id="ref-sub-research" style="padding: 0.35rem 0.8rem; font-size: 0.82rem;" onclick="setRefCategory('RESEARCH')">🔬 Research (12)</button>
          <button class="cat-pill" id="ref-sub-ships" style="padding: 0.35rem 0.8rem; font-size: 0.82rem;" onclick="setRefCategory('SHIPS')">🚀 Ships (35)</button>
        </div>
      </div>

      <div id="ref-stats-banner" style="font-family: var(--font-mono); font-size: 0.8rem; color: var(--text-dim);">
        Showing all game objects.
      </div>
    </div>

    <!-- Reference Grid Container -->
    <div id="reference-items-grid" style="display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 1rem;">
      <div style="color: var(--text-dim); font-family: var(--font-mono);">Loading Game Codex & IDs...</div>
    </div>
  </div>

  <!-- TAB 8: Battle Simulator & Fleet Calculator -->
  <div id="tab-battlecalc" class="tab-content">
    <div class="panel" style="margin-bottom: 1.5rem;">
      <div class="panel-header">
        <div class="panel-title">⚔️ Interstellar Fleet Battle Simulator</div>
        <span class="badge badge-warning">Simulated Combat Sandbox</span>
      </div>
      <p style="color: var(--text-dim); margin-bottom: 1rem; font-size: 0.92rem; line-height: 1.5;">
        Simulate tactical fleet engagements between your active named fleets and enemy targets extracted automatically from live fleet scans (Deep Scans, Military Scans, and Fleet Scans). Accurately predicts initiative firing order, target class prioritization, planetary shield absorption, EMP disruption, and plunder capacity.
      </p>
      <div style="display: flex; gap: 0.75rem; align-items: center; justify-content: space-between; flex-wrap: wrap;">
        <div style="display: flex; gap: 0.5rem; align-items: center; flex-wrap: wrap;">
          <div style="font-size: 0.85rem; font-weight: 600; color: var(--text-dim); margin-right: 0.25rem;">Simulation Mode:</div>
          <button id="sim-mode-assault-btn" class="sim-mode-btn active" onclick="setSimulationMode('assault')">
            ⚔️ Planetary Assault (User Attacks Enemy)
          </button>
          <button id="sim-mode-defense-btn" class="sim-mode-btn" onclick="setSimulationMode('defense')">
            🛡️ Home Base Defense (Enemy Attacks User)
          </button>
          <button class="btn-refresh" onclick="swapSimulatorSides()" title="Swap Attacker and Defender Sides" style="padding: 0.4rem 0.9rem; font-size: 0.85rem; margin-left: 0.25rem;">
            ⇄ Swap Sides
          </button>
        </div>
        <div style="display: flex; gap: 0.75rem; align-items: center;">
          <button class="btn-primary" onclick="loadCombatSimulator()" style="padding: 0.4rem 1rem; font-size: 0.85rem;">
            🔄 Refresh Fleets & Scans
          </button>
          <span id="combat-status-badge" style="font-family: var(--font-mono); font-size: 0.82rem; color: var(--text-dim);">
            Ready to simulate.
          </span>
        </div>
      </div>
    </div>

    <!-- Two-Column Army Setup Grid -->
    <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(350px, 1fr)); gap: 1.5rem; margin-bottom: 1.5rem;">
      
      <!-- ATTACKER PANEL (Cyan Accent) -->
      <div class="panel" style="border-top: 3px solid var(--cyan);">
        <div class="panel-header" style="display: flex; justify-content: space-between; align-items: center;">
          <div>
            <div class="panel-title" id="sim-atk-title" style="color: var(--cyan);">🚀 Attacker Forces (Coalition Fleets)</div>
            <div style="font-size: 0.75rem; color: var(--text-dim); margin-top: 0.15rem;">Multi-attacker coalition • Toggle, add, or edit fleets</div>
          </div>
          <div style="display: flex; gap: 0.4rem; align-items: center; flex-wrap: wrap;">
            <button class="btn-refresh" style="padding: 0.25rem 0.65rem; font-size: 0.8rem; font-weight: 600; color: var(--cyan); border-color: rgba(0,229,255,0.4);" onclick="addAttackerFleet()">
              + Add Fleet
            </button>
            <select id="sim-atk-add-scan-select" class="form-control" style="font-size: 0.78rem; padding: 0.22rem 0.5rem; max-width: 220px; border-color: rgba(128,216,255,0.4); color: #80d8ff; background: rgba(0,229,255,0.06);" onchange="onQuickAddScanSelect('atk', this)">
              <option value="">📡 Add from Scan...</option>
            </select>
            <button class="btn-refresh" style="padding: 0.25rem 0.65rem; font-size: 0.8rem; font-weight: 600; color: #80d8ff; border-color: rgba(128,216,255,0.4);" onclick="openScanPickerModal('atk')" title="Browse all scanned fleets to pick from">
              🔍 Browse Scans
            </button>
          </div>
        </div>

        <div id="sim-atk-fleet-summary" style="background: rgba(0,229,255,0.05); border: 1px solid rgba(0,229,255,0.2); border-radius: 6px; padding: 0.75rem; margin-bottom: 1rem; font-family: var(--font-mono); font-size: 0.82rem;">
          <div style="display: flex; justify-content: space-between; margin-bottom: 0.25rem;">
            <span>Active Fleets: <strong id="sim-atk-active-fleets-count" style="color: var(--cyan);">0</strong></span>
            <span>Total Ships: <strong id="sim-atk-total-ships" style="color: var(--cyan);">0</strong></span>
            <span>Est. Firepower: <strong id="sim-atk-total-dmg" style="color: var(--green);">0</strong></span>
          </div>
          <div style="display: flex; justify-content: space-between; margin-bottom: 0.25rem;">
            <span>Total Armor: <strong id="sim-atk-total-armor" style="color: var(--yellow);">0</strong></span>
            <span>Cargo Capacity: <strong id="sim-atk-total-cargo" style="color: var(--text-main);">0</strong></span>
          </div>
          <div style="display: flex; justify-content: space-between;">
            <span>Asteroid Cargo: <strong id="sim-atk-total-roids-cap" style="color: #69f0ae;">0 roids</strong></span>
          </div>
        </div>

        <!-- Research Tech -->
        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 0.75rem; margin-bottom: 1rem;">
          <div class="form-group">
            <label style="font-size: 0.8rem; color: var(--text-dim);">Hulls Tech (+5% Armor/lvl):</label>
            <input type="number" id="sim-atk-hulls" class="form-control" min="0" max="10" value="5">
          </div>
          <div class="form-group">
            <label style="font-size: 0.8rem; color: var(--text-dim);">Ship Tech Lvl:</label>
            <input type="number" id="sim-atk-shiptech" class="form-control" min="0" max="10" value="5">
          </div>
        </div>

        <!-- Multi-Fleet Cards Container -->
        <div id="sim-atk-fleets-container" style="display: flex; flex-direction: column; gap: 0.75rem;">
          <div style="color: var(--text-dim); font-size: 0.85rem; font-style: italic;">Loading attacker fleets...</div>
        </div>
      </div>

      <!-- DEFENDER PANEL (Red Accent) -->
      <div class="panel" style="border-top: 3px solid #ff5252;">
        <div class="panel-header" style="display: flex; justify-content: space-between; align-items: center;">
          <div>
            <div class="panel-title" id="sim-def-title" style="color: #ff5252;">🛡️ Defender Target (Enemy Planet & Coalition)</div>
            <div style="font-size: 0.75rem; color: var(--text-dim); margin-top: 0.15rem;">Planet garrison + allied defender fleets</div>
          </div>
          <div style="display: flex; gap: 0.4rem; align-items: center; flex-wrap: wrap;">
            <button class="btn-refresh" style="padding: 0.25rem 0.65rem; font-size: 0.8rem; font-weight: 600; color: #ff5252; border-color: rgba(255,82,82,0.4);" onclick="addDefenderFleet()">
              + Add Fleet
            </button>
            <select id="sim-def-add-scan-select" class="form-control" style="font-size: 0.78rem; padding: 0.22rem 0.5rem; max-width: 220px; border-color: rgba(255,138,128,0.4); color: #ff8a80; background: rgba(255,82,82,0.06);" onchange="onQuickAddScanSelect('def', this)">
              <option value="">📡 Add from Scan...</option>
            </select>
            <button class="btn-refresh" style="padding: 0.25rem 0.65rem; font-size: 0.8rem; font-weight: 600; color: #ff8a80; border-color: rgba(255,138,128,0.4);" onclick="openScanPickerModal('def')" title="Browse all scanned fleets to pick from">
              🔍 Browse Scans
            </button>
          </div>
        </div>

        <div class="form-group" style="margin-bottom: 0.75rem;">
          <label style="display: block; font-size: 0.85rem; font-weight: 600; color: var(--text-dim); margin-bottom: 0.35rem;">
            Select Scanned Target Planet:
          </label>
          <select id="sim-def-target" class="form-control" onchange="onTargetPlanetChange()" style="width: 100%;">
            <option value="">Loading scans...</option>
          </select>
        </div>

        <div id="sim-def-scan-details" style="background: rgba(255,82,82,0.06); border: 1px solid rgba(255,82,82,0.25); border-radius: 6px; padding: 0.75rem; margin-bottom: 1rem; font-family: var(--font-mono); font-size: 0.82rem; display: none;">
          <div style="display: flex; justify-content: space-between; margin-bottom: 0.35rem; flex-wrap: wrap; gap: 0.5rem;">
            <span>Target: <strong id="sim-def-coords" style="color: #ff5252;">Unknown</strong></span>
            <span>Type: <strong id="sim-def-type" style="color: var(--cyan);">---</strong></span>
            <span>Scan Tick: <strong id="sim-def-tick">---</strong></span>
          </div>
          <div style="color: var(--text-dim); font-size: 0.78rem; margin-bottom: 0.25rem;">
            Scanned Resources: <span id="sim-def-res-badge" style="color: var(--cyan);">0 Metal • 0 Crystal • 0 Eonium</span>
          </div>
          <div style="color: var(--text-dim); font-size: 0.78rem;">
            Scanned Asteroids: <span id="sim-def-roids-badge" style="color: #69f0ae;">0 Metal • 0 Crystal • 0 Eonium</span>
          </div>
        </div>

        <!-- PDS Planetary Defenses (Scattered only on Defended Base Planet) -->
        <div style="background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.08); border-radius: 6px; padding: 0.75rem; margin-bottom: 1rem;">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem;">
            <div>
              <span style="font-size: 0.82rem; font-weight: 600; color: #ff5252; text-transform: uppercase; letter-spacing: 0.05em;">
                Planetary Defense Structures (PDS)
              </span>
              <div style="font-size: 0.72rem; color: var(--text-dim);">Fixed base defenses on planet only — not shared with allied fleets</div>
            </div>
            <button class="btn-refresh" style="padding: 0.15rem 0.5rem; font-size: 0.75rem;" onclick="applyUserPdsToDefender()" title="Load your own live PDS levels">
              🛡️ Load My PDS
            </button>
          </div>
          <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 0.5rem; font-size: 0.82rem;">
            <label style="display: flex; align-items: center; gap: 0.4rem;">
              <input type="checkbox" id="sim-pds-shield-chk" checked>
              <span>🛡️ Shield Gen (Lvl <input type="number" id="sim-pds-shield-lvl" value="2" min="1" max="5" style="width: 38px; padding: 0.1rem; background: var(--bg-space); border: 1px solid rgba(255,255,255,0.2); color: #fff; border-radius: 3px;">)</span>
            </label>
            <label style="display: flex; align-items: center; gap: 0.4rem;">
              <input type="checkbox" id="sim-pds-ion-chk" checked>
              <span>⚡ Ion Cannon (Lvl <input type="number" id="sim-pds-ion-lvl" value="2" min="1" max="5" style="width: 38px; padding: 0.1rem; background: var(--bg-space); border: 1px solid rgba(255,255,255,0.2); color: #fff; border-radius: 3px;">)</span>
            </label>
            <label style="display: flex; align-items: center; gap: 0.4rem;">
              <input type="checkbox" id="sim-pds-silo-chk" checked>
              <span>🚀 Missile Silo (Lvl <input type="number" id="sim-pds-silo-lvl" value="2" min="1" max="5" style="width: 38px; padding: 0.1rem; background: var(--bg-space); border: 1px solid rgba(255,255,255,0.2); color: #fff; border-radius: 3px;">)</span>
            </label>
            <label style="display: flex; align-items: center; gap: 0.4rem;">
              <input type="checkbox" id="sim-pds-laser-chk" checked>
              <span>🔴 Laser Batt (Lvl <input type="number" id="sim-pds-laser-lvl" value="2" min="1" max="5" style="width: 38px; padding: 0.1rem; background: var(--bg-space); border: 1px solid rgba(255,255,255,0.2); color: #fff; border-radius: 3px;">)</span>
            </label>
          </div>
        </div>

        <!-- Multi-Fleet Cards Container -->
        <div id="sim-def-fleets-container" style="display: flex; flex-direction: column; gap: 0.75rem;">
          <div style="color: var(--text-dim); font-size: 0.85rem; font-style: italic;">Loading defender fleets...</div>
        </div>
      </div>
    </div>

    <!-- ACTION BAR -->
    <div style="background: rgba(10, 20, 36, 0.9); border: 1px solid var(--border-glow); border-radius: 8px; padding: 1.25rem; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 1rem; margin-bottom: 2rem;">
      <div style="display: flex; align-items: center; gap: 1rem;">
        <span style="font-size: 0.9rem; font-weight: 600;">Max Combat Rounds:</span>
        <select id="sim-max-rounds" class="form-control" style="width: 80px;">
          <option value="1" selected>1</option>
          <option value="3">3</option>
          <option value="6">6</option>
          <option value="10">10</option>
        </select>
      </div>

      <button class="btn-primary" onclick="runBattleSimulation()" style="padding: 0.75rem 2.2rem; font-size: 1.05rem; font-weight: 700; letter-spacing: 0.05em; background: linear-gradient(135deg, #00e5ff 0%, #0077b6 100%); box-shadow: 0 0 15px rgba(0,229,255,0.4);">
        ⚡ RUN BATTLE SIMULATION
      </button>
    </div>

    <!-- SIMULATION RESULTS (DASHBOARD) -->
    <div id="sim-results-container" style="display: none;"></div>
  </div>

  <!-- Footer -->
  <footer style="text-align: center; padding: 1.5rem 0 2rem; color: var(--text-dim); font-size: 0.78rem; font-family: var(--font-mono); border-top: 1px solid rgba(255,255,255,0.06); margin-top: 2rem;">
    <div>🌌 Pegasus Galaxy MCP Suite <strong style="color: var(--cyan);">v0.3</strong> • Cross-Platform (macOS / Linux / Windows)</div>
    <div style="margin-top: 0.35rem;">GitHub: <a href="https://github.com/phuture707/PEGMCPCOMMAND" target="_blank" style="color: var(--cyan); text-decoration: none;">phuture707/PEGMCPCOMMAND</a> • 67 Live MCP Tools • Streamable HTTP</div>
  </footer>
</div>

<!-- Scan Fleet Picker Modal -->
<div id="sim-scan-picker-modal" style="display: none; position: fixed; inset: 0; z-index: 9999; background: rgba(5, 7, 15, 0.85); backdrop-filter: blur(4px); align-items: center; justify-content: center; padding: 1.5rem;" onclick="if(event.target === this) closeScanPickerModal()">
  <div style="background: #0f1322; border: 1px solid rgba(0,229,255,0.3); border-radius: 8px; width: 100%; max-width: 720px; max-height: 85vh; display: flex; flex-direction: column; box-shadow: 0 10px 40px rgba(0,0,0,0.8);" onclick="event.stopPropagation()">
    <div style="padding: 1rem 1.25rem; border-bottom: 1px solid rgba(255,255,255,0.08); display: flex; justify-content: space-between; align-items: center;">
      <div>
        <div id="sim-picker-title" style="font-size: 1.05rem; font-weight: 700; color: var(--cyan); display: flex; align-items: center; gap: 0.5rem;">
          📡 Choose a Scanned Fleet to Add
        </div>
        <div id="sim-picker-subtitle" style="font-size: 0.78rem; color: var(--text-dim); margin-top: 0.2rem;">
          Select any scanned garrison or fleet from your recent intel to deploy into the coalition
        </div>
      </div>
      <button class="btn-refresh" style="font-size: 1.2rem; padding: 0.2rem 0.6rem; line-height: 1;" onclick="closeScanPickerModal()">✕</button>
    </div>

    <div style="padding: 0.75rem 1.25rem; border-bottom: 1px solid rgba(255,255,255,0.06);">
      <input type="text" id="sim-picker-search" class="form-control" placeholder="🔍 Filter by coords (e.g. 8:1:4), scan type (e.g. military, fleet), or ship..." style="font-size: 0.85rem;" oninput="renderScanPickerList()">
    </div>

    <div id="sim-picker-list" style="overflow-y: auto; padding: 1rem 1.25rem; display: flex; flex-direction: column; gap: 0.75rem; flex: 1;">
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

  function switchTab(tabId, btn) {
    try {
      document.querySelectorAll('.tabs .tab-btn').forEach(b => b.classList.remove('active'));
      document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
      
      const activeBtn = btn || (typeof event !== 'undefined' && event && event.currentTarget) || document.querySelector(`.tabs .tab-btn[onclick*="'${tabId}'"]`);
      if (activeBtn) activeBtn.classList.add('active');

      const targetTab = document.getElementById('tab-' + tabId);
      if (targetTab) targetTab.classList.add('active');
    } catch(err) {
      console.error("DOM tab activation error:", err);
    }

    // Auto-refresh when switching tabs (wrapped in try-catch so failure in one never blocks tab display)
    try {
      if (tabId === 'dashboard') refreshDashboard();
      if (tabId === 'commands' && allTools.length === 0) loadTools();
      if (tabId === 'missions') loadMissions();
      if (tabId === 'ships') loadShipsAndPds();
      if (tabId === 'reference') loadReferenceTab();
      if (tabId === 'bot') loadBotStudio();
      if (tabId === 'memory') loadMemory();
      if (tabId === 'battlecalc') loadCombatSimulator();
    } catch(err) {
      console.error("Tab data loading error for " + tabId + ":", err);
    }
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

  // --- Official Game Codex & IDs Reference Tab ---
  let refData = { constructions: [], research: [], ships: [] };
  let refCategory = 'ALL';

  async function loadReferenceTab() {
    const grid = document.getElementById('reference-items-grid');
    if (!refData.constructions.length && !refData.research.length && !refData.ships.length) {
      grid.innerHTML = '<div style="color: var(--text-dim); font-family: var(--font-mono);">Fetching all Game IDs from MCP server...</div>';
      try {
        const res = await fetch('/api/reference');
        const json = await res.json();
        if (json.success) {
          refData = {
            constructions: json.constructions || [],
            research: json.research || [],
            ships: json.ships || []
          };
        }
      } catch (e) {
        grid.innerHTML = `<div style="color: var(--red);">Error loading game reference data: ${e.message}</div>`;
        return;
      }
    }
    renderReferenceTab();
  }

  function setRefCategory(cat) {
    refCategory = cat;
    ['all', 'constructions', 'research', 'ships'].forEach(c => {
      const btn = document.getElementById('ref-sub-' + c);
      if (btn) btn.classList.toggle('active', c.toUpperCase() === cat);
    });
    renderReferenceTab();
  }

  function copyToClipboard(text, label) {
    navigator.clipboard.writeText(text).then(() => {
      showToast(`📋 Copied ${label || 'ID'}: "${text}"`);
    }).catch(() => {
      const temp = document.createElement('textarea');
      temp.value = text;
      document.body.appendChild(temp);
      temp.select();
      document.execCommand('copy');
      document.body.removeChild(temp);
      showToast(`📋 Copied: "${text}"`);
    });
  }

  function injectToBotQueue(toolName, argKey, objId) {
    switchTab('bot');
    const toolSelect = document.getElementById('bot-dispatch-tool');
    if (toolSelect) toolSelect.value = toolName;

    if (dispatchRawMode) {
      // Raw JSON mode fallback
      const argsInput = document.getElementById('bot-dispatch-args');
      if (argsInput) {
        if (toolName === 'produce_ships') {
          argsInput.value = JSON.stringify({ [argKey]: objId, quantity: 10 }, null, 2);
        } else {
          argsInput.value = JSON.stringify({ [argKey]: objId }, null, 2);
        }
      }
    } else {
      // Smart form mode — build form then pre-select dropdown value
      buildDispatchForm(toolName).then(() => {
        const paramEl = document.getElementById('dispatch-param-' + argKey);
        if (paramEl) paramEl.value = objId;
        // For produce_ships, also set quantity
        if (toolName === 'produce_ships') {
          const qtyEl = document.getElementById('dispatch-param-quantity');
          if (qtyEl) qtyEl.value = 10;
        }
      });
    }
    showToast(`⚡ Loaded "${objId}" into Bot Studio dispatcher (${toolName})`);
  }

  function renderReferenceTab() {
    const grid = document.getElementById('reference-items-grid');
    const searchVal = (document.getElementById('ref-search-input')?.value || '').toLowerCase().trim();
    const statsBanner = document.getElementById('ref-stats-banner');

    let items = [];

    if (refCategory === 'ALL' || refCategory === 'CONSTRUCTIONS') {
      refData.constructions.forEach(c => {
        items.push({
          type: 'CONSTRUCTION',
          typeLabel: '🏗️ Construction',
          id: c.id,
          name: c.name,
          category: c.category || 'Structure',
          description: c.description || '',
          metal: c.requiredMetal || 0,
          crystal: c.requiredCrystal || 0,
          eonium: c.requiredEonium || 0,
          points: c.requiredPoints || 0,
          prerequisites: c.prerequisites || [],
          toolName: c.category && c.category.toUpperCase().includes('DEFEN') ? 'repair_pds' : 'build_construction',
          argKey: 'constructionId'
        });
      });
    }

    if (refCategory === 'ALL' || refCategory === 'RESEARCH') {
      refData.research.forEach(r => {
        items.push({
          type: 'RESEARCH',
          typeLabel: '🔬 Research Tech',
          id: r.id,
          name: r.name,
          category: r.category || 'Technology',
          description: r.description || '',
          metal: r.requiredMetal || 0,
          crystal: r.requiredCrystal || 0,
          eonium: r.requiredEonium || 0,
          points: r.requiredPoints || 0,
          prerequisites: r.prerequisites || [],
          toolName: 'start_research',
          argKey: 'researchId'
        });
      });
    }

    if (refCategory === 'ALL' || refCategory === 'SHIPS') {
      refData.ships.forEach(s => {
        items.push({
          type: 'SHIP',
          typeLabel: '🚀 Ship Design',
          id: s.id,
          name: s.name,
          category: s.category || s.shipClass || 'Vessel',
          faction: s.faction || 'Neutral',
          description: s.description || '',
          metal: s.requiredMetal || 0,
          crystal: s.requiredCrystal || 0,
          eonium: s.requiredEonium || 0,
          points: s.requiredPoints || 0,
          prerequisites: s.prerequisites || [],
          toolName: 'produce_ships',
          argKey: 'shipDefinitionId'
        });
      });
    }

    // Apply text search
    if (searchVal) {
      items = items.filter(it => 
        it.id.toLowerCase().includes(searchVal) ||
        it.name.toLowerCase().includes(searchVal) ||
        it.category.toLowerCase().includes(searchVal) ||
        it.description.toLowerCase().includes(searchVal) ||
        (it.faction && it.faction.toLowerCase().includes(searchVal))
      );
    }

    if (statsBanner) {
      statsBanner.innerHTML = `Displaying <strong style="color: var(--cyan);">${items.length}</strong> matching game definitions (Category: ${refCategory}). Click any code snippet to copy to clipboard!`;
    }

    if (items.length === 0) {
      grid.innerHTML = '<div style="color: var(--yellow); font-family: var(--font-mono); grid-column: 1/-1; padding: 2rem; text-align: center;">No items matched your filter query.</div>';
      return;
    }

    grid.innerHTML = '';
    items.forEach(it => {
      const card = document.createElement('div');
      card.className = 'ship-card';
      card.style.display = 'flex';
      card.style.flexDirection = 'column';
      card.style.justifyContent = 'space-between';

      const typeColor = it.type === 'CONSTRUCTION' ? 'var(--blue)' : (it.type === 'RESEARCH' ? 'var(--purple)' : 'var(--cyan)');
      const badgeBorder = it.type === 'CONSTRUCTION' ? 'rgba(77, 157, 224, 0.3)' : (it.type === 'RESEARCH' ? 'rgba(168, 85, 247, 0.3)' : 'rgba(0, 229, 255, 0.3)');

      let prereqHtml = '';
      if (it.prerequisites && it.prerequisites.length > 0) {
        const pList = it.prerequisites.map(p => `<span style="background: rgba(255,255,255,0.06); padding: 0.15rem 0.4rem; border-radius: 4px; margin-right: 0.3rem;">${p.name || p.id} (Lvl ${p.minLevel || 1})</span>`).join(' ');
        prereqHtml = `<div style="font-family: var(--font-mono); font-size: 0.72rem; color: var(--text-dim); margin-bottom: 0.6rem;">Requires: ${pList}</div>`;
      }

      card.innerHTML = `
        <div>
          <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 0.4rem;">
            <div>
              <span style="font-size: 0.7rem; font-weight: 700; text-transform: uppercase; color: ${typeColor}; border: 1px solid ${badgeBorder}; background: rgba(0,0,0,0.3); padding: 0.15rem 0.5rem; border-radius: 4px; display: inline-block; margin-bottom: 0.3rem;">
                ${it.typeLabel} • ${it.category}
              </span>
              <div class="ship-name" style="font-size: 1.15rem;">${it.name}</div>
            </div>
          </div>

          <!-- Click-to-copy exact ID -->
          <div style="margin-bottom: 0.75rem;">
            <div style="font-size: 0.7rem; color: var(--text-dim); margin-bottom: 0.2rem; font-family: var(--font-mono);">EXACT SERVER ID:</div>
            <div onclick="copyToClipboard('${it.id}', 'Object ID')" title="Click to Copy ID" style="cursor: pointer; background: #030712; border: 1px solid rgba(0, 229, 255, 0.4); border-radius: 6px; padding: 0.4rem 0.6rem; display: flex; justify-content: space-between; align-items: center; transition: all 0.2s;">
              <code style="color: #a5f3fc; font-family: var(--font-mono); font-size: 0.85rem; font-weight: 700;">${it.id}</code>
              <span style="color: var(--cyan); font-size: 0.75rem;">📋 Copy</span>
            </div>
          </div>

          <p style="font-size: 0.82rem; color: var(--text-dim); margin-bottom: 0.75rem; line-height: 1.4;">${it.description || 'Standard galactic asset.'}</p>
          ${prereqHtml}
        </div>

        <div>
          <!-- Resource Costs -->
          <div style="font-family: var(--font-mono); font-size: 0.76rem; background: rgba(0,0,0,0.25); border-radius: 6px; padding: 0.45rem 0.6rem; margin-bottom: 0.75rem; display: flex; justify-content: space-between;">
            <span style="color: #94a3b8;">M: <strong style="color: #e2e8f0;">${formatNum(it.metal)}</strong></span>
            <span style="color: #94a3b8;">C: <strong style="color: #a5f3fc;">${formatNum(it.crystal)}</strong></span>
            <span style="color: #94a3b8;">E: <strong style="color: #e879f9;">${formatNum(it.eonium)}</strong></span>
          </div>

          <!-- Action Buttons -->
          <div style="display: flex; gap: 0.4rem;">
            <button class="btn-refresh" style="flex: 1; padding: 0.35rem 0.5rem; font-size: 0.75rem;" onclick="injectToBotQueue('${it.toolName}', '${it.argKey}', '${it.id}')">
              ⚡ Queue in Bot
            </button>
            <button class="btn-refresh" style="padding: 0.35rem 0.5rem; font-size: 0.75rem;" onclick="copyToClipboard('${it.id}', 'ID')">
              📋 ID
            </button>
          </div>
        </div>
      `;
      grid.appendChild(card);
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

  // Tool category definitions for optgroup grouping
  const TOOL_CATEGORIES = {
    '🏗️ Colony & Construction': ['build_construction', 'cancel_construction', 'list_construction_options', 'get_active_construction'],
    '🔬 Research & Technology': ['start_research', 'cancel_research', 'list_research_options', 'get_active_research', 'get_tech_tree'],
    '🚀 Fleet & Ships': ['produce_ships', 'launch_fleet', 'recall_fleet', 'list_active_fleets', 'list_incoming_fleets', 'get_planet_ships', 'list_production_options'],
    '🛡️ Defense & PDS': ['list_pds', 'repair_pds'],
    '🔭 Intelligence & Scanning': ['perform_scan', 'perform_wave_scan', 'get_radar_contacts', 'get_planet_intel'],
    '💰 Economy & Trade': ['get_planet_status', 'assign_population', 'trade_resources', 'search_asteroids', 'change_government', 'transfer_resources'],
    '🎁 Missions & Quests': ['list_missions', 'claim_missions'],
    '💬 Diplomacy & Social': ['send_message', 'list_messages', 'get_message', 'delete_message', 'create_alliance', 'list_alliances', 'join_alliance', 'leave_alliance', 'invite_to_alliance', 'kick_from_alliance', 'declare_war', 'accept_invite', 'decline_invite'],
    '📊 Leaderboard & Info': ['get_game_state_summary', 'get_tick_info', 'get_player_rank', 'get_leaderboard', 'get_game_rules', 'view_planet', 'get_battle_reports', 'view_battle_report'],
    '🧠 Memory': ['get_memory', 'set_memory', 'list_memory_keys']
  };

  // Known enum values for parameters that don't have enums in the schema
  const KNOWN_ENUMS = {
    'mission': ['ATTACK', 'DEFEND', 'SPY', 'TRADE', 'COLONIZE'],
    'scanType': ['SURFACE', 'DEEP'],
    'governmentType': ['democracy', 'dictatorship', 'communism', 'anarchy', 'technocracy'],
    'sourceResource': ['metal', 'crystal', 'eonium'],
    'targetResource': ['metal', 'crystal', 'eonium'],
    'role': ['miners', 'scientists', 'soldiers']
  };

  let dispatchRawMode = false;

  async function ensureRefData() {
    if (refData.constructions.length || refData.research.length || refData.ships.length) return;
    try {
      const res = await fetch('/api/reference');
      const json = await res.json();
      if (json.success) {
        refData = { constructions: json.constructions || [], research: json.research || [], ships: json.ships || [] };
      }
    } catch(e) {}
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
    const categorized = new Set();

    // Build optgroups from category definitions
    for (const [catName, toolNames] of Object.entries(TOOL_CATEGORIES)) {
      const catTools = toolNames
        .map(n => allTools.find(t => t.name === n))
        .filter(Boolean)
        .sort((a, b) => a.name.localeCompare(b.name));

      if (catTools.length === 0) continue;
      const group = document.createElement('optgroup');
      group.label = catName;
      for (const t of catTools) {
        const opt = document.createElement('option');
        opt.value = t.name;
        opt.textContent = `${t.name} — ${(t.description || '').substring(0, 50)}`;
        group.appendChild(opt);
        categorized.add(t.name);
      }
      sel.appendChild(group);
    }

    // Any uncategorized tools go into "Other"
    const uncategorized = allTools.filter(t => !categorized.has(t.name)).sort((a, b) => a.name.localeCompare(b.name));
    if (uncategorized.length > 0) {
      const group = document.createElement('optgroup');
      group.label = '📦 Other';
      for (const t of uncategorized) {
        const opt = document.createElement('option');
        opt.value = t.name;
        opt.textContent = `${t.name} — ${(t.description || '').substring(0, 50)}`;
        group.appendChild(opt);
      }
      sel.appendChild(group);
    }

    // Pre-load reference data
    ensureRefData();
  }

  function filterDispatchTools(query) {
    const sel = document.getElementById('bot-dispatch-tool');
    if (!sel) return;
    const q = query.toLowerCase().trim();
    for (const optgroup of sel.querySelectorAll('optgroup')) {
      let anyVisible = false;
      for (const opt of optgroup.querySelectorAll('option')) {
        const match = !q || opt.value.includes(q) || opt.textContent.toLowerCase().includes(q);
        opt.style.display = match ? '' : 'none';
        if (match) anyVisible = true;
      }
      optgroup.style.display = anyVisible ? '' : 'none';
    }
  }

  function toggleRawJsonMode() {
    dispatchRawMode = !dispatchRawMode;
    const form = document.getElementById('bot-dispatch-form');
    const textarea = document.getElementById('bot-dispatch-args');
    const btn = document.getElementById('btn-toggle-raw-json');

    if (dispatchRawMode) {
      // Switching to raw JSON — sync form values into textarea
      const args = collectDispatchArgs();
      textarea.value = JSON.stringify(args, null, 2);
      form.style.display = 'none';
      textarea.style.display = 'block';
      btn.textContent = '🔧 Switch to Smart Form';
    } else {
      // Switching back to form — rebuild form from current tool selection
      form.style.display = 'flex';
      textarea.style.display = 'none';
      btn.textContent = '📝 Switch to Raw JSON';
      const toolName = document.getElementById('bot-dispatch-tool').value;
      if (toolName) buildDispatchForm(toolName);
    }
  }

  function buildRefDropdown(paramKey, items, idField, nameField, extraFields) {
    let html = '<select id="dispatch-param-' + paramKey + '" class="form-control" style="font-size: 0.82rem;">';
    html += '<option value="">-- Select --</option>';
    for (const item of items) {
      const id = item[idField] || item.id || item.definitionId || '';
      const name = item[nameField] || item.name || id;
      let label = name;
      if (extraFields) {
        const extras = extraFields.map(f => item[f]).filter(Boolean).join(', ');
        if (extras) label += ' (' + extras + ')';
      }
      label += ' → ' + id;
      html += '<option value="' + id + '">' + label + '</option>';
    }
    html += '</select>';
    return html;
  }

  async function buildDispatchForm(toolName) {
    const container = document.getElementById('bot-dispatch-form');
    if (!container) return;
    const t = allTools.find(x => x.name === toolName);
    if (!t) {
      container.innerHTML = '<span style="color: var(--text-dim); font-size: 0.82rem; font-family: var(--font-mono);">Select a command above to see its parameters...</span>';
      return;
    }

    const schema = t.inputSchema || {};
    const props = schema.properties || {};
    const required = schema.required || [];
    const keys = Object.keys(props);

    // Show action/read badge
    const badgeEl = document.getElementById('bot-dispatch-tool-badge');
    if (badgeEl) {
      const isAction = /build|start|cancel|produce|assign|change|trade|search|initiate|repair|launch|recall|perform|send|create|join|leave|accept|invite|kick|declare|decline|claim|set|delete|transfer/.test(toolName);
      badgeEl.innerHTML = '<span class="badge ' + (isAction ? 'badge-action' : 'badge-read') + '" style="font-size: 0.72rem;">' +
        (isAction ? '⚠️ ACTION (Consumes Quota)' : '✨ READ (Free / Unlimited)') + '</span>' +
        '<span style="color: var(--text-dim); font-size: 0.72rem; margin-left: 0.5rem;">' + (t.description || '') + '</span>';
    }

    if (keys.length === 0) {
      container.innerHTML = '<span style="color: var(--green); font-size: 0.85rem; font-family: var(--font-mono);">✅ This command takes no parameters. Ready to execute.</span>';
      return;
    }

    await ensureRefData();
    let html = '';

    for (const k of keys) {
      const p = props[k];
      const isReq = required.includes(k);
      const reqMark = isReq ? ' <strong style="color: var(--red);">*</strong>' : '';
      const typeLabel = '<span style="color: var(--cyan);">(' + (p.type || 'any') + ')</span>';

      html += '<div class="form-group" style="margin-bottom: 0;">';
      html += '<label class="form-label" style="font-size: 0.78rem;">' + k + reqMark + ' ' + typeLabel + '</label>';

      // Check for reference-data-populated dropdowns
      if (k === 'constructionId' && refData.constructions.length) {
        html += buildRefDropdown(k, refData.constructions, 'definitionId', 'name', ['category']);
      } else if (k === 'shipDefinitionId' && refData.ships.length) {
        html += buildRefDropdown(k, refData.ships, 'definitionId', 'name', ['class', 'faction']);
      } else if (k === 'researchId' && refData.research.length) {
        html += buildRefDropdown(k, refData.research, 'definitionId', 'name', ['area']);
      } else if (p.enum && p.enum.length > 0) {
        // Schema-defined enum
        html += '<select id="dispatch-param-' + k + '" class="form-control" style="font-size: 0.82rem;">';
        html += '<option value="">-- Select --</option>';
        for (const v of p.enum) {
          html += '<option value="' + v + '">' + v + '</option>';
        }
        html += '</select>';
      } else if (KNOWN_ENUMS[k]) {
        // Known enum from our mapping
        html += '<select id="dispatch-param-' + k + '" class="form-control" style="font-size: 0.82rem;">';
        html += '<option value="">-- Select --</option>';
        for (const v of KNOWN_ENUMS[k]) {
          html += '<option value="' + v + '">' + v + '</option>';
        }
        html += '</select>';
      } else if (p.type === 'boolean') {
        html += '<select id="dispatch-param-' + k + '" class="form-control" style="font-size: 0.82rem;">';
        html += '<option value="false">false</option>';
        html += '<option value="true">true</option>';
        html += '</select>';
      } else if (p.type === 'number' || p.type === 'integer') {
        html += '<input type="number" id="dispatch-param-' + k + '" class="form-control" style="font-size: 0.82rem;" placeholder="' + (p.description || '') + '">';
      } else if (p.type === 'object' || p.type === 'array') {
        html += '<textarea id="dispatch-param-' + k + '" class="form-control" rows="2" style="font-family: var(--font-mono); font-size: 0.8rem; background: #030712; color: #a5f3fc;" placeholder="' + (p.description || 'JSON ' + p.type) + '"></textarea>';
      } else {
        html += '<input type="text" id="dispatch-param-' + k + '" class="form-control" style="font-size: 0.82rem;" placeholder="' + (p.description || '') + '">';
      }
      html += '</div>';
    }

    container.innerHTML = html;
  }

  function collectDispatchArgs() {
    const toolName = document.getElementById('bot-dispatch-tool').value;
    if (dispatchRawMode) {
      const raw = document.getElementById('bot-dispatch-args').value.trim();
      try { return raw ? JSON.parse(raw) : {}; }
      catch(e) { showToast('Invalid JSON: ' + e.message); return null; }
    }

    const t = allTools.find(x => x.name === toolName);
    if (!t) return {};
    const schema = t.inputSchema || {};
    const props = schema.properties || {};
    const args = {};

    for (const k of Object.keys(props)) {
      const el = document.getElementById('dispatch-param-' + k);
      if (!el) continue;
      const p = props[k];
      let val = (el.tagName === 'TEXTAREA') ? el.value.trim() : el.value;

      if (!val && val !== 0) continue; // skip empty optional fields

      if (p.type === 'number' || p.type === 'integer') {
        args[k] = Number(val);
      } else if (p.type === 'boolean') {
        args[k] = val === 'true';
      } else if (p.type === 'object' || p.type === 'array') {
        try { args[k] = JSON.parse(val); }
        catch(e) { showToast('Invalid JSON in ' + k + ': ' + e.message); return null; }
      } else {
        args[k] = val;
      }
    }
    return args;
  }

  function onDispatchToolChange(toolName) {
    if (!dispatchRawMode) {
      buildDispatchForm(toolName);
    } else {
      // In raw mode, generate sample JSON
      const input = document.getElementById('bot-dispatch-args');
      const t = allTools.find(x => x.name === toolName);
      if (t && t.inputSchema && t.inputSchema.properties) {
        const sample = {};
        for (let k of Object.keys(t.inputSchema.properties)) {
          const p = t.inputSchema.properties[k];
          if (p.type === 'number' || p.type === 'integer') sample[k] = 1;
          else if (p.type === 'boolean') sample[k] = false;
          else if (p.type === 'object') sample[k] = {};
          else sample[k] = '...';
        }
        input.value = JSON.stringify(sample, null, 2);
      } else {
        input.value = '{}';
      }
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
    if (!tool) {
      showToast("Please select a command to execute");
      return;
    }
    const args = collectDispatchArgs();
    if (args === null) return;

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
    if (!tool) {
      showToast("Please select a command to queue");
      return;
    }
    const args = collectDispatchArgs();
    if (args === null) return;

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
    if (!tool) {
      showToast("Please select a command to schedule");
      return;
    }
    const args = collectDispatchArgs();
    if (args === null) return;

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

  function summarizeArgs(args) {
    if (!args || Object.keys(args).length === 0) return '';
    const parts = [];
    for (const [k, v] of Object.entries(args)) {
      if (typeof v === 'object') parts.push(k + '=' + JSON.stringify(v));
      else parts.push(k + '=' + v);
    }
    return parts.join(', ');
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
      const argSummary = summarizeArgs(item.arguments);
      row.innerHTML = `
        <div style="flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">
          <span style="color: var(--yellow);">#${idx + 1}</span>
          <strong style="color: var(--cyan); margin-left: 0.3rem;">${item.tool}</strong>
          ${argSummary ? '<span style="color: var(--text-dim); margin-left: 0.5rem; font-size: 0.72rem;">' + argSummary + '</span>' : ''}
        </div>
        <div style="display: flex; align-items: center; gap: 0.4rem;">
          <span style="color: var(--text-dim); font-size: 0.7rem; white-space: nowrap;">${item.queued_at || 'now'}</span>
          <button class="btn-refresh" style="font-size: 0.68rem; padding: 0.15rem 0.4rem; color: #f87171; border-color: rgba(239,68,68,0.3);" onclick="deleteQueueItem(${idx})" title="Remove this order">✕</button>
        </div>
      `;
      list.appendChild(row);
    });
  }

  async function deleteQueueItem(idx) {
    try {
      const res = await fetch('/api/bot/queue_delete', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ index: idx })
      });
      const data = await res.json();
      if (data.success) {
        showToast("Removed queued order #" + (idx + 1));
        renderBotQueue(data.queue || []);
      }
    } catch(e) {
      showToast("Error removing order: " + e.message);
    }
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

  async function ensureRefData() {
    if (!refData.constructions.length && !refData.research.length && !refData.ships.length) {
      try {
        const res = await fetch('/api/reference');
        const json = await res.json();
        if (json.success) {
          refData = {
            constructions: json.constructions || [],
            research: json.research || [],
            ships: json.ships || []
          };
        }
      } catch (e) {
        console.error("Error loading reference data:", e);
      }
    }
    return refData;
  }

  // --- Priority Badge Picker ---
  function buildPriorityPicker(type) {
    // type is 'construction' or 'research'
    const selectedContainer = document.getElementById('cfg-' + type + '-prio-selected');
    const availableContainer = document.getElementById('cfg-' + type + '-prio-available');
    const hiddenInput = document.getElementById('cfg-' + type + '-prio');
    if (!selectedContainer || !availableContainer || !hiddenInput) return;

    const currentIds = hiddenInput.value.split(',').map(s => s.trim()).filter(Boolean);
    const items = type === 'construction' ? refData.constructions : refData.research;

    // If no ref data loaded yet, show a simple fallback
    if (!items || items.length === 0) {
      availableContainer.innerHTML = '<span style="color: var(--text-dim); font-size: 0.75rem;">Loading game data...</span>';
      return;
    }

    // Render selected badges (ordered)
    selectedContainer.innerHTML = '';
    if (currentIds.length === 0) {
      selectedContainer.innerHTML = '<span style="color: var(--text-dim); font-size: 0.75rem; font-family: var(--font-mono);">Click items below to add priorities...</span>';
    }
    currentIds.forEach((id, idx) => {
      const item = items.find(i => (i.definitionId || i.id) === id);
      const label = item ? (item.name || id) : id;
      const chip = document.createElement('span');
      chip.style.cssText = 'display: inline-flex; align-items: center; gap: 0.3rem; padding: 0.2rem 0.5rem; background: rgba(0, 229, 255, 0.15); border: 1px solid rgba(0, 229, 255, 0.4); border-radius: 4px; font-size: 0.72rem; color: #a5f3fc; cursor: default; font-family: var(--font-mono);';
      chip.innerHTML = '<span style="color: var(--yellow); font-size: 0.68rem;">#' + (idx + 1) + '</span> ' + label;
      // Move up button
      if (idx > 0) {
        const upBtn = document.createElement('span');
        upBtn.textContent = '↑';
        upBtn.style.cssText = 'cursor: pointer; color: var(--cyan); font-size: 0.7rem; margin-left: 0.1rem;';
        upBtn.onclick = () => { movePriority(type, idx, idx - 1); };
        chip.appendChild(upBtn);
      }
      // Move down button
      if (idx < currentIds.length - 1) {
        const downBtn = document.createElement('span');
        downBtn.textContent = '↓';
        downBtn.style.cssText = 'cursor: pointer; color: var(--cyan); font-size: 0.7rem;';
        downBtn.onclick = () => { movePriority(type, idx, idx + 1); };
        chip.appendChild(downBtn);
      }
      // Remove button
      const removeBtn = document.createElement('span');
      removeBtn.textContent = '×';
      removeBtn.style.cssText = 'cursor: pointer; color: #f87171; font-weight: bold; font-size: 0.8rem; margin-left: 0.15rem;';
      removeBtn.onclick = () => { removePriority(type, id); };
      chip.appendChild(removeBtn);
      selectedContainer.appendChild(chip);
    });

    // Render available badges (unselected)
    availableContainer.innerHTML = '';
    const remaining = items.filter(i => !currentIds.includes(i.definitionId || i.id));
    if (remaining.length === 0) {
      availableContainer.innerHTML = '<span style="color: var(--text-dim); font-size: 0.72rem;">All items added ✓</span>';
    }
    remaining.forEach(item => {
      const id = item.definitionId || item.id || '';
      const label = item.name || id;
      const badge = document.createElement('span');
      badge.style.cssText = 'display: inline-block; padding: 0.18rem 0.45rem; background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.12); border-radius: 4px; font-size: 0.72rem; color: var(--text-dim); cursor: pointer; font-family: var(--font-mono); transition: all 0.15s;';
      badge.textContent = '+ ' + label;
      badge.title = id;
      badge.onmouseenter = () => { badge.style.borderColor = 'rgba(0, 229, 255, 0.4)'; badge.style.color = '#a5f3fc'; };
      badge.onmouseleave = () => { badge.style.borderColor = 'rgba(255,255,255,0.12)'; badge.style.color = 'var(--text-dim)'; };
      badge.onclick = () => { addPriority(type, id); };
      availableContainer.appendChild(badge);
    });
  }

  function addPriority(type, id) {
    const input = document.getElementById('cfg-' + type + '-prio');
    const current = input.value.split(',').map(s => s.trim()).filter(Boolean);
    if (!current.includes(id)) {
      current.push(id);
      input.value = current.join(', ');
    }
    buildPriorityPicker(type);
  }

  function removePriority(type, id) {
    const input = document.getElementById('cfg-' + type + '-prio');
    const current = input.value.split(',').map(s => s.trim()).filter(Boolean);
    input.value = current.filter(x => x !== id).join(', ');
    buildPriorityPicker(type);
  }

  function movePriority(type, fromIdx, toIdx) {
    const input = document.getElementById('cfg-' + type + '-prio');
    const current = input.value.split(',').map(s => s.trim()).filter(Boolean);
    if (fromIdx < 0 || toIdx < 0 || fromIdx >= current.length || toIdx >= current.length) return;
    const item = current.splice(fromIdx, 1)[0];
    current.splice(toIdx, 0, item);
    input.value = current.join(', ');
    buildPriorityPicker(type);
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

    // Build priority pickers after setting values
    ensureRefData().then(() => {
      buildPriorityPicker('construction');
      buildPriorityPicker('research');
    });
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

// =========================================================================
// =========================================================================
  // ⚔️ BATTLE SIMULATOR & FLEET CALCULATOR SYSTEM (MULTI-FLEET COALITIONS)
  // =========================================================================
  let simAttackerData = { namedFleets: [], hangarShips: {} };
  let simScanTargets = [];
  let currentTargetScan = null;
  let currentSimMode = 'assault';
  let homeDefenseData = null;
  let simAttackerFleets = [];
  let simDefenderFleets = [];
  let simFleetSeq = 1;

  function formatScanType(type) {
    if (!type) return 'Scan';
    if (type === 'DEEP_SCAN') return 'Deep Scan';
    if (type === 'MILITARY_SCAN') return 'Military Scan';
    if (type === 'FLEET_COMPOSITION_SCAN') return 'Fleet Scan';
    if (type === 'INCOMING_SCAN') return 'Incoming Scan';
    if (type === 'SURFACE_SCAN') return 'Surface Scan';
    return type.replace('_SCAN', '').replace(/_/g, ' ');
  }

  async function loadCombatSimulator() {
    const badge = document.getElementById('combat-status-badge');
    badge.textContent = 'Fetching fleets & scans...';

    try {
      await ensureRefData();

      // 1. Fetch attacker fleets + home defense
      const atkRes = await fetch('/api/combat/attacker_fleets');
      const atkJson = await atkRes.json();
      if (atkJson.success) {
        simAttackerData = atkJson;
        homeDefenseData = atkJson.homeDefense || null;
      }

      // 2. Fetch fleet & planetary scan targets
      const scanRes = await fetch('/api/combat/scan_targets');
      const scanJson = await scanRes.json();
      if (scanJson.success) {
        simScanTargets = scanJson.targets || [];
        populateScanTargetsDropdown();
      }

      // Initialize default attacker fleet if none exists
      if (simAttackerFleets.length === 0) {
        initDefaultAttackerFleet();
      }

      // Initialize default defender fleet if none exists
      if (simDefenderFleets.length === 0) {
        initDefaultDefenderFleet();
      }

      renderAllFleetCards('atk');
      renderAllFleetCards('def');
      recalcCoalitionSummary('atk');

      const totalFleets = (simAttackerData.namedFleets || []).length;
      badge.textContent = `Ready (${totalFleets} fleet(s), ${simScanTargets.length} scan(s) loaded).`;
    } catch (e) {
      console.error("Combat simulator load error:", e);
      badge.textContent = 'Error loading combat data: ' + e.message;
    }
  }

  function initDefaultAttackerFleet() {
    let ships = {};
    let name = 'Primary Assault Fleet';
    let sourceVal = '__custom__';

    if (simAttackerData.namedFleets && simAttackerData.namedFleets.length > 0) {
      const f = simAttackerData.namedFleets[0];
      ships = Object.assign({}, f.ships || {});
      name = f.name || 'Primary Assault Fleet';
      sourceVal = 'fleet_0';
    } else if (simAttackerData.hangarShips && Object.keys(simAttackerData.hangarShips).length > 0) {
      ships = Object.assign({}, simAttackerData.hangarShips);
      name = 'Home Planet Hangar';
      sourceVal = '__hangar__';
    } else {
      ships = { 'main-vanguard-striker': 100 };
    }

    simAttackerFleets = [{
      id: 'atk_' + (simFleetSeq++),
      side: 'atk',
      name: name,
      enabled: true,
      sourceVal: sourceVal,
      ships: ships
    }];
  }

  function initDefaultDefenderFleet() {
    let ships = {};
    let name = 'Planet Garrison';
    let sourceVal = '__garrison__';

    if (currentTargetScan && currentTargetScan.garrisonShips && Object.keys(currentTargetScan.garrisonShips).length > 0) {
      ships = Object.assign({}, currentTargetScan.garrisonShips);
    } else {
      ships = { 'main-ashkari-fang': 100 };
      sourceVal = '__custom__';
    }

    simDefenderFleets = [{
      id: 'def_' + (simFleetSeq++),
      side: 'def',
      name: name,
      enabled: true,
      sourceVal: sourceVal,
      ships: ships
    }];
  }

  function setSimulationMode(mode) {
    currentSimMode = mode;
    const assaultBtn = document.getElementById('sim-mode-assault-btn');
    const defenseBtn = document.getElementById('sim-mode-defense-btn');

    if (mode === 'defense') {
      if (assaultBtn) assaultBtn.classList.remove('active');
      if (defenseBtn) defenseBtn.classList.add('active');

      const atkTitle = document.getElementById('sim-atk-title');
      const defTitle = document.getElementById('sim-def-title');
      if (atkTitle) { atkTitle.textContent = '🚀 Attacking Forces (Enemy Coalition Fleets)'; atkTitle.style.color = '#ff5252'; }
      if (defTitle) { defTitle.textContent = '🛡️ Defender Base (Your Empire Garrison & PDS)'; defTitle.style.color = 'var(--cyan)'; }

      applyUserPdsToDefender();

      if (homeDefenseData && homeDefenseData.hangarShips && simDefenderFleets.length > 0) {
        simDefenderFleets[0].ships = Object.assign({}, homeDefenseData.hangarShips);
        simDefenderFleets[0].name = 'Home Planet Garrison';
        simDefenderFleets[0].sourceVal = '__home_hangar__';
        renderAllFleetCards('def');
      }

      showToast('Switched to Home Defense Mode (Enemy attacking your base & PDS)');
    } else {
      if (assaultBtn) assaultBtn.classList.add('active');
      if (defenseBtn) defenseBtn.classList.remove('active');

      const atkTitle = document.getElementById('sim-atk-title');
      const defTitle = document.getElementById('sim-def-title');
      if (atkTitle) { atkTitle.textContent = '🚀 Attacker Forces (Coalition Fleets)'; atkTitle.style.color = 'var(--cyan)'; }
      if (defTitle) { defTitle.textContent = '🛡️ Defender Target (Enemy Planet & Garrison)'; defTitle.style.color = '#ff5252'; }

      if (currentTargetScan) {
        const pds = currentTargetScan.pds || {};
        setControlValue('sim-pds-shield-chk', 'checked', !!pds['Shield Generator']);
        if (pds['Shield Generator']) document.getElementById('sim-pds-shield-lvl').value = pds['Shield Generator'];
        setControlValue('sim-pds-ion-chk', 'checked', !!pds['Ion Cannon']);
        if (pds['Ion Cannon']) document.getElementById('sim-pds-ion-lvl').value = pds['Ion Cannon'];
        setControlValue('sim-pds-silo-chk', 'checked', !!pds['Missile Silo']);
        if (pds['Missile Silo']) document.getElementById('sim-pds-silo-lvl').value = pds['Missile Silo'];
        setControlValue('sim-pds-laser-chk', 'checked', !!pds['Laser Battery']);
        if (pds['Laser Battery']) document.getElementById('sim-pds-laser-lvl').value = pds['Laser Battery'];
      }

      showToast('Switched to Planetary Assault Mode (You attacking enemy target)');
    }
  }

  function swapSimulatorSides() {
    const tmp = simAttackerFleets;
    simAttackerFleets = simDefenderFleets;
    simDefenderFleets = tmp;

    simAttackerFleets.forEach(f => { f.side = 'atk'; });
    simDefenderFleets.forEach(f => { f.side = 'def'; });

    renderAllFleetCards('atk');
    renderAllFleetCards('def');
    recalcCoalitionSummary('atk');

    const newMode = currentSimMode === 'assault' ? 'defense' : 'assault';
    currentSimMode = newMode;
    const assaultBtn = document.getElementById('sim-mode-assault-btn');
    const defenseBtn = document.getElementById('sim-mode-defense-btn');

    if (newMode === 'defense') {
      if (assaultBtn) assaultBtn.classList.remove('active');
      if (defenseBtn) defenseBtn.classList.add('active');
      const atkTitle = document.getElementById('sim-atk-title');
      const defTitle = document.getElementById('sim-def-title');
      if (atkTitle) { atkTitle.textContent = '🚀 Attacking Forces (Enemy Coalition Fleets)'; atkTitle.style.color = '#ff5252'; }
      if (defTitle) { defTitle.textContent = '🛡️ Defender Base (Your Empire Garrison & PDS)'; defTitle.style.color = 'var(--cyan)'; }
      applyUserPdsToDefender();
    } else {
      if (assaultBtn) assaultBtn.classList.add('active');
      if (defenseBtn) defenseBtn.classList.remove('active');
      const atkTitle = document.getElementById('sim-atk-title');
      const defTitle = document.getElementById('sim-def-title');
      if (atkTitle) { atkTitle.textContent = '🚀 Attacker Forces (Coalition Fleets)'; atkTitle.style.color = 'var(--cyan)'; }
      if (defTitle) { defTitle.textContent = '🛡️ Defender Target (Enemy Planet & Garrison)'; defTitle.style.color = '#ff5252'; }
    }

    showToast('Sides inverted! Rosters and roles swapped.');
  }

  function applyUserPdsToDefender() {
    const pds = (homeDefenseData && homeDefenseData.pds) ? homeDefenseData.pds : {
      'Shield Generator': 5,
      'Laser Battery': 3,
      'Missile Silo': 3,
      'Ion Cannon': 3
    };

    setControlValue('sim-pds-shield-chk', 'checked', true);
    document.getElementById('sim-pds-shield-lvl').value = pds['Shield Generator'] || 5;

    setControlValue('sim-pds-ion-chk', 'checked', true);
    document.getElementById('sim-pds-ion-lvl').value = pds['Ion Cannon'] || 3;

    setControlValue('sim-pds-silo-chk', 'checked', true);
    document.getElementById('sim-pds-silo-lvl').value = pds['Missile Silo'] || 3;

    setControlValue('sim-pds-laser-chk', 'checked', true);
    document.getElementById('sim-pds-laser-lvl').value = pds['Laser Battery'] || 3;

    showToast('Loaded your live Planetary Defense Structures (PDS)');
  }

  function setControlValue(id, prop, val) {
    const el = document.getElementById(id);
    if (el) el[prop] = val;
  }

  function addAttackerFleet(presetVal) {
    const newIdx = simAttackerFleets.length + 1;
    let initialShips = { 'main-vanguard-striker': 100 };
    let initialName = `Attacker Fleet ${newIdx}`;
    let sourceVal = presetVal || '__custom__';

    if (presetVal && presetVal.startsWith('scan_')) {
      const parts = presetVal.split('_');
      const tIdx = parseInt(parts[1], 10);
      const target = (simScanTargets || [])[tIdx];
      if (target) {
        const coords = target.coords || `Target ${tIdx + 1}`;
        const typeLabel = formatScanType(target.scanType);
        if (parts[2] === 'garrison') {
          initialShips = Object.assign({}, target.garrisonShips || {});
          initialName = `[${typeLabel}] Garrison [${coords}]`;
        } else if (parts[2] === 'nf') {
          const nfIdx = parseInt(parts[3], 10);
          const nf = (target.namedFleets || [])[nfIdx];
          if (nf) {
            initialShips = Object.assign({}, nf.ships || {});
            initialName = `${nf.name || 'Fleet'} [${coords}]`;
          }
        }
      }
    }

    simAttackerFleets.push({
      id: 'atk_' + (simFleetSeq++),
      side: 'atk',
      name: initialName,
      enabled: true,
      sourceVal: sourceVal,
      ships: initialShips
    });
    renderAllFleetCards('atk');
    recalcCoalitionSummary('atk');
    showToast(`Added ${initialName}`);
  }

  function addDefenderFleet(presetVal) {
    const newIdx = simDefenderFleets.length + 1;
    let initialShips = { 'main-ashkari-fang': 100 };
    let initialName = `Defender Fleet ${newIdx}`;
    let sourceVal = presetVal || '__custom__';

    if (presetVal && presetVal.startsWith('scan_')) {
      const parts = presetVal.split('_');
      const tIdx = parseInt(parts[1], 10);
      const target = (simScanTargets || [])[tIdx];
      if (target) {
        const coords = target.coords || `Target ${tIdx + 1}`;
        const typeLabel = formatScanType(target.scanType);
        if (parts[2] === 'garrison') {
          initialShips = Object.assign({}, target.garrisonShips || {});
          initialName = `[${typeLabel}] Garrison [${coords}]`;
        } else if (parts[2] === 'nf') {
          const nfIdx = parseInt(parts[3], 10);
          const nf = (target.namedFleets || [])[nfIdx];
          if (nf) {
            initialShips = Object.assign({}, nf.ships || {});
            initialName = `${nf.name || 'Fleet'} [${coords}]`;
          }
        }
      }
    }

    simDefenderFleets.push({
      id: 'def_' + (simFleetSeq++),
      side: 'def',
      name: initialName,
      enabled: true,
      sourceVal: sourceVal,
      ships: initialShips
    });
    renderAllFleetCards('def');
    showToast(`Added ${initialName}`);
  }

  let currentPickerSide = 'atk';

  function openScanPickerModal(side) {
    currentPickerSide = side || 'atk';
    const modal = document.getElementById('sim-scan-picker-modal');
    if (!modal) return;

    const titleEl = document.getElementById('sim-picker-title');
    if (titleEl) {
      if (currentPickerSide === 'atk') {
        titleEl.textContent = '🚀 Choose a Scanned Fleet to Add to Attacker Coalition';
        titleEl.style.color = 'var(--cyan)';
      } else {
        titleEl.textContent = '🛡️ Choose a Scanned Fleet to Add to Defender Forces';
        titleEl.style.color = '#ff5252';
      }
    }

    const searchInput = document.getElementById('sim-picker-search');
    if (searchInput) searchInput.value = '';

    renderScanPickerList('');
    modal.style.display = 'flex';
  }

  function closeScanPickerModal() {
    const modal = document.getElementById('sim-scan-picker-modal');
    if (modal) modal.style.display = 'none';
  }

  function renderScanPickerList(query) {
    const container = document.getElementById('sim-picker-list');
    if (!container) return;
    container.innerHTML = '';

    const q = (query !== undefined ? query : (document.getElementById('sim-picker-search')?.value || '')).trim().toLowerCase();

    if (!simScanTargets || simScanTargets.length === 0) {
      container.innerHTML = '<div style="text-align: center; color: var(--text-dim); padding: 2rem;">No fleet scans found in scan history.</div>';
      return;
    }

    let matchCount = 0;

    simScanTargets.forEach((t, tIdx) => {
      const typeLabel = formatScanType(t.scanType);
      const coords = t.coords || `Target ${tIdx + 1}`;
      const tick = t.tick ? `Tick ${t.tick}` : '';
      const owner = (t.owner && t.owner !== 'Unknown') ? t.owner : '';
      const gShips = t.garrisonShips || {};
      const gTotal = Object.values(gShips).reduce((a, b) => a + (parseInt(b, 10) || 0), 0);
      const namedFleets = t.namedFleets || [];

      // Check search match
      const searchHaystack = `${typeLabel} ${coords} ${tick} ${owner} ${Object.keys(gShips).join(' ')} ${namedFleets.map(f => f.name + ' ' + Object.keys(f.ships||{}).join(' ')).join(' ')}`.toLowerCase();
      if (q && !searchHaystack.includes(q)) {
        return;
      }
      matchCount++;

      // Scan target card
      const card = document.createElement('div');
      card.style.background = 'rgba(255,255,255,0.03)';
      card.style.border = '1px solid rgba(255,255,255,0.08)';
      card.style.borderRadius = '6px';
      card.style.padding = '0.75rem';

      // Card Header
      const hdr = document.createElement('div');
      hdr.style.display = 'flex';
      hdr.style.justifyContent = 'space-between';
      hdr.style.alignItems = 'center';
      hdr.style.marginBottom = '0.5rem';
      hdr.style.flexWrap = 'wrap';
      hdr.style.gap = '0.4rem';

      const typeBadgeColor = t.scanType === 'FLEET_COMPOSITION_SCAN' ? '#80d8ff' : (t.scanType === 'MILITARY_SCAN' ? '#ffd600' : 'var(--cyan)');
      hdr.innerHTML = `
        <div>
          <span style="display: inline-block; font-size: 0.72rem; font-weight: 700; padding: 0.1rem 0.4rem; border-radius: 3px; background: rgba(255,255,255,0.08); color: ${typeBadgeColor}; border: 1px solid ${typeBadgeColor}40; margin-right: 0.4rem;">
            ${typeLabel}
          </span>
          <strong style="color: #fff; font-size: 0.9rem;">Planet [${coords}]</strong>
          <span style="color: var(--text-dim); font-size: 0.78rem; margin-left: 0.4rem;">(${tick}${owner ? ' • ' + owner : ''})</span>
        </div>
      `;
      card.appendChild(hdr);

      // Section: Garrison
      if (gTotal > 0 || namedFleets.length === 0) {
        const gRow = document.createElement('div');
        gRow.style.display = 'flex';
        gRow.style.justifyContent = 'space-between';
        gRow.style.alignItems = 'center';
        gRow.style.padding = '0.4rem 0.6rem';
        gRow.style.background = 'rgba(0,0,0,0.2)';
        gRow.style.borderRadius = '4px';
        gRow.style.marginBottom = '0.4rem';

        const shipNames = Object.entries(gShips).slice(0, 4).map(([sid, cnt]) => `${cnt}x ${sid.replace('main-', '').replace(/-/g, ' ')}`).join(', ');
        const extraShips = Object.keys(gShips).length > 4 ? ` +${Object.keys(gShips).length - 4} more` : '';

        gRow.innerHTML = `
          <div>
            <div style="font-weight: 600; font-size: 0.82rem; color: #fff;">🏛️ Planet Garrison (${gTotal.toLocaleString()} ships)</div>
            <div style="font-size: 0.74rem; color: var(--text-dim);">${shipNames || 'No ships'}${extraShips}</div>
          </div>
          <button class="btn-refresh" style="padding: 0.2rem 0.6rem; font-size: 0.78rem; font-weight: 600; color: ${currentPickerSide === 'atk' ? 'var(--cyan)' : '#ff5252'}; border-color: ${currentPickerSide === 'atk' ? 'rgba(0,229,255,0.4)' : 'rgba(255,82,82,0.4)'}; white-space: nowrap;" onclick="pickScanFleet('scan_${tIdx}_garrison')">
            + Add to ${currentPickerSide === 'atk' ? 'Attacker' : 'Defender'}
          </button>
        `;
        card.appendChild(gRow);
      }

      // Section: Named Fleets
      namedFleets.forEach((nf, nfIdx) => {
        const nfShips = nf.ships || {};
        const nfTotal = Object.values(nfShips).reduce((a, b) => a + (parseInt(b, 10) || 0), 0);
        const shipNames = Object.entries(nfShips).slice(0, 4).map(([sid, cnt]) => `${cnt}x ${sid.replace('main-', '').replace(/-/g, ' ')}`).join(', ');
        const extraShips = Object.keys(nfShips).length > 4 ? ` +${Object.keys(nfShips).length - 4} more` : '';

        const nfRow = document.createElement('div');
        nfRow.style.display = 'flex';
        nfRow.style.justifyContent = 'space-between';
        nfRow.style.alignItems = 'center';
        nfRow.style.padding = '0.4rem 0.6rem';
        nfRow.style.background = 'rgba(0,0,0,0.2)';
        nfRow.style.borderRadius = '4px';
        nfRow.style.marginBottom = '0.4rem';

        nfRow.innerHTML = `
          <div>
            <div style="font-weight: 600; font-size: 0.82rem; color: #fff;">🚀 Fleet "${nf.name || 'Unnamed'}" (${nfTotal.toLocaleString()} ships) [${nf.status || 'DOCKED'}]</div>
            <div style="font-size: 0.74rem; color: var(--text-dim);">${shipNames || 'No ships'}${extraShips}</div>
          </div>
          <button class="btn-refresh" style="padding: 0.2rem 0.6rem; font-size: 0.78rem; font-weight: 600; color: ${currentPickerSide === 'atk' ? 'var(--cyan)' : '#ff5252'}; border-color: ${currentPickerSide === 'atk' ? 'rgba(0,229,255,0.4)' : 'rgba(255,82,82,0.4)'}; white-space: nowrap;" onclick="pickScanFleet('scan_${tIdx}_nf_${nfIdx}')">
            + Add to ${currentPickerSide === 'atk' ? 'Attacker' : 'Defender'}
          </button>
        `;
        card.appendChild(nfRow);
      });

      container.appendChild(card);
    });

    if (matchCount === 0) {
      container.innerHTML = `<div style="text-align: center; color: var(--text-dim); padding: 2rem;">No scans matching "${escapeHtml(q)}".</div>`;
    }
  }

  function pickScanFleet(presetVal) {
    if (currentPickerSide === 'atk') {
      addAttackerFleet(presetVal);
    } else {
      addDefenderFleet(presetVal);
    }
    closeScanPickerModal();
  }

  function quickAddFleetFromScan(side) {
    openScanPickerModal(side);
  }

  function populateQuickScanAddDropdowns() {
    ['atk', 'def'].forEach(side => {
      const sel = document.getElementById(`sim-${side}-add-scan-select`);
      if (!sel) return;
      sel.innerHTML = '<option value="">📡 Add from Scan...</option>';

      if (!simScanTargets || simScanTargets.length === 0) {
        const opt = document.createElement('option');
        opt.value = '';
        opt.disabled = true;
        opt.textContent = 'No fleet scans in history';
        sel.appendChild(opt);
        return;
      }

      simScanTargets.forEach((t, tIdx) => {
        const typeLabel = formatScanType(t.scanType);
        const coords = t.coords || `Target ${tIdx + 1}`;
        const gShips = t.garrisonShips || {};
        const gTotal = Object.values(gShips).reduce((a, b) => a + (parseInt(b, 10) || 0), 0);

        // Garrison option
        const gOpt = document.createElement('option');
        gOpt.value = `scan_${tIdx}_garrison`;
        gOpt.textContent = `[${typeLabel}] [${coords}] Garrison (${gTotal.toLocaleString()} ships)`;
        sel.appendChild(gOpt);

        // Named fleets options
        (t.namedFleets || []).forEach((nf, nfIdx) => {
          const nfTotal = Object.values(nf.ships || {}).reduce((a, b) => a + (parseInt(b, 10) || 0), 0);
          const nfOpt = document.createElement('option');
          nfOpt.value = `scan_${tIdx}_nf_${nfIdx}`;
          nfOpt.textContent = `[${typeLabel}] [${coords}] Fleet "${nf.name || 'Unnamed'}" (${nfTotal.toLocaleString()} ships)`;
          sel.appendChild(nfOpt);
        });
      });
    });
  }

  function onQuickAddScanSelect(side, selectEl) {
    const val = selectEl.value;
    if (!val) return;
    if (side === 'atk') {
      addAttackerFleet(val);
    } else {
      addDefenderFleet(val);
    }
    selectEl.value = '';
  }

  function removeFleet(side, fleetId) {
    if (side === 'atk') {
      simAttackerFleets = simAttackerFleets.filter(f => f.id !== fleetId);
      renderAllFleetCards('atk');
      recalcCoalitionSummary('atk');
    } else {
      simDefenderFleets = simDefenderFleets.filter(f => f.id !== fleetId);
      renderAllFleetCards('def');
    }
    showToast('Fleet removed');
  }

  function onFleetToggle(side, fleetId, isChecked) {
    const list = (side === 'atk') ? simAttackerFleets : simDefenderFleets;
    const fleet = list.find(f => f.id === fleetId);
    if (!fleet) return;
    fleet.enabled = isChecked;

    const card = document.getElementById(`fleet-card-${fleetId}`);
    if (card) {
      if (isChecked) {
        card.style.opacity = '1';
        card.style.borderColor = (side === 'atk') ? 'rgba(0,229,255,0.3)' : 'rgba(255,82,82,0.3)';
        const lbl = card.querySelector('.fleet-status-label');
        if (lbl) { lbl.textContent = 'Active'; lbl.style.color = 'var(--green)'; }
      } else {
        card.style.opacity = '0.55';
        card.style.borderColor = 'rgba(255,255,255,0.06)';
        const lbl = card.querySelector('.fleet-status-label');
        if (lbl) { lbl.textContent = 'Disabled (Excluded)'; lbl.style.color = 'var(--text-dim)'; }
      }
    }
    if (side === 'atk') recalcCoalitionSummary('atk');
  }

  function onFleetNameChange(side, fleetId, newName) {
    const list = (side === 'atk') ? simAttackerFleets : simDefenderFleets;
    const fleet = list.find(f => f.id === fleetId);
    if (fleet) {
      fleet.name = newName.trim() || (side === 'atk' ? 'Attacker Fleet' : 'Defender Fleet');
    }
  }

  function onFleetPresetChange(side, fleetId, presetVal) {
    const list = (side === 'atk') ? simAttackerFleets : simDefenderFleets;
    const fleet = list.find(f => f.id === fleetId);
    if (!fleet) return;

    fleet.sourceVal = presetVal;
    let newShips = {};
    let suggestedName = '';

    if (presetVal === '__custom__') {
      return;
    } else if (presetVal.startsWith('scan_')) {
      const parts = presetVal.split('_');
      const tIdx = parseInt(parts[1], 10);
      const target = (simScanTargets || [])[tIdx];
      if (target) {
        const coords = target.coords || `Target ${tIdx + 1}`;
        const typeLabel = formatScanType(target.scanType);
        if (parts[2] === 'garrison') {
          newShips = Object.assign({}, target.garrisonShips || {});
          suggestedName = `[${typeLabel}] Garrison [${coords}]`;
        } else if (parts[2] === 'nf') {
          const nfIdx = parseInt(parts[3], 10);
          const nf = (target.namedFleets || [])[nfIdx];
          if (nf) {
            newShips = Object.assign({}, nf.ships || {});
            suggestedName = `${nf.name || 'Fleet'} [${coords}]`;
          }
        }
      }
    } else if (presetVal.startsWith('fleet_') || presetVal.startsWith('myfleet_')) {
      const idx = parseInt(presetVal.replace('myfleet_', '').replace('fleet_', ''), 10);
      const nf = (simAttackerData.namedFleets || [])[idx];
      if (nf) {
        newShips = Object.assign({}, nf.ships || {});
        suggestedName = nf.name || `Empire Fleet ${idx + 1}`;
      }
    } else if (presetVal === '__hangar__' || presetVal === '__my_hangar__' || presetVal === '__home_hangar__') {
      const h = (simAttackerData && simAttackerData.hangarShips) ? simAttackerData.hangarShips : (homeDefenseData ? homeDefenseData.hangarShips : {});
      newShips = Object.assign({}, h || {});
      suggestedName = 'Home Planet Hangar';
    } else if (presetVal === '__garrison__') {
      if (currentTargetScan) {
        newShips = Object.assign({}, currentTargetScan.garrisonShips || {});
        suggestedName = `Garrison [${currentTargetScan.coords || 'Target'}]`;
      }
    } else if (presetVal.startsWith('nf_')) {
      const idx = parseInt(presetVal.split('_')[1], 10);
      if (currentTargetScan && currentTargetScan.namedFleets) {
        const nf = currentTargetScan.namedFleets[idx];
        if (nf) {
          newShips = Object.assign({}, nf.ships || {});
          suggestedName = `${nf.name || 'Fleet'} [${currentTargetScan.coords || 'Target'}]`;
        }
      }
    }

    if (suggestedName) {
      fleet.name = suggestedName;
      const nameEl = document.getElementById(`fleet-name-${fleetId}`);
      if (nameEl) nameEl.value = fleet.name;
    }

    fleet.ships = newShips;

    const container = document.getElementById(`fleet-ships-${fleetId}`);
    if (container) {
      renderFleetShipRows(container, fleet, side);
    }
    updateFleetSubtotal(fleetId, side);
    if (side === 'atk') recalcCoalitionSummary('atk');
  }

  function addShipToFleet(side, fleetId) {
    const list = (side === 'atk') ? simAttackerFleets : simDefenderFleets;
    const fleet = list.find(f => f.id === fleetId);
    if (!fleet) return;

    const shipList = (typeof refData !== 'undefined' && refData && refData.ships && refData.ships.length > 0) ? refData.ships : [];
    const defaultShip = shipList.length > 0 ? shipList[0].id : (side === 'atk' ? 'main-vanguard-striker' : 'main-ashkari-fang');

    let shipToAdd = defaultShip;
    for (const s of shipList) {
      if (!fleet.ships[s.id]) {
        shipToAdd = s.id;
        break;
      }
    }

    fleet.ships[shipToAdd] = 100;
    const container = document.getElementById(`fleet-ships-${fleetId}`);
    if (container) {
      renderFleetShipRows(container, fleet, side);
    }
    updateFleetSubtotal(fleetId, side);
    if (side === 'atk') recalcCoalitionSummary('atk');
  }

  function removeShipFromFleet(side, fleetId, shipId) {
    const list = (side === 'atk') ? simAttackerFleets : simDefenderFleets;
    const fleet = list.find(f => f.id === fleetId);
    if (!fleet) return;

    delete fleet.ships[shipId];
    const container = document.getElementById(`fleet-ships-${fleetId}`);
    if (container) {
      renderFleetShipRows(container, fleet, side);
    }
    updateFleetSubtotal(fleetId, side);
    if (side === 'atk') recalcCoalitionSummary('atk');
  }

  function onShipRowChange(side, fleetId, oldShipId, newShipId, newCount) {
    const list = (side === 'atk') ? simAttackerFleets : simDefenderFleets;
    const fleet = list.find(f => f.id === fleetId);
    if (!fleet) return;

    if (oldShipId !== newShipId) {
      delete fleet.ships[oldShipId];
    }
    if (newCount > 0) {
      fleet.ships[newShipId] = newCount;
    } else {
      delete fleet.ships[newShipId];
    }

    updateFleetSubtotal(fleetId, side);
    if (side === 'atk') recalcCoalitionSummary('atk');
  }

  function renderAllFleetCards(side) {
    const container = document.getElementById(`sim-${side}-fleets-container`);
    if (!container) return;
    container.innerHTML = '';

    const list = (side === 'atk') ? simAttackerFleets : simDefenderFleets;
    if (list.length === 0) {
      container.innerHTML = `
        <div style="color: var(--text-dim); font-size: 0.85rem; font-style: italic; padding: 1.25rem; text-align: center; border: 1px dashed rgba(255,255,255,0.1); border-radius: 6px;">
          No fleets configured. Click <strong>"+ Add ${side === 'atk' ? 'Attacker' : 'Defender'} Fleet"</strong> above to deploy forces.
        </div>`;
      return;
    }

    list.forEach((fleet, idx) => {
      container.appendChild(buildFleetCardElement(fleet, side, idx));
    });
  }

  function buildFleetCardElement(fleet, side, idx) {
    const card = document.createElement('div');
    card.id = `fleet-card-${fleet.id}`;
    card.style.background = fleet.enabled ? 'rgba(255,255,255,0.03)' : 'rgba(0,0,0,0.3)';
    card.style.border = `1px solid ${fleet.enabled ? (side === 'atk' ? 'rgba(0,229,255,0.25)' : 'rgba(255,82,82,0.25)') : 'rgba(255,255,255,0.06)'}`;
    card.style.borderRadius = '6px';
    card.style.padding = '0.75rem';
    card.style.transition = 'all 0.2s ease';
    if (!fleet.enabled) {
      card.style.opacity = '0.55';
    }

    // Top Header: Toggle Checkbox, Editable Name, Delete button
    const header = document.createElement('div');
    header.style.display = 'flex';
    header.style.justifyContent = 'space-between';
    header.style.alignItems = 'center';
    header.style.gap = '0.5rem';
    header.style.marginBottom = '0.6rem';
    header.style.flexWrap = 'wrap';

    const toggleLabel = document.createElement('label');
    toggleLabel.style.display = 'flex';
    toggleLabel.style.alignItems = 'center';
    toggleLabel.style.gap = '0.35rem';
    toggleLabel.style.cursor = 'pointer';
    toggleLabel.style.fontSize = '0.82rem';
    toggleLabel.style.fontWeight = '700';

    const chk = document.createElement('input');
    chk.type = 'checkbox';
    chk.checked = fleet.enabled;
    chk.onchange = (e) => onFleetToggle(side, fleet.id, e.target.checked);

    const statusText = document.createElement('span');
    statusText.className = 'fleet-status-label';
    statusText.textContent = fleet.enabled ? 'Active' : 'Disabled (Excluded)';
    statusText.style.color = fleet.enabled ? 'var(--green)' : 'var(--text-dim)';

    toggleLabel.appendChild(chk);
    toggleLabel.appendChild(statusText);

    const nameInput = document.createElement('input');
    nameInput.id = `fleet-name-${fleet.id}`;
    nameInput.type = 'text';
    nameInput.className = 'form-control';
    nameInput.value = fleet.name;
    nameInput.style.flex = '1';
    nameInput.style.minWidth = '130px';
    nameInput.style.fontSize = '0.85rem';
    nameInput.style.fontWeight = '600';
    nameInput.style.padding = '0.2rem 0.5rem';
    nameInput.onchange = (e) => onFleetNameChange(side, fleet.id, e.target.value);

    const delBtn = document.createElement('button');
    delBtn.className = 'btn-refresh';
    delBtn.innerHTML = '🗑️ Remove';
    delBtn.style.color = '#ff5252';
    delBtn.style.fontSize = '0.78rem';
    delBtn.style.padding = '0.2rem 0.5rem';
    delBtn.onclick = () => removeFleet(side, fleet.id);

    header.appendChild(toggleLabel);
    header.appendChild(nameInput);
    header.appendChild(delBtn);
    card.appendChild(header);

    // Preset selector row
    const presetRow = document.createElement('div');
    presetRow.style.display = 'flex';
    presetRow.style.gap = '0.5rem';
    presetRow.style.alignItems = 'center';
    presetRow.style.marginBottom = '0.5rem';

    const presetLabel = document.createElement('span');
    presetLabel.style.fontSize = '0.75rem';
    presetLabel.style.color = 'var(--text-dim)';
    presetLabel.style.whiteSpace = 'nowrap';
    presetLabel.textContent = 'Load Preset:';

    const presetSel = document.createElement('select');
    presetSel.className = 'form-control';
    presetSel.style.fontSize = '0.78rem';
    presetSel.style.padding = '0.2rem 0.4rem';
    presetSel.style.flex = '1';
    populatePresetOptions(presetSel, side, fleet.sourceVal);
    presetSel.onchange = (e) => onFleetPresetChange(side, fleet.id, e.target.value);

    presetRow.appendChild(presetLabel);
    presetRow.appendChild(presetSel);
    card.appendChild(presetRow);

    // Ships list container
    const shipsContainer = document.createElement('div');
    shipsContainer.id = `fleet-ships-${fleet.id}`;
    shipsContainer.style.display = 'flex';
    shipsContainer.style.flexDirection = 'column';
    shipsContainer.style.gap = '0.35rem';
    shipsContainer.style.marginBottom = '0.5rem';
    card.appendChild(shipsContainer);

    renderFleetShipRows(shipsContainer, fleet, side);

    // Footer: Add Ship button & Subtotal text
    const footer = document.createElement('div');
    footer.style.display = 'flex';
    footer.style.justifyContent = 'space-between';
    footer.style.alignItems = 'center';
    footer.style.borderTop = '1px solid rgba(255,255,255,0.06)';
    footer.style.paddingTop = '0.4rem';

    const addShipBtn = document.createElement('button');
    addShipBtn.className = 'btn-refresh';
    addShipBtn.style.padding = '0.15rem 0.5rem';
    addShipBtn.style.fontSize = '0.75rem';
    addShipBtn.textContent = '+ Add Ship';
    addShipBtn.onclick = () => addShipToFleet(side, fleet.id);

    const subtotal = document.createElement('span');
    subtotal.id = `fleet-subtotal-${fleet.id}`;
    subtotal.style.fontSize = '0.75rem';
    subtotal.style.fontFamily = 'var(--font-mono)';
    subtotal.style.color = 'var(--text-dim)';

    footer.appendChild(addShipBtn);
    footer.appendChild(subtotal);
    card.appendChild(footer);

    setTimeout(() => updateFleetSubtotal(fleet.id, side), 0);
    return card;
  }

  function populatePresetOptions(sel, side, currentVal) {
    sel.innerHTML = '';

    // 1. Custom Manifest
    const customOpt = document.createElement('option');
    customOpt.value = '__custom__';
    customOpt.textContent = '✏️ Custom Manifest';
    if (currentVal === '__custom__') customOpt.selected = true;
    sel.appendChild(customOpt);

    // 2. Your Empire Forces (Available on both Attacker and Defender sides)
    const empireGrp = document.createElement('optgroup');
    empireGrp.label = '🏰 Your Empire Forces';

    const myFleets = (simAttackerData && simAttackerData.namedFleets) ? simAttackerData.namedFleets : [];
    myFleets.forEach((f, idx) => {
      const fTotal = Object.values(f.ships || {}).reduce((a, b) => a + (parseInt(b, 10) || 0), 0);
      const opt = document.createElement('option');
      opt.value = `fleet_${idx}`;
      opt.textContent = `Fleet "${f.name || 'Unnamed'}" (${fTotal.toLocaleString()} ships) [${f.status || 'ACTIVE'}]`;
      if (currentVal === opt.value) opt.selected = true;
      empireGrp.appendChild(opt);
    });

    const myHangar = (simAttackerData && simAttackerData.hangarShips) ? simAttackerData.hangarShips : (homeDefenseData ? homeDefenseData.hangarShips : {});
    const hangarTotal = Object.values(myHangar || {}).reduce((a, b) => a + (parseInt(b, 10) || 0), 0);
    const hangarOpt = document.createElement('option');
    hangarOpt.value = '__hangar__';
    hangarOpt.textContent = `🏠 Home Planet Hangar (${hangarTotal.toLocaleString()} ships)`;
    if (currentVal === '__hangar__' || currentVal === '__my_hangar__' || currentVal === '__home_hangar__') hangarOpt.selected = true;
    empireGrp.appendChild(hangarOpt);

    sel.appendChild(empireGrp);

    // 3. Recent Scanned Planets & Fleets (Available on BOTH Attacker and Defender sides!)
    if (simScanTargets && simScanTargets.length > 0) {
      simScanTargets.forEach((t, tIdx) => {
        const coords = t.coords || `Target ${tIdx + 1}`;
        const tick = t.tick ? `Tick ${t.tick}` : '';
        const owner = (t.owner && t.owner !== 'Unknown') ? ` • ${t.owner}` : '';
        const typeLabel = formatScanType(t.scanType);
        const scanGrp = document.createElement('optgroup');
        scanGrp.label = `📡 [${typeLabel}] [${coords}] (${tick}${owner})`;

        // Planet garrison / docked ships
        const gShips = t.garrisonShips || {};
        const gTotal = Object.values(gShips).reduce((a, b) => a + (parseInt(b, 10) || 0), 0);
        if (gTotal > 0 || (t.namedFleets || []).length === 0) {
          const gOpt = document.createElement('option');
          gOpt.value = `scan_${tIdx}_garrison`;
          gOpt.textContent = `Planet Garrison (${gTotal.toLocaleString()} ships)`;
          if (currentVal === gOpt.value || (side === 'def' && tIdx === 0 && currentVal === '__garrison__')) {
            gOpt.selected = true;
          }
          scanGrp.appendChild(gOpt);
        }

        // Named fleets at scanned planet
        (t.namedFleets || []).forEach((nf, nfIdx) => {
          const nfTotal = Object.values(nf.ships || {}).reduce((a, b) => a + (parseInt(b, 10) || 0), 0);
          const nfOpt = document.createElement('option');
          nfOpt.value = `scan_${tIdx}_nf_${nfIdx}`;
          nfOpt.textContent = `Fleet "${nf.name || 'Unnamed'}" (${nfTotal.toLocaleString()} ships)`;
          if (currentVal === nfOpt.value || (side === 'def' && tIdx === 0 && currentVal === `nf_${nfIdx}`)) {
            nfOpt.selected = true;
          }
          scanGrp.appendChild(nfOpt);
        });

        sel.appendChild(scanGrp);
      });
    }
  }

  function renderFleetShipRows(container, fleet, side) {
    container.innerHTML = '';
    const entries = Object.entries(fleet.ships || {});
    if (entries.length === 0) {
      container.innerHTML = '<div style="color: var(--text-dim); font-size: 0.8rem; font-style: italic; padding: 0.25rem 0;">No ships in fleet. Click "+ Add Ship" below.</div>';
      return;
    }

    entries.forEach(([shipId, count]) => {
      const row = document.createElement('div');
      row.style.display = 'flex';
      row.style.gap = '0.4rem';
      row.style.alignItems = 'center';
      row.style.background = 'rgba(255,255,255,0.02)';
      row.style.padding = '0.25rem 0.4rem';
      row.style.borderRadius = '4px';
      row.style.border = '1px solid rgba(255,255,255,0.05)';

      const sel = document.createElement('select');
      sel.className = 'form-control';
      sel.style.flex = '1';
      sel.style.fontSize = '0.8rem';
      sel.style.padding = '0.2rem 0.4rem';

      const shipList = (typeof refData !== 'undefined' && refData && refData.ships && refData.ships.length > 0) ? refData.ships : [];
      if (shipList.length > 0) {
        shipList.forEach(s => {
          const opt = document.createElement('option');
          opt.value = s.id;
          opt.textContent = `${s.name} (${s.category || s.shipClass || 'Ship'})`;
          if (s.id === shipId) opt.selected = true;
          sel.appendChild(opt);
        });
      } else {
        const opt = document.createElement('option');
        opt.value = shipId;
        opt.textContent = shipId;
        opt.selected = true;
        sel.appendChild(opt);
      }

      const countInput = document.createElement('input');
      countInput.type = 'number';
      countInput.className = 'form-control';
      countInput.value = count;
      countInput.min = '1';
      countInput.style.width = '80px';
      countInput.style.fontSize = '0.8rem';
      countInput.style.padding = '0.2rem 0.4rem';

      sel.onchange = () => {
        const newId = sel.value;
        const cnt = parseInt(countInput.value, 10) || 1;
        onShipRowChange(side, fleet.id, shipId, newId, cnt);
      };

      countInput.onchange = () => {
        const cnt = parseInt(countInput.value, 10) || 0;
        onShipRowChange(side, fleet.id, shipId, sel.value, cnt);
      };

      const delBtn = document.createElement('button');
      delBtn.className = 'btn-refresh';
      delBtn.innerHTML = '×';
      delBtn.style.color = '#ff5252';
      delBtn.style.padding = '0.15rem 0.4rem';
      delBtn.style.fontSize = '0.85rem';
      delBtn.onclick = () => removeShipFromFleet(side, fleet.id, shipId);

      row.appendChild(sel);
      row.appendChild(countInput);
      row.appendChild(delBtn);
      container.appendChild(row);
    });
  }

  function updateFleetSubtotal(fleetId, side) {
    const list = (side === 'atk') ? simAttackerFleets : simDefenderFleets;
    const fleet = list.find(f => f.id === fleetId);
    const subtotalEl = document.getElementById(`fleet-subtotal-${fleetId}`);
    if (!fleet || !subtotalEl) return;

    const totalShips = Object.values(fleet.ships || {}).reduce((a, b) => a + (parseInt(b, 10) || 0), 0);
    const shipList = (typeof refData !== 'undefined' && refData && refData.ships) ? refData.ships : [];
    const shipMap = {};
    shipList.forEach(s => { shipMap[s.id] = s; });

    let totalDmg = 0;
    for (const [sId, qty] of Object.entries(fleet.ships || {})) {
      const s = shipMap[sId];
      if (s) totalDmg += (s.damage || 0) * qty;
    }

    subtotalEl.textContent = `${totalShips.toLocaleString()} ships • Est. ${totalDmg > 0 ? totalDmg.toLocaleString() : '0'} Dmg`;
  }

  function recalcCoalitionSummary(side) {
    if (side !== 'atk') return;
    const activeFleets = simAttackerFleets.filter(f => f.enabled);
    const totalActiveCount = activeFleets.length;
    const totalShips = activeFleets.reduce((sum, f) => {
      return sum + Object.values(f.ships || {}).reduce((a, b) => a + (parseInt(b, 10) || 0), 0);
    }, 0);

    const activeFleetsCountEl = document.getElementById('sim-atk-active-fleets-count');
    if (activeFleetsCountEl) activeFleetsCountEl.textContent = `${totalActiveCount} / ${simAttackerFleets.length}`;

    const totalShipsEl = document.getElementById('sim-atk-total-ships');
    if (totalShipsEl) totalShipsEl.textContent = totalShips.toLocaleString();

    let totalDmg = 0;
    let totalArmor = 0;
    let totalCargo = 0;
    let totalRoidsCap = 0;

    const shipList = (typeof refData !== 'undefined' && refData && refData.ships) ? refData.ships : [];
    const shipMap = {};
    shipList.forEach(s => { shipMap[s.id] = s; });

    activeFleets.forEach(f => {
      for (const [sId, qty] of Object.entries(f.ships || {})) {
        const s = shipMap[sId];
        if (s) {
          totalDmg += (s.damage || 0) * qty;
          totalArmor += (s.armor || 0) * qty;
          totalCargo += (s.resourceCapacity || 0) * qty;
          totalRoidsCap += (s.asteroidCapacity || 0) * qty;
        }
      }
    });

    const dmgEl = document.getElementById('sim-atk-total-dmg');
    if (dmgEl) dmgEl.textContent = totalDmg > 0 ? totalDmg.toLocaleString() : '---';
    const armorEl = document.getElementById('sim-atk-total-armor');
    if (armorEl) armorEl.textContent = totalArmor > 0 ? totalArmor.toLocaleString() : '---';
    const cargoEl = document.getElementById('sim-atk-total-cargo');
    if (cargoEl) cargoEl.textContent = totalCargo > 0 ? totalCargo.toLocaleString() : '---';
    const roidsCapEl = document.getElementById('sim-atk-total-roids-cap');
    if (roidsCapEl) roidsCapEl.textContent = totalRoidsCap > 0 ? `${totalRoidsCap.toLocaleString()} roids` : '0 roids';
  }

  function collectFleetsData(side) {
    const list = (side === 'atk') ? simAttackerFleets : simDefenderFleets;
    return list.map(f => {
      const cleanShips = {};
      for (const [sId, cnt] of Object.entries(f.ships || {})) {
        const n = parseInt(cnt, 10);
        if (n > 0) cleanShips[sId] = n;
      }
      return {
        id: f.id,
        name: f.name || (side === 'atk' ? 'Attacker Fleet' : 'Defender Fleet'),
        enabled: !!f.enabled,
        ships: cleanShips
      };
    });
  }

  function populateScanTargetsDropdown() {
    const sel = document.getElementById('sim-def-target');
    sel.innerHTML = '<option value="">-- Select Scanned Enemy Target / Fleet --</option>';

    if (simScanTargets.length === 0) {
      const opt = document.createElement('option');
      opt.value = '__none__';
      opt.textContent = 'No fleet scans found in scan history';
      sel.appendChild(opt);
      return;
    }

    simScanTargets.forEach((t, idx) => {
      const typeLabel = formatScanType(t.scanType);
      const fleetCount = (t.namedFleets || []).length;
      const shipCount = Object.values(t.garrisonShips || {}).reduce((a, b) => a + (parseInt(b, 10) || 0), 0);
      const pdsCount = Object.keys(t.pds || {}).length;
      const opt = document.createElement('option');
      opt.value = idx;
      opt.textContent = `[${typeLabel}] Planet [${t.coords || '?'}] (Tick ${t.tick || '?'}) — ${shipCount.toLocaleString()} Garrison Ships, ${fleetCount} Fleets${pdsCount > 0 ? `, ${pdsCount} PDS` : ''}`;
      if (idx === 0) opt.selected = true;
      sel.appendChild(opt);
    });

    const customOpt = document.createElement('option');
    customOpt.value = '__custom__';
    customOpt.textContent = '✏️ Custom Enemy Defense';
    sel.appendChild(customOpt);

    onTargetPlanetChange();
    populateQuickScanAddDropdowns();
  }

  function onTargetPlanetChange() {
    const selVal = document.getElementById('sim-def-target').value;
    const scanCard = document.getElementById('sim-def-scan-details');

    if (selVal === '' || selVal === '__custom__' || selVal === '__none__') {
      currentTargetScan = null;
      if (scanCard) scanCard.style.display = 'none';
      renderAllFleetCards('def');
      return;
    }

    const idx = parseInt(selVal, 10);
    currentTargetScan = simScanTargets[idx];
    if (!currentTargetScan) return;

    if (scanCard) scanCard.style.display = 'block';
    const coordsEl = document.getElementById('sim-def-coords');
    if (coordsEl) coordsEl.textContent = currentTargetScan.coords || 'Unknown';
    const typeEl = document.getElementById('sim-def-type');
    if (typeEl) typeEl.textContent = formatScanType(currentTargetScan.scanType);
    const tickEl = document.getElementById('sim-def-tick');
    if (tickEl) tickEl.textContent = currentTargetScan.tick || '---';

    const res = currentTargetScan.resources || {};
    const resBadge = document.getElementById('sim-def-res-badge');
    if (resBadge) {
      if (res.metal || res.crystal || res.eonium) {
        resBadge.textContent = `${(res.metal || 0).toLocaleString()} Metal • ${(res.crystal || 0).toLocaleString()} Crystal • ${(res.eonium || 0).toLocaleString()} Eonium`;
      } else {
        resBadge.textContent = 'Not included in this scan type';
      }
    }

    const roids = currentTargetScan.asteroids || {};
    const roidsBadge = document.getElementById('sim-def-roids-badge');
    if (roidsBadge) {
      if (roids.metalRoids || roids.crystalRoids || roids.eoniumRoids) {
        roidsBadge.textContent = `${(roids.metalRoids || 0).toLocaleString()} Metal • ${(roids.crystalRoids || 0).toLocaleString()} Crystal • ${(roids.eoniumRoids || 0).toLocaleString()} Eonium`;
      } else {
        roidsBadge.textContent = 'Not included in this scan type';
      }
    }

    // Set PDS checkboxes and levels from scan (applied strictly to planet garrison only)
    const pds = currentTargetScan.pds || {};
    setControlValue('sim-pds-shield-chk', 'checked', !!pds['Shield Generator']);
    if (pds['Shield Generator']) document.getElementById('sim-pds-shield-lvl').value = pds['Shield Generator'];

    setControlValue('sim-pds-ion-chk', 'checked', !!pds['Ion Cannon']);
    if (pds['Ion Cannon']) document.getElementById('sim-pds-ion-lvl').value = pds['Ion Cannon'];

    setControlValue('sim-pds-silo-chk', 'checked', !!pds['Missile Silo']);
    if (pds['Missile Silo']) document.getElementById('sim-pds-silo-lvl').value = pds['Missile Silo'];

    setControlValue('sim-pds-laser-chk', 'checked', !!pds['Laser Battery']);
    if (pds['Laser Battery']) document.getElementById('sim-pds-laser-lvl').value = pds['Laser Battery'];

    // Update defender fleet presets
    if (simDefenderFleets.length > 0 && (simDefenderFleets[0].sourceVal === '__garrison__' || simDefenderFleets[0].sourceVal === '__custom__')) {
      simDefenderFleets[0].ships = Object.assign({}, currentTargetScan.garrisonShips || {});
      const typeLabel = formatScanType(currentTargetScan.scanType);
      simDefenderFleets[0].name = `[${typeLabel}] Garrison [${currentTargetScan.coords || 'Target'}]`;
      simDefenderFleets[0].sourceVal = '__garrison__';
    }

    renderAllFleetCards('def');
  }

  async function runBattleSimulation() {
    const statusBadge = document.getElementById('combat-status-badge');
    const resultsContainer = document.getElementById('sim-results-container');
    statusBadge.textContent = 'Simulating combat engagements...';
    resultsContainer.style.display = 'none';

    const atkFleets = collectFleetsData('atk');
    const defFleets = collectFleetsData('def');

    const totalActiveAtkShips = atkFleets.filter(f => f.enabled).reduce((tot, f) => {
      return tot + Object.values(f.ships).reduce((a, b) => a + (parseInt(b, 10) || 0), 0);
    }, 0);

    if (totalActiveAtkShips === 0) {
      showToast('Please enable at least one attacking fleet with ships');
      statusBadge.textContent = 'Simulation halted: No active attacking ships.';
      return;
    }

    // Collect PDS settings (applies strictly to base planet only)
    const pds = {};
    if (document.getElementById('sim-pds-shield-chk').checked) {
      pds['Shield Generator'] = parseInt(document.getElementById('sim-pds-shield-lvl').value, 10) || 1;
    }
    if (document.getElementById('sim-pds-ion-chk').checked) {
      pds['Ion Cannon'] = parseInt(document.getElementById('sim-pds-ion-lvl').value, 10) || 1;
    }
    if (document.getElementById('sim-pds-silo-chk').checked) {
      pds['Missile Silo'] = parseInt(document.getElementById('sim-pds-silo-lvl').value, 10) || 1;
    }
    if (document.getElementById('sim-pds-laser-chk').checked) {
      pds['Laser Battery'] = parseInt(document.getElementById('sim-pds-laser-lvl').value, 10) || 1;
    }

    let atkResearch = {
      Hulls: parseInt(document.getElementById('sim-atk-hulls').value, 10) || 0,
      ShipTechnology: parseInt(document.getElementById('sim-atk-shiptech').value, 10) || 0
    };
    let defResearch = { Hulls: 5, PDS: 5 };
    let defResources = {};
    let defAsteroids = {};

    if (currentSimMode === 'defense' && homeDefenseData) {
      defResearch = homeDefenseData.research || { Hulls: 5, PDS: 5 };
      defResources = homeDefenseData.resources || {};
      defAsteroids = homeDefenseData.asteroids || {};
      if (currentTargetScan && currentTargetScan.research) {
        atkResearch = currentTargetScan.research;
      }
    } else {
      defResearch = currentTargetScan ? currentTargetScan.research : { Hulls: 5, PDS: 5 };
      defResources = currentTargetScan ? currentTargetScan.resources : {};
      defAsteroids = currentTargetScan ? (currentTargetScan.asteroids || {}) : {};
    }

    const payload = {
      attackerFleets: atkFleets,
      defenderFleets: defFleets,
      defenderPds: pds,
      attackerResearch: atkResearch,
      defenderResearch: defResearch,
      defenderResources: defResources,
      defenderAsteroids: defAsteroids,
      maxRounds: parseInt(document.getElementById('sim-max-rounds').value, 10) || 1
    };

    try {
      const res = await fetch('/api/combat/simulate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      const data = await res.json();
      if (!data.success) throw new Error(data.error);

      statusBadge.textContent = `Simulation completed in ${data.result.rounds} rounds.`;
      renderSimResults(data.result);
    } catch (e) {
      statusBadge.textContent = 'Simulation error: ' + e.message;
      showToast('Simulation failed: ' + e.message);
    }
  }

  function renderSimResults(res) {
    const container = document.getElementById('sim-results-container');
    container.style.display = 'block';

    const isUserDefender = (currentSimMode === 'defense');
    const isAttackerWin = res.outcome === 'attacker';
    const isDefenderWin = res.outcome === 'defender';

    const isUserVictory = (isUserDefender && isDefenderWin) || (!isUserDefender && isAttackerWin);
    const isUserDefeat = (isUserDefender && isAttackerWin) || (!isUserDefender && isDefenderWin);

    const bannerColor = isUserVictory ? 'var(--green)' : (isUserDefeat ? '#ff5252' : '#ffb74d');
    const bannerBg = isUserVictory ? 'rgba(0,255,170,0.08)' : (isUserDefeat ? 'rgba(255,82,82,0.08)' : 'rgba(255,183,77,0.08)');
    const bannerBorder = isUserVictory ? 'rgba(0,255,170,0.3)' : (isUserDefeat ? 'rgba(255,82,82,0.3)' : 'rgba(255,183,77,0.3)');

    let bannerHeadline = res.outcomeDetail;
    if (isUserDefender) {
      if (isDefenderWin) {
        bannerHeadline = 'HOME BASE DEFENSE VICTORIOUS! Planetary Garrison Repelled the Invaders';
      } else if (isAttackerWin) {
        bannerHeadline = 'PLANETARY DEFENSE BREACHED! Invading Fleet Overwhelmed Garrison';
      }
    }

    let adviceHtml = (res.tacticalAdvice || []).map(a => `<div style="margin-bottom: 0.35rem;">${escapeHtml(a)}</div>`).join('');

    // Per-Fleet Casualty Breakdown Rows
    let fleetRowsHtml = '';
    const atkFleetsRes = (res.attacker && res.attacker.fleets) ? res.attacker.fleets : [];
    const defFleetsRes = (res.defender && res.defender.fleets) ? res.defender.fleets : [];

    atkFleetsRes.forEach(f => {
      const statusBadge = f.enabled 
        ? '<span class="badge badge-info" style="font-size: 0.7rem;">Active</span>' 
        : '<span class="badge" style="background: rgba(255,255,255,0.1); color: var(--text-dim); font-size: 0.7rem;">Disabled (0 Losses)</span>';
      fleetRowsHtml += `
        <tr style="border-bottom: 1px solid rgba(255,255,255,0.04);">
          <td style="padding: 0.5rem 0.75rem;"><span style="color: var(--cyan); font-weight: 700;">[Attacker]</span> <strong>${escapeHtml(f.name)}</strong></td>
          <td style="padding: 0.5rem 0.75rem; text-align: center;">${statusBadge}</td>
          <td style="padding: 0.5rem 0.75rem; text-align: center;">${f.totalStart.toLocaleString()}</td>
          <td style="padding: 0.5rem 0.75rem; text-align: center; color: ${f.totalLost > 0 ? '#ff5252' : 'var(--text-dim)'}; font-weight: 600;">-${f.totalLost.toLocaleString()}</td>
          <td style="padding: 0.5rem 0.75rem; text-align: center; color: var(--green); font-weight: 600;">${f.totalSurvived.toLocaleString()}</td>
          <td style="padding: 0.5rem 0.75rem; text-align: center;">${f.lossPercent}%</td>
          <td style="padding: 0.5rem 0.75rem; text-align: right; color: var(--text-dim);">${(f.valueLost?.total || 0).toLocaleString()}</td>
        </tr>
      `;
    });

    defFleetsRes.forEach(f => {
      const isPds = f.isPds;
      const sideLabel = isPds ? '<span style="color: #ffd54f; font-weight: 700;">[Planet PDS]</span>' : '<span style="color: #ff5252; font-weight: 700;">[Defender]</span>';
      const statusBadge = f.enabled 
        ? '<span class="badge badge-warning" style="font-size: 0.7rem;">Active</span>' 
        : '<span class="badge" style="background: rgba(255,255,255,0.1); color: var(--text-dim); font-size: 0.7rem;">Disabled (0 Losses)</span>';
      fleetRowsHtml += `
        <tr style="border-bottom: 1px solid rgba(255,255,255,0.04);">
          <td style="padding: 0.5rem 0.75rem;">${sideLabel} <strong>${escapeHtml(f.name)}</strong></td>
          <td style="padding: 0.5rem 0.75rem; text-align: center;">${statusBadge}</td>
          <td style="padding: 0.5rem 0.75rem; text-align: center;">${f.totalStart.toLocaleString()}</td>
          <td style="padding: 0.5rem 0.75rem; text-align: center; color: ${f.totalLost > 0 ? '#ff5252' : 'var(--text-dim)'}; font-weight: 600;">-${f.totalLost.toLocaleString()}</td>
          <td style="padding: 0.5rem 0.75rem; text-align: center; color: var(--green); font-weight: 600;">${f.totalSurvived.toLocaleString()}</td>
          <td style="padding: 0.5rem 0.75rem; text-align: center;">${f.lossPercent}%</td>
          <td style="padding: 0.5rem 0.75rem; text-align: right; color: var(--text-dim);">${(f.valueLost?.total || 0).toLocaleString()}</td>
        </tr>
      `;
    });

    // Side-by-side casualty rows
    let casualtiesHtml = '';
    const allUnitIds = Array.from(new Set([...Object.keys(res.attacker.startCounts), ...Object.keys(res.defender.startCounts)]));

    allUnitIds.forEach(uId => {
      const isAtk = uId in res.attacker.startCounts;
      const sideLabel = isAtk 
        ? (isUserDefender ? '<span style="color: #ff5252;">[Enemy Attacker]</span>' : '<span style="color: var(--cyan);">[Your Fleet]</span>')
        : (isUserDefender ? '<span style="color: var(--cyan);">[Your Defense]</span>' : '<span style="color: #ff5252;">[Enemy Defender]</span>');
      const sideData = isAtk ? res.attacker : res.defender;
      const start = sideData.startCounts[uId] || 0;
      const lost = sideData.lostCounts[uId] || 0;
      const survived = sideData.survivedCounts[uId] || 0;

      casualtiesHtml += `
        <tr style="border-bottom: 1px solid rgba(255,255,255,0.04);">
          <td style="padding: 0.5rem 0.75rem;">${sideLabel} <strong>${escapeHtml(uId.replace('main-', '').replace(/-/g, ' '))}</strong></td>
          <td style="padding: 0.5rem 0.75rem; text-align: center;">${start.toLocaleString()}</td>
          <td style="padding: 0.5rem 0.75rem; text-align: center; color: ${lost > 0 ? '#ff5252' : 'var(--text-dim)'}; font-weight: 600;">-${lost.toLocaleString()}</td>
          <td style="padding: 0.5rem 0.75rem; text-align: center; color: var(--green); font-weight: 600;">${survived.toLocaleString()}</td>
        </tr>
      `;
    });

    // Round replay accordion
    let roundsLogHtml = '';
    (res.roundDetails || []).forEach(rd => {
      const events = (rd.events || []).map(e => {
        let icon = '•';
        let color = '#cbd5e1';
        if (e.includes('Shield Aura') || e.includes('Planetary Shield')) {
          color = '#80d8ff';
        } else if (e.includes('Siege Barrier')) {
          color = '#ffd54f';
        } else if (e.includes('Disruption Field') || e.includes('EMP')) {
          color = '#b388ff';
        } else if (e.includes('destroyed')) {
          color = '#ff8a80';
        }
        return `<li style="margin-bottom: 0.35rem; color: ${color}; line-height: 1.4;">${escapeHtml(e)}</li>`;
      }).join('');

      const killsCount = (rd.actions || []).reduce((sum, a) => sum + (a.shipsDestroyed || 0), 0);
      const empCount = (rd.actions || []).reduce((sum, a) => sum + (a.shipsEmped || 0), 0);

      roundsLogHtml += `
        <details open style="background: rgba(0,0,0,0.3); border: 1px solid rgba(255,255,255,0.07); border-radius: 6px; padding: 0.75rem;">
          <summary style="font-weight: 700; color: var(--cyan); cursor: pointer; display: flex; justify-content: space-between; align-items: center; user-select: none;">
            <span>⚔️ Combat Round ${rd.roundNumber}</span>
            <span style="font-size: 0.75rem; font-family: var(--font-mono); color: var(--text-dim);">
              ${killsCount > 0 ? `<span style="color: #ff5252; margin-right: 0.5rem;">${killsCount.toLocaleString()} destroyed</span>` : ''}
              ${empCount > 0 ? `<span style="color: #b388ff; margin-right: 0.5rem;">${empCount.toLocaleString()} EMP disabled</span>` : ''}
              <span>Shield: ${rd.shieldRemainingHP ? rd.shieldRemainingHP.toLocaleString() + ' HP' : '0 HP'}</span>
            </span>
          </summary>
          <div style="margin-top: 0.75rem; max-height: 240px; overflow-y: auto; padding-right: 0.35rem;">
            <ul style="margin: 0; padding-left: 1.25rem; font-family: var(--font-mono); font-size: 0.8rem;">
              ${events || '<li style="color: var(--text-dim);">No significant damage dealt.</li>'}
            </ul>
          </div>
        </details>
      `;
    });

    const roidsStolen = res.asteroidsStolen || { metalRoids: 0, crystalRoids: 0, eoniumRoids: 0, total: 0 };
    const scoreChange = res.scoreChange || { attacker: 0, defender: 0 };
    const atkScoreClass = scoreChange.attacker >= 0 ? 'var(--green)' : '#ff5252';
    const atkScoreSign = scoreChange.attacker >= 0 ? '+' : '';
    const defScoreClass = scoreChange.defender >= 0 ? 'var(--green)' : '#ff5252';
    const defScoreSign = scoreChange.defender >= 0 ? '+' : '';

    container.innerHTML = `
      <!-- OUTCOME BANNER -->
      <div style="background: ${bannerBg}; border: 1px solid ${bannerBorder}; border-radius: 8px; padding: 1.5rem; margin-bottom: 1.5rem; text-align: center;">
        <div style="font-size: 1.6rem; font-weight: 900; color: ${bannerColor}; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 0.5rem;">
          ${isUserVictory ? '🏆 ' : (isUserDefeat ? '💀 ' : '⚖️ ')}${escapeHtml(bannerHeadline)}
        </div>
        <div style="font-family: var(--font-mono); font-size: 0.95rem; color: var(--text-dim); margin-bottom: 1rem;">
          Simulation concluded after <strong>${res.rounds}</strong> combat rounds. Tactical dominance score: <strong style="color: ${bannerColor};">${Math.round(res.dominance * 100)}%</strong>
        </div>

        <!-- DOMINANCE BAR GAUGE -->
        <div style="height: 10px; background: rgba(255,82,82,0.4); border-radius: 5px; overflow: hidden; max-width: 600px; margin: 0 auto;">
          <div style="height: 100%; width: ${Math.round(res.dominance * 100)}%; background: var(--cyan);"></div>
        </div>
        <div style="display: flex; justify-content: space-between; max-width: 600px; margin: 0.35rem auto 0; font-family: var(--font-mono); font-size: 0.75rem; color: var(--text-dim);">
          <span>Attacker Advantage (${Math.round(res.dominance * 100)}%)</span>
          <span>Defender Advantage (${100 - Math.round(res.dominance * 100)}%)</span>
        </div>
      </div>

      <!-- 6-CARD BALANCE METRICS STRIP -->
      <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 1rem; margin-bottom: 1.5rem;">
        <div class="panel" style="padding: 1rem; text-align: center;">
          <div style="font-size: 0.78rem; color: var(--text-dim); text-transform: uppercase;">Attacker Losses</div>
          <div style="font-size: 1.3rem; font-weight: 800; color: ${res.attacker.totalLost > 0 ? '#ff5252' : 'var(--green)'}; margin: 0.25rem 0;">
            ${res.attacker.totalLost.toLocaleString()} ships (${res.attacker.lossPercent}%)
          </div>
          <div style="font-size: 0.78rem; color: var(--text-dim); font-family: var(--font-mono);">
            -${(res.attacker.valueLost.total || 0).toLocaleString()} net value
          </div>
        </div>

        <div class="panel" style="padding: 1rem; text-align: center;">
          <div style="font-size: 0.78rem; color: var(--text-dim); text-transform: uppercase;">Defender Losses</div>
          <div style="font-size: 1.3rem; font-weight: 800; color: ${res.defender.totalLost > 0 ? 'var(--green)' : 'var(--text-dim)'}; margin: 0.25rem 0;">
            ${res.defender.totalLost.toLocaleString()} ships (${res.defender.lossPercent}%)
          </div>
          <div style="font-size: 0.78rem; color: var(--text-dim); font-family: var(--font-mono);">
            -${(res.defender.valueLost.total || 0).toLocaleString()} net value
          </div>
        </div>

        <div class="panel" style="padding: 1rem; text-align: center;">
          <div style="font-size: 0.78rem; color: var(--text-dim); text-transform: uppercase;">Projected Salvage</div>
          <div style="font-size: 1.3rem; font-weight: 800; color: var(--cyan); margin: 0.25rem 0;">
            +${(res.salvage.total || 0).toLocaleString()}
          </div>
          <div style="font-size: 0.78rem; color: var(--text-dim); font-family: var(--font-mono);">
            ${res.salvage.metal.toLocaleString()} M • ${res.salvage.crystal.toLocaleString()} C • ${res.salvage.eonium.toLocaleString()} E
          </div>
        </div>

        <div class="panel" style="padding: 1rem; text-align: center;">
          <div style="font-size: 0.78rem; color: var(--text-dim); text-transform: uppercase;">Estimated Plunder</div>
          <div style="font-size: 1.3rem; font-weight: 800; color: var(--yellow); margin: 0.25rem 0;">
            ${(res.plunder.total || 0).toLocaleString()}
          </div>
          <div style="font-size: 0.78rem; color: var(--text-dim); font-family: var(--font-mono);">
            Cargo Cap: ${(res.attacker.cargoCapacity || 0).toLocaleString()}
          </div>
        </div>

        <div class="panel" style="padding: 1rem; text-align: center; border-top: 2px solid #69f0ae;">
          <div style="font-size: 0.78rem; color: var(--text-dim); text-transform: uppercase;">Asteroids Stolen</div>
          <div style="font-size: 1.3rem; font-weight: 800; color: #69f0ae; margin: 0.25rem 0;">
            ${roidsStolen.total.toLocaleString()} roids
          </div>
          <div style="font-size: 0.78rem; color: var(--text-dim); font-family: var(--font-mono);">
            ${roidsStolen.metalRoids} M • ${roidsStolen.crystalRoids} C • ${roidsStolen.eoniumRoids} E
          </div>
        </div>

        <div class="panel" style="padding: 1rem; text-align: center; border-top: 2px solid var(--purple);">
          <div style="font-size: 0.78rem; color: var(--text-dim); text-transform: uppercase;">Predicted Score Δ</div>
          <div style="font-size: 1.3rem; font-weight: 800; color: ${atkScoreClass}; margin: 0.25rem 0;">
            ${atkScoreSign}${scoreChange.attacker.toLocaleString()}
          </div>
          <div style="font-size: 0.78rem; color: var(--text-dim); font-family: var(--font-mono);">
            Defender: <span style="color: ${defScoreClass};">${defScoreSign}${scoreChange.defender.toLocaleString()}</span>
          </div>
        </div>
      </div>

      <!-- COALITION FLEETS CASUALTY BREAKDOWN -->
      <div class="panel" style="margin-bottom: 1.5rem;">
        <div class="panel-header">
          <div class="panel-title">👥 Coalition Fleets Casualty Breakdown</div>
          <span class="badge badge-info">${atkFleetsRes.length} Atk Fleet(s) • ${defFleetsRes.length} Def Fleet(s)</span>
        </div>
        <div style="overflow-x: auto;">
          <table style="width: 100%; border-collapse: collapse; font-family: var(--font-mono); font-size: 0.85rem;">
            <thead>
              <tr style="border-bottom: 1px solid rgba(255,255,255,0.1); background: rgba(255,255,255,0.02);">
                <th style="padding: 0.6rem 0.75rem; text-align: left;">Fleet / Force</th>
                <th style="padding: 0.6rem 0.75rem; text-align: center;">Status</th>
                <th style="padding: 0.6rem 0.75rem; text-align: center;">Initial Force</th>
                <th style="padding: 0.6rem 0.75rem; text-align: center;">Destroyed</th>
                <th style="padding: 0.6rem 0.75rem; text-align: center;">Survivors</th>
                <th style="padding: 0.6rem 0.75rem; text-align: center;">Loss %</th>
                <th style="padding: 0.6rem 0.75rem; text-align: right;">Net Value Lost</th>
              </tr>
            </thead>
            <tbody>
              ${fleetRowsHtml || '<tr><td colspan="7" style="text-align: center; padding: 1rem; color: var(--text-dim);">No fleet breakdown data available.</td></tr>'}
            </tbody>
          </table>
        </div>
      </div>

      <!-- PREDICTED SCORE & ROID THEFT IMPACT BREAKDOWN PANEL -->
      <div class="panel" style="margin-bottom: 1.5rem; background: rgba(187,134,252,0.03); border-left: 4px solid var(--purple);">
        <div class="panel-header" style="margin-bottom: 0.5rem;">
          <div class="panel-title" style="font-size: 0.95rem; color: #d8b4fe;">📈 Projected Score Dynamics & Asteroid Seizure Breakdown</div>
          <span class="badge" style="background: rgba(187,134,252,0.15); color: #d8b4fe;">Score Economy Model</span>
        </div>
        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 1rem; font-size: 0.85rem; font-family: var(--font-mono);">
          <div style="background: rgba(0,0,0,0.25); border-radius: 6px; padding: 0.75rem;">
            <div style="font-weight: 700; color: var(--cyan); margin-bottom: 0.35rem;">🚀 Attacker Score Impact: <span style="color: ${atkScoreClass};">${atkScoreSign}${scoreChange.attacker.toLocaleString()} pts</span></div>
            <div style="color: var(--text-dim); line-height: 1.6; font-size: 0.8rem;">
              • Ships Lost Penalty: <span style="color: #ff5252;">${(scoreChange.attackerBreakdown?.shipsLostPenalty || 0).toLocaleString()} pts</span><br>
              • Salvage Recovery: <span style="color: var(--cyan);">+${(scoreChange.attackerBreakdown?.salvageBonus || 0).toLocaleString()} pts</span><br>
              • Resource Plunder: <span style="color: var(--yellow);">+${(scoreChange.attackerBreakdown?.plunderBonus || 0).toLocaleString()} pts</span><br>
              • Asteroids Captured: <span style="color: #69f0ae;">+${(scoreChange.attackerBreakdown?.asteroidsBonus || 0).toLocaleString()} pts</span> (${roidsStolen.total} × 500)
            </div>
          </div>
          <div style="background: rgba(0,0,0,0.25); border-radius: 6px; padding: 0.75rem;">
            <div style="font-weight: 700; color: #ff5252; margin-bottom: 0.35rem;">🛡️ Defender Score Impact: <span style="color: ${defScoreClass};">${defScoreSign}${scoreChange.defender.toLocaleString()} pts</span></div>
            <div style="color: var(--text-dim); line-height: 1.6; font-size: 0.8rem;">
              • Ships Lost Penalty: <span style="color: #ff5252;">${(scoreChange.defenderBreakdown?.shipsLostPenalty || 0).toLocaleString()} pts</span><br>
              • Resources Plundered: <span style="color: #ff5252;">${(scoreChange.defenderBreakdown?.plunderPenalty || 0).toLocaleString()} pts</span><br>
              • Asteroids Seized: <span style="color: #ff5252;">${(scoreChange.defenderBreakdown?.asteroidsPenalty || 0).toLocaleString()} pts</span> (-${roidsStolen.total} roids)
            </div>
          </div>
        </div>
      </div>

      <!-- TACTICAL ADVICE -->
      <div class="panel" style="margin-bottom: 1.5rem; background: rgba(0,229,255,0.03); border-left: 4px solid var(--cyan);">
        <div class="panel-header" style="margin-bottom: 0.5rem;">
          <div class="panel-title" style="font-size: 0.95rem;">💡 Fleet Commander Tactical Debrief</div>
        </div>
        <div style="font-size: 0.88rem; line-height: 1.5;">
          ${adviceHtml}
        </div>
      </div>

      <!-- DETAILED CASUALTY TABLE -->
      <div class="panel" style="margin-bottom: 1.5rem;">
        <div class="panel-header">
          <div class="panel-title">📊 Unit Casualties & Survivor Manifest</div>
        </div>
        <div style="overflow-x: auto;">
          <table style="width: 100%; border-collapse: collapse; font-family: var(--font-mono); font-size: 0.85rem;">
            <thead>
              <tr style="border-bottom: 1px solid rgba(255,255,255,0.1); background: rgba(255,255,255,0.02);">
                <th style="padding: 0.6rem 0.75rem; text-align: left;">Unit Name</th>
                <th style="padding: 0.6rem 0.75rem; text-align: center;">Initial Force</th>
                <th style="padding: 0.6rem 0.75rem; text-align: center;">Destroyed</th>
                <th style="padding: 0.6rem 0.75rem; text-align: center;">Survivors</th>
              </tr>
            </thead>
            <tbody>
              ${casualtiesHtml}
            </tbody>
          </table>
        </div>
      </div>

      <!-- ROUND-BY-ROUND COMBAT REPLAY LOG -->
      <div class="panel" style="margin-bottom: 2rem;">
        <div class="panel-header">
          <div class="panel-title">📜 Round-by-Round Engagement Replay</div>
          <div style="display: flex; gap: 0.5rem; align-items: center;">
            <span class="badge badge-info">${res.rounds} Round(s)</span>
            <span style="font-size: 0.75rem; color: var(--text-dim); font-family: var(--font-mono);">Scrollable Telemetry</span>
          </div>
        </div>
        <div style="max-height: 480px; overflow-y: auto; padding-right: 0.5rem; display: flex; flex-direction: column; gap: 0.75rem;">
          ${roundsLogHtml}
        </div>
      </div>
    `;

    // Scroll to results smoothly
    container.scrollIntoView({ behavior: 'smooth' });
  }
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
    print("🌌 PEGASUS GALAXY MCP CONTROL HUB GUI (v0.3)")
    print(f"🚀 Server running at: http://{host}:{port}")
    if host == "0.0.0.0":
        print("🌐 Remote VPS Mode: Accessible from any device with network access to this server")
    print("⚡ Real-time Telemetry • 67 MCP Commands • Cross-Platform")
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
