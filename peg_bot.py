#!/usr/bin/env python3
"""
Pegasus Galaxy Autonomous Bot Engine (Cross-Platform)
Runs 24/7 on Windows, Linux VPS, or Docker.
Syncs to the 30-minute game ticks and automates colony development.
"""

import argparse
import datetime
import importlib.util
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

# Ensure UTF-8 stdout
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass

from peg_client import PegasusMCPClient, PegasusMCPError

BASE_DIR = Path(__file__).parent.resolve()
DEFAULT_CONFIG_PATH = BASE_DIR / "bot_config.json"
DEFAULT_STRATEGY_PATH = BASE_DIR / "bot_strategy.py"
DEFAULT_LOG_PATH = BASE_DIR / "bot.log"
DEFAULT_STATE_PATH = BASE_DIR / "bot_state.json"


def log_msg(msg: str, log_file: Optional[Path] = None):
    """Prints and appends timestamped message to bot.log."""
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    formatted = f"[{now_str}] {msg}"
    print(formatted, flush=True)
    target = log_file or DEFAULT_LOG_PATH
    try:
        with open(target, "a", encoding="utf-8") as f:
            f.write(formatted + "\n")
    except Exception:
        pass


def load_config(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        log_msg(f"⚠️ Error reading config file {path}: {e}")
        return {}


def save_state(state_data: Dict[str, Any], path: Path = DEFAULT_STATE_PATH):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(state_data, f, indent=2)
    except Exception:
        pass


def load_strategy_module(path: Path):
    """Dynamically loads or reloads bot_strategy.py so changes in GUI take effect instantly."""
    if not path.exists():
        return None
    try:
        spec = importlib.util.spec_from_file_location("bot_strategy", str(path))
        if spec and spec.loader:
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module
    except Exception as e:
        log_msg(f"⚠️ Error loading custom strategy from {path}: {e}")
    return None


class PegasusBot:
    def __init__(
        self,
        config_path: Path = DEFAULT_CONFIG_PATH,
        strategy_path: Path = DEFAULT_STRATEGY_PATH,
        dry_run: bool = False,
    ):
        self.config_path = config_path
        self.strategy_path = strategy_path
        self.dry_run = dry_run
        self.client = PegasusMCPClient()
        self.actions_this_tick = 0
        self.max_actions = 8
        self.last_tick_processed = -1

    def run_tick_cycle(self) -> Dict[str, Any]:
        """Executes one complete automation cycle for the current game tick."""
        config = load_config(self.config_path)
        dry = self.dry_run or config.get("dry_run", False)
        self.max_actions = config.get("max_actions_per_tick", 8)
        self.actions_this_tick = 0
        actions_log = []

        log_msg("=" * 50)
        log_msg("🚀 STARTING TICK EVALUATION CYCLE" + (" [DRY-RUN]" if dry else ""))

        # 1. Fetch Game State
        try:
            state_resp = self.client.get_game_state_summary()
            state = state_resp.get("data", {}) if isinstance(state_resp, dict) else {}
        except Exception as e:
            log_msg(f"❌ Failed to fetch game state: {e}")
            return {"success": False, "error": str(e)}

        tick_num = state.get("tick", 0)
        planet = state.get("planet", {})
        colony_name = planet.get("name", "Colony")
        coords = planet.get("coords", "N/A")
        metal = planet.get("metal", 0)
        crystal = planet.get("crystal", 0)
        eonium = planet.get("eonium", 0)

        log_msg(f"🌌 Colony: {colony_name} ({coords}) • Tick: {tick_num}")
        log_msg(f"📦 Resources: Metal: {metal:,} | Crystal: {crystal:,} | Eonium: {eonium:,}")

        # 2. Auto-Claim Missions
        if config.get("auto_claim_missions", True) and self.actions_this_tick < self.max_actions:
            try:
                missions_resp = self.client.list_missions()
                m_data = missions_resp.get("data", {}) if isinstance(missions_resp, dict) else {}
                completed_count = m_data.get("summary", {}).get("completed", 0)
                if completed_count > 0:
                    log_msg(f"🎁 Found {completed_count} completed mission(s). Claiming rewards...")
                    if not dry:
                        claim_res = self.client.call_tool("claim_missions")
                        self.actions_this_tick += 1
                        act_msg = f"Claimed {completed_count} missions"
                        actions_log.append(act_msg)
                        log_msg(f"✅ {act_msg}")
                    else:
                        log_msg(f"🔍 [Dry-Run] Would call claim_missions ({completed_count} ready)")
                else:
                    log_msg("🎁 Missions check: 0 completed missions pending.")
            except Exception as e:
                log_msg(f"⚠️ Error in auto-claim missions: {e}")

        # 3. Auto-Repair PDS Defenses
        if config.get("auto_repair_pds", True) and self.actions_this_tick < self.max_actions:
            try:
                pds_resp = self.client.call_tool("list_pds")
                pds_list = pds_resp.get("data", []) if isinstance(pds_resp, dict) else []
                damaged = [p for p in pds_list if p.get("damaged")]
                if damaged:
                    for p in damaged:
                        if self.actions_this_tick >= self.max_actions:
                            break
                        c_id = p.get("constructionId")
                        p_name = p.get("name", c_id)
                        log_msg(f"🛡️ Defense damaged: {p_name}. Initiating emergency repair...")
                        if not dry:
                            self.client.call_tool("repair_pds", {"constructionId": c_id})
                            self.actions_this_tick += 1
                            act_msg = f"Repaired {p_name}"
                            actions_log.append(act_msg)
                            log_msg(f"✅ {act_msg}")
                        else:
                            log_msg(f"🔍 [Dry-Run] Would repair {p_name}")
                else:
                    log_msg(f"🛡️ PDS defenses check: All {len(pds_list)} structures healthy.")
            except Exception as e:
                log_msg(f"⚠️ Error checking PDS defenses: {e}")

        # 4. Auto-Construction
        if config.get("auto_construct", True) and self.actions_this_tick < self.max_actions:
            try:
                constructions = state.get("constructions", [])
                active_build = any(c.get("currentlyInProgress") for c in constructions if isinstance(c, dict))
                if active_build:
                    b_name = [c.get("name") for c in constructions if c.get("currentlyInProgress")]
                    log_msg(f"🔨 Construction queue: '{b_name[0] if b_name else 'Upgrade'}' currently in progress (queue busy, will check next tick).")
                else:
                    log_msg("🔨 Construction queue is idle. Checking upgrade priorities...")
                    opts_resp = self.client.list_construction_options()
                    opts = opts_resp.get("data", []) if isinstance(opts_resp, dict) else []
                    priorities = config.get("construction_priorities", [])

                    chosen_build = None
                    for prio_id in priorities:
                        match = next((o for o in opts if o.get("id") == prio_id or o.get("constructionId") == prio_id), None)
                        if match and match.get("canAfford", True):
                            chosen_build = match
                            break

                    if not chosen_build and opts:
                        affordable = [o for o in opts if o.get("canAfford", True)]
                        if affordable:
                            chosen_build = affordable[0]

                    if chosen_build:
                        build_id = chosen_build.get("id") or chosen_build.get("constructionId")
                        build_name = chosen_build.get("name", build_id)
                        log_msg(f"🏗️ Starting construction: {build_name} ({build_id})...")
                        if not dry:
                            self.client.call_tool("build_construction", {"constructionId": build_id})
                            self.actions_this_tick += 1
                            act_msg = f"Started construction: {build_name}"
                            actions_log.append(act_msg)
                            log_msg(f"✅ {act_msg}")
                        else:
                            log_msg(f"🔍 [Dry-Run] Would start {build_name}")
                    else:
                        log_msg("ℹ️ Construction queue: Idle, but no affordable options match priorities.")
            except Exception as e:
                log_msg(f"⚠️ Error in auto-construction: {e}")

        # 5. Auto-Research
        if config.get("auto_research", True) and self.actions_this_tick < self.max_actions:
            try:
                research_list = state.get("research", [])
                active_res = any(r.get("currentlyInProgress") for r in research_list if isinstance(r, dict))
                if active_res:
                    r_name = [r.get("name") for r in research_list if r.get("currentlyInProgress")]
                    log_msg(f"🔬 Research queue: '{r_name[0] if r_name else 'Tech'}' currently in progress (queue busy, will check next tick).")
                else:
                    log_msg("🔬 Research queue is idle. Checking tech priorities...")
                    opts_resp = self.client.list_research_options()
                    opts = opts_resp.get("data", []) if isinstance(opts_resp, dict) else []
                    priorities = config.get("research_priorities", [])

                    chosen_res = None
                    for prio_id in priorities:
                        match = next((o for o in opts if o.get("id") == prio_id or o.get("researchId") == prio_id), None)
                        if match and match.get("canAfford", True):
                            chosen_res = match
                            break

                    if not chosen_res and opts:
                        affordable = [o for o in opts if o.get("canAfford", True)]
                        if affordable:
                            chosen_res = affordable[0]

                    if chosen_res:
                        res_id = chosen_res.get("id") or chosen_res.get("researchId")
                        res_name = chosen_res.get("name", res_id)
                        log_msg(f"🧪 Starting research: {res_name} ({res_id})...")
                        if not dry:
                            self.client.call_tool("start_research", {"researchId": res_id})
                            self.actions_this_tick += 1
                            act_msg = f"Started research: {res_name}"
                            actions_log.append(act_msg)
                            log_msg(f"✅ {act_msg}")
                        else:
                            log_msg(f"🔍 [Dry-Run] Would start research: {res_name}")
                    else:
                        log_msg("ℹ️ Research queue: Idle, but no affordable tech options match priorities.")
            except Exception as e:
                log_msg(f"⚠️ Error in auto-research: {e}")

        # 6. Execute User-Queued Specific Orders
        queued_actions = config.get("queued_actions", [])
        if queued_actions:
            remaining_queue = []
            for action in queued_actions:
                tool_name = action.get("tool")
                args = action.get("arguments", {})
                if not tool_name:
                    continue
                if self.actions_this_tick >= self.max_actions:
                    log_msg(f"⏳ Action quota full ({self.actions_this_tick}/{self.max_actions}). Rolled over queued {tool_name} to next tick.")
                    remaining_queue.append(action)
                    continue
                log_msg(f"🎯 Executing specific queued order: {tool_name} with args {args}")
                if not dry:
                    try:
                        res = self.client.call_tool(tool_name, args)
                        self.actions_this_tick += 1
                        act_msg = f"Executed queued order: {tool_name}"
                        actions_log.append(act_msg)
                        log_msg(f"✅ {tool_name} completed: {res}")
                    except Exception as err:
                        log_msg(f"❌ {tool_name} execution error: {err}")
                else:
                    log_msg(f"🔍 [Dry-Run] Would execute queued order: {tool_name}")

            if not dry:
                config["queued_actions"] = remaining_queue
                try:
                    with open(self.config_path, "w", encoding="utf-8") as f:
                        json.dump(config, f, indent=2)
                except Exception:
                    pass
        else:
            log_msg("🎯 Specific queued orders: None pending.")

        # 7. Execute Scheduled Recurring / Interval Tasks
        scheduled_tasks = config.get("scheduled_tasks", [])
        if scheduled_tasks and self.actions_this_tick < self.max_actions:
            tasks_modified = False
            due_tasks = 0
            for task in scheduled_tasks:
                if not task.get("enabled", True):
                    continue
                if self.actions_this_tick >= self.max_actions:
                    log_msg(f"⏳ Action quota full ({self.actions_this_tick}/{self.max_actions}). Scheduled task '{task.get('id')}' held for next tick.")
                    break

                tool_name = task.get("tool")
                args = task.get("arguments", {})
                sched_type = task.get("schedule_type", "interval_ticks")
                interval = int(task.get("interval_ticks", 1))
                last_tick = task.get("last_executed_tick", -1)
                target_tick = task.get("target_tick", None)

                is_due = False
                if sched_type == "every_tick":
                    is_due = (last_tick != tick_num)
                elif sched_type == "interval_ticks":
                    if last_tick == -1:
                        is_due = True
                    else:
                        is_due = (tick_num - last_tick) >= interval
                elif sched_type == "specific_tick":
                    is_due = (target_tick is not None and tick_num == int(target_tick) and last_tick != tick_num)

                if is_due and tool_name:
                    due_tasks += 1
                    log_msg(f"⏰ [Scheduled Task '{task.get('id', tool_name)}'] Due on Tick {tick_num}: Executing {tool_name} (args: {args})")
                    if not dry:
                        try:
                            res = self.client.call_tool(tool_name, args)
                            self.actions_this_tick += 1
                            act_msg = f"Scheduled task: {tool_name}"
                            actions_log.append(act_msg)
                            task["last_executed_tick"] = tick_num
                            task["last_result"] = "Success"
                            tasks_modified = True
                            log_msg(f"✅ Scheduled {tool_name} finished: {res}")
                            if sched_type == "specific_tick":
                                task["enabled"] = False
                        except Exception as err:
                            task["last_result"] = f"Error: {err}"
                            tasks_modified = True
                            log_msg(f"❌ Scheduled {tool_name} error: {err}")
                    else:
                        log_msg(f"🔍 [Dry-Run] Would execute scheduled task: {tool_name}")

            if tasks_modified and not dry:
                config["scheduled_tasks"] = scheduled_tasks
                try:
                    with open(self.config_path, "w", encoding="utf-8") as f:
                        json.dump(config, f, indent=2)
                except Exception:
                    pass
            if due_tasks == 0:
                log_msg(f"⏰ Scheduled interval tasks: {len(scheduled_tasks)} configured, 0 due this tick.")
        else:
            log_msg("⏰ Scheduled interval tasks: None configured.")

        # 8. Execute User Custom Strategy Hook
        strategy_mod = load_strategy_module(self.strategy_path)
        if strategy_mod and hasattr(strategy_mod, "on_tick"):
            try:
                log_msg("📜 Executing custom strategy hook (bot_strategy.py)...")
                strategy_mod.on_tick(self.client, state, config, log_msg)
            except Exception as e:
                log_msg(f"⚠️ Error executing custom strategy hook: {e}")

        self.last_tick_processed = tick_num
        summary_result = {
            "success": True,
            "tick": tick_num,
            "actionsUsed": self.actions_this_tick,
            "maxActions": self.max_actions,
            "actionsLog": actions_log,
            "timestamp": datetime.datetime.now().isoformat(),
        }

        save_state({
            "status": "RUNNING",
            "lastTick": tick_num,
            "lastRunTime": summary_result["timestamp"],
            "actionsUsed": self.actions_this_tick,
            "actionsLog": actions_log,
        })

        if self.actions_this_tick == 0:
            log_msg(f"🏁 Tick {tick_num} cycle finished: 0 actions executed (All queues busy / Nothing needed). Actions quota preserved (0 / {self.max_actions}).")
        else:
            log_msg(f"🏁 Tick {tick_num} cycle finished: {self.actions_this_tick} action(s) executed:")
            for act in actions_log:
                log_msg(f"   ▶ {act}")
            log_msg(f"   Quota consumed: {self.actions_this_tick} / {self.max_actions}")
        log_msg("=" * 50)
        return summary_result

    def run_loop(self):
        """Continuous execution loop synced to the 30-minute game ticks."""
        log_msg("🛰️ Pegasus Autonomous Bot starting 24/7 continuous tick loop...")
        log_msg(f"📁 Config: {self.config_path}")
        log_msg(f"📜 Strategy: {self.strategy_path}")

        save_state({
            "status": "RUNNING",
            "pid": os.getpid(),
            "startedAt": datetime.datetime.now().isoformat(),
            "lastTick": None,
        })

        while True:
            try:
                # 1. Check current tick
                tick_info_resp = self.client.get_tick_info()
                tick_data = tick_info_resp.get("data", {}) if isinstance(tick_info_resp, dict) else {}
                current_tick = tick_data.get("tick")
                next_tick_in = tick_data.get("nextTickIn", "unknown")

                # If this tick hasn't been processed yet, run it!
                if current_tick != self.last_tick_processed:
                    self.run_tick_cycle()
                    log_msg(f"💤 Tick {current_tick} complete. Bot standing by for Tick {current_tick + 1 if current_tick else ''} (Next tick in: {next_tick_in}).")

                # Sleep quietly for 20 seconds before checking if a new tick has arrived (NO log spam)
                time.sleep(20)

            except KeyboardInterrupt:
                log_msg("🛑 Bot loop stopped by user (Ctrl+C).")
                save_state({"status": "STOPPED", "stoppedAt": datetime.datetime.now().isoformat()})
                break
            except Exception as e:
                err_str = str(e)
                if "500" in err_str or "502" in err_str or "503" in err_str or "504" in err_str:
                    log_msg(f"⏳ Upstream Pegasus server momentary maintenance/tick rollover (HTTP 5xx). Auto-resuming in 30s...")
                else:
                    log_msg(f"❌ Loop exception: {e}. Retrying in 30 seconds...")
                time.sleep(30)


def main():
    parser = argparse.ArgumentParser(description="Pegasus Galaxy Autonomous Bot")
    parser.add_argument("--config", type=str, default=str(DEFAULT_CONFIG_PATH), help="Path to bot_config.json")
    parser.add_argument("--strategy", type=str, default=str(DEFAULT_STRATEGY_PATH), help="Path to bot_strategy.py")
    parser.add_argument("--once", action="store_true", help="Execute 1 tick cycle and exit")
    parser.add_argument("--dry-run", action="store_true", help="Simulate actions without modifying game state")
    args = parser.parse_args()

    bot = PegasusBot(
        config_path=Path(args.config),
        strategy_path=Path(args.strategy),
        dry_run=args.dry_run,
    )

    if args.once:
        res = bot.run_tick_cycle()
        print(json.dumps(res, indent=2))
    else:
        bot.run_loop()


if __name__ == "__main__":
    main()
