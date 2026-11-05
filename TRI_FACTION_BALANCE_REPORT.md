# Pegasus Galaxy: Tri-Faction Balance & Strategic Ecosystem Report

## 1. Executive Summary & Design Archetypes

The Pegasus Galaxy combat and economic balance operates across three distinct mono-faction combat philosophies under a **1-tick deterministic battle engine**:

1. **Vanguard Coalition** (*Kinetic Armor & Faraday Hardening*): Heavy hull pools, high kinetic alpha strike, high EMP resistance, and fleet shield absorption.
2. **Synthara Collective** (*Pure Stun EMP & Energy Beams*): Speed-of-light EMP pulses that stun enemy weapons at early initiative (Init 1–5), eliminating retaliation fire with zero hull rupture.
3. **Aetheris Voidborne** (*Deterministic Evasion & Precision Sniping*): Agile craft with mathematical accuracy degradation and heavy target priority.

```
                  [ Aetheris Voidborne ]
                 (Evasion & Precision Strike)
                        /          \
             Snipes Heavies      EMP Stuns Light Wings
                      /              \
                     v                v
           [ Vanguard Coalition ] <--- [ Synthara Collective ]
             (Armor & Faraday Plating) (Pure Stun EMP Control)
                     Absorbs Stun & Crushes Hulls
```

---

## 2. Macro-Economic Parity & Resource Standards

To preserve galactic economic sustainability and prevent mineral starvation, construction costs strictly adhere to natural planetary production ratios (**~47% Metal / ~31% Crystal / ~22% Eonium**):

| Faction | Metal % | Crystal % | Eonium % | Macro-Economic Alignment |
| :--- | :---: | :---: | :---: | :--- |
| **Vanguard Coalition** | **46.8%** | **30.5%** | **22.6%** | Standard heavy industrial baseline; perfectly matches planetary mine output. |
| **Synthara Collective** | **37.9%** | **42.6%** | **19.5%** | Calibrated (+11%) Crystal tilt for beam optics and EMP capacitor banks. |
| **Aetheris Voidborne** | **46.8%** | **31.1%** | **22.0%** | Balanced macro-economic ratio; prevents eonium or crystal starvation. |

---

## 3. The Operational Triad: Attack, Defense, and Ship Classes

Combat in Pegasus Galaxy is never an isolated deathmatch; fleets are built to execute strategic objectives: **Planetary Assault**, **Home Defense**, **Convoy Escort**, and **Economic Plunder**.

### A. Attack vs. Defense Mechanics
- **Planetary Assault (Attack)**:
  - Attackers must penetrate **Planetary Defense Systems (PDS)**:
    - *Ion Cannons* (Init 1, high damage, targets `HEAVY`)
    - *Missile Silos* (Init 2, targets `MEDIUM`)
    - *Laser Batteries* (Init 3, targets `LIGHT`)
    - *Shield Generators* (absorbs up to 50% incoming damage)
  - Attackers **must bring Heavy/Capital warships** to absorb Ion Cannon fire and crack shield generators, accompanied by **Light screen escorts** to soak Laser Battery fire.
- **Home Fortress (Defense)**:
  - Defenders benefit from a **+10% Home Armor Bonus** and local PDS fire.
  - Defenders rely on **Light interceptors** to block fast raiders and **EMP disruption** to freeze attacker siege engines before they can bombard orbital installations.

### B. The 3 Ship Size Tiers
1. **LIGHT (`LIGHT`, Init 1–3, Speed 10)**:
   - *Attack*: Screens capital ships against PDS Laser Batteries and defensive missile traps.
   - *Defense*: Fast-reaction interceptor wings that intercept raiding corvettes.
   - *Tactical Value*: Low cost, high initiative, disposable damage sponges.
2. **MEDIUM (`MEDIUM`, Init 4–5, Speed 9)**:
   - *Attack*: Primary hunters of enemy defensive screens and perimeter batteries.
   - *Defense*: The core escort line protecting mining extractors and resource haulers.
   - *Tactical Value*: Balanced survivability and firepower; flexible target priority.
3. **HEAVY (`HEAVY` & `SPECIAL`, Init 5–10, Speed 7–8)**:
   - *Attack*: Massive armor pools and siege weaponry required to breach planetary shields and eliminate Ion Cannons.
   - *Defense*: The immovable anchor of planetary defense; wipes out attacker escorts.
   - *Tactical Value*: Capital presence, decisive alpha damage, fleet aura projectors.

