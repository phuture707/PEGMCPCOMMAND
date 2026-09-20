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
import urllib.parse
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
cached_universe_map: Optional[list] = None
cached_universe_time: float = 0.0
cached_alliance_info: Optional[dict] = None
cached_alliance_time: float = 0.0
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


def log_to_bot_log(msg: str):
    """Appends a timestamped log entry to bot.log so immediate manual actions are persisted."""
    log_file = BASE_DIR / "bot.log"
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    formatted = f"[{now_str}] {msg}\n"
    print(formatted, end="", flush=True)
    try:
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(formatted)
    except Exception:
        pass


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
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Requested-With")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Private-Network", "true")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Requested-With")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Private-Network", "true")
        self.end_headers()

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        global mcp_client, cached_tools, cached_ships, cached_universe_map, cached_universe_time, cached_alliance_info, cached_alliance_time

        url_path = self.path.split("?")[0]
        query_str = self.path.split("?")[1] if "?" in self.path else ""

        if url_path in ("/calc.html", "/docs/calc.html", "/docs/index.html"):
            doc_file = BASE_DIR / "docs" / ("index.html" if "index.html" in url_path else "calc.html")
            if doc_file.exists():
                body = doc_file.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Access-Control-Allow-Private-Network", "true")
                self.end_headers()
                self.wfile.write(body)
                return

        if url_path in ("/", "/index.html", "/calc", "/bcalc", "/battlecalc"):
            is_standalone = url_path in ("/calc", "/bcalc", "/battlecalc") or (
                "calc" in query_str.lower() and ("mode=calc" in query_str.lower() or "calc=1" in query_str.lower())
            )
            html_to_serve = HTML_CONTENT
            if is_standalone:
                html_to_serve = html_to_serve.replace(
                    "<head>",
                    "<head>\n  <script>window.IS_STANDALONE_CALC = true;</script>",
                    1
                )
            body = html_to_serve.encode("utf-8")
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
                fleets = []
                hangar = {}
                home_pds_from_base = {}

                # 1. Fetch complete fleet summary (includes ALL fleets including DOCKED, plus baseFleet)
                try:
                    summary_resp = mcp_client.call_tool("get_fleet_summary") or {}
                    s_data = summary_resp.get("data", {}) if isinstance(summary_resp, dict) else {}
                    if isinstance(s_data, dict):
                        fleets = s_data.get("fleets", []) or []
                        raw_base = s_data.get("baseFleet", {}) or {}
                        for sid, cnt in raw_base.items():
                            if sid.startswith("pds-"):
                                sid_lower = sid.lower()
                                if "laser" in sid_lower:
                                    home_pds_from_base["Laser Battery"] = max(home_pds_from_base.get("Laser Battery", 0), int(cnt))
                                elif "missile" in sid_lower:
                                    home_pds_from_base["Missile Silo"] = max(home_pds_from_base.get("Missile Silo", 0), int(cnt))
                                elif "ion" in sid_lower:
                                    home_pds_from_base["Ion Cannon"] = max(home_pds_from_base.get("Ion Cannon", 0), int(cnt))
                                elif "shield" in sid_lower:
                                    home_pds_from_base["Shield Generator"] = max(home_pds_from_base.get("Shield Generator", 0), int(cnt))
                            else:
                                try:
                                    hangar[sid] = int(cnt)
                                except (ValueError, TypeError):
                                    pass
                except Exception:
                    pass

                # Fallback if fleets is empty
                if not fleets:
                    try:
                        active_fleets_resp = mcp_client.call_tool("list_active_fleets") or {}
                        fleets = active_fleets_resp.get("data", []) if isinstance(active_fleets_resp, dict) else []
                    except Exception:
                        pass

                # Fallback for hangar if empty
                if not hangar:
                    try:
                        planet_ships_resp = mcp_client.call_tool("get_planet_ships") or {}
                        raw_hangar = planet_ships_resp.get("data", {}) if isinstance(planet_ships_resp, dict) else {}
                        if isinstance(raw_hangar, dict):
                            hangar = {k: int(v) for k, v in raw_hangar.items() if isinstance(v, (int, float))}
                        elif isinstance(raw_hangar, list):
                            for item in raw_hangar:
                                if isinstance(item, dict):
                                    sid = item.get("shipDefinitionId") or item.get("id")
                                    qty = item.get("quantity") or item.get("count", 1)
                                    if sid:
                                        hangar[sid] = hangar.get(sid, 0) + int(qty)
                    except Exception:
                        pass

                # Query Home Defense info (PDS, research, resources, asteroids)
                home_pds = dict(home_pds_from_base)
                try:
                    pds_resp = mcp_client.call_tool("list_pds") or {}
                    pds_list = pds_resp.get("data", []) if isinstance(pds_resp, dict) else []
                    for p in pds_list:
                        name = p.get("name")
                        lvl = p.get("currentLevel", 1)
                        if name:
                            home_pds[name] = max(home_pds.get(name, 0), lvl)
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

        if url_path == "/api/combat/defense_scenario":
            try:
                coords_param = ""
                tick_param = 0
                window_param = 0
                if query_str:
                    params = urllib.parse.parse_qs(query_str)
                    coords_param = params.get("coords", [""])[0].strip()
                    try:
                        tick_param = int(params.get("tick", ["0"])[0])
                    except (ValueError, TypeError):
                        tick_param = 0
                    try:
                        window_param = int(params.get("window", ["0"])[0])
                    except (ValueError, TypeError):
                        window_param = 0

                # 1. Fetch current tick info
                tick_info_resp = mcp_client.call_tool("get_tick_info") or {}
                t_data = tick_info_resp.get("data", {}) if isinstance(tick_info_resp, dict) else {}
                current_tick = int(t_data.get("tick", 0)) if t_data else 0
                next_tick_in = t_data.get("nextTickIn", "unknown") if t_data else "unknown"

                # 2. Fetch planet status (for home planet coords and fallback)
                home_p_resp = mcp_client.get_planet_status() or {}
                hp_data = home_p_resp.get("data", {}) if isinstance(home_p_resp, dict) else {}
                home_coords = hp_data.get("coords", "")
                home_planet_name = hp_data.get("name", "Home Planet")

                effective_coords = coords_param or home_coords
                is_home = (effective_coords == home_coords) or not coords_param

                # 3. Fetch Player Garrison & Defenses (PDS, research, hangar)
                garrison_ships = {}
                pds_levels = {"Shield Generator": 0, "Laser Battery": 0, "Ion Cannon": 0, "Missile Silo": 0}
                research_levels = {"Hulls": 5, "ShipTechnology": 5, "PDS": 5}

                if is_home:
                    try:
                        ships_resp = mcp_client.call_tool("get_planet_ships") or {}
                        raw_ships = ships_resp.get("data", {}) if isinstance(ships_resp, dict) else {}
                        if isinstance(raw_ships, dict):
                            garrison_ships = {k: int(v) for k, v in raw_ships.items() if isinstance(v, (int, float))}
                        elif isinstance(raw_ships, list):
                            for item in raw_ships:
                                if isinstance(item, dict):
                                    sid = item.get("shipDefinitionId") or item.get("id")
                                    qty = item.get("quantity") or item.get("count", 1)
                                    if sid:
                                        garrison_ships[sid] = garrison_ships.get(sid, 0) + int(qty)
                    except Exception:
                        pass

                    try:
                        pds_resp = mcp_client.call_tool("list_pds") or {}
                        for p in (pds_resp.get("data", []) if isinstance(pds_resp, dict) else []):
                            name = p.get("name")
                            lvl = p.get("currentLevel", 1)
                            if name:
                                pds_levels[name] = max(pds_levels.get(name, 0), int(lvl))
                    except Exception:
                        pass

                    try:
                        res_resp = mcp_client.call_tool("get_planet_research") or {}
                        for r in (res_resp.get("data", []) if isinstance(res_resp, dict) else []):
                            rn = r.get("name", "")
                            lvl = r.get("currentLevel", 5)
                            if rn == "Hulls":
                                research_levels["Hulls"] = int(lvl)
                            elif rn == "Ship Technology":
                                research_levels["ShipTechnology"] = int(lvl)
                            elif rn == "PDS":
                                research_levels["PDS"] = int(lvl)
                    except Exception:
                        pass

                # 4. Fetch all player fleet movements
                raw_fleets = []
                try:
                    f_act = mcp_client.call_tool("get_planet_fleet_activity") or {}
                    raw_fleets = f_act.get("data", []) if isinstance(f_act, dict) else []
                except Exception:
                    pass

                if not raw_fleets:
                    try:
                        f_sum = mcp_client.call_tool("get_fleet_summary") or {}
                        s_data = f_sum.get("data", {}) if isinstance(f_sum, dict) else {}
                        raw_fleets = s_data.get("fleets", []) if isinstance(s_data, dict) else []
                    except Exception:
                        pass

                # 5. Fetch Events to detect incoming hostile fleets & ETAs
                incoming_events = []
                attacker_scores = {}
                try:
                    ev_resp = mcp_client.call_tool("get_events", {"limit": 50}) or {}
                    raw_events = ev_resp.get("data", []) if isinstance(ev_resp, dict) else []
                    for ev in raw_events:
                        ev_type = ev.get("eventType")
                        if ev_type == "FLEET_INCOMING":
                            incoming_events.append(ev)
                        elif ev_type == "SCORE_CHANGE":
                            d_raw = ev.get("data", "")
                            if isinstance(d_raw, str) and "breakdown" in d_raw:
                                try:
                                    d_json = json.loads(d_raw)
                                    p_id = ev.get("playerId")
                                    if p_id and "breakdown" in d_json:
                                        attacker_scores[p_id] = d_json["breakdown"]
                                except Exception:
                                    pass
                except Exception:
                    pass

                # Auto-detect earliest incoming hostile arrival tick if tick_param <= 0
                earliest_hostile_tick = 0
                for ie in incoming_events:
                    ie_tick = int(ie.get("tick") or current_tick)
                    ie_data_raw = ie.get("data")
                    ie_data = {}
                    if isinstance(ie_data_raw, str):
                        try:
                            ie_data = json.loads(ie_data_raw)
                        except Exception:
                            pass
                    elif isinstance(ie_data_raw, dict):
                        ie_data = ie_data_raw
                    eta = int(ie_data.get("eta") or 0)
                    arrival = ie_tick + eta
                    if arrival >= current_tick:
                        if earliest_hostile_tick == 0 or arrival < earliest_hostile_tick:
                            earliest_hostile_tick = arrival

                target_battle_tick = tick_param if tick_param > 0 else (earliest_hostile_tick if earliest_hostile_tick > 0 else (current_tick + 10 if current_tick > 0 else 100))

                # Partition defender fleets
                fleet_partition = peg_combat.filter_fleets_by_arrival(raw_fleets, target_battle_tick, window_param)

                # 6. Fetch Scans to extract attacker fleets & planet intel
                scans_resp = mcp_client.call_tool("get_scan_history", {"limit": 100}) or {}
                user_scans = scans_resp.get("data", []) if isinstance(scans_resp, dict) else []
                for s in user_scans:
                    s["source"] = "user"

                ally_scans = []
                if cached_alliance_info and cached_alliance_info.get("id"):
                    try:
                        a_intel = mcp_client.call_tool("get_scan_intel", {"allianceId": cached_alliance_info["id"], "limit": 100}) or {}
                        ally_scans = a_intel.get("data", []) if isinstance(a_intel, dict) else []
                        for s in ally_scans:
                            s["source"] = "ally"
                    except Exception:
                        pass

                all_scans = user_scans + ally_scans

                # Gather inbound hostiles matching incoming events and scans
                attacker_fleets = []
                # 6a. Add from FLEET_INCOMING events
                for ie in incoming_events:
                    ie_tick = int(ie.get("tick") or current_tick)
                    ie_data_raw = ie.get("data")
                    ie_data = {}
                    if isinstance(ie_data_raw, str):
                        try:
                            ie_data = json.loads(ie_data_raw)
                        except Exception:
                            pass
                    elif isinstance(ie_data_raw, dict):
                        ie_data = ie_data_raw
                    eta = int(ie_data.get("eta") or 0)
                    arrival = ie_tick + eta
                    
                    if abs(arrival - target_battle_tick) <= window_param or target_battle_tick == arrival or (target_battle_tick <= 0):
                        fl_id = ie_data.get("fleetId") or f"incoming_{ie.get('id', '1')}"
                        fl_ships = ie_data.get("ships", {})
                        total_cnt = ie_data.get("totalShips") or (sum(fl_ships.values()) if fl_ships else 0)
                        if not fl_ships and total_cnt > 0:
                            fl_ships = {"main-vanguard-sentinel": total_cnt}

                        sim_fl = {
                            "id": fl_id,
                            "name": f"Incoming Hostile ({total_cnt} ships)",
                            "mission": ie_data.get("mission", "ATTACK"),
                            "arrivalTick": arrival,
                            "eta": max(0, arrival - current_tick),
                            "ships": fl_ships,
                            "totalShips": total_cnt,
                            "sourcePlanetId": ie_data.get("sourcePlanetId", ""),
                            "eventMessage": ie.get("message", "")
                        }
                        
                        rel = peg_combat.evaluate_scan_reliability({
                            "scanType": "INCOMING_SCAN",
                            "tick": ie_tick
                        }, current_tick)
                        decoy = peg_combat.detect_fleet_decoy(sim_fl, attacker_scores.get(ie_data.get("sourcePlanetId")))
                        
                        sim_fl["reliability"] = rel
                        sim_fl["decoy"] = decoy
                        sim_fl["scanSource"] = "incoming_radar"
                        attacker_fleets.append(sim_fl)

                # 6b. Search scans for fleets matching effective_coords
                norm_target = re.sub(r"[^0-9:]", ":", str(effective_coords)).strip(":")
                for s in all_scans:
                    s_coords = s.get("coords") or ""
                    r_raw = s.get("result")
                    r = {}
                    if isinstance(r_raw, str):
                        try:
                            r = json.loads(r_raw)
                        except Exception:
                            pass
                    elif isinstance(r_raw, dict):
                        r = r_raw
                    s_coords = r.get("coords") or s_coords
                    norm_s = re.sub(r"[^0-9:]", ":", str(s_coords)).strip(":")
                    if norm_s and norm_s == norm_target:
                        if not is_home and r.get("ships") and not garrison_ships:
                            garrison_ships = {k: int(v) for k, v in r.get("ships", {}).items() if not k.startswith("pds-")}
                        if not is_home and r.get("constructions") and not any(pds_levels.values()):
                            for cn in r.get("constructions", []):
                                c_name = cn.get("name", "")
                                lvl = cn.get("level", 0)
                                if any(k in c_name.lower() for k in ["laser", "missile", "ion", "shield"]):
                                    pds_levels[c_name] = max(pds_levels.get(c_name, 0), int(lvl))

                        for tf in (r.get("transitFleets") or r.get("incomingFleets") or []):
                            tf_name = tf.get("name") or "Inbound Scanned Fleet"
                            tf_ships = tf.get("ships") or {}
                            tf_arr = int(tf.get("arrivesAt") or tf.get("arrivalTick") or (current_tick + int(tf.get("eta") or 5)))
                            if abs(tf_arr - target_battle_tick) <= window_param or target_battle_tick == tf_arr:
                                sim_fl = {
                                    "id": tf.get("id") or f"scan_fl_{len(attacker_fleets)+1}",
                                    "name": tf_name,
                                    "mission": tf.get("mission", "ATTACK"),
                                    "arrivalTick": tf_arr,
                                    "eta": max(0, tf_arr - current_tick),
                                    "ships": tf_ships,
                                    "totalShips": sum(tf_ships.values()),
                                    "scanSource": s.get("source", "user"),
                                    "scanType": s.get("scanType", "DEEP_SCAN")
                                }
                                sim_fl["reliability"] = peg_combat.evaluate_scan_reliability(s, current_tick)
                                sim_fl["decoy"] = peg_combat.detect_fleet_decoy(sim_fl)
                                attacker_fleets.append(sim_fl)

                # Deduplicate attacker fleets by ID
                unique_attackers = []
                seen_atk_ids = set()
                for af in attacker_fleets:
                    if af["id"] not in seen_atk_ids:
                        seen_atk_ids.add(af["id"])
                        unique_attackers.append(af)

                total_def_ships = sum(garrison_ships.values())
                for fl in fleet_partition["availableFleets"]:
                    total_def_ships += sum(fl.get("ships", {}).values())

                self._send_json({
                    "success": True,
                    "currentTick": current_tick,
                    "nextTickIn": next_tick_in,
                    "targetTick": target_battle_tick,
                    "window": window_param,
                    "coords": effective_coords,
                    "isHomePlanet": is_home,
                    "planetName": home_planet_name if is_home else f"Planet {effective_coords}",
                    "defender": {
                        "coords": effective_coords,
                        "isHomePlanet": is_home,
                        "garrisonShips": garrison_ships,
                        "pds": pds_levels,
                        "research": research_levels,
                        "availableFleets": fleet_partition["availableFleets"],
                        "lateFleets": fleet_partition["lateFleets"],
                        "totalAvailableShips": total_def_ships
                    },
                    "attackers": unique_attackers,
                    "totalAttackersCount": len(unique_attackers),
                    "totalAttackerShips": sum(af.get("totalShips", 0) for af in unique_attackers)
                })
            except Exception as e:
                self._send_json({"success": False, "error": str(e)}, status=500)
            return

        if url_path == "/api/combat/scan_targets":
            try:
                # 1. Fetch universe map (cached for 10 minutes)
                now = time.time()
                if not cached_universe_map or (now - cached_universe_time > 600):
                    try:
                        u_resp = mcp_client.call_tool("get_universe_map") or {}
                        cached_universe_map = u_resp.get("data", []) if isinstance(u_resp, dict) else []
                        cached_universe_time = now
                    except Exception:
                        cached_universe_map = cached_universe_map or []

                # Build planetary metadata lookup from universe map
                planet_meta = {}
                coords_lookup = {}
                universe_planets = []
                for p in (cached_universe_map or []):
                    pid = p.get("id")
                    c = p.get("coords") or f"{p.get('coordX', 0)}:{p.get('coordY', 0)}:{p.get('coordZ', 0)}"
                    pname = p.get("name") or "Unnamed Planet"
                    powner = p.get("playerId") or ""
                    if pid:
                        planet_meta[pid] = {
                            "coords": c,
                            "name": pname,
                            "owner": powner,
                            "pds": {},
                            "research": {},
                            "resources": {},
                            "asteroids": {}
                        }
                    if c:
                        norm_c = re.sub(r"[^0-9:]", ":", c.strip())
                        norm_c = re.sub(r":+", ":", norm_c).strip(":")
                        coords_lookup[norm_c] = pid
                    universe_planets.append({"id": pid, "name": pname, "coords": c, "owner": powner})

                # 2. Fetch User Personal Scans
                user_scans = []
                try:
                    scans_resp = mcp_client.call_tool("get_scan_history", {"limit": 100}) or {}
                    raw_user_scans = scans_resp.get("data", []) if isinstance(scans_resp, dict) else []
                    for s in raw_user_scans:
                        s["source"] = "user"
                        user_scans.append(s)
                except Exception:
                    user_scans = []

                # 3. Detect Alliance & Fetch Alliance Shared Scans
                alliance_info = None
                alliance_scans = []
                alliance_error = None
                try:
                    if not cached_alliance_info or (now - cached_alliance_time > 300):
                        cached_alliance_info = mcp_client.get_user_alliance()
                        cached_alliance_time = now
                    user_alliance = cached_alliance_info
                    if user_alliance and user_alliance.get("id"):
                        alliance_info = {
                            "id": user_alliance.get("id"),
                            "name": user_alliance.get("name"),
                            "tag": user_alliance.get("tag"),
                            "leaderId": user_alliance.get("leaderId"),
                        }
                        # Attempt get_scan_intel
                        intel_resp = mcp_client.call_tool("get_scan_intel", {
                            "allianceId": user_alliance["id"],
                            "limit": 100
                        })
                        if isinstance(intel_resp, dict) and intel_resp.get("success"):
                            raw_ally = intel_resp.get("data", []) or []
                            for ascan in raw_ally:
                                ascan["source"] = "ally"
                                ascan["allianceTag"] = user_alliance.get("tag", "")
                                alliance_scans.append(ascan)
                        elif isinstance(intel_resp, dict) and intel_resp.get("error"):
                            alliance_error = str(intel_resp.get("error"))
                except Exception as e:
                    alliance_error = str(e)

                # Combine all scans
                all_scans = user_scans + alliance_scans

                # Enrich planetary metadata from all scan results
                for s in all_scans:
                    pid = s.get("targetPlanetId") or s.get("planetId")
                    if not pid:
                        continue
                    if pid not in planet_meta:
                        planet_meta[pid] = {"coords": "", "owner": "", "name": "", "pds": {}, "research": {}, "resources": {}, "asteroids": {}}
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

                # Filter all scans that contain fleet, military, or docked ships data (or blocked scans)
                fleet_scan_types = {"DEEP_SCAN", "MILITARY_SCAN", "FLEET_COMPOSITION_SCAN", "INCOMING_SCAN"}
                fleet_scans = []
                for s in all_scans:
                    is_blocked = (s.get("status") == "blocked")
                    if not is_blocked and s.get("status") != "success":
                        continue
                    st = s.get("scanType", "")
                    if st in fleet_scan_types or is_blocked:
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
                    source = s.get("source", "user")
                    # Deduplicate duplicate entries from the same tick, scan type, and source on the same target
                    scan_key = (t_id, tick, st, source)
                    if scan_key in seen_scans:
                        continue
                    seen_scans.add(scan_key)

                    parsed = peg_combat.parse_scan_record(s, planet_lookup=planet_meta)
                    if parsed:
                        targets.append(parsed)

                # Sort newest tick first
                targets.sort(key=lambda t: t.get("tick", 0), reverse=True)

                self._send_json({
                    "success": True,
                    "targets": targets,
                    "universePlanets": universe_planets,
                    "allianceInfo": alliance_info,
                    "allianceError": alliance_error,
                    "totalScans": len(targets),
                    "userScansCount": sum(1 for t in targets if t.get("source") == "user"),
                    "allyScansCount": sum(1 for t in targets if t.get("source") == "ally"),
                })
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
                # Check if result indicates a blocked action (e.g. Wave Distorter) or error
                is_blocked = False
                if isinstance(result, dict):
                    if result.get("status") == "blocked" or (isinstance(result.get("data"), dict) and result["data"].get("status") == "blocked"):
                        is_blocked = True

                if is_blocked:
                    log_to_bot_log(f"⚠️ [Immediate Order: {tool_name}] BLOCKED by planetary defenses (Wave Distorter) | args: {json.dumps(args)}")
                elif isinstance(result, dict) and (result.get("isError") or result.get("success") is False):
                    err_msg = result.get("error") or result.get("message") or "Action returned error"
                    log_to_bot_log(f"❌ [Immediate Order: {tool_name}] FAILED: {err_msg} | args: {json.dumps(args)}")
                else:
                    if tool_name in ("perform_scan", "perform_wave_scan"):
                        stype = args.get("scanType", "SCAN")
                        tpid = args.get("targetPlanetId") or args.get("coords") or "target"
                        log_to_bot_log(f"✅ [Immediate Order: {tool_name}] COMPLETED: {stype} on {tpid}")
                    elif tool_name == "launch_fleet":
                        mission = args.get("mission", "FLEET_MISSION")
                        tpid = args.get("targetPlanetId") or args.get("coords") or "target"
                        log_to_bot_log(f"🚀 [Immediate Order: launch_fleet] COMPLETED: {mission} toward {tpid}")
                    else:
                        log_to_bot_log(f"✅ [Immediate Order: {tool_name}] COMPLETED successfully")

                self._send_json({"success": True, "result": result, "blocked": is_blocked})
            except PegasusMCPError as e:
                log_to_bot_log(f"❌ [Immediate Order: {tool_name}] FAILED: {str(e)} | args: {json.dumps(args)}")
                self._send_json({"success": False, "error": str(e), "code": e.code, "data": e.data}, status=400)
            except Exception as e:
                log_to_bot_log(f"❌ [Immediate Order: {tool_name}] EXCEPTION: {str(e)} | args: {json.dumps(args)}")
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

        # Combat Simulator - Execute Live Scan & Add to Fleet (POST)
        if url_path == "/api/combat/execute_scan_and_add":
            try:
                coords = str(payload.get("coords", "")).strip()
                target_planet_id = payload.get("targetPlanetId", "")
                scan_type = payload.get("scanType", "MILITARY_SCAN")
                side = payload.get("side", "def")
                ingest_mode = payload.get("ingestMode", "consolidated")

                # Normalize coords
                norm_coords = re.sub(r"[^0-9:]", ":", coords)
                norm_coords = re.sub(r":+", ":", norm_coords).strip(":")

                # If target_planet_id not supplied, resolve via universe map
                if not target_planet_id and norm_coords:
                    try:
                        umap_resp = mcp_client.call_tool("get_universe_map") or {}
                        planets_list = umap_resp.get("data", []) if isinstance(umap_resp, dict) else []
                        for p in planets_list:
                            pc = re.sub(r"[^0-9:]", ":", str(p.get("coords", "")).strip())
                            pc = re.sub(r":+", ":", pc).strip(":")
                            if pc == norm_coords:
                                target_planet_id = p.get("id") or p.get("planetId")
                                break
                    except Exception as e:
                        log_to_bot_log(f"⚠️ [execute_scan_and_add] Universe map lookup error: {e}")

                if not target_planet_id:
                    self._send_json({
                        "success": False,
                        "error": f"Could not resolve planet ID for coordinates [{coords}]. Please verify the coordinates exist on the universe map."
                    }, status=400)
                    return

                # Calculate remaining scans for current tick
                current_tick = 0
                scans_this_tick = 0
                try:
                    state_resp = mcp_client.call_tool("get_game_state_summary") or {}
                    current_tick = (state_resp.get("data", {}) if isinstance(state_resp, dict) else {}).get("tick", 0)
                    history_resp = mcp_client.call_tool("get_scan_history", {"limit": 50}) or {}
                    raw_scans = history_resp.get("data", []) if isinstance(history_resp, dict) else []
                    scans_this_tick = sum(1 for s in raw_scans if s.get("tick") == current_tick)
                except Exception:
                    pass

                # Check if rate limit reached (3 per tick)
                if scans_this_tick >= 3:
                    self._send_json({
                        "success": False,
                        "error": f"Rate limit reached: Maximum 3 wave scans per tick. You have already executed {scans_this_tick}/3 scans in Tick {current_tick}. Please wait for the next tick.",
                        "restriction": "rate_limit",
                        "currentTick": current_tick,
                        "scansThisTick": scans_this_tick
                    }, status=429)
                    return

                # Execute scan tool
                log_to_bot_log(f"📡 [execute_scan_and_add] Executing {scan_type} on target {target_planet_id} [{coords}] for {side}...")
                scan_res = mcp_client.call_tool("perform_scan", {
                    "targetPlanetId": target_planet_id,
                    "scanType": scan_type
                })

                # Check if tool execution resulted in an error
                if isinstance(scan_res, dict) and (scan_res.get("isError") or scan_res.get("success") is False):
                    err_msg = scan_res.get("error") or scan_res.get("message") or "Scan action rejected by server"
                    log_to_bot_log(f"❌ [execute_scan_and_add] Scan failed: {err_msg}")
                    self._send_json({
                        "success": False,
                        "error": err_msg,
                        "restriction": "api_error"
                    }, status=400)
                    return

                # Check if blocked by Wave Distorter
                is_blocked = False
                res_data = scan_res.get("data") if isinstance(scan_res, dict) else scan_res
                if isinstance(scan_res, dict) and scan_res.get("status") == "blocked":
                    is_blocked = True
                elif isinstance(res_data, dict) and res_data.get("status") == "blocked":
                    is_blocked = True

                # Parse the scan record using peg_combat.parse_scan_record
                scan_record_to_parse = res_data if isinstance(res_data, dict) else scan_res
                if isinstance(scan_record_to_parse, dict) and "result" not in scan_record_to_parse:
                    scan_record_to_parse = {
                        "targetPlanetId": target_planet_id,
                        "coords": coords,
                        "scanType": scan_type,
                        "tick": current_tick,
                        "status": "blocked" if is_blocked else "success",
                        "result": res_data
                    }

                parsed_target = peg_combat.parse_scan_record(scan_record_to_parse)
                if parsed_target and not parsed_target.get("coords"):
                    parsed_target["coords"] = coords

                new_scans_this_tick = scans_this_tick + 1
                remaining_scans = max(0, 3 - new_scans_this_tick)

                log_to_bot_log(f"✅ [execute_scan_and_add] Scan successful on [{coords}]! Blocked={is_blocked}. Remaining quota: {remaining_scans}/3.")

                self._send_json({
                    "success": True,
                    "scan": parsed_target,
                    "blocked": is_blocked,
                    "coords": coords,
                    "targetPlanetId": target_planet_id,
                    "scanType": scan_type,
                    "side": side,
                    "ingestMode": ingest_mode,
                    "currentTick": current_tick,
                    "remainingScans": remaining_scans,
                    "raw": scan_res
                })
            except PegasusMCPError as e:
                log_to_bot_log(f"❌ [execute_scan_and_add] MCP Error: {str(e)}")
                self._send_json({"success": False, "error": str(e), "code": getattr(e, 'code', None)}, status=400)
            except Exception as e:
                log_to_bot_log(f"❌ [execute_scan_and_add] Exception: {str(e)}")
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
  <title>Pegasus Galaxy v0.5 • MCP Control Hub</title>
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
      transition: max-width 0.25s ease, padding 0.25s ease;
    }
    .container.wide-mode {
      max-width: 98vw;
      width: 98vw;
      padding: 1rem 1.25rem;
    }

    /* Standalone BattleCalc Mode */
    body.standalone-mode header#main-header,
    body.standalone-mode div#main-tabs,
    body.standalone-mode footer {
      display: none !important;
    }
    body.standalone-mode .container {
      max-width: 99vw !important;
      width: 99vw !important;
      padding: 0.6rem 1rem !important;
    }
    .calc-session-pill {
      user-select: none;
      transition: all 0.15s ease;
    }
    .calc-session-pill:hover {
      border-color: var(--cyan) !important;
      background: rgba(0, 229, 255, 0.12) !important;
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

    .filter-pill-btn {
      font-family: var(--font-display);
      font-size: 0.78rem;
      letter-spacing: 0.04em;
      padding: 0.25rem 0.65rem;
      background: rgba(255,255,255,0.04);
      border: 1px solid rgba(255,255,255,0.12);
      border-radius: 20px;
      color: var(--text-dim);
      cursor: pointer;
      transition: all 0.2s;
    }
    .filter-pill-btn:hover {
      color: #fff;
      border-color: rgba(255,255,255,0.3);
      background: rgba(255,255,255,0.08);
    }
    .filter-pill-btn.active {
      color: var(--cyan);
      border-color: var(--cyan);
      background: rgba(0,229,255,0.14);
      box-shadow: 0 0 10px rgba(0,229,255,0.25);
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
    /* Combat Matrix Mode Styles */
    .bcalc-table-wrapper {
      overflow-x: auto;
      background: #020617;
      border: 1px solid rgba(255,255,255,0.1);
      border-radius: 8px;
      padding: 0.5rem;
      scrollbar-width: thin;
      scrollbar-color: var(--cyan) #0a1020;
    }
    .bcalc-table-wrapper::-webkit-scrollbar {
      height: 8px;
    }
    .bcalc-table-wrapper::-webkit-scrollbar-track {
      background: #0a1020;
      border-radius: 4px;
    }
    .bcalc-table-wrapper::-webkit-scrollbar-thumb {
      background: rgba(0, 229, 255, 0.4);
      border-radius: 4px;
    }
    .bcalc-table-wrapper::-webkit-scrollbar-thumb:hover {
      background: var(--cyan);
    }
    /* Hide native number spinners so 100% of cell width is usable for digits */
    .bcalc-matrix-table input[type=number]::-webkit-inner-spin-button,
    .bcalc-matrix-table input[type=number]::-webkit-outer-spin-button,
    input.bcalc-cell-input::-webkit-inner-spin-button,
    input.bcalc-cell-input::-webkit-outer-spin-button,
    .bcalc-table input[type=number]::-webkit-inner-spin-button,
    .bcalc-table input[type=number]::-webkit-outer-spin-button,
    input.ship-input::-webkit-inner-spin-button,
    input.ship-input::-webkit-outer-spin-button {
      -webkit-appearance: none !important;
      margin: 0 !important;
    }
    .bcalc-matrix-table input[type=number],
    input.bcalc-cell-input,
    .bcalc-table input[type=number],
    input.ship-input {
      -moz-appearance: textfield !important;
    }

    .bcalc-matrix-table {
      min-width: 100%;
      width: max-content;
      border-collapse: collapse;
      font-family: var(--font-mono);
      font-size: var(--bcalc-font-size, 0.80rem);
    }
    .bcalc-matrix-table th, .bcalc-matrix-table td {
      border: 1px solid rgba(255,255,255,0.08);
      padding: var(--bcalc-cell-pad, 0.28rem 0.42rem);
      text-align: right;
      white-space: nowrap;
    }
    .bcalc-matrix-table th {
      background: #0b1329;
      color: var(--text-dim);
      font-weight: 600;
      position: sticky;
      top: 0;
      z-index: 10;
    }
    .bcalc-matrix-table tr:hover td {
      background: rgba(255,255,255,0.02);
    }
    .bcalc-matrix-table td.bcalc-ship-name {
      text-align: left;
      font-weight: 600;
      white-space: nowrap;
      position: sticky;
      left: 0;
      z-index: 3;
      background: #090e1a;
      box-shadow: 2px 0 6px rgba(0,0,0,0.5);
    }
    .bcalc-matrix-table input.bcalc-cell-input {
      width: var(--bcalc-input-w, 94px);
      min-width: 82px;
      max-width: 160px;
      background: rgba(0,0,0,0.65);
      border: 1px solid rgba(255,255,255,0.18);
      border-radius: 4px;
      color: #fff;
      font-family: var(--font-mono);
      font-size: var(--bcalc-input-font, 0.82rem);
      padding: 0.22rem 0.45rem;
      text-align: right;
      box-sizing: border-box;
      field-sizing: content;
      transition: width 0.15s ease, border-color 0.15s ease, box-shadow 0.15s ease;
    }
    .bcalc-matrix-table input.bcalc-cell-input:focus {
      outline: none;
      border-color: var(--cyan);
      box-shadow: 0 0 8px rgba(0, 229, 255, 0.4);
      background: rgba(0, 229, 255, 0.08);
    }
    /* Enhanced Matrix Fleet Delineation - Defender = Blue, Attacker = Red */
    .bcalc-matrix-table th.bcalc-def-col,
    .bcalc-matrix-table td.bcalc-def-col {
      min-width: 95px;
      border-right: 2px solid rgba(56, 189, 248, 0.4) !important;
    }
    .bcalc-matrix-table th.bcalc-atk-col,
    .bcalc-matrix-table td.bcalc-atk-col {
      min-width: 95px;
      border-right: 2px solid rgba(239, 68, 68, 0.4) !important;
    }
    .bcalc-matrix-table th.bcalc-side-divider,
    .bcalc-matrix-table td.bcalc-side-divider {
      border-right: 4px solid rgba(255, 255, 255, 0.45) !important;
    }
    .bcalc-fleet-pill {
      display: inline-block;
      font-size: 0.65rem;
      font-weight: 800;
      padding: 0.1rem 0.4rem;
      border-radius: 3px;
      letter-spacing: 0.04em;
      margin-bottom: 0.2rem;
      text-transform: uppercase;
    }
    .bcalc-fleet-pill.def {
      background: rgba(56, 189, 248, 0.2);
      color: #38bdf8;
      border: 1px solid rgba(56, 189, 248, 0.5);
    }
    .bcalc-fleet-pill.atk {
      background: rgba(239, 68, 68, 0.2);
      color: #f87171;
      border: 1px solid rgba(239, 68, 68, 0.5);
    }
    .bcalc-matrix-table input.bcalc-cell-input.has-ships {
      background: rgba(255, 255, 255, 0.14) !important;
      font-weight: 800 !important;
      color: #ffffff !important;
      border-color: rgba(255, 255, 255, 0.45) !important;
      box-shadow: inset 0 0 4px rgba(255, 255, 255, 0.15);
    }
    .bcalc-matrix-table input.bcalc-cell-input.zero-ships {
      color: rgba(255, 255, 255, 0.35);
    }
    .bcalc-matrix-table th.bcalc-fleet-header {
      padding: 0.5rem 0.45rem;
      text-align: center;
      min-width: 110px;
      vertical-align: top;
    }
    .bcalc-matrix-table th.bcalc-fleet-header.def-even {
      background: rgba(56, 189, 248, 0.07);
    }
    .bcalc-matrix-table th.bcalc-fleet-header.def-odd {
      background: rgba(56, 189, 248, 0.12);
    }
    .bcalc-matrix-table th.bcalc-fleet-header.atk-even {
      background: rgba(239, 68, 68, 0.07);
    }
    .bcalc-matrix-table th.bcalc-fleet-header.atk-odd {
      background: rgba(239, 68, 68, 0.12);
    }
    .bcalc-matrix-table td.def-col-even {
      background: rgba(56, 189, 248, 0.02);
    }
    .bcalc-matrix-table td.def-col-odd {
      background: rgba(56, 189, 248, 0.05);
    }
    .bcalc-matrix-table td.atk-col-even {
      background: rgba(239, 68, 68, 0.02);
    }
    .bcalc-matrix-table td.atk-col-odd {
      background: rgba(239, 68, 68, 0.05);
    }
    .bcalc-filter-btn {
      font-family: var(--font-mono);
      font-size: 0.72rem;
      padding: 0.2rem 0.55rem;
      background: rgba(255,255,255,0.05);
      border: 1px solid rgba(255,255,255,0.15);
      border-radius: 4px;
      color: var(--text-dim);
      cursor: pointer;
      transition: all 0.15s;
    }
    .bcalc-filter-btn:hover {
      color: #fff;
      border-color: var(--cyan);
    }
    .bcalc-filter-btn.active {
      background: var(--cyan);
      color: #000;
      font-weight: 700;
      border-color: var(--cyan);
    }
    .bcalc-report-panel {
      background: rgba(2, 6, 23, 0.7);
      border: 1px solid rgba(255,255,255,0.08);
      border-radius: 6px;
      padding: 0.75rem;
      font-family: var(--font-mono);
      font-size: 0.8rem;
      margin-bottom: 1rem;
    }
    .bcalc-report-table {
      width: 100%;
      border-collapse: collapse;
      margin-top: 0.4rem;
    }
    .bcalc-report-table th, .bcalc-report-table td {
      padding: 0.35rem 0.6rem;
      border-bottom: 1px solid rgba(255,255,255,0.05);
    }
    .bcalc-report-table th {
      color: var(--text-dim);
      text-align: right;
      font-size: 0.75rem;
    }
    .bcalc-report-table td {
      text-align: right;
    }
    .bcalc-report-table th:first-child, .bcalc-report-table td:first-child {
      text-align: left;
    }
  </style>
</head>
<body>

<div class="container">
  <!-- Standalone BattleCalc Top Header (Visible only when in standalone mode) -->
  <header id="standalone-calc-header" style="display: none; justify-content: space-between; align-items: center; padding: 0.75rem 1.25rem; background: var(--bg-panel); backdrop-filter: blur(12px); border: 1px solid var(--border-glow); border-radius: 10px; margin-bottom: 1rem; box-shadow: 0 8px 32px rgba(0,0,0,0.5);">
    <div class="brand" style="gap: 0.75rem;">
      <div class="logo-icon" style="font-size: 1.5rem;">⚔️</div>
      <div>
        <div style="display: flex; align-items: center; gap: 0.6rem; flex-wrap: wrap;">
          <div style="font-family: var(--font-display); font-size: 1.15rem; font-weight: 800; letter-spacing: 0.08em; color: var(--text-bright); text-transform: uppercase; display: flex; align-items: center; gap: 0.4rem;">
            <span>⚔️ Interstellar Battle Simulator</span>
            <span style="font-size: 0.68rem; font-family: var(--font-mono); color: var(--cyan); border: 1px solid rgba(0, 229, 255, 0.45); background: rgba(0, 229, 255, 0.1); border-radius: 4px; padding: 0.1rem 0.35rem; vertical-align: middle;">v0.5</span>
          </div>
          <!-- MCP Enhanced Mode Indicator (Inline next to Interstellar Battle Simulator text) -->
          <span class="badge" style="background: rgba(16,185,129,0.2); color: #86efac; border: 1.5px solid rgba(16,185,129,0.7); font-family: var(--font-mono); font-size: 0.76rem; font-weight: 800; border-radius: 9999px; padding: 0.25rem 0.7rem; display: inline-flex; align-items: center; gap: 0.4rem; text-transform: uppercase; letter-spacing: 0.04em; box-shadow: 0 0 12px rgba(16,185,129,0.35);" title="MCP Enhanced Mode is active! Live game state, empire fleets, PDS garrison, and scan browser are connected.">
            <span style="width: 7px; height: 7px; background: #10b981; box-shadow: 0 0 8px #10b981; border-radius: 50%; display: inline-block;"></span>
            <span>⚡ MCP Enhanced Mode: Detected &amp; Enabled</span>
          </span>
        </div>
        <div class="subtitle" style="font-size: 0.72rem; color: var(--cyan);">Dedicated Combat Sandbox &amp; Multi-Fleet Coalition Calculator</div>
      </div>
    </div>
    <div style="display: flex; align-items: center; gap: 0.5rem; flex-wrap: wrap;">
      <button class="btn-refresh" onclick="openDefenseScenarioModal()" title="Auto-plan defense: calculate available defender fleets vs inbound attacker fleets for a specific tick" style="padding: 0.38rem 0.85rem; font-size: 0.82rem; color: #38bdf8; border-color: rgba(56,189,248,0.5); background: rgba(56,189,248,0.12); font-weight: 700;">
        🛡️ Plan Defense at Tick X
      </button>
      <button class="btn-refresh" onclick="openCalcShareModal()" title="Share calculation via public link or MCP" style="padding: 0.38rem 0.85rem; font-size: 0.82rem; color: var(--cyan); border-color: rgba(0,229,255,0.45); background: rgba(0,229,255,0.1);">
        🔗 Share Link
      </button>
      <button class="btn-refresh" onclick="openCalcImportModal()" title="Import calculation from share link or code" style="padding: 0.38rem 0.85rem; font-size: 0.82rem; color: #86efac; border-color: rgba(34,197,94,0.4); background: rgba(34,197,94,0.08);">
        📥 Import
      </button>
      <button class="btn-refresh" onclick="openAllianceMessageModal()" title="Send battle plan to alliance mate via in-game message" style="padding: 0.38rem 0.85rem; font-size: 0.82rem; color: #fde047; border-color: rgba(234,179,8,0.4); background: rgba(234,179,8,0.08);">
        💬 In-Game Msg
      </button>
      <button class="btn-refresh" onclick="downloadOfflineCalcHtml()" title="Download offline standalone calculator HTML" style="padding: 0.38rem 0.85rem; font-size: 0.82rem; color: #cbd5e1; border-color: rgba(255,255,255,0.18);">
        💾 Export HTML
      </button>
      <button class="btn-refresh" onclick="popOutCalculatorToWindow()" title="Send this calculation to another new window" style="padding: 0.38rem 0.85rem; font-size: 0.82rem; color: #a5b4fc; border-color: rgba(165, 180, 252, 0.4); background: rgba(99, 102, 241, 0.1);">
        ↗️ Pop Out
      </button>
      <button class="btn-refresh" onclick="startFreshCalculation()" title="Start a clean calculation from scratch" style="padding: 0.38rem 0.85rem; font-size: 0.82rem; color: #38bdf8; border-color: rgba(56, 189, 248, 0.4); background: rgba(56, 189, 248, 0.08);">
        ✨ Start Fresh
      </button>
      <a href="/" target="_blank" class="btn-refresh" style="text-decoration: none; padding: 0.38rem 0.85rem; font-size: 0.82rem; color: #86efac; border-color: rgba(16, 185, 129, 0.4); background: rgba(16, 185, 129, 0.08);">
        🪐 Open Full Hub
      </a>
    </div>
  </header>

  <!-- Header -->
  <header id="main-header">
    <div class="brand">
      <div class="logo-icon">🪐</div>
      <div>
        <h1>Pegasus Galaxy <span style="font-size: 0.72rem; font-family: var(--font-mono); color: var(--cyan); border: 1px solid rgba(0, 229, 255, 0.45); background: rgba(0, 229, 255, 0.1); border-radius: 4px; padding: 0.15rem 0.45rem; vertical-align: middle; margin-left: 0.4rem; font-weight: 500; letter-spacing: 0.05em;">v0.5</span></h1>
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
  <div class="tabs" id="main-tabs">
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

    <!-- MULTI-CALCULATION SESSIONS BAR -->
    <div id="calc-multi-tabs-bar" style="display: flex; align-items: center; justify-content: space-between; gap: 0.6rem; margin-bottom: 1.25rem; background: rgba(15, 23, 42, 0.75); border: 1px solid rgba(0, 229, 255, 0.25); border-radius: 8px; padding: 0.55rem 0.9rem; flex-wrap: wrap;">
      <div style="display: flex; align-items: center; gap: 0.5rem; flex-wrap: wrap;">
        <span style="font-size: 0.78rem; font-family: var(--font-mono); color: var(--cyan); font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em; display: flex; align-items: center; gap: 0.3rem;">
          📑 Calculations:
        </span>
        <div id="calc-tab-list" style="display: flex; gap: 0.4rem; align-items: center; flex-wrap: wrap;">
          <!-- Dynamically populated calculation session pills -->
        </div>
        <button class="btn-refresh" onclick="addNewCalcTab()" title="Open a new blank calculation from scratch in this window" style="padding: 0.28rem 0.65rem; font-size: 0.78rem; color: var(--cyan); border-color: rgba(0,229,255,0.4); background: rgba(0,229,255,0.08);">
          ➕ New Tab
        </button>
      </div>
      <div style="display: flex; align-items: center; gap: 0.4rem; flex-wrap: wrap;">
        <button class="btn-refresh" onclick="openDefenseScenarioModal()" title="Auto-plan defense: calculate available defender fleets vs inbound attacker fleets for a specific tick" style="padding: 0.28rem 0.65rem; font-size: 0.78rem; color: #38bdf8; border-color: rgba(56,189,248,0.45); background: rgba(56,189,248,0.1); font-weight: 700;">
          🛡️ Plan Defense at Tick X
        </button>
        <button class="btn-refresh" onclick="openCalcShareModal()" title="Share calculation via public link or MCP" style="padding: 0.28rem 0.65rem; font-size: 0.78rem; color: var(--cyan); border-color: rgba(0,229,255,0.4); background: rgba(0,229,255,0.08);">
          🔗 Share Link
        </button>
        <button class="btn-refresh" onclick="openCalcImportModal()" title="Import a shared calculation link or code string" style="padding: 0.28rem 0.65rem; font-size: 0.78rem; color: #86efac; border-color: rgba(34,197,94,0.4); background: rgba(34,197,94,0.08);">
          📥 Import
        </button>
        <button class="btn-refresh" onclick="openAllianceMessageModal()" title="Dispatch battle brief & public link to alliance member via MCP" style="padding: 0.28rem 0.65rem; font-size: 0.78rem; color: #fde047; border-color: rgba(234,179,8,0.4); background: rgba(234,179,8,0.08);">
          💬 In-Game Msg
        </button>
        <button class="btn-refresh" onclick="downloadOfflineCalcHtml()" title="Download standalone offline battle calculator HTML file" style="padding: 0.28rem 0.65rem; font-size: 0.78rem; color: #cbd5e1; border-color: rgba(255,255,255,0.18);">
          💾 Export HTML
        </button>
        <button class="btn-refresh" onclick="duplicateCurrentCalcTab()" title="Clone active calculation to a new tab" style="padding: 0.28rem 0.65rem; font-size: 0.78rem; color: #cbd5e1; border-color: rgba(255,255,255,0.18);">
          📋 Duplicate
        </button>
        <button class="btn-refresh" onclick="renameCurrentCalcTab()" title="Rename active calculation tab" style="padding: 0.28rem 0.65rem; font-size: 0.78rem; color: #cbd5e1; border-color: rgba(255,255,255,0.18);">
          ✏️ Rename
        </button>
        <button class="btn-refresh" onclick="popOutCalculatorToWindow()" title="Pop this calculation out into an independent browser window" style="padding: 0.28rem 0.75rem; font-size: 0.78rem; color: #a5b4fc; border-color: rgba(165,180,252,0.45); background: rgba(99,102,241,0.12);">
          ↗️ Pop Out Window
        </button>
      </div>
    </div>

    <div class="panel" style="margin-bottom: 1.5rem;">
      <div class="panel-header" style="display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 0.5rem;">
        <div style="display: flex; align-items: center; gap: 0.6rem; flex-wrap: wrap;">
          <div class="panel-title">⚔️ Interstellar Battle Simulator</div>
          <span class="badge" style="background: rgba(16,185,129,0.2); color: #86efac; border: 1.5px solid rgba(16,185,129,0.7); font-family: var(--font-mono); font-size: 0.76rem; font-weight: 800; border-radius: 9999px; padding: 0.25rem 0.7rem; display: inline-flex; align-items: center; gap: 0.4rem; text-transform: uppercase; letter-spacing: 0.04em; box-shadow: 0 0 12px rgba(16,185,129,0.35);" title="MCP Enhanced Mode is active in the Pegasus Control Suite">
            <span style="width: 7px; height: 7px; background: #10b981; box-shadow: 0 0 8px #10b981; border-radius: 50%; display: inline-block;"></span>
            <span>⚡ MCP Enhanced Mode: Detected &amp; Enabled</span>
          </span>
        </div>
        <span class="badge badge-warning">Simulated Combat Sandbox</span>
      </div>
      <p style="color: var(--text-dim); margin-bottom: 1rem; font-size: 0.92rem; line-height: 1.5;">
        Simulate tactical fleet engagements between your active named fleets and enemy targets extracted automatically from live fleet scans (Deep Scans, Military Scans, and Fleet Scans). Accurately predicts initiative firing order, target class prioritization, planetary shield absorption, EMP disruption, and plunder capacity.
      </p>
      <div style="display: flex; gap: 0.75rem; align-items: center; justify-content: space-between; flex-wrap: wrap;">
        <div style="display: flex; gap: 0.5rem; align-items: center; flex-wrap: wrap;">
          <div style="font-size: 0.85rem; font-weight: 600; color: var(--text-dim); margin-right: 0.25rem;">Simulation Mode:</div>
          <button id="sim-mode-defense-btn" class="sim-mode-btn active" onclick="setSimulationMode('defense')">
            🛡️ Home Base Defense (User = Defender)
          </button>
          <button id="sim-mode-assault-btn" class="sim-mode-btn" onclick="setSimulationMode('assault')">
            ⚔️ Planetary Assault (User = Attacker)
          </button>
          <button class="btn-refresh" onclick="swapSimulatorSides()" title="Swap Attacker and Defender Sides" style="padding: 0.4rem 0.9rem; font-size: 0.85rem; margin-left: 0.25rem;">
            ⇄ Swap Sides
          </button>
        </div>
        <div style="display: flex; gap: 0.5rem; align-items: center; flex-wrap: wrap;">
          <div style="font-size: 0.82rem; font-weight: 600; color: var(--text-dim);">Layout:</div>
          <button id="sim-layout-bcalc-btn" class="filter-pill-btn active" onclick="setSimulatorLayout('bcalc')">
            📊 Matrix Mode
          </button>
          <button id="sim-layout-cards-btn" class="filter-pill-btn" onclick="setSimulatorLayout('cards')">
            🗂️ Cards View
          </button>
          <button class="btn-refresh" onclick="popOutCalculatorToWindow()" title="Send this calculation to an independent new window" style="padding: 0.4rem 0.9rem; font-size: 0.85rem; color: #a5b4fc; border-color: rgba(165,180,252,0.4); background: rgba(99,102,241,0.12);">
            ↗️ Pop Out Window
          </button>
          <button class="btn-refresh" onclick="startFreshCalculation()" title="Reset calculator to clean state to start a new calculation from scratch" style="padding: 0.4rem 0.9rem; font-size: 0.85rem; color: #38bdf8; border-color: rgba(56,189,248,0.4); background: rgba(56,189,248,0.08);">
            ✨ Start Fresh
          </button>
          <button class="btn-refresh" onclick="resetCombatSimulator()" title="Reset all fleets, coordinates, scans and results to clean default" style="padding: 0.4rem 0.9rem; font-size: 0.85rem; color: #f87171; border-color: rgba(239, 68, 68, 0.4); background: rgba(239, 68, 68, 0.1);">
            🔄 Reset
          </button>
          <button class="btn-primary" onclick="loadCombatSimulator()" style="padding: 0.4rem 1rem; font-size: 0.85rem; margin-left: 0.25rem;">
            🔄 Refresh Fleets
          </button>
          <span id="combat-status-badge" style="font-family: var(--font-mono); font-size: 0.82rem; color: var(--text-dim);">
            Ready to simulate.
          </span>
        </div>
      </div>
    </div>

    <!-- DUAL PLANET & INTEL COORDINATES EXPLORER (ATTACKER & DEFENDER) -->
    <div id="sim-cards-explorer-panel" class="panel" style="display: none; background: rgba(15, 23, 42, 0.92); border: 1px solid rgba(255,255,255,0.12); border-radius: 10px; padding: 1rem 1.25rem; margin-bottom: 1.5rem; box-shadow: 0 6px 30px rgba(0,0,0,0.6);">
      <!-- Top Bar: Header + Intel Source Filter Pills -->
      <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.85rem; flex-wrap: wrap; gap: 0.5rem; border-bottom: 1px solid rgba(255,255,255,0.06); padding-bottom: 0.6rem;">
        <div style="display: flex; align-items: center; gap: 0.6rem;">
          <span style="font-size: 1.05rem; font-weight: 700; color: #fff;">🛰️ Dual Fleet & Coordinates Intelligence Explorer</span>
          <span class="badge" style="background: rgba(0,229,255,0.15); color: var(--cyan); border: 1px solid var(--cyan); font-size: 0.7rem;">Scans & Coalition Auto-Loader</span>
        </div>
        <div style="display: flex; gap: 0.4rem; align-items: center; flex-wrap: wrap;">
          <span style="font-size: 0.78rem; font-weight: 600; color: var(--text-dim); margin-right: 0.2rem;">Intel Source:</span>
          <button id="sim-source-all-btn" class="filter-pill-btn active" onclick="setScanSourceFilter('all')">
            🌐 All (<span id="sim-count-all">0</span>)
          </button>
          <button id="sim-source-user-btn" class="filter-pill-btn" onclick="setScanSourceFilter('user')">
            👤 My Scans (<span id="sim-count-user">0</span>)
          </button>
          <button id="sim-source-ally-btn" class="filter-pill-btn" onclick="setScanSourceFilter('ally')">
            🤝 Ally Intel (<span id="sim-count-ally">0</span>)
          </button>
          <span id="sim-alliance-badge" style="font-size: 0.74rem; color: var(--text-dim); font-family: var(--font-mono); margin-left: 0.4rem;">
            Alliance: Checking...
          </span>
        </div>
      </div>

      <!-- Two Side-By-Side Columns: Defender Intel Search (Left) and Attacker Intel Search (Right) -->
      <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(360px, 1fr)); gap: 1.25rem;">
        
        <!-- DEFENDER INTEL & COORDS SEARCH (Blue - Left) -->
        <div style="background: rgba(56, 189, 248, 0.03); border: 1px solid rgba(56, 189, 248, 0.25); border-radius: 8px; padding: 0.85rem;">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.55rem; flex-wrap: wrap; gap: 0.3rem;">
            <div style="font-size: 0.9rem; font-weight: 700; color: #38bdf8; display: flex; align-items: center; gap: 0.4rem;">
              🛡️ Defender Target & Coordinates
            </div>
            <div style="display: flex; gap: 0.3rem; align-items: center; flex-wrap: wrap;">
              <button class="btn-refresh" style="font-size: 0.72rem; padding: 0.2rem 0.55rem; color: #38bdf8; border-color: rgba(56,189,248,0.4);" onclick="loadMyEmpireIntoDefender()" title="Click to load your own colony base garrison & PDS into defender">
                🏰 Load My Defense
              </button>
              <button class="btn-refresh" style="font-size: 0.72rem; padding: 0.2rem 0.55rem; color: #ffd54f; border-color: rgba(255,213,79,0.4);" onclick="consolidateFleets('def')" title="Consolidate all defender fleets into 1 unified fleet">
                ⚡ Consolidate
              </button>
            </div>
          </div>

          <div style="display: flex; gap: 0.35rem; margin-bottom: 0.5rem;">
            <input type="text" id="sim-coords-input" class="form-control" placeholder="Search defender coords (e.g. 12:1:1)" style="font-size: 0.85rem; padding: 0.32rem 0.55rem; font-family: var(--font-mono); font-weight: 700; border-color: rgba(56,189,248,0.45); color: #fff; background: rgba(56,189,248,0.06);" oninput="onCoordsInputChanged('def', this.value)" onkeydown="if(event.key==='Enter') onCoordsInputEnter('def')">
            <button class="btn-refresh" style="padding: 0.2rem 0.55rem; font-size: 0.8rem;" onclick="clearCoordsFilter('def')" title="Clear Defender Coords">✕</button>
            <button class="btn-refresh" style="padding: 0.2rem 0.6rem; font-size: 0.74rem; font-weight: 600; color: #38bdf8; border-color: rgba(56,189,248,0.4); white-space: nowrap;" onclick="addFleetFromCurrentCoords('def')" title="Deploy a new defender fleet column for these coordinates">
              + Fleet for Coords
            </button>
          </div>

          <div style="margin-bottom: 0.5rem;">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.2rem;">
              <label style="font-size: 0.76rem; font-weight: 700; color: #38bdf8;">
                📡 Latest Scans for <span id="sim-coords-active-label" style="color: #fff; font-family: var(--font-mono);">Defender Coords</span>:
              </label>
              <span id="sim-coords-match-badge" style="font-size: 0.72rem; color: #38bdf8; font-family: var(--font-mono);">
                0 scan(s)
              </span>
            </div>
            <select id="sim-coords-scans-select" class="form-control" onchange="onCoordsScanSelected('def', this)" style="width: 100%; font-size: 0.8rem; padding: 0.3rem 0.5rem; border-color: rgba(56,189,248,0.4); background: rgba(56,189,248,0.08); color: #fff;">
              <option value="">Enter defender coords above to view scan history...</option>
            </select>
          </div>

          <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 0.4rem; font-size: 0.76rem;">
            <div>
              <span style="color: var(--text-dim); display: block; margin-bottom: 0.15rem;">Universe Planet:</span>
              <select id="sim-planet-quickpick" class="form-control" style="font-size: 0.78rem; padding: 0.22rem 0.45rem;" onchange="onPlanetQuickPick('def', this)">
                <option value="">Jump to planet...</option>
              </select>
            </div>
            <div>
              <span style="color: var(--text-dim); display: block; margin-bottom: 0.15rem;">All Scanned Targets:</span>
              <select id="sim-def-target" class="form-control" onchange="onTargetSelectChange('def', this)" style="font-size: 0.78rem; padding: 0.22rem 0.45rem;">
                <option value="">Pick any scanned target...</option>
              </select>
            </div>
          </div>
        </div>

        <!-- ATTACKER INTEL & COORDS SEARCH (Red - Right) -->
        <div style="background: rgba(239, 68, 68, 0.03); border: 1px solid rgba(239, 68, 68, 0.25); border-radius: 8px; padding: 0.85rem;">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.55rem; flex-wrap: wrap; gap: 0.3rem;">
            <div style="font-size: 0.9rem; font-weight: 700; color: #ef4444; display: flex; align-items: center; gap: 0.4rem;">
              🚀 Attacker Origin & Coordinates
            </div>
            <div style="display: flex; gap: 0.3rem; align-items: center; flex-wrap: wrap;">
              <button class="btn-refresh" style="font-size: 0.72rem; padding: 0.2rem 0.55rem; color: #f87171; border-color: rgba(239,68,68,0.4);" onclick="loadMyEmpireIntoAttacker()" title="Click to load your own colony's active fleets into the attacker roster">
                🏰 Load My Fleets
              </button>
              <button class="btn-refresh" style="font-size: 0.72rem; padding: 0.2rem 0.55rem; color: #ffd54f; border-color: rgba(255,213,79,0.4);" onclick="consolidateFleets('atk')" title="Consolidate all attacker fleets into 1 unified fleet">
                ⚡ Consolidate
              </button>
            </div>
          </div>

          <div style="display: flex; gap: 0.35rem; margin-bottom: 0.5rem;">
            <input type="text" id="sim-atk-coords-input" class="form-control" placeholder="Search attacker coords (e.g. 12:1:5)" style="font-size: 0.85rem; padding: 0.32rem 0.55rem; font-family: var(--font-mono); font-weight: 700; border-color: rgba(239,68,68,0.45); color: #fff; background: rgba(239,68,68,0.06);" oninput="onCoordsInputChanged('atk', this.value)" onkeydown="if(event.key==='Enter') onCoordsInputEnter('atk')">
            <button class="btn-refresh" style="padding: 0.2rem 0.55rem; font-size: 0.8rem;" onclick="clearCoordsFilter('atk')" title="Clear Attacker Coords">✕</button>
            <button class="btn-refresh" style="padding: 0.2rem 0.6rem; font-size: 0.74rem; font-weight: 600; color: #f87171; border-color: rgba(239,68,68,0.4); white-space: nowrap;" onclick="addFleetFromCurrentCoords('atk')" title="Deploy a new attacker fleet column for these coordinates">
              + Fleet for Coords
            </button>
          </div>

          <div style="margin-bottom: 0.5rem;">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.2rem;">
              <label style="font-size: 0.76rem; font-weight: 700; color: #f87171;">
                📡 Latest Scans for <span id="sim-atk-coords-active-label" style="color: #fff; font-family: var(--font-mono);">Attacker Coords</span>:
              </label>
              <span id="sim-atk-coords-match-badge" style="font-size: 0.72rem; color: #f87171; font-family: var(--font-mono);">
                0 scan(s)
              </span>
            </div>
            <select id="sim-atk-coords-scans-select" class="form-control" onchange="onCoordsScanSelected('atk', this)" style="width: 100%; font-size: 0.8rem; padding: 0.3rem 0.5rem; border-color: rgba(239,68,68,0.4); background: rgba(239,68,68,0.08); color: #fff;">
              <option value="">Enter attacker coords above to view scan history...</option>
            </select>
          </div>

          <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 0.4rem; font-size: 0.76rem;">
            <div>
              <span style="color: var(--text-dim); display: block; margin-bottom: 0.15rem;">Universe Planet:</span>
              <select id="sim-atk-planet-quickpick" class="form-control" style="font-size: 0.78rem; padding: 0.22rem 0.45rem;" onchange="onPlanetQuickPick('atk', this)">
                <option value="">Jump to planet...</option>
              </select>
            </div>
            <div>
              <span style="color: var(--text-dim); display: block; margin-bottom: 0.15rem;">All Scanned Targets:</span>
              <select id="sim-atk-target-select" class="form-control" onchange="onTargetSelectChange('atk', this)" style="font-size: 0.78rem; padding: 0.22rem 0.45rem;">
                <option value="">Pick any scanned target...</option>
              </select>
            </div>
          </div>
        </div>

      </div>

      <!-- Defender Target Details Card (if loaded) -->
      <div id="sim-def-scan-details" style="background: rgba(255,82,82,0.06); border: 1px solid rgba(255,82,82,0.25); border-radius: 6px; padding: 0.65rem 0.85rem; margin-top: 0.85rem; font-family: var(--font-mono); font-size: 0.82rem; display: none;">
        <div style="display: flex; justify-content: space-between; margin-bottom: 0.3rem; flex-wrap: wrap; gap: 0.5rem;">
          <span>Defender Target: <strong id="sim-def-coords" style="color: #ff5252;">Unknown</strong></span>
          <span>Type: <strong id="sim-def-type" style="color: var(--cyan);">---</strong></span>
          <span>Scan Tick: <strong id="sim-def-tick">---</strong></span>
        </div>
        <div style="color: var(--text-dim); font-size: 0.78rem; display: flex; gap: 1.2rem; flex-wrap: wrap; margin-bottom: 0.15rem;">
          <span>Resources: <strong id="sim-def-res-badge" style="color: var(--cyan);">0 M • 0 C • 0 E</strong></span>
          <span>Asteroids: <strong id="sim-def-roids-badge" style="color: #69f0ae;">0 M • 0 C • 0 E</strong></span>
        </div>
        <div id="sim-def-scan-fleet-options" style="margin-top: 0.5rem; display: flex; gap: 0.35rem; align-items: center; flex-wrap: wrap;"></div>
        <div id="sim-def-blocked-banner" style="display: none; margin-top: 0.45rem; padding: 0.4rem 0.65rem; border-radius: 4px; background: rgba(234, 179, 8, 0.15); border: 1px solid var(--yellow); color: var(--yellow); font-size: 0.8rem;">
          ⚠️ <strong>Wave Distorter Active:</strong> Enemy planetary defenses blocked this scan. No fleet or structural intel was retrieved.
        </div>
      </div>

      <!-- Attacker Target Details Card (if loaded) -->
      <div id="sim-atk-scan-details" style="background: rgba(0,229,255,0.06); border: 1px solid rgba(0,229,255,0.25); border-radius: 6px; padding: 0.65rem 0.85rem; margin-top: 0.85rem; font-family: var(--font-mono); font-size: 0.82rem; display: none;">
        <div style="display: flex; justify-content: space-between; margin-bottom: 0.3rem; flex-wrap: wrap; gap: 0.5rem;">
          <span>Attacker Target/Intel: <strong id="sim-atk-coords" style="color: var(--cyan);">Unknown</strong></span>
          <span>Type: <strong id="sim-atk-type" style="color: var(--cyan);">---</strong></span>
          <span>Scan Tick: <strong id="sim-atk-tick">---</strong></span>
        </div>
        <div style="color: var(--text-dim); font-size: 0.78rem; display: flex; gap: 1.2rem; flex-wrap: wrap; margin-bottom: 0.15rem;">
          <span>Resources: <strong id="sim-atk-res-badge" style="color: var(--cyan);">0 M • 0 C • 0 E</strong></span>
          <span>Asteroids: <strong id="sim-atk-roids-badge" style="color: #69f0ae;">0 M • 0 C • 0 E</strong></span>
        </div>
        <div id="sim-atk-scan-fleet-options" style="margin-top: 0.5rem; display: flex; gap: 0.35rem; align-items: center; flex-wrap: wrap;"></div>
        <div id="sim-atk-blocked-banner" style="display: none; margin-top: 0.45rem; padding: 0.4rem 0.65rem; border-radius: 4px; background: rgba(234, 179, 8, 0.15); border: 1px solid var(--yellow); color: var(--yellow); font-size: 0.8rem;">
          ⚠️ <strong>Wave Distorter Active:</strong> Enemy planetary defenses blocked this scan. No fleet or structural intel was retrieved.
        </div>
      </div>
    </div>

    <!-- Two-Column Army Setup Grid (Cards View) -->
    <div id="sim-cards-view-container" style="display: none; grid-template-columns: repeat(auto-fit, minmax(350px, 1fr)); gap: 1.5rem; margin-bottom: 1.5rem;">
      
      <!-- DEFENDER PANEL (Red Accent - Left) -->
      <div class="panel" style="border-top: 3px solid #ff5252;">
        <div class="panel-header" style="display: flex; justify-content: space-between; align-items: center;">
          <div>
            <div class="panel-title" id="sim-def-title" style="color: #ff5252;">🛡️ Defender Forces (Base Garrison, Fleets & PDS)</div>
            <div style="font-size: 0.75rem; color: var(--text-dim); margin-top: 0.15rem;">Live intel or home base • Garrison & docked fleets auto-loaded</div>
          </div>
          <div style="display: flex; gap: 0.4rem; align-items: center; flex-wrap: wrap;">
            <button class="btn-refresh" style="padding: 0.25rem 0.65rem; font-size: 0.8rem; font-weight: 600; color: #ff5252; border-color: rgba(255,82,82,0.4);" onclick="addDefenderFleet()" title="Add an extra defender garrison or reinforcement fleet card">
              + Custom Fleet
            </button>
            <select id="sim-def-add-empire-select" class="form-control" style="font-size: 0.78rem; padding: 0.22rem 0.5rem; max-width: 220px; border-color: rgba(255,82,82,0.4); color: #ff8a80; background: rgba(255,82,82,0.06);" onchange="onQuickAddEmpireSelect('def', this)" title="Add one of your own fleets or base garrison to defense">
              <option value="">🏰 Add Own Fleet...</option>
            </select>
            <button class="btn-refresh" style="padding: 0.25rem 0.65rem; font-size: 0.8rem; font-weight: 600; color: #ff8a80; border-color: rgba(255,138,128,0.4);" onclick="openScanPickerModal('def')" title="Browse all scanned fleets to pick from">
              🔍 Browse Scans
            </button>
          </div>
        </div>

        <!-- Defender Target Notice -->
        <div style="background: rgba(56,189,248,0.05); border: 1px solid rgba(56,189,248,0.25); border-radius: 6px; padding: 0.55rem 0.8rem; margin-bottom: 0.85rem; font-size: 0.78rem; display: flex; justify-content: space-between; align-items: center;">
          <span style="color: var(--text-dim);">Target intel auto-loaded from the <strong style="color: #38bdf8;">Defender Coordinates Explorer</strong> above.</span>
          <button class="btn-refresh" style="font-size: 0.72rem; padding: 0.15rem 0.45rem; color: #38bdf8; border-color: rgba(56,189,248,0.4);" onclick="document.getElementById('sim-coords-input').focus()">🎯 Focus Coordinates</button>
        </div>

        <!-- Planetary Defense Structures (PDS) & Shield -->
        <div style="background: rgba(255,255,255,0.02); border: 1px solid rgba(255,255,255,0.06); border-radius: 6px; padding: 0.75rem; margin-bottom: 1rem;">
          <div style="font-size: 0.8rem; font-weight: 700; color: #ffd54f; margin-bottom: 0.5rem; display: flex; justify-content: space-between;">
            <span>🛡️ Orbital & Surface Base Defenses (PDS)</span>
            <span style="font-weight: 400; color: var(--text-dim); font-size: 0.75rem;">Protects Home Base Planet</span>
          </div>
          <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 0.5rem; font-size: 0.78rem;">
            <label style="display: flex; align-items: center; gap: 0.4rem;">
              <input type="checkbox" id="sim-pds-shield-chk" checked>
              <span>🌐 Shield (Lvl <input type="number" id="sim-pds-shield-lvl" value="3" min="1" max="5" style="width: 38px; padding: 0.1rem; background: var(--bg-space); border: 1px solid rgba(255,255,255,0.2); color: #fff; border-radius: 3px;">)</span>
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

      <!-- ATTACKER PANEL (Cyan Accent - Right) -->
      <div class="panel" style="border-top: 3px solid var(--cyan);">
        <div class="panel-header" style="display: flex; justify-content: space-between; align-items: center;">
          <div>
            <div class="panel-title" id="sim-atk-title" style="color: var(--cyan);">🚀 Attacker Forces (Coalition Fleets)</div>
            <div style="font-size: 0.75rem; color: var(--text-dim); margin-top: 0.15rem;">Multi-attacker coalition • Toggle, add, or edit fleets</div>
          </div>
          <div style="display: flex; gap: 0.4rem; align-items: center; flex-wrap: wrap;">
            <button class="btn-refresh" style="padding: 0.25rem 0.65rem; font-size: 0.8rem; font-weight: 600; color: var(--cyan); border-color: rgba(0,229,255,0.4);" onclick="addAttackerFleet()" title="Add a custom editable fleet card">
              + Custom Fleet
            </button>
            <select id="sim-atk-add-empire-select" class="form-control" style="font-size: 0.78rem; padding: 0.22rem 0.5rem; max-width: 220px; border-color: rgba(0,229,255,0.4); color: var(--cyan); background: rgba(0,229,255,0.06);" onchange="onQuickAddEmpireSelect('atk', this)" title="Add one of your own fleets or base garrison">
              <option value="">🏰 Add Own Fleet...</option>
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
            <span>Mining Capacity: <strong id="sim-atk-total-miners" style="color: #69f0ae;">0 roids</strong></span>
            <span>Assault Speed: <strong id="sim-atk-slowest-speed" style="color: var(--text-dim);">--</strong></span>
          </div>
        </div>

        <!-- Attacker Coalition Technology Multipliers -->
        <div style="background: rgba(0,0,0,0.2); border: 1px solid rgba(255,255,255,0.05); border-radius: 6px; padding: 0.6rem 0.75rem; margin-bottom: 1rem; display: flex; gap: 1rem; align-items: center; font-size: 0.8rem;">
          <span style="font-weight: 600; color: var(--text-dim);">Attacker Research:</span>
          <label style="display: flex; align-items: center; gap: 0.35rem;">
            <span>Hulls Tech:</span>
            <input type="number" id="sim-atk-hulls" value="5" min="0" max="25" style="width: 44px; padding: 0.15rem 0.3rem; background: var(--bg-space); border: 1px solid rgba(255,255,255,0.2); color: #fff; border-radius: 3px;" onchange="recalcCoalitionSummary('atk')">
          </label>
          <label style="display: flex; align-items: center; gap: 0.35rem;">
            <span>Ship Tech:</span>
            <input type="number" id="sim-atk-shiptech" value="5" min="0" max="25" style="width: 44px; padding: 0.15rem 0.3rem; background: var(--bg-space); border: 1px solid rgba(255,255,255,0.2); color: #fff; border-radius: 3px;" onchange="recalcCoalitionSummary('atk')">
          </label>
        </div>

        <!-- Multi-Fleet Cards Container -->
        <div id="sim-atk-fleets-container" style="display: flex; flex-direction: column; gap: 0.75rem;">
          <div style="color: var(--text-dim); font-size: 0.85rem; font-style: italic;">Loading attacker fleets...</div>
        </div>
      </div>
    </div>

    <!-- Combat Matrix Mode View Container -->
    <div id="sim-bcalc-view-container" style="display: block; margin-bottom: 1.5rem;">
      <div class="panel" style="border-top: 3px solid #f59e0b;">
        <div class="panel-header" style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 0.5rem;">
          <div style="display: flex; align-items: center; gap: 0.75rem;">
            <span style="font-size: 1.1rem; font-weight: 700; color: #f59e0b;">📊 Combat Matrix Mode</span>
            <span class="badge" style="background: rgba(245, 158, 11, 0.15); color: #f59e0b; border: 1px solid #f59e0b; font-size: 0.72rem;">Side-by-Side Fleet Columns</span>
          </div>
          <div style="display: flex; gap: 0.35rem; align-items: center; flex-wrap: wrap;">
            <span style="font-size: 0.72rem; color: var(--text-dim); margin-right: 0.15rem;">Hull:</span>
            <button class="bcalc-filter-btn active" onclick="setBcalcHullFilter('ALL')">All</button>
            <button class="bcalc-filter-btn" onclick="setBcalcHullFilter('FIGHTER')">Fi</button>
            <button class="bcalc-filter-btn" onclick="setBcalcHullFilter('CORVETTE')">Co</button>
            <button class="bcalc-filter-btn" onclick="setBcalcHullFilter('FRIGATE')">Fr</button>
            <button class="bcalc-filter-btn" onclick="setBcalcHullFilter('DESTROYER')">De</button>
            <button class="bcalc-filter-btn" onclick="setBcalcHullFilter('CRUISER')">Cr</button>
            <button class="bcalc-filter-btn" onclick="setBcalcHullFilter('BATTLESHIP')">Bs</button>
            <button class="bcalc-filter-btn" onclick="setBcalcHullFilter('PDS')">PDS</button>
            <span style="border-left: 1px solid rgba(255,255,255,0.15); height: 16px; margin: 0 0.2rem;"></span>
            <button class="bcalc-filter-btn" onclick="addDefenderFleet()" style="color: #ff5252; border-color: rgba(255,82,82,0.3);">+ Def Fleet</button>
            <button class="bcalc-filter-btn" onclick="addAttackerFleet()" style="color: var(--cyan); border-color: rgba(0,229,255,0.3);">+ Att Fleet</button>
            <button class="bcalc-filter-btn" onclick="emptyAllFleets()" style="color: #cbd5e1;">Empty (E)</button>
            <button class="bcalc-filter-btn" onclick="resetCombatSimulator()" style="color: #f87171; border-color: rgba(239,68,68,0.4); background: rgba(239,68,68,0.1);">🔄 Reset</button>
            <span style="border-left: 1px solid rgba(255,255,255,0.15); height: 16px; margin: 0 0.2rem;"></span>
            <span style="font-size: 0.72rem; color: var(--text-dim);">Resize:</span>
            <button id="bcalc-toggle-width-btn" class="bcalc-filter-btn active" onclick="toggleBcalcWideMode()" title="Toggle wide/full-screen matrix layout">🖥️ Full Width</button>
            <button id="bcalc-zoom-auto-btn" class="bcalc-filter-btn active" onclick="setBcalcZoom('auto')" title="Automatically resize columns to fit all fleets">Auto-Fit</button>
            <button id="bcalc-zoom-100-btn" class="bcalc-filter-btn" onclick="setBcalcZoom('100')">100%</button>
            <button id="bcalc-zoom-85-btn" class="bcalc-filter-btn" onclick="setBcalcZoom('85')">85%</button>
            <button id="bcalc-zoom-70-btn" class="bcalc-filter-btn" onclick="setBcalcZoom('70')">70%</button>
          </div>
        </div>

        <div style="font-size: 0.78rem; color: var(--text-dim); margin-bottom: 0.75rem;">
          Side-by-side combat grid in Matrix Mode. Columns automatically shrink to fit your screen. Numbers entered here directly mirror the coalition fleet cards and vice-versa.
        </div>

        <!-- Matrix Dual-Side Fleet & Intel Action Bar -->
        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(440px, 1fr)); gap: 1rem; margin-bottom: 0.85rem; padding: 0.75rem 0.95rem; background: rgba(0,0,0,0.32); border: 1px solid rgba(255,255,255,0.08); border-radius: 6px;">
          
          <!-- Defender Side Controls (Blue Accent - Left) -->
          <div style="border-left: 3px solid #38bdf8; padding-left: 0.75rem; display: flex; flex-direction: column; gap: 0.45rem;">
            <!-- Row 1: Side Header & Primary Fleet Actions -->
            <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 0.4rem;">
              <div style="display: flex; align-items: center; gap: 0.4rem;">
                <span style="font-size: 0.85rem; font-weight: 700; color: #38bdf8;">🛡️ Defender Fleet Controls</span>
                <span style="font-size: 0.7rem; color: var(--text-dim);">(Base & Reinforcements)</span>
              </div>
              <div style="display: flex; gap: 0.3rem; align-items: center; flex-wrap: wrap;">
                <button class="btn-refresh" style="padding: 0.22rem 0.55rem; font-size: 0.76rem; font-weight: 600; color: #38bdf8; border-color: rgba(56,189,248,0.45);" onclick="addDefenderFleet()" title="Add a custom defender fleet column">
                  + Def Fleet
                </button>
                <button class="btn-refresh" style="padding: 0.22rem 0.55rem; font-size: 0.76rem; font-weight: 600; color: #38bdf8; border-color: rgba(56,189,248,0.45);" onclick="loadMyEmpireIntoDefender()" title="Load your home defense garrison & PDS into defender (overwrites garrison)">
                  🏰 Load Base
                </button>
                <button class="btn-refresh" style="padding: 0.22rem 0.55rem; font-size: 0.76rem; font-weight: 600; color: #ffd54f; border-color: rgba(255,213,79,0.4);" onclick="consolidateFleets('def')" title="Consolidate all defender fleets into 1 unified column">
                  ⚡ Consolidate
                </button>
                <button class="btn-refresh" style="padding: 0.22rem 0.55rem; font-size: 0.76rem; font-weight: 600; color: #38bdf8; border-color: rgba(56,189,248,0.4);" onclick="openScanPickerModal('def')" title="Browse all scanned fleets to pick into Defender side">
                  🔍 Browse Scans
                </button>
                <button class="btn-refresh" style="padding: 0.22rem 0.55rem; font-size: 0.76rem; font-weight: 700; color: #38bdf8; border-color: rgba(56,189,248,0.5); background: rgba(56,189,248,0.08);" onclick="openExecuteScanModal('def')" title="Execute live scan on target coordinates and deploy into Defender">
                  📡 Add from Scan
                </button>
              </div>
            </div>
            <!-- Row 2: Selectors, Coords & Scanned Targets -->
            <div style="display: flex; gap: 0.4rem; align-items: center; flex-wrap: wrap; font-size: 0.75rem;">
              <select id="sim-bcalc-def-add-empire-select" class="form-control" style="font-size: 0.75rem; padding: 0.2rem 0.45rem; max-width: 170px; border-color: rgba(56,189,248,0.4); color: #38bdf8; background: rgba(56,189,248,0.06);" onchange="onQuickAddEmpireSelect('def', this)" title="Add one of your own fleets or base garrison to defense">
                <option value="">🏰 Add Own Fleet...</option>
              </select>
              <div style="display: flex; align-items: center; gap: 0.25rem;">
                <span style="color: var(--text-dim); font-size: 0.72rem;">Coords:</span>
                <input type="text" id="sim-bcalc-def-coords-input" placeholder="e.g. 12:1:5" style="width: 76px; padding: 0.16rem 0.35rem; font-size: 0.75rem; font-family: var(--font-mono); background: var(--bg-space); border: 1px solid rgba(56,189,248,0.45); color: #fff; border-radius: 3px;" oninput="syncBcalcCoordsInput('def', this.value)" onkeydown="if(event.key==='Enter') onCoordsInputEnter('def')">
                <button class="btn-refresh" style="font-size: 0.72rem; padding: 0.16rem 0.45rem; color: #38bdf8; border-color: rgba(56,189,248,0.45);" onclick="addFleetFromCurrentCoords('def')" title="Deploy a new defender fleet column for these coordinates">+ Fleet</button>
              </div>
              <select id="sim-bcalc-def-target-select" class="form-control" onchange="onTargetSelectChange('def', this)" style="font-size: 0.74rem; padding: 0.16rem 0.35rem; max-width: 180px;">
                <option value="">Pick scanned target...</option>
              </select>
            </div>
          </div>

          <!-- Attacker Side Controls (Red Accent - Right) -->
          <div style="border-left: 3px solid #ef4444; padding-left: 0.75rem; display: flex; flex-direction: column; gap: 0.45rem;">
            <!-- Row 1: Side Header & Primary Fleet Actions -->
            <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 0.4rem;">
              <div style="display: flex; align-items: center; gap: 0.4rem;">
                <span style="font-size: 0.85rem; font-weight: 700; color: #ef4444;">🚀 Attacker Fleet Controls</span>
                <span style="font-size: 0.7rem; color: var(--text-dim);">(Coalition & Strikes)</span>
              </div>
              <div style="display: flex; gap: 0.3rem; align-items: center; flex-wrap: wrap;">
                <button class="btn-refresh" style="padding: 0.22rem 0.55rem; font-size: 0.76rem; font-weight: 600; color: #f87171; border-color: rgba(239,68,68,0.45);" onclick="addAttackerFleet()" title="Add a custom attacker fleet column">
                  + Att Fleet
                </button>
                <button class="btn-refresh" style="padding: 0.22rem 0.55rem; font-size: 0.76rem; font-weight: 600; color: #f87171; border-color: rgba(239,68,68,0.45);" onclick="loadMyEmpireIntoAttacker()" title="Load your active empire fleets into attacker">
                  🏰 Load Fleets
                </button>
                <button class="btn-refresh" style="padding: 0.22rem 0.55rem; font-size: 0.76rem; font-weight: 600; color: #ffd54f; border-color: rgba(255,213,79,0.4);" onclick="consolidateFleets('atk')" title="Consolidate all attacker fleets into 1 unified column">
                  ⚡ Consolidate
                </button>
                <button class="btn-refresh" style="padding: 0.22rem 0.55rem; font-size: 0.76rem; font-weight: 600; color: #f87171; border-color: rgba(239,68,68,0.4);" onclick="openScanPickerModal('atk')" title="Browse all scanned fleets to pick into Attacker side">
                  🔍 Browse Scans
                </button>
                <button class="btn-refresh" style="padding: 0.22rem 0.55rem; font-size: 0.76rem; font-weight: 700; color: #ef4444; border-color: rgba(239,68,68,0.5); background: rgba(239,68,68,0.08);" onclick="openExecuteScanModal('atk')" title="Execute live scan on target coordinates and deploy into Attacker">
                  📡 Add from Scan
                </button>
              </div>
            </div>
            <!-- Row 2: Selectors, Coords & Scanned Targets -->
            <div style="display: flex; gap: 0.4rem; align-items: center; flex-wrap: wrap; font-size: 0.75rem;">
              <select id="sim-bcalc-atk-add-empire-select" class="form-control" style="font-size: 0.75rem; padding: 0.2rem 0.45rem; max-width: 170px; border-color: rgba(239,68,68,0.4); color: #f87171; background: rgba(239,68,68,0.06);" onchange="onQuickAddEmpireSelect('atk', this)" title="Add one of your own fleets to attack">
                <option value="">🏰 Add Own Fleet...</option>
              </select>
              <div style="display: flex; align-items: center; gap: 0.25rem;">
                <span style="color: var(--text-dim); font-size: 0.72rem;">Coords:</span>
                <input type="text" id="sim-bcalc-atk-coords-input" placeholder="e.g. 12:1:1" style="width: 76px; padding: 0.16rem 0.35rem; font-size: 0.75rem; font-family: var(--font-mono); background: var(--bg-space); border: 1px solid rgba(239,68,68,0.45); color: #fff; border-radius: 3px;" oninput="syncBcalcCoordsInput('atk', this.value)" onkeydown="if(event.key==='Enter') onCoordsInputEnter('atk')">
                <button class="btn-refresh" style="font-size: 0.72rem; padding: 0.16rem 0.45rem; color: #f87171; border-color: rgba(239,68,68,0.45);" onclick="addFleetFromCurrentCoords('atk')" title="Deploy a new attacker fleet column for these coordinates">+ Fleet</button>
              </div>
              <select id="sim-bcalc-atk-target-select" class="form-control" onchange="onTargetSelectChange('atk', this)" style="font-size: 0.74rem; padding: 0.16rem 0.35rem; max-width: 180px;">
                <option value="">Pick scanned target...</option>
              </select>
            </div>
          </div>
        </div>

        <!-- Rendered Matrix Table Container -->
        <div class="bcalc-table-wrapper" id="bcalc-matrix-container">
          <div style="color: var(--text-dim); text-align: center; padding: 2rem;">Loading Combat Matrix...</div>
        </div>

        <!-- Bottom Scan Coordinates & Battle Reference Bar (Editable, No Side-Effects) -->
        <div id="sim-bcalc-bottom-bar" style="margin-top: 0.65rem; padding: 0.6rem 0.95rem; background: rgba(0,0,0,0.38); border: 1px solid rgba(255,255,255,0.09); border-radius: 6px; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 0.75rem;">
          <div style="display: flex; align-items: center; gap: 0.6rem; flex-wrap: wrap;">
            <span style="font-size: 0.78rem; font-weight: 700; color: var(--cyan); letter-spacing: 0.04em;">
              📍 Coordinates of Scan:
            </span>
            <input type="text" id="sim-bcalc-bottom-coords" placeholder="e.g. 12:1:1" style="width: 110px; padding: 0.22rem 0.5rem; font-size: 0.8rem; font-family: var(--font-mono); background: var(--bg-space); border: 1px solid rgba(0,229,255,0.45); color: #fff; border-radius: 4px; text-align: center; font-weight: 700;" title="Editable coordinates reference label (has no side-effects on simulation fleets)">
            <span style="font-size: 0.7rem; color: var(--text-dim); font-style: italic;">
              (Reference label • Editable for battle notes/reports • Does not alter simulator fleets)
            </span>
          </div>
          <div style="display: flex; align-items: center; gap: 1rem; font-size: 0.76rem; font-family: var(--font-mono);">
            <span style="color: #38bdf8;">🛡️ Def Ships: <strong id="sim-bcalc-bottom-def-count" style="color: #fff;">0</strong></span>
            <span style="color: rgba(255,255,255,0.2);">|</span>
            <span style="color: #f87171;">🚀 Atk Ships: <strong id="sim-bcalc-bottom-atk-count" style="color: #fff;">0</strong></span>
          </div>
        </div>
      </div>
    </div>

    <!-- ACTION BAR -->
    <div style="background: rgba(10, 20, 36, 0.9); border: 1px solid var(--border-glow); border-radius: 8px; padding: 1.25rem; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 1rem; margin-bottom: 2rem;">
      <div style="display: flex; align-items: center; gap: 1rem; flex-wrap: wrap;">
        <span style="font-size: 0.9rem; font-weight: 600;">Max Combat Rounds:</span>
        <select id="sim-max-rounds" class="form-control" style="width: 80px;">
          <option value="1" selected>1</option>
          <option value="3">3</option>
          <option value="6">6</option>
          <option value="10">10</option>
        </select>
        <button class="btn-refresh" onclick="openCalcShareModal()" title="Share calculation via public link or MCP" style="padding: 0.45rem 1rem; font-size: 0.85rem; color: var(--cyan); border-color: rgba(0,229,255,0.4); background: rgba(0,229,255,0.08);">
          🔗 Share Link
        </button>
        <button class="btn-refresh" onclick="openCalcImportModal()" title="Import a calculation link or code string" style="padding: 0.45rem 1rem; font-size: 0.85rem; color: #86efac; border-color: rgba(34,197,94,0.4); background: rgba(34,197,94,0.08);">
          📥 Import
        </button>
        <button class="btn-refresh" onclick="resetCombatSimulator()" title="Reset all fleets, coordinates, scans and results to clean state" style="padding: 0.45rem 1rem; font-size: 0.85rem; color: #f87171; border-color: rgba(239, 68, 68, 0.4); background: rgba(239, 68, 68, 0.1);">
          🔄 Reset
        </button>
        <button class="btn-refresh" onclick="startFreshCalculation()" title="Start a fresh calculation from scratch" style="padding: 0.45rem 1rem; font-size: 0.85rem; color: #38bdf8; border-color: rgba(56,189,248,0.4); background: rgba(56,189,248,0.08);">
          ✨ Start Fresh
        </button>
        <button class="btn-refresh" onclick="popOutCalculatorToWindow()" title="Pop this calculation out into an independent browser window" style="padding: 0.45rem 1rem; font-size: 0.85rem; color: #a5b4fc; border-color: rgba(165,180,252,0.45); background: rgba(99,102,241,0.12);">
          ↗️ Pop Out Window
        </button>
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
    <div>🌌 Pegasus Galaxy MCP Suite <strong style="color: var(--cyan);">v0.5</strong> • Cross-Platform (macOS / Linux / Windows)</div>
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
        <div id="sim-picker-subtitle" style="font-size: 0.78rem; color: var(--text-dim); margin-top: 0.2rem; display: flex; align-items: center; gap: 0.75rem; flex-wrap: wrap;">
          <span>Select any scanned garrison or fleet from your recent intel to deploy</span>
          <span id="sim-picker-sync-status" style="color: #86efac; font-family: var(--font-mono); font-size: 0.72rem;">🟢 Auto-syncing alliance intel (every 30s)</span>
        </div>
      </div>
      <div style="display: flex; gap: 0.5rem; align-items: center;">
        <button type="button" class="btn-refresh" style="font-size: 0.76rem; padding: 0.25rem 0.65rem; color: var(--cyan); border-color: rgba(0,229,255,0.4);" onclick="refreshScanTargets(false)" title="Fetch latest scans from server & alliance">
          🔄 Sync Intel Now
        </button>
        <button class="btn-refresh" style="font-size: 1.2rem; padding: 0.2rem 0.6rem; line-height: 1;" onclick="closeScanPickerModal()">✕</button>
      </div>
    </div>

    <div style="padding: 0.75rem 1.25rem; border-bottom: 1px solid rgba(255,255,255,0.06); display: flex; gap: 0.6rem; align-items: center; flex-wrap: wrap;">
      <input type="text" id="sim-picker-search" class="form-control" placeholder="🔍 Filter by coords (e.g. 12:1:1), scan type, ship name, or ally..." style="font-size: 0.85rem; flex: 1; min-width: 220px;" oninput="renderScanPickerList()">
      <div style="display: flex; gap: 0.3rem; align-items: center;">
        <button id="sim-picker-src-all-btn" class="filter-pill-btn active" onclick="setPickerSourceFilter('all')">🌐 All</button>
        <button id="sim-picker-src-user-btn" class="filter-pill-btn" onclick="setPickerSourceFilter('user')">👤 My Scans</button>
        <button id="sim-picker-src-ally-btn" class="filter-pill-btn" onclick="setPickerSourceFilter('ally')">🤝 Ally Intel</button>
      </div>
    </div>

    <div id="sim-picker-list" style="overflow-y: auto; padding: 1rem 1.25rem; display: flex; flex-direction: column; gap: 0.75rem; flex: 1;">
    </div>
  </div>
</div>

<!-- Interactive Execute Scan & Add to Fleet Modal -->
<div id="sim-execute-scan-modal" style="display: none; position: fixed; inset: 0; z-index: 10000; background: rgba(5, 7, 15, 0.88); backdrop-filter: blur(5px); align-items: center; justify-content: center; padding: 1.5rem;" onclick="if(event.target === this) closeExecuteScanModal()">
  <div style="background: #0d1222; border: 1px solid rgba(0,229,255,0.4); border-radius: 10px; width: 100%; max-width: 640px; max-height: 90vh; display: flex; flex-direction: column; box-shadow: 0 12px 50px rgba(0,0,0,0.85); overflow: hidden;" onclick="event.stopPropagation()">
    
    <!-- Modal Header -->
    <div style="padding: 1.1rem 1.4rem; border-bottom: 1px solid rgba(255,255,255,0.08); display: flex; justify-content: space-between; align-items: center; background: rgba(0,0,0,0.25);">
      <div>
        <div id="exec-scan-title" style="font-size: 1.1rem; font-weight: 700; color: var(--cyan); display: flex; align-items: center; gap: 0.5rem;">
          📡 Execute Planetary Scan & Deploy Fleet
        </div>
        <div style="font-size: 0.78rem; color: var(--text-dim); margin-top: 0.2rem;">
          Trigger live game intelligence to scan planet defenses and auto-deploy into combat matrix
        </div>
      </div>
      <button class="btn-refresh" style="font-size: 1.2rem; padding: 0.2rem 0.6rem; line-height: 1;" onclick="closeExecuteScanModal()">✕</button>
    </div>

    <!-- Modal Body -->
    <div style="padding: 1.25rem 1.4rem; overflow-y: auto; display: flex; flex-direction: column; gap: 1.1rem;">
      
      <!-- Target Side & Coordinates Group -->
      <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 0.85rem;">
        <div>
          <label style="display: block; font-size: 0.78rem; font-weight: 700; color: var(--text-main); margin-bottom: 0.35rem;">
            🎯 Deploy Fleet Into Side:
          </label>
          <div style="display: flex; gap: 0.5rem;">
            <button type="button" id="exec-scan-side-def-btn" class="filter-pill-btn active" style="flex: 1; text-align: center; border-color: rgba(255,82,82,0.5); color: #ff8a80;" onclick="setExecScanSide('def')">
              🛡️ Defender
            </button>
            <button type="button" id="exec-scan-side-atk-btn" class="filter-pill-btn" style="flex: 1; text-align: center; border-color: rgba(0,229,255,0.5); color: var(--cyan);" onclick="setExecScanSide('atk')">
              🚀 Attacker
            </button>
          </div>
        </div>

        <div>
          <label style="display: block; font-size: 0.78rem; font-weight: 700; color: var(--text-main); margin-bottom: 0.35rem;">
            📍 Target Coordinates:
          </label>
          <div style="display: flex; gap: 0.35rem;">
            <input type="text" id="exec-scan-coords" class="form-control" placeholder="e.g. 12:1:1" style="font-family: var(--font-mono); font-weight: 700; font-size: 0.9rem;" oninput="onExecScanCoordsInput(this.value)">
            <select id="exec-scan-planet-quickpick" class="form-control" style="max-width: 140px; font-size: 0.76rem;" onchange="onExecScanQuickPick(this.value)">
              <option value="">Jump...</option>
            </select>
          </div>
          <div id="exec-scan-planet-label" style="font-size: 0.72rem; color: var(--cyan); margin-top: 0.25rem; font-family: var(--font-mono); min-height: 1rem;"></div>
        </div>
      </div>

      <!-- Scan Type Chooser -->
      <div>
        <label style="display: block; font-size: 0.78rem; font-weight: 700; color: var(--text-main); margin-bottom: 0.35rem;">
          🔬 Select Scan Type:
        </label>
        <select id="exec-scan-type" class="form-control" style="width: 100%; font-size: 0.85rem; font-weight: 600;" onchange="onExecScanTypeChange()">
          <option value="MILITARY_SCAN" selected>⚡ MILITARY SCAN (Recommended — Garrison, docked fleets, base PDS & tech)</option>
          <option value="FLEET_COMPOSITION_SCAN">🚀 FLEET COMPOSITION SCAN (Detailed ship types & fleet distributions)</option>
          <option value="DEEP_SCAN">🔍 DEEP SCAN (Comprehensive planetary, economic & fleet manifest)</option>
          <option value="INCOMING_SCAN">🎯 INCOMING SCAN (Hostile and friendly fleets in transit toward planet)</option>
          <option value="SURFACE_SCAN">🏛️ SURFACE SCAN (Basic constructions, mines, defenses)</option>
        </select>
        <div id="exec-scan-type-desc" style="font-size: 0.74rem; color: var(--text-dim); margin-top: 0.3rem; line-height: 1.4;">
          Scans all defending ships, docked named fleets, orbital PDS structures, and military research levels.
        </div>
      </div>

      <!-- Ingestion Mode -->
      <div>
        <label style="display: block; font-size: 0.78rem; font-weight: 700; color: var(--text-main); margin-bottom: 0.35rem;">
          📦 Ingestion Into Matrix:
        </label>
        <div style="display: flex; gap: 0.5rem; flex-wrap: wrap;">
          <label style="display: flex; align-items: center; gap: 0.35rem; font-size: 0.78rem; cursor: pointer;">
            <input type="radio" name="exec-ingest-mode" value="consolidated" checked>
            <span>⚡ All Consolidated (Combine all detected fleets into 1 column)</span>
          </label>
          <label style="display: flex; align-items: center; gap: 0.35rem; font-size: 0.78rem; cursor: pointer;">
            <input type="radio" name="exec-ingest-mode" value="garrison">
            <span>🏛️ Garrison Only</span>
          </label>
        </div>
      </div>

      <!-- Action Restrictions & Quota Bar -->
      <div style="background: rgba(0,0,0,0.35); border: 1px solid rgba(255,255,255,0.08); border-radius: 6px; padding: 0.75rem 0.95rem; font-family: var(--font-mono); font-size: 0.78rem;">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.4rem; flex-wrap: wrap; gap: 0.5rem;">
          <span>⚡ Scans This Tick: <strong id="exec-scan-quota-badge" style="color: #69f0ae;">0 / 3 Used (3 Remaining)</strong></span>
          <span>Tick: <strong id="exec-scan-tick-badge" style="color: var(--cyan);">---</strong></span>
        </div>
        <div style="display: flex; justify-content: space-between; align-items: center; font-size: 0.74rem; color: var(--text-dim); flex-wrap: wrap; gap: 0.5rem;">
          <span>Eonium Reserves: <strong id="exec-scan-eonium-badge" style="color: #ffd54f;">---</strong></span>
          <span>Wave Amplifier: <strong style="color: #fff;">Required</strong></span>
        </div>
      </div>

      <!-- Action Warnings -->
      <div style="background: rgba(234, 179, 8, 0.08); border: 1px solid rgba(234, 179, 8, 0.35); border-radius: 6px; padding: 0.75rem 0.95rem; font-size: 0.76rem; color: #fde047; line-height: 1.5;">
        <div style="font-weight: 700; margin-bottom: 0.25rem; display: flex; align-items: center; gap: 0.35rem;">
          ⚠️ Scan Restrictions & Planetary Defense Warnings:
        </div>
        <ul style="margin: 0; padding-left: 1.2rem; color: rgba(255,255,255,0.85);">
          <li><strong>Wave Distorters:</strong> If the target planet has active Wave Distorter defenses, this scan may be scrambled or blocked.</li>
          <li><strong>Cloaking:</strong> Cloaked warships are concealed from standard planetary wave scans.</li>
          <li><strong>Rate Limit:</strong> Pegasus servers enforce a strict limit of <strong>3 wave scans per tick</strong>.</li>
        </ul>
      </div>

      <!-- Error / Restrictions Alert Banner -->
      <div id="exec-scan-error" style="display: none; background: rgba(239, 68, 68, 0.15); border: 1px solid #ef4444; border-radius: 6px; padding: 0.75rem; color: #fca5a5; font-size: 0.8rem; line-height: 1.4;"></div>

    </div>

    <!-- Modal Footer Actions -->
    <div style="padding: 0.9rem 1.4rem; border-top: 1px solid rgba(255,255,255,0.08); display: flex; justify-content: space-between; align-items: center; background: rgba(0,0,0,0.3);">
      <button type="button" class="btn-refresh" onclick="closeExecuteScanModal()" style="font-size: 0.85rem; padding: 0.4rem 1rem;">
        Cancel
      </button>
      <button type="button" id="exec-scan-submit-btn" class="btn-primary" onclick="submitExecuteScan()" style="font-size: 0.85rem; font-weight: 700; padding: 0.45rem 1.4rem; background: linear-gradient(135deg, #0284c7, #06b6d4);">
        📡 Launch Scan & Add Fleet
      </button>
    </div>

  </div>
</div>

<!-- Public Share Calculation Modal -->
<div id="sim-share-modal" style="display: none; position: fixed; inset: 0; z-index: 10001; background: rgba(5, 7, 15, 0.88); backdrop-filter: blur(6px); align-items: center; justify-content: center; padding: 1.5rem;" onclick="if(event.target === this) closeCalcShareModal()">
  <div style="background: #0d1222; border: 1px solid rgba(0,229,255,0.4); border-radius: 10px; width: 100%; max-width: 680px; max-height: 90vh; display: flex; flex-direction: column; box-shadow: 0 12px 50px rgba(0,0,0,0.9); overflow: hidden;" onclick="event.stopPropagation()">
    <div style="padding: 1.1rem 1.4rem; border-bottom: 1px solid rgba(255,255,255,0.08); display: flex; justify-content: space-between; align-items: center; background: rgba(0,0,0,0.25);">
      <div>
        <div style="font-size: 1.1rem; font-weight: 700; color: var(--cyan); display: flex; align-items: center; gap: 0.5rem;">
          🔗 Share Battle Calculation
        </div>
        <div style="font-size: 0.78rem; color: var(--text-dim); margin-top: 0.2rem;">
          Generate instant links for alliance members and external players (no MCP installation required)
        </div>
      </div>
      <button class="btn-refresh" style="font-size: 1.2rem; padding: 0.2rem 0.6rem; line-height: 1;" onclick="closeCalcShareModal()">✕</button>
    </div>

    <div style="padding: 1.25rem 1.4rem; overflow-y: auto; display: flex; flex-direction: column; gap: 1.1rem;">
      <!-- Public GitHub Pages Link -->
      <div>
        <label style="display: block; font-size: 0.78rem; font-weight: 700; color: #38bdf8; margin-bottom: 0.35rem; display: flex; align-items: center; justify-content: space-between;">
          <span>🌐 Public Web Link (GitHub Pages — Works for Everyone):</span>
          <span style="font-size: 0.7rem; color: #86efac; font-weight: normal;">✓ Free &amp; Client-Side</span>
        </label>
        <div style="display: flex; gap: 0.5rem;">
          <input type="text" id="sim-share-public-url" class="form-control" readonly style="font-family: var(--font-mono); font-size: 0.78rem; background: #070b14; flex: 1;" onclick="this.select()">
          <button class="btn-primary" onclick="copyPublicShareLink()" style="padding: 0.4rem 1rem; font-size: 0.82rem; white-space: nowrap;">
            📋 Copy Public Link
          </button>
          <button class="btn-refresh" onclick="openPublicShareLinkInTab()" style="padding: 0.4rem 0.8rem; font-size: 0.82rem;" title="Open link in a new browser tab">
            ↗️
          </button>
        </div>
        <div style="font-size: 0.72rem; color: var(--text-dim); margin-top: 0.35rem; line-height: 1.45;">
          Recipient can open this in any browser on PC, tablet, or phone, view the full Battle Matrix, add fleets, and simulate battles directly.<br>
          <span style="color: #38bdf8;">🚀 <em>Tip:</em> If you or an ally open the public link while running this local suite, click <strong>"🚀 Open in Local MCP"</strong> in the top bar to bridge instantly into your local .env session.</span><br>
          <span style="color: #fde047;">⚙️ <em>Note:</em> Requires GitHub Pages enabled on GitHub: <a href="https://github.com/phuture707/PEGMCPCOMMAND/settings/pages" target="_blank" style="color: #38bdf8; text-decoration: underline;">Settings → Pages → Deploy from branch: main, folder: /docs</a>.</span>
        </div>
      </div>

      <!-- Local MCP Hub Link -->
      <div>
        <label style="display: block; font-size: 0.78rem; font-weight: 700; color: #a5b4fc; margin-bottom: 0.35rem;">
          💻 Local MCP Hub Link (For Commanders running this MCP Suite):
        </label>
        <div style="display: flex; gap: 0.5rem;">
          <input type="text" id="sim-share-local-url" class="form-control" readonly style="font-family: var(--font-mono); font-size: 0.78rem; background: #070b14; flex: 1;" onclick="this.select()">
          <button class="btn-refresh" onclick="copyLocalShareLink()" style="padding: 0.4rem 1rem; font-size: 0.82rem; white-space: nowrap; color: #a5b4fc; border-color: rgba(165,180,252,0.4);">
            📋 Copy Local Link
          </button>
        </div>
      </div>

      <!-- Quick Actions Grid -->
      <div style="background: rgba(0,229,255,0.04); border: 1px solid rgba(0,229,255,0.15); border-radius: 8px; padding: 0.85rem 1rem; display: flex; gap: 0.75rem; flex-wrap: wrap; align-items: center; justify-content: space-between;">
        <div style="font-size: 0.82rem; color: var(--text-main);">
          <strong>Direct Sharing:</strong> Send battle report to an ally or save an offline file
        </div>
        <div style="display: flex; gap: 0.5rem; flex-wrap: wrap;">
          <button class="btn-refresh" onclick="closeCalcShareModal(); openAllianceMessageModal();" style="padding: 0.35rem 0.85rem; font-size: 0.8rem; color: #fde047; border-color: rgba(234,179,8,0.4); background: rgba(234,179,8,0.08);">
            💬 In-Game Message
          </button>
          <button class="btn-refresh" onclick="downloadOfflineCalcHtml()" style="padding: 0.35rem 0.85rem; font-size: 0.8rem; color: #cbd5e1; border-color: rgba(255,255,255,0.2);">
            💾 Save HTML File
          </button>
        </div>
      </div>
    </div>

    <div style="padding: 0.8rem 1.4rem; border-top: 1px solid rgba(255,255,255,0.08); display: flex; justify-content: flex-end; background: rgba(0,0,0,0.3);">
      <button type="button" class="btn-refresh" onclick="closeCalcShareModal()" style="font-size: 0.85rem; padding: 0.35rem 1.2rem;">
        Done
      </button>
    </div>
  </div>
</div>

<!-- Import Calculation Modal -->
<div id="sim-import-modal" style="display: none; position: fixed; inset: 0; z-index: 10001; background: rgba(5, 7, 15, 0.88); backdrop-filter: blur(6px); align-items: center; justify-content: center; padding: 1.5rem;" onclick="if(event.target === this) closeCalcImportModal()">
  <div style="background: #0d1222; border: 1px solid rgba(0,229,255,0.4); border-radius: 10px; width: 100%; max-width: 620px; max-height: 90vh; display: flex; flex-direction: column; box-shadow: 0 12px 50px rgba(0,0,0,0.9); overflow: hidden;" onclick="event.stopPropagation()">
    <div style="padding: 1.1rem 1.4rem; border-bottom: 1px solid rgba(255,255,255,0.08); display: flex; justify-content: space-between; align-items: center; background: rgba(0,0,0,0.25);">
      <div>
        <div style="font-size: 1.1rem; font-weight: 700; color: #86efac; display: flex; align-items: center; gap: 0.5rem;">
          📥 Import Battle Calculation
        </div>
        <div style="font-size: 0.78rem; color: var(--text-dim); margin-top: 0.2rem;">
          Paste a shared calculation link, compressed state code, or coordinates
        </div>
      </div>
      <button class="btn-refresh" style="font-size: 1.2rem; padding: 0.2rem 0.6rem; line-height: 1;" onclick="closeCalcImportModal()">✕</button>
    </div>

    <div style="padding: 1.25rem 1.4rem; display: flex; flex-direction: column; gap: 1rem;">
      <div>
        <label style="display: block; font-size: 0.8rem; font-weight: 700; color: var(--text-main); margin-bottom: 0.4rem;">
          Paste Shared URL or Compressed Code:
        </label>
        <textarea id="sim-import-code-input" class="form-control" rows="4" placeholder="https://phuture707.github.io/PEGMCPCOMMAND/calc.html#c=...&#10;or pasted code / coordinates (e.g. 12:1:1)" style="font-family: var(--font-mono); font-size: 0.82rem; background: #070b14; resize: vertical;"></textarea>
      </div>
      <div style="font-size: 0.75rem; color: var(--text-dim); line-height: 1.4;">
        💡 <strong>Supports:</strong> GitHub Pages share links, local MCP suite links, compressed Base64 codes, and coordinate targets. Imported calculations will open as an active session.
      </div>
    </div>

    <div style="padding: 0.9rem 1.4rem; border-top: 1px solid rgba(255,255,255,0.08); display: flex; justify-content: space-between; align-items: center; background: rgba(0,0,0,0.3);">
      <button type="button" class="btn-refresh" onclick="closeCalcImportModal()" style="font-size: 0.85rem; padding: 0.4rem 1rem;">
        Cancel
      </button>
      <button type="button" class="btn-primary" onclick="applyImportedCode()" style="font-size: 0.85rem; font-weight: 700; padding: 0.45rem 1.5rem; background: linear-gradient(135deg, #10b981, #059669);">
        📥 Import into Active Calculation
      </button>
    </div>
  </div>
</div>

<!-- Alliance In-Game Message Modal -->
<div id="sim-alliance-msg-modal" style="display: none; position: fixed; inset: 0; z-index: 10001; background: rgba(5, 7, 15, 0.88); backdrop-filter: blur(6px); align-items: center; justify-content: center; padding: 1.5rem;" onclick="if(event.target === this) closeAllianceMessageModal()">
  <div style="background: #0d1222; border: 1px solid rgba(234,179,8,0.45); border-radius: 10px; width: 100%; max-width: 640px; max-height: 90vh; display: flex; flex-direction: column; box-shadow: 0 12px 50px rgba(0,0,0,0.9); overflow: hidden;" onclick="event.stopPropagation()">
    <div style="padding: 1.1rem 1.4rem; border-bottom: 1px solid rgba(255,255,255,0.08); display: flex; justify-content: space-between; align-items: center; background: rgba(0,0,0,0.25);">
      <div>
        <div style="font-size: 1.1rem; font-weight: 700; color: #fde047; display: flex; align-items: center; gap: 0.5rem;">
          💬 Dispatch Battle Brief via In-Game Message
        </div>
        <div style="font-size: 0.78rem; color: var(--text-dim); margin-top: 0.2rem;">
          Send the tactical simulation and public web link directly to an alliance mate's in-game inbox
        </div>
      </div>
      <button class="btn-refresh" style="font-size: 1.2rem; padding: 0.2rem 0.6rem; line-height: 1;" onclick="closeAllianceMessageModal()">✕</button>
    </div>

    <div style="padding: 1.25rem 1.4rem; overflow-y: auto; display: flex; flex-direction: column; gap: 1rem;">
      <div>
        <label style="display: block; font-size: 0.8rem; font-weight: 700; color: var(--text-main); margin-bottom: 0.4rem;">
          👤 Recipient Commander (Username or Player ID):
        </label>
        <input type="text" id="sim-ally-recipient" class="form-control" placeholder="e.g. CommanderName or player ID" style="font-size: 0.85rem; background: #070b14;">
      </div>

      <div>
        <label style="display: block; font-size: 0.8rem; font-weight: 700; color: var(--text-main); margin-bottom: 0.4rem;">
          📝 Battle Plan Brief &amp; Web Calculator Link:
        </label>
        <textarea id="sim-ally-msg-body" class="form-control" rows="6" style="font-family: var(--font-mono); font-size: 0.8rem; background: #070b14; resize: vertical; line-height: 1.4;"></textarea>
      </div>

      <div id="sim-ally-msg-status" style="display: none; padding: 0.6rem 0.8rem; border-radius: 6px; font-size: 0.8rem;"></div>
    </div>

    <div style="padding: 0.9rem 1.4rem; border-top: 1px solid rgba(255,255,255,0.08); display: flex; justify-content: space-between; align-items: center; background: rgba(0,0,0,0.3);">
      <button type="button" class="btn-refresh" onclick="copyAllianceMessageText()" style="font-size: 0.85rem; padding: 0.4rem 1rem;">
        📋 Copy Text
      </button>
      <div style="display: flex; gap: 0.5rem;">
        <button type="button" class="btn-refresh" onclick="closeAllianceMessageModal()" style="font-size: 0.85rem; padding: 0.4rem 1rem;">
          Cancel
        </button>
        <button type="button" id="sim-ally-send-btn" class="btn-primary" onclick="sendAllianceCombatMessage()" style="font-size: 0.85rem; font-weight: 700; padding: 0.45rem 1.4rem; background: linear-gradient(135deg, #eab308, #ca8a04); color: #000;">
          🚀 Send In-Game Message
        </button>
      </div>
    </div>
  </div>
</div>

<!-- Tactical Defense Auto-Planner Modal -->
<div id="sim-defense-planner-modal" style="display: none; position: fixed; inset: 0; z-index: 10002; background: rgba(5, 7, 15, 0.9); backdrop-filter: blur(8px); align-items: center; justify-content: center; padding: 1.5rem;" onclick="if(event.target === this) closeDefenseScenarioModal()">
  <div style="background: #0d1222; border: 1px solid rgba(56,189,248,0.5); border-radius: 12px; width: 100%; max-width: 980px; max-height: 92vh; display: flex; flex-direction: column; box-shadow: 0 16px 60px rgba(0,0,0,0.95); overflow: hidden;" onclick="event.stopPropagation()">
    
    <!-- Modal Header -->
    <div style="padding: 1.1rem 1.4rem; border-bottom: 1px solid rgba(255,255,255,0.08); display: flex; justify-content: space-between; align-items: center; background: rgba(0,0,0,0.3);">
      <div>
        <div style="font-size: 1.15rem; font-weight: 700; color: #38bdf8; display: flex; align-items: center; gap: 0.5rem;">
          🛡️ Tactical Defense Auto-Planner at Specific Tick
        </div>
        <div style="font-size: 0.78rem; color: var(--text-dim); margin-top: 0.2rem;">
          Calculates available defending forces (garrison + arriving fleets) vs inbound hostile attackers with scan reliability &amp; decoy analysis
        </div>
      </div>
      <button class="btn-refresh" style="font-size: 1.2rem; padding: 0.2rem 0.6rem; line-height: 1;" onclick="closeDefenseScenarioModal()">✕</button>
    </div>

    <!-- Parameter Controls Bar -->
    <div style="padding: 0.9rem 1.4rem; border-bottom: 1px solid rgba(255,255,255,0.06); background: rgba(15,23,42,0.6); display: flex; gap: 1rem; align-items: flex-end; flex-wrap: wrap;">
      <div style="flex: 1; min-width: 190px;">
        <label style="display: block; font-size: 0.75rem; font-weight: 700; color: var(--text-dim); margin-bottom: 0.3rem;">
          🎯 Defender Planet / Coords:
        </label>
        <div style="display: flex; gap: 0.4rem;">
          <input type="text" id="sim-plan-coords" class="form-control" placeholder="e.g. 12:1:1" style="font-size: 0.85rem; background: #070b14; font-family: var(--font-mono);">
          <select id="sim-plan-planet-select" class="form-control" style="font-size: 0.8rem; max-width: 160px;" onchange="if(this.value){ document.getElementById('sim-plan-coords').value = this.value; loadDefenseScenarioPreview(); }">
            <option value="">Select Planet...</option>
          </select>
        </div>
      </div>

      <div style="width: 145px;">
        <label style="display: block; font-size: 0.75rem; font-weight: 700; color: var(--text-dim); margin-bottom: 0.3rem;">
          ⏱️ Battle Tick <span id="sim-plan-cur-tick-badge" style="color:var(--cyan); font-weight: normal;">(Now: ...)</span>:
        </label>
        <input type="number" id="sim-plan-tick" class="form-control" placeholder="e.g. 1118" style="font-size: 0.85rem; background: #070b14; font-family: var(--font-mono);">
      </div>

      <div style="width: 115px;">
        <label style="display: block; font-size: 0.75rem; font-weight: 700; color: var(--text-dim); margin-bottom: 0.3rem;">
          🎯 Window (±):
        </label>
        <select id="sim-plan-window" class="form-control" style="font-size: 0.8rem;">
          <option value="0">±0 Ticks</option>
          <option value="1">±1 Tick</option>
          <option value="2">±2 Ticks</option>
        </select>
      </div>

      <button type="button" class="btn-refresh" onclick="loadDefenseScenarioPreview()" style="font-size: 0.82rem; font-weight: 700; padding: 0.45rem 1rem; color: #38bdf8; border-color: rgba(56,189,248,0.5); background: rgba(56,189,248,0.12);">
        🔄 Analyze Tick
      </button>
    </div>

    <!-- Live Preview Split Container -->
    <div id="sim-plan-body" style="padding: 1.25rem 1.4rem; overflow-y: auto; flex: 1; display: grid; grid-template-columns: 1.1fr 1.3fr; gap: 1.25rem;">
      <div style="grid-column: 1 / -1; text-align: center; padding: 2rem; color: var(--text-dim);">
        Select target coordinates and battle tick to run tactical analysis.
      </div>
    </div>

    <!-- Modal Footer Actions -->
    <div style="padding: 0.9rem 1.4rem; border-top: 1px solid rgba(255,255,255,0.08); display: flex; justify-content: space-between; align-items: center; background: rgba(0,0,0,0.3);">
      <div style="display: flex; gap: 0.5rem;">
        <button type="button" class="btn-refresh" onclick="copyDefenseScenarioBrief()" style="font-size: 0.82rem; padding: 0.4rem 0.9rem;">
          📋 Copy Brief
        </button>
        <button type="button" class="btn-refresh" onclick="shareDefenseScenarioLink()" style="font-size: 0.82rem; padding: 0.4rem 0.9rem; color: var(--cyan); border-color: rgba(0,229,255,0.4);">
          🔗 Share Plan
        </button>
      </div>
      <div style="display: flex; gap: 0.6rem;">
        <button type="button" class="btn-refresh" onclick="closeDefenseScenarioModal()" style="font-size: 0.85rem; padding: 0.4rem 1.1rem;">
          Close
        </button>
        <button type="button" id="sim-plan-apply-btn" class="btn-primary" onclick="applyDefenseScenarioToCalculator()" style="font-size: 0.85rem; font-weight: 700; padding: 0.45rem 1.5rem; background: linear-gradient(135deg, #0284c7, #0369a1); color: #fff;">
          ⚡ Populate Calculator &amp; Simulate
        </button>
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
    if (!t) {
      console.log("[Toast]", msg);
      return;
    }
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
      
      const isBlocked = data.blocked || data.result?.status === 'blocked' || data.result?.data?.status === 'blocked';
      if (isBlocked) {
        outputEl.innerHTML = `<span style="color: var(--yellow); font-weight: 700;">⚠️ Wave Distorter / Planetary Defense Interference:</span>\n` +
          `<span style="color: var(--text-dim);">This scan or action was blocked by enemy planetary defenses (Wave Distorter). No intel was retrieved.</span>\n\n` +
          escapeHtml(outText);
        showToast(`⚠️ ${selectedTool.name} was BLOCKED by planetary defenses!`);
      } else if (outText.includes('The table does not have the specified index')) {
        outputEl.innerHTML = `<span style="color: var(--yellow); font-weight: 700;">⚠️ Pegasus Galaxy Server-Side Database Issue:</span>\n` +
          `<span style="color: var(--text-dim);">The game server's AWS DynamoDB database is missing a Global Secondary Index (GSI) for this query on their backend.</span>\n\n` +
          escapeHtml(outText);
        showToast("Server returned DynamoDB index error (game server issue)");
      } else {
        outputEl.textContent = outText;
        if (!data.error && data.result?.success !== false && !data.result?.isError) {
          recordQuotaUsage(selectedTool.name);
          showToast(`Executed ${selectedTool.name} successfully!`);
        } else {
          showToast(`❌ ${selectedTool.name} returned error`);
        }
      }

      // If a scan was performed, auto-refresh combat simulator scan targets immediately
      if (selectedTool.name.toLowerCase().includes('scan')) {
        loadCombatSimulator();
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
    if (refData.constructions.length || refData.research.length || refData.ships.length) return refData;
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
    } catch(e) {
      console.error("Error loading reference data:", e);
    }
    return refData;
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

      // Immediately refresh server logs in UI so bot.log entry is reflected
      await fetchBotLogs();

      const isBlocked = data.blocked || data.result?.status === 'blocked' || data.result?.data?.status === 'blocked';
      if (isBlocked) {
        showToast(`⚠️ ${tool} was BLOCKED by planetary defenses!`);
        box.textContent += `⚠️ [BLOCKED]: Order was blocked by enemy planetary defenses (Wave Distorter).\n`;
      } else if (data.success && !data.result?.isError && data.result?.success !== false) {
        showToast(`✅ ${tool} executed successfully!`);
        box.textContent += `✅ [Result]: ` + JSON.stringify(data.result, null, 2) + `\n`;
      } else {
        const errMsg = data.error || data.result?.error || 'Action failed';
        showToast(`❌ Error: ${errMsg}`);
        box.textContent += `❌ [Error]: ${errMsg}\n`;
      }
      box.scrollTop = box.scrollHeight;

      // If a scan was performed, auto-refresh combat simulator targets immediately
      if (tool.toLowerCase().includes('scan')) {
        loadCombatSimulator();
      }
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
    const isStandalone = window.IS_STANDALONE_CALC || 
      window.location.pathname.startsWith('/calc') || 
      window.location.pathname.startsWith('/bcalc') ||
      window.location.pathname.startsWith('/battlecalc') ||
      window.location.search.includes('calc=1') ||
      window.location.search.includes('mode=calc');

    if (isStandalone) {
      initStandaloneCombatSimulator();
      return;
    }

    refreshDashboard();
    refreshBotStatus();
    // Auto-refresh telemetry every 30 seconds
    setInterval(refreshDashboard, 30000);
    startScanBackgroundSync();

    if (window.location.hash.includes('c=') || window.location.hash.includes('import=') || window.location.hash.includes('coords=')) {
      setTimeout(() => {
        if (typeof switchTab === 'function') switchTab('battlecalc');
        handleCalcUrlHash();
      }, 500);
    }
  };

// =========================================================================
// =========================================================================
  // ⚔️ BATTLE SIMULATOR & FLEET CALCULATOR SYSTEM (MULTI-FLEET COALITIONS)
  // =========================================================================
  let simAttackerData = { namedFleets: [], hangarShips: {} };
  let simScanTargets = [];
  let currentTargetScan = null;
  let currentSimMode = 'defense';
  let homeDefenseData = null;
  let simAttackerFleets = [];
  let simDefenderFleets = [];
  let simFleetSeq = 1;

  // New state for coordinate search & source filtering
  let simScanSourceFilter = 'all'; // 'all' | 'user' | 'ally'
  let simPickerSourceFilter = 'all';
  let simEnteredCoords = '';
  let universePlanetsList = [];
  let userAllianceData = null;

  function normalizeCoords(str) {
    if (!str) return '';
    let clean = String(str).trim().replace(/[^0-9:]/g, ':');
    clean = clean.replace(/:+/g, ':').replace(/^:+|:+$/g, '');
    return clean;
  }

  function formatScanType(type) {
    if (!type) return 'Scan';
    if (type === 'DEEP_SCAN') return 'Deep Scan';
    if (type === 'MILITARY_SCAN') return 'Military Scan';
    if (type === 'FLEET_COMPOSITION_SCAN') return 'Fleet Scan';
    if (type === 'INCOMING_SCAN') return 'Incoming Scan';
    if (type === 'SURFACE_SCAN') return 'Surface Scan';
    return type.replace('_SCAN', '').replace(/_/g, ' ');
  }

  let scanPollTimer = null;
  let lastScanCount = 0;

  async function refreshScanTargets(isBackground = false) {
    try {
      const scanRes = await fetch('/api/combat/scan_targets');
      const scanJson = await scanRes.json();
      if (scanJson.success) {
        const prevCount = simScanTargets.length;
        simScanTargets = scanJson.targets || [];
        universePlanetsList = scanJson.universePlanets || [];
        userAllianceData = scanJson.allianceInfo || null;

        // Update alliance badge
        const aBadge = document.getElementById('sim-alliance-badge');
        if (aBadge) {
          if (userAllianceData && userAllianceData.name) {
            aBadge.innerHTML = `Alliance: <strong style="color:#a78bfa;">[${userAllianceData.tag || 'ALLY'}] ${userAllianceData.name}</strong>`;
          } else if (scanJson.allianceError) {
            aBadge.innerHTML = `Alliance Intel: <span style="color:var(--yellow);" title="${escapeHtml(scanJson.allianceError)}">Endpoint Unavailable</span>`;
          } else {
            aBadge.innerHTML = `Alliance: <span style="color:var(--text-dim);">No Alliance</span>`;
          }
        }

        // Update count badges
        const allCount = scanJson.totalScans !== undefined ? scanJson.totalScans : simScanTargets.length;
        const userCount = scanJson.userScansCount !== undefined ? scanJson.userScansCount : simScanTargets.filter(t => t.source === 'user').length;
        const allyCount = scanJson.allyScansCount !== undefined ? scanJson.allyScansCount : simScanTargets.filter(t => t.source === 'ally').length;
        if (document.getElementById('sim-count-all')) document.getElementById('sim-count-all').textContent = allCount;
        if (document.getElementById('sim-count-user')) document.getElementById('sim-count-user').textContent = userCount;
        if (document.getElementById('sim-count-ally')) document.getElementById('sim-count-ally').textContent = allyCount;

        populateUniversePlanetQuickPick();
        populateScanTargetsDropdown();
        populateQuickScanAddDropdowns();
        updateCoordsScansDropdown('atk');
        updateCoordsScansDropdown('def');

        // Update live sync status in scan picker modal
        const syncStatusEl = document.getElementById('sim-picker-sync-status');
        if (syncStatusEl) {
          syncStatusEl.textContent = `🟢 Synced: ${new Date().toLocaleTimeString()} (${allCount} scans: ${userCount} personal, ${allyCount} ally)`;
        }

        // Re-render picker list if modal is currently open
        const pickerModal = document.getElementById('sim-scan-picker-modal');
        if (pickerModal && pickerModal.style.display === 'flex') {
          renderScanPickerList();
        }

        if (isBackground && prevCount > 0 && simScanTargets.length > prevCount) {
          const diff = simScanTargets.length - prevCount;
          showToast(`📡 ${diff} fresh scan(s) synced from alliance intel!`);
        }

        lastScanCount = simScanTargets.length;
      }
    } catch(e) {
      console.warn("Scan targets refresh error:", e);
    }
  }

  function startScanBackgroundSync() {
    if (scanPollTimer) return;
    scanPollTimer = setInterval(() => {
      const isCalcActive = document.getElementById('tab-battlecalc')?.classList.contains('active');
      const isPickerOpen = document.getElementById('sim-scan-picker-modal')?.style.display === 'flex';
      const isPlannerOpen = document.getElementById('sim-defense-planner-modal')?.style.display === 'flex';
      if (isCalcActive || isPickerOpen || isPlannerOpen) {
        refreshScanTargets(true);
      }
    }, 30000); // Auto-poll every 30 seconds
  }

  async function loadCombatSimulator() {
    const badge = document.getElementById('combat-status-badge');
    badge.textContent = 'Fetching fleets, universe map & scan intel...';

    try {
      await ensureRefData();

      // 1. Fetch attacker fleets + home defense
      const atkRes = await fetch('/api/combat/attacker_fleets');
      const atkJson = await atkRes.json();
      if (atkJson.success) {
        simAttackerData = atkJson;
        homeDefenseData = atkJson.homeDefense || null;
        populateQuickEmpireAddDropdowns();
      }

      // 2. Fetch fleet & planetary scan targets with universe map & alliance intel
      await refreshScanTargets(false);
      startScanBackgroundSync();

      // Initialize default attacker fleet if none exists (starts empty)
      if (simAttackerFleets.length === 0) {
        initDefaultAttackerFleet();
      }

      // Initialize default defender fleet if none exists (starts empty)
      if (simDefenderFleets.length === 0) {
        initDefaultDefenderFleet();
      }

      setSimulationMode(currentSimMode, true);
      setSimulatorLayout(currentBcalcLayout);
      initCalcSessions();

      const userScansN = simScanTargets.filter(t => t.source === 'user').length;
      const allyScansN = simScanTargets.filter(t => t.source === 'ally').length;
      badge.textContent = `Calculator Ready (Empty) • ${userScansN} personal scan(s), ${allyScansN} ally scan(s). Enter coords or load scans.`;
    } catch (e) {
      console.error("Combat simulator load error:", e);
      badge.textContent = 'Error loading combat data: ' + e.message;
    }
  }

  let simEnteredCoordsAtk = '';
  let simEnteredCoordsDef = '';

  function populateUniversePlanetQuickPick() {
    ['atk', 'def'].forEach(side => {
      const selId = side === 'atk' ? 'sim-atk-planet-quickpick' : 'sim-planet-quickpick';
      const sel = document.getElementById(selId);
      if (!sel) return;
      const curr = sel.value;
      sel.innerHTML = '<option value="">Jump to planet...</option>';
      if (!universePlanetsList || universePlanetsList.length === 0) return;

      universePlanetsList.forEach(p => {
        if (!p.coords) return;
        const opt = document.createElement('option');
        opt.value = p.coords;
        opt.textContent = `${p.name || 'Planet'} [${p.coords}]`;
        if (curr === p.coords) opt.selected = true;
        sel.appendChild(opt);
      });
    });
  }

  function populateScanTargetsDropdown() {
    const sourceFiltered = getFilteredScans();

    ['atk', 'def'].forEach(side => {
      const selIds = [
        side === 'atk' ? 'sim-atk-target-select' : 'sim-def-target',
        side === 'atk' ? 'sim-bcalc-atk-target-select' : 'sim-bcalc-def-target-select'
      ];

      selIds.forEach(selId => {
        const sel = document.getElementById(selId);
        if (!sel) return;

        sel.innerHTML = `<option value="">-- Choose ${side === 'atk' ? 'Attacker' : 'Defender'} Target from Scans --</option>`;

        if (sourceFiltered.length === 0) {
          const opt = document.createElement('option');
          opt.value = '__none__';
          opt.textContent = 'No scans found in selected source';
          sel.appendChild(opt);
          return;
        }

        sourceFiltered.forEach(t => {
          const globalIdx = simScanTargets.indexOf(t);
          const opt = document.createElement('option');
          opt.value = globalIdx;
          const srcBadge = t.source === 'ally' ? `[🤝 Ally${t.allianceTag ? ' ' + t.allianceTag : ''}]` : '[👤 Mine]';
          const typeBadge = formatScanType(t.scanType);
          const tickBadge = t.tick ? `[Tick ${t.tick}]` : '';
          const nameBadge = t.planetName ? `${t.planetName} ` : '';
          const isBlocked = (t.status === 'blocked' || t.isBlocked);
          const blockedText = isBlocked ? ' ⚠️ BLOCKED' : '';
          opt.textContent = `${srcBadge} ${nameBadge}[${t.coords || '?'}] ${tickBadge} (${typeBadge}${blockedText})`;
          sel.appendChild(opt);
        });
      });
    });
  }

  function onPlanetQuickPick(side, selectEl) {
    const coords = selectEl.value;
    if (!coords) return;
    const inputId = side === 'atk' ? 'sim-atk-coords-input' : 'sim-coords-input';
    const input = document.getElementById(inputId);
    if (input) input.value = coords;
    const bcalcInputId = side === 'atk' ? 'sim-bcalc-atk-coords-input' : 'sim-bcalc-def-coords-input';
    const bcalcInput = document.getElementById(bcalcInputId);
    if (bcalcInput) bcalcInput.value = coords;
    onCoordsInputChanged(side, coords);
  }

  function setScanSourceFilter(src) {
    simScanSourceFilter = src;
    ['all', 'user', 'ally'].forEach(s => {
      const btn = document.getElementById(`sim-source-${s}-btn`);
      if (btn) {
        if (s === src) btn.classList.add('active');
        else btn.classList.remove('active');
      }
    });

    populateScanTargetsDropdown();
    populateQuickScanAddDropdowns();
    updateCoordsScansDropdown('atk');
    updateCoordsScansDropdown('def');
    showToast(`Filtering scans by: ${src === 'all' ? 'All Scans' : (src === 'user' ? 'My Scans' : 'Alliance Intel')}`);
  }

  function getFilteredScans() {
    let list = simScanTargets || [];
    if (simScanSourceFilter === 'user') {
      list = list.filter(t => t.source === 'user');
    } else if (simScanSourceFilter === 'ally') {
      list = list.filter(t => t.source === 'ally');
    }
    return list;
  }

  function onCoordsInputChanged(side, val) {
    const normVal = (val || '').trim();
    // Synchronize both inputs (Cards View and Planetarion View)
    const bcalcInputId = side === 'atk' ? 'sim-bcalc-atk-coords-input' : 'sim-bcalc-def-coords-input';
    const bcalcInput = document.getElementById(bcalcInputId);
    if (bcalcInput && bcalcInput.value !== normVal) bcalcInput.value = normVal;

    const mainInputId = side === 'atk' ? 'sim-atk-coords-input' : 'sim-coords-input';
    const mainInput = document.getElementById(mainInputId);
    if (mainInput && mainInput.value !== normVal) mainInput.value = normVal;

    if (side === 'atk') {
      simEnteredCoordsAtk = normVal;
      updateCoordsScansDropdown('atk');
    } else {
      simEnteredCoordsDef = normVal;
      updateCoordsScansDropdown('def');
      if (typeof updateActiveCalcTabTitleFromCoords === 'function') {
        updateActiveCalcTabTitleFromCoords(normVal);
      }
    }
  }

  function syncBcalcCoordsInput(side, val) {
    onCoordsInputChanged(side, val);
  }

  function onCoordsInputEnter(side) {
    const selId = side === 'atk' ? 'sim-atk-coords-scans-select' : 'sim-coords-scans-select';
    const sel = document.getElementById(selId);
    if (sel && sel.value && sel.value !== '__none__') {
      onCoordsScanSelected(side, sel);
    }
  }

  function clearCoordsFilter(side) {
    if (side === 'atk') {
      const input = document.getElementById('sim-atk-coords-input');
      if (input) input.value = '';
      const bcalcInput = document.getElementById('sim-bcalc-atk-coords-input');
      if (bcalcInput) bcalcInput.value = '';
      const quick = document.getElementById('sim-atk-planet-quickpick');
      if (quick) quick.value = '';
      const bcalcTarget = document.getElementById('sim-bcalc-atk-target-select');
      if (bcalcTarget) bcalcTarget.selectedIndex = 0;
      simEnteredCoordsAtk = '';
      updateCoordsScansDropdown('atk');
    } else {
      const input = document.getElementById('sim-coords-input');
      if (input) input.value = '';
      const bcalcInput = document.getElementById('sim-bcalc-def-coords-input');
      if (bcalcInput) bcalcInput.value = '';
      const quick = document.getElementById('sim-planet-quickpick');
      if (quick) quick.value = '';
      const bcalcTarget = document.getElementById('sim-bcalc-def-target-select');
      if (bcalcTarget) bcalcTarget.selectedIndex = 0;
      simEnteredCoordsDef = '';
      updateCoordsScansDropdown('def');
    }
    showToast(`Cleared ${side === 'atk' ? 'Attacker' : 'Defender'} coordinates filter`);
  }

  function updateCoordsScansDropdown(side) {
    const isAtk = (side === 'atk');
    const enteredCoords = isAtk ? simEnteredCoordsAtk : simEnteredCoordsDef;
    const selId = isAtk ? 'sim-atk-coords-scans-select' : 'sim-coords-scans-select';
    const labelId = isAtk ? 'sim-atk-coords-active-label' : 'sim-coords-active-label';
    const badgeId = isAtk ? 'sim-atk-coords-match-badge' : 'sim-coords-match-badge';

    const sel = document.getElementById(selId);
    const labelEl = document.getElementById(labelId);
    const badgeEl = document.getElementById(badgeId);
    if (!sel) return;

    const normEntered = normalizeCoords(enteredCoords);
    if (!normEntered) {
      if (labelEl) labelEl.textContent = isAtk ? 'Attacker Coords' : 'Defender Coords';
      if (badgeEl) badgeEl.textContent = '0 scan(s)';
      sel.innerHTML = `<option value="">Enter ${isAtk ? 'attacker' : 'defender'} coords above (e.g. 12:1:1) to view scans...</option>`;
      return;
    }

    if (labelEl) labelEl.textContent = `[${normEntered}]`;

    // Filter scans matching this coordinate
    const sourceFiltered = getFilteredScans();
    const matchingScans = sourceFiltered.filter(t => {
      const c = normalizeCoords(t.coords);
      return c === normEntered || c.startsWith(normEntered);
    });

    if (badgeEl) {
      badgeEl.textContent = `${matchingScans.length} scan(s)`;
      badgeEl.style.color = matchingScans.length > 0 ? 'var(--green)' : 'var(--yellow)';
    }

    sel.innerHTML = '';
    if (matchingScans.length === 0) {
      const opt = document.createElement('option');
      opt.value = '__none__';
      opt.textContent = `⚠️ No scans found for [${normEntered}] in ${simScanSourceFilter === 'all' ? 'user or ally scans' : simScanSourceFilter + ' scans'}`;
      sel.appendChild(opt);
      return;
    }

    matchingScans.forEach((t, mIdx) => {
      const globalIdx = simScanTargets.indexOf(t);
      const typeLabel = formatScanType(t.scanType);
      const tick = t.tick ? `Tick ${t.tick}` : 'Tick ?';
      const sourceBadge = t.source === 'ally' ? `[🤝 Ally${t.allianceTag ? ' ' + t.allianceTag : ''}]` : '[👤 Mine]';
      const shipCount = Object.values(t.garrisonShips || {}).reduce((a, b) => a + (parseInt(b, 10) || 0), 0);
      const fleetCount = (t.namedFleets || []).length;
      const pdsCount = Object.keys(t.pds || {}).length;
      const isBlocked = (t.status === 'blocked' || t.isBlocked);

      const opt = document.createElement('option');
      opt.value = globalIdx;
      if (isBlocked) {
        opt.textContent = `${sourceBadge} [${tick}] [BLOCKED ${typeLabel}] — ⚠️ Distorter Active`;
      } else {
        opt.textContent = `${sourceBadge} [${tick}] [${typeLabel}] — ${shipCount.toLocaleString()} ships, ${fleetCount} fleet(s)${pdsCount > 0 ? `, ${pdsCount} PDS` : ''}`;
      }
      if (mIdx === 0) opt.selected = true;
      sel.appendChild(opt);
    });

    // Auto-load newest scan if valid
    if (matchingScans.length > 0) {
      const newestGlobalIdx = simScanTargets.indexOf(matchingScans[0]);
      sel.value = newestGlobalIdx;
      const targetSelIds = isAtk ? ['sim-atk-target-select', 'sim-bcalc-atk-target-select'] : ['sim-def-target', 'sim-bcalc-def-target-select'];
      targetSelIds.forEach(id => {
        const tSel = document.getElementById(id);
        if (tSel) tSel.value = newestGlobalIdx;
      });
      loadScanIntoSide(side, matchingScans[0]);
    }
  }

  function onCoordsScanSelected(side, selectEl) {
    const val = selectEl.value;
    if (val === '' || val === '__none__') return;
    const idx = parseInt(val, 10);
    const targetScan = simScanTargets[idx];
    if (targetScan) {
      const targetSelIds = (side === 'atk') ? ['sim-atk-target-select', 'sim-bcalc-atk-target-select'] : ['sim-def-target', 'sim-bcalc-def-target-select'];
      targetSelIds.forEach(id => {
        const targetSel = document.getElementById(id);
        if (targetSel) targetSel.value = val;
      });
      loadScanIntoSide(side, targetScan);
    }
  }

  function onTargetSelectChange(side, selectEl) {
    const val = selectEl.value;
    if (val === '' || val === '__none__') return;
    // Synchronize the other selector for this side
    const otherId = (side === 'atk')
      ? (selectEl.id === 'sim-atk-target-select' ? 'sim-bcalc-atk-target-select' : 'sim-atk-target-select')
      : (selectEl.id === 'sim-def-target' ? 'sim-bcalc-def-target-select' : 'sim-def-target');
    const otherSel = document.getElementById(otherId);
    if (otherSel) otherSel.value = val;

    const idx = parseInt(val, 10);
    const targetScan = simScanTargets[idx];
    if (targetScan) {
      loadScanIntoSide(side, targetScan);
    }
  }

  function loadScanIntoSide(side, targetScan, mode) {
    if (!targetScan) return;
    const isAtk = (side === 'atk');
    const isBlocked = (targetScan.status === 'blocked' || targetScan.isBlocked);
    const typeLabel = formatScanType(targetScan.scanType);
    const scanCoords = (targetScan.coords && targetScan.coords !== 'Unknown') ? targetScan.coords : '';

    // Sync direct coords input box if coords are known
    if (scanCoords) {
      const inputId = isAtk ? 'sim-atk-coords-input' : 'sim-coords-input';
      const input = document.getElementById(inputId);
      if (input && normalizeCoords(input.value) !== normalizeCoords(scanCoords)) {
        input.value = scanCoords;
      }
      const bcalcInputId = isAtk ? 'sim-bcalc-atk-coords-input' : 'sim-bcalc-def-coords-input';
      const bcalcInput = document.getElementById(bcalcInputId);
      if (bcalcInput && normalizeCoords(bcalcInput.value) !== normalizeCoords(scanCoords)) {
        bcalcInput.value = scanCoords;
      }
      const labelId = isAtk ? 'sim-atk-coords-active-label' : 'sim-coords-active-label';
      const labelEl = document.getElementById(labelId);
      if (labelEl) labelEl.textContent = `[${scanCoords}]`;
      const bottomInput = document.getElementById('sim-bcalc-bottom-coords');
      if (bottomInput) bottomInput.value = scanCoords;
      if (typeof updateActiveCalcTabTitleFromCoords === 'function') {
        updateActiveCalcTabTitleFromCoords(scanCoords);
      }
    }

    const list = [];
    const gShips = targetScan.garrisonShips || {};
    const gCount = Object.values(gShips).reduce((a, b) => a + (parseInt(b, 10) || 0), 0);
    const namedFleets = targetScan.namedFleets || [];

    if (isBlocked) {
      list.push({
        id: side + '_' + (simFleetSeq++),
        side: side,
        name: `[BLOCKED ${typeLabel}] Garrison [${scanCoords || 'Target'}]`,
        sourceVal: '__custom__',
        coords: scanCoords,
        enabled: true,
        ships: {}
      });
      showToast('⚠️ Scan blocked by enemy Wave Distorters. No fleet data available.');
    } else if (mode === 'consolidated') {
      // Consolidate all scanned garrison and named fleets into 1 fleet column
      const mergedShips = {};
      Object.entries(gShips).forEach(([sid, cnt]) => {
        mergedShips[sid] = (mergedShips[sid] || 0) + (parseInt(cnt, 10) || 0);
      });
      namedFleets.forEach(nf => {
        Object.entries(nf.ships || {}).forEach(([sid, cnt]) => {
          mergedShips[sid] = (mergedShips[sid] || 0) + (parseInt(cnt, 10) || 0);
        });
      });
      list.push({
        id: side + '_' + (simFleetSeq++),
        side: side,
        name: `[${typeLabel}] Consolidated Forces [${scanCoords || 'Target'}]`,
        sourceVal: '__custom__',
        coords: scanCoords,
        enabled: true,
        ships: mergedShips
      });
    } else if (mode === 'garrison') {
      list.push({
        id: side + '_' + (simFleetSeq++),
        side: side,
        name: `[${typeLabel}] Garrison [${scanCoords || 'Target'}]`,
        sourceVal: '__garrison__',
        coords: scanCoords,
        enabled: true,
        ships: Object.assign({}, gShips)
      });
    } else if (mode && mode.startsWith('nf_')) {
      const nfIdx = parseInt(mode.replace('nf_', ''), 10);
      const nf = namedFleets[nfIdx];
      if (nf) {
        list.push({
          id: side + '_' + (simFleetSeq++),
          side: side,
          name: `[${typeLabel}] Fleet "${nf.name || 'Fleet'}" [${scanCoords || 'Target'}]`,
          sourceVal: mode,
          coords: scanCoords,
          enabled: true,
          ships: Object.assign({}, nf.ships || {})
        });
      }
    } else {
      // Default: Separate garrison and named fleets
      if (gCount > 0 || namedFleets.length === 0) {
        list.push({
          id: side + '_' + (simFleetSeq++),
          side: side,
          name: `[${typeLabel}] Garrison [${scanCoords || 'Target'}]`,
          sourceVal: '__garrison__',
          coords: scanCoords,
          enabled: true,
          ships: Object.assign({}, gShips)
        });
      }
      namedFleets.forEach((nf, nfIdx) => {
        list.push({
          id: side + '_' + (simFleetSeq++),
          side: side,
          name: `[Scanned Fleet ${nfIdx + 1}] "${nf.name || 'Fleet'}" [${scanCoords || 'Target'}]`,
          sourceVal: `nf_${nfIdx}`,
          coords: scanCoords,
          enabled: true,
          ships: Object.assign({}, nf.ships || {})
        });
      });
    }

    if (list.length === 0) {
      list.push({
        id: side + '_' + (simFleetSeq++),
        side: side,
        name: `[${typeLabel}] Fleet [${scanCoords || 'Target'}]`,
        sourceVal: '__custom__',
        coords: scanCoords,
        enabled: true,
        ships: {}
      });
    }

    if (isAtk) {
      simAttackerFleets = list;
    } else {
      simDefenderFleets = list;
      currentTargetScan = targetScan;

      // Update PDS levels if defender
      const pds = targetScan.pds || {};
      ['Shield Generator', 'Ion Cannon', 'Missile Silo', 'Laser Battery'].forEach(k => {
        const id = k === 'Shield Generator' ? 'shield' : (k === 'Ion Cannon' ? 'ion' : (k === 'Missile Silo' ? 'silo' : 'laser'));
        const chk = document.getElementById(`sim-pds-${id}-chk`);
        const lvl = document.getElementById(`sim-pds-${id}-lvl`);
        if (chk && lvl) {
          chk.checked = !!pds[k];
          if (pds[k]) lvl.value = pds[k];
        }
      });
    }

    // Update target details card (both defender and attacker detail cards)
    const scanCard = document.getElementById(`sim-${side}-scan-details`);
    if (scanCard) {
      scanCard.style.display = 'block';
      const coordsEl = document.getElementById(`sim-${side}-coords`);
      if (coordsEl) coordsEl.textContent = (targetScan.planetName ? targetScan.planetName + ' ' : '') + (targetScan.coords || 'Unknown');
      const typeEl = document.getElementById(`sim-${side}-type`);
      if (typeEl) {
        const srcLabel = targetScan.source === 'ally' ? `[🤝 Ally${targetScan.allianceTag ? ' ' + targetScan.allianceTag : ''}] ` : '[👤 Mine] ';
        typeEl.textContent = srcLabel + (isBlocked ? '⚠️ BLOCKED ' : '') + formatScanType(targetScan.scanType);
      }
      const tickEl = document.getElementById(`sim-${side}-tick`);
      if (tickEl) tickEl.textContent = targetScan.tick !== undefined ? `Tick ${targetScan.tick}` : 'Tick ?';
      const resEl = document.getElementById(`sim-${side}-res-badge`);
      if (resEl && targetScan.resources) {
        resEl.textContent = `${formatNum(targetScan.resources.metal || 0)} M • ${formatNum(targetScan.resources.crystal || 0)} C • ${formatNum(targetScan.resources.eonium || 0)} E`;
      }
      const roidsEl = document.getElementById(`sim-${side}-roids-badge`);
      if (roidsEl && targetScan.asteroids) {
        roidsEl.textContent = `${formatNum(targetScan.asteroids.metal || 0)} M • ${formatNum(targetScan.asteroids.crystal || 0)} C • ${formatNum(targetScan.asteroids.eonium || 0)} E`;
      }
      const blockedBanner = document.getElementById(`sim-${side}-blocked-banner`);
      if (blockedBanner) blockedBanner.style.display = isBlocked ? 'block' : 'none';

      // Fleet selection & consolidation buttons
      const fleetOptionsEl = document.getElementById(`sim-${side}-scan-fleet-options`);
      if (fleetOptionsEl) {
        fleetOptionsEl.innerHTML = '';
        if (!isBlocked && (namedFleets.length > 0 || gCount > 0)) {
          const globalIdx = simScanTargets.indexOf(targetScan);
          // 1. All Consolidated Button
          const consBtn = document.createElement('button');
          consBtn.className = 'btn-refresh';
          consBtn.style.fontSize = '0.74rem';
          consBtn.style.padding = '0.15rem 0.45rem';
          consBtn.style.fontWeight = '700';
          consBtn.style.color = '#ffd54f';
          consBtn.style.borderColor = 'rgba(255,213,79,0.5)';
          consBtn.innerHTML = '⚡ Consolidate All';
          consBtn.title = 'Combine all scanned fleets and garrison into 1 fleet column';
          consBtn.onclick = () => loadScanIntoSide(side, targetScan, 'consolidated');
          fleetOptionsEl.appendChild(consBtn);

          // 2. Garrison Only Button
          if (gCount > 0) {
            const garBtn = document.createElement('button');
            garBtn.className = 'btn-refresh';
            garBtn.style.fontSize = '0.74rem';
            garBtn.style.padding = '0.15rem 0.45rem';
            garBtn.style.color = (side === 'atk') ? 'var(--cyan)' : '#ff8a80';
            garBtn.innerHTML = `🏛️ Garrison (${gCount.toLocaleString()})`;
            garBtn.title = 'Load only planet garrison';
            garBtn.onclick = () => loadScanIntoSide(side, targetScan, 'garrison');
            fleetOptionsEl.appendChild(garBtn);
          }

          // 3. Named Fleets Buttons
          namedFleets.forEach((nf, nfIdx) => {
            const nfCount = Object.values(nf.ships || {}).reduce((a, b) => a + (parseInt(b, 10) || 0), 0);
            const nfBtn = document.createElement('button');
            nfBtn.className = 'btn-refresh';
            nfBtn.style.fontSize = '0.74rem';
            nfBtn.style.padding = '0.15rem 0.45rem';
            nfBtn.style.color = (side === 'atk') ? 'var(--cyan)' : '#ff8a80';
            nfBtn.innerHTML = `🚀 "${escapeHtml(nf.name || 'Fleet ' + (nfIdx + 1))}" (${nfCount.toLocaleString()})`;
            nfBtn.title = `Load only fleet "${nf.name}"`;
            nfBtn.onclick = () => loadScanIntoSide(side, targetScan, `nf_${nfIdx}`);
            fleetOptionsEl.appendChild(nfBtn);
          });

          // 4. Separate All Fleets Button
          if (namedFleets.length > 0 && gCount > 0) {
            const sepBtn = document.createElement('button');
            sepBtn.className = 'btn-refresh';
            sepBtn.style.fontSize = '0.74rem';
            sepBtn.style.padding = '0.15rem 0.45rem';
            sepBtn.style.color = 'var(--text-dim)';
            sepBtn.innerHTML = '📋 All Separate';
            sepBtn.title = 'Load garrison and each fleet into separate columns';
            sepBtn.onclick = () => loadScanIntoSide(side, targetScan, 'separate');
            fleetOptionsEl.appendChild(sepBtn);
          }
        }
      }
    }

    renderAllFleetCards(side);
    recalcCoalitionSummary(side);
    renderBcalcMatrix();
    showToast(`Loaded ${list.length} fleet(s) into ${isAtk ? 'Attacker' : 'Defender'} from [${targetScan.coords || 'Scan'}]`);
  }

  function loadMyEmpireIntoAttacker() {
    simAttackerFleets = [];
    const namedFleets = simAttackerData.namedFleets || [];
    const myCoords = (homeDefenseData && homeDefenseData.coords) ? homeDefenseData.coords : (simAttackerData.coords || '');
    let count = 0;

    namedFleets.forEach((nf, idx) => {
      const shipCount = Object.values(nf.ships || {}).reduce((a, b) => a + (parseInt(b, 10) || 0), 0);
      if (shipCount > 0) {
        simAttackerFleets.push({
          id: 'atk_' + (simFleetSeq++),
          side: 'atk',
          name: `🚀 Fleet "${nf.name || 'Fleet ' + (idx + 1)}" [${nf.status || 'Active'}]`,
          sourceVal: `fleet_${idx}`,
          coords: myCoords,
          enabled: true,
          ships: Object.assign({}, nf.ships || {})
        });
        count++;
      }
    });

    if (count === 0) {
      initDefaultAttackerFleet();
      showToast('No active empire fleets found in flight. Added empty custom fleet.');
    } else {
      showToast(`Loaded ${count} empire fleet(s) into Attacker roster.`);
    }

    renderAllFleetCards('atk');
    recalcCoalitionSummary('atk');
    renderBcalcMatrix();
  }

  function getFleetShipCount(fleet) {
    if (!fleet || !fleet.ships) return 0;
    return Object.values(fleet.ships).reduce((acc, v) => acc + (parseInt(v, 10) || 0), 0);
  }

  function isPlaceholderFleet(fleet) {
    if (!fleet) return false;
    if (getFleetShipCount(fleet) > 0) return false;
    const name = (fleet.name || '').toLowerCase();
    const src = fleet.sourceVal || '';
    return (src === '__custom__' || name.includes('garrison') || name.includes('base') || name.includes('fleet 1') || name.includes('empty'));
  }

  function loadMyEmpireIntoDefender() {
    const rawHangar = (homeDefenseData && (homeDefenseData.hangarShips || homeDefenseData.garrisonShips))
      ? (homeDefenseData.hangarShips || homeDefenseData.garrisonShips)
      : (simAttackerData ? simAttackerData.hangarShips : {});
    const myCoords = (homeDefenseData && homeDefenseData.coords) ? homeDefenseData.coords : (simAttackerData.coords || '');

    // Synchronize defender coordinates inputs with home base coordinates
    if (myCoords) {
      const defCoordsInput = document.getElementById('sim-coords-input');
      if (defCoordsInput) defCoordsInput.value = myCoords;
      const bcalcDefCoordsInput = document.getElementById('sim-bcalc-def-coords-input');
      if (bcalcDefCoordsInput) bcalcDefCoordsInput.value = myCoords;
      simEnteredCoordsDef = myCoords;
      const activeLabel = document.getElementById('sim-coords-active-label');
      if (activeLabel) activeLabel.textContent = `[${myCoords}]`;
      const bottomCoords = document.getElementById('sim-bcalc-bottom-coords');
      if (bottomCoords && !bottomCoords.value) bottomCoords.value = myCoords;
    }

    // Overwrite defender garrison (fleet 0) instead of duplicating, and remove any other empty placeholder columns
    const garrisonShips = Object.assign({}, rawHangar || {});
    const garrisonFleet = {
      id: (simDefenderFleets.length > 0) ? simDefenderFleets[0].id : ('def_' + (simFleetSeq++)),
      side: 'def',
      name: '🏠 Home Colony Garrison',
      sourceVal: '__hangar__',
      coords: myCoords,
      enabled: true,
      ships: garrisonShips
    };

    if (simDefenderFleets.length > 0) {
      simDefenderFleets[0] = garrisonFleet;
      simDefenderFleets = [simDefenderFleets[0], ...simDefenderFleets.slice(1).filter(f => !isPlaceholderFleet(f))];
    } else {
      simDefenderFleets = [garrisonFleet];
    }

    if (homeDefenseData && homeDefenseData.pds) {
      const pds = homeDefenseData.pds;
      ['Shield Generator', 'Ion Cannon', 'Missile Silo', 'Laser Battery'].forEach(k => {
        const id = k === 'Shield Generator' ? 'shield' : (k === 'Ion Cannon' ? 'ion' : (k === 'Missile Silo' ? 'silo' : 'laser'));
        const chk = document.getElementById(`sim-pds-${id}-chk`);
        const lvl = document.getElementById(`sim-pds-${id}-lvl`);
        if (chk && lvl) {
          chk.checked = !!pds[k];
          if (pds[k]) lvl.value = pds[k];
        }
      });
    }

    showToast('Loaded your home base defense garrison and PDS into Defender (overwriting garrison).');
    renderAllFleetCards('def');
    recalcCoalitionSummary('def');
    renderBcalcMatrix();
  }

  // By default, initialize with clean EMPTY fleets (0 ships) waiting for user input
  function initDefaultAttackerFleet() {
    simAttackerFleets = [{
      id: 'atk_' + (simFleetSeq++),
      side: 'atk',
      name: 'Attacker Fleet 1',
      coords: '',
      enabled: true,
      sourceVal: '__custom__',
      ships: {}
    }];
  }

  function initDefaultDefenderFleet() {
    simDefenderFleets = [{
      id: 'def_' + (simFleetSeq++),
      side: 'def',
      name: 'Defender Garrison',
      coords: '',
      enabled: true,
      sourceVal: '__custom__',
      ships: {}
    }];
  }

  function setSimulationMode(mode, silent) {
    currentSimMode = mode;
    const assaultBtn = document.getElementById('sim-mode-assault-btn');
    const defenseBtn = document.getElementById('sim-mode-defense-btn');

    const atkTitle = document.getElementById('sim-atk-title');
    const defTitle = document.getElementById('sim-def-title');

    if (mode === 'defense') {
      if (assaultBtn) assaultBtn.classList.remove('active');
      if (defenseBtn) defenseBtn.classList.add('active');

      if (atkTitle) { atkTitle.textContent = '🚀 Attacking Forces (Coalition Fleets)'; atkTitle.style.color = '#ef4444'; }
      if (defTitle) { defTitle.textContent = '🛡️ Defender Forces (Your Base Garrison, Docked Fleets & PDS)'; defTitle.style.color = '#38bdf8'; }

      applyUserPdsToDefender(true);
      if (!silent) showToast('Simulation Mode: Defense (Defender on Left, Attacker on Right)');
    } else {
      if (assaultBtn) assaultBtn.classList.add('active');
      if (defenseBtn) defenseBtn.classList.remove('active');

      if (atkTitle) { atkTitle.textContent = '🚀 Attacker Forces (Your Coalition Fleets)'; atkTitle.style.color = '#ef4444'; }
      if (defTitle) { defTitle.textContent = '🛡️ Defender Forces (Enemy Target Planet & Garrison)'; defTitle.style.color = '#38bdf8'; }

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

      if (!silent) showToast('Simulation Mode: Planetary Assault (User is Attacker on Right)');
    }

    renderAllFleetCards('atk');
    renderAllFleetCards('def');
    recalcCoalitionSummary('atk');
    recalcCoalitionSummary('def');
    renderBcalcMatrix();
  }

  function swapSimulatorSides() {
    // Check if Defender currently has PDS
    const sChk = document.getElementById('sim-pds-shield-chk')?.checked;
    const iChk = document.getElementById('sim-pds-ion-chk')?.checked;
    const mChk = document.getElementById('sim-pds-silo-chk')?.checked;
    const lChk = document.getElementById('sim-pds-laser-chk')?.checked;
    const sLvl = parseInt(document.getElementById('sim-pds-shield-lvl')?.value || '0', 10);
    const iLvl = parseInt(document.getElementById('sim-pds-ion-lvl')?.value || '0', 10);
    const mLvl = parseInt(document.getElementById('sim-pds-silo-lvl')?.value || '0', 10);
    const lLvl = parseInt(document.getElementById('sim-pds-laser-lvl')?.value || '0', 10);
    const hasPds = (sChk && sLvl > 0) || (iChk && iLvl > 0) || (mChk && mLvl > 0) || (lChk && lLvl > 0);

    if (hasPds) {
      const proceed = confirm(
        "⚠️ PDS REMOVAL WARNING:\n\n" +
        "The current Defender forces have Planetary Defense Structures (PDS) installed.\n" +
        "Planetary defenses are stationary ground emplacements and CANNOT be transferred to Attacker forces.\n\n" +
        "Swapping sides will remove all PDS installations from defense. Do you wish to proceed?"
      );
      if (!proceed) return;

      // Clear PDS controls
      setControlValue('sim-pds-shield-chk', 'checked', false);
      setControlValue('sim-pds-ion-chk', 'checked', false);
      setControlValue('sim-pds-silo-chk', 'checked', false);
      setControlValue('sim-pds-laser-chk', 'checked', false);
      if (document.getElementById('sim-pds-shield-lvl')) document.getElementById('sim-pds-shield-lvl').value = 0;
      if (document.getElementById('sim-pds-ion-lvl')) document.getElementById('sim-pds-ion-lvl').value = 0;
      if (document.getElementById('sim-pds-silo-lvl')) document.getElementById('sim-pds-silo-lvl').value = 0;
      if (document.getElementById('sim-pds-laser-lvl')) document.getElementById('sim-pds-laser-lvl').value = 0;
    }

    // 1. Swap fleet rosters
    const tmp = simAttackerFleets;
    simAttackerFleets = simDefenderFleets;
    simDefenderFleets = tmp;

    simAttackerFleets.forEach(f => { f.side = 'atk'; });
    simDefenderFleets.forEach(f => { f.side = 'def'; });

    // 2. Swap coordinate inputs and search filters
    const tmpCoords = simEnteredCoordsAtk;
    simEnteredCoordsAtk = simEnteredCoordsDef;
    simEnteredCoordsDef = tmpCoords;

    const atkInput = document.getElementById('sim-atk-coords-input');
    const defInput = document.getElementById('sim-coords-input');
    if (atkInput && defInput) {
      const tmpVal = atkInput.value;
      atkInput.value = defInput.value;
      defInput.value = tmpVal;
    }

    const bcalcAtkInput = document.getElementById('sim-bcalc-atk-coords-input');
    const bcalcDefInput = document.getElementById('sim-bcalc-def-coords-input');
    if (bcalcAtkInput && bcalcDefInput) {
      const tmpVal = bcalcAtkInput.value;
      bcalcAtkInput.value = bcalcDefInput.value;
      bcalcDefInput.value = tmpVal;
    }

    const bcalcAtkTarget = document.getElementById('sim-bcalc-atk-target-select');
    const bcalcDefTarget = document.getElementById('sim-bcalc-def-target-select');
    if (bcalcAtkTarget && bcalcDefTarget) {
      const tmpIdx = bcalcAtkTarget.selectedIndex;
      bcalcAtkTarget.selectedIndex = bcalcDefTarget.selectedIndex;
      bcalcDefTarget.selectedIndex = tmpIdx;
    }

    updateCoordsScansDropdown('atk');
    updateCoordsScansDropdown('def');

    // 3. Toggle simulation mode (user role: Defender <-> Attacker)
    const newMode = currentSimMode === 'assault' ? 'defense' : 'assault';
    currentSimMode = newMode;
    const assaultBtn = document.getElementById('sim-mode-assault-btn');
    const defenseBtn = document.getElementById('sim-mode-defense-btn');

    const atkTitle = document.getElementById('sim-atk-title');
    const defTitle = document.getElementById('sim-def-title');

    if (newMode === 'defense') {
      if (assaultBtn) assaultBtn.classList.remove('active');
      if (defenseBtn) defenseBtn.classList.add('active');
      if (atkTitle) { atkTitle.textContent = '🚀 Attacking Forces (Coalition Fleets)'; atkTitle.style.color = '#ef4444'; }
      if (defTitle) { defTitle.textContent = '🛡️ Defender Forces (Your Base Garrison & PDS — You Defend)'; defTitle.style.color = '#38bdf8'; }
      applyUserPdsToDefender(true);
    } else {
      if (assaultBtn) assaultBtn.classList.add('active');
      if (defenseBtn) defenseBtn.classList.remove('active');
      if (atkTitle) { atkTitle.textContent = '🚀 Attacker Forces (Your Coalition Fleets — You Attack)'; atkTitle.style.color = '#ef4444'; }
      if (defTitle) { defTitle.textContent = '🛡️ Defender Forces (Enemy Target Planet & Garrison)'; defTitle.style.color = '#38bdf8'; }
    }

    renderAllFleetCards('atk');
    renderAllFleetCards('def');
    recalcCoalitionSummary('atk');
    recalcCoalitionSummary('def');
    renderBcalcMatrix();

    // 4. If simulation results were already displayed, re-render immediately to update perspective!
    if (lastSimResult) {
      renderSimResults(lastSimResult);
    }

    const roleDesc = newMode === 'assault' ? '🚀 Attacker (Right side)' : '🛡️ Defender (Left side)';
    showToast(`Sides swapped! You are now the ${roleDesc}.`);
  }

  function applyUserPdsToDefender(silent) {
    const pds = (homeDefenseData && homeDefenseData.pds) ? homeDefenseData.pds : {
      'Shield Generator': 5,
      'Laser Battery': 3,
      'Missile Silo': 3,
      'Ion Cannon': 3
    };

    setControlValue('sim-pds-shield-chk', 'checked', true);
    const sEl = document.getElementById('sim-pds-shield-lvl');
    if (sEl) sEl.value = pds['Shield Generator'] || 5;

    setControlValue('sim-pds-ion-chk', 'checked', true);
    const iEl = document.getElementById('sim-pds-ion-lvl');
    if (iEl) iEl.value = pds['Ion Cannon'] || 3;

    setControlValue('sim-pds-silo-chk', 'checked', true);
    const mEl = document.getElementById('sim-pds-silo-lvl');
    if (mEl) mEl.value = pds['Missile Silo'] || 3;

    setControlValue('sim-pds-laser-chk', 'checked', true);
    const lEl = document.getElementById('sim-pds-laser-lvl');
    if (lEl) lEl.value = pds['Laser Battery'] || 3;

    if (!silent) {
      showToast('Loaded your live Planetary Defense Structures (PDS)');
    }
  }

  function setControlValue(id, prop, val) {
    const el = document.getElementById(id);
    if (el) el[prop] = val;
  }

  function resolveFleetPreset(presetVal, side) {
    let ships = {};
    let name = (side === 'atk') ? 'Attacker Fleet' : 'Defender Fleet';
    let sourceVal = presetVal || '__custom__';
    let coords = '';

    if (!presetVal || presetVal === '__custom__') {
      return { ships: {}, name: name, sourceVal: '__custom__', coords: '' };
    }

    // Attacker cannot add base garrison or home hangar (stationary defender-only)
    if (side === 'atk' && (presetVal === '__hangar__' || presetVal === '__my_hangar__' || presetVal === '__home_hangar__' || presetVal === '__garrison__' || (presetVal.startsWith('scan_') && presetVal.includes('_garrison')))) {
      showToast('Base Garrison is stationary and cannot be added to Attacker forces.', 'warning');
      return { ships: {}, name: 'Attacker Fleet', sourceVal: '__custom__', coords: '' };
    }

    if (presetVal === '__hangar__' || presetVal === '__my_hangar__' || presetVal === '__home_hangar__') {
      const h = (simAttackerData && simAttackerData.hangarShips && Object.keys(simAttackerData.hangarShips).length > 0)
        ? simAttackerData.hangarShips
        : (homeDefenseData ? (homeDefenseData.hangarShips || homeDefenseData.garrisonShips) : {});
      ships = Object.assign({}, h || {});
      name = '🏠 Base Garrison (Docked at Base)';
      sourceVal = '__hangar__';
      coords = (homeDefenseData && homeDefenseData.coords) ? homeDefenseData.coords : (simAttackerData.coords || '');
    } else if (presetVal.startsWith('fleet_') || presetVal.startsWith('myfleet_')) {
      const idx = parseInt(presetVal.replace('myfleet_', '').replace('fleet_', ''), 10);
      const f = (simAttackerData.namedFleets || [])[idx];
      if (f) {
        ships = Object.assign({}, f.ships || {});
        const isDocked = (f.status === 'DOCKED');
        const statusLabel = isDocked ? 'Docked at Base' : (f.status || 'Active');
        name = `🚀 Fleet "${f.name || 'Unnamed'}" [${statusLabel}]`;
        sourceVal = `fleet_${idx}`;
        coords = (homeDefenseData && homeDefenseData.coords) ? homeDefenseData.coords : (simAttackerData.coords || '');
      }
    } else if (presetVal === '__garrison__') {
      if (currentTargetScan) {
        ships = Object.assign({}, currentTargetScan.garrisonShips || {});
        const typeLabel = formatScanType(currentTargetScan.scanType);
        coords = currentTargetScan.coords || '';
        name = `[${typeLabel}] Garrison [${coords || 'Target'}]`;
        sourceVal = '__garrison__';
      }
    } else if (presetVal.startsWith('nf_')) {
      const idx = parseInt(presetVal.split('_')[1], 10);
      if (currentTargetScan && currentTargetScan.namedFleets) {
        const nf = currentTargetScan.namedFleets[idx];
        if (nf) {
          ships = Object.assign({}, nf.ships || {});
          coords = currentTargetScan.coords || '';
          name = `Fleet "${nf.name || 'Fleet'}" [${coords || 'Target'}]`;
          sourceVal = presetVal;
        }
      }
    } else if (presetVal.startsWith('scan_')) {
      const parts = presetVal.split('_');
      const tIdx = parseInt(parts[1], 10);
      const target = (simScanTargets || [])[tIdx];
      if (target) {
        coords = target.coords || `Target ${tIdx + 1}`;
        const typeLabel = formatScanType(target.scanType);
        if (parts[2] === 'consolidated') {
          // Combine named fleets, and garrison if defender
          const merged = {};
          if (side !== 'atk') {
            Object.entries(target.garrisonShips || {}).forEach(([sid, cnt]) => {
              merged[sid] = (merged[sid] || 0) + (parseInt(cnt, 10) || 0);
            });
          }
          (target.namedFleets || []).forEach(nf => {
            Object.entries(nf.ships || {}).forEach(([sid, cnt]) => {
              merged[sid] = (merged[sid] || 0) + (parseInt(cnt, 10) || 0);
            });
          });
          ships = merged;
          name = (side === 'atk') ? `[${typeLabel}] Consolidated Fleets [${coords}]` : `[${typeLabel}] Consolidated [${coords}]`;
        } else if (parts[2] === 'garrison') {
          ships = Object.assign({}, target.garrisonShips || {});
          name = `[${typeLabel}] Garrison [${coords}]`;
        } else if (parts[2] === 'nf') {
          const nfIdx = parseInt(parts[3], 10);
          const nf = (target.namedFleets || [])[nfIdx];
          if (nf) {
            ships = Object.assign({}, nf.ships || {});
            name = `[${typeLabel}] Fleet "${nf.name || 'Fleet'}" [${coords}]`;
          }
        }
      }
    }
    return { ships, name, sourceVal, coords };
  }

  function addAttackerFleet(presetVal, coords) {
    const resolved = resolveFleetPreset(presetVal, 'atk');
    const finalCoords = coords || resolved.coords || simEnteredCoordsAtk || '';

    // Update bottom coordinates input with these coordinates
    const bottomCoords = document.getElementById('sim-bcalc-bottom-coords');
    if (bottomCoords && (resolved.coords || !bottomCoords.value) && finalCoords) {
      bottomCoords.value = resolved.coords || finalCoords;
    }

    // Check if there is an existing empty placeholder fleet to replace
    const placeholderIdx = simAttackerFleets.findIndex(f => isPlaceholderFleet(f));
    if (placeholderIdx !== -1) {
      const f = simAttackerFleets[placeholderIdx];
      f.name = presetVal ? resolved.name : (finalCoords ? `Attacker Fleet [${finalCoords}]` : (placeholderIdx === 0 ? 'Attacker Fleet 1' : `Attacker Fleet ${placeholderIdx + 1}`));
      f.ships = presetVal ? Object.assign({}, resolved.ships) : {};
      f.sourceVal = resolved.sourceVal;
      f.coords = finalCoords;
      // Prune any other empty placeholders
      simAttackerFleets = simAttackerFleets.filter((fl, i) => i === placeholderIdx || !isPlaceholderFleet(fl));
      renderAllFleetCards('atk');
      recalcCoalitionSummary('atk');
      renderBcalcMatrix();
      showToast(`Updated Attacker with ${f.name}`);
      return;
    }

    const newIdx = simAttackerFleets.length + 1;
    const finalName = presetVal ? resolved.name : (finalCoords ? `Attacker Fleet ${newIdx} [${finalCoords}]` : `Attacker Fleet ${newIdx}`);
    const finalShips = presetVal ? Object.assign({}, resolved.ships) : {};

    simAttackerFleets.push({
      id: 'atk_' + (simFleetSeq++),
      side: 'atk',
      name: finalName,
      coords: finalCoords,
      enabled: true,
      sourceVal: resolved.sourceVal,
      ships: finalShips
    });
    renderAllFleetCards('atk');
    recalcCoalitionSummary('atk');
    renderBcalcMatrix();
    showToast(`Added ${finalName}`);
  }

  function addDefenderFleet(presetVal, coords) {
    const resolved = resolveFleetPreset(presetVal, 'def');
    const finalCoords = coords || resolved.coords || simEnteredCoordsDef || '';

    // Update bottom coordinates input with these coordinates
    const bottomCoords = document.getElementById('sim-bcalc-bottom-coords');
    if (bottomCoords && (resolved.coords || !bottomCoords.value) && finalCoords) {
      bottomCoords.value = resolved.coords || finalCoords;
    }

    // Special case: If adding Base Garrison (__hangar__), overwrite Defender Fleet 0 (Base Garrison)
    if (presetVal === '__hangar__' || presetVal === '__my_hangar__' || presetVal === '__home_hangar__') {
      const fName = resolved.name || (finalCoords ? `Home Base Garrison [${finalCoords}]` : 'Defender Base Garrison');
      if (simDefenderFleets.length > 0) {
        simDefenderFleets[0].name = fName;
        simDefenderFleets[0].ships = Object.assign({}, resolved.ships);
        simDefenderFleets[0].sourceVal = '__hangar__';
        simDefenderFleets[0].coords = finalCoords;
        simDefenderFleets[0].enabled = true;
      } else {
        simDefenderFleets.push({
          id: 'def_' + (simFleetSeq++),
          side: 'def',
          name: fName,
          coords: finalCoords,
          enabled: true,
          sourceVal: '__hangar__',
          ships: Object.assign({}, resolved.ships)
        });
      }
      // Prune any remaining empty placeholder columns so the user never has an unnecessary column
      if (simDefenderFleets.length > 1) {
        simDefenderFleets = [simDefenderFleets[0], ...simDefenderFleets.slice(1).filter(f => !isPlaceholderFleet(f))];
      }
      applyUserPdsToDefender(true);
      renderAllFleetCards('def');
      recalcCoalitionSummary('def');
      renderBcalcMatrix();
      showToast(`Loaded ${fName} into Defender Base.`);
      return;
    }

    // Check if there is an existing empty placeholder fleet to replace
    const placeholderIdx = simDefenderFleets.findIndex(f => isPlaceholderFleet(f));
    if (placeholderIdx !== -1) {
      const f = simDefenderFleets[placeholderIdx];
      f.name = presetVal ? resolved.name : (finalCoords ? `Defender Fleet [${finalCoords}]` : (placeholderIdx === 0 ? 'Defender Garrison' : `Defender Fleet ${placeholderIdx + 1}`));
      f.ships = presetVal ? Object.assign({}, resolved.ships) : {};
      f.sourceVal = resolved.sourceVal;
      f.coords = finalCoords;
      // Prune any other empty placeholders
      simDefenderFleets = simDefenderFleets.filter((fl, i) => i === placeholderIdx || !isPlaceholderFleet(fl));
      renderAllFleetCards('def');
      recalcCoalitionSummary('def');
      renderBcalcMatrix();
      showToast(`Updated Defender with ${f.name}`);
      return;
    }

    const newIdx = simDefenderFleets.length + 1;
    const finalName = presetVal ? resolved.name : (finalCoords ? `Defender Fleet ${newIdx} [${finalCoords}]` : `Defender Fleet ${newIdx}`);
    const finalShips = presetVal ? Object.assign({}, resolved.ships) : {};

    simDefenderFleets.push({
      id: 'def_' + (simFleetSeq++),
      side: 'def',
      name: finalName,
      coords: finalCoords,
      enabled: true,
      sourceVal: resolved.sourceVal,
      ships: finalShips
    });
    renderAllFleetCards('def');
    recalcCoalitionSummary('def');
    renderBcalcMatrix();
    showToast(`Added ${finalName}`);
  }

  function addFleetFromCurrentCoords(side) {
    const isAtk = (side === 'atk');
    let entered = isAtk ? simEnteredCoordsAtk : simEnteredCoordsDef;
    if (!entered) {
      const inputId = isAtk ? 'sim-atk-coords-input' : 'sim-coords-input';
      entered = document.getElementById(inputId)?.value?.trim() || '';
    }
    if (!entered) {
      entered = prompt(`Enter coordinates for new ${isAtk ? 'Attacker' : 'Defender'} fleet (e.g. 12:1:5):`, '');
      if (!entered) return;
      entered = entered.trim();
      if (isAtk) {
        onCoordsInputChanged('atk', entered);
      } else {
        onCoordsInputChanged('def', entered);
      }
    }

    if (isAtk) {
      addAttackerFleet(null, entered);
    } else {
      addDefenderFleet(null, entered);
    }
  }

  function promptFleetCoords(side, fleetId) {
    const list = (side === 'atk') ? simAttackerFleets : simDefenderFleets;
    const fleet = list.find(f => f.id === fleetId);
    if (!fleet) return;
    const newCoords = prompt(`Enter coordinates for fleet "${fleet.name}":`, fleet.coords || '');
    if (newCoords !== null) {
      onFleetCoordsChange(side, fleetId, newCoords.trim());
    }
  }

  function onFleetCoordsChange(side, fleetId, newCoords) {
    const list = (side === 'atk') ? simAttackerFleets : simDefenderFleets;
    const fleet = list.find(f => f.id === fleetId);
    if (fleet) {
      fleet.coords = newCoords || '';
      const cInput = document.getElementById(`fleet-coords-${fleetId}`);
      if (cInput && cInput.value !== fleet.coords) cInput.value = fleet.coords;
      renderBcalcMatrix();
    }
  }

  function consolidateFleets(side) {
    const list = (side === 'atk') ? simAttackerFleets : simDefenderFleets;
    if (!list || list.length <= 1) {
      showToast(`Only ${list.length} fleet on ${side === 'atk' ? 'Attacker' : 'Defender'} side. Nothing to consolidate.`);
      return;
    }

    const mergedShips = {};
    const coordsSet = new Set();
    list.forEach(f => {
      if (f.coords) coordsSet.add(f.coords);
      Object.entries(f.ships || {}).forEach(([sid, cnt]) => {
        mergedShips[sid] = (mergedShips[sid] || 0) + (parseInt(cnt, 10) || 0);
      });
    });

    const coordsArr = Array.from(coordsSet);
    const combinedCoords = coordsArr.length > 0 ? coordsArr.join(', ') : '';
    const sideLabel = side === 'atk' ? 'Attacking Forces' : 'Defending Forces';
    const finalName = `⚡ Consolidated ${sideLabel}${combinedCoords ? ' [' + combinedCoords + ']' : ''}`;

    const consolidatedFleet = {
      id: side + '_' + (simFleetSeq++),
      side: side,
      name: finalName,
      coords: combinedCoords,
      enabled: true,
      sourceVal: '__custom__',
      ships: mergedShips
    };

    if (side === 'atk') {
      simAttackerFleets = [consolidatedFleet];
    } else {
      simDefenderFleets = [consolidatedFleet];
    }

    renderAllFleetCards(side);
    recalcCoalitionSummary(side);
    renderBcalcMatrix();
    showToast(`Consolidated ${list.length} fleets into 1 unified ${sideLabel} column!`);
  }

  let currentPickerSide = 'atk';

  function setPickerSourceFilter(src) {
    simPickerSourceFilter = src;
    ['all', 'user', 'ally'].forEach(s => {
      const btn = document.getElementById(`sim-picker-src-${s}-btn`);
      if (btn) {
        if (s === src) btn.classList.add('active');
        else btn.classList.remove('active');
      }
    });
    renderScanPickerList();
  }

  function openScanPickerModal(side) {
    currentPickerSide = side || 'atk';
    const modal = document.getElementById('sim-scan-picker-modal');
    if (!modal) return;

    const titleEl = document.getElementById('sim-picker-title');
    if (titleEl) {
      if (currentPickerSide === 'atk') {
        titleEl.textContent = '🚀 Choose a Scanned Fleet to Add to Attacker Coalition';
        titleEl.style.color = '#ef4444';
      } else {
        titleEl.textContent = '🛡️ Choose a Scanned Fleet to Add to Defender Forces';
        titleEl.style.color = '#38bdf8';
      }
    }

    const searchInput = document.getElementById('sim-picker-search');
    if (searchInput) searchInput.value = '';

    renderScanPickerList('');
    modal.style.display = 'flex';

    // Immediately trigger fresh server & alliance scan sync
    refreshScanTargets(false);
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
      // Source filter check
      if (simPickerSourceFilter !== 'all' && t.source !== simPickerSourceFilter) {
        return;
      }

      const typeLabel = formatScanType(t.scanType);
      const coords = t.coords || `Target ${tIdx + 1}`;
      const tick = t.tick ? `Tick ${t.tick}` : '';
      const owner = (t.owner && t.owner !== 'Unknown') ? t.owner : '';
      const pName = t.planetName ? t.planetName : '';
      const gShips = t.garrisonShips || {};
      const gTotal = Object.values(gShips).reduce((a, b) => a + (parseInt(b, 10) || 0), 0);
      const namedFleets = t.namedFleets || [];

      // Check search match including source terms and planet name
      const sourceTerms = t.source === 'ally' ? 'ally alliance intel' : 'user mine personal own';
      const searchHaystack = `${typeLabel} ${coords} ${tick} ${owner} ${pName} ${sourceTerms} ${t.allianceTag || ''} ${Object.keys(gShips).join(' ')} ${namedFleets.map(f => f.name + ' ' + Object.keys(f.ships||{}).join(' ')).join(' ')}`.toLowerCase();
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
      const sourceBadgeHtml = t.source === 'ally'
        ? `<span style="display: inline-block; font-size: 0.72rem; font-weight: 700; padding: 0.1rem 0.4rem; border-radius: 3px; background: rgba(167,139,250,0.15); color: #a78bfa; border: 1px solid rgba(167,139,250,0.4); margin-right: 0.35rem;">🤝 Ally${t.allianceTag ? ' ' + t.allianceTag : ''}</span>`
        : `<span style="display: inline-block; font-size: 0.72rem; font-weight: 700; padding: 0.1rem 0.4rem; border-radius: 3px; background: rgba(0,229,255,0.1); color: var(--cyan); border: 1px solid rgba(0,229,255,0.3); margin-right: 0.35rem;">👤 Mine</span>`;

      hdr.innerHTML = `
        <div>
          ${sourceBadgeHtml}
          <span style="display: inline-block; font-size: 0.72rem; font-weight: 700; padding: 0.1rem 0.4rem; border-radius: 3px; background: rgba(255,255,255,0.08); color: ${typeBadgeColor}; border: 1px solid ${typeBadgeColor}40; margin-right: 0.4rem;">
            ${typeLabel}
          </span>
          <strong style="color: #fff; font-size: 0.9rem;">${pName ? pName + ' ' : ''}[${coords}]</strong>
          <span style="color: var(--text-dim); font-size: 0.78rem; margin-left: 0.4rem;">(${tick}${owner ? ' • ' + owner : ''})</span>
        </div>
      `;
      card.appendChild(hdr);

      if (t.status === 'blocked' || t.isBlocked) {
        const blockedRow = document.createElement('div');
        blockedRow.style.padding = '0.4rem 0.6rem';
        blockedRow.style.background = 'rgba(234, 179, 8, 0.1)';
        blockedRow.style.border = '1px solid rgba(234, 179, 8, 0.3)';
        blockedRow.style.borderRadius = '4px';
        blockedRow.style.color = 'var(--yellow)';
        blockedRow.style.fontSize = '0.8rem';
        blockedRow.textContent = '⚠️ This scan was blocked by enemy Wave Distorters. No fleet data retrieved.';
        card.appendChild(blockedRow);
        container.appendChild(card);
        return;
      }

      // Consolidated Option
      if (currentPickerSide === 'atk') {
        // Attacker Consolidated: only named fleets, strictly excludes garrison
        const nfTotalShips = namedFleets.reduce((acc, nf) => acc + Object.values(nf.ships || {}).reduce((a, b) => a + (parseInt(b, 10) || 0), 0), 0);
        if (namedFleets.length > 0) {
          const consRow = document.createElement('div');
          consRow.style.display = 'flex';
          consRow.style.justifyContent = 'space-between';
          consRow.style.alignItems = 'center';
          consRow.style.padding = '0.4rem 0.6rem';
          consRow.style.background = 'rgba(255,213,79,0.08)';
          consRow.style.border = '1px solid rgba(255,213,79,0.3)';
          consRow.style.borderRadius = '4px';
          consRow.style.marginBottom = '0.4rem';

          consRow.innerHTML = `
            <div>
              <div style="font-weight: 700; font-size: 0.82rem; color: #ffd54f;">⚡ Consolidated Fleets (Excl. Garrison) (${nfTotalShips.toLocaleString()} ships)</div>
              <div style="font-size: 0.74rem; color: var(--text-dim);">Combines all ${namedFleets.length} named fleet(s) into 1 fleet (Garrison excluded)</div>
            </div>
            <button class="btn-refresh" style="padding: 0.2rem 0.6rem; font-size: 0.78rem; font-weight: 700; color: #ffd54f; border-color: rgba(255,213,79,0.5); white-space: nowrap;" onclick="pickScanFleet('scan_${tIdx}_consolidated')">
              ⚡ Add Fleets
            </button>
          `;
          card.appendChild(consRow);
        }
      } else {
        // Defender Consolidated: combines garrison and named fleets
        if (namedFleets.length > 0 && gTotal > 0) {
          const consRow = document.createElement('div');
          consRow.style.display = 'flex';
          consRow.style.justifyContent = 'space-between';
          consRow.style.alignItems = 'center';
          consRow.style.padding = '0.4rem 0.6rem';
          consRow.style.background = 'rgba(255,213,79,0.08)';
          consRow.style.border = '1px solid rgba(255,213,79,0.3)';
          consRow.style.borderRadius = '4px';
          consRow.style.marginBottom = '0.4rem';

          const allTotal = gTotal + namedFleets.reduce((acc, nf) => acc + Object.values(nf.ships || {}).reduce((a, b) => a + (parseInt(b, 10) || 0), 0), 0);
          consRow.innerHTML = `
            <div>
              <div style="font-weight: 700; font-size: 0.82rem; color: #ffd54f;">⚡ Consolidated Fleets (${allTotal.toLocaleString()} total ships)</div>
              <div style="font-size: 0.74rem; color: var(--text-dim);">Combines Garrison and all ${namedFleets.length} named fleet(s) into 1 fleet</div>
            </div>
            <button class="btn-refresh" style="padding: 0.2rem 0.6rem; font-size: 0.78rem; font-weight: 700; color: #ffd54f; border-color: rgba(255,213,79,0.5); white-space: nowrap;" onclick="pickScanFleet('scan_${tIdx}_consolidated')">
              ⚡ Add All Consolidated
            </button>
          `;
          card.appendChild(consRow);
        }
      }

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

        const actionHtml = currentPickerSide === 'atk'
          ? `<span style="font-size: 0.72rem; padding: 0.2rem 0.5rem; background: rgba(239,68,68,0.12); color: #fca5a5; border: 1px solid rgba(239,68,68,0.3); border-radius: 4px; font-weight: 600;">Stationary Garrison (Defender Only)</span>`
          : `<button class="btn-refresh" style="padding: 0.2rem 0.6rem; font-size: 0.78rem; font-weight: 600; color: #38bdf8; border-color: rgba(56,189,248,0.45); white-space: nowrap;" onclick="pickScanFleet('scan_${tIdx}_garrison')">+ Add to Defender</button>`;

        gRow.innerHTML = `
          <div>
            <div style="font-weight: 600; font-size: 0.82rem; color: #fff;">🏛️ Planet Garrison (${gTotal.toLocaleString()} ships)</div>
            <div style="font-size: 0.74rem; color: var(--text-dim);">${shipNames || 'No ships'}${extraShips}</div>
          </div>
          ${actionHtml}
        `;
        card.appendChild(gRow);
      }

      // Section: Named Fleets
      namedFleets.forEach((nf, nfIdx) => {
        const nfTotal = Object.values(nf.ships || {}).reduce((a, b) => a + (parseInt(b, 10) || 0), 0);
        const nfRow = document.createElement('div');
        nfRow.style.display = 'flex';
        nfRow.style.justifyContent = 'space-between';
        nfRow.style.alignItems = 'center';
        nfRow.style.padding = '0.4rem 0.6rem';
        nfRow.style.background = 'rgba(0,0,0,0.2)';
        nfRow.style.borderRadius = '4px';
        nfRow.style.marginBottom = '0.4rem';

        const shipNames = Object.entries(nf.ships || {}).slice(0, 4).map(([sid, cnt]) => `${cnt}x ${sid.replace('main-', '').replace(/-/g, ' ')}`).join(', ');
        const extraShips = Object.keys(nf.ships || {}).length > 4 ? ` +${Object.keys(nf.ships || {}).length - 4} more` : '';

        const btnColor = currentPickerSide === 'atk' ? '#f87171' : '#38bdf8';
        const btnBorder = currentPickerSide === 'atk' ? 'rgba(239,68,68,0.45)' : 'rgba(56,189,248,0.45)';

        nfRow.innerHTML = `
          <div>
            <div style="font-weight: 600; font-size: 0.82rem; color: #fff;">🚀 Fleet "${nf.name || 'Unnamed'}" (${nfTotal.toLocaleString()} ships) [${nf.status || 'DOCKED'}]</div>
            <div style="font-size: 0.74rem; color: var(--text-dim);">${shipNames || 'No ships'}${extraShips}</div>
          </div>
          <button class="btn-refresh" style="padding: 0.2rem 0.6rem; font-size: 0.78rem; font-weight: 600; color: ${btnColor}; border-color: ${btnBorder}; white-space: nowrap;" onclick="pickScanFleet('scan_${tIdx}_nf_${nfIdx}')">
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
    if (currentPickerSide === 'atk' && (presetVal.includes('_garrison') || presetVal === '__hangar__' || presetVal === '__garrison__')) {
      showToast('Base Garrison is stationary and cannot be added to Attacker forces.', 'warning');
      return;
    }
    if (currentPickerSide === 'atk') {
      addAttackerFleet(presetVal);
    } else {
      addDefenderFleet(presetVal);
    }
    const resolved = resolveFleetPreset(presetVal, currentPickerSide);
    if (resolved && resolved.coords) {
      const bottomCoords = document.getElementById('sim-bcalc-bottom-coords');
      if (bottomCoords) bottomCoords.value = resolved.coords;
    }
    closeScanPickerModal();
  }

  function quickAddFleetFromScan(side) {
    openExecuteScanModal(side);
  }

  let currentExecScanSide = 'def';

  function openExecuteScanModal(side) {
    currentExecScanSide = side || 'def';
    const modal = document.getElementById('sim-execute-scan-modal');
    if (!modal) return;

    // 1. Update side selection buttons & header
    setExecScanSide(currentExecScanSide);

    // 2. Prepopulate coords input if available
    const coordsInput = document.getElementById('exec-scan-coords');
    let prefill = '';
    if (side === 'atk') {
      prefill = simEnteredCoordsAtk || document.getElementById('sim-bcalc-atk-coords-input')?.value || '';
    } else {
      prefill = simEnteredCoordsDef || document.getElementById('sim-bcalc-def-coords-input')?.value || '';
    }
    if (!prefill) {
      prefill = document.getElementById('sim-bcalc-bottom-coords')?.value || '';
    }
    if (coordsInput) {
      coordsInput.value = prefill;
      onExecScanCoordsInput(prefill);
    }

    // 3. Populate planet quickpick jump dropdown
    const qp = document.getElementById('exec-scan-planet-quickpick');
    if (qp) {
      qp.innerHTML = '<option value="">Jump...</option>';
      (universePlanetsList || []).forEach(p => {
        if (!p.coords) return;
        const opt = document.createElement('option');
        opt.value = p.coords;
        opt.textContent = `${p.name || 'Planet'} [${p.coords}]`;
        if (prefill && normalizeCoords(prefill) === normalizeCoords(p.coords)) {
          opt.selected = true;
        }
        qp.appendChild(opt);
      });
    }

    // 4. Calculate scans performed this tick
    const tickBadge = document.getElementById('exec-scan-tick-badge');
    if (tickBadge) tickBadge.textContent = currentTick || '---';

    const quotaBadge = document.getElementById('exec-scan-quota-badge');
    if (quotaBadge) {
      const scansThisTick = (simScanTargets || []).filter(t => t.source === 'user' && t.tick === currentTick).length;
      const remaining = Math.max(0, 3 - scansThisTick);
      quotaBadge.textContent = `${scansThisTick} / 3 Used (${remaining} Remaining)`;
      quotaBadge.style.color = (remaining > 0 ? '#69f0ae' : '#ef4444');
    }

    // 5. Update Eonium status
    const eoniumBadge = document.getElementById('exec-scan-eonium-badge');
    if (eoniumBadge) {
      let eon = '---';
      if (typeof currentPlanetData !== 'undefined' && currentPlanetData && currentPlanetData.eonium !== undefined) {
        eon = Number(currentPlanetData.eonium).toLocaleString() + ' Eon';
      } else if (typeof refData !== 'undefined' && refData && refData.planet && refData.planet.eonium !== undefined) {
        eon = Number(refData.planet.eonium).toLocaleString() + ' Eon';
      }
      eoniumBadge.textContent = eon;
    }

    // 6. Reset error alert & submit button
    const errBox = document.getElementById('exec-scan-error');
    if (errBox) {
      errBox.style.display = 'none';
      errBox.textContent = '';
    }
    const submitBtn = document.getElementById('exec-scan-submit-btn');
    if (submitBtn) {
      submitBtn.disabled = false;
      submitBtn.textContent = '📡 Launch Scan & Add Fleet';
    }

    onExecScanTypeChange();
    modal.style.display = 'flex';
  }

  function closeExecuteScanModal() {
    const modal = document.getElementById('sim-execute-scan-modal');
    if (modal) modal.style.display = 'none';
  }

  function setExecScanSide(side) {
    currentExecScanSide = side || 'def';
    const defBtn = document.getElementById('exec-scan-side-def-btn');
    const atkBtn = document.getElementById('exec-scan-side-atk-btn');
    const title = document.getElementById('exec-scan-title');
    if (side === 'atk') {
      if (defBtn) defBtn.classList.remove('active');
      if (atkBtn) atkBtn.classList.add('active');
      if (title) {
        title.textContent = '🚀 Execute Live Scan & Deploy to Attacker';
        title.style.color = 'var(--cyan)';
      }
    } else {
      if (defBtn) defBtn.classList.add('active');
      if (atkBtn) atkBtn.classList.remove('active');
      if (title) {
        title.textContent = '🛡️ Execute Live Scan & Deploy to Defender';
        title.style.color = '#ff8a80';
      }
    }
  }

  function onExecScanQuickPick(val) {
    const input = document.getElementById('exec-scan-coords');
    if (input) {
      input.value = val || '';
      onExecScanCoordsInput(val || '');
    }
  }

  function onExecScanCoordsInput(val) {
    const label = document.getElementById('exec-scan-planet-label');
    if (!label) return;
    const clean = normalizeCoords(val);
    if (!clean) {
      label.textContent = '';
      return;
    }
    const found = (universePlanetsList || []).find(p => normalizeCoords(p.coords) === clean);
    if (found) {
      label.innerHTML = `🪐 <strong>${escapeHtml(found.name || 'Planet')}</strong> [${found.coords}]`;
    } else {
      label.innerHTML = `<span style="color:var(--text-dim);">Coordinates [${clean}] (Unmapped or Deep Space)</span>`;
    }
  }

  function onExecScanTypeChange() {
    const sel = document.getElementById('exec-scan-type');
    const desc = document.getElementById('exec-scan-type-desc');
    if (!sel || !desc) return;
    const descriptions = {
      'MILITARY_SCAN': 'Scans all defending ships, docked named fleets, orbital PDS structures, and military research levels.',
      'FLEET_COMPOSITION_SCAN': 'Detailed scan of ship types, hulls, and fleet distributions on the target planet.',
      'DEEP_SCAN': 'Comprehensive planetary manifest: ships, structures, asteroid mines, and resources.',
      'INCOMING_SCAN': 'Scans incoming hostile and friendly fleets currently in flight toward this planet.',
      'SURFACE_SCAN': 'Basic surface constructions, asteroid mines, and ground installations.'
    };
    desc.textContent = descriptions[sel.value] || 'Executes a planetary wave scan on target.';
  }

  async function submitExecuteScan() {
    const coordsInput = document.getElementById('exec-scan-coords');
    const coords = coordsInput ? coordsInput.value.trim() : '';
    const cleanCoords = normalizeCoords(coords);
    const errBox = document.getElementById('exec-scan-error');
    const submitBtn = document.getElementById('exec-scan-submit-btn');

    if (!cleanCoords) {
      if (errBox) {
        errBox.style.display = 'block';
        errBox.textContent = '⚠️ Please enter valid coordinates (e.g. 12:1:1) to scan.';
      }
      return;
    }

    if (errBox) {
      errBox.style.display = 'none';
      errBox.textContent = '';
    }

    const scanType = document.getElementById('exec-scan-type')?.value || 'MILITARY_SCAN';
    const ingestMode = document.querySelector('input[name="exec-ingest-mode"]:checked')?.value || 'consolidated';

    if (submitBtn) {
      submitBtn.disabled = true;
      submitBtn.innerHTML = '<span class="loading-spinner" style="display:inline-block; vertical-align:middle; margin-right:0.4rem;"></span> Scanning Server...';
    }

    try {
      const res = await fetch('/api/combat/execute_scan_and_add', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          coords: cleanCoords,
          scanType: scanType,
          side: currentExecScanSide,
          ingestMode: ingestMode
        })
      });

      const json = await res.json();
      if (!json.success) {
        throw new Error(json.error || 'Server rejected scan request');
      }

      // Check if blocked by Wave Distorter
      if (json.blocked) {
        showToast(`⚠️ Scan on [${cleanCoords}] blocked by Wave Distorters! No fleet data retrieved.`);
        // Deploy a blocked placeholder fleet column so the user sees the target was scanned
        const blockedFleet = {
          id: currentExecScanSide + '_' + (simFleetSeq++),
          side: currentExecScanSide,
          name: `[BLOCKED ${formatScanType(scanType)}] [${cleanCoords}]`,
          coords: cleanCoords,
          enabled: true,
          sourceVal: '__custom__',
          ships: {}
        };
        if (currentExecScanSide === 'atk') {
          simAttackerFleets.push(blockedFleet);
          renderAllFleetCards('atk');
          recalcCoalitionSummary('atk');
        } else {
          simDefenderFleets.push(blockedFleet);
          renderAllFleetCards('def');
          recalcCoalitionSummary('def');
        }
        renderBcalcMatrix();
        closeExecuteScanModal();
        return;
      }

      // Successful scan ingestion
      const scanData = json.scan || {};
      const gShips = scanData.garrisonShips || {};
      const namedFleets = scanData.namedFleets || [];
      const gTotal = Object.values(gShips).reduce((a, b) => a + (parseInt(b, 10) || 0), 0);
      const typeLabel = formatScanType(json.scanType || scanType);

      if (ingestMode === 'consolidated') {
        // Merge all garrison & named fleets
        const mergedShips = Object.assign({}, gShips);
        namedFleets.forEach(nf => {
          Object.entries(nf.ships || {}).forEach(([sid, cnt]) => {
            mergedShips[sid] = (mergedShips[sid] || 0) + (parseInt(cnt, 10) || 0);
          });
        });

        const fleetObj = {
          ships: mergedShips,
          name: `[${typeLabel}] Consolidated [${cleanCoords}]`,
          sourceVal: '__custom__',
          coords: cleanCoords
        };

        deployFleetObjectIntoSide(currentExecScanSide, fleetObj);
      } else {
        // Garrison only
        const fleetObj = {
          ships: Object.assign({}, gShips),
          name: `[${typeLabel}] Garrison [${cleanCoords}]`,
          sourceVal: '__custom__',
          coords: cleanCoords
        };
        deployFleetObjectIntoSide(currentExecScanSide, fleetObj);
      }

      // Set bottom coordinates reference
      const bottomCoords = document.getElementById('sim-bcalc-bottom-coords');
      if (bottomCoords) {
        bottomCoords.value = cleanCoords;
      }

      // Update PDS if defender side
      if (currentExecScanSide === 'def' && scanData.pds) {
        Object.entries(scanData.pds).forEach(([name, lvl]) => {
          const lower = name.toLowerCase();
          let pdsKey = '';
          if (lower.includes('shield')) pdsKey = 'shield';
          else if (lower.includes('ion')) pdsKey = 'ion';
          else if (lower.includes('silo') || lower.includes('missile')) pdsKey = 'silo';
          else if (lower.includes('laser')) pdsKey = 'laser';
          if (pdsKey) {
            const chk = document.getElementById(`sim-pds-${pdsKey}-chk`);
            const lvlInput = document.getElementById(`sim-pds-${pdsKey}-lvl`);
            if (chk) chk.checked = true;
            if (lvlInput) lvlInput.value = lvl;
          }
        });
      }

      closeExecuteScanModal();
      showToast(`✅ Scan completed: Deployed [${cleanCoords}] into ${currentExecScanSide === 'def' ? 'Defender' : 'Attacker'}!`);

      // Refresh scans in background so Browse Scans has the new scan record
      try {
        const scanRes = await fetch('/api/combat/scan_targets');
        const scanJson = await scanRes.json();
        if (scanJson.success) {
          simScanTargets = scanJson.targets || [];
          populateScanTargetsDropdown();
          updateCoordsScansDropdown('atk');
          updateCoordsScansDropdown('def');
        }
      } catch (e) {}

    } catch (err) {
      console.error("Execute scan error:", err);
      if (errBox) {
        errBox.style.display = 'block';
        errBox.textContent = `❌ ${err.message || 'Scan execution failed'}`;
      }
    } finally {
      if (submitBtn) {
        submitBtn.disabled = false;
        submitBtn.textContent = '📡 Launch Scan & Add Fleet';
      }
    }
  }

  function deployFleetObjectIntoSide(side, fleetObj) {
    const list = (side === 'atk') ? simAttackerFleets : simDefenderFleets;
    
    // Check if there is an existing empty placeholder fleet to overwrite
    const placeholderIdx = list.findIndex(f => isPlaceholderFleet(f));
    if (placeholderIdx !== -1) {
      const f = list[placeholderIdx];
      f.name = fleetObj.name;
      f.ships = Object.assign({}, fleetObj.ships);
      f.sourceVal = fleetObj.sourceVal || '__custom__';
      f.coords = fleetObj.coords;
      // Prune any other empty placeholders
      if (side === 'atk') {
        simAttackerFleets = simAttackerFleets.filter((fl, i) => i === placeholderIdx || !isPlaceholderFleet(fl));
      } else {
        simDefenderFleets = simDefenderFleets.filter((fl, i) => i === placeholderIdx || !isPlaceholderFleet(fl));
      }
    } else {
      list.push({
        id: side + '_' + (simFleetSeq++),
        side: side,
        name: fleetObj.name,
        coords: fleetObj.coords,
        enabled: true,
        sourceVal: fleetObj.sourceVal || '__custom__',
        ships: Object.assign({}, fleetObj.ships)
      });
    }

    renderAllFleetCards(side);
    recalcCoalitionSummary(side);
    renderBcalcMatrix();
  }

  function populateQuickScanAddDropdowns() {
    ['atk', 'def'].forEach(side => {
      const selIds = [`sim-${side}-add-scan-select`, `sim-bcalc-${side}-add-scan-select`];
      selIds.forEach(id => {
        const sel = document.getElementById(id);
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

        const filteredList = (typeof getFilteredScans === 'function') ? getFilteredScans() : simScanTargets;
        if (filteredList.length === 0) {
          const opt = document.createElement('option');
          opt.value = '';
          opt.disabled = true;
          opt.textContent = 'No scans match current filter';
          sel.appendChild(opt);
          return;
        }

        filteredList.forEach(t => {
          if (t.status === 'blocked' || t.isBlocked) return;
          const tIdx = simScanTargets.indexOf(t);
          if (tIdx === -1) return;
          const typeLabel = formatScanType(t.scanType);
          const coords = t.coords || `Target ${tIdx + 1}`;
          const gShips = t.garrisonShips || {};
          const gTotal = Object.values(gShips).reduce((a, b) => a + (parseInt(b, 10) || 0), 0);
          const namedFleets = t.namedFleets || [];

          // Consolidated option (if multi-fleet)
          if (namedFleets.length > 0) {
            const allTotal = (side === 'atk')
              ? namedFleets.reduce((acc, nf) => acc + Object.values(nf.ships || {}).reduce((a, b) => a + (parseInt(b, 10) || 0), 0), 0)
              : gTotal + namedFleets.reduce((acc, nf) => acc + Object.values(nf.ships || {}).reduce((a, b) => a + (parseInt(b, 10) || 0), 0), 0);
            if (allTotal > 0 && (side === 'atk' ? namedFleets.length > 1 : (namedFleets.length > 0 && gTotal > 0))) {
              const cOpt = document.createElement('option');
              cOpt.value = `scan_${tIdx}_consolidated`;
              cOpt.textContent = `⚡ [${typeLabel}] [${coords}] All Consolidated (${allTotal.toLocaleString()} ships)`;
              sel.appendChild(cOpt);
            }
          }

          // Garrison option (Defender only: PDS & Garrison are stationary planetary defenses)
          if (side !== 'atk' && (gTotal > 0 || namedFleets.length === 0)) {
            const gOpt = document.createElement('option');
            gOpt.value = `scan_${tIdx}_garrison`;
            gOpt.textContent = `[${typeLabel}] [${coords}] Garrison (${gTotal.toLocaleString()} ships)`;
            sel.appendChild(gOpt);
          }

          // Named fleets options
          namedFleets.forEach((nf, nfIdx) => {
            const nfTotal = Object.values(nf.ships || {}).reduce((a, b) => a + (parseInt(b, 10) || 0), 0);
            const nfOpt = document.createElement('option');
            nfOpt.value = `scan_${tIdx}_nf_${nfIdx}`;
            nfOpt.textContent = `[${typeLabel}] [${coords}] Fleet "${nf.name || 'Unnamed'}" (${nfTotal.toLocaleString()} ships)`;
            sel.appendChild(nfOpt);
          });
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

  function populateQuickEmpireAddDropdowns() {
    ['atk', 'def'].forEach(side => {
      const selIds = [`sim-${side}-add-empire-select`, `sim-bcalc-${side}-add-empire-select`];
      selIds.forEach(id => {
        const sel = document.getElementById(id);
        if (!sel) return;
        sel.innerHTML = '<option value="">🏰 Add Own Fleet...</option>';

        // 1. Home Base Garrison / Docked at Base (DEFENDER ONLY: PDS & Garrison are stationary defenses)
        if (side === 'def') {
          const myHangar = (simAttackerData && simAttackerData.hangarShips && Object.keys(simAttackerData.hangarShips).length > 0)
            ? simAttackerData.hangarShips
            : (homeDefenseData ? homeDefenseData.hangarShips : {});
          const hangarTotal = Object.values(myHangar || {}).reduce((a, b) => a + (parseInt(b, 10) || 0), 0);
          const hOpt = document.createElement('option');
          hOpt.value = '__hangar__';
          hOpt.textContent = `🏠 Base Garrison / Docked (${hangarTotal.toLocaleString()} ships)`;
          sel.appendChild(hOpt);
        }

        // 2. Named Fleets (including docked at base and in transit)
        const myFleets = (simAttackerData && simAttackerData.namedFleets) ? simAttackerData.namedFleets : [];
        myFleets.forEach((f, idx) => {
          const fTotal = Object.values(f.ships || {}).reduce((a, b) => a + (parseInt(b, 10) || 0), 0);
          const fOpt = document.createElement('option');
          fOpt.value = `fleet_${idx}`;
          const isDocked = (f.status === 'DOCKED');
          const statusLabel = isDocked ? '⚓ Docked' : (f.status || 'Active');
          fOpt.textContent = `🚀 Fleet "${f.name || 'Unnamed'}" (${fTotal.toLocaleString()} ships) [${statusLabel}]`;
          sel.appendChild(fOpt);
        });
      });
    });
  }

  function onQuickAddEmpireSelect(side, selectEl) {
    const val = selectEl.value;
    if (!val) return;
    if (side === 'atk' && val === '__hangar__') {
      showToast('Base Garrison is stationary and cannot be added to Attacker forces.', 'warning');
      selectEl.value = '';
      return;
    }
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
      recalcCoalitionSummary('def');
    }
    renderBcalcMatrix();
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
        card.style.borderColor = (side === 'atk') ? 'rgba(239, 68, 68, 0.4)' : 'rgba(56, 189, 248, 0.4)';
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
    renderBcalcMatrix();
  }

  function onFleetNameChange(side, fleetId, newName) {
    const list = (side === 'atk') ? simAttackerFleets : simDefenderFleets;
    const fleet = list.find(f => f.id === fleetId);
    if (fleet) {
      fleet.name = newName.trim() || (side === 'atk' ? 'Attacker Fleet' : 'Defender Fleet');
      renderBcalcMatrix();
    }
  }

  function promptRenameFleet(side, fleetId) {
    const list = (side === 'atk') ? simAttackerFleets : simDefenderFleets;
    const fleet = list.find(f => f.id === fleetId);
    if (!fleet) return;
    const newName = prompt(`Enter new name for ${side === 'atk' ? 'Attacker' : 'Defender'} fleet:`, fleet.name);
    if (newName !== null && newName.trim() !== '') {
      fleet.name = newName.trim();
      renderAllFleetCards(side);
      renderBcalcMatrix();
      showToast(`Renamed fleet to "${fleet.name}"`);
    }
  }

  function onFleetPresetChange(side, fleetId, presetVal) {
    const list = (side === 'atk') ? simAttackerFleets : simDefenderFleets;
    const fleet = list.find(f => f.id === fleetId);
    if (!fleet) return;

    if (presetVal === '__custom__') {
      fleet.sourceVal = '__custom__';
      renderBcalcMatrix();
      return;
    }

    const resolved = resolveFleetPreset(presetVal, side);
    fleet.sourceVal = resolved.sourceVal;
    fleet.name = resolved.name;
    fleet.ships = resolved.ships;

    const nameEl = document.getElementById(`fleet-name-${fleetId}`);
    if (nameEl) nameEl.value = fleet.name;

    const container = document.getElementById(`fleet-ships-${fleetId}`);
    if (container) {
      renderFleetShipRows(container, fleet, side);
    }
    updateFleetSubtotal(fleetId, side);
    if (side === 'atk') recalcCoalitionSummary('atk');
    renderBcalcMatrix();
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
    syncWithBcalcMatrix();
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
      syncWithBcalcMatrix();
      return;
    }

    list.forEach((fleet, idx) => {
      container.appendChild(buildFleetCardElement(fleet, side, idx));
    });
    syncWithBcalcMatrix();
  }

  // =========================================================================
  // 📊 COMBAT MATRIX MODE ENGINE
  // =========================================================================
  let currentBcalcLayout = localStorage.getItem('peg_sim_layout');
  if (!currentBcalcLayout || currentBcalcLayout === 'planetarion') {
    currentBcalcLayout = 'bcalc';
    try { localStorage.setItem('peg_sim_layout', 'bcalc'); } catch (e) {}
  }
  let bcalcHullFilter = 'ALL';      // 'ALL' | 'FIGHTER' | 'CORVETTE' | 'FRIGATE' | 'DESTROYER' | 'CRUISER' | 'BATTLESHIP' | 'PDS'
  let lastSimResult = null;
  let bcalcZoomMode = 'auto';       // 'auto' | '100' | '85' | '70'
  let bcalcWideMode = true;

  function setSimulatorLayout(layout) {
    currentBcalcLayout = layout;
    try { localStorage.setItem('peg_sim_layout', layout); } catch (e) {}
    const cardsContainer = document.getElementById('sim-cards-view-container');
    const cardsExplorer = document.getElementById('sim-cards-explorer-panel');
    const bcalcContainer = document.getElementById('sim-bcalc-view-container');
    const cardsBtn = document.getElementById('sim-layout-cards-btn');
    const bcalcBtn = document.getElementById('sim-layout-bcalc-btn');
    const mainContainer = document.querySelector('.container');

    if (layout === 'bcalc') {
      if (cardsContainer) cardsContainer.style.display = 'none';
      if (cardsExplorer) cardsExplorer.style.display = 'none';
      if (bcalcContainer) bcalcContainer.style.display = 'block';
      if (cardsBtn) cardsBtn.classList.remove('active');
      if (bcalcBtn) bcalcBtn.classList.add('active');
      // Auto-enable wide-mode for matrix view to maximize horizontal space
      if (mainContainer && bcalcWideMode) mainContainer.classList.add('wide-mode');
      renderBcalcMatrix();
    } else {
      if (cardsContainer) cardsContainer.style.display = 'grid';
      if (cardsExplorer) cardsExplorer.style.display = 'block';
      if (bcalcContainer) bcalcContainer.style.display = 'none';
      if (cardsBtn) cardsBtn.classList.add('active');
      if (bcalcBtn) bcalcBtn.classList.remove('active');
      renderAllFleetCards('atk');
      renderAllFleetCards('def');
    }
  }

  function toggleBcalcWideMode() {
    bcalcWideMode = !bcalcWideMode;
    const mainContainer = document.querySelector('.container');
    const btn = document.getElementById('bcalc-toggle-width-btn');
    if (mainContainer) {
      if (bcalcWideMode) {
        mainContainer.classList.add('wide-mode');
        if (btn) btn.classList.add('active');
        showToast('Expanded layout to Full Screen Width');
      } else {
        mainContainer.classList.remove('wide-mode');
        if (btn) btn.classList.remove('active');
        showToast('Restored standard width layout');
      }
    }
  }

  function setBcalcZoom(mode) {
    bcalcZoomMode = mode;
    ['auto', '100', '85', '70'].forEach(m => {
      const b = document.getElementById(`bcalc-zoom-${m}-btn`);
      if (b) {
        if (m === mode) b.classList.add('active');
        else b.classList.remove('active');
      }
    });
    renderBcalcMatrix();
  }

  function resetCombatSimulator() {
    // 1. Reset Attacker Fleets to 1 empty roster
    simAttackerFleets = [
      {
        id: 'atk_' + (simFleetSeq++),
        side: 'atk',
        name: 'Primary Fleet 1 (Coalition)',
        sourceVal: '__custom__',
        enabled: true,
        ships: {}
      }
    ];

    // 2. Reset Defender Fleets to 1 empty garrison
    simDefenderFleets = [
      {
        id: 'def_' + (simFleetSeq++),
        side: 'def',
        name: 'Defender Garrison (Base)',
        sourceVal: '__custom__',
        enabled: true,
        ships: {}
      }
    ];

    // 3. Reset Coordinates Search & Dropdown Filters (Attacker & Defender)
    simEnteredCoordsAtk = '';
    const atkCoordsInput = document.getElementById('sim-atk-coords-input');
    if (atkCoordsInput) atkCoordsInput.value = '';
    const atkQuick = document.getElementById('sim-atk-planet-quickpick');
    if (atkQuick) atkQuick.value = '';
    const atkActiveLabel = document.getElementById('sim-atk-coords-active-label');
    if (atkActiveLabel) atkActiveLabel.textContent = 'Attacker Coords';
    const atkMatchBadge = document.getElementById('sim-atk-coords-match-badge');
    if (atkMatchBadge) {
      atkMatchBadge.textContent = '0 scan(s)';
      atkMatchBadge.style.color = 'var(--cyan)';
    }
    const atkCoordsScansSel = document.getElementById('sim-atk-coords-scans-select');
    if (atkCoordsScansSel) {
      atkCoordsScansSel.innerHTML = '<option value="">Enter attacker coords above (e.g. 12:1:1) to view scans...</option>';
    }
    const atkMainTargetSel = document.getElementById('sim-atk-target-select');
    if (atkMainTargetSel) atkMainTargetSel.selectedIndex = 0;
    const bcalcAtkCoordsInput = document.getElementById('sim-bcalc-atk-coords-input');
    if (bcalcAtkCoordsInput) bcalcAtkCoordsInput.value = '';
    const bcalcAtkTargetSel = document.getElementById('sim-bcalc-atk-target-select');
    if (bcalcAtkTargetSel) bcalcAtkTargetSel.selectedIndex = 0;
    const bcalcAtkEmpireSel = document.getElementById('sim-bcalc-atk-add-empire-select');
    if (bcalcAtkEmpireSel) bcalcAtkEmpireSel.selectedIndex = 0;
    const atkScanDetails = document.getElementById('sim-atk-scan-details');
    if (atkScanDetails) atkScanDetails.style.display = 'none';

    simEnteredCoordsDef = '';
    const coordsInput = document.getElementById('sim-coords-input');
    if (coordsInput) coordsInput.value = '';
    const quick = document.getElementById('sim-planet-quickpick');
    if (quick) quick.value = '';
    const activeLabel = document.getElementById('sim-coords-active-label');
    if (activeLabel) activeLabel.textContent = 'Defender Coords';
    const matchBadge = document.getElementById('sim-coords-match-badge');
    if (matchBadge) {
      matchBadge.textContent = '0 scan(s)';
      matchBadge.style.color = 'var(--cyan)';
    }
    const coordsScansSel = document.getElementById('sim-coords-scans-select');
    if (coordsScansSel) {
      coordsScansSel.innerHTML = '<option value="">Enter defender coords above (e.g. 12:1:1) to view scans...</option>';
    }
    const mainTargetSel = document.getElementById('sim-def-target');
    if (mainTargetSel) mainTargetSel.selectedIndex = 0;
    const bcalcDefCoordsInput = document.getElementById('sim-bcalc-def-coords-input');
    if (bcalcDefCoordsInput) bcalcDefCoordsInput.value = '';
    const bcalcDefTargetSel = document.getElementById('sim-bcalc-def-target-select');
    if (bcalcDefTargetSel) bcalcDefTargetSel.selectedIndex = 0;
    const bcalcDefEmpireSel = document.getElementById('sim-bcalc-def-add-empire-select');
    if (bcalcDefEmpireSel) bcalcDefEmpireSel.selectedIndex = 0;
    const bcalcBottomCoords = document.getElementById('sim-bcalc-bottom-coords');
    if (bcalcBottomCoords) bcalcBottomCoords.value = '';
    const scanDetails = document.getElementById('sim-def-scan-details');
    if (scanDetails) scanDetails.style.display = 'none';

    currentTargetScan = null;

    // 4. Reset Tech Levels (Attacker Hulls: 5, Ship Tech: 5)
    const atkHulls = document.getElementById('sim-atk-hulls');
    if (atkHulls) atkHulls.value = '5';
    const atkShipTech = document.getElementById('sim-atk-shiptech');
    if (atkShipTech) atkShipTech.value = '5';

    // 5. Reset PDS Levels & Checks
    ['shield', 'ion', 'silo', 'laser'].forEach(id => {
      const chk = document.getElementById(`sim-pds-${id}-chk`);
      if (chk) chk.checked = true;
      const lvl = document.getElementById(`sim-pds-${id}-lvl`);
      if (lvl) lvl.value = (id === 'shield' ? 3 : 2);
    });

    // 6. Reset Mode to Default (Defense / User = Defender)
    currentSimMode = 'defense';
    const assaultBtn = document.getElementById('sim-mode-assault-btn');
    if (assaultBtn) assaultBtn.classList.remove('active');
    const defenseBtn = document.getElementById('sim-mode-defense-btn');
    if (defenseBtn) defenseBtn.classList.add('active');
    const atkTitle = document.getElementById('sim-atk-title');
    if (atkTitle) { atkTitle.textContent = '🚀 Attacking Forces (Coalition Fleets)'; atkTitle.style.color = '#ef4444'; }
    const defTitle = document.getElementById('sim-def-title');
    if (defTitle) { defTitle.textContent = '🛡️ Defender Forces (Base Garrison, Fleets & PDS)'; defTitle.style.color = '#38bdf8'; }

    // 7. Reset Results & Cache
    lastSimResult = null;
    const resDiv = document.getElementById('sim-results-container');
    if (resDiv) {
      resDiv.innerHTML = '';
      resDiv.style.display = 'none';
    }

    // 8. Refresh Renders & Ensure Matrix Mode is Default
    renderAllFleetCards('atk');
    renderAllFleetCards('def');
    recalcCoalitionSummary('atk');
    recalcCoalitionSummary('def');
    setSimulatorLayout('bcalc');
    renderBcalcMatrix();

    const statusBadge = document.getElementById('combat-status-badge');
    if (statusBadge) {
      statusBadge.textContent = 'Calculator reset to clean state.';
      statusBadge.style.color = 'var(--cyan)';
    }
    showToast('Battle Calculator reset to clean state.');
  }

  // =========================================================================
  // MULTI-CALCULATION SESSIONS & POP-OUT WINDOW ARCHITECTURE
  // =========================================================================
  let calcSessions = [
    { id: 'session_init', name: 'Calc #1', state: null }
  ];
  let activeSessionId = 'session_init';

  function captureCurrentCalcState() {
    const pdsLevels = {};
    ['shield', 'ion', 'silo', 'laser'].forEach(id => {
      const chk = document.getElementById(`sim-pds-${id}-chk`);
      const lvl = document.getElementById(`sim-pds-${id}-lvl`);
      pdsLevels[id] = {
        enabled: chk ? chk.checked : true,
        level: lvl ? parseInt(lvl.value, 10) || 0 : 0
      };
    });

    const atkHulls = document.getElementById('sim-atk-hulls');
    const atkShipTech = document.getElementById('sim-atk-shiptech');
    const bcalcBottomCoords = document.getElementById('sim-bcalc-bottom-coords');

    const bottomVal = bcalcBottomCoords ? bcalcBottomCoords.value.trim() : '';
    const defVal = (simEnteredCoordsDef || '').trim();
    const effectiveCoords = bottomVal || defVal;
    const title = effectiveCoords ? `Target ${effectiveCoords}` : 'Battle Calc';

    return {
      version: 1,
      title: title,
      timestamp: Date.now(),
      simMode: currentSimMode,
      attackerFleets: JSON.parse(JSON.stringify(simAttackerFleets)),
      defenderFleets: JSON.parse(JSON.stringify(simDefenderFleets)),
      enteredCoordsDef: simEnteredCoordsDef || '',
      enteredCoordsAtk: simEnteredCoordsAtk || '',
      bottomCoords: bottomVal,
      atkHulls: atkHulls ? atkHulls.value : '5',
      atkShipTech: atkShipTech ? atkShipTech.value : '5',
      pdsLevels: pdsLevels,
      layout: currentBcalcLayout || 'bcalc',
      matrixFilter: typeof bcalcHullFilter !== 'undefined' ? bcalcHullFilter : 'ALL'
    };
  }

  function applyCalcState(state) {
    if (!state) return;

    // Check for expired / stale intel (> 7 days)
    if (state.timestamp) {
      const ageMs = Date.now() - state.timestamp;
      const SEVEN_DAYS_MS = 7 * 24 * 60 * 60 * 1000;
      if (ageMs > SEVEN_DAYS_MS) {
        const daysAgo = Math.floor(ageMs / (24 * 60 * 60 * 1000));
        showExpiredIntelBanner(daysAgo, state.timestamp);
      } else {
        hideExpiredIntelBanner();
      }
    }

    if (state.simMode) {
      setSimulationMode(state.simMode, true);
    }

    if (Array.isArray(state.atk)) {
      simAttackerFleets = state.atk.map((f, i) => ({
        id: f.id || ('atk_' + (i + 1)),
        side: 'atk',
        name: f.name || ('Fleet ' + (i + 1)),
        coords: state.coords || '',
        enabled: f.enabled !== false && !f.disabled,
        ships: Object.assign({}, f.ships || {})
      }));
    } else if (Array.isArray(state.attackerFleets)) {
      simAttackerFleets = JSON.parse(JSON.stringify(state.attackerFleets));
    }

    if (Array.isArray(state.def)) {
      simDefenderFleets = state.def.map((f, i) => ({
        id: f.id || ('def_' + (i + 1)),
        side: 'def',
        name: f.name || (i === 0 ? 'Defender Garrison' : ('Fleet ' + (i + 1))),
        coords: state.coords || '',
        enabled: f.enabled !== false && !f.disabled,
        ships: Object.assign({}, f.ships || {})
      }));
    } else if (Array.isArray(state.defenderFleets)) {
      simDefenderFleets = JSON.parse(JSON.stringify(state.defenderFleets));
    }

    const coordsVal = state.coords || state.bottomCoords || state.enteredCoordsDef || '';
    if (coordsVal) {
      onCoordsInputChanged('def', coordsVal);
      const bcalcBottomCoords = document.getElementById('sim-bcalc-bottom-coords');
      if (bcalcBottomCoords) bcalcBottomCoords.value = coordsVal;
    }
    if (state.enteredCoordsAtk) {
      onCoordsInputChanged('atk', state.enteredCoordsAtk);
    }

    if (state.tech) {
      const atkHulls = document.getElementById('sim-atk-hulls');
      if (atkHulls && state.tech.atkHulls !== undefined) atkHulls.value = state.tech.atkHulls;
      const atkShipTech = document.getElementById('sim-atk-shiptech');
      if (atkShipTech && state.tech.atkShipTech !== undefined) atkShipTech.value = state.tech.atkShipTech;
    } else {
      if (state.atkHulls) {
        const atkHulls = document.getElementById('sim-atk-hulls');
        if (atkHulls) atkHulls.value = state.atkHulls;
      }
      if (state.atkShipTech) {
        const atkShipTech = document.getElementById('sim-atk-shiptech');
        if (atkShipTech) atkShipTech.value = state.atkShipTech;
      }
    }

    const pdsMap = state.pds || state.pdsLevels || {};
    function getPdsInfo(raw, shortKey, longKey, nameKey) {
      for (const k of [shortKey, longKey, nameKey]) {
        if (raw[k] !== undefined && raw[k] !== null) {
          if (typeof raw[k] === 'number') return { enabled: true, level: raw[k] };
          if (typeof raw[k] === 'object') {
            return {
              enabled: raw[k].enabled !== undefined ? raw[k].enabled : true,
              level: raw[k].level !== undefined ? (parseInt(raw[k].level, 10) || 0) : (typeof raw[k] === 'number' ? raw[k] : 0)
            };
          }
          const parsed = parseInt(raw[k], 10);
          if (!isNaN(parsed)) return { enabled: true, level: parsed };
        }
      }
      return { enabled: true, level: 0 };
    }

    const pdsDefs = [
      { id: 'shield', long: 'main-shield-generator', name: 'Shield Generator' },
      { id: 'ion', long: 'main-ion-cannon', name: 'Ion Cannon' },
      { id: 'silo', long: 'main-missile-silo', name: 'Missile Silo' },
      { id: 'laser', long: 'main-laser-battery', name: 'Laser Battery' }
    ];

    pdsDefs.forEach(pd => {
      const info = getPdsInfo(pdsMap, pd.id, pd.long, pd.name);
      const chk = document.getElementById(`sim-pds-${pd.id}-chk`);
      if (chk) chk.checked = info.enabled;
      const lvl = document.getElementById(`sim-pds-${pd.id}-lvl`);
      if (lvl) lvl.value = info.level;
    });

    if (state.rounds) {
      const rSel = document.getElementById('sim-max-rounds');
      if (rSel) rSel.value = String(state.rounds);
    }

    if (state.matrixFilter && typeof setBcalcHullFilter === 'function') {
      setBcalcHullFilter(state.matrixFilter);
    }

    if (state.layout && typeof setSimulatorLayout === 'function') {
      setSimulatorLayout(state.layout);
    } else {
      renderBcalcMatrix();
    }

    renderAllFleetCards('atk');
    renderAllFleetCards('def');
    recalcCoalitionSummary('atk');
    recalcCoalitionSummary('def');
  }

  function showExpiredIntelBanner(daysAgo, ts) {
    let banner = document.getElementById('calc-expired-banner');
    if (!banner) {
      banner = document.createElement('div');
      banner.id = 'calc-expired-banner';
      banner.style.cssText = `
        background: rgba(239, 68, 68, 0.15); border: 1px solid #ef4444; border-radius: 8px;
        padding: 0.85rem 1.25rem; margin-bottom: 1.25rem; display: flex; justify-content: space-between;
        align-items: center; flex-wrap: wrap; gap: 0.75rem; box-shadow: 0 4px 20px rgba(239, 68, 68, 0.2);
      `;
      const targetPanel = document.getElementById('calc-multi-tabs-bar');
      if (targetPanel && targetPanel.parentNode) {
        targetPanel.parentNode.insertBefore(banner, targetPanel);
      }
    }
    const dateStr = ts ? new Date(ts).toLocaleDateString() : '';
    banner.innerHTML = `
      <div>
        <div style="font-weight: 700; color: #f87171; font-size: 0.92rem; display: flex; align-items: center; gap: 0.4rem;">
          ⏳ Expired Battle Intel (${daysAgo} days old)
        </div>
        <div style="font-size: 0.78rem; color: #fca5a5; margin-top: 0.2rem;">
          This battle calculation was generated ${daysAgo} days ago (${dateStr}). In Pegasus Galaxy, defenses, fleets, and tech change every tick.
        </div>
      </div>
      <div style="display: flex; gap: 0.5rem;">
        <button class="btn-refresh" onclick="startFreshCalculation()" style="padding: 0.35rem 0.85rem; font-size: 0.8rem; color: #38bdf8; border-color: rgba(56,189,248,0.4); background: rgba(56,189,248,0.08);">
          ✨ Start Fresh
        </button>
        <button class="btn-refresh" onclick="hideExpiredIntelBanner()" style="padding: 0.35rem 0.85rem; font-size: 0.8rem; color: #cbd5e1; border-color: rgba(255,255,255,0.2);">
          Dismiss &amp; Inspect
        </button>
      </div>
    `;
    banner.style.display = 'flex';
  }

  function hideExpiredIntelBanner() {
    const banner = document.getElementById('calc-expired-banner');
    if (banner) banner.style.display = 'none';
  }

  function pruneOldLocalStorage() {
    try {
      const SEVEN_DAYS_MS = 7 * 24 * 60 * 60 * 1000;
      const now = Date.now();
      const toRemove = [];
      for (let i = 0; i < localStorage.length; i++) {
        const key = localStorage.key(i);
        if (key && (key.startsWith('peg_calc_') || key.startsWith('peg_transfer_'))) {
          try {
            const item = JSON.parse(localStorage.getItem(key));
            if (item && item.timestamp && (now - item.timestamp > SEVEN_DAYS_MS)) {
              toRemove.push(key);
            }
          } catch(e) {
            const parts = key.split('_');
            const ts = parseInt(parts[2] || parts[1], 10);
            if (ts && (now - ts > SEVEN_DAYS_MS)) {
              toRemove.push(key);
            }
          }
        }
      }
      toRemove.forEach(k => localStorage.removeItem(k));
    } catch(e) {}
  }

  function initCalcSessions() {
    pruneOldLocalStorage();
    if (!calcSessions || calcSessions.length === 0) {
      calcSessions = [{ id: 'session_init', name: 'Calc #1', state: null }];
      activeSessionId = 'session_init';
    }
    renderCalcTabs();
  }

  function renderCalcTabs() {
    const container = document.getElementById('calc-tab-list');
    if (!container) return;
    container.innerHTML = '';
    calcSessions.forEach((sess, idx) => {
      const isActive = sess.id === activeSessionId;
      const tabEl = document.createElement('div');
      tabEl.className = 'calc-session-pill ' + (isActive ? 'active' : '');
      tabEl.style.cssText = `
        display: inline-flex; align-items: center; gap: 0.45rem; padding: 0.28rem 0.68rem;
        border-radius: 6px; font-size: 0.8rem; font-family: var(--font-mono); cursor: pointer;
        border: 1px solid ${isActive ? 'var(--cyan)' : 'rgba(255,255,255,0.14)'};
        background: ${isActive ? 'rgba(0,229,255,0.18)' : 'rgba(15,23,42,0.6)'};
        color: ${isActive ? '#fff' : 'var(--text-dim)'};
        font-weight: ${isActive ? '600' : '400'};
        box-shadow: ${isActive ? '0 0 10px rgba(0,229,255,0.2)' : 'none'};
      `;
      
      const titleSpan = document.createElement('span');
      titleSpan.textContent = sess.name || ('Calc #' + (idx + 1));
      titleSpan.title = 'Click to switch to this calculation';
      titleSpan.onclick = () => switchCalcSession(sess.id);
      tabEl.appendChild(titleSpan);

      const popBtn = document.createElement('span');
      popBtn.innerHTML = '↗️';
      popBtn.title = 'Pop this calculation into a new independent window';
      popBtn.style.cssText = 'font-size: 0.72rem; opacity: 0.7; padding: 0 2px; cursor: pointer;';
      popBtn.onmouseover = () => popBtn.style.opacity = '1';
      popBtn.onmouseout = () => popBtn.style.opacity = '0.7';
      popBtn.onclick = (e) => {
        e.stopPropagation();
        popOutSession(sess.id);
      };
      tabEl.appendChild(popBtn);

      if (calcSessions.length > 1) {
        const closeBtn = document.createElement('span');
        closeBtn.innerHTML = '×';
        closeBtn.title = 'Close this calculation';
        closeBtn.style.cssText = 'font-size: 0.95rem; font-weight: bold; opacity: 0.6; padding: 0 2px; cursor: pointer; line-height: 1;';
        closeBtn.onmouseover = () => closeBtn.style.opacity = '1';
        closeBtn.onmouseout = () => closeBtn.style.opacity = '0.6';
        closeBtn.onclick = (e) => {
          e.stopPropagation();
          closeCalcSession(sess.id);
        };
        tabEl.appendChild(closeBtn);
      }

      container.appendChild(tabEl);
    });
  }

  function updateActiveCalcTabTitleFromCoords(coords) {
    if (!coords) return;
    const cur = calcSessions.find(s => s.id === activeSessionId);
    if (cur && (cur.name.startsWith('Calc #') || cur.name.startsWith('Target ') || cur.name === 'Scratch')) {
      cur.name = `Target ${coords}`;
      renderCalcTabs();
    }
  }

  function switchCalcSession(targetId) {
    if (targetId === activeSessionId) return;
    const cur = calcSessions.find(s => s.id === activeSessionId);
    if (cur) {
      cur.state = captureCurrentCalcState();
      const bottomVal = document.getElementById('sim-bcalc-bottom-coords')?.value?.trim();
      if (bottomVal && (cur.name.startsWith('Calc #') || cur.name.startsWith('Target '))) {
        cur.name = `Target ${bottomVal}`;
      }
    }

    activeSessionId = targetId;
    const target = calcSessions.find(s => s.id === targetId);
    if (target && target.state) {
      applyCalcState(target.state);
    } else {
      resetCombatSimulator();
    }
    renderCalcTabs();
  }

  function addNewCalcTab() {
    const cur = calcSessions.find(s => s.id === activeSessionId);
    if (cur) cur.state = captureCurrentCalcState();

    const newId = 'session_' + Date.now();
    const newName = 'Calc #' + (calcSessions.length + 1);
    calcSessions.push({ id: newId, name: newName, state: null });
    activeSessionId = newId;

    resetCombatSimulator();
    renderCalcTabs();
    showToast(`Created new calculation tab "${newName}"`);
  }

  function duplicateCurrentCalcTab() {
    const state = captureCurrentCalcState();
    const cur = calcSessions.find(s => s.id === activeSessionId);
    const newId = 'session_' + Date.now();
    const baseName = cur ? cur.name : 'Calc';
    const newName = baseName.includes('(Copy)') ? baseName : (baseName + ' (Copy)');
    calcSessions.push({ id: newId, name: newName, state: JSON.parse(JSON.stringify(state)) });
    activeSessionId = newId;
    applyCalcState(state);
    renderCalcTabs();
    showToast(`Duplicated into "${newName}"`);
  }

  function renameCurrentCalcTab() {
    const cur = calcSessions.find(s => s.id === activeSessionId);
    if (!cur) return;
    const newName = prompt('Enter a name or target label for this calculation tab:', cur.name);
    if (newName && newName.trim()) {
      cur.name = newName.trim();
      renderCalcTabs();
    }
  }

  function closeCalcSession(sessionId) {
    if (calcSessions.length <= 1) {
      if (confirm("Reset this calculation to start from scratch?")) {
        resetCombatSimulator();
        calcSessions[0].name = 'Calc #1';
        calcSessions[0].state = null;
        renderCalcTabs();
      }
      return;
    }
    const target = calcSessions.find(s => s.id === sessionId);
    if (target && target.state) {
      let shipCount = 0;
      (target.state.attackerFleets || []).forEach(f => Object.values(f.ships || {}).forEach(c => shipCount += c));
      (target.state.defenderFleets || []).forEach(f => Object.values(f.ships || {}).forEach(c => shipCount += c));
      if (shipCount > 0) {
        if (!confirm(`Close "${target.name}"? This calculation has ${shipCount} ship(s) and will be removed.`)) return;
      }
    }
    const idx = calcSessions.findIndex(s => s.id === sessionId);
    calcSessions = calcSessions.filter(s => s.id !== sessionId);
    if (activeSessionId === sessionId) {
      const nextIdx = Math.max(0, idx - 1);
      activeSessionId = calcSessions[nextIdx].id;
      if (calcSessions[nextIdx].state) {
        applyCalcState(calcSessions[nextIdx].state);
      } else {
        resetCombatSimulator();
      }
    }
    renderCalcTabs();
  }

  function popOutSession(sessionId) {
    let state;
    if (sessionId === activeSessionId) {
      state = captureCurrentCalcState();
    } else {
      const target = calcSessions.find(s => s.id === sessionId);
      state = target ? target.state : null;
    }
    if (!state) state = captureCurrentCalcState();

    const transferId = 'peg_calc_' + Date.now() + '_' + Math.floor(Math.random() * 10000);
    try {
      localStorage.setItem(transferId, JSON.stringify(state));
      localStorage.setItem('peg_calc_transfer_latest', JSON.stringify(state));
    } catch(e) {
      console.warn("localStorage error:", e);
    }
    window.open(`/calc#import=${transferId}`, '_blank');
  }

  function popOutCalculatorToWindow() {
    const state = captureCurrentCalcState();
    const transferId = 'peg_calc_' + Date.now() + '_' + Math.floor(Math.random() * 10000);
    try {
      localStorage.setItem(transferId, JSON.stringify(state));
      localStorage.setItem('peg_calc_transfer_latest', JSON.stringify(state));
    } catch(e) {
      console.warn("localStorage quota/error:", e);
    }

    const newWin = window.open(`/calc#import=${transferId}`, '_blank');
    if (!newWin) {
      alert("Popup blocked by your browser. Please allow popups for this site so the calculator can open in a new window.");
      return;
    }

    showToast("Calculation popped out to new window!");

    setTimeout(() => {
      if (confirm("Calculation sent to new window!\n\nWould you like to reset THIS window back to clean scratch state?")) {
        resetCombatSimulator();
        const cur = calcSessions.find(s => s.id === activeSessionId);
        if (cur) {
          cur.name = 'Scratch';
          cur.state = null;
          renderCalcTabs();
        }
      }
    }, 350);
  }

  function startFreshCalculation() {
    if (confirm("Start a clean calculation from scratch? This will clear all fleets, scans, and coordinates in this window.")) {
      resetCombatSimulator();
      const cur = calcSessions.find(s => s.id === activeSessionId);
      if (cur) {
        cur.name = 'Scratch';
        cur.state = null;
        renderCalcTabs();
      }
      showToast("Ready for new battle calculation.");
    }
  }

  // Compression & Public Link Sharing (URL Safe Deflate-Raw)
  async function compressToUrlSafe(obj) {
    try {
      const jsonStr = JSON.stringify(obj);
      if (typeof CompressionStream !== 'undefined') {
        const stream = new Blob([jsonStr]).stream().pipeThrough(new CompressionStream('deflate-raw'));
        const buf = await new Response(stream).arrayBuffer();
        const bytes = new Uint8Array(buf);
        let bin = '';
        for (let i = 0; i < bytes.length; i++) bin += String.fromCharCode(bytes[i]);
        return btoa(bin).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
      } else {
        return btoa(unescape(encodeURIComponent(jsonStr))).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
      }
    } catch(e) {
      console.error("Compression failed:", e);
      return null;
    }
  }

  async function decompressFromUrlSafe(b64url) {
    try {
      let b64 = b64url.replace(/-/g, '+').replace(/_/g, '/');
      while (b64.length % 4) b64 += '=';
      if (typeof DecompressionStream !== 'undefined') {
        const bin = atob(b64);
        const bytes = new Uint8Array(bin.length);
        for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
        const stream = new Blob([bytes]).stream().pipeThrough(new DecompressionStream('deflate-raw'));
        const txt = await new Response(stream).text();
        return JSON.parse(txt);
      } else {
        return JSON.parse(decodeURIComponent(escape(atob(b64))));
      }
    } catch(e) {
      console.error("Decompression failed:", e);
      return null;
    }
  }

  function getCalcShareSnapshot() {
    const bcalcBottomCoords = document.getElementById('sim-bcalc-bottom-coords');
    const bottomVal = bcalcBottomCoords ? bcalcBottomCoords.value.trim() : '';
    const defVal = (typeof simEnteredCoordsDef !== 'undefined' && simEnteredCoordsDef ? simEnteredCoordsDef : '').trim();
    const effectiveCoords = bottomVal || defVal;
    const atkHulls = document.getElementById('sim-atk-hulls');
    const atkShipTech = document.getElementById('sim-atk-shiptech');

    const pdsLevels = {};
    const pdsFullMap = {
      shield: 'main-shield-generator',
      ion: 'main-ion-cannon',
      silo: 'main-missile-silo',
      laser: 'main-laser-battery'
    };
    ['shield', 'ion', 'silo', 'laser'].forEach(id => {
      const chk = document.getElementById(`sim-pds-${id}-chk`);
      const lvl = document.getElementById(`sim-pds-${id}-lvl`);
      const val = lvl ? parseInt(lvl.value, 10) || 0 : 0;
      const en = chk ? chk.checked : true;
      pdsLevels[id] = { enabled: en, level: val };
      pdsLevels[pdsFullMap[id]] = val;
    });

    const cleanAtk = (typeof simAttackerFleets !== 'undefined' && Array.isArray(simAttackerFleets) ? simAttackerFleets : []).map((f, i) => ({
      id: f.id || ('atk_' + (i + 1)),
      name: f.name || ('Fleet ' + (i + 1)),
      enabled: f.enabled !== false && !f.disabled,
      ships: Object.assign({}, f.ships || {})
    }));

    const cleanDef = (typeof simDefenderFleets !== 'undefined' && Array.isArray(simDefenderFleets) ? simDefenderFleets : []).map((f, i) => ({
      id: f.id || ('def_' + (i + 1)),
      name: f.name || (i === 0 ? 'Defender Garrison' : ('Fleet ' + (i + 1))),
      enabled: f.enabled !== false && !f.disabled,
      ships: Object.assign({}, f.ships || {})
    }));

    return {
      version: 1,
      title: effectiveCoords ? `Target ${effectiveCoords}` : 'Battle Calc',
      coords: effectiveCoords,
      atk: cleanAtk,
      def: cleanDef,
      pds: pdsLevels,
      tech: {
        atkHulls: parseInt(atkHulls ? atkHulls.value : 5, 10) || 5,
        atkShipTech: parseInt(atkShipTech ? atkShipTech.value : 5, 10) || 5,
        defHulls: 5,
        defShipTech: 5
      },
      rounds: parseInt(document.getElementById('sim-max-rounds')?.value || '1', 10) || 1,
      timestamp: Date.now()
    };
  }

  async function openCalcShareModal() {
    const snap = getCalcShareSnapshot();
    const code = await compressToUrlSafe(snap);
    if (!code) {
      showToast("Error compressing calculation");
      return;
    }
    const publicUrl = `https://phuture707.github.io/PEGMCPCOMMAND/calc.html#c=${code}`;
    const localUrl = `${window.location.origin}/calc#c=${code}`;

    const pubInp = document.getElementById('sim-share-public-url');
    if (pubInp) pubInp.value = publicUrl;

    const locInp = document.getElementById('sim-share-local-url');
    if (locInp) locInp.value = localUrl;

    const modal = document.getElementById('sim-share-modal');
    if (modal) modal.style.display = 'flex';
  }

  function closeCalcShareModal() {
    const modal = document.getElementById('sim-share-modal');
    if (modal) modal.style.display = 'none';
  }

  async function copyPublicShareLink() {
    let pubUrl = document.getElementById('sim-share-public-url')?.value;
    if (!pubUrl) {
      const snap = getCalcShareSnapshot();
      const code = await compressToUrlSafe(snap);
      if (code) pubUrl = `https://phuture707.github.io/PEGMCPCOMMAND/calc.html#c=${code}`;
    }
    if (!pubUrl) {
      showToast("Could not generate share link.");
      return;
    }
    if (navigator.clipboard && navigator.clipboard.writeText) {
      try {
        await navigator.clipboard.writeText(pubUrl);
        showToast("🔗 Public Share Link copied to clipboard!");
        return;
      } catch(e) {}
    }
    prompt("Public Share Link (GitHub Pages - for players without MCP):", pubUrl);
  }

  async function copyLocalShareLink() {
    let locUrl = document.getElementById('sim-share-local-url')?.value;
    if (!locUrl) {
      const snap = getCalcShareSnapshot();
      const code = await compressToUrlSafe(snap);
      if (code) locUrl = `${window.location.origin}/calc#c=${code}`;
    }
    if (!locUrl) return;
    if (navigator.clipboard && navigator.clipboard.writeText) {
      try {
        await navigator.clipboard.writeText(locUrl);
        showToast("💻 Local MCP Link copied to clipboard!");
        return;
      } catch(e) {}
    }
    prompt("Local MCP Link:", locUrl);
  }

  function openPublicShareLinkInTab() {
    const pubUrl = document.getElementById('sim-share-public-url')?.value;
    if (pubUrl) window.open(pubUrl, '_blank');
  }

  function openCalcImportModal() {
    const inp = document.getElementById('sim-import-code-input');
    if (inp) inp.value = '';
    const modal = document.getElementById('sim-import-modal');
    if (modal) modal.style.display = 'flex';
  }

  function closeCalcImportModal() {
    const modal = document.getElementById('sim-import-modal');
    if (modal) modal.style.display = 'none';
  }

  async function applyImportedCode() {
    const inp = document.getElementById('sim-import-code-input');
    let raw = inp ? inp.value.trim() : '';
    if (!raw) return;

    if (raw.includes('c=')) {
      raw = raw.split(/#?c=/)[1].split('&')[0];
    } else if (raw.includes('import=')) {
      const transferId = raw.split(/#?import=/)[1].split('&')[0];
      const stored = localStorage.getItem(transferId) || localStorage.getItem('peg_calc_transfer_latest');
      if (stored) {
        try {
          const state = JSON.parse(stored);
          applyCalcState(state);
          closeCalcImportModal();
          showToast(`Imported ${state.title || 'Calculation'}`);
          return;
        } catch(e) {}
      }
    } else if (raw.includes('coords=')) {
      const coords = decodeURIComponent(raw.split(/#?coords=/)[1].split('&')[0]);
      onCoordsInputChanged('def', coords);
      const bcalcBottom = document.getElementById('sim-bcalc-bottom-coords');
      if (bcalcBottom) bcalcBottom.value = coords;
      closeCalcImportModal();
      showToast(`Loaded target coordinates: ${coords}`);
      return;
    } else if (/^\d+:\d+:\d+$/.test(raw)) {
      onCoordsInputChanged('def', raw);
      const bcalcBottom = document.getElementById('sim-bcalc-bottom-coords');
      if (bcalcBottom) bcalcBottom.value = raw;
      closeCalcImportModal();
      showToast(`Loaded target coordinates: ${raw}`);
      return;
    }

    const state = await decompressFromUrlSafe(raw);
    if (state) {
      let hasExistingShips = false;
      simAttackerFleets.forEach(f => Object.values(f.ships || {}).forEach(c => { if (c > 0) hasExistingShips = true; }));
      simDefenderFleets.forEach(f => Object.values(f.ships || {}).forEach(c => { if (c > 0) hasExistingShips = true; }));

      if (hasExistingShips) {
        const newId = 'session_' + Date.now();
        const newName = state.title || ('Calc #' + (calcSessions.length + 1));
        calcSessions.push({ id: newId, name: newName, state: state });
        activeSessionId = newId;
      } else {
        const cur = calcSessions.find(s => s.id === activeSessionId);
        if (cur) cur.name = state.title || cur.name;
      }

      applyCalcState(state);
      renderCalcTabs();
      closeCalcImportModal();
      showToast(`Successfully imported ${state.title || 'Battle Calculation'}!`);
    } else {
      alert("Could not decode calculation data. Please verify the URL or code string.");
    }
  }

  async function downloadOfflineCalcHtml() {
    try {
      const snap = getCalcShareSnapshot();
      let code = '';
      try {
        code = await compressToUrlSafe(snap);
      } catch(ce) {
        console.warn("Could not compress calculation for offline export:", ce);
      }
      const coords = (snap.coords || 'battle').replace(/[^a-zA-Z0-9_-]/g, '_');
      
      let html = '';
      try {
        const res = await fetch('/calc.html');
        if (res.ok) {
          html = await res.text();
        }
      } catch(fe) {
        console.warn("Fetch /calc.html failed:", fe);
      }

      if (!html) {
        try {
          const resDocs = await fetch('/docs/calc.html');
          if (resDocs.ok) html = await resDocs.text();
        } catch(e) {}
      }

      if (!html) {
        showToast("Notice: Could not reach /calc.html template. Please verify docs/calc.html exists.");
        return;
      }

      if (code) {
        const injectScript = `<script>window.addEventListener('DOMContentLoaded', () => { if (!window.location.hash) window.location.hash = '#c=${code}'; });<\/script>`;
        html = html.replace('</head>', `${injectScript}\n</head>`);
      }

      const blob = new Blob([html], { type: 'text/html' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `pegasus_battlecalc_${coords}.html`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
      showToast("💾 Offline BattleCalc HTML downloaded!");
    } catch(e) {
      console.error("Export HTML failed:", e);
      showToast("Failed to export offline HTML: " + (e.message || e));
    }
  }

  async function openAllianceMessageModal() {
    try {
      const snap = getCalcShareSnapshot();
      let code = '';
      try {
        code = await compressToUrlSafe(snap);
      } catch(ce) {
        console.warn("Could not compress calculation for alliance message:", ce);
      }
      const publicUrl = code ? `https://phuture707.github.io/PEGMCPCOMMAND/calc.html#c=${code}` : 'N/A';

      let atkShips = 0;
      (snap.atk || []).forEach(f => Object.values(f.ships || {}).forEach(c => atkShips += (Number(c) || 0)));
      let defShips = 0;
      (snap.def || []).forEach(f => Object.values(f.ships || {}).forEach(c => defShips += (Number(c) || 0)));

      const targetCoords = snap.coords || 'Target Planet';
      const brief = `[BATTLE SIMULATION BRIEFING]\nTarget: ${targetCoords}\nAttacker Coalition: ${atkShips} ships across ${(snap.atk || []).length} fleet(s)\nDefender Garrison: ${defShips} ships across ${(snap.def || []).length} fleet(s)\nPublic Interactive BattleCalc:\n${publicUrl}`;

      const txt = document.getElementById('sim-ally-msg-body');
      if (txt) txt.value = brief;

      const stat = document.getElementById('sim-ally-msg-status');
      if (stat) { stat.style.display = 'none'; stat.textContent = ''; }

      const modal = document.getElementById('sim-alliance-msg-modal');
      if (modal) {
        modal.style.display = 'flex';
      } else {
        alert("Alliance message modal element not found in DOM.");
      }
    } catch (err) {
      console.error("Open alliance message modal failed:", err);
      alert("Error opening alliance message dialog: " + (err.message || err));
    }
  }

  function closeAllianceMessageModal() {
    const modal = document.getElementById('sim-alliance-msg-modal');
    if (modal) modal.style.display = 'none';
  }

  async function sendAllianceCombatMessage() {
    const recipient = document.getElementById('sim-ally-recipient')?.value?.trim();
    const message = document.getElementById('sim-ally-msg-body')?.value?.trim();
    const statusDiv = document.getElementById('sim-ally-msg-status');
    const sendBtn = document.getElementById('sim-ally-send-btn');

    if (!recipient) {
      alert("Please specify a recipient commander username or player ID.");
      return;
    }
    if (!message) {
      alert("Message body cannot be empty.");
      return;
    }

    if (statusDiv) {
      statusDiv.style.display = 'block';
      statusDiv.style.background = 'rgba(0,229,255,0.15)';
      statusDiv.style.color = 'var(--cyan)';
      statusDiv.textContent = 'Transmitting message via MCP send_message tool...';
    }
    if (sendBtn) sendBtn.disabled = true;

    try {
      const res = await fetch('/api/call', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          tool: 'send_message',
          arguments: {
            recipient: recipient,
            recipientId: recipient,
            message: message,
            body: message
          }
        })
      });
      const data = await res.json();
      if (data.success) {
        if (statusDiv) {
          statusDiv.style.background = 'rgba(16,185,129,0.15)';
          statusDiv.style.color = '#86efac';
          statusDiv.textContent = `✅ Message successfully delivered to ${recipient}!`;
        }
        showToast(`In-game battle brief dispatched to ${recipient}!`);
        setTimeout(() => closeAllianceMessageModal(), 1800);
      } else {
        const err = data.error || 'Failed to dispatch message';
        if (statusDiv) {
          statusDiv.style.background = 'rgba(239,68,68,0.15)';
          statusDiv.style.color = '#fca5a5';
          statusDiv.textContent = `❌ Transmission error: ${err}`;
        }
      }
    } catch(e) {
      if (statusDiv) {
        statusDiv.style.background = 'rgba(239,68,68,0.15)';
        statusDiv.style.color = '#fca5a5';
        statusDiv.textContent = `❌ Network/MCP error: ${e.message}`;
      }
    } finally {
      if (sendBtn) sendBtn.disabled = false;
    }
  }

  function copyAllianceMessageText() {
    const msg = document.getElementById('sim-ally-msg-body')?.value;
    if (msg && navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(msg).then(() => {
        showToast("📋 Message text copied to clipboard!");
      });
    } else if (msg) {
      prompt("Copy battle brief message:", msg);
    }
  }

  // =========================================================================
  // TACTICAL DEFENSE AUTO-PLANNER AT SPECIFIC TICK
  // =========================================================================
  let currentDefenseScenarioData = null;

  async function openDefenseScenarioModal() {
    const bottomCoords = document.getElementById('sim-bcalc-bottom-coords');
    let initCoords = (bottomCoords ? bottomCoords.value.trim() : '') || (simEnteredCoordsDef || '');
    if (!initCoords && homeDefenseData && homeDefenseData.coords && homeDefenseData.coords !== 'Unknown') {
      initCoords = homeDefenseData.coords;
    }

    const cInput = document.getElementById('sim-plan-coords');
    if (cInput) cInput.value = initCoords;

    const selectEl = document.getElementById('sim-plan-planet-select');
    if (selectEl) {
      selectEl.innerHTML = '<option value="">Select Planet...</option>';
      if (homeDefenseData && homeDefenseData.coords && homeDefenseData.coords !== 'Unknown') {
        const opt = document.createElement('option');
        opt.value = homeDefenseData.coords;
        opt.textContent = `🪐 Home Planet (${homeDefenseData.coords})`;
        selectEl.appendChild(opt);
      }
      (universePlanetsList || []).slice(0, 40).forEach(p => {
        if (p.coords && p.coords !== (homeDefenseData ? homeDefenseData.coords : '')) {
          const opt = document.createElement('option');
          opt.value = p.coords;
          opt.textContent = `${p.name || 'Planet'} (${p.coords})`;
          selectEl.appendChild(opt);
        }
      });
    }

    const modal = document.getElementById('sim-defense-planner-modal');
    if (modal) modal.style.display = 'flex';

    await loadDefenseScenarioPreview();
  }

  function closeDefenseScenarioModal() {
    const modal = document.getElementById('sim-defense-planner-modal');
    if (modal) modal.style.display = 'none';
  }

  async function loadDefenseScenarioPreview() {
    const coords = document.getElementById('sim-plan-coords')?.value?.trim() || '';
    const tickInput = document.getElementById('sim-plan-tick');
    const tick = tickInput ? parseInt(tickInput.value, 10) || 0 : 0;
    const windowVal = parseInt(document.getElementById('sim-plan-window')?.value || '0', 10);
    const bodyEl = document.getElementById('sim-plan-body');

    if (bodyEl) {
      bodyEl.innerHTML = `
        <div style="grid-column: 1 / -1; text-align: center; padding: 2.5rem; color: var(--cyan);">
          <div class="spinner" style="margin: 0 auto 1rem auto; width: 32px; height: 32px; border: 3px solid rgba(0,229,255,0.2); border-top-color: var(--cyan); border-radius: 50%; animation: spin 0.8s linear infinite;"></div>
          Scanning fleet radars, movements, and intel for coordinates ${escapeHtml(coords || 'Home Planet')}...
        </div>
      `;
    }

    try {
      const q = (typeof URLSearchParams !== 'undefined')
        ? new URLSearchParams({ coords: coords, tick: String(tick), window: String(windowVal) }).toString()
        : (`coords=${encodeURIComponent(coords)}&tick=${tick}&window=${windowVal}`);
      const res = await fetch(`/api/combat/defense_scenario?${q}`);
      const data = await res.json();

      if (!data.success) {
        if (bodyEl) {
          bodyEl.innerHTML = `
            <div style="grid-column: 1 / -1; padding: 1.5rem; background: rgba(239,68,68,0.1); border: 1px solid rgba(239,68,68,0.3); border-radius: 8px; color: #fca5a5;">
              ❌ Error loading defense scenario: ${escapeHtml(data.error || 'Server error')}
            </div>
          `;
        }
        return;
      }

      currentDefenseScenarioData = data;

      if (tickInput && (!tickInput.value || tickInput.value === '0')) {
        tickInput.value = data.targetTick || data.currentTick || 1;
      }

      const curTickBadge = document.getElementById('sim-plan-cur-tick-badge');
      if (curTickBadge) {
        curTickBadge.textContent = `(Now: Tick ${data.currentTick}${data.nextTickIn ? ' • ' + data.nextTickIn : ''})`;
      }

      renderDefenseScenarioPreview(data);
    } catch(e) {
      console.error("Defense scenario error:", e);
      if (bodyEl) {
        bodyEl.innerHTML = `
          <div style="grid-column: 1 / -1; padding: 1.5rem; background: rgba(239,68,68,0.1); border: 1px solid rgba(239,68,68,0.3); border-radius: 8px; color: #fca5a5;">
            ❌ Network/Fetch error: ${escapeHtml(e.message)}
          </div>
        `;
      }
    }
  }

  function renderDefenseScenarioPreview(data) {
    const bodyEl = document.getElementById('sim-plan-body');
    if (!bodyEl) return;

    const def = data.defender || {};
    const availFleets = def.availableFleets || [];
    const lateFleets = def.lateFleets || [];
    const garrison = def.garrisonShips || {};
    const pds = def.pds || {};
    const attackers = data.attackers || [];

    // Left Column: Defender Readiness
    let defHtml = `
      <div style="background: rgba(13,18,34,0.7); border: 1px solid rgba(56,189,248,0.25); border-radius: 8px; padding: 1.1rem; display: flex; flex-direction: column; gap: 0.9rem;">
        <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid rgba(255,255,255,0.06); padding-bottom: 0.6rem;">
          <div>
            <div style="font-weight: 700; color: #38bdf8; font-size: 0.95rem; display: flex; align-items: center; gap: 0.4rem;">
              🛡️ Defender Force at Tick ${data.targetTick}
            </div>
            <div style="font-size: 0.75rem; color: var(--text-dim); margin-top: 0.15rem;">
              ${escapeHtml(data.planetName || 'Planet')} [${escapeHtml(data.coords || 'Coordinates')}]
            </div>
          </div>
          <span class="badge" style="background: rgba(56,189,248,0.15); color: #38bdf8; font-family: var(--font-mono); font-size: 0.8rem;">
            ${formatNum(def.totalAvailableShips || 0)} Total Ships
          </span>
        </div>

        <!-- Stationary Hangar Garrison -->
        <div style="background: rgba(0,0,0,0.25); border: 1px solid rgba(255,255,255,0.05); border-radius: 6px; padding: 0.75rem;">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.4rem;">
            <strong style="font-size: 0.82rem; color: var(--text-bright);">🏛️ Stationary Garrison (Docked)</strong>
            <span style="font-size: 0.75rem; color: #86efac; font-family: var(--font-mono);">${formatNum(Object.values(garrison).reduce((a,b)=>a+b, 0))} ships</span>
          </div>
          <div style="display: flex; flex-wrap: wrap; gap: 0.35rem; font-size: 0.75rem;">
            ${Object.keys(garrison).length > 0 ? Object.entries(garrison).map(([sid, cnt]) => `
              <span style="background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.1); padding: 0.15rem 0.45rem; border-radius: 4px; font-family: var(--font-mono);">
                ${sid.replace('main-vanguard-', '').replace('main-', '')}: <strong>${formatNum(cnt)}</strong>
              </span>
            `).join('') : '<span style="color: var(--text-dim); font-style: italic;">No docked hangar ships</span>'}
          </div>
        </div>

        <!-- Station Defense PDS -->
        <div style="background: rgba(0,0,0,0.25); border: 1px solid rgba(255,255,255,0.05); border-radius: 6px; padding: 0.75rem;">
          <div style="font-size: 0.82rem; font-weight: 700; color: var(--yellow); margin-bottom: 0.4rem;">
            ⚡ Planetary Defense Structures (PDS)
          </div>
          <div style="display: grid; grid-template-columns: repeat(2, 1fr); gap: 0.4rem; font-size: 0.75rem;">
            <div>🛡️ Shield: <strong>Lvl ${pds['Shield Generator'] || 0}</strong></div>
            <div>⚡ Laser: <strong>Lvl ${pds['Laser Battery'] || 0}</strong></div>
            <div>🔮 Ion Cannon: <strong>Lvl ${pds['Ion Cannon'] || 0}</strong></div>
            <div>🚀 Missile Silo: <strong>Lvl ${pds['Missile Silo'] || 0}</strong></div>
          </div>
        </div>

        <!-- Available In-Transit / Returning Fleets -->
        <div>
          <div style="font-size: 0.82rem; font-weight: 700; color: #86efac; margin-bottom: 0.4rem;">
            ✅ Arriving in Time for Battle (${availFleets.length} fleet(s))
          </div>
          <div style="display: flex; flex-direction: column; gap: 0.4rem; max-height: 180px; overflow-y: auto;">
            ${availFleets.map(f => {
              const shipsCnt = Object.values(f.ships || {}).reduce((a,b)=>a+b, 0);
              const isDocked = f.arrivalStatus === 'DOCKED_NOW';
              return `
                <div style="background: rgba(16,185,129,0.06); border: 1px solid rgba(16,185,129,0.2); border-radius: 6px; padding: 0.5rem 0.7rem; font-size: 0.75rem;">
                  <div style="display: flex; justify-content: space-between; align-items: center;">
                    <strong style="color: #86efac;">${escapeHtml(f.name || 'Fleet')}</strong>
                    <span class="badge" style="background: rgba(16,185,129,0.2); color: #86efac;">
                      ${isDocked ? 'Docked Now' : `Arrives Tick ${f.arrivalTick} (+${f.marginTicks || 0} margin)`}
                    </span>
                  </div>
                  <div style="margin-top: 0.2rem; color: var(--text-dim); font-family: var(--font-mono);">
                    ${shipsCnt} ships • ${Object.entries(f.ships || {}).map(([s,c])=>`${s.replace('main-vanguard-','')}:${c}`).slice(0,4).join(', ')}
                  </div>
                </div>
              `;
            }).join('') || '<div style="color: var(--text-dim); font-style: italic; font-size: 0.75rem;">No returning fleets available.</div>'}
          </div>
        </div>

        <!-- Late Fleets (Misses Battle) -->
        ${lateFleets.length > 0 ? `
          <div>
            <div style="font-size: 0.8rem; font-weight: 700; color: #f87171; margin-bottom: 0.3rem;">
              ⚠️ Late Arrivals — Miss Battle (${lateFleets.length})
            </div>
            <div style="display: flex; flex-direction: column; gap: 0.3rem; max-height: 120px; overflow-y: auto;">
              ${lateFleets.map(f => `
                <div style="background: rgba(239,68,68,0.08); border: 1px solid rgba(239,68,68,0.2); border-radius: 5px; padding: 0.4rem 0.6rem; font-size: 0.72rem; color: #fca5a5;">
                  <strong>${escapeHtml(f.name || 'Fleet')}</strong>: Arrives at Tick ${f.arrivalTick} (misses battle by ${f.missedByTicks} ticks)
                </div>
              `).join('')}
            </div>
          </div>
        ` : ''}
      </div>
    `;

    // Right Column: Inbound Hostile Attackers & Scans
    let atkHtml = `
      <div style="background: rgba(13,18,34,0.7); border: 1px solid rgba(239,68,68,0.3); border-radius: 8px; padding: 1.1rem; display: flex; flex-direction: column; gap: 0.9rem;">
        <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid rgba(255,255,255,0.06); padding-bottom: 0.6rem;">
          <div>
            <div style="font-weight: 700; color: #f87171; font-size: 0.95rem; display: flex; align-items: center; gap: 0.4rem;">
              ⚔️ Inbound Attack Coalition (${attackers.length} fleet(s))
            </div>
            <div style="font-size: 0.75rem; color: var(--text-dim); margin-top: 0.15rem;">
              Landing at Tick ${data.targetTick} (±${data.window})
            </div>
          </div>
          <span class="badge" style="background: rgba(239,68,68,0.15); color: #fca5a5; font-family: var(--font-mono); font-size: 0.8rem;">
            ${formatNum(data.totalAttackerShips || 0)} Scanned Ships
          </span>
        </div>

        <div style="display: flex; flex-direction: column; gap: 0.8rem; overflow-y: auto; max-height: 480px;">
          ${attackers.length > 0 ? attackers.map((af, idx) => {
            const rel = af.reliability || { score: 50, rating: 'MODERATE', color: '#fde047', scanType: 'SCAN' };
            const decoy = af.decoy || { isDecoy: false, decoyChance: 0, badge: 'GENUINE', color: '#86efac', reasons: [] };
            const shipsMap = af.ships || {};
            return `
              <div style="background: rgba(0,0,0,0.35); border: 1px solid rgba(255,255,255,0.08); border-radius: 8px; padding: 0.8rem; display: flex; flex-direction: column; gap: 0.5rem;">
                <div style="display: flex; justify-content: space-between; align-items: flex-start; gap: 0.5rem;">
                  <div>
                    <div style="font-weight: 700; color: #fca5a5; font-size: 0.85rem;">
                      ${escapeHtml(af.name || ('Hostile Fleet ' + (idx+1)))}
                    </div>
                    <div style="font-size: 0.72rem; color: var(--text-dim); margin-top: 0.1rem; font-family: var(--font-mono);">
                      Lands Tick <strong>${af.arrivalTick}</strong> (ETA: ${af.eta} ticks) • Mission: ${af.mission || 'ATTACK'}
                    </div>
                  </div>
                  <span class="badge" style="background: rgba(239,68,68,0.2); color: #f87171; font-weight: 700; font-family: var(--font-mono);">
                    ${formatNum(af.totalShips || 0)} ships
                  </span>
                </div>

                <div style="display: flex; gap: 0.4rem; flex-wrap: wrap; align-items: center;">
                  <div style="display: inline-flex; align-items: center; gap: 0.35rem; padding: 0.2rem 0.5rem; border-radius: 4px; background: rgba(0,0,0,0.4); border: 1px solid ${rel.color}; font-size: 0.72rem;">
                    <span style="color: ${rel.color}; font-weight: 700;">📡 Intel Reliability: ${rel.score}% [${rel.rating}]</span>
                  </div>

                  <div style="display: inline-flex; align-items: center; gap: 0.35rem; padding: 0.2rem 0.5rem; border-radius: 4px; background: rgba(0,0,0,0.4); border: 1px solid ${decoy.color}; font-size: 0.72rem;">
                    <span style="color: ${decoy.color}; font-weight: 700;">🎯 Decoy Chance: ${decoy.decoyChance}% [${decoy.badge}]</span>
                  </div>
                </div>

                ${(rel.warnings && rel.warnings.length > 0) || (decoy.reasons && decoy.reasons.length > 0) ? `
                  <div style="font-size: 0.72rem; background: rgba(255,255,255,0.03); border-left: 2px solid ${decoy.isDecoy ? '#f87171' : (rel.cloakRisk ? '#fde047' : 'var(--cyan)')}; padding: 0.4rem 0.6rem; border-radius: 0 4px 4px 0;">
                    ${(rel.warnings || []).map(w => `<div style="color: #fde047;">${escapeHtml(w)}</div>`).join('')}
                    ${(decoy.reasons || []).map(r => `<div style="color: ${decoy.color};">💡 ${escapeHtml(r)}</div>`).join('')}
                  </div>
                ` : ''}

                <div style="display: flex; flex-wrap: wrap; gap: 0.3rem; font-size: 0.72rem; margin-top: 0.2rem;">
                  ${Object.entries(shipsMap).map(([sid, cnt]) => `
                    <span style="background: rgba(239,68,68,0.1); border: 1px solid rgba(239,68,68,0.25); padding: 0.1rem 0.4rem; border-radius: 3px; font-family: var(--font-mono); color: #fca5a5;">
                      ${sid.replace('main-vanguard-', '').replace('main-', '')}: <strong>${formatNum(cnt)}</strong>
                    </span>
                  `).join('')}
                </div>
              </div>
            `;
          }).join('') : `
            <div style="text-align: center; padding: 3rem 1.5rem; color: var(--text-dim);">
              <div style="font-size: 2rem; margin-bottom: 0.5rem;">🌌</div>
              <div>No incoming hostile attacks or scans detected for Tick ${data.targetTick}.</div>
              <div style="font-size: 0.75rem; margin-top: 0.4rem;">You can adjust coordinates or battle tick above, or enter manually in the simulator.</div>
            </div>
          `}
        </div>
      </div>
    `;

    bodyEl.innerHTML = defHtml + atkHtml;
  }

  function applyDefenseScenarioToCalculator() {
    if (!currentDefenseScenarioData) {
      showToast("No defense scenario data loaded.");
      return;
    }

    const data = currentDefenseScenarioData;
    const def = data.defender || {};
    const availFleets = def.availableFleets || [];
    const garrison = def.garrisonShips || {};
    const pds = def.pds || {};
    const attackers = data.attackers || [];

    // 1. Populate Defender Fleets
    simDefenderFleets = [];
    simFleetSeq = 1;

    simDefenderFleets.push({
      id: 'def_garrison',
      name: (data.planetName || 'Defender') + ' Garrison',
      side: 'def',
      enabled: true,
      ships: Object.assign({}, garrison)
    });

    availFleets.forEach((fl, i) => {
      if (fl.arrivalStatus !== 'DOCKED_NOW') {
        simDefenderFleets.push({
          id: fl.id || ('def_reinforce_' + (i+1)),
          name: (fl.name || 'Fleet') + ` (Arrives Tick ${fl.arrivalTick})`,
          side: 'def',
          enabled: true,
          ships: Object.assign({}, fl.ships || {})
        });
      }
    });

    // 2. Set PDS levels
    if (pds) {
      if (document.getElementById('sim-pds-shield-lvl')) {
        document.getElementById('sim-pds-shield-lvl').value = pds['Shield Generator'] || 0;
        document.getElementById('sim-pds-shield-chk').checked = (pds['Shield Generator'] || 0) > 0;
      }
      if (document.getElementById('sim-pds-laser-lvl')) {
        document.getElementById('sim-pds-laser-lvl').value = pds['Laser Battery'] || 0;
        document.getElementById('sim-pds-laser-chk').checked = (pds['Laser Battery'] || 0) > 0;
      }
      if (document.getElementById('sim-pds-ion-lvl')) {
        document.getElementById('sim-pds-ion-lvl').value = pds['Ion Cannon'] || 0;
        document.getElementById('sim-pds-ion-chk').checked = (pds['Ion Cannon'] || 0) > 0;
      }
      if (document.getElementById('sim-pds-silo-lvl')) {
        document.getElementById('sim-pds-silo-lvl').value = pds['Missile Silo'] || 0;
        document.getElementById('sim-pds-silo-chk').checked = (pds['Missile Silo'] || 0) > 0;
      }
    }

    // 3. Populate Attacker Fleets
    simAttackerFleets = [];
    if (attackers.length > 0) {
      attackers.forEach((af, idx) => {
        simAttackerFleets.push({
          id: af.id || ('atk_' + (idx + 1)),
          name: (af.name || `Hostile Fleet ${idx + 1}`) + ` (Tick ${af.arrivalTick})`,
          side: 'atk',
          enabled: true,
          ships: Object.assign({}, af.ships || {})
        });
      });
    } else {
      initDefaultAttackerFleet();
    }

    // 4. Set Coordinates
    const targetCoords = data.coords || '';
    simEnteredCoordsDef = targetCoords;
    const bcalcBottom = document.getElementById('sim-bcalc-bottom-coords');
    if (bcalcBottom) bcalcBottom.value = targetCoords;

    closeDefenseScenarioModal();
    renderCalcTabs();
    renderSimulatorFleets();
    calculateCombat();
    showToast(`🛡️ Defense scenario loaded for Tick ${data.targetTick}! Simulating combat...`);
  }

  function copyDefenseScenarioBrief() {
    if (!currentDefenseScenarioData) {
      showToast("No active scenario to copy.");
      return;
    }
    const d = currentDefenseScenarioData;
    const def = d.defender || {};
    const avail = def.availableFleets || [];
    const atks = d.attackers || [];

    const brief = [
      `[TACTICAL DEFENSE SCENARIO — TICK ${d.targetTick}]`,
      `Target: ${d.planetName || 'Planet'} [${d.coords}]`,
      `Defender Total Force: ${def.totalAvailableShips || 0} ships across ${avail.length + 1} defending element(s)`,
      `Inbound Attackers: ${d.totalAttackerShips || 0} ships across ${atks.length} fleet(s)`,
      atks.map((a, i) => ` • Fleet ${i+1}: ${a.name} (${a.totalShips} ships) | Reliability: ${a.reliability?.score || 50}% | Decoy Chance: ${a.decoy?.decoyChance || 0}% [${a.decoy?.badge || 'NORMAL'}]`).join('\n'),
      `Generated by Pegasus Galaxy MCP Suite v0.5`
    ].join('\n');

    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(brief).then(() => showToast("📋 Defense brief copied to clipboard!"));
    } else {
      prompt("Copy tactical defense brief:", brief);
    }
  }

  async function shareDefenseScenarioLink() {
    applyDefenseScenarioToCalculator();
    openCalcShareModal();
  }

  function handleCalcUrlHash() {
    const hash = window.location.hash || '';
    if (!hash) return;

    // Check for compressed share link #c=...
    const matchC = hash.match(/c=([^&]+)/);
    if (matchC) {
      const code = matchC[1];
      decompressFromUrlSafe(code).then(state => {
        if (state) {
          applyCalcState(state);
          if (calcSessions && calcSessions.length > 0) {
            calcSessions[0].name = state.title || 'Shared Calc';
            calcSessions[0].state = state;
            renderCalcTabs();
          }
          showToast(`Imported shared battle: ${state.title || 'Battle'}`);
        }
      }).catch(e => console.warn("Failed to decompress hash:", e));
      return;
    }

    // Check for import
    const matchImport = hash.match(/import=([^&]+)/);
    if (matchImport) {
      const transferId = matchImport[1];
      try {
        const raw = localStorage.getItem(transferId) || localStorage.getItem('peg_calc_transfer_latest');
        if (raw) {
          const state = JSON.parse(raw);
          applyCalcState(state);
          if (calcSessions && calcSessions.length > 0) {
            calcSessions[0].name = state.title || 'Imported Calc';
            calcSessions[0].state = state;
            renderCalcTabs();
          }
          showToast(`Imported calculation: ${state.title || 'Battle'}`);
        }
      } catch(e) {
        console.warn("Failed to load transferred calculation:", e);
      }
      return;
    }

    // Check for coords
    const matchCoords = hash.match(/coords=([^&]+)/);
    if (matchCoords) {
      const coords = decodeURIComponent(matchCoords[1]).trim();
      setTimeout(() => {
        onCoordsInputChanged('def', coords);
        const bottomCoords = document.getElementById('sim-bcalc-bottom-coords');
        if (bottomCoords) bottomCoords.value = coords;
        if (calcSessions && calcSessions.length > 0) {
          calcSessions[0].name = `Target ${coords}`;
          renderCalcTabs();
        }
      }, 250);
    }
  }

  function handleCalcUrlHashPostLoad() {
    const hash = window.location.hash || '';
    if (!hash) return;

    const matchC = hash.match(/c=([^&]+)/);
    if (matchC) {
      const code = matchC[1];
      decompressFromUrlSafe(code).then(state => {
        if (state) applyCalcState(state);
      }).catch(e => {});
      return;
    }

    const matchImport = hash.match(/import=([^&]+)/);
    if (matchImport) {
      const transferId = matchImport[1];
      try {
        const raw = localStorage.getItem(transferId) || localStorage.getItem('peg_calc_transfer_latest');
        if (raw) {
          const state = JSON.parse(raw);
          applyCalcState(state);
        }
      } catch(e) {}
    }
  }

  async function initStandaloneCombatSimulator() {
    document.body.classList.add('standalone-mode');
    const container = document.querySelector('.container');
    if (container) container.classList.add('wide-mode');

    const mainHeader = document.getElementById('main-header');
    if (mainHeader) mainHeader.style.display = 'none';
    const mainTabs = document.getElementById('main-tabs');
    if (mainTabs) mainTabs.style.display = 'none';
    const footer = document.querySelector('footer');
    if (footer) footer.style.display = 'none';

    const standHeader = document.getElementById('standalone-calc-header');
    if (standHeader) standHeader.style.display = 'flex';

    document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
    const bcalcTab = document.getElementById('tab-battlecalc');
    if (bcalcTab) bcalcTab.classList.add('active');

    initCalcSessions();
    handleCalcUrlHash();

    await loadCombatSimulator();
    handleCalcUrlHashPostLoad();
  }

  function setBcalcHullFilter(filter) {
    bcalcHullFilter = filter;
    document.querySelectorAll('.bcalc-filter-btn').forEach(btn => {
      if (btn.textContent.trim().toUpperCase() === filter.toUpperCase() ||
         (filter === 'FIGHTER' && btn.textContent.trim() === 'Fi') ||
         (filter === 'CORVETTE' && btn.textContent.trim() === 'Co') ||
         (filter === 'FRIGATE' && btn.textContent.trim() === 'Fr') ||
         (filter === 'DESTROYER' && btn.textContent.trim() === 'De') ||
         (filter === 'CRUISER' && btn.textContent.trim() === 'Cr') ||
         (filter === 'BATTLESHIP' && btn.textContent.trim() === 'Bs') ||
         (filter === 'ALL' && btn.textContent.trim() === 'All') ||
         (filter === 'PDS' && btn.textContent.trim() === 'PDS')) {
        btn.classList.add('active');
      } else if (!btn.textContent.includes('Fleet') && !btn.textContent.includes('Empty') && !btn.textContent.includes('Reset') && !btn.textContent.includes('Width') && !btn.textContent.includes('Fit') && !btn.textContent.includes('%')) {
        btn.classList.remove('active');
      }
    });
    renderBcalcMatrix();
  }

  function emptyAllFleets() {
    simAttackerFleets.forEach(f => { f.ships = {}; });
    simDefenderFleets.forEach(f => { f.ships = {}; });
    renderBcalcMatrix();
    renderAllFleetCards('atk');
    renderAllFleetCards('def');
    recalcCoalitionSummary('atk');
    showToast('Emptied all attacking and defending fleet ship counts.');
  }

  function emptySingleFleet(side, fleetId) {
    const list = (side === 'atk') ? simAttackerFleets : simDefenderFleets;
    const f = list.find(x => x.id === fleetId);
    if (f) {
      f.ships = {};
      renderBcalcMatrix();
      renderAllFleetCards(side);
      if (side === 'atk') recalcCoalitionSummary('atk');
      showToast(`Emptied ${f.name}`);
    }
  }

  function toggleBcalcFleetDisable(side, fleetId, isChecked) {
    onFleetToggle(side, fleetId, !isChecked); // checked means disabled in Planetarion
    renderBcalcMatrix();
  }

  function syncWithBcalcMatrix() {
    if (currentBcalcLayout === 'bcalc') {
      renderBcalcMatrix();
    }
  }

  function parseShipCount(val) {
    if (val === null || val === undefined) return 0;
    if (typeof val === 'number') return Math.max(0, Math.floor(val));
    let str = String(val).trim();
    if (!str) return 0;
    
    // Support 'k' / 'm' shorthand: e.g. 60k -> 60000, 1.5m -> 1500000
    const kMatch = str.match(/^([\d.,]+)\s*k$/i);
    if (kMatch) {
      const num = parseFloat(kMatch[1].replace(/,/g, ''));
      return isNaN(num) ? 0 : Math.max(0, Math.round(num * 1000));
    }
    const mMatch = str.match(/^([\d.,]+)\s*m$/i);
    if (mMatch) {
      const num = parseFloat(mMatch[1].replace(/,/g, ''));
      return isNaN(num) ? 0 : Math.max(0, Math.round(num * 1000000));
    }

    // Strip commas, spaces, and non-numeric chars
    const clean = str.replace(/[, \s]/g, '');
    const num = parseInt(clean, 10);
    return isNaN(num) ? 0 : Math.max(0, num);
  }

  function autoResizeBcalcInput(inputEl) {
    if (!inputEl) return;
    const val = inputEl.value;
    const len = String(val || '').length;
    // Auto-expand input width dynamically if number has 7+ characters
    if (len >= 7) {
      inputEl.style.width = Math.max(94, len * 9.5 + 18) + 'px';
    } else {
      inputEl.style.width = '';
    }
    const count = parseShipCount(val);
    if (count > 0) {
      inputEl.classList.remove('zero-ships');
      inputEl.classList.add('has-ships');
      inputEl.title = `${count.toLocaleString()} ships`;
    } else {
      inputEl.classList.remove('has-ships');
      inputEl.classList.add('zero-ships');
      inputEl.title = '0 ships';
    }
  }

  function getBcalcInputWidthStyle(cnt) {
    const len = String(cnt || '').length;
    if (len >= 7) {
      return `style="width: ${Math.max(94, len * 9.5 + 18)}px;"`;
    }
    return '';
  }

  function onBcalcShipCountChange(side, fleetId, shipId, val) {
    const count = parseShipCount(val);
    const list = (side === 'atk') ? simAttackerFleets : simDefenderFleets;
    const f = list.find(x => x.id === fleetId);
    if (!f) return;

    if (count > 0) {
      f.ships[shipId] = count;
    } else {
      delete f.ships[shipId];
    }

    if (side === 'atk') recalcCoalitionSummary('atk');
    renderBcalcMatrix();
  }

  function renderBcalcMatrix() {
    const container = document.getElementById('bcalc-matrix-container');
    if (!container) return;

    const shipList = (typeof refData !== 'undefined' && refData && refData.ships && refData.ships.length > 0)
      ? refData.ships
      : [];

    // Filter ships by selected category
    let filteredShips = shipList;
    if (bcalcHullFilter === 'PDS') {
      filteredShips = [];
    } else if (bcalcHullFilter !== 'ALL') {
      filteredShips = shipList.filter(s => (s.category || s.shipClass || '').toUpperCase() === bcalcHullFilter);
    }

    const showPds = (bcalcHullFilter === 'ALL' || bcalcHullFilter === 'PDS');
    const pdsStructures = [
      { id: 'Shield Generator', name: 'Shield Generator', cat: 'PDS', short: 'PDS', chkId: 'sim-pds-shield-chk', lvlId: 'sim-pds-shield-lvl' },
      { id: 'Ion Cannon', name: 'Ion Cannon Battery', cat: 'PDS', short: 'PDS', chkId: 'sim-pds-ion-chk', lvlId: 'sim-pds-ion-lvl' },
      { id: 'Missile Silo', name: 'Orbital Missile Silo', cat: 'PDS', short: 'PDS', chkId: 'sim-pds-silo-chk', lvlId: 'sim-pds-silo-lvl' },
      { id: 'Laser Battery', name: 'Heavy Laser Battery', cat: 'PDS', short: 'PDS', chkId: 'sim-pds-laser-chk', lvlId: 'sim-pds-laser-lvl' },
    ];

    const defFleets = simDefenderFleets;
    const atkFleets = simAttackerFleets;

    // Planetarion-style column sizing: columns NEVER squish or truncate numbers
    let styleVars = '';
    if (bcalcZoomMode === '70') {
      styleVars = '--bcalc-font-size: 0.72rem; --bcalc-cell-pad: 0.2rem 0.3rem; --bcalc-input-w: 78px; --bcalc-input-font: 0.74rem;';
    } else if (bcalcZoomMode === '85') {
      styleVars = '--bcalc-font-size: 0.76rem; --bcalc-cell-pad: 0.24rem 0.35rem; --bcalc-input-w: 86px; --bcalc-input-font: 0.78rem;';
    } else {
      // Auto or 100%: Standard generous width accommodating 8+ figure ship counts with ease
      styleVars = '--bcalc-font-size: 0.80rem; --bcalc-cell-pad: 0.28rem 0.42rem; --bcalc-input-w: 94px; --bcalc-input-font: 0.82rem;';
    }

    // Build the Planetarion side-by-side table HTML
    let html = `
      <table class="bcalc-matrix-table" style="${styleVars}">
        <thead>
          <!-- Top Row: Big Side Titles -->
          <tr>
            <th colspan="${2 + defFleets.length + 3}" class="side-main-header" style="color: #38bdf8; background: rgba(56, 189, 248, 0.15); border-right: 2px solid rgba(255,255,255,0.2);">
              🛡️ DEFENDING FORCES & GARRISONS
            </th>
            <th colspan="${2 + atkFleets.length + 3}" class="side-main-header" style="color: #ef4444; background: rgba(239, 68, 68, 0.15);">
              🚀 ATTACKING COALITION FLEETS
            </th>
          </tr>

          <!-- Header Row 2: Columns -->
          <tr>
            <!-- Defender Columns -->
            <th class="ship-name-cell">Ship / Defense</th>
            <th style="font-size: 0.7rem; color: var(--text-dim);">Class</th>
    `;

    // Defender fleet columns
    defFleets.forEach((f, idx) => {
      const shortName = f.name.length > 15 ? f.name.substring(0, 13) + '…' : f.name;
      const coordsBadge = f.coords ? `[${f.coords}]` : '[Set Coords]';
      const colClass = (idx % 2 === 0) ? 'def-even' : 'def-odd';
      const fTotal = getFleetShipCount(f);
      html += `
        <th class="bcalc-fleet-header bcalc-def-col ${colClass}">
          <div><span class="bcalc-fleet-pill def">DEF ${idx + 1}</span></div>
          <div style="font-weight: 700; color: #38bdf8; cursor: pointer; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 110px; margin: 0 auto;" title="Click to rename: ${escapeHtml(f.name)}" onclick="promptRenameFleet('def', '${f.id}')">
            ${escapeHtml(shortName)} <span style="font-size: 0.65rem; opacity: 0.7;">✏️</span>
          </div>
          <div style="font-size: 0.68rem; color: #ffd54f; cursor: pointer; margin-top: 0.1rem;" title="Click to set/edit coordinates" onclick="promptFleetCoords('def', '${f.id}')">
            ${escapeHtml(coordsBadge)} 🎯
          </div>
          <div style="font-size: 0.72rem; font-weight: 700; color: #fff; margin-top: 0.15rem; font-family: var(--font-mono);" title="Total ships in this fleet">
            ${fTotal.toLocaleString()} <span style="font-size: 0.64rem; font-weight: 400; color: var(--text-dim);">ships</span>
          </div>
          <div style="margin-top: 0.25rem; display: flex; justify-content: center; gap: 0.35rem; align-items: center;">
            <a href="javascript:void(0)" onclick="emptySingleFleet('def', '${f.id}')" style="color: #38bdf8; text-decoration: none; font-size: 0.7rem; font-weight: 600;" title="Empty fleet counts">(E)</a>
            <a href="javascript:void(0)" onclick="removeFleet('def', '${f.id}')" style="color: #f87171; text-decoration: none; font-size: 0.75rem; font-weight: 700;" title="Remove this fleet column">✕</a>
            <input type="checkbox" ${!f.enabled ? 'checked' : ''} onchange="toggleBcalcFleetDisable('def', '${f.id}', this.checked)" title="Check to Disable Fleet" style="cursor: pointer;">
          </div>
        </th>
      `;
    });

    html += `
      <th style="color: #38bdf8; background: rgba(56, 189, 248, 0.1);">Total</th>
      <th style="color: #f87171; background: rgba(239, 68, 68, 0.15);">Killed</th>
      <th style="color: #b388ff; background: rgba(179,136,255,0.15);" class="bcalc-side-divider">EMPed</th>

      <!-- Attacker Columns -->
      <th class="ship-name-cell">Ship</th>
      <th style="font-size: 0.7rem; color: var(--text-dim);">Class</th>
    `;

    // Attacker fleet columns
    atkFleets.forEach((f, idx) => {
      const shortName = f.name.length > 15 ? f.name.substring(0, 13) + '…' : f.name;
      const coordsBadge = f.coords ? `[${f.coords}]` : '[Set Coords]';
      const colClass = (idx % 2 === 0) ? 'atk-even' : 'atk-odd';
      const fTotal = getFleetShipCount(f);
      html += `
        <th class="bcalc-fleet-header bcalc-atk-col ${colClass}">
          <div><span class="bcalc-fleet-pill atk">ATK ${idx + 1}</span></div>
          <div style="font-weight: 700; color: #f87171; cursor: pointer; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 110px; margin: 0 auto;" title="Click to rename: ${escapeHtml(f.name)}" onclick="promptRenameFleet('atk', '${f.id}')">
            ${escapeHtml(shortName)} <span style="font-size: 0.65rem; opacity: 0.7;">✏️</span>
          </div>
          <div style="font-size: 0.68rem; color: #fca5a5; cursor: pointer; margin-top: 0.1rem;" title="Click to set/edit coordinates" onclick="promptFleetCoords('atk', '${f.id}')">
            ${escapeHtml(coordsBadge)} 🎯
          </div>
          <div style="font-size: 0.72rem; font-weight: 700; color: #fff; margin-top: 0.15rem; font-family: var(--font-mono);" title="Total ships in this fleet">
            ${fTotal.toLocaleString()} <span style="font-size: 0.64rem; font-weight: 400; color: var(--text-dim);">ships</span>
          </div>
          <div style="margin-top: 0.25rem; display: flex; justify-content: center; gap: 0.35rem; align-items: center;">
            <a href="javascript:void(0)" onclick="emptySingleFleet('atk', '${f.id}')" style="color: #f87171; text-decoration: none; font-size: 0.7rem; font-weight: 600;" title="Empty fleet counts">(E)</a>
            <a href="javascript:void(0)" onclick="removeFleet('atk', '${f.id}')" style="color: #f87171; text-decoration: none; font-size: 0.75rem; font-weight: 700;" title="Remove this fleet column">✕</a>
            <input type="checkbox" ${!f.enabled ? 'checked' : ''} onchange="toggleBcalcFleetDisable('atk', '${f.id}', this.checked)" title="Check to Disable Fleet" style="cursor: pointer;">
          </div>
        </th>
      `;
    });

    html += `
            <th style="color: #f87171; background: rgba(239, 68, 68, 0.1);">Total</th>
            <th style="color: #f87171; background: rgba(239, 68, 68, 0.15);">Killed</th>
            <th style="color: #b388ff; background: rgba(179,136,255,0.15);">EMPed</th>
          </tr>
        </thead>
        <tbody>
    `;

    // Map categories to Planetarion 2-letter abbreviation
    function getAbbr(cat) {
      const c = (cat || '').toUpperCase();
      if (c === 'FIGHTER') return 'Fi';
      if (c === 'CORVETTE') return 'Co';
      if (c === 'FRIGATE') return 'Fr';
      if (c === 'DESTROYER') return 'De';
      if (c === 'CRUISER') return 'Cr';
      if (c === 'BATTLESHIP') return 'Bs';
      if (c === 'PDS') return 'PDS';
      return 'Sh';
    }

    // Combine ships and PDS items for matrix rows
    const allRows = [];
    filteredShips.forEach(s => allRows.push({ isPds: false, data: s }));
    if (showPds) {
      pdsStructures.forEach(p => allRows.push({ isPds: true, data: p }));
    }

    allRows.forEach(rowItem => {
      const isPds = rowItem.isPds;
      const s = rowItem.data;
      const shipId = s.id;
      const shipName = s.name;
      const shipCat = s.category || s.shipClass || s.cat || 'Ship';
      const abbr = getAbbr(shipCat);

      // DEFENDER SIDE ROW
      let defTotalRow = 0;
      let defRowInputsHtml = '';
      defFleets.forEach((f, idx) => {
        let cnt = 0;
        if (isPds) {
          // PDS only applies if enabled
          const chk = document.getElementById(s.chkId);
          const lvl = document.getElementById(s.lvlId);
          cnt = (chk && chk.checked) ? (parseInt(lvl?.value, 10) || 0) : 0;
        } else {
          cnt = f.ships[shipId] || 0;
        }
        if (f.enabled) defTotalRow += cnt;
        const colClass = (idx % 2 === 0) ? 'def-col-even' : 'def-col-odd';
        const hasShipsClass = cnt > 0 ? 'has-ships' : 'zero-ships';

        defRowInputsHtml += `
          <td class="bcalc-def-col ${colClass}" style="text-align: center;">
            ${isPds 
              ? `<span style="font-family: var(--font-mono); color: #ffd54f; font-weight: ${cnt > 0 ? '700' : '400'};">${cnt > 0 ? 'Lvl ' + cnt : '-'}</span>`
              : `<input type="text" inputmode="numeric" class="bcalc-cell-input ${hasShipsClass}" value="${cnt > 0 ? cnt.toLocaleString() : '0'}" placeholder="0" title="${cnt > 0 ? cnt.toLocaleString() + ' ships' : '0 ships'}" onfocus="this.value = (parseShipCount(this.value) > 0 ? parseShipCount(this.value) : ''); this.select();" oninput="autoResizeBcalcInput(this)" onblur="const c = parseShipCount(this.value); this.value = c > 0 ? c.toLocaleString() : '0'; onBcalcShipCountChange('def', '${f.id}', '${shipId}', c);" onchange="onBcalcShipCountChange('def', '${f.id}', '${shipId}', this.value)" ${getBcalcInputWidthStyle(cnt)}>`
            }
          </td>
        `;
      });

      // Defender result stats (if simulated)
      let defKilled = 0;
      let defEmped = 0;
      if (lastSimResult && lastSimResult.defender) {
        defKilled = lastSimResult.defender.lostCounts[shipId] || 0;
        defEmped = (lastSimResult.roundDetails || []).reduce((sum, rd) => {
          return sum + (rd.actions || []).filter(a => a.targetSide === 'defender' && a.targetShipGroup && a.targetShipGroup.includes(shipName)).reduce((s2, act) => s2 + (act.shipsEmped || 0), 0);
        }, 0);
      }

      // ATTACKER SIDE ROW
      let atkTotalRow = 0;
      let atkRowInputsHtml = '';
      atkFleets.forEach((f, idx) => {
        const cnt = isPds ? 0 : (f.ships[shipId] || 0);
        if (f.enabled) atkTotalRow += cnt;
        const colClass = (idx % 2 === 0) ? 'atk-col-even' : 'atk-col-odd';
        const hasShipsClass = cnt > 0 ? 'has-ships' : 'zero-ships';

        atkRowInputsHtml += `
          <td class="bcalc-atk-col ${colClass}" style="text-align: center;">
            ${isPds 
              ? `<span style="color: var(--text-dim);">-</span>`
              : `<input type="text" inputmode="numeric" class="bcalc-cell-input ${hasShipsClass}" value="${cnt > 0 ? cnt.toLocaleString() : '0'}" placeholder="0" title="${cnt > 0 ? cnt.toLocaleString() + ' ships' : '0 ships'}" onfocus="this.value = (parseShipCount(this.value) > 0 ? parseShipCount(this.value) : ''); this.select();" oninput="autoResizeBcalcInput(this)" onblur="const c = parseShipCount(this.value); this.value = c > 0 ? c.toLocaleString() : '0'; onBcalcShipCountChange('atk', '${f.id}', '${shipId}', c);" onchange="onBcalcShipCountChange('atk', '${f.id}', '${shipId}', this.value)" ${getBcalcInputWidthStyle(cnt)}>`
            }
          </td>
        `;
      });

      // Attacker result stats (if simulated)
      let atkKilled = 0;
      let atkEmped = 0;
      if (lastSimResult && lastSimResult.attacker) {
        atkKilled = lastSimResult.attacker.lostCounts[shipId] || 0;
        atkEmped = (lastSimResult.roundDetails || []).reduce((sum, rd) => {
          return sum + (rd.actions || []).filter(a => a.targetSide === 'attacker' && a.targetShipGroup && a.targetShipGroup.includes(shipName)).reduce((s2, act) => s2 + (act.shipsEmped || 0), 0);
        }, 0);
      }

      html += `
        <tr style="border-bottom: 1px solid rgba(255,255,255,0.04);">
          <!-- Defender Details -->
          <td class="ship-name-cell" style="color: ${isPds ? '#ffd54f' : '#fff'};">
            ${isPds ? '🛡️ ' : ''}${escapeHtml(shipName)}
          </td>
          <td style="text-align: center; color: var(--text-dim); font-size: 0.72rem;">(${abbr})</td>
          ${defRowInputsHtml}
          <td style="font-weight: 700; color: #38bdf8;">${defTotalRow.toLocaleString()}</td>
          <td style="color: ${defKilled > 0 ? '#f87171' : 'var(--text-dim)'}; font-weight: ${defKilled > 0 ? '700' : '400'};">${defKilled.toLocaleString()}</td>
          <td style="color: ${defEmped > 0 ? '#b388ff' : 'var(--text-dim)'};" class="bcalc-side-divider">${defEmped.toLocaleString()}</td>

          <!-- Attacker Details -->
          <td class="ship-name-cell" style="color: ${isPds ? 'var(--text-dim)' : '#fff'};">
            ${escapeHtml(shipName)}
          </td>
          <td style="text-align: center; color: var(--text-dim); font-size: 0.72rem;">(${abbr})</td>
          ${atkRowInputsHtml}
          <td style="font-weight: 700; color: #f87171;">${atkTotalRow.toLocaleString()}</td>
          <td style="color: ${atkKilled > 0 ? '#f87171' : 'var(--text-dim)'}; font-weight: ${atkKilled > 0 ? '700' : '400'};">${atkKilled.toLocaleString()}</td>
          <td style="color: ${atkEmped > 0 ? '#b388ff' : 'var(--text-dim)'};">${atkEmped.toLocaleString()}</td>
        </tr>
      `;
    });

    html += `
        </tbody>
      </table>
    `;

    container.innerHTML = html;

    // Update bottom scan coordinates reference & ship totals
    const bottomCoords = document.getElementById('sim-bcalc-bottom-coords');
    if (bottomCoords && !bottomCoords.value) {
      const anyCoord = (simDefenderFleets.find(f => f.coords)?.coords) || (simAttackerFleets.find(f => f.coords)?.coords) || simEnteredCoordsDef || simEnteredCoordsAtk || '';
      if (anyCoord) bottomCoords.value = anyCoord;
    }
    const defShipTotal = simDefenderFleets.reduce((acc, f) => acc + (f.enabled ? getFleetShipCount(f) : 0), 0);
    const atkShipTotal = simAttackerFleets.reduce((acc, f) => acc + (f.enabled ? getFleetShipCount(f) : 0), 0);
    const bDefCount = document.getElementById('sim-bcalc-bottom-def-count');
    if (bDefCount) bDefCount.textContent = defShipTotal.toLocaleString();
    const bAtkCount = document.getElementById('sim-bcalc-bottom-atk-count');
    if (bAtkCount) bAtkCount.textContent = atkShipTotal.toLocaleString();
  }


  function buildFleetCardElement(fleet, side, idx) {
    const card = document.createElement('div');
    card.id = `fleet-card-${fleet.id}`;
    card.style.background = fleet.enabled ? 'rgba(255,255,255,0.03)' : 'rgba(0,0,0,0.3)';
    card.style.border = `1px solid ${fleet.enabled ? (side === 'atk' ? 'rgba(239, 68, 68, 0.4)' : 'rgba(56, 189, 248, 0.4)') : 'rgba(255,255,255,0.06)'}`;
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

    // Coords Input Field
    const coordsInput = document.createElement('input');
    coordsInput.id = `fleet-coords-${fleet.id}`;
    coordsInput.type = 'text';
    coordsInput.className = 'form-control';
    coordsInput.placeholder = 'Coords (e.g. 12:1:5)';
    coordsInput.value = fleet.coords || '';
    coordsInput.style.width = '115px';
    coordsInput.style.fontSize = '0.78rem';
    coordsInput.style.fontFamily = 'var(--font-mono)';
    coordsInput.style.padding = '0.2rem 0.4rem';
    coordsInput.title = 'Fleet origin/destination coordinates';
    coordsInput.onchange = (e) => onFleetCoordsChange(side, fleet.id, e.target.value);

    const delBtn = document.createElement('button');
    delBtn.className = 'btn-refresh';
    delBtn.innerHTML = '🗑️ Remove';
    delBtn.style.color = '#ff5252';
    delBtn.style.fontSize = '0.78rem';
    delBtn.style.padding = '0.2rem 0.5rem';
    delBtn.onclick = () => removeFleet(side, fleet.id);

    header.appendChild(toggleLabel);
    header.appendChild(nameInput);
    header.appendChild(coordsInput);
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

    const myHangar = (simAttackerData && simAttackerData.hangarShips && Object.keys(simAttackerData.hangarShips).length > 0)
      ? simAttackerData.hangarShips
      : (homeDefenseData ? (homeDefenseData.hangarShips || homeDefenseData.garrisonShips) : {});
    const hangarTotal = Object.values(myHangar || {}).reduce((a, b) => a + (parseInt(b, 10) || 0), 0);
    const hangarOpt = document.createElement('option');
    hangarOpt.value = '__hangar__';
    hangarOpt.textContent = `🏠 Base Garrison / Docked at Base (${hangarTotal.toLocaleString()} ships)`;
    if (currentVal === '__hangar__' || currentVal === '__my_hangar__' || currentVal === '__home_hangar__') hangarOpt.selected = true;
    empireGrp.appendChild(hangarOpt);

    const myFleets = (simAttackerData && simAttackerData.namedFleets) ? simAttackerData.namedFleets : [];
    myFleets.forEach((f, idx) => {
      const fTotal = Object.values(f.ships || {}).reduce((a, b) => a + (parseInt(b, 10) || 0), 0);
      const opt = document.createElement('option');
      opt.value = `fleet_${idx}`;
      const isDocked = (f.status === 'DOCKED');
      const statusLabel = isDocked ? '⚓ Docked' : (f.status || 'Active');
      opt.textContent = `🚀 Fleet "${f.name || 'Unnamed'}" (${fTotal.toLocaleString()} ships) [${statusLabel}]`;
      if (currentVal === opt.value) opt.selected = true;
      empireGrp.appendChild(opt);
    });

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

        const gShips = t.garrisonShips || {};
        const gTotal = Object.values(gShips).reduce((a, b) => a + (parseInt(b, 10) || 0), 0);
        const namedFleets = t.namedFleets || [];

        // Consolidated option
        if (namedFleets.length > 0 && gTotal > 0) {
          const allTotal = gTotal + namedFleets.reduce((acc, nf) => acc + Object.values(nf.ships || {}).reduce((a, b) => a + (parseInt(b, 10) || 0), 0), 0);
          const cOpt = document.createElement('option');
          cOpt.value = `scan_${tIdx}_consolidated`;
          cOpt.textContent = `⚡ All Consolidated (${allTotal.toLocaleString()} ships)`;
          if (currentVal === cOpt.value) cOpt.selected = true;
          scanGrp.appendChild(cOpt);
        }

        // Planet garrison / docked ships
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
      countInput.type = 'text';
      countInput.inputMode = 'numeric';
      countInput.className = 'form-control';
      countInput.value = count > 0 ? Number(count).toLocaleString() : '';
      countInput.placeholder = '0';
      countInput.style.width = '96px';
      countInput.style.fontSize = '0.8rem';
      countInput.style.padding = '0.2rem 0.4rem';
      countInput.title = `${Number(count).toLocaleString()} ships`;

      sel.onchange = () => {
        const newId = sel.value;
        const cnt = parseShipCount(countInput.value) || 1;
        onShipRowChange(side, fleet.id, shipId, newId, cnt);
      };

      countInput.onfocus = () => {
        const raw = parseShipCount(countInput.value);
        countInput.value = raw > 0 ? raw : '';
        countInput.select();
      };

      countInput.oninput = () => {
        const cnt = parseShipCount(countInput.value);
        onShipRowChange(side, fleet.id, shipId, sel.value, cnt);
      };

      countInput.onblur = () => {
        const cnt = parseShipCount(countInput.value);
        countInput.value = cnt > 0 ? cnt.toLocaleString() : '';
        countInput.title = `${cnt.toLocaleString()} ships`;
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

    const totalShips = Object.values(fleet.ships || {}).reduce((a, b) => a + (parseShipCount(b) || 0), 0);
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

  function checkFriendlyFireConflict() {
    const conflicts = [];
    const defHasOwn = simDefenderFleets.some(f => f.enabled && (
      f.name.includes('Base Garrison') || f.name.includes('Own Fleet') || f.name.includes('🏠') || (f.sourceVal && f.sourceVal.includes('hangar')) || (f.sourceVal && f.sourceVal.startsWith('fleet_'))
    ));
    const atkHasOwn = simAttackerFleets.some(f => f.enabled && (
      f.name.includes('Base Garrison') || f.name.includes('Own Fleet') || f.name.includes('🏠') || (f.sourceVal && f.sourceVal.includes('hangar')) || (f.sourceVal && f.sourceVal.startsWith('fleet_'))
    ));
    if (defHasOwn && atkHasOwn) {
      conflicts.push("Your own Empire forces are assigned to BOTH Attacker and Defender sides.");
    }
    const defAlly = simDefenderFleets.some(f => f.enabled && (f.name.includes('Ally') || f.name.includes('🤝')));
    const atkAlly = simAttackerFleets.some(f => f.enabled && (f.name.includes('Ally') || f.name.includes('🤝')));
    if (defAlly && atkAlly) {
      conflicts.push("Allied coalition fleets are assigned to BOTH sides against each other.");
    }
    if ((defHasOwn && atkAlly) || (atkHasOwn && defAlly)) {
      conflicts.push("Your own Empire forces are pitted directly against Allied forces.");
    }
    return conflicts;
  }

  async function runBattleSimulation() {
    const statusBadge = document.getElementById('combat-status-badge');
    const resultsContainer = document.getElementById('sim-results-container');
    statusBadge.textContent = 'Simulating combat engagements...';
    resultsContainer.style.display = 'none';

    // Friendly fire conflict check
    const ffConflicts = checkFriendlyFireConflict();
    if (ffConflicts.length > 0) {
      const proceed = confirm(
        "⚠️ FRIENDLY FIRE / ALLIANCE CONFLICT WARNING:\n\n" +
        ffConflicts.map(c => `• ${c}`).join('\n') +
        "\n\nPitting friendly forces against each other will calculate mutual casualties and score damage.\n\nDo you want to proceed anyway?"
      );
      if (!proceed) {
        statusBadge.textContent = 'Simulation aborted by user.';
        return;
      }
    }

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
    lastSimResult = res;
    syncWithBcalcMatrix();

    const container = document.getElementById('sim-results-container');
    container.style.display = 'block';

    const isUserDefender = (currentSimMode === 'defense');
    const isAttackerWin = res.outcome === 'attacker';
    const isDefenderWin = res.outcome === 'defender';

    const isUserVictory = (isUserDefender && isDefenderWin) || (!isUserDefender && isAttackerWin);
    const isUserDefeat = (isUserDefender && isAttackerWin) || (!isUserDefender && isDefenderWin);

    const bannerColor = isUserVictory ? 'var(--green)' : (isUserDefeat ? '#ef4444' : '#ffd54f');
    const bannerBg = isUserVictory ? 'rgba(0,255,170,0.08)' : (isUserDefeat ? 'rgba(239,68,68,0.08)' : 'rgba(255,213,79,0.08)');
    const bannerBorder = isUserVictory ? 'rgba(0,255,170,0.3)' : (isUserDefeat ? 'rgba(239,68,68,0.3)' : 'rgba(255,213,79,0.3)');

    let bannerHeadline = res.outcomeDetail;
    if (isUserDefender) {
      if (isDefenderWin) {
        bannerHeadline = 'HOME BASE DEFENSE VICTORIOUS! Planetary Garrison Repelled the Invaders';
      } else if (isAttackerWin) {
        bannerHeadline = 'PLANETARY DEFENSE BREACHED! Invading Fleet Overwhelmed Garrison';
      }
    } else {
      if (isAttackerWin) {
        bannerHeadline = 'PLANETARY ASSAULT VICTORIOUS! Your Attacking Forces Overwhelmed the Defense';
      } else if (isDefenderWin) {
        bannerHeadline = 'PLANETARY ASSAULT REPELLED! Enemy Defenses Repelled Your Forces';
      }
    }

    // Build classic Planetarion "Report of Losses from [Fleet]" sections
    let bcalcLossReportsHtml = '';
    const defFleetsList = (res.defender && res.defender.fleets) ? res.defender.fleets : [];
    const atkFleetsList = (res.attacker && res.attacker.fleets) ? res.attacker.fleets : [];

    defFleetsList.forEach(df => {
      const start = df.startCounts || {};
      const lost = df.lostCounts || {};
      const survived = df.survivedCounts || {};
      const rows = Object.keys(start).map(uId => {
        const uName = (typeof refData !== 'undefined' && refData?.ships)
          ? (refData.ships.find(s => s.id === uId)?.name || uId.replace('main-', '').replace(/-/g, ' '))
          : uId.replace('main-', '').replace(/-/g, ' ');
        const aCount = start[uId] || 0;
        const lCount = lost[uId] || 0;
        const sCount = survived[uId] || (aCount - lCount);
        return `<tr><td>${escapeHtml(uName)}</td><td>${aCount.toLocaleString()}</td><td style="color: ${lCount > 0 ? '#f87171' : 'var(--text-dim)'}; font-weight: 600;">${lCount.toLocaleString()}</td><td style="color: var(--green);">${sCount.toLocaleString()}</td></tr>`;
      }).join('');

      bcalcLossReportsHtml += `
        <div class="bcalc-report-panel" style="border-left: 3px solid #38bdf8;">
          <div style="font-weight: 700; color: #38bdf8; font-size: 0.85rem;">
            Report of Losses from ${escapeHtml(df.name)} ${df.isPds ? '(Planet Base Defenses)' : '(Defender)'}
          </div>
          <table class="bcalc-report-table">
            <thead>
              <tr><th>Ship / Structure</th><th>Arrived</th><th>Lost</th><th>Survivors</th></tr>
            </thead>
            <tbody>
              ${rows || '<tr><td colspan="4" style="color: var(--text-dim); text-align: center;">No ships deployed in fleet.</td></tr>'}
            </tbody>
          </table>
        </div>
      `;
    });

    atkFleetsList.forEach(af => {
      const start = af.startCounts || {};
      const lost = af.lostCounts || {};
      const survived = af.survivedCounts || {};
      const rows = Object.keys(start).map(uId => {
        const uName = (typeof refData !== 'undefined' && refData?.ships)
          ? (refData.ships.find(s => s.id === uId)?.name || uId.replace('main-', '').replace(/-/g, ' '))
          : uId.replace('main-', '').replace(/-/g, ' ');
        const aCount = start[uId] || 0;
        const lCount = lost[uId] || 0;
        const sCount = survived[uId] || (aCount - lCount);
        return `<tr><td>${escapeHtml(uName)}</td><td>${aCount.toLocaleString()}</td><td style="color: ${lCount > 0 ? '#f87171' : 'var(--text-dim)'}; font-weight: 600;">${lCount.toLocaleString()}</td><td style="color: var(--green);">${sCount.toLocaleString()}</td></tr>`;
      }).join('');

      bcalcLossReportsHtml += `
        <div class="bcalc-report-panel" style="border-left: 3px solid #ef4444;">
          <div style="font-weight: 700; color: #f87171; font-size: 0.85rem;">
            Report of Losses from ${escapeHtml(af.name)} (Attacker)
          </div>
          <table class="bcalc-report-table">
            <thead>
              <tr><th>Ship</th><th>Arrived</th><th>Lost</th><th>Survivors</th></tr>
            </thead>
            <tbody>
              ${rows || '<tr><td colspan="4" style="color: var(--text-dim); text-align: center;">No ships deployed in fleet.</td></tr>'}
            </tbody>
          </table>
        </div>
      `;
    });

    let adviceHtml = (res.tacticalAdvice || []).map(a => `<div style="margin-bottom: 0.35rem;">${escapeHtml(a)}</div>`).join('');

    // Per-Fleet Score Dynamics and Ship Values
    const atkFleetsRes = (res.attacker && res.attacker.fleets) ? res.attacker.fleets : [];
    const defFleetsRes = (res.defender && res.defender.fleets) ? res.defender.fleets : [];

    let defTotalValStart = 0, defTotalScoreStart = 0, defTotalValLost = 0, defTotalScoreLost = 0;
    let atkTotalValStart = 0, atkTotalScoreStart = 0, atkTotalValLost = 0, atkTotalScoreLost = 0;

    defFleetsRes.forEach(f => {
      defTotalValStart += f.valueStart?.total || 0;
      defTotalScoreStart += f.scoreStart || 0;
      defTotalValLost += f.valueLost?.total || 0;
      defTotalScoreLost += f.scoreLost || 0;
    });
    atkFleetsRes.forEach(f => {
      atkTotalValStart += f.valueStart?.total || 0;
      atkTotalScoreStart += f.scoreStart || 0;
      atkTotalValLost += f.valueLost?.total || 0;
      atkTotalScoreLost += f.scoreLost || 0;
    });

    // Individual Fleet Score Dynamics Table Rows
    let perFleetScoreDynamicsRowsHtml = '';
    const allCombatFleets = [...defFleetsRes, ...atkFleetsRes];
    allCombatFleets.forEach(f => {
      const isDef = (f.side === 'def');
      const sideColor = isDef ? '#38bdf8' : '#f87171';
      const sideBadge = f.isPds ? '🛡️ PDS' : (isDef ? '🛡️ DEF' : '🚀 ATK');
      const valStart = f.valueStart?.total || 0;
      const valLost = f.valueLost?.total || 0;
      const valSurv = f.valueSurvived?.total || 0;
      const scStart = f.scoreStart || Math.round(valStart / 9);
      const scLost = f.scoreLost || Math.round(valLost / 9);
      const scSurv = f.scoreSurvived || Math.round(valSurv / 9);

      perFleetScoreDynamicsRowsHtml += `
        <tr style="border-bottom: 1px solid rgba(255,255,255,0.05);">
          <td style="padding: 0.5rem 0.75rem; font-weight: 600; color: #fff;">${escapeHtml(f.name)}</td>
          <td style="padding: 0.5rem 0.75rem; text-align: center; color: ${sideColor}; font-weight: 700;">${sideBadge}</td>
          <td style="padding: 0.5rem 0.75rem; text-align: right; color: #cbd5e1;">${valStart.toLocaleString()}</td>
          <td style="padding: 0.5rem 0.75rem; text-align: right; color: #a5b4fc; font-weight: 600;">${scStart.toLocaleString()} pts</td>
          <td style="padding: 0.5rem 0.75rem; text-align: right; color: ${f.totalLost > 0 ? '#f87171' : 'var(--text-dim)'}; font-weight: 600;">-${f.totalLost.toLocaleString()}</td>
          <td style="padding: 0.5rem 0.75rem; text-align: right; color: ${valLost > 0 ? '#f87171' : 'var(--text-dim)'};">-${valLost.toLocaleString()}</td>
          <td style="padding: 0.5rem 0.75rem; text-align: right; color: ${scLost > 0 ? '#f87171' : 'var(--text-dim)'}; font-weight: 700;">-${scLost.toLocaleString()} pts</td>
          <td style="padding: 0.5rem 0.75rem; text-align: right; color: #86efac;">${valSurv.toLocaleString()}</td>
          <td style="padding: 0.5rem 0.75rem; text-align: right; font-weight: 700;">${f.lossPercent}%</td>
        </tr>
      `;
    });

    // Side-by-side casualty rows
    let casualtiesHtml = '';
    const allUnitIds = Array.from(new Set([...Object.keys(res.attacker.startCounts), ...Object.keys(res.defender.startCounts)]));

    allUnitIds.forEach(uId => {
      const isAtk = uId in res.attacker.startCounts;
      const sideLabel = isAtk 
        ? '<span style="color: #ef4444; font-weight: 700;">[Attacker]</span>'
        : '<span style="color: #38bdf8; font-weight: 700;">[Defender]</span>';
      const sideData = isAtk ? res.attacker : res.defender;
      const start = sideData.startCounts[uId] || 0;
      const lost = sideData.lostCounts[uId] || 0;
      const survived = sideData.survivedCounts[uId] || 0;

      casualtiesHtml += `
        <tr style="border-bottom: 1px solid rgba(255,255,255,0.04);">
          <td style="padding: 0.5rem 0.75rem;">${sideLabel} <strong>${escapeHtml(uId.replace('main-', '').replace(/-/g, ' '))}</strong></td>
          <td style="padding: 0.5rem 0.75rem; text-align: center;">${start.toLocaleString()}</td>
          <td style="padding: 0.5rem 0.75rem; text-align: center; color: ${lost > 0 ? '#f87171' : 'var(--text-dim)'}; font-weight: 600;">-${lost.toLocaleString()}</td>
          <td style="padding: 0.5rem 0.75rem; text-align: center; color: var(--green); font-weight: 600;">${survived.toLocaleString()}</td>
        </tr>
      `;
    });

    // Round replay accordion
    let roundsLogHtml = '';
    (res.roundDetails || []).forEach(rd => {
      const events = (rd.events || []).map(e => {
        let color = '#cbd5e1';
        if (e.startsWith('🛡️ DEFENDER') || e.includes('[Defender]')) {
          color = '#38bdf8';
        } else if (e.startsWith('🚀 ATTACKER') || e.includes('[Attacker]')) {
          color = '#f87171';
        } else if (e.includes('Shield Aura') || e.includes('Planetary Shield')) {
          color = '#80d8ff';
        } else if (e.includes('Siege Barrier')) {
          color = '#ffd54f';
        } else if (e.includes('Disruption Field') || e.includes('EMP')) {
          color = '#b388ff';
        } else if (e.includes('destroyed')) {
          color = '#fca5a5';
        }
        return `<li style="margin-bottom: 0.35rem; color: ${color}; line-height: 1.4;">${escapeHtml(e)}</li>`;
      }).join('');

      const killsCount = (rd.actions || []).reduce((sum, a) => sum + (a.shipsDestroyed || 0), 0);
      const empCount = (rd.actions || []).reduce((sum, a) => sum + (a.shipsEmped || 0), 0);

      roundsLogHtml += `
        <details open style="background: rgba(0,0,0,0.3); border: 1px solid rgba(255,255,255,0.07); border-radius: 6px; padding: 0.75rem;">
          <summary style="font-weight: 700; color: #fff; cursor: pointer; display: flex; justify-content: space-between; align-items: center; user-select: none;">
            <span>⚔️ Combat Round ${rd.roundNumber}</span>
            <span style="font-size: 0.75rem; font-family: var(--font-mono); color: var(--text-dim);">
              ${killsCount > 0 ? `<span style="color: #f87171; margin-right: 0.5rem;">${killsCount.toLocaleString()} destroyed</span>` : ''}
              ${empCount > 0 ? `<span style="color: #b388ff; margin-right: 0.5rem;">${empCount.toLocaleString()} EMP disabled</span>` : ''}
              <span>Shield: ${rd.shieldRemainingHP ? rd.shieldRemainingHP.toLocaleString() + ' HP' : '0 HP'}</span>
            </span>
          </summary>
          <div style="margin-top: 0.75rem; max-height: 260px; overflow-y: auto; padding-right: 0.35rem;">
            <ul style="margin: 0; padding-left: 1.25rem; font-family: var(--font-mono); font-size: 0.8rem;">
              ${events || '<li style="color: var(--text-dim);">No significant damage dealt.</li>'}
            </ul>
          </div>
        </details>
      `;
    });

    const roidsStolen = res.asteroidsStolen || { metalRoids: 0, crystalRoids: 0, eoniumRoids: 0, total: 0 };
    const scoreChange = res.scoreChange || { attacker: 0, defender: 0 };
    const atkScoreClass = scoreChange.attacker >= 0 ? 'var(--green)' : '#ef4444';
    const atkScoreSign = scoreChange.attacker >= 0 ? '+' : '';
    const defScoreClass = scoreChange.defender >= 0 ? 'var(--green)' : '#ef4444';
    const defScoreSign = scoreChange.defender >= 0 ? '+' : '';

    const atkDominancePct = Math.round(res.dominance * 100);
    const defDominancePct = 100 - atkDominancePct;

    let dominanceLabel = '';
    let dominanceSideColor = '';
    let dominanceBadge = '';
    if (atkDominancePct > defDominancePct) {
      dominanceLabel = `🚀 Attacking Dominance: ${atkDominancePct}% (${!isUserDefender ? 'Your Advantage' : 'Enemy Advantage'})`;
      dominanceSideColor = '#ef4444';
      dominanceBadge = `<span class="badge" style="background: rgba(239,68,68,0.18); color: #f87171; border: 1px solid #ef4444; font-size: 0.88rem; padding: 0.3rem 0.8rem; font-weight: 700;">🚀 Attacking Dominance: ${atkDominancePct}%</span>`;
    } else if (defDominancePct > atkDominancePct) {
      dominanceLabel = `🛡️ Defending Dominance: ${defDominancePct}% (${isUserDefender ? 'Your Advantage' : 'Enemy Advantage'})`;
      dominanceSideColor = '#38bdf8';
      dominanceBadge = `<span class="badge" style="background: rgba(56,189,248,0.18); color: #38bdf8; border: 1px solid #38bdf8; font-size: 0.88rem; padding: 0.3rem 0.8rem; font-weight: 700;">🛡️ Defending Dominance: ${defDominancePct}%</span>`;
    } else {
      dominanceLabel = `⚖️ Contested Combat: 50% / 50%`;
      dominanceSideColor = '#ffd54f';
      dominanceBadge = `<span class="badge" style="background: rgba(255,213,79,0.18); color: #ffd54f; border: 1px solid #ffd54f; font-size: 0.88rem; padding: 0.3rem 0.8rem; font-weight: 700;">⚖️ Contested: 50% / 50%</span>`;
    }

    const userPerspectiveTag = isUserDefender
      ? `<span class="badge" style="background: rgba(56,189,248,0.15); color: #38bdf8; border: 1px solid rgba(56,189,248,0.4); font-size: 0.82rem; padding: 0.28rem 0.65rem;">👤 Your Role: 🛡️ Home Base Defender (Left Side)</span>`
      : `<span class="badge" style="background: rgba(239,68,68,0.15); color: #f87171; border: 1px solid rgba(239,68,68,0.4); font-size: 0.82rem; padding: 0.28rem 0.65rem;">👤 Your Role: 🚀 Coalition Attacker (Right Side)</span>`;

    const salvScoreEquiv = Math.round((res.salvage?.total || 0) / 9);

    container.innerHTML = `
      <!-- OUTCOME BANNER -->
      <div style="background: ${bannerBg}; border: 1px solid ${bannerBorder}; border-radius: 8px; padding: 1.5rem; margin-bottom: 1.5rem; text-align: center;">
        <div style="font-size: 1.6rem; font-weight: 900; color: ${bannerColor}; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 0.6rem;">
          ${isUserVictory ? '🏆 ' : (isUserDefeat ? '💀 ' : '⚖️ ')}${escapeHtml(bannerHeadline)}
        </div>
        <div style="display: flex; justify-content: center; gap: 0.6rem; align-items: center; flex-wrap: wrap; margin-bottom: 0.75rem;">
          ${userPerspectiveTag}
          ${dominanceBadge}
        </div>
        <div style="font-family: var(--font-mono); font-size: 0.92rem; color: var(--text-dim); margin-bottom: 1rem;">
          Simulation concluded after <strong>${res.rounds}</strong> combat round(s). Tactical verdict: <strong style="color: ${dominanceSideColor};">${dominanceLabel}</strong>
        </div>

        <!-- DOMINANCE BAR GAUGE -->
        <div style="max-width: 620px; margin: 0 auto;">
          <div style="height: 12px; background: rgba(255,255,255,0.08); border-radius: 6px; overflow: hidden; display: flex;">
            <div style="height: 100%; width: ${defDominancePct}%; background: linear-gradient(90deg, #0284c7 0%, #38bdf8 100%); transition: width 0.3s;" title="Defender Advantage: ${defDominancePct}%"></div>
            <div style="height: 100%; width: ${atkDominancePct}%; background: linear-gradient(90deg, #dc2626 0%, #ef4444 100%); transition: width 0.3s;" title="Attacker Advantage: ${atkDominancePct}%"></div>
          </div>
          <div style="display: flex; justify-content: space-between; margin-top: 0.4rem; font-family: var(--font-mono); font-size: 0.8rem;">
            <span style="color: #38bdf8; font-weight: 700;">
              🛡️ Defender ${isUserDefender ? '(You)' : '(Enemy)'}: ${defDominancePct}%
            </span>
            <span style="color: #ef4444; font-weight: 700;">
              🚀 Attacker ${!isUserDefender ? '(You)' : '(Enemy)'}: ${atkDominancePct}%
            </span>
          </div>
        </div>
      </div>

      <!-- 6-CARD BALANCE METRICS STRIP -->
      <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 1rem; margin-bottom: 1.5rem;">
        <div class="panel" style="padding: 1rem; text-align: center; border-left: 3px solid #38bdf8;">
          <div style="font-size: 0.78rem; color: #38bdf8; text-transform: uppercase; font-weight: 700;">🛡️ Defender Losses ${isUserDefender ? '(You)' : '(Enemy)'}</div>
          <div style="font-size: 1.3rem; font-weight: 800; color: ${res.defender.totalLost > 0 ? (isUserDefender ? '#f87171' : 'var(--green)') : 'var(--text-dim)'}; margin: 0.25rem 0;">
            ${res.defender.totalLost.toLocaleString()} ships (${res.defender.lossPercent}%)
          </div>
          <div style="font-size: 0.78rem; color: var(--text-dim); font-family: var(--font-mono);">
            -${(res.defender.valueLost?.total || 0).toLocaleString()} net value
          </div>
        </div>

        <div class="panel" style="padding: 1rem; text-align: center; border-left: 3px solid #ef4444;">
          <div style="font-size: 0.78rem; color: #f87171; text-transform: uppercase; font-weight: 700;">🚀 Attacker Losses ${!isUserDefender ? '(You)' : '(Enemy)'}</div>
          <div style="font-size: 1.3rem; font-weight: 800; color: ${res.attacker.totalLost > 0 ? (!isUserDefender ? '#f87171' : 'var(--green)') : 'var(--text-dim)'}; margin: 0.25rem 0;">
            ${res.attacker.totalLost.toLocaleString()} ships (${res.attacker.lossPercent}%)
          </div>
          <div style="font-size: 0.78rem; color: var(--text-dim); font-family: var(--font-mono);">
            -${(res.attacker.valueLost?.total || 0).toLocaleString()} net value
          </div>
        </div>

        <div class="panel" style="padding: 1rem; text-align: center;">
          <div style="font-size: 0.78rem; color: var(--text-dim); text-transform: uppercase;">Projected Salvage</div>
          <div style="font-size: 1.3rem; font-weight: 800; color: var(--cyan); margin: 0.25rem 0;">
            +${(res.salvage?.total || 0).toLocaleString()}
          </div>
          <div style="font-size: 0.78rem; color: var(--text-dim); font-family: var(--font-mono);">
            ${(res.salvage?.metal || 0).toLocaleString()} M • ${(res.salvage?.crystal || 0).toLocaleString()} C • ${(res.salvage?.eonium || 0).toLocaleString()} E
          </div>
        </div>

        <div class="panel" style="padding: 1rem; text-align: center;">
          <div style="font-size: 0.78rem; color: var(--text-dim); text-transform: uppercase;">Estimated Plunder</div>
          <div style="font-size: 1.3rem; font-weight: 800; color: var(--yellow); margin: 0.25rem 0;">
            ${(res.plunder?.total || 0).toLocaleString()}
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

      <!-- MATRIX MODE LOSS REPORTS BY FLEET -->
      <div class="panel" style="margin-bottom: 1.5rem; border-top: 3px solid #f59e0b;">
        <div class="panel-header">
          <div class="panel-title" style="color: #f59e0b;">📊 Matrix Mode Reports by Fleet</div>
          <span class="badge" style="background: rgba(245, 158, 11, 0.15); color: #f59e0b;">Loss Report Format</span>
        </div>
        <div style="font-size: 0.8rem; color: var(--text-dim); margin-bottom: 0.75rem;">
          Individual fleet casualty breakdown reports matching the combat matrix engine.
        </div>
        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 1rem;">
          ${bcalcLossReportsHtml || '<div style="color: var(--text-dim); padding: 1rem;">No fleet reports available.</div>'}
        </div>
      </div>

      <!-- PROJECTED SCORE DYNAMICS & SHIP VALUE IMPACT (PER INDIVIDUAL FLEET) -->
      <div class="panel" style="margin-bottom: 1.5rem; background: rgba(0,0,0,0.3); border: 1px solid rgba(255,255,255,0.08); border-radius: 8px; padding: 1rem;">
        <div class="panel-header" style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.85rem; flex-wrap: wrap; gap: 0.5rem;">
          <div class="panel-title" style="font-family: var(--font-mono); font-weight: 800; font-size: 0.95rem; color: #ffd54f;">
            📈 Projected Score Dynamics & Ship Value Impact (Official pg: Res/9 Formula)
          </div>
          <span class="badge" style="background: rgba(255,213,79,0.15); color: #ffd54f; border: 1px solid rgba(255,213,79,0.4); font-size: 0.72rem;">
            Per-Fleet Impact Breakdown
          </span>
        </div>

        <!-- High-Level Score Impact Strip -->
        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 0.75rem; margin-bottom: 1rem; font-family: var(--font-mono);">
          <div style="background: rgba(56, 189, 248, 0.07); border-left: 3px solid #38bdf8; border-radius: 4px; padding: 0.6rem 0.8rem;">
            <div style="font-size: 0.75rem; color: #38bdf8; text-transform: uppercase; font-weight: 700;">🛡️ Defender Total Impact</div>
            <div style="font-size: 1.15rem; font-weight: 900; color: #f87171; margin: 0.15rem 0;">-${defTotalScoreLost.toLocaleString()} pts</div>
            <div style="font-size: 0.72rem; color: var(--text-dim);">${defTotalValLost.toLocaleString()} net res value lost</div>
          </div>
          <div style="background: rgba(239, 68, 68, 0.07); border-left: 3px solid #ef4444; border-radius: 4px; padding: 0.6rem 0.8rem;">
            <div style="font-size: 0.75rem; color: #f87171; text-transform: uppercase; font-weight: 700;">🚀 Attacker Total Impact</div>
            <div style="font-size: 1.15rem; font-weight: 900; color: #f87171; margin: 0.15rem 0;">-${atkTotalScoreLost.toLocaleString()} pts</div>
            <div style="font-size: 0.72rem; color: var(--text-dim);">${atkTotalValLost.toLocaleString()} net res value lost</div>
          </div>
          <div style="background: rgba(16, 185, 129, 0.07); border-left: 3px solid #10b981; border-radius: 4px; padding: 0.6rem 0.8rem;">
            <div style="font-size: 0.75rem; color: #10b981; text-transform: uppercase; font-weight: 700;">⚖️ Net Score Differential</div>
            <div style="font-size: 1.15rem; font-weight: 900; color: ${atkTotalScoreLost > defTotalScoreLost ? '#38bdf8' : (defTotalScoreLost > atkTotalScoreLost ? '#f87171' : '#ffd54f')}; margin: 0.15rem 0;">
              ${Math.abs(defTotalScoreLost - atkTotalScoreLost).toLocaleString()} pts Δ
            </div>
            <div style="font-size: 0.72rem; color: var(--text-dim);">${atkTotalScoreLost > defTotalScoreLost ? 'Defender Advantage' : (defTotalScoreLost > atkTotalScoreLost ? 'Attacker Advantage' : 'Parity')}</div>
          </div>
        </div>

        <!-- Per Individual Fleet Breakdown Table -->
        <div style="overflow-x: auto;">
          <table class="bcalc-table" style="font-size: 0.78rem; width: 100%;">
            <thead>
              <tr>
                <th style="text-align: left;">Fleet Roster</th>
                <th style="text-align: center;">Side</th>
                <th style="text-align: right;">Initial Value (M+C+E)</th>
                <th style="text-align: right;">Initial Score</th>
                <th style="text-align: right;">Ships Lost</th>
                <th style="text-align: right;">Value Lost</th>
                <th style="text-align: right;">Score Δ</th>
                <th style="text-align: right;">Surviving Value</th>
                <th style="text-align: right;">Loss %</th>
              </tr>
            </thead>
            <tbody>
              ${perFleetScoreDynamicsRowsHtml || '<tr><td colspan="9" style="text-align: center; padding: 1rem; color: var(--text-dim);">No fleet dynamics data available.</td></tr>'}
            </tbody>
          </table>
        </div>

        <!-- Debris Field Salvage Projection -->
        <div style="padding: 0.75rem 1rem; margin-top: 1rem; background: rgba(56, 189, 248, 0.06); border: 1px solid rgba(56, 189, 248, 0.3); border-radius: 6px; font-family: var(--font-mono); font-size: 0.85rem; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 0.75rem;">
          <span style="font-weight: 700; color: #38bdf8;">♻️ Projected Debris Salvage (30%):</span>
          <div style="display: flex; gap: 1.25rem; flex-wrap: wrap;">
            <span>🔩 Metal: <strong style="color: #cbd5e1;">${(res.salvage?.metal || 0).toLocaleString()}</strong></span>
            <span>💎 Crystal: <strong style="color: #38bdf8;">${(res.salvage?.crystal || 0).toLocaleString()}</strong></span>
            <span>⚡ Eonium: <strong style="color: var(--yellow);">${(res.salvage?.eonium || 0).toLocaleString()}</strong></span>
            <span style="color: #a5b4fc;">(≈ <strong>+${salvScoreEquiv.toLocaleString()} pts</strong> score value)</span>
          </div>
        </div>
      </div>

      <!-- PREDICTED SCORE & ROID THEFT IMPACT BREAKDOWN PANEL -->
      <div class="panel" style="margin-bottom: 1.5rem; background: rgba(187,134,252,0.03); border-left: 4px solid var(--purple);">
        <div class="panel-header" style="margin-bottom: 0.5rem;">
          <div class="panel-title" style="font-size: 0.95rem; color: #d8b4fe;">📈 Projected Empire Score & Asteroid Seizure Breakdown</div>
          <span class="badge" style="background: rgba(187,134,252,0.15); color: #d8b4fe;">Official Formulae Standard</span>
        </div>
        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 1rem; font-size: 0.85rem; font-family: var(--font-mono);">
          <div style="background: rgba(0,0,0,0.25); border-radius: 6px; padding: 0.75rem;">
            <div style="font-weight: 700; color: #38bdf8; margin-bottom: 0.35rem;">🛡️ Defender Score Impact: <span style="color: ${defScoreClass};">${defScoreSign}${scoreChange.defender.toLocaleString()} pts</span></div>
            <div style="color: var(--text-dim); line-height: 1.6; font-size: 0.8rem;">
              • Asteroids Lost: <span style="color: #f87171;">${(scoreChange.defenderBreakdown?.asteroidsPenalty || 0).toLocaleString()} pts</span> (-${roidsStolen.total} × 50 pts)<br>
              • Resources Plundered: <span style="color: #f87171;">${(scoreChange.defenderBreakdown?.plunderPenalty || 0).toLocaleString()} pts</span> (-fromRes / 9)<br>
              • Garrison Salvage Recovery: <span style="color: var(--green);">+${(scoreChange.defenderBreakdown?.salvageBonus || 0).toLocaleString()} pts</span> (30% atk wreck res / 9)
            </div>
          </div>
          <div style="background: rgba(0,0,0,0.25); border-radius: 6px; padding: 0.75rem;">
            <div style="font-weight: 700; color: #f87171; margin-bottom: 0.35rem;">🚀 Attacker Score Impact: <span style="color: ${atkScoreClass};">${atkScoreSign}${scoreChange.attacker.toLocaleString()} pts</span></div>
            <div style="color: var(--text-dim); line-height: 1.6; font-size: 0.8rem;">
              • Asteroids Captured: <span style="color: #69f0ae;">+${(scoreChange.attackerBreakdown?.asteroidsBonus || 0).toLocaleString()} pts</span> (${roidsStolen.total} × 50 pts)<br>
              • Resource Plunder: <span style="color: var(--yellow);">+${(scoreChange.attackerBreakdown?.plunderBonus || 0).toLocaleString()} pts</span> (fromRes / 9)<br>
              • Fleet Salvage Recovery: <span style="color: #38bdf8;">+${(scoreChange.attackerBreakdown?.salvageBonus || 0).toLocaleString()} pts</span> (30% def wreck res / 9)
            </div>
          </div>
        </div>
      </div>

      <!-- TACTICAL ADVICE -->
      <div class="panel" style="margin-bottom: 1.5rem; background: rgba(56,189,248,0.03); border-left: 4px solid #38bdf8;">
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
    print("🌌 PEGASUS GALAXY MCP CONTROL HUB GUI (v0.5)")
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
