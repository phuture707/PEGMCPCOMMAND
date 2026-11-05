"""Ship designer compile/validate — fairness contract v1.3.

Executable spec for the PDF. GUI is not implemented here.
Mode C: same stats as native, +18% cost, +1 unlock, 1 foreign combat slot.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

CURVE_EXP = 1.6
FOREIGN_COST_MULT = 1.18
FOREIGN_DP_TAX = 0.0  # retracted: stacked stat nerf made Mode C unsellable
FOREIGN_UNLOCK_DELTA = 1
MAX_FOREIGN_COMBAT = 1
MAX_BLUEPRINTS = 6
SIEGE_COST_TAX = 1.08
CLOAK_MASS_CAP = 0.25

FACTION_LOCKED = "FACTION_LOCKED"
FACTION_TAXED = "FACTION_TAXED"
OPEN = "OPEN"
UNIQUE_FRAMES = frozenset({"frm_cp_ghost", "frm_cp_siege"})

MIX_TOTAL = 10
LIVE_SHIP_KEYS = (
    "armor",
    "asteroidCapacity",
    "capitalAbility",
    "category",
    "cloak",
    "cost",
    "damage",
    "empDamage",
    "empResistance",
    "faction",
    "gun",
    "id",
    "init",
    "name",
    "resourceCapacity",
    "shipClass",
    "targetClass1",
    "targetClass2",
    "targetClass3",
)

SIEGE_ABILITY_PAYLOADS = {
    "shield_aura": {
        "type": "shield_aura",
        "shieldAbsorptionPercent": 8,
        "maxAbsorptionPercent": 25,
    },
    "siege_barrier": {
        "type": "siege_barrier",
        "damageReflectPercent": 15,
    },
}

DOCTRINES = {
    "ANTI_LIGHT": ("LIGHT", "MEDIUM", "HEAVY"),
    "ANTI_MEDIUM": ("MEDIUM", "LIGHT", "HEAVY"),
    "ANTI_HEAVY": ("HEAVY", "MEDIUM", "LIGHT"),
    "RESOURCES": ("RESOURCES", "", ""),
    "ROIDS": ("ROIDS", "", ""),
}


class DesignReject(Exception):
    """Illegal draft."""


def axis_fraction(pts: int, dp_max: int) -> float:
    """Share of a slider's range. Same f for armour, guns, and init."""
    if dp_max <= 0:
        return 0.0
    pts = max(0, min(int(pts), dp_max))
    f = pts / dp_max
    return 1.0 - (1.0 - f) ** CURVE_EXP


def curve(lo: float, hi: float, pts: int, dp_max: int) -> float:
    if hi == lo:
        return float(lo)
    return lo + (hi - lo) * axis_fraction(pts, dp_max)


def curve_int(lo: int, hi: int, pts: int, dp_max: int) -> int:
    return int(round(curve(lo, hi, pts, dp_max)))


def init_from_drive(slow: int, fast: int, drive_pts: int, dp_max: int) -> int:
    """Init steps up or down in whole numbers, paid with the same DP curve as armour/guns.

    You do not pay '3 points because init is 3'. Filling the drive slider costs
    the same budget as filling the armour slider; the compiled init is just the
    integer on that curve (lower = faster).
    """
    slow_i, fast_i = int(slow), int(fast)
    stepped = int(round(curve(slow_i, fast_i, drive_pts, dp_max)))
    lo, hi = min(slow_i, fast_i), max(slow_i, fast_i)
    return max(lo, min(hi, stepped))