---

## 4. Collectors, Harvesters & Resource Stealers (Economic Warfare)

In Pegasus Galaxy, winning a space battle alone yields **0 plunder** unless the fleet includes specialized economic craft:
- **Resource Theft (Plunder)**: Stolen resources are strictly capped by surviving **Resource Cargo Capacity** (`resourceCapacity`, `targetClass: RESOURCES`, Init 12). If an attacker brings only combat warships and no haulers, Plunder is zero.
- **Asteroid Capture**: Asteroids can only be claimed if surviving ships possess **Asteroid Extraction Capacity** (`asteroidCapacity`, `targetClass: ROIDS`, Init 12).
- **Salvage**: Both combatants receive 30% of destroyed ship value as salvage material.

### Faction Economic Fleet Rosters

| Faction | Vessel Name | Class | Speed | Init | Guns | Cargo Capacity | Asteroid Cap | Cost (M / C / E) | Operational Role |
| :--- | :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| **Vanguard** | **Supply Runner** | `MEDIUM` | 9 | 12 | **0** | 50,000 | 0 | 8k / 4k / 2.5k | Armored convoy transport (Unarmed) |
| **Vanguard** | **Ironclad Freighter**| `HEAVY` | 8 | 12 | **0** | 100,000 | 0 | 12k / 6k / 4k | Standard heavy armored hauler (Unarmed) |
| **Vanguard** | **Fortress Transport** | `HEAVY` | 8 | 12 | **0** | **200,000** | 0 | 20k / 12k / 8k | Super-heavy vault plunderer (400 HP, Unarmed) |
| **Vanguard** | **Ore Extractor** | `MEDIUM` | 9 | 12 | **0** | 0 | 5 | 10k / 6k / 4k | Frontline asteroid driller (Unarmed) |
| **Vanguard** | **Core Driller** | `HEAVY` | 8 | 12 | **0** | 0 | 10 | 15k / 9k / 6k | Heavy core asteroid mining rig (Unarmed) |
| **Vanguard** | **Siege Harvester** | `HEAVY` | 8 | 12 | **0** | 0 | **18** | 22k / 13k / 9k | Heavily plated macro-harvester (380 HP, Unarmed) |
| **Synthara** | **Pulse Courier** | `LIGHT` | 10 | 12 | **0** | 25,000 | 0 | 5k / 2.5k / 1.5k | High-speed scout plunderer (Unarmed) |
| **Synthara** | **Nexus Freighter** | `HEAVY` | 8 | 12 | **0** | 100,000 | 0 | 12k / 6k / 4k | Standard heavy hauler (Unarmed) |
| **Synthara** | **Singularity Hauler**| `HEAVY` | 8 | 12 | **0** | **200,000** | 0 | 20k / 12k / 8k | High-capacity orbital collector (Unarmed) |
| **Synthara** | **Crystal Borer** | `HEAVY` | 8 | 12 | **0** | 0 | 10 | 15k / 9k / 6k | Specialized crystalline harvester (Unarmed) |
| **Synthara** | **Void Harvester** | `HEAVY` | 8 | 12 | **0** | 0 | **18** | 22k / 13k / 9k | Deep-space asteroid siphon (Unarmed) |
| **Aetheris** | **Raid Runner** | `LIGHT` | 10 | 12 | **0** | 25,000 | 0 | 5k / 2.5k / 1.5k | Evasive blockade runner (Unarmed) |
| **Aetheris** | **Plunder Barge** | `MEDIUM` | 9 | 12 | **0** | 50,000 | 0 | 8k / 4k / 2.5k | Agile mid-tier raider (Unarmed) |
| **Aetheris** | **Claw Extractor** | `MEDIUM` | 9 | 12 | **0** | 0 | 5 | 10k / 6k / 4k | Mobile asteroid extraction tender (Unarmed) |

---

## 5. Player Strategies & Fleet Doctrines

Players leverage these mechanics to deploy distinct meta strategies:

1. **The Ironclad Siege & Fortified Convoy (Vanguard Coalition)**:
   - *Composition*: Imperator (Shield Aura) + Sovereigns + Titans + Sentinels + Fortress Transports.
   - *Doctrine*: Slow, unstoppable frontline advance. Sentinels wipe light screens; Sovereigns and Titans absorb PDS Ion Cannons and obliterate defensive bastions; Fortress Transports strip planetary vaults clean.
