"""
Armada Factory Strategy Hook
Focuses on shipyard throughput, light/medium combat vessels, and fleet readiness.
"""

def on_tick(client, state, config, logger):
    logger("⚔️ [Custom Strategy] Running Armada Factory Hook...")
    planet = state.get("planet", {})
    metal = planet.get("metal", 0)
    crystal = planet.get("crystal", 0)

    # If reserves are plentiful, queue Centurion combat ships
    if metal >= 50000 and crystal >= 25000:
        logger("🔨 Stockpile adequate: Ordering 10 Centurion fighters...")
        try:
            client.call_tool("produce_ships", {"shipDefinitionId": "main-centurion", "quantity": 10})
        except Exception as e:
            logger(f"   Produce ships note: {e}")