FRAMES: dict[str, dict[str, Any]] = {
    "frm_lt_strike": {
        "band": "light",
        "combat": True,
        "category": "FIGHTER",
        "shipClass": "LIGHT",
        "weaponAllowed": ["KINETIC"],
        "armor": (20, 32),
        "damage": (16, 24),
        "emp": (0, 0),
        "guns": (8, 11),
        "initFast": 3,
        "initSlow": 6,
        "dpMax": 12,
        "unlock": 1,
        "resist": (0, 6),
        "cargo": (0, 0),
        "roid": (0, 0),
        "baseCost": {"metal": 900, "crystal": 500, "eonium": 500},
        "nativeRace": "VANGUARD",  # also ASHKARI; listed as kinetic-native
    },
    "frm_lt_emp": {
        "band": "light",
        "combat": True,
        "category": "FIGHTER",
        "shipClass": "LIGHT",
        "weaponAllowed": ["EMP"],
        "armor": (40, 54),
        "damage": (0, 0),
        "emp": (12, 16),
        "guns": (6, 8),
        "initFast": 5,
        "initSlow": 6,
        "dpMax": 12,
        "unlock": 1,
        "resist": (12, 16),
        "cargo": (0, 0),
        "roid": (0, 0),
        "baseCost": {"metal": 1100, "crystal": 900, "eonium": 800},
        "nativeRace": "SYNTHARA",
    },
    "frm_lt_courier": {
        "band": "light",
        "combat": False,
        "category": "CORVETTE",
        "shipClass": "LIGHT",
        "weaponAllowed": ["NONE"],
        "armor": (80, 80),
        "damage": (0, 0),
        "emp": (0, 0),
        "guns": (0, 0),
        "initFast": 12,
        "initSlow": 12,
        "dpMax": 8,
        "unlock": 1,
        "resist": (5, 5),
        "cargo": (25000, 25000),
        "roid": (0, 0),
        "baseCost": {"metal": 5000, "crystal": 2500, "eonium": 1500},
        "nativeRace": None,
    },
    "frm_md_gun": {
        "band": "medium",
        "combat": True,
        "category": "FRIGATE",
        "shipClass": "MEDIUM",
        "weaponAllowed": ["KINETIC"],
        "armor": (54, 94),
        "damage": (44, 58),
        "emp": (0, 0),
        "guns": (15, 17),
        "initFast": 4,
        "initSlow": 6,
        "dpMax": 18,
        "unlock": 2,
        "resist": (0, 16),
        "cargo": (0, 0),
        "roid": (0, 0),
        "baseCost": {"metal": 1800, "crystal": 1400, "eonium": 1300},
        "nativeRace": "VANGUARD",
    },
    "frm_md_destroyer": {
        "band": "medium",
        "combat": True,
        "category": "DESTROYER",
        "shipClass": "MEDIUM",
        "weaponAllowed": ["KINETIC"],
        "armor": (66, 116),
        "damage": (54, 72),
        "emp": (0, 0),
        "guns": (17, 19),
        "initFast": 4,
        "initSlow": 6,
        "dpMax": 20,
        "unlock": 3,
        "resist": (0, 16),
        "cargo": (0, 0),
        "roid": (0, 0),
        "baseCost": {"metal": 2800, "crystal": 2500, "eonium": 2400},
        "nativeRace": "VANGUARD",
    },
    "frm_md_emp": {
        "band": "medium",
        "combat": True,
        "category": "DESTROYER",
        "shipClass": "MEDIUM",
        "weaponAllowed": ["EMP"],
        "armor": (66, 116),
        "damage": (0, 0),
        "emp": (20, 28),
        "guns": (15, 19),
        "initFast": 4,
        "initSlow": 6,
        "dpMax": 20,
        "unlock": 3,
        "resist": (16, 28),
        "cargo": (0, 0),
        "roid": (0, 0),
        "baseCost": {"metal": 3000, "crystal": 2800, "eonium": 2600},
        "nativeRace": None,
        "modeBOnly": True,
    },
    "frm_cp_cruiser": {
        "band": "capital",
        "combat": True,
        "category": "CRUISER",
        "shipClass": "HEAVY",
        "weaponAllowed": ["KINETIC"],
        "armor": (250, 340),
        "damage": (112, 156),
        "emp": (0, 0),
        "guns": (25, 30),
        "initFast": 5,
        "initSlow": 8,
        "dpMax": 28,
        "unlock": 4,
        "resist": (24, 30),
        "cargo": (0, 0),
        "roid": (0, 0),
        "baseCost": {"metal": 7000, "crystal": 5000, "eonium": 4200},
        "nativeRace": "VANGUARD",
    },
    "frm_cp_emp": {
        "band": "capital",
        "combat": True,
        "category": "CRUISER",
        "shipClass": "HEAVY",
        "weaponAllowed": ["EMP"],
        "armor": (250, 330),
        "damage": (0, 0),
        "emp": (30, 36),
        "guns": (20, 24),
        "initFast": 8,
        "initSlow": 10,
        "dpMax": 28,
        "unlock": 4,
        "resist": (40, 50),
        "cargo": (0, 0),
        "roid": (0, 0),
        "baseCost": {"metal": 8000, "crystal": 6000, "eonium": 5000},
        "nativeRace": "SYNTHARA",
    },
    "frm_cp_battle": {
        "band": "capital",
        "combat": True,
        "category": "BATTLESHIP",
        "shipClass": "HEAVY",
        "weaponAllowed": ["KINETIC"],
        "armor": (340, 420),
        "damage": (156, 200),
        "emp": (0, 0),
        "guns": (30, 34),
        "initFast": 6,
        "initSlow": 9,
        "dpMax": 32,
        "unlock": 5,
        "resist": (30, 35),
        "cargo": (0, 0),
        "roid": (0, 0),
        "baseCost": {"metal": 12000, "crystal": 9000, "eonium": 8000},
        "nativeRace": "VANGUARD",
    },
    "frm_cp_ghost": {
        "band": "special",
        "combat": True,
        "category": "BATTLESHIP",
        "shipClass": "SPECIAL",
        "weaponAllowed": ["EMP"],
        "armor": (640, 640),
        "damage": (0, 0),
        "emp": (60, 60),
        "guns": (30, 30),
        "initFast": 8,
        "initSlow": 8,
        "dpMax": 36,
        "unlock": 6,
        "resist": (80, 80),
        "cargo": (0, 0),
        "roid": (0, 0),
        "baseCost": {"metal": 24000, "crystal": 29000, "eonium": 12000},
        "nativeRace": "SYNTHARA",
        "cloak": True,
        "capitalAbility": {"type": "disruption_field", "fleetEmpChanceMultiplier": 0.3},
    },
    "frm_cp_siege": {
        "band": "special",
        "combat": True,
        "category": "BATTLESHIP",
        "shipClass": "SPECIAL",
        "weaponAllowed": ["KINETIC"],
        "armor": (470, 720),
        "damage": (170, 250),
        "emp": (0, 0),
        "guns": (42, 55),
        "initFast": 7,
        "initSlow": 11,
        "dpMax": 40,
        "unlock": 6,
        "resist": (45, 100),
        "cargo": (0, 0),
        "roid": (0, 0),
        "baseCost": {"metal": 25000, "crystal": 22000, "eonium": 20000},
        "nativeRace": "VANGUARD",
    },
}

