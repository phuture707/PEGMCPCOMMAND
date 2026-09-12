# 🌌 Pegasus Galaxy MCP Suite v0.2 — Web GUI, Bot Engine & CLI Inspector

A production-ready Python client, interactive web control dashboard, and autonomous bot suite for [Pegasus Galaxy](https://pegasus-galaxy.net/mcp), connected via Model Context Protocol (MCP 2025-03-26 Streamable HTTP).

[![Suite Version](https://img.shields.io/badge/Version-0.2-orange)](https://github.com/phuture707/PEGMCPCOMMAND)
[![GitHub Repository](https://img.shields.io/badge/GitHub-phuture707%2FPEGMCPCOMMAND-blue?logo=github)](https://github.com/phuture707/PEGMCPCOMMAND)
[![Platform](https://img.shields.io/badge/Platform-macOS%20%7C%20Linux%20%7C%20Windows-blueviolet)](https://github.com/phuture707/PEGMCPCOMMAND)
[![MCP Version](https://img.shields.io/badge/MCP-2025--03--26-cyan)](https://pegasus-galaxy.net/mcp)
[![Python Version](https://img.shields.io/badge/Python-3.10%2B-brightgreen)](https://python.org)

**Official GitHub Repository:** [https://github.com/phuture707/PEGMCPCOMMAND](https://github.com/phuture707/PEGMCPCOMMAND)

---

## 💡 Running 100% Locally: GUI + Local Bot on Your PC or Mac

**You do NOT need a cloud server or VPS to run this suite.** 

You can run everything **100% locally** on your personal computer (macOS, Windows, or Linux) while your machine is on:
1. **Run the Web GUI locally** (`peg_gui.py`) to monitor telemetry, browse ships, review quest progress, and dispatch commands.
2. **Run the Local Bot simultaneously**:
   - **Method A (Easiest — 1 Click from GUI)**: Inside `peg_gui.py`, switch to the **🤖 Bot Studio** tab and click **"Start Bot Process"**. The GUI automatically spawns `peg_bot.py` as a local background worker on your PC/Mac, tracks its live process PID, and streams its decision log directly into your browser console.
   - **Method B (Dual Terminal)**: Run `python3 peg_gui.py` in Terminal 1 for visual control, and `python3 peg_bot.py` in Terminal 2 for direct command-line output. Both share the same configuration (`bot_config.json`) and state files.
3. **Deploy to a VPS only when you want to**: A remote VPS is completely optional — you only need it if you want the bot to continue advancing your empire 24/7 while your desktop computer is powered off or asleep.

---

## 🚀 What's New in v0.2

- **Full macOS & Linux Cross-Platform Compatibility**: Native process management using POSIX sessions, cross-platform paths (`pathlib`), and auto-browser opening on macOS (Safari, Chrome, etc.).
- **Bot Studio UX Overhaul**:
  - **Smart Schema-Aware Parameter Forms**: Selecting any of the 67 tools generates typed form fields. `constructionId`, `shipDefinitionId`, and `researchId` are auto-populated as searchable dropdown menus from live game definitions.
  - **Categorized Tool Palette**: 67 tools organized into 10 clean `<optgroup>` categories with real-time text filter.
  - **Interactive Priority Pickers**: Click-to-add badges with `↑` `↓` reordering and `×` removal for colony construction and research tech queues.
  - **Granular Queue Management**: Inspect scheduled orders with human-readable arguments and delete individual queued items with one click.
  - **Advanced Mode**: Instant toggle between Smart Form inputs and raw JSON editor.
- **Official Game Codex & IDs Tab (Tab 5)**: Searchable reference cards for all 24 buildings, 12 technologies, and 35 ship hulls with click-to-copy badges and instant "⚡ Queue in Bot" injection.
- **Persistent Local Bot Memory**: Key-value memory scratchpad (`set_memory`, `get_memory`, `list_memory_keys`) persists locally in `bot_memory.json`.
- **Transient 500 Rollover Resilience**: Automatic retry with exponential backoff for tick boundary maintenance windows.

---

## ⚡ Quickstart Setup

### Step 1: Clone Repository
```bash
git clone https://github.com/phuture707/PEGMCPCOMMAND.git
cd PEGMCPCOMMAND
```

### Step 2: Set Up Python Virtual Environment

* **On macOS / Linux:**
  ```bash
  python3 -m venv venv
  source venv/bin/activate
  pip install -r requirements.txt
  ```

* **On Windows:**
  ```powershell
  python -m venv venv
  venv\Scripts\activate
  pip install -r requirements.txt
  ```

### Step 3: Configure Your Access Token
1. Copy the template credentials file:
   ```bash
   cp .env.example .env      # macOS / Linux
   copy .env.example .env    # Windows
   ```
2. Open `.env` and paste your Personal Access Token (PAT):
   ```env
   PEGASUS_PAT=pg_pat_your_actual_token_here
   ```
   *(Find or create your token under your player profile at https://pegasus-galaxy.net)*

### Step 4: Launch the Web Control Hub
```bash
python peg_gui.py           # On Windows
python3 peg_gui.py          # On macOS / Linux
```
Your browser will automatically open **`http://localhost:7890`**.

---

## 🎮 The 7 Web GUI Tabs (`peg_gui.py`)

1. **📊 Mission Control**: Colony telemetry, 30-minute tick countdown, resource reserves (Metal, Crystal, Eonium), net yields, population allocation bars, active construction/research timers, fleet movements, and quota usage.
2. **🛠️ Command Hub (67 Tools)**: Categorized tool palette (*Colony, Military, Social, Meta, Memory*). Selecting any tool renders schema-validated inputs, quota warnings, and runs directly against the live server.
3. **🎯 Quests & Missions**: Live story mission, daily quest, and achievement tracker with a one-click **"Claim All Rewards"** banner.
4. **🚀 Hangar & Ship Codex**: Side-by-side racial ship blueprints (**Vanguard**, **Synthara**, **Ashkari**) across classes (Light, Medium, Heavy, Transport, Mining) with deep combat stats and PDS defense battery health.
5. **📚 Game Codex & IDs Reference**: Searchable encyclopedia of exact IDs needed for commands (`constructionId`, `researchId`, `shipDefinitionId`) with one-click copy and "⚡ Queue in Bot" buttons.
6. **🤖 Bot Studio**:
   - Start, stop, step (1-tick test run), and monitor the local autonomous daemon with 1 click.
   - **Layer 1 Rules**: Visual toggles for Auto-Claim, Auto-Repair PDS, Auto-Construct, Auto-Research, and interactive priority badge pickers.
   - **Layer 2 Python Strategy**: In-browser Python editor for `bot_strategy.py` with 1-click deploy and live reload.
   - **Smart Dispatcher & Task Scheduler**: Queue one-off orders for the next tick, run recurring schedules (every N ticks), or execute immediately using auto-populated dropdowns.
   - **Live Log Stream**: Real-time console showing tick evaluations and quota status.
7. **🧠 Bot Memory**: Persistent scratchpad to store strategic notes, enemy coordinates, and state flags in `bot_memory.json`.

---

## 🔄 Dual-Environment Workflow: Local Play & 24/7 VPS Deployment

```
┌────────────────────────────────────────┐       git push        ┌──────────────────────────────────────┐
│  LOCAL PC / Mac (While Computer is On) │ ────────────────────> │      24/7 CLOUD VPS (Optional 24/7)  │
│  • Run GUI & local Bot simultaneously  │                       │  • Runs pegasus-bot in background    │
│  • Test new strategies in Bot Studio   │ <──────────────────── │  • Evaluates every 30-min game tick  │
│  • Tweak build orders & dry-run test   │       git pull        │  • Never wastes resources while away │
└────────────────────────────────────────┘                       └──────────────────────────────────────┘
```

### 1. Running Locally on Your PC / Mac
You can run the entire system locally:
- **Option 1 (All-in-One GUI)**: Launch `python peg_gui.py`. Go to the **Bot Studio** tab and click **Start Bot Process**. The bot runs locally in the background on your PC while you browse.
- **Option 2 (Terminal Bot)**: Run `python peg_bot.py` directly in your terminal. It logs every tick evaluation to your screen and `bot.log`.
- **Testing Logic**: Use **Dry-Run Mode** or the **Step 1 Tick Cycle** button to verify decisions without spending actions.

### 2. Pushing Strategy Updates to GitHub
When you have dialed in your settings and want to sync them:
```bash
# Check modified configuration or strategy files
git status

# Stage and commit your strategy improvements
git add bot_config.json bot_strategy.py custom_strategies/ config_profiles/
git commit -m "Optimize fleet factory and shield defense priorities"

# Push to your GitHub repository
git push origin main
```
> [!NOTE]
> Your `.env` token and local runtime logs (`bot.log`, `bot_state.json`, `bot_memory.json`) are automatically protected by `.gitignore` and will never be committed or overwritten.

### 3. Updating Your 24/7 Cloud VPS (When Stepping Away)
If you have an optional VPS running the bot 24/7 while your computer is asleep:
```bash
# Connect to your VPS
ssh root@YOUR_VPS_IP
cd /opt/peg-mcp

# Pull the latest strategy rules you tuned locally
git pull

# Restart the background service to pick up new changes immediately
sudo systemctl restart pegasus-bot

# Verify live logs
journalctl -u pegasus-bot -f
```

---

## 🖥️ CLI Inspector Tool (`peg_tool.py`)

Run terminal commands on any operating system (macOS, Linux, Windows):

```bash
# View colony telemetry dashboard
python peg_tool.py

# List all 67 tools with argument descriptions
python peg_tool.py --tools

# Inspect official Game IDs (Constructions, Research, Ships)
python peg_tool.py --reference
python peg_tool.py --reference constructions
python peg_tool.py --reference ships

# Check active and completed missions
python peg_tool.py --missions

# Claim all completed mission rewards
python peg_tool.py --call claim_missions

# Execute specific MCP tools
python peg_tool.py --call get_player_rank
python peg_tool.py --call build_construction --args '{"constructionId": "main-metal-mine"}'
python peg_tool.py --call produce_ships --args '{"shipDefinitionId": "main-vanguard-centurion", "quantity": 10}'
python peg_tool.py --call get_leaderboard --args '{"limit": 5}'

# Read MCP game resources
python peg_tool.py --resources
python peg_tool.py --read pegasus://ship/definitions

# Output JSON for script piping
python peg_tool.py --missions --json
```

---

## 🤖 Autonomous Bot Engine (`peg_bot.py`)

The background bot synchronizes to the server's 30-minute ticks:

```bash
# Test 1 tick cycle in dry-run mode (no game state modified)
python peg_bot.py --once --dry-run

# Run 1 tick cycle and exit (great for cron testing)
python peg_bot.py --once

# Run continuous 24/7 autonomous loop
python peg_bot.py
```

### Automation Features:
- **Tick Synchronized**: Calculates exact seconds to next tick via `get_tick_info()` and wakes up at rollover.
- **Quota Guard**: Caps actions at `max_actions_per_tick` (default 8) to never trigger server rate limits.
- **Auto-Claim**: Claims finished mission and quest rewards automatically.
- **Auto-Repair PDS**: Immediately detects damaged planetary defense structures and repairs them.
- **Priority Upgrades**: Follows your prioritized build order for mines, power plants, and research.
- **Custom Strategy Hook (`bot_strategy.py`)**: Executes your custom Python function `on_tick(client, state, config, logger)` on every cycle with live reload.

---

## ☁️ 24/7 VPS & Cloud Deployment (Optional)

### Option A: 1-Click Systemd Installer (Ubuntu / Debian VPS)
```bash
chmod +x deploy_vps.sh
./deploy_vps.sh
```
This sets up Python, creates a virtualenv, installs dependencies, and enables two systemd services:
* `pegasus-bot.service` — Autonomous 24/7 game engine with auto-restart on boot.
* `pegasus-gui.service` — Web Control Hub on port 7890.

### Option B: Docker Container
```bash
# Build Docker image
docker build -t pegasus-bot .

# Run 24/7 with auto-restart
docker run -d --name pegasus-bot --restart unless-stopped pegasus-bot

# Monitor live logs
docker logs -f pegasus-bot
```

### Secure Remote GUI Access via SSH Tunnel (No Open Ports):
Leave port 7890 blocked on your VPS firewall and forward it securely through SSH:
```bash
ssh -L 7890:localhost:7890 root@YOUR_VPS_IP
```
Then open `http://localhost:7890` in your desktop browser.

---

## ⚡ Game Quota & Rate Limits Reference

| Limit | Quota | Notes |
| :--- | :--- | :--- |
| **Tick Interval** | 30 Minutes | Construction, research, and fleet movements advance at tick rollover. |
| **Total Actions** | 10 per tick | Modifying actions (building, researching, producing, trading). |
| **Fleet Launches** | 3 per tick | Min 20 ships per fleet, 1 eonium fuel per ship. |
| **Scans** | 2 per tick | Surface, deep, or wave scans. |
| **Read Queries** | **Unlimited** | `get_planet_status`, `get_tick_info`, etc. consume **0** quota. |

---

## ❓ FAQ & Troubleshooting

* **Can I run the Web GUI and the Bot locally at the same time on my PC / Mac?**
  * *Yes!* You can launch `peg_gui.py` and click **"Start Bot Process"** directly inside the Bot Studio tab. The GUI spawns the local bot as a child process and streams its live logs right into your browser. Alternatively, open two terminal windows and run `python peg_gui.py` in one and `python peg_bot.py` in the other.
* **Does it work on macOS?**
  * *Yes*. Full macOS support is verified for both Intel and Apple Silicon (M1/M2/M3/M4). Subprocess detachment, terminal formatting, paths, and automatic browser launch operate natively.
* **Do I need a cloud VPS?**
  * *No*. A VPS is only needed if you want the bot to keep running around the clock while your computer is turned off. While your computer is running, running everything locally is 100% functional.
* **Are my API token and logs exposed in Git?**
  * *No*. `.env`, `bot.log`, `bot_state.json`, and `bot_memory.json` are listed in `.gitignore` and stay local to each machine.
* **Port 7890 already in use?**
  * Run on a different port: `python peg_gui.py --port 8080`.\n