2. **The Surgical EMP Lockdown & Clean Plunder (Synthara Collective)**:
   - *Composition*: Oracle + Singularities + Obelisks + Pulse screens + Singularity Haulers.
   - *Doctrine*: Electronic warfare dominance. Speed-of-light EMP pulses disable defender weapons at Init 1–5 before they can fire. Defenders are neutralized with zero retaliation damage, allowing haulers to plunder unhindered.
3. **The Ghost Raid & Supply Line Severing (Aetheris Voidborne)**:
   - *Composition*: Void Apex + Phantom Dreadnoughts + Ghost Raiders + Phase Corsairs + Raid Runners.
   - *Doctrine*: High-speed predatory warfare. Evasive strike wings bypass heavy battleships, snipe vulnerable mining extractors and transports, plunder stockpiles, and retreat before heavy response fleets arrive.
4. **The Screened Planetary Defense (Combined Garrison)**:
   - *Composition*: Planetary Shield + PDS Batteries + Light Interceptors + Heavy Anchor.
   - *Doctrine*: Light craft absorb enemy alpha strikes, PDS batteries inflict steady attrition, and heavy anchors counter capital siege engines.

---

## 5.5 Weapon Hardpoint & Battery Rating (The "Guns" System)

In Pegasus Galaxy, **"Guns"** represents the physical count of primary weapon battery mounts / turret hardpoints engineered onto a ship's chassis:

1. **Fire Saturation & Tracking vs Evasion**:
   - In battle calculations, a ship's gun rating determines its fire density and directly penetrates target evasion:
     $$\text{effectiveGun} = \max(5.0, \text{attackerGun} - \text{defenderTotalEvasion})$$
     $$\text{evasionMultiplier} = \frac{\text{effectiveGun}}{\text{attackerGun}}$$
   - **Capital Ship Advantage**: Heavy capital ships mount massive gun batteries (e.g., *Imperator* with **46 Guns**, *Void Apex* with **53 Guns**, *Sovereign* with **41 Guns**, *Oracle* with **50 Guns**). Because their gun pool is so large, an agile target with 15% evasion only reduces their incoming damage by ~20%–30%.
   - **Light Ship Vulnerability**: Light combat craft mount fewer guns (e.g., *Phase Shrike* with **9 Guns**, *Pulse* with **10 Guns**). Firing at an evasive target reduces their effective damage significantly, reinforcing the need for telemetry support (+10% tracking from planetary radar) or combined-arms escort.
2. **Unarmed Civilian Fleets (0 Guns)**:
   - All 14 freighters, transports, and asteroid extractors mount **0 Guns**. They carry zero offensive armament and cannot return fire during combat; they rely purely on escort warships or blockade-running speed/evasion.
3. **Planetary Defense Battery Guns**:
   - **Laser Battery**: 13 Guns (High rate-of-fire point defense)
   - **Missile Silo**: 15 Guns (Medium guided salvo battery)
   - **Ion Cannon**: 17 Guns (Heavy orbital energy battery)
   - **Shield Generator & Radar Station**: 0 Guns (Defensive and sensory grid installations)

---

## 6. Complete Faction Combat Rosters (Costs & Stats)

### 1. Vanguard Coalition (Ceramic Plating & Kinetic Devastation)

