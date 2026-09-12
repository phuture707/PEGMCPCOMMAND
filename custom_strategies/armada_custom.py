"""
Armada Factory Strategy Hook
Prioritizes Shipyard infrastructure, Light/Medium ship manufacturing, and fleet readiness.
"""

def on_tick(client, state, config, logger):
    logger("⚔️ [Custom Strategy] Running Armada Factory Hook...")
    planet = state.get("planet", {}).get("data", {}) or {}
    ships = planet.get("ships", []) or []
    logger(f"   Hangar ship count: {len(ships)}")