RACES: dict[str, dict[str, Any]] = {
    "VANGUARD": {
        "nativeFrameIds": {
            "frm_lt_strike",
            "frm_lt_courier",
            "frm_md_gun",
            "frm_md_destroyer",
            "frm_cp_cruiser",
            "frm_cp_battle",
            "frm_cp_siege",
        },
        "weaponLock": "KINETIC",
        "siegeAbility": "shield_aura",
        "allowsGhost": False,
        "uniqueFrameIds": {"frm_cp_siege"},
    },
    "ASHKARI": {
        "nativeFrameIds": {
            "frm_lt_strike",
            "frm_lt_courier",
            "frm_md_gun",
            "frm_md_destroyer",
            "frm_cp_cruiser",
            "frm_cp_battle",
            "frm_cp_siege",
        },
        "weaponLock": "KINETIC",
        "siegeAbility": "siege_barrier",
        "allowsGhost": False,
        "uniqueFrameIds": {"frm_cp_siege"},
    },
    "SYNTHARA": {
        "nativeFrameIds": {
            "frm_lt_emp",
            "frm_lt_courier",
            "frm_cp_emp",
            "frm_cp_ghost",
        },
        "weaponLock": "EMP",
        "siegeAbility": None,
        "allowsGhost": True,
        "uniqueFrameIds": {"frm_cp_ghost"},
    },
}


def default_config(**overrides) -> dict[str, Any]:
    cfg = {
        "designerMode": FACTION_LOCKED,
        "cosmeticRaces": False,
        "allowMediumEmp": False,
        "foreignCostMult": FOREIGN_COST_MULT,
        "foreignDpTax": FOREIGN_DP_TAX,
        "foreignUnlockDelta": FOREIGN_UNLOCK_DELTA,
        "maxForeignCombatBlueprints": MAX_FOREIGN_COMBAT,
        "maxBlueprints": MAX_BLUEPRINTS,
    }
    cfg.update(overrides)
    return cfg


def alloc_spent(frame: dict[str, Any], alloc: dict[str, int]) -> int:
    if frame["combat"]:
        return (
            int(alloc.get("armor", 0))
            + int(alloc.get("battery", alloc.get("damage", 0)))
            + int(alloc.get("drive", 0))
            + int(alloc.get("resist", 0))
        )
    return (
        int(alloc.get("armor", 0))
        + int(alloc.get("cargo", 0))
        + int(alloc.get("roid", 0))
        + int(alloc.get("resist", 0))
    )


def score_from_cost(cost: dict[str, int]) -> int:
    return int(cost["metal"] + cost["crystal"] + cost["eonium"])
    return int(cost["metal"] + cost["crystal"] + cost["eonium"])


