# 🌌 Pegasus Galaxy MCP Suite — Complete User & Operations Guide

Welcome to the **Pegasus Galaxy Model Context Protocol (MCP) Suite**. This package provides a comprehensive, production-ready suite of tools to interact with, inspect, automate, and dominate the interstellar universe of [Pegasus Galaxy](https://pegasus-galaxy.net).

[![GitHub Repository](https://img.shields.io/badge/GitHub-phuture707%2FPEGMCPCOMMAND-blue?logo=github)](https://github.com/phuture707/PEGMCPCOMMAND)
[![MCP Version](https://img.shields.io/badge/MCP-2025--03--26-cyan)](https://pegasus-galaxy.net/mcp)
[![Python Version](https://img.shields.io/badge/Python-3.10%2B-brightgreen)](https://python.org)

**Official GitHub Repository:** [https://github.com/phuture707/PEGMCPCOMMAND](https://github.com/phuture707/PEGMCPCOMMAND)

---

## 📑 Table of Contents
1. [Official Repository & Installation](#-official-github-repository)
2. [Quickstart (3-Step Setup)](#-quickstart-3-step-setup)
3. [Suite Architecture & Components](#-suite-architecture--components)
4. [Tool 1: Web Control Hub (`peg_gui.py`)](#-tool-1-web-control-hub-peg_guipy)
5. [Tool 2: Autonomous Game Bot (`peg_bot.py`)](#-tool-2-autonomous-game-bot-peg_botpy)
6. [Tool 3: Terminal CLI Inspector (`peg_tool.py`)](#-tool-3-terminal-cli-inspector-peg_toolpy)
7. [Tool 4: Python Client SDK (`peg_client.py`)](#-tool-4-python-client-sdk-peg_clientpy)
8. [Strategy Profiles & Custom Python Scripts](#-strategy-profiles--custom-python-scripts)
9. [24/7 Cloud & VPS Deployment Guide](#-247-cloud--vps-deployment-guide)
10. [Troubleshooting & FAQ](#-troubleshooting--faq)

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

## ⚡ Quickstart (3-Step Setup)

### Step 1: Install Python Dependencies
Ensure Python 3.10+ is installed, then run:
```bash
pip install -r requirements.txt
```

### Step 2: Configure Your Personal Access Token
1. Copy the sample environment file:
   ```bash
   cp .env.example .env     # Linux / macOS
   copy .env.example .env   # Windows
   ```
2. Open `.env` in any text editor and paste your personal access token (PAT):
   ```env
   PEGASUS_PAT=pg_pat_your_actual_token_here
   ```
   *(Find or generate your token under your player profile or settings at https://pegasus-galaxy.net)*

### Step 3: Launch the Web Dashboard
```bash
python peg_gui.py
```
Your default browser will automatically open **`http://localhost:7890`**.

---

## 🧩 Suite Architecture & Components

```
pegasus-mcp-suite/
├── peg_gui.py              # Interactive sci-fi web control dashboard & Bot Studio
├── peg_bot.py              # Autonomous 24/7 tick-synchronized background bot
├── peg_tool.py             # Rich terminal CLI inspector & command runner
├── peg_client.py           # Core Python MCP client SDK (JSON-RPC / Streamable HTTP)
├── bot_config.json         # Active Layer 1 automation rules & priorities
├── bot_strategy.py         # Active Layer 2 Python strategy hook (live-reloaded)
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
├── requirements.txt        # Python package dependencies
├── .env.example            # Sample credentials file
└── INSTRUCTIONS.md         # Complete user and operations manual
```

---

## 🌐 Tool 1: Web Control Hub (`peg_gui.py`)

A full-featured, zero-external-frontend-dependency web application styled with a cyber/sci-fi space aesthetic. It runs on Python's built-in threaded HTTP server.

### How to Run:
* **Local Desktop Mode** (auto-launches browser):
  ```bash
  python peg_gui.py
  ```
* **Headless / VPS Server Mode** (accessible remotely):
  ```bash
  python peg_gui.py --host 0.0.0.0 --port 7890 --no-browser
  ```

### Dashboard Tabs & Features:
1. **📊 Mission Control**:
   - **Colony Telemetry**: Real-time metal, crystal, eonium reserves, and net production rates.
   - **Tick Countdown Clock**: Synchronized with Pegasus Galaxy server 30-minute ticks.
   - **Player Rank & Civilization Intel**: Population allocation, level, and race traits.
   - **Active Construction & Research Progress**: Visual progress bars and completion timers.
   - **Fleet Tracker**: Incoming and outgoing space fleets with coordinates and ETAs.
   - **Quota Guard Meter**: Tracks modifying actions used during the current tick window.
2. **🛠️ Command Hub (All 67 Tools)**:
   - Searchable, categorized command palette (*Colony, Military, Social, Meta, Memory*).
   - Dynamic form generator: reads the tool parameter JSON schemas and renders inputs.
   - Safety badges: distinguishes between safe `[READ]` queries and quota-consuming `[ACTION]` commands.
3. **🎯 Quests & Missions**:
   - Live quest tracker for story missions, daily objectives, and achievements.
   - **"Claim All Rewards"**: Single-click button to collect all completed rewards in one batch.
4. **🚀 Hangar & Ship Codex**:
   - Ships categorized side-by-side by race (**Vanguard**, **Synthara**, **Ashkari**).
   - Filterable by combat class (**Light**, **Medium**, **Heavy**, **Special**).
   - Deep combat metrics: Armor, Direct Firepower, EMP Damage, Sublight Speed, Fuel Burn/Capacity, and Cargo capacity.
   - **Planetary Defense Structures (PDS)**: Live defense status showing active health points (HP), level, damage state, and base weapon stats.
5. **🧠 Agent Memory**:
   - Persistent key-value memory scratchpad for recording intelligence, diplomatic notes, or target coordinates.
6. **🤖 Bot Studio**:
   - Start, stop, and monitor the autonomous bot daemon directly from your browser.
   - **Layer 1 Automation Rules**: Configure auto-claim, auto-repair, auto-build, auto-research, and action safety caps. Load and save named profiles to `config_profiles/`.
   - **Layer 2 Python Strategy Hook**: Edit custom Python strategy code in an embedded dark-theme editor. Save scripts to `custom_strategies/` and deploy them to `bot_strategy.py` with 1 click (live reloads on the next tick).
   - **Specific Command Dispatcher & Task Scheduler**: Queue any of the 67 commands to run immediately, on the next tick, or on recurring tick intervals (every N ticks).
   - **Live Log Streamer**: Real-time console showing tick evaluations, server responses, and decisions.

---

## 🤖 Tool 2: Autonomous Game Bot (`peg_bot.py`)

A robust, 24/7 background worker engineered to never waste a game tick.

### Core Philosophy:
* **Tick Synchronization**: The bot queries the server for `get_tick_info()`, calculates the exact seconds remaining in the current 30-minute game cycle, and sleeps until the new tick fires.
* **Quota Safety Cap**: Never exceeds your designated `max_actions_per_tick` (default 8) to protect against accidental action overdrafts.
* **Two-Layer Strategy Pipeline**:
  1. **Layer 1 (Declarative Rules)**: Evaluates mission claims, checks PDS defense health, triggers prioritized building upgrades, and queues tech research.
  2. **Layer 2 (Custom Python Script)**: Dynamically imports `bot_strategy.py` and executes `on_tick(client, state, config, logger)` for custom tactics.

### Command-Line Arguments:
```bash
# Run 24/7 background daemon
python peg_bot.py

# Run a single tick evaluation and exit immediately (ideal for testing or cron jobs)
python peg_bot.py --once

# Dry-run mode: evaluate logic and log decisions without executing modifying actions
python peg_bot.py --once --dry-run

# Specify custom configuration or strategy paths
python peg_bot.py --config custom_config.json --strategy custom_strategy.py
```

---

## 💻 Tool 3: Terminal CLI Inspector (`peg_tool.py`)

A command-line tool equipped with Rich formatting for terminal enthusiasts, SSH sessions, and script automation.

### Commands Reference:
```bash
# 1. Print full colony telemetry dashboard (resources, tick timer, buildings, fleets)
python peg_tool.py

# 2. List all 67 tools with argument descriptions
python peg_tool.py --tools

# 3. Check quests, achievements, and completed mission rewards
python peg_tool.py --missions

# 4. Call any MCP tool with optional JSON arguments
python peg_tool.py --call get_player_rank
python peg_tool.py --call list_construction_options
python peg_tool.py --call build_construction --args '{"constructionId": "main-metal-mine"}'
python peg_tool.py --call get_leaderboard --args '{"limit": 10}'

# 5. List and inspect MCP resources
python peg_tool.py --resources
python peg_tool.py --read pegasus://ship/definitions
python peg_tool.py --read pegasus://construction/definitions

# 6. Read game rules and mechanics
python peg_tool.py --rules overview
python peg_tool.py --rules combat
python peg_tool.py --rules constructions
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

# Call any arbitrary tool
res = client.call_tool("get_planet_ships")
print(f"Ships in hangar: {res}")

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
Custom scripts reside in `custom_strategies/`. When a script is activated, it is copied to `bot_strategy.py` and reloaded live every tick.

Sample Strategy Hook Structure:
```python
def on_tick(client, state, config, logger):
    logger("🚀 Executing custom strategy hook...")
    planet = state.get("planet", {}).get("data", {})
    resources = planet.get("resources", {})
    
    # Access your Layer 1 rules via the 'config' argument
    max_actions = config.get("max_actions_per_tick", 8)
    
    # Write your own custom logic
    if resources.get("metal", 0) > 100000:
        logger("Surplus metal detected! Launching specialized action...")
```

---

## ☁️ 24/7 Cloud & VPS Deployment Guide

You can run the suite indefinitely on any cheap Linux VPS (e.g. Hetzner, DigitalOcean, Linode, AWS EC2, Ubuntu/Debian).

### Automated 1-Click VPS Setup:
1. Transfer the suite folder to your VPS:
   ```bash
   scp -r pegasus-mcp-suite root@YOUR_VPS_IP:/opt/peg-mcp
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

Whenever queuing actions in `bot_config.json`, writing custom strategies in `custom_strategies/`, or issuing direct MCP commands via GUI or CLI (`peg_tool.py`), you must use the exact server identifier strings:

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

*(Tip: In the GUI Dashboard, open the **📚 Game Codex & IDs** tab to filter and copy any ID with one click, or use `python peg_tool.py --reference` in the terminal!)*

---

## ❓ Troubleshooting & FAQ

* **Issue: "Token is missing or invalid"**
  * *Fix*: Ensure your `.env` file contains `PEGASUS_PAT=pg_pat_...`. Verify the token in your Pegasus Galaxy settings.
* **Issue: "Action Quota Exceeded"**
  * *Fix*: The game enforces an action quota per 30-minute tick. Adjust `max_actions_per_tick` in `bot_config.json` (or in GUI Bot Studio) to a lower number (e.g., 5-8).
* **Issue: "Port 7890 is already in use"**
  * *Fix*: Specify a different port using `python peg_gui.py --port 8080`.
* **Issue: Can I run both GUI and Bot at the same time?**
  * *Yes*. In fact, the GUI Bot Studio has built-in buttons to start, stop, and monitor the bot daemon seamlessly.

---
*Developed for the Pegasus Galaxy interstellar commander community.*
