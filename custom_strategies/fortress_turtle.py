"""
Fortress Defense Strategy Hook
Prioritizes planetary defenses (PDS), shield generators, and colony repair.
"""

def on_tick(client, state, config, logger):
    logger("🛡️ [Custom Strategy] Running Fortress Defense Hook...")
    pds = state.get("pds", [])
    built_pds = [p for p in pds if p.get("level", 0) > 0]
    logger(f"   Active defense emplacements: {len(built_pds)}")

    for p in built_pds:
        if p.get("currentHealth", 1) < p.get("maxHealth", 1):
            logger(f"   ⚠️ Repairing damaged defense: {p.get('name')}")
            try:
                client.call_tool("repair_pds", {"constructionId": p.get("constructionId")})
            except Exception as e:
                logger(f"   Repair error: {e}")
