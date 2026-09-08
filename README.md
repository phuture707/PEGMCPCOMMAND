# Pegasus Galaxy MCP Client & Inspector Tool

A Python client and interactive command-line inspector for [Pegasus Galaxy](https://pegasus-galaxy.net/mcp), connected via Model Context Protocol (MCP 2025-03-26 Streamable HTTP).

[![GitHub Repository](https://img.shields.io/badge/GitHub-phuture707%2FPEGMCPCOMMAND-blue?logo=github)](https://github.com/phuture707/PEGMCPCOMMAND)
[![MCP Version](https://img.shields.io/badge/MCP-2025--03--26-cyan)](https://pegasus-galaxy.net/mcp)
[![Python Version](https://img.shields.io/badge/Python-3.10%2B-brightgreen)](https://python.org)

**Official GitHub Repository:** [https://github.com/phuture707/PEGMCPCOMMAND](https://github.com/phuture707/PEGMCPCOMMAND)

Designed both as an **instant game state viewer** and as the **core SDK library for building an autonomous game bot**.

---

## 🚀 Features

- **Interactive Sci-Fi Web GUI (`peg_gui.py`)**: Real-time interstellar control hub with live telemetry, tick countdown, dynamic tool runner for all 67 tools, mission tracker, and ship blueprints codex.
- **Terminal CLI Inspector (`peg_tool.py`)**: Rich terminal tables and dashboards for rapid checks and script piping.
- **Full MCP Discovery**: Inspect all 67 server tools and 6 dynamic resources.
- **Dynamic Tool Execution**: Call any game tool directly from the GUI, CLI, or via Python code.
- **Mission Tracker & Auto-Claim**: Monitor achievements, daily quests, story missions, and claim pending rewards with one click.
- **Hangar & Blueprint Codex**: Inspect combat statistics (Armor, Damage, Speed, Fuel, Cargo) for every ship type.
- **Agent Memory Scratchpad**: Read and write persistent memory entries (`set_memory`, `get_memory`) for your future autonomous bot.
- **Bot-Ready Library (`peg_client.py`)**: Reusable Python client for polling, queueing builds, launching fleets, and automating turns.

---

## 🎮 Launching the GUI

To launch the interactive GUI control hub:
```bash
python peg_gui.py
```
This starts the local control server on `http://localhost:7890` and **automatically opens your browser**.

### GUI Tabs & Capabilities:
1. **📊 Mission Control**: Colony telemetry, tick clock, resource meters, population allocation bars, active construction/research progress, traveling fleet countdowns, and quota limits.
2. **🛠️ Command Hub (67 Tools)**: Searchable tool sidebar with category filters. Selecting any tool auto-generates dynamic input forms based on its JSON schema, shows quota warnings, and executes on the live server.
3. **🎯 Quests & Missions**: Full achievement and quest tracker with a **"Claim All Rewards"** one-click banner.
4. **🚀 Hangar & Ship Codex**: Interactive visual cards detailing firepower, armor, speed, fuel burn, cargo, and tech prerequisites for all combat and transport vessels.
5. **🧠 Bot Memory**: Persistent scratchpad for your future bot to save notes, targets, and strategic states.

---

## ⚙️ Setup & Authentication

The client automatically loads your personal access token from `.env` or from environment variables (`PEGASUS_PAT` / `PEGASUS_API_KEY`).

Copy `.env.example` to `.env` and paste your personal access token (obtained from your Pegasus Galaxy account profile):
```env
PEGASUS_PAT=your_personal_access_token_here
```

---

## 🖥️ CLI Tool Usage (`peg_tool.py`)

### 1. View Game Dashboard
Displays colony overview, tick countdown, resources, population, construction/research progress, and fleet movements:
```bash
python peg_tool.py
```

### 2. View All Available MCP Tools
Lists all 67 tools with their parameter schemas, descriptions, and action vs. read categorization:
```bash
python peg_tool.py --tools
```

### 3. Check Missions & Quest Progress
Shows completed, active, and claimed missions (and prompts you if rewards are ready):
```bash
python peg_tool.py --missions
```

### 4. Claim Completed Missions
Claim resource and XP rewards:
```bash
python peg_tool.py --call claim_missions
```

### 5. Call Any Tool Dynamically
Invoke arbitrary MCP tools with optional JSON arguments:
```bash
# Get player ranking and total player count
python peg_tool.py --call get_player_rank

# Preview available constructions
python peg_tool.py --call list_construction_options

# Get the tech tree
python peg_tool.py --call get_tech_tree

# View leaderboard (top 5)
python peg_tool.py --call get_leaderboard --args '{"limit": 5}'

# View game rules
python peg_tool.py --rules overview
```

### 6. Browse & Read MCP Resources
Inspect static and dynamic game definitions:
```bash
# List available resources
python peg_tool.py --resources

# Read ship combat statistics
python peg_tool.py --read-resource pegasus://ship/definitions

# Read construction building trees
python peg_tool.py --read-resource pegasus://construction/definitions
```

### 7. Output JSON for Bot or Shell Piping
Add `--json` to any command for clean machine-readable output:
```bash
python peg_tool.py --json
python peg_tool.py --missions --json
```

---

## 🤖 Autonomous Bot Engine (`peg_bot.py`)

The repository includes a cross-platform autonomous bot engine designed to run 24/7 on Windows, Linux, or a remote VPS.

### Key Features:
- **Tick-Synchronized**: Automatically checks `get_tick_info()`, sleeps until the exact moment the 30-minute tick fires, and evaluates your colony state.
- **Quota-Protected**: Enforces a strict maximum of 8 actions/tick (under the 10 action server ceiling) so your account is never rate-limited.
- **Rule-Based Automation**: Configurable via `bot_config.json` for auto-claiming missions, repairing damaged PDS defenses, auto-constructing prioritized buildings, and researching prioritized technologies.
- **Dynamic Python Hook (`bot_strategy.py`)**: Programmable custom hook executed on every tick with live reload on file save (no bot restart required).

### CLI Bot Commands:
```bash
# Test 1 tick cycle in dry-run mode (no modifying actions taken)
python peg_bot.py --once --dry-run

# Execute 1 real tick cycle and exit
python peg_bot.py --once

# Run 24/7 continuous autonomous loop
python peg_bot.py
```

---

## 🌐 Programming the Bot from the GUI (Bot Studio)

You can monitor, configure, and code the bot directly in your web browser:
1. Launch `python peg_gui.py` and navigate to the **🤖 Bot Studio** tab.
2. **Process Controls**: Click **Start Bot Process**, **Stop Bot**, or **Step 1 Tick Cycle (Test Run)**.
3. **Strategy Rules**: Toggle Auto-Claim, Auto-Repair, Auto-Construct, and Auto-Research, and adjust priority ID queues.
4. **In-Browser Code Editor**: Write Python logic in `bot_strategy.py` directly from the web browser or load preset templates (*Economic Boom*, *Fortress Turtle*, *Armada Factory*). Edits take effect immediately on the next tick!
5. **Live Log Stream**: View the bot's real-time decisions and action logs directly in the embedded terminal console.

---

## ☁️ Deploying to a Linux VPS (Cloud 24/7)

You can run the bot 24/7 in the cloud using either **systemd** or **Docker**:

### Option A: Automated Systemd Setup (Recommended)
Copy the project folder to your VPS, make the script executable, and run:
```bash
chmod +x deploy_vps.sh
./deploy_vps.sh
```
This installs Python dependencies, creates a systemd service (`pegasus-bot.service`), enables auto-start on boot, and starts the service.

Monitor your VPS bot:
```bash
# View live bot logs
journalctl -u pegasus-bot -f

# Check service status
systemctl status pegasus-bot

# Restart or stop service
sudo systemctl restart pegasus-bot
sudo systemctl stop pegasus-bot
```

### Option B: Docker Container
```bash
# Build the container
docker build -t pegasus-bot .

# Run 24/7 in the background with auto-restart
docker run -d --name pegasus-bot --restart unless-stopped pegasus-bot

# View container logs
docker logs -f pegasus-bot
```

---

## ⚡ Game Mechanics & Rate Limits Reference

| Limit | Quota | Notes |
| :--- | :--- | :--- |
| **Tick Interval** | 30 Minutes | All constructions, research, and fleet travels progress when a tick fires. |
| **Total Actions** | 10 per tick | Modifying actions (building, researching, trading, producing ships). |
| **Fleet Launches** | 3 per tick | Min 20 ships per fleet, 1 eonium fuel per ship. |
| **Scans** | 2 per tick | Surface, deep, or military scans. |
| **Read Queries** | **Unlimited** | `get_game_state_summary`, `get_planet_status`, etc. consume **0** quota. |
