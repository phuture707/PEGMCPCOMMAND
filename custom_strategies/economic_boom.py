"""
Economic Expansion Strategy Hook
Focuses on resource mining, prospect scans, and maximizing metal/crystal.
"""

def on_tick(client, state, config, logger):
    logger("🚀 [Custom Strategy] Running Economic Expansion Hook...")
    planet = state.get("planet", {})
    metal = planet.get("metal", 0)
    crystal = planet.get("crystal", 0)
    logger(f"   Current reserves: Metal={metal:,}, Crystal={crystal:,}")

    # Check active construction queue from state
    constructions = planet.get("constructions", [])
    logger(f"   Active infrastructure projects: {len(constructions)}")
