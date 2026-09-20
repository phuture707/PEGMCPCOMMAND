# 🌌 Pegasus Galaxy MCP Suite v0.6 — Complete User & Operations Guide

Welcome to the **Pegasus Galaxy Model Context Protocol (MCP) Suite v0.6**. This package provides a comprehensive, production-ready suite of tools to interact with, inspect, automate, and dominate the interstellar universe of [Pegasus Galaxy](https://pegasus-galaxy.net).

[![Suite Version](https://img.shields.io/badge/Version-0.6-orange)](https://github.com/phuture707/PEGMCPCOMMAND)
[![GitHub Repository](https://img.shields.io/badge/GitHub-phuture707%2FPEGMCPCOMMAND-blue?logo=github)](https://github.com/phuture707/PEGMCPCOMMAND)
[![Platform](https://img.shields.io/badge/Platform-macOS%20%7C%20Linux%20%7C%20Windows-blueviolet)](https://github.com/phuture707/PEGMCPCOMMAND)
[![MCP Version](https://img.shields.io/badge/MCP-2025--03--26-cyan)](https://pegasus-galaxy.net/mcp)
[![Python Version](https://img.shields.io/badge/Python-3.10%2B-brightgreen)](https://python.org)

**Official GitHub Repository:** [https://github.com/phuture707/PEGMCPCOMMAND](https://github.com/phuture707/PEGMCPCOMMAND)

---

## 📑 Table of Contents
1. [Official Repository & Installation](#-official-github-repository)
2. [Running Locally: Web GUI + Local Bot on PC/Mac](#-running-locally-web-gui--local-bot-on-pcmac)
3. [Quickstart Setup (macOS, Linux & Windows)](#-quickstart-setup)
4. [Dual-Environment & Git Deployment Workflow](#-dual-environment--git-deployment-workflow)
5. [Suite Architecture & Components](#-suite-architecture--components)
6. [Tool 1: Web Control Hub (`peg_gui.py`)](#-tool-1-web-control-hub-peg_guipy)
7. [Tool 2: Autonomous Game Bot (`peg_bot.py`)](#-tool-2-autonomous-game-bot-peg_botpy)
8. [Tool 3: Terminal CLI Inspector (`peg_tool.py`)](#-tool-3-terminal-cli-inspector-peg_toolpy)
9. [Tool 4: Python Client SDK (`peg_client.py`)](#-tool-4-python-client-sdk-peg_clientpy)
10. [Strategy Profiles & Custom Python Scripts](#-strategy-profiles--custom-python-scripts)
11. [Mobile Phone Access & Zero-PC Cloud Architecture](#-mobile-phone-access--zero-pc-cloud-architecture)
12. [24/7 Cloud & VPS Deployment Guide](#-247-cloud--vps-deployment-guide)
13. [Official Game IDs Reference (Buildings, Tech & Ships)](#-official-game-ids-reference-buildings-tech--ships)
14. [Troubleshooting & FAQ](#-troubleshooting--faq)

---

## 🔗 Official GitHub Repository

You can find the latest releases, submit bug reports, or contribute improvements at:
👉 **[https://github.com/phuture707/PEGMCPCOMMAND](https://github.com/phuture707/PEGMCPCOMMAND)**

To clone the repository directly using Git:
```bash
git clone https://github.com/phuture707/PEGMCPCOMMAND.git
cd PEGMCPCOMMAND
```

---

## 💻 Running Locally: Web GUI + Local Bot on PC/Mac

**You do NOT need a remote VPS or server to automate Pegasus Galaxy.** 

You can run both the **interactive Web GUI** and the **autonomous Bot** simultaneously on your local computer (macOS, Windows, or Linux) whenever your PC is on.

### How Local Execution Works:
* **Option 1 (All-in-One via Browser — Recommended)**:
  1. Launch `python peg_gui.py` (or `python3 peg_gui.py` on Mac).
  2. In your browser, open the **🤖 Bot Studio** tab.
  3. Click **"Start Bot Process"**. 
  4. The GUI will spawn `peg_bot.py` locally as a background process, show its active PID badge, and stream its live evaluation logs directly into the embedded console!
  5. You can tweak rules, add building priorities, or edit `bot_strategy.py` right from your browser, and the local bot will immediately apply them on the next 30-minute tick.
* **Option 2 (Two Terminal Windows)**:
  1. **Terminal 1**: Run `python peg_gui.py` to keep your visual dashboard active.
  2. **Terminal 2**: Run `python peg_bot.py` to watch the autonomous tick loop execute in real time.
  3. Both share the local `bot_config.json`, `bot_state.json`, and `bot.log` files seamlessly.

You only need an external cloud VPS if you want the bot to continue advancing your empire 24/7 while your computer is turned off.

---

## ⚡ Quickstart Setup

### Step 1: Install Python Dependencies

The suite requires Python 3.10+ and works seamlessly on **macOS (Intel & Apple Silicon M1/M2/M3/M4)**, **Linux (Ubuntu, Debian, Fedora)**, and **Windows (10/11)**.

* **On macOS / Linux:**
  ```bash
  python3 -m venv venv
  source venv/bin/activate
  pip install -r requirements.txt
  ```

* **On Windows (PowerShell / Command Prompt):**
  ```powershell
  python -m venv venv
  venv\Scripts\activate
  pip install -r requirements.txt
  ```

### Step 2: Configure Your Personal Access Token (Automated or Manual)

**Option A (Recommended — Automated Setup):**
Run the interactive setup assistant:
```bash
python setup_env.py
```
*Prompts for your Pegasus Galaxy API key / Personal Access Token, automatically creates your `.env` file, tests connection to the server, and offers a 1-click launch into `peg_gui.py`!*

**Option B (Manual):**
1. Copy the sample environment file:
   ```bash
   cp .env.example .env      # macOS / Linux
   copy .env.example .env    # Windows
   ```
2. Open `.env` in any text editor and paste your personal access token (PAT):
   ```env
   PEGASUS_PAT=pg_pat_your_actual_token_here
   ```
   *(Find or generate your token under your player profile or settings at https://pegasus-galaxy.net)*

### Step 3: Launch the Web Dashboard
```bash
python3 peg_gui.py          # macOS / Linux
python peg_gui.py           # Windows
```
Your default web browser will automatically open **`http://localhost:7890`**.

---

## 🔄 Dual-Environment & Git Deployment Workflow

### Developing Locally While PC is On, Then Pushing to 24/7 VPS
This is the ultimate setup: play and tune locally, then push your strategy to run on a 24/7 cloud server while you sleep.

```
┌────────────────────────────────────────┐       git push        ┌──────────────────────────────────────┐
│  LOCAL PC / Mac (While Computer is On) │ ────────────────────> │      24/7 CLOUD VPS (Always-On)      │
│  • Play in GUI & run local Bot         │                       │  • Runs pegasus-bot in background    │
│  • Test new strategies & build orders  │ <──────────────────── │  • Evaluates every 30-min game tick  │
│  • Use dry-run & 1-tick test cycles    │       git pull        │  • Advances empire while PC is off   │
└────────────────────────────────────────┘                       └──────────────────────────────────────┘
```

#### Phase 1: Local Tuning & Play (PC or Mac is Running)
1. Launch `python peg_gui.py` on your computer.
2. Monitor your colony telemetry, manage fleet launches, and queue actions in the 7-tab GUI.
3. In the **🤖 Bot Studio** tab:
   - Adjust building upgrade priorities or tech research order using the interactive badge pickers.
   - Edit custom Python code in `bot_strategy.py` or try out preset templates (`armada_factory.py`, `fortress_turtle.py`, `economic_boom.py`).
   - Use the **Step 1 Tick Cycle** button or dry-run mode to verify your logic without wasting actions.
   - Click **Start Bot Process** to run the bot locally on your machine while your PC is awake.

#### Phase 2: Committing and Pushing to Git
When you are ready to push your strategy improvements to your repository so your 24/7 VPS can take over:
```bash
# 1. Check which strategy/config files you modified
git status

# 2. Stage your updated strategy files and configurations
git add bot_config.json bot_strategy.py custom_strategies/ config_profiles/

# 3. Commit your changes with a clear summary
git commit -m "Tune armada production and shield defense priorities"

# 4. Push to your GitHub repository
git push origin main
```

> [!IMPORTANT]
> **Safety & Privacy**: Your Personal Access Token (`.env`), runtime state (`bot_state.json`), local execution logs (`bot.log`), and local scratchpad memory (`bot_memory.json`) are **strictly excluded** by `.gitignore`. Pushing your strategy code will **never** leak your token or overwrite server-specific runtime logs.

#### Phase 3: Pulling on Your 24/7 Cloud VPS
When you turn off or put your PC/Mac to sleep, your VPS continues managing your empire around the clock:
```bash
# 1. SSH into your VPS
ssh root@YOUR_VPS_IP

# 2. Navigate to your installation directory
cd /opt/peg-mcp

# 3. Pull the latest strategy code you pushed from your PC
git pull

# 4. Restart the bot background service to reload the updated strategy
sudo systemctl restart pegasus-bot

# 5. Follow live bot evaluation logs
journalctl -u pegasus-bot -f
```

---

## 🧩 Suite Architecture & Components

```
pegasus-mcp-suite/
├── peg_gui.py              # Interactive sci-fi web control dashboard, Bot Studio & Combat Simulator v0.6
├── peg_calc.py             # Standalone BattleCalc launcher & multi-window coordinator v0.6
├── peg_bot.py              # Autonomous 24/7 tick-synchronized background bot v0.6
├── peg_tool.py             # Rich terminal CLI inspector & command runner v0.6
├── peg_combat.py           # Tactical combat simulator & multi-fleet coalition battle engine v0.6
├── docs/                   # Public static BattleCalc (GitHub Pages) & client-side combat engine v0.6
│   ├── calc.html           # Zero-dependency browser battle calculator & JS combat simulator
│   └── index.html          # Clean entry point with hash preservation
├── peg_client.py           # Core Python MCP client SDK (JSON-RPC / Streamable HTTP)
├── game_rules.json         # Official rules, tech modifiers, ship definitions & scan mechanics
├── bot_config.json         # Active Layer 1 automation rules & priorities
├── bot_strategy.py         # Active Layer 2 Python strategy hook (live-reloaded)
├── bot_memory.json         # Local persistent key-value memory scratchpad
├── config_profiles/        # Library of named automation profiles (.json)
│   ├── Default Economy.json
│   ├── Fortress Defense.json
│   └── Armada War.json
├── custom_strategies/      # Library of custom Python strategy hooks (.py)
│   ├── economic_boom.py
│   ├── fortress_turtle.py
│   └── armada_factory.py
├── deploy_vps.sh           # Automated 1-click Linux VPS installer
├── Dockerfile              # Containerized deployment definition
├── pegasus-bot.service     # Linux systemd service for 24/7 autonomous bot
├── pegasus-gui.service     # Linux systemd service for 24/7 web dashboard
├── requirements.txt        # Python package dependencies (httpx, rich, python-dotenv)
├── .env.example            # Sample credentials file
├── README.md               # Quickstart and feature overview
└── INSTRUCTIONS.md         # Complete user and operations manual
```

---

## 🌐 Tool 1: Web Control Hub (`peg_gui.py`)

A full-featured, zero-external-frontend-dependency web application styled with a cyber/sci-fi space aesthetic. Runs natively on macOS, Linux, and Windows.

### How to Run:
* **Local Desktop Mode** (auto-launches default browser):
  ```bash
  python3 peg_gui.py        # macOS / Linux
  python peg_gui.py         # Windows
  ```
* **Headless / VPS Server Mode** (accessible remotely):
  ```bash
  python3 peg_gui.py --host 0.0.0.0 --port 7890 --no-browser
  ```

### The 8 Dashboard Tabs & Features:
1. **📊 Mission Control**:
   - **Colony Telemetry**: Real-time metal, crystal, eonium reserves, and net production rates.
   - **Tick Countdown Clock**: Synchronized with Pegasus Galaxy server 30-minute ticks.
   - **Player Rank & Civilization Intel**: Population allocation, level, score, and race traits.
   - **Active Construction & Research Progress**: Visual progress bars and completion timers.
   - **Fleet Tracker**: Incoming and outgoing space fleets with coordinates and ETAs.
   - **Quota Guard Meter**: Tracks modifying actions used during the current tick window.
2. **🛠️ Command Hub (All 67 Tools)**:
   - Searchable, categorized command palette (*Colony, Military, Social, Meta, Memory*).
   - Dynamic form generator: reads parameter schemas and renders validated inputs.
   - Safety badges: distinguishes between safe `[READ]` queries and quota-consuming `[ACTION]` commands.
3. **🎯 Quests & Missions**:
   - Live quest tracker for story missions, daily objectives, and achievements.
   - **"Claim All Rewards"**: Single-click button to collect all completed rewards in one batch.
4. **🚀 Hangar & Ship Codex**:
   - Ships categorized side-by-side by race (**Vanguard**, **Synthara**, **Ashkari**).
   - Filterable by combat class (**Light**, **Medium**, **Heavy**, **Special**, **Transport**, **Mining**).
   - Deep combat metrics: Armor, Direct Firepower, EMP Damage, Sublight Speed, Fuel Burn/Capacity, and Cargo capacity.
   - **Planetary Defense Structures (PDS)**: Live defense status showing active health points (HP), level, damage state, and base weapon stats.
5. **📚 Game Codex & IDs Reference**:
   - Live catalog of all 24 constructions, 12 research technologies, and 35 ship hull designs.
   - Click-to-copy badges and instant **"⚡ Queue in Bot"** injection directly into the Bot Studio dispatcher.
6. **🤖 Bot Studio (v0.2 Overhaul)**:
   - Start, stop, step (1-tick test run), and monitor the local autonomous bot daemon directly from your browser.
   - **Smart Parameter Forms**: Select any tool to render typed controls; game object IDs auto-populate from live server data.
   - **Interactive Priority Pickers**: Clickable chips for construction and research queues with `↑` `↓` reordering and `×` removal.
   - **Task Scheduler**: Schedule recurring tasks (every N ticks) or queue orders for next tick.
   - **Individual Queue Deletion**: Remove staged orders one-by-one with human-readable argument summaries.
   - **In-Browser Python Editor**: Write custom code for `bot_strategy.py` with 1-click deploy.
   - **Live Log Streamer**: Real-time console showing tick evaluations, server responses, and decisions.
7. **🧠 Bot Memory**:
   - Persistent key-value memory scratchpad backed by local `bot_memory.json` storage.
8. **⚔️ Battle Simulator & Coalition Calculator (v0.6)**:
    - **Hybrid Standalone & MCP Bridge Engine (`docs/calc.html`)**:
      - **Zero-Dependency Public Standalone Mode**:
        - Accessible directly via GitHub Pages (`https://phuture707.github.io/PEGMCPCOMMAND/calc.html`) or as an offline single-file HTML export.
        - Requires **zero installation, zero Python, and zero server backend**. Anyone—including alliance members without MCP—can open the page on any device (desktop, tablet, mobile) and run client-side simulations.
        - Pure JavaScript combat engine faithfully simulating Pegasus Galaxy mechanics: PDS battery pre-emptive strikes, class-based ship targeting, shield absorption, EMP system disabling, and 30% metal/crystal debris salvage.
        - **URL Hash Scenario Sharing (`#c=...`)**: Battle scenarios (fleets, techs, coordinates, PDS structures) are compressed using native browser `CompressionStream('deflate-raw')` / Base64URL. Links are 100% serverless, never expire, and require no external database.
        - **"💾 Export HTML"**: Generates a self-contained, standalone single-file HTML battle calculation that can be archived or shared on Discord.
      - **Zero-Click MCP Auto-Activation (When Local Suite is Running)**:
        - When opened by a commander running the Pegasus Control Suite (`python peg_gui.py` on port 7890), `docs/calc.html` silently probes `http://127.0.0.1:7890/api/state` and `/api/combat/attacker_fleets` on page load.
        - **No button clicks or manual login required**: The page instantly shifts from ⚪ `Standalone Mode` to 🟢 `MCP Connected • Live Access`, auto-detects current tick and home planet coordinates, and unlocks the full suite of live MCP combat capabilities.
        - **Secure `.env` Session Access**: The browser utilizes the local Python daemon's existing authenticated credentials, completely eliminating the need to expose `.env` files or grant filesystem access to the browser.
        - **Live Empire Fleet & Base Garrison Auto-Ingestion**: Ingests your empire's active named fleets and docked hangar craft into the `🏰 Add Own Fleet...` dropdowns, and automatically initializes your home base Garrison and Planetary Defense Structures (PDS levels 1–4) into the Defender matrix on startup if empty.
        - **Interactive Scan Browser & Fleet Picker Modal (`🔍 Browse Scans`)**: Browse, search, and import personal scans (`get_scan_history`) and alliance shared intel (`get_scan_intel`) directly into Defender or Attacker matrix columns with 1 click (Garrison, Named Fleets, or Consolidated Forces).
        - **Automated 30-Second Background Scan Polling**: Background sync polls for new alliance intelligence every 30 seconds (`startScanBackgroundSync()`), alerting commanders with live notifications when fresh scans arrive and auto-updating intel badges.
        - **Multi-Calculation Sessions System (`#calc-multi-tabs-bar`)**: Work on multiple simultaneous battle plans (`Calc #1`, `Calc #2`, `➕ New Tab`, `📋 Duplicate`, `✏️ Rename`, `✕ Close`) within the same standalone window.
        - **Dual-Side Matrix Controls**: Full feature parity across Defender and Attacker—`+ Fleet`, `🏰 Load Base/Fleets`, `⚡ Consolidate`, `🔍 Browse Scans`, `🏰 Add Own Fleet...`, and `📡 Pick Scanned Target...` controls.
        - **Tactical Defense Auto-Setup (`[🛡️ Plan Defense at Tick X]`)**: Evaluates arriving vs late fleets at target tick $T$, inbound attacker coalitions, scan reliability ratings (0–100%), and decoy/feint detection.
        - **1-Click MCP In-Game Message Dispatch (`send_message`)**: Automatically formats tactical battle briefings, casualty projections, and public calculation links, transmitting them directly to an alliance mate's in-game inbox.
        - **Remote / Mobile Token Fallback**: Commanders opening `docs/calc.html` on mobile phones or remote devices without `peg_gui.py` running locally can optionally enter their Personal Access Token (`pat_...`) in the connection modal for direct game access.
      - **Shared Link Recipient Experience (MCP vs Standalone Comparison)**:
        When a commander shares a calculation link (e.g. `https://phuture707.github.io/PEGMCPCOMMAND/calc.html#c=...`), anyone can open it. If the recipient has the local Control Suite (`python peg_gui.py`) running, their browser automatically upgrades to full MCP capability connected to their own empire, pre-populated with the sender's tactical scenario:

        | Feature / Capability | Recipient Has MCP (`peg_gui.py` running) | Recipient Does NOT Have MCP (Offline / Standalone) |
        | :--- | :---: | :---: |
        | **View Shared Battle & Scenarios** | ✅ Yes (Decompresses `#c=...` hash) | ✅ Yes (Decompresses `#c=...` hash) |
        | **Run Combat Simulations & Salvage** | ✅ Yes (Client-Side JS) | ✅ Yes (Client-Side JS) |
        | **Edit Fleets & Export New Links** | ✅ Yes | ✅ Yes |
        | **Auto-Detect `.env` & Live Game Tick** | ✅ Yes (Zero clicks / auto-probed) | ❌ No (Shows offline/standalone badge) |
        | **`🏰 Add Own Fleet...` (Hangar / Fleets)** | ✅ Yes (Auto-loads recipient's empire) | ❌ No (Manual fleet entry) |
        | **`🔍 Browse Scans` (Personal & Ally Intel)** | ✅ Yes (Auto-polled every 30s) | ❌ No (Manual scan entry) |
        | **`[🛡️ Plan Defense at Tick X]`** | ✅ Yes (Arrival margins & decoy detection) | ❌ No |
        | **`[💬 In-Game Msg]` Dispatch** | ✅ Yes (Direct in-game MCP send) | ❌ No |
    - **Standalone Mode & Zero-Overhead Multi-Window (`/calc`)**:
      - Access `http://127.0.0.1:7890/calc` (or `python peg_calc.py`) for a pure, dedicated Battle Matrix interface without background polling or dashboard tabs.
      - A single background Python server handles unlimited calculation windows and tabs simultaneously without duplicate processes.
    - **1-Click "↗️ Pop Out to Window"**:
      - Click `↗️ Pop Out Window` in the toolbar or action bar to snapshot current fleets, scans, coordinates, and PDS into an independent new browser window.
      - Provides a 1-click prompt to reset the original window back to clean scratch state, enabling parallel multi-target planning.
    - **Combat Matrix Mode (Default View)**: Default layout provides a high-density side-by-side combat grid matching classic BattleCalc engines (`bcalc.pl`). Forces are rendered in side-by-side columns with per-fleet input columns, `(E)` empty buttons, disable checkboxes, totals, destroyed casualties, and EMP disabled counts. You can also toggle to **🗂️ Cards View** anytime.
    - **Report of Losses from [Fleet]**: Replicates signature per-fleet casualty manifests, followed by exact Salvage and Plunder/Asteroid reports.
    - **CLI BattleCalc Format (`--format bcalc`)**: Generates copy-pasteable battle reports in terminal or for Discord/alliance comms (`python peg_tool.py --battle-calc --defender 12:1:1 --format bcalc`).
    - **Direct Coordinate Entry & Latest Scans Dropdown**: Enter coordinates directly (e.g. `12:1:1`, `12, 1, 1`, `12 1 1`) or jump via universe planet picker to instantly view a dedicated dropdown of the latest scans for those coordinates (sorted newest tick first) with auto-population of garrison, fleets, and PDS.
    - **Alliance Scan Intelligence Ingestion (`get_scan_intel`)**: Automatically detects alliance membership and queries shared alliance scans alongside personal scan history (`get_scan_history`), with universe map coordinate enrichment and error resilience.
    - **Source Search & Filtering**: Segmented filter pills (`🌐 All Scans`, `👤 My Scans`, `🤝 Ally Intel`) across target selectors, dropdowns, and the Scan Picker modal.
    - **CLI Battle Simulator Coordinate & Source Support**: Run `python peg_tool.py --battle-calc --defender <COORDS> [--source {all,user,ally}]` with automatic multi-scan comparison tables and latest scan selection.
    - **Multi-Fleet Coalitions**: Build and simulate coalitions of multiple attacking and defending fleets simultaneously. Add, remove, rename, and individually toggle fleets in combat calculations.
    - **Live Telemetry & Capacity Aggregates**: Calculates total coalition firepower, armor, cargo capacity, and asteroid capture capacity in real time.
    - **Comprehensive Scan Type Ingestion**: Ingests all combat-capable scan types (`FLEET_COMPOSITION_SCAN`, `MILITARY_SCAN`, `DEEP_SCAN`, `INCOMING_SCAN`) from your scan history.
    - **Planetary Intelligence Resolution**: Automatically resolves coordinates and ownership across multiple scans for focused fleet scans. Ground PDS structures (`Laser Battery`, `Missile Silo`, `Ion Cannon`, `Shield Generator`) are parsed directly from scan records and applied strictly to base planet defenses.
    - **Planetary Assault & Home Defense Modes**: 1-click role inversion swaps rosters and applies your empire's live PDS levels when defending.

---

## 🤖 Tool 2: Autonomous Game Bot (`peg_bot.py`)

A robust background worker engineered to never waste a game tick. Works identically on macOS, Linux VPS, or Windows.

### Core Philosophy:
* **Tick Synchronization**: The bot queries the server for `get_tick_info()`, calculates the exact seconds remaining in the current 30-minute game cycle, and sleeps until the new tick fires.
* **Quota Safety Cap**: Never exceeds your designated `max_actions_per_tick` (default 8) to protect against accidental action overdrafts.
* **Two-Layer Strategy Pipeline**:
  1. **Layer 1 (Declarative Rules)**: Evaluates mission claims, checks PDS defense health, triggers prioritized building upgrades, and queues tech research.
  2. **Layer 2 (Custom Python Script)**: Dynamically imports `bot_strategy.py` and executes `on_tick(client, state, config, logger)` for custom tactics.

### Command-Line Arguments:
```bash
# Run continuous background daemon locally or on VPS
python3 peg_bot.py

# Run a single tick evaluation and exit immediately (ideal for testing or cron jobs)
python3 peg_bot.py --once

# Dry-run mode: evaluate logic and log decisions without executing modifying actions
python3 peg_bot.py --once --dry-run

# Specify custom configuration or strategy paths
python3 peg_bot.py --config custom_config.json --strategy custom_strategy.py
```

---

## 💻 Tool 3: Terminal CLI Inspector (`peg_tool.py`)

A command-line tool equipped with Rich formatting for terminal enthusiasts, macOS Terminal / iTerm2, SSH sessions, and script automation.

### Commands Reference:
```bash
# 1. Print full colony telemetry dashboard (resources, tick timer, buildings, fleets)
python3 peg_tool.py

# 2. List all 67 tools with argument descriptions
python3 peg_tool.py --tools

# 3. Inspect official Game IDs (Constructions, Research, Ships)
python3 peg_tool.py --reference
python3 peg_tool.py --reference constructions
python3 peg_tool.py --reference ships
python3 peg_tool.py --reference research

# 4. Check quests, achievements, and completed mission rewards
python3 peg_tool.py --missions

# 5. Call any MCP tool with optional JSON arguments
python3 peg_tool.py --call get_player_rank
python3 peg_tool.py --call list_construction_options
python3 peg_tool.py --call build_construction --args '{"constructionId": "main-metal-mine"}'
python3 peg_tool.py --call produce_ships --args '{"shipDefinitionId": "main-vanguard-centurion", "quantity": 10}'
python3 peg_tool.py --call get_leaderboard --args '{"limit": 10}'

# 6. List and inspect MCP resources
python3 peg_tool.py --resources
python3 peg_tool.py --read pegasus://ship/definitions
python3 peg_tool.py --read pegasus://construction/definitions

# 7. Read game rules and mechanics
python3 peg_tool.py --rules overview
python3 peg_tool.py --rules combat
python3 peg_tool.py --rules constructions
```

---

## 📦 Tool 4: Python Client SDK (`peg_client.py`)

`peg_client.py` can be imported into your own Python scripts or automated workflows.

### Example Usage:
```python
from peg_client import PegasusMCPClient

# Initialize client (loads token automatically from .env)
client = PegasusMCPClient()

# Check tick status
tick = client.get_tick_info()
print(f"Current Tick: {tick.get('currentTick')}, Seconds Remaining: {tick.get('secondsToNextTick')}")

# Fetch colony planet status
planet = client.get_planet_status()
print(f"Planet Name: {planet.get('name')}")

# Call any arbitrary tool (with automatic retry on transient 500s)
res = client.call_tool("get_planet_ships")
print(f"Ships in hangar: {res}")

# Local agent memory persistence
client.call_tool("set_memory", {"key": "primary_target", "value": "55:2:8"})
target = client.call_tool("get_memory", {"key": "primary_target"})
print(f"Target from memory: {target}")

# Close connection when finished
client.close()
```

---

## 🧠 Strategy Profiles & Custom Python Scripts

### 1. Layer 1: Rules & Profiles (`config_profiles/`)
Rules are saved as clean JSON files inside `config_profiles/`. Three presets are included out of the box:
* **Default Economy**: Focuses on resource expansion (metal mines, crystal synthesizers, eonium refineries).
* **Fortress Defense**: Focuses on defensive emplacements (missile silos, shield generators, ion cannons).
* **Armada War**: Focuses on shipyard infrastructure and heavy manufacturing facilities.

### 2. Layer 2: Custom Python Hooks (`custom_strategies/`)
Custom scripts reside in `custom_strategies/`. When a script is activated, it is copied to `bot_strategy.py` and reloaded live every tick without bot restart.

---

## 📱 Mobile Phone Access & Zero-PC Cloud Architecture

The Pegasus Galaxy Standalone BattleCalc, Live Radar, and Intel Browser are fully mobile-responsive and engineered to work natively on **smartphones (iOS Safari, Android Chrome, iPad, tablets)** — **even while your personal computer is turned completely OFF**.

### 1. Mobile-Optimized Responsive Experience
- **Vertical Force Stacking**: On screens under 960px (mobile phones and narrow tablets), Defender forces (Blue) and Attacker coalitions (Red) automatically stack vertically instead of side-by-side. Each side gets **100% full-screen width**, providing ample space to navigate fleets.
- **Sticky Ship Name Column**: Swiping horizontally through fleet columns locks the first column (**Ship / Class**) frozen on the left edge. Ship class names (Pulse Courier, Arc, Monolith, Oblivion, etc.) stay visible as you pan across up to 8–16 fleet columns.
- **Touch Ergonomics & Input Sizing**: Number inputs and action buttons adapt with generous touch-friendly padding. Font sizes are set to prevent iOS Safari from auto-zooming when tapping numerical inputs.
- **Adaptive Dialog Modals**: Share link, scan browser, and import modals scale responsively (`max-width: 96vw; max-height: 88vh;`) with smooth inertial touch-scrolling.

### 2. How MCP Works While Your PC is Powered OFF
When your home desktop or laptop computer is shut down, the local computer's processor, RAM, and `.env` file are physically unreachable.

The architecture solves this through cloud persistence:
1. **The Game's MCP Server is Cloud-Hosted**: The official Pegasus Galaxy MCP server operates 24/7 in the cloud at `https://mcp.pegasus-galaxy.net`.
2. **The Web Calculator is Cloud-Hosted**: Hosted 24/7 on GitHub Pages at [`https://phuture707.github.io/PEGMCPCOMMAND/calc.html`](https://phuture707.github.io/PEGMCPCOMMAND/calc.html).
3. **Persistent Flash Memory (`localStorage`)**: Your game credentials are saved in your phone's browser `localStorage` (`peg_mcp_pat`). Unlike `sessionStorage` (which wipes when closing a tab), `localStorage` is saved to your phone's persistent flash storage, surviving tab closures, browser restarts, and phone reboots.
4. **Direct HTTPS Cloud Bridge**: Your mobile browser communicates directly with `https://mcp.pegasus-galaxy.net` over cellular data (5G/LTE) or Wi-Fi. It queries `get_planet_status`, `get_tick_info`, `get_fleet_summary`, and `get_scan_history` with zero local PC or Python required.

### 3. Transferring Your Credentials to Your Phone

#### Method A: 1-Click QR Code Transfer (Recommended — Zero Typing)
1. On your PC, open the desktop Control Hub (`peg_gui.py`).
2. Click **`📱 Connect Phone`** in the Standalone BattleCalc header (or **`📱 Phone Setup`** in the top navigation).
3. A modal opens displaying a scannable **QR Code** pre-encoded with your active `.env` token:
   `https://phuture707.github.io/PEGMCPCOMMAND/calc.html#setup_pat=<YOUR_TOKEN>`
4. Point your phone's camera at your computer screen and tap the link notification.
5. The mobile calculator opens, detects `#setup_pat=...`, automatically saves your token into phone `localStorage`, and instantly wipes the token from the URL bar for security and clean sharing.
6. **You can now shut down your PC completely.** Your phone will remain connected to your empire whenever you open the link.

#### Method B: Direct In-Game Copy/Paste (No PC Needed At All)
1. On your phone's browser, navigate to [pegasus-galaxy.net](https://pegasus-galaxy.net) and log into your account.
2. Go to **Settings** -> **Profile** -> **MCP Access Token** -> tap **Copy Token** (`pg_pat_...`).
3. Open [`https://phuture707.github.io/PEGMCPCOMMAND/calc.html`](https://phuture707.github.io/PEGMCPCOMMAND/calc.html) on your phone.
4. Tap **`⚙️ Settings`** (or the connection pill) -> scroll down to **Option 2: Pegasus Cloud MCP via PAT**.
5. Paste your token into the field and tap **`🔑 Save & Connect Cloud MCP`**.
6. The phone confirms authentication and saves your token permanently to local mobile storage.

### 4. Local Wi-Fi Direct Access (While PC is Running)
If your computer is on and you want to control the full desktop Control Hub (all 67 tools, Bot Studio, Codex) from your phone on the same local network:
1. Start the GUI bound to all interfaces:
   ```bash
   python peg_gui.py --host 0.0.0.0
   ```
2. The console and `📱 Phone Setup` modal will display your local IP address:
   ```text
   📱 Mobile Phone Access: http://192.168.1.110:7890/calc
   ```
3. Open that address in your mobile browser while connected to your home Wi-Fi.

### 5. Running the Autonomous Bot 24/7 With PC OFF
A computer that is powered off cannot run Python code. While the **BattleCalc & Intel Radar** operate with the PC off (because the game server handles calculations), the **autonomous bot (`peg_bot.py`)** requires an active CPU to execute automated builds, mine upgrades, and attack-dodging logic.

To run the bot around the clock with your home computer off, deploy the suite to a **$3/month Linux Cloud VPS** using our included installer below.

---

## ☁️ 24/7 Cloud & VPS Deployment Guide (Optional)

You can run the suite indefinitely on any cheap Linux VPS (e.g. Hetzner, DigitalOcean, Linode, AWS EC2, Ubuntu/Debian).

### Automated 1-Click VPS Setup:
1. Transfer the suite folder to your VPS:
   ```bash
   scp -r PEGMCPCOMMAND root@YOUR_VPS_IP:/opt/peg-mcp
   ```
2. SSH into your VPS:
   ```bash
   ssh root@YOUR_VPS_IP
   cd /opt/peg-mcp
   ```
3. Set your token in `.env`:
   ```bash
   cp .env.example .env
   nano .env
   ```
4. Run the installer:
   ```bash
   chmod +x deploy_vps.sh
   ./deploy_vps.sh
   ```
The installer automatically sets up Python virtual environment, installs requirements, and registers two systemd services:
* `pegasus-bot`: Autonomous 24/7 background engine with automatic crash restart.
* `pegasus-gui`: Web Control Hub accessible on port 7890.

### Recommended Secure Access via SSH Tunnel (No Open Ports):
To keep port 7890 closed on your VPS firewall for maximum security, create an encrypted SSH tunnel from your desktop:
```bash
ssh -L 7890:localhost:7890 root@YOUR_VPS_IP
```
Then open `http://localhost:7890` on your desktop browser. It connects directly and securely to your remote VPS instance!

---

## 📚 Official Game IDs Reference (Buildings, Tech & Ships)

Whenever queuing actions in `bot_config.json`, writing custom strategies in `custom_strategies/`, or issuing direct MCP commands via GUI or CLI (`peg_tool.py`), use the exact server identifier strings:

### 🏗️ Constructions (`constructionId`) — 24 Buildings
Used with: `build_construction`, `cancel_construction`, and `repair_pds`

| Exact Construction ID | Building Name | Category | Lvl 1 Metal | Lvl 1 Crystal | Lvl 1 Eonium |
| :--- | :--- | :--- | :---: | :---: | :---: |
| `main-metal-mine` | Metal Mine | Economy | 60 | 15 | 0 |
| `main-crystal-synthesizer` | Crystal Synthesizer | Economy | 48 | 24 | 0 |
| `main-eonium-refinery` | Eonium Refinery | Economy | 225 | 90 | 0 |
| `main-metal-refinery` | Metal Refinery | Economy | 800 | 400 | 200 |
| `main-crystal-refinery` | Crystal Refinery | Economy | 1,000 | 500 | 250 |
| `main-mining-center` | Mining Center | Economy | 500 | 300 | 100 |
| `main-resource-vault` | Resource Vault | Economy | 1,000 | 500 | 0 |
| `main-power-plant` | Power Plant | Infrastructure | 75 | 30 | 0 |
| `main-city` | City | Infrastructure | 500 | 200 | 100 |
| `main-habitat` | Habitat | Infrastructure | 200 | 100 | 50 |
| `main-research-lab` | Research Lab | Science | 200 | 400 | 200 |
| `main-radar-station` | Radar Station | Science | 150 | 100 | 50 |
| `main-shipyard` | Shipyard | Military | 400 | 200 | 100 |
| `main-light-factory` | Light Factory | Military | 8,000 | 5,000 | 2,000 |
| `main-medium-factory` | Medium Factory | Military | 25,000 | 15,000 | 8,000 |
| `main-heavy-factory` | Heavy Factory | Military | 80,000 | 50,000 | 25,000 |
| `main-tactical-defence-system` | Tactical Defence System | Military | 300 | 150 | 50 |
| `main-intelligence-hq` | Intelligence HQ | Military | 500 | 300 | 200 |
| `main-wave-amplifier` | Wave Amplifier | Waves | 5,000 | 3,000 | 1,000 |
| `main-wave-distorter` | Wave Distorter | Waves | 8,000 | 4,000 | 2,000 |
| `main-missile-battery` | Missile Battery | Defence (PDS) | 2,000 | 0 | 0 |
| `main-laser-battery` | Laser Battery | Defence (PDS) | 1,500 | 500 | 0 |
| `main-ion-cannon` | Ion Cannon | Defence (PDS) | 2,000 | 2,000 | 500 |
| `main-shield-generator` | Planetary Shield | Defence (PDS) | 10,000 | 10,000 | 5,000 |

---

### 🔬 Research Technologies (`researchId`) — 12 Technologies
Used with: `start_research` and `cancel_research`

| Exact Research ID | Technology Name | Category | Lvl 1 Metal | Lvl 1 Crystal | Lvl 1 Eonium |
| :--- | :--- | :--- | :---: | :---: | :---: |
| `main-constructions` | Engineering | Population | 3,000 | 3,000 | 3,000 |
| `main-asteroid-mining` | Asteroid Mining | Mining | 4,000 | 4,000 | 4,000 |
| `main-core-mining` | Core Mining | Mining | 5,000 | 5,000 | 5,000 |
| `main-deep-core-mining` | Deep Core Mining | Mining | 8,000 | 8,000 | 8,000 |
| `main-prospecting` | Prospecting | Mining | 3,000 | 3,000 | 5,000 |
| `main-ship-technology` | Ship Technology | Ships | 5,000 | 3,000 | 2,000 |
| `main-hulls` | Hulls | Ships | 6,000 | 3,000 | 2,000 |
| `main-pds` | PDS Defense Tech | Ships | 8,000 | 5,000 | 4,000 |
| `main-advanced-scanning` | Advanced Scanning | Scans | 6,000 | 10,000 | 6,000 |
| `main-waves` | Waves | Scans | 3,000 | 5,000 | 3,000 |
| `main-hyperspace-travel` | Hyperspace Travel | Travel | 5,000 | 5,000 | 3,000 |
| `main-intelligence` | Covert Operations | Intelligence | 5,000 | 5,000 | 5,000 |

---

### 🚀 Ship Designs (`shipDefinitionId`) — 35 Ships
Used with: `produce_ships` (`{"shipDefinitionId": "...", "quantity": 10}`) and `launch_fleet`

| Exact Ship ID | Ship Name | Faction | Class | Unit Metal | Unit Crystal | Unit Eonium |
| :--- | :--- | :--- | :--- | :---: | :---: | :---: |
| `main-vanguard-centurion` | Centurion | Vanguard | Frigate | 10,000 | 4,000 | 1,500 |
| `main-vanguard-guardian` | Guardian | Vanguard | Frigate | 15,000 | 6,000 | 2,500 |
| `main-vanguard-sentinel` | Sentinel | Vanguard | Destroyer | 30,000 | 12,000 | 5,000 |
| `main-vanguard-titan` | Titan | Vanguard | Cruiser | 60,000 | 25,000 | 12,000 |
| `main-vanguard-colossus` | Colossus | Vanguard | Battleship | 150,000 | 75,000 | 40,000 |
| `main-vanguard-imperator` | Imperator | Vanguard | Battleship | 250,000 | 120,000 | 70,000 |
| `main-vanguard-sovereign` | Sovereign | Vanguard | Battleship | 400,000 | 200,000 | 120,000 |
| `main-vanguard-ironclad-freighter` | Ironclad Freighter | Vanguard | Transport | 12,000 | 4,000 | 2,000 |
| `main-vanguard-fortress-transport` | Fortress Transport | Vanguard | Transport | 35,000 | 12,000 | 6,000 |
| `main-vanguard-supply-runner` | Supply Runner | Vanguard | Transport | 5,000 | 2,000 | 1,000 |
| `main-vanguard-ore-extractor` | Ore Extractor | Vanguard | Miner | 8,000 | 3,000 | 1,500 |
| `main-vanguard-core-driller` | Core Driller | Vanguard | Miner | 20,000 | 8,000 | 4,000 |
| `main-vanguard-siege-harvester` | Siege Harvester | Vanguard | Miner | 50,000 | 20,000 | 10,000 |
| `main-ashkari-talon` | Talon | Ashkari | Fighter | 3,000 | 1,500 | 500 |
| `main-ashkari-fang` | Fang | Ashkari | Fighter | 4,500 | 2,000 | 800 |
| `main-ashkari-viper` | Viper | Ashkari | Fighter | 6,000 | 2,500 | 1,000 |
| `main-ashkari-raid-runner` | Raid Runner | Ashkari | Corvette | 5,000 | 2,500 | 1,500 |
| `main-ashkari-ravager` | Ravager | Ashkari | Frigate | 12,000 | 5,000 | 2,000 |
| `main-ashkari-marauder` | Marauder | Ashkari | Destroyer | 28,000 | 10,000 | 4,500 |
| `main-ashkari-reaper` | Reaper | Ashkari | Destroyer | 45,000 | 18,000 | 8,000 |
| `main-ashkari-oblivion` | Oblivion | Ashkari | Battleship | 180,000 | 85,000 | 45,000 |
| `main-ashkari-plunder-barge` | Plunder Barge | Ashkari | Transport | 10,000 | 3,500 | 1,500 |
| `main-ashkari-claw-extractor` | Claw Extractor | Ashkari | Miner | 7,500 | 2,500 | 1,200 |
| `main-synthara-pulse` | Pulse | Synthara | Fighter | 3,500 | 2,000 | 1,000 |
| `main-synthara-arc` | Arc | Synthara | Fighter | 5,000 | 3,000 | 1,500 |
| `main-synthara-nexus` | Nexus | Synthara | Fighter | 7,000 | 4,000 | 2,000 |
| `main-synthara-pulse-courier` | Pulse Courier | Synthara | Corvette | 6,000 | 3,500 | 2,000 |
| `main-synthara-monolith` | Monolith | Synthara | Cruiser | 55,000 | 30,000 | 15,000 |
| `main-synthara-oracle` | Oracle | Synthara | Battleship | 140,000 | 80,000 | 45,000 |
| `main-synthara-obelisk` | Obelisk | Synthara | Battleship | 220,000 | 130,000 | 75,000 |
| `main-synthara-singularity` | Singularity | Synthara | Battleship | 380,000 | 220,000 | 130,000 |
| `main-synthara-nexus-freighter` | Nexus Freighter | Synthara | Transport | 14,000 | 6,000 | 3,000 |
| `main-synthara-singularity-hauler` | Singularity Hauler | Synthara | Transport | 40,000 | 18,000 | 9,000 |
| `main-synthara-crystal-borer` | Crystal Borer | Synthara | Miner | 9,000 | 4,500 | 2,000 |
| `main-synthara-void-harvester` | Void Harvester | Synthara | Miner | 45,000 | 22,000 | 11,000 |

*(Tip: In the GUI Dashboard, open the **📚 Game Codex & IDs** tab to filter and copy any ID with one click, or use `python3 peg_tool.py --reference` in the terminal!)*

---

## ❓ Troubleshooting & FAQ

* **Can I run the Web GUI and the Bot locally at the same time on my PC / Mac?**
  * *Yes!* You can launch `peg_gui.py` and click **"Start Bot Process"** directly inside the Bot Studio tab. The GUI spawns the local bot as a child process and streams its live logs right into your browser. Alternatively, open two terminal windows and run `python peg_gui.py` in one and `python peg_bot.py` in the other.
* **Does it work on macOS?**
  * *Yes*. Full macOS support is verified for both Intel and Apple Silicon (M1/M2/M3/M4). Subprocess detachment, terminal formatting, paths, and automatic browser launch operate natively.
* **Do I need a cloud VPS?**
  * *No*. A VPS is only needed if you want the bot to keep running around the clock while your computer is turned off. While your computer is running, running everything locally is 100% functional.
* **Can I run the bot locally while my PC/Mac is on, then deploy to a VPS?**
  * *Yes*. See the [Dual-Environment & Git Deployment Workflow](#-dual-environment--git-deployment-workflow) section above. You can test and refine your strategy locally, `git push` to your repository, and `git pull` on your VPS so the bot advances your colony 24/7 while your computer is powered off.
* **Are my API token and logs exposed in Git?**
  * *No*. `.env`, `bot.log`, `bot_state.json`, and `bot_memory.json` are listed in `.gitignore` and remain strictly local to each machine.
* **Issue: "Token is missing or invalid"**
  * *Fix*: Ensure your `.env` file contains `PEGASUS_PAT=pg_pat_...`. Verify the token in your Pegasus Galaxy settings.
* **Issue: "Action Quota Exceeded"**
  * *Fix*: The game enforces an action quota per 30-minute tick. Adjust `max_actions_per_tick` in `bot_config.json` (or in GUI Bot Studio) to a lower number (e.g., 5-8).
* **Issue: "Port 7890 is already in use"**
  * *Fix*: Specify a different port using `python3 peg_gui.py --port 8080`.

*Developed for the Pegasus Galaxy interstellar commander community • Version 0.5*