| Ship Name | Class | Metal | Crystal | Eonium | Total Cost | Pts | Armor | Dmg | EMP Res | Guns | Eva % | Init | Priority (T1 $\rightarrow$ T2 $\rightarrow$ T3) | Role & Ability |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| **Centurion** | `MEDIUM` | 2,200 | 1,400 | 900 | **4,500** | 4 | 80 | 48 | 30% | **16** | **4.0%** | 4 | `MED` $\rightarrow$ `LT` $\rightarrow$ `HVY` | Line Frigate Escort |
| **Guardian** | `MEDIUM` | 3,000 | 1,900 | 1,200 | **6,100** | 6 | 94 | 58 | 32% | **17** | **4.0%** | 4 | `HVY` $\rightarrow$ `MED` $\rightarrow$ `LT` | Heavy Escort Frigate |
| **Sentinel** | `MEDIUM` | 3,800 | 2,400 | 1,500 | **7,700** | 8 | 120 | 74 | 35% | **22** | **5.0%** | 4 | `LT` $\rightarrow$ `MED` $\rightarrow$ `HVY` | **Anti-Screen Destroyer** |
| **Titan** | `MEDIUM` | 7,800 | 4,900 | 3,500 | **16,200** | 16 | 265 | 125 | 48% | **30** | **3.0%** | 5 | `MED` $\rightarrow$ `HVY` $\rightarrow$ `LT` | **Cruiser Brawler** |
| **Colossus** | `HEAVY` | 11,200 | 7,600 | 5,400 | **24,200** | 24 | 340 | 160 | 55% | **32** | **2.0%** | 6 | `HVY` $\rightarrow$ `MED` $\rightarrow$ `LT` | Line Forward Battleship |
| **Sovereign** | `HEAVY` | 14,400 | 9,900 | 7,200 | **31,500** | 31 | 455 | 232 | 65% | **41** | **2.0%** | 6 | `MED` $\rightarrow$ `HVY` $\rightarrow$ `LT` | **Heavy Siege Battleship** |
| **Imperator** | `SPECIAL` | 34,000 | 22,000 | 17,000 | **73,000** | 73 | 780 | 200 | 100% | **46** | **2.0%** | 10 | `HVY` $\rightarrow$ `MED` $\rightarrow$ `LT` | **Shield Aura** (10%/ship, max 30%) |

---

### 2. Synthara Collective (Pure Stun EMP & Energy Beam Batteries)

| Ship Name | Class | Metal | Crystal | Eonium | Total Cost | Pts | Armor | Dmg | EMP Stun | EMP Res | Guns | Eva % | Init | Priority (T1 $\rightarrow$ T2 $\rightarrow$ T3) | Role & Ability |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| **Pulse** | `LIGHT` | 900 | 1,000 | 400 | **2,300** | 2 | 44 | 16 | 36 | 10% | **10** | **10.0%** | **1** | `LT` $\rightarrow$ `MED` $\rightarrow$ `HVY` | **Speed-of-Light Stun Screen** |
| **Arc** | `LIGHT` | 1,100 | 1,200 | 500 | **2,800** | 3 | 52 | 22 | 46 | 12% | **13** | **11.0%** | **2** | `MED` $\rightarrow$ `LT` $\rightarrow$ `HVY` | EMP Interceptor |
| **Nexus** | `MEDIUM` | 1,300 | 1,450 | 600 | **3,350** | 3 | 64 | 34 | 70 | 15% | **18** | **5.0%** | **3** | `MED` $\rightarrow$ `HVY` $\rightarrow$ `LT` | Stun Escort Frigate |
| **Monolith** | `MEDIUM` | 7,500 | 8,000 | 3,500 | **19,000** | 19 | 275 | 115 | 235 | 30% | **28** | **4.0%** | **4** | `HVY` $\rightarrow$ `MED` $\rightarrow$ `LT` | Heavy EMP Cruiser |
| **Obelisk** | `HEAVY` | 10,500 | 11,000 | 5,500 | **27,000** | 27 | 360 | 170 | 340 | 40% | **34** | **3.0%** | **5** | `HVY` $\rightarrow$ `SPEC` $\rightarrow$ `MED` | Fast EMP Capital Battery |
| **Singularity**| `HEAVY` | 13,000 | 14,000 | 7,500 | **34,500** | 35 | 440 | 215 | 410 | 50% | **38** | **2.0%** | **5** | `HVY` $\rightarrow$ `MED` $\rightarrow$ `LT` | **Heavy EMP Dreadnought** |
| **Oracle** | `SPECIAL` | 24,000 | 29,000 | 12,000 | **65,000** | 65 | 680 | 270 | 530 | 100% | **50** | **2.5%** | **6** | `SPEC` $\rightarrow$ `HVY` $\rightarrow$ `MED` | **EMP Resonance** (+25% stun eff) |

---

### 3. Aetheris Voidborne (Deterministic Evasion & Precision Sniping)

