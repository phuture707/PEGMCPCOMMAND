# 🌌 Pegasus Galaxy MCP Suite v0.5 — Web GUI, Bot Engine, Combat Simulator & CLI Inspector

A production-ready Python client, interactive web control dashboard, multi-fleet battle simulator, and autonomous bot suite for [Pegasus Galaxy](https://pegasus-galaxy.net/mcp), connected via Model Context Protocol (MCP 2025-03-26 Streamable HTTP).

[![Suite Version](https://img.shields.io/badge/Version-0.5-orange)](https://github.com/phuture707/PEGMCPCOMMAND)
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

## ⚔️ What's New in v0.5

- **Universal Tactical Color Standards**: Strict color-coding across all elements, matrices, logs, and summary cards—Defenders are always **Blue** (`#38bdf8` / `#60a5fa`) and Attackers are always **Red** (`#ef4444` / `#f87171`), preventing orientation confusion during side swaps.
- **Stationary Defense & Base Garrison Isolation**: Attackers cannot add Planetary Defense Structures (PDS) or home base garrisons (`__hangar__`) from fleet dropdowns, empire presets, or scan pickers. Consolidated attacker imports automatically exclude stationary planetary garrison defenses.
- **PDS Side-Swap Safety Confirmation**: Swapping simulator sides when PDS units are deployed triggers a confirmation warning indicating PDS will be reset (as PDS are defender-only structures).
- **Friendly Fire & Coalition Conflict Warning**: Detects and prompts when allied or self-owned fleets are placed on opposing battle lines.
- **Granular Combat Initiative & Firing Log**: Round-by-round breakdown recording shooter side, fleet name, firing unit counts, target fleet, damage dealt, and destroyed units.
- **Projected Score Dynamics & Ship Value Impact**: Comprehensive financial and leaderboard analytics for **each individual fleet** in battle:
  - Total resource value ($Metal + Crystal + Eonium$).
  - Pegasus score value ($\frac{Res}{9}$) lost and surviving.
  - Net score delta ($\Delta$) and debris salvage score equivalence.
- **Default Matrix Mode Layout**: Streamlined multi-fleet spreadsheet matrix loaded as standard across both GUI and Standalone BattleCalc.

---

## 🛡️ Key Features in v0.45 & v0.4

- **Hybrid Standalone + MCP BattleCalc Bridge (`docs/calc.html` / GitHub Pages)**:
  - **Zero-Dependency Public Standalone Mode**: Anyone (even alliance members and players without Python, MCP, or `.env` files) can use the complete dual-matrix battle calculator directly in their web browser via GitHub Pages (`https://phuture707.github.io/PEGMCPCOMMAND/calc.html`) or offline single-file HTML export (`💾 Export HTML`).
  - **Zero-Click MCP Auto-Activation**: When opened by a player running the local Pegasus Control Suite (`python peg_gui.py` on port 7890), `docs/calc.html` automatically probes the local daemon on load. **Requires zero clicks or activation buttons**—it instantly transitions from standalone mode to live 🟢 **`MCP Connected`** mode!
  - **Secure `.env` & Game Session Access**: The browser client leverages the local Python daemon's existing authenticated `.env` session, completely eliminating the need for browser filesystem permissions or re-authenticating credentials.
  - **Automatic Empire & Garrison Ingestion**: Dynamically populates your empire's named fleets and docked hangar ships into fleet selection dropdowns, and automatically initializes your home base Garrison and Planetary Defense Structures (PDS levels 1–4) into the Defender matrix on startup if empty.
  - **Interactive Scan Browser & Fleet Picker Modal (`🔍 Browse Scans`)**: Browse, search, and import personal scans (`get_scan_history`) and alliance shared intel (`get_scan_intel`) directly into Defender or Attacker matrix columns with 1 click (Garrison, Named Fleets, or Consolidated Forces).
  - **30-Second Background Scan Polling**: Automatically queries for new scans conducted by alliance members in the background every 30 seconds, alerting commanders with live notifications when fresh intel arrives.
  - **Multi-Calculation Sessions System (`#calc-multi-tabs-bar`)**: Work on multiple simultaneous battles (`Calc #1`, `Calc #2`, `➕ New Tab`, `📋 Duplicate`, `✏️ Rename`, `✕ Close`) within the same standalone window.
  - **Dual-Side Matrix Actions**: Complete parity with the Control Suite—`+ Fleet`, `🏰 Load Base/Fleets`, `⚡ Consolidate`, `🔍 Browse Scans`, `🏰 Add Own Fleet...`, and `📡 Pick Scanned Target...` controls across both Defender and Attacker columns.
  - **Tactical Defense Auto-Setup (`[🛡️ Plan Defense at Tick X]`)**: Evaluates arriving vs late fleets at target tick $T$, inbound attacker coalitions, scan reliability ratings (0–100%), and decoy/feint detection.
  - **Remote / Mobile Token Fallback**: Commanders opening `docs/calc.html` on mobile phones or remote devices without `peg_gui.py` running locally can optionally enter their Personal Access Token (`pat_...`) in the connection modal for direct game access.
  - **Client-Side URL Hash Compression (`#c=...`)**: Compressed via native browser `CompressionStream('deflate-raw')` / Base64URL into permanent, serverless links that preserve complete battle scenarios without external databases.
  - **"💬 In-Game Message Dispatch"**: 1-click modal to dispatch tactical battle briefings, casualty projections, and public calculation links directly to alliance members' in-game mailboxes via MCP `send_message`.
  - **Shared Link Recipient Experience (MCP vs Standalone)**:
    When a commander shares a public calculation link (`https://...calc.html#c=...`), the recipient automatically receives the complete battle plan. If the person opening it has `peg_gui.py` running on their computer, the page automatically detects their local MCP suite, illuminates `⚡ MCP Enhanced Mode: Detected & Enabled`, and overlays their own empire's active fleets, live ticks, and alliance scans:

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

## ⚔️ What's New in v0.35

- **Standalone BattleCalc & Multi-Window Architecture (`/calc` & `peg_calc.py`)**:
  - **Zero Server Overhead**: Run unlimited independent calculation windows and tabs simultaneously off the same single Python server without spawning multiple server processes.
  - **Dedicated `/calc` Route**: Direct, ultra-lean Battle Matrix endpoint with no background polling, stripped navigation, and full-width combat view.
  - **1-Click "↗️ Pop Out to Window"**: Instantly export any calculation snapshot (fleets, scans, PDS, coordinates) into a new independent window, with 1-click option to start fresh on the original window.
  - **Multi-Calculation Tabs**: Manage multiple simultaneous battle calculations within the same window (`[Calc #1: 12:1:1] [Calc #2: Base Defense] [+]`), switch instantly, duplicate, rename, or pop any tab out.
  - **Standalone Launcher (`python peg_calc.py [COORDS]`)**: Instantly connects to the active server or starts it in the background, pre-loading coordinates if specified.
- **Live In-Simulator Scan Execution ("Add from Scan")**:
  - Interactively trigger live scans directly from the Combat Simulator for any galaxy coordinates (`X:Y:Z`).
  - Supports all scan protocols (`FLEET_COMPOSITION_SCAN`, `MILITARY_SCAN`, `DEEP_SCAN`).
  - Automatic quota guard (3 scans per tick maximum limit), live eonium balance verification, and wave distorter detection alerts.
  - Automatically parses scan results into a dedicated fleet column and attaches scan timestamp and coordinates to the view.
- **Default Combat Matrix Mode**:
  - BattleCalc matrix layout is now the default view upon launch with optimized high-density column spacing and clear fleet boundaries.
  - Scan coordinates reference stamp at the base of the matrix view (editable for manual simulation labeling without altering server state).
  - Streamlined fleet management: auto-cleans empty placeholder fleets when adding live base scans or player fleets.
- **Tactical Battle Simulator & Coalition Calculator (Tab 8)**:
  - **Direct Coordinate Entry & Latest Scans Dropdown**: Enter coordinates directly (e.g. `12:1:1`, `12, 1, 1`, `12 1 1`) or jump via universe planet picker to instantly view a dedicated dropdown of the latest scans for those coordinates (sorted newest tick first) with auto-population of garrison, fleets, and PDS.
  - **Alliance Scan Intelligence Ingestion (`get_scan_intel`)**: Automatically detects alliance membership and queries shared alliance scans alongside personal scan history (`get_scan_history`), with universe map coordinate enrichment and error resilience.
  - **Source Search & Filtering**: Segmented filter pills (`🌐 All Scans`, `👤 My Scans`, `🤝 Ally Intel`) across target selectors, dropdowns, and the Scan Picker modal.
  - **CLI Battle Simulator Coordinate & Source Support**: Run `python peg_tool.py --battle-calc --defender <COORDS> [--source {all,user,ally}]` with automatic multi-scan comparison tables and latest scan selection.
  - **Multi-Fleet Coalitions**: Support for multiple attacking and defending fleets simultaneously. Add, remove, rename, and individually enable/disable fleets in simulation calculations.
  - **Live Coalition Telemetry**: Real-time aggregate counters for active fleets, total ship counts, firepower estimation, armor, cargo capacity, and asteroid hauling capacity.
  - **Comprehensive Scan Type Ingestion**: Ingests all combat-capable scan types (`FLEET_COMPOSITION_SCAN`, `MILITARY_SCAN`, `DEEP_SCAN`, `INCOMING_SCAN`) from scan history.
  - **Planetary Intelligence Resolution**: Automatically resolves coordinates, planet ownership, and defense structures across multiple scans for focused scans lacking direct coordinates.
  - **Accurate PDS Ground Structure Modeling**: Isolates ground defense batteries (`pds-...`) from ship manifests, modeling them strictly as planetary defense structures with live level multipliers.
  - **Interactive Scan Chooser & Visual Picker**:
    - Inline quick-add dropdown (`📡 Add from Scan...`) directly in Attacker and Defender headers.
    - Full visual scan browser modal (`🔍 Browse Scans`) with search filtering, source badges, scan type badges, ship breakdowns, and 1-click fleet deployment.
  - **Tactical Role Inversion**: Instant 1-click roster swap between Planetary Assault and Home Base Defense modes.

---

## 🚀 What's New in v0.3

- **Interactive Setup Assistant (`setup_env.py` / `setup.py`)**:
  - Automatic guided Personal Access Token (PAT) setup with quotation and whitespace cleaning.
  - Existing `.env` protection with masked token preview (`pg_pat_xxxx...xxxx`).
  - Pre-flight connection test against the Pegasus Galaxy MCP server (`tools/list`).
  - 1-click launch prompt to start `peg_gui.py` directly upon setup completion.
- **Planetarion BattleCalc Interface (`bcalc.pl`)**:
  - Optional side-by-side battle matrix view for attacker and defender forces.
  - Quick hull category filter pills (`Fi`, `Co`, `Fr`, `De`, `Cr`, `Bs`, `PDS`).
  - Per-fleet casualty breakdown panels: detailed **Arrived**, **Lost**, and **Survivors** counts, plus Salvage and Asteroid plunder metrics.
  - Authentic Planetarion format output in CLI (`peg_tool.py --battle-calc --format bcalc`).
- **Alliance & Cross-Scan Intelligence Search**:
  - Manual coordinate entry (`X:Y:Z`) with live coordinate resolution.
  - Unified search across personal scans and shared alliance intelligence with quick filter pills (`All`, `Mine`, `Alliance`).

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

### Step 3: Configure Your Access Token (Automated or Manual)

**Option A (Recommended — Automated Setup):**
Run the interactive setup assistant:
```bash
python setup_env.py
```
*Prompts for your Pegasus Galaxy API key / Personal Access Token, automatically generates your `.env` file, tests the server connection, and gives you a 1-click launch to `peg_gui.py`!*

**Option B (Manual):**
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

## 🎮 The 8 Web GUI Tabs (`peg_gui.py`)

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
8. **⚔️ Battle Simulator & Coalition Calculator**:
   - Tactical sandbox with live telemetry, personal scans, and alliance intel integration.
   - **View Layouts**: Default **📊 Matrix Mode** (side-by-side combat grid matching classic BattleCalc engines) with optional **🗂️ Cards View**.
   - **Hybrid Standalone Calculator (`docs/calc.html` / GitHub Pages)**:
     - **Offline / Non-MCP Mode**: 100% client-side simulation, shareable Deflate-raw compressed URLs (`#c=...`), and single-file HTML exports.
     - **Zero-Click MCP Integration**: When `peg_gui.py` is active, `docs/calc.html` auto-probes the local daemon on load with zero clicks needed, connects securely without exposing `.env` files, loads active empire fleets/PDS, provides the interactive **Scan Browser Modal** (`🔍 Browse Scans`), and auto-polls alliance intel every 30 seconds.
     - **Multi-Calculation Sessions**: Manage multiple parallel scenarios with tabs (`Calc #1`, `Calc #2`, `➕ New Tab`, `📋 Duplicate`, `✏️ Rename`).
     - **Tactical Defense Auto-Setup**: 1-click auto-planning for target tick $T$ with fleet arrival partitioning, reliability ratings (0–100%), and decoy detection.
   - Generates per-fleet **Report of Losses from [Fleet]** tables, salvage predictions, and asteroid/resource plunder dynamics.

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

# Interstellar Fleet Battle Simulator & Coalition Calculator
python peg_tool.py --battle-calc --defender 12:1:1
python peg_tool.py --battle-calc --defender 12:1:1 --format bcalc   # Planetarion format!
python peg_tool.py --battle-calc --defend --source ally

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

## 📱 Mobile Phone Access & Zero-PC Cloud Architecture

The Standalone BattleCalc and Live MCP Intel can be operated directly from your **mobile phone (iOS Safari / Android Chrome)** anywhere in the world — **even with your home PC completely turned OFF**.

### 1. Mobile-Friendly Layout
- **Vertical Auto-Stacking**: On screens under 960px, Defender forces (Blue) and Attacker coalitions (Red) stack vertically, giving each side 100% full-screen width.
- **Sticky Ship Names**: Swiping horizontally through fleet columns locks the first column (**Ship / Class**) on the left so you always know which ship row you are editing.
- **Touch Ergonomics & Responsive Modals**: Input fields and dialog modals automatically adapt to smartphone viewports (`max-width: 96vw; max-height: 88vh;`) and prevent iOS Safari auto-zoom.

### 2. How MCP Works on a Phone with PC OFF
When your home PC is turned off, the PC's hard drive and `.env` file cannot be reached. Instead:
1. **The Game's MCP Server is in the Cloud**: Pegasus Galaxy hosts its official MCP server 24/7 at `https://mcp.pegasus-galaxy.net`.
2. **The Web Calculator is in the Cloud**: Hosted 24/7 on GitHub Pages at `https://phuture707.github.io/PEGMCPCOMMAND/calc.html`.
3. **Phone Browser Persistent Storage (`localStorage`)**: Your authentication token is stored in your phone's browser `localStorage` (`peg_mcp_pat`), which lives in your phone's physical flash storage across tab closures and device reboots.
4. **Direct HTTPS Bridge**: Your phone talks directly to `https://mcp.pegasus-galaxy.net` over mobile data (5G/LTE) or Wi-Fi. Live radar, scans, and defense planning work with zero PC required!

### 3. How to Transfer Your Token to Your Phone
- **Method A: 1-Click QR Code Transfer (Fastest)**:
  1. In the desktop GUI (`peg_gui.py`), click **`📱 Connect Phone`** (or **`📱 Phone Setup`** in the main header).
  2. Point your phone's camera at the QR code on your PC monitor.
  3. Tap the link: the calculator opens and automatically saves your token into phone `localStorage`, then removes it from the URL bar for privacy.
  4. **You can now shut down your PC completely.**
- **Method B: Direct In-Game Copy/Paste (No PC Needed)**:
  1. On your phone browser, log into [pegasus-galaxy.net](https://pegasus-galaxy.net) -> **Settings / Profile / MCP Token** -> Copy token.
  2. Open `https://phuture707.github.io/PEGMCPCOMMAND/calc.html` on your phone.
  3. Tap **`⚙️ Settings`** -> scroll to **Option 2: Pegasus Cloud MCP via PAT**.
  4. Paste your token and tap **`🔑 Save & Connect Cloud MCP`**.

### 4. Local Wi-Fi Access (While PC is Running)
If you want to view the full desktop Control Hub on your phone while your PC is on:
1. Run `python peg_gui.py --host 0.0.0.0`.
2. Open `http://<YOUR-PC-IP>:7890/calc` (e.g. `http://192.168.1.110:7890/calc`) on your phone browser.

### 5. Running the Automated Bot While PC is OFF
A powered-off computer cannot execute Python scripts. If you want the **automated bot (`peg_bot.py`)** to auto-build mines, repair defenses, and dodge incoming attacks 24/7 while your PC is off, run the suite on a cheap **$3/month Linux Cloud VPS** using our included `deploy_vps.sh` or Docker setup below.

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