def derive(frame: dict[str, Any], alloc: dict[str, int], weapon: str) -> dict[str, Any]:
    dp = frame["dpMax"]
    a = int(alloc.get("armor", 0))
    b = int(alloc.get("battery", alloc.get("damage", 0)))
    d = int(alloc.get("drive", 0))
    r = int(alloc.get("resist", 0))
    if alloc_spent(frame, alloc) != dp:
        raise DesignReject(f"must spend exactly {dp} DP")
    armor_lo, armor_hi = frame["armor"]
    dmg_lo, dmg_hi = frame["damage"]
    emp_lo, emp_hi = frame["emp"]
    gun_lo, gun_hi = frame["guns"]
    res_lo, res_hi = frame.get("resist", (0, 0))
    cargo_lo, cargo_hi = frame.get("cargo", (0, 0))
    roid_lo, roid_hi = frame.get("roid", (0, 0))

    armor = max(armor_lo, min(armor_hi, curve_int(armor_lo, armor_hi, a, dp)))
    resist = max(res_lo, min(res_hi, curve_int(res_lo, res_hi, r, dp)))
    cargo = curve_int(cargo_lo, cargo_hi, int(alloc.get("cargo", 0)), dp) if not frame["combat"] else 0
    roid = curve_int(roid_lo, roid_hi, int(alloc.get("roid", 0)), dp) if not frame["combat"] else 0

    if weapon == "KINETIC":
        damage = curve_int(dmg_lo, dmg_hi, b, dp)
        emp = 0
        guns = curve_int(gun_lo, gun_hi, b, dp)
    elif weapon == "EMP":
        damage = 0
        emp = curve_int(emp_lo, emp_hi, b, dp)
        guns = curve_int(gun_lo, gun_hi, b, dp)
    else:
        if b != 0:
            raise DesignReject("utility batteryPts must be 0")
        damage = 0
        emp = 0
        guns = 0

    if not frame["combat"]:
        init = 12
        guns = 0
        damage = 0
        emp = 0
    else:
        init = init_from_drive(frame["initSlow"], frame["initFast"], d, dp)
        cargo = 0
        roid = 0

    return {
        "armor": armor,
        "damage": damage,
        "empDamage": emp,
        "gun": guns,
        "init": init,
        "empResistance": resist,
        "cloak": bool(frame.get("cloak")),
        "category": frame["category"],
        "shipClass": frame["shipClass"],
        "capitalAbility": deepcopy(frame.get("capitalAbility")),
        "resourceCapacity": cargo,
        "asteroidCapacity": roid,
    }


def _is_unique(frame_id: str) -> bool:
    return frame_id in UNIQUE_FRAMES or any(
        frame_id in r["uniqueFrameIds"] for r in RACES.values()
    )


def _native(race: str, frame_id: str) -> bool:
    return frame_id in RACES[race]["nativeFrameIds"]