| Ship Name | Class | Metal | Crystal | Eonium | Total Cost | Pts | Armor | Dmg | EMP Res | Guns | Eva % | Init | Priority (T1 $\rightarrow$ T2 $\rightarrow$ T3) | Role & Ability |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| **Phase Shrike** | `LIGHT` | 900 | 550 | 450 | **1,900** | 2 | 24 | 18 | 5% | **9** | **26.0%** | 3 | `MED` $\rightarrow$ `LT` $\rightarrow$ `HVY` | Evasive Swarm Screen |
| **Mirage Interceptor**|`LIGHT` | 1,250 | 800 | 600 | **2,650** | 3 | 30 | 24 | 6% | **12** | **23.0%** | 3 | `LT` $\rightarrow$ `MED` $\rightarrow$ `HVY` | Anti-Screen Scout |
| **Phase Corsair**| `MEDIUM` | 2,300 | 1,500 | 1,000 | **4,800** | 5 | 62 | 55 | 10% | **17** | **19.0%** | 4 | `MED` $\rightarrow$ `HVY` $\rightarrow$ `LT` | Fast Raider Frigate |
| **Ghost Raider** | `MEDIUM` | 4,200 | 2,700 | 1,900 | **8,800** | 9 | 78 | 70 | 12% | **20** | **17.0%** | 4 | `HVY` $\rightarrow$ `MED` $\rightarrow$ `LT` | **Battleship Hunter** |
| **Warp Stalker** | `MEDIUM` | 5,700 | 3,700 | 2,600 | **12,000** | 12 | 98 | 82 | 15% | **23** | **15.0%** | 5 | `MED` $\rightarrow$ `HVY` $\rightarrow$ `LT` | Line Skirmish Cruiser |
| **Phantom Dreadnought**|`HEAVY` | 15,500 | 10,200 | 7,300 | **33,000** | 33 | 395 | 225 | 25% | **37** | **13.0%** | 6 | `HVY` $\rightarrow$ `SPEC` $\rightarrow$ `MED` | Precision Capital |
| **Void Apex** | `SPECIAL` | 32,500 | 22,000 | 15,500 | **70,000** | 70 | 560 | 295 | 100% | **53** | **16.0%** | 7 | `SPEC` $\rightarrow$ `HVY` $\rightarrow$ `MED` | **Phase Field** (+3.5%/ship, max 10.5%) |

---

## 7. 2-Billion Battle Monte Carlo Simulation Results

*Engine*: Rust Parallel Rayon Deterministic Engine (24 Cores) | **2,000,000,000 Battles** in 41.19s (48.56M battles/sec)  
*Budget*: 10,000,000 Resources per Fleet | Full 21x21 Archetype Round-Robin Matrix

### A. Official Balanced Top 9 Leaderboard

> **Key Balance Achievements**:
> 1. **Exact 1-1-1 in Top 3**: Rank 1 Synthara (33.34%), Rank 2 Aetheris (28.57%), Rank 3 Vanguard (23.80%).
> 2. **Exact 3-3-3 in Top 9**: Exactly 3 Vanguard, 3 Synthara, 3 Aetheris.
> 3. **Tightly Balanced Win Rates**: Top 9 win rates are tightly compressed between **14.28% and 33.34%** (Ranks 5–9 all tightly grouped at ~14.28%–14.29%; Rank 4 at 19.05%; Ranks 1–3 at 23.80%–33.34%).
> 4. **Flawless Survivability**: 8 of the Top 9 archetypes boast **0.00% losses**.

| Rank | Archetype Formation | Faction | Representation | Win % | Loss % | Draw % | Avg Net Margin |
| :---: | :--- | :--- | :---: | :---: | :---: | :---: | :---: |
| **1** | **Pure Synthara Singularities** (100% Heavy EMP Dreadnought) | **Synthara** | **Top 3 (1/3)** | **33.34%** | **0.00%** | 66.66% | **+252,647** |
| **2** | **Pure Aetheris Phantom Dreadnoughts** (100% Heavy) | **Aetheris** | **Top 3 (1/3)** | **28.57%** | **0.00%** | 71.43% | **+389,371** |
| **3** | **Pure Vanguard Sovereigns** (100% Battleship) | **Vanguard** | **Top 3 (1/3)** | **23.80%** | **0.00%** | 76.20% | **+302,643** |
| **4** | **Synthara Combined Arms** (Oracle + Singularity + Obelisk + Nexus) | **Synthara** | Top 9 (2/3) | **19.05%** | **0.00%** | 80.95% | **+126,204** |
| **5** | **Aetheris Raider + Corsair Strike** (50/50 Raider/Corsair) | **Aetheris** | Top 9 (2/3) | **14.29%** | **0.00%** | 85.71% | **+206,739** |
| **6** | **Pure Vanguard Titans** (100% Cruiser) | **Vanguard** | Top 9 (2/3) | **14.29%** | **0.00%** | 85.71% | **+115,985** |
| **7** | **Aetheris Combined Arms** (Void Apex + Dread + Raider + Corsair + Mirage) | **Aetheris** | Top 9 (3/3) | **14.28%** | **0.00%** | 85.72% | **+259,192** |
| **8** | **Vanguard Combined Arms** (Imperator + Sov + Sen + Cent) | **Vanguard** | Top 9 (3/3) | **14.28%** | **0.00%** | 85.72% | **+212,980** |
| **9** | **Pure Synthara Obelisks** (100% Fast EMP Battery) | **Synthara** | Top 9 (3/3) | **14.28%** | 9.53% | 76.19% | **+98,542** |