def validate_and_compile(
    player: dict[str, Any],
    draft: dict[str, Any],
    cfg: dict[str, Any] | None = None,
    existing_bps: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    cfg = cfg or default_config()
    existing_bps = existing_bps or []
    frame_id = draft["frameId"]
    if frame_id not in FRAMES:
        raise DesignReject(f"unknown frame {frame_id}")
    frame = FRAMES[frame_id]
    mode = cfg["designerMode"]
    race = player["race"]
    weapon = draft["weaponType"]
    alloc = draft["alloc"]
    tech = int(player.get("techLevel", 99))

    if len(existing_bps) >= cfg["maxBlueprints"] and draft.get("blueprintId") not in {
        bp.get("blueprintId") for bp in existing_bps
    }:
        raise DesignReject("seventh blueprint")

    native = False if mode == OPEN else _native(race, frame_id)
    foreign = False

    if mode == FACTION_LOCKED:
        if draft.get("race") != race:
            raise DesignReject("race mismatch")
        if not native:
            raise DesignReject("off-race frame in FACTION_LOCKED")
        if weapon != frame["weaponAllowed"][0]:
            raise DesignReject("weapon not allowed on frame")
        if frame_id == "frm_cp_siege":
            want = RACES[race]["siegeAbility"]
            got = (draft.get("capitalAbility") or {}).get("type")
            if got != want:
                raise DesignReject("wrong siege ability")
        if frame_id == "frm_cp_ghost" and not RACES[race]["allowsGhost"]:
            raise DesignReject("ghost not allowed")
        need = frame["unlock"]
        if tech < need:
            raise DesignReject("locked")
    elif mode == FACTION_TAXED:
        if draft.get("race") != race:
            raise DesignReject("race mismatch")
        if native:
            if frame_id == "frm_cp_siege":
                want = RACES[race]["siegeAbility"]
                got = (draft.get("capitalAbility") or {}).get("type")
                if got != want:
                    raise DesignReject("wrong siege ability")
            need = frame["unlock"]
            if tech < need:
                raise DesignReject("locked")
        else:
            if _is_unique(frame_id):
                raise DesignReject("unique SPECIAL cannot be bought")
            if frame.get("modeBOnly") and not cfg.get("allowMediumEmp"):
                raise DesignReject("medium EMP disabled")
            if weapon != frame["weaponAllowed"][0]:
                raise DesignReject("weapon not allowed on frame")
            combat_foreign = sum(
                1
                for bp in existing_bps
                if bp.get("taxed") and FRAMES[bp["frameId"]]["combat"]
            )
            if frame["combat"]:
                combat_foreign += 1
            if combat_foreign > cfg["maxForeignCombatBlueprints"]:
                raise DesignReject("second foreign combat blueprint")
            need = frame["unlock"] + int(cfg["foreignUnlockDelta"])
            if tech < need:
                raise DesignReject("foreign unlock lag")
            foreign = True
        if not native and weapon != frame["weaponAllowed"][0]:
            raise DesignReject("weapon not allowed on frame")
        if native and weapon != frame["weaponAllowed"][0]:
            raise DesignReject("weapon not allowed on frame")
    else:  # OPEN
        if weapon not in frame["weaponAllowed"]:
            raise DesignReject("weapon not allowed on frame")
        if frame_id == "frm_md_emp" and not cfg.get("allowMediumEmp"):
            raise DesignReject("medium EMP disabled")
        need = frame["unlock"]
        if tech < need:
            raise DesignReject("locked")

    spendable = frame["dpMax"]
    if alloc_spent(frame, alloc) != spendable:
        raise DesignReject(f"must spend exactly {spendable} DP")

    compiled = derive(frame, alloc, weapon)
    if frame_id == "frm_cp_siege":
        ability_type = (draft.get("capitalAbility") or {}).get("type")
        if mode == OPEN:
            compiled["capitalAbility"] = {"type": ability_type} if ability_type else None
        else:
            compiled["capitalAbility"] = deepcopy(
                SIEGE_ABILITY_PAYLOADS[RACES[player["race"]]["siegeAbility"]]
            )

    if frame_id == "frm_cp_ghost":
        compiled["cloak"] = True
        compiled["capitalAbility"] = deepcopy(frame["capitalAbility"])

    if not frame["combat"] and compiled["gun"] > 0:
        raise DesignReject("courier guns")

    mult = 1.0
    if foreign:
        mult *= float(cfg["foreignCostMult"])
    if compiled.get("capitalAbility") and compiled["capitalAbility"].get("type") in {
        "shield_aura",
        "siege_barrier",
    }:
        mult *= SIEGE_COST_TAX
    compiled["cost"] = {
        res: int(round(frame["baseCost"][res] * mult)) for res in ("metal", "crystal", "eonium")
    }
    compiled["taxed"] = foreign
    compiled["frameId"] = frame_id
    compiled["weaponType"] = weapon
    compiled["faction"] = race if mode != OPEN else (draft.get("cosmeticRace") or "NONE")
    compiled["frameNativeRace"] = frame.get("nativeRace")
    compiled["score"] = score_from_cost(compiled["cost"])
    compiled["name"] = draft.get("name") or frame_id
    compiled["id"] = draft.get("blueprintId") or ("custom-" + frame_id)
    if not frame["combat"]:
        if frame.get("roid", (0, 0))[1] > 0:
            t1, t2, t3 = DOCTRINES["ROIDS"]
        else:
            t1, t2, t3 = DOCTRINES["RESOURCES"]
    else:
        t1, t2, t3 = DOCTRINES.get(draft.get("doctrine") or "", DOCTRINES["ANTI_MEDIUM"])
    compiled["targetClass1"], compiled["targetClass2"], compiled["targetClass3"] = t1, t2, t3
    return compiled


def cloaked_mass_ok(units: list[tuple[bool, float]]) -> bool:
    """units: list of (cloak, mass)."""
    total = sum(m for _, m in units)
    if total <= 0:
        return True
    cloaked = sum(m for c, m in units if c)
    return cloaked / total <= CLOAK_MASS_CAP + 1e-9