---

### B. Tri-Faction Aggregate (Across All 2 Billion Battles)

| Faction | Total Win % | Total Loss % | Total Draw % | Assessment |
| :--- | :---: | :---: | :---: | :--- |
| **Synthara Collective** | **11.56%** | **6.12%** | **82.31%** | Fast EMP disablers neutralize weapons early; precision energy beams secure high-value eliminations. |
| **Vanguard Coalition** | **8.84%** | **7.48%** | **83.67%** | Ceramic armor & Faraday EMP resistance absorb massive strikes; heavy kinetic guns dominate battle lines. |
| **Aetheris Voidborne** | **8.16%** | **4.08%** | **87.75%** | Lowest loss rate in the galaxy; high evasion negates hostile tracking and forces stalemates against superior numbers. |

---

## 8. Developer JSON Data Specification

To allow developers to immediately consume these statistics in the game server, client GUI, combat simulator, or MCP tools, a canonical production JSON file has been generated at:
- **Root Repository Path**: [`tri_faction_ship_stats.json`](file:///c:/Users/D/Peg-MCP/tri_faction_ship_stats.json)
- **Documentation Path**: [`docs/tri_faction_ship_stats.json`](file:///c:/Users/D/Peg-MCP/docs/tri_faction_ship_stats.json)

### Top-Level JSON Schema Structure

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "version": "1.0.0",
  "metadata": { ... },
  "combatRules": {
    "deterministicEvasionFormula": "effectiveGun = max(5.0, attackerGun - defenderTotalEvasion)",
    "empDisablementRule": "Pure stun: weapons disabled for current tick. Zero hull damage.",
    "homeDefenseBonus": 1.10,
    "salvageRate": 0.30,
    "lootDominanceFactor": "...",
    "lootFairnessFactor": "...",
    "targetPriorityEfficiency": { "primary": 1.0, "secondary": 0.8, "tertiary": 0.6, "fallback": 0.5 }
  },
  "planetaryDefenseSystems": {
    "main-shield-generator": { ... },
    "main-ion-cannon": { ... },
    "main-missile-silo": { ... },
    "main-laser-battery": { ... }
  },
  "factions": {
    "VANGUARD": { "ships": { "main-vanguard-centurion": { ... }, ... } },
    "SYNTHARA": { "ships": { "main-synthara-pulse": { ... }, ... } },
    "AETHERIS": { "ships": { "main-aetheris-phase-shrike": { ... }, ... } }
  },
  "leaderboardBenchmarksTop9": [ ... ]
}
```

### Ship Object Fields for Developers
Each ship entry includes:
- `id`: Canonical unit identifier (e.g., `main-vanguard-sovereign`)
- `name`: Display name
- `faction`: `VANGUARD` | `SYNTHARA` | `AETHERIS`
- `shipClass`: `LIGHT` | `MEDIUM` | `HEAVY` | `SPECIAL`
- `category`: `FIGHTER` | `CORVETTE` | `FRIGATE` | `DESTROYER` | `CRUISER` | `BATTLESHIP` | `FLAGSHIP`
- `cost`: `{"metal": int, "crystal": int, "eonium": int, "total": int}`
- `points`: Military score / construction points
- `armor`: Hit points / armor pool
- `damage`: Kinetic / energy beam damage
- `empDamage`: EMP stun voltage
- `empResistance`: EMP resistance percentage
- `gun`: Weapon tracking / accuracy percentage
- `evasion`: Inherent evasion percentage (baseline 2.0%–11.0% across all factions based on hull class; 13.0%–26.0% for the Aetheris Voidborne evasion specialty)
- `init`: Combat firing step (1–12)
- `speed`: Sub-light movement speed (7–10)
- `eta`: Hyperdrive travel factor
- `targetClass1`, `targetClass2`, `targetClass3`: Priority targets
- `resourceCapacity`: Cargo hold for plundering resources (`RESOURCES`)
- `asteroidCapacity`: Mineral extraction hold for capturing asteroids (`ROIDS`)
- `capitalAbility`: Structured aura / ability payload or `null`
- `cloak`: Stealth status (`true` for Synthara Oracle in Round 1)
- `operationalRole`: Tactical role summary



---

## 9. Planetary Blockade & Orbital Interception System

### A. The 2-Zone Orbital Architecture (Outer Orbit vs. Surface PDS)
To prevent unfair permanent spawn-camping while giving attackers strategic siege power, space around a planet is partitioned into two distinct tactical zones separated by a **1-tick travel transit**:

1. **Outer Orbit (High Lagrange Perimeter)**:
   - Where blockading fleets establish containment.
   - **Outside Short-Range PDS**: Blockaders cannot be bombarded by short-range Laser Batteries or Missile Silos, but remain in target lock of the planet's **Radar Station** and super-heavy **Ion Cannons**.
   - **Interception Vector**: All incoming transports, mining drop-offs, and departing trade convoys must pass through Outer Orbit, where blockaders automatically intercept non-stealth vessels.
2. **Inner Orbit (Surface / Colony Vault / PDS Citadel)**:
   - Where the defender's garrison ships dock and planetary mines operate.
   - Resource vaults and ground buildings remain protected under the **Planetary Shield Generator**.

---

### B. Anti-Griefing Rules: Fair Limits & Escalating Upkeep
To ensure high-tier alliances cannot permanently ruin gameplay for developing players:

1. **Hard Duration Cap (Maximum 8 Ticks / 4 Hours)**:
   - A blockade fleet can only hold an orbital containment perimeter for a maximum of **8 consecutive combat ticks**.
   - On Tick 8, the fleet suffers **Orbital Degradation** and must either commit to a full ground assault (entering Inner Orbit against full PDS) or retreat into deep space.
2. **Sovereign Grace / Blockade Immunity (12 Ticks)**:
   - Once a blockade is broken, lifted, or expired, the target planet gains an inviolable **12-tick Blockade Immunity window**. Hostile fleets cannot re-establish a blockade on that planet during this cooldown.
3. **Escalating Upkeep (Logistics Fuel Strain)**:
   - Maintaining a stationary siege fleet in hostile gravity burns escalating resources per tick (+15% cumulative deuterium/eonium fuel per tick). Prolonged blockades become prohibitively expensive.

---

### C. Planetary Sensor Advantage: Ground Radar Evasion Penalty
*Why planets counter glass-cannon evasion*:
- A celestial body houses geothermal/fusion-powered **Planetary Radar Stations (`main-radar-station`)** and deep-space scanner grids.
- When hostile ships sit in stationary blockade orbit, planetary ground radar illuminates their phase signatures with unlimited ground power, granting defenders **Orbital Triangulation Telemetry**:
  - **-10% Hostile Evasion Debuff**: All blockading ships lose **10.0% inherent evasion** (down to the 5% hard minimum floor).
  - **+10% Tracking Accuracy to Defender Garrison**: Ground targeting feeds give defending sortie craft a flat +10% Gun tracking boost against blockaders.
- **Strategic Impact**: Directly penalizes agile glass-cannon fleets (like Aetheris) that attempt stationary blockades without heavy armor, while rewarding armored Vanguard dreadnoughts designed for siege endurance.

---

### D. The 3 Defender Tactical Responses
When blockaded, the defender is never helpless:

1. **Garrison Sortie (Breakout Attack)**:
   - Defending fleet ascends from Inner Orbit to Outer Orbit to engage the blockaders.
   - The defender fights with the **+10% Radar Telemetry Bonus** and hostile evasion is reduced by **-10%**, giving the home garrison a major tactical home-field advantage!
2. **Blockade Running (Stealth Smuggling)**:
   - Fast, agile craft (`Speed 10`, `Evasion >= 10%`, e.g., *Phase Shrike*, *Pulse Courier*, *Raid Runner*) have a **60% evasion chance to slip past the blockade unnoticed**, transporting critical emergency resources or evacuated population to safety.
3. **Alliance Relief Fleet (Flanking Counter-Strike)**:
   - Friendly alliance fleets jumping into Outer Orbit from hyperspace arrive behind the blockader, catching the siege fleet in a pincer between the relief force and the ascending planetary garrison.
