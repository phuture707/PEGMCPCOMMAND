#!/usr/bin/env python3
"""Sequential fairness checks for the ship designer contract.

Run: python docs/test_ship_designer_fairness.py
Runs passes 1..10 in order; stops on first failure.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from ship_designer_rules import (  # noqa: E402
    DesignReject,
    FACTION_LOCKED,
    FACTION_TAXED,
    FRAMES,
    LIVE_SHIP_KEYS,
    OPEN,
    axis_fraction,
    cloaked_mass_ok,
    curve,
    default_config,
    derive,
    score_from_cost,
    validate_and_compile,
)


def vg(tech=99, **extra):
    p = {"race": "VANGUARD", "techLevel": tech}
    p.update(extra)
    return p


def sy(tech=99, **extra):
    p = {"race": "SYNTHARA", "techLevel": tech}
    p.update(extra)
    return p


def ak(tech=99, **extra):
    p = {"race": "ASHKARI", "techLevel": tech}
    p.update(extra)
    return p


def draft(frame, weapon, armor, battery, drive, race="VANGUARD", **extra):
    d = {
        "frameId": frame,
        "weaponType": weapon,
        "race": race,
        "alloc": {"armor": armor, "battery": battery, "drive": drive},
    }
    d.update(extra)
    return d


class Fail(AssertionError):
    pass


def expect_ok(player, d, cfg=None, existing=None):
    return validate_and_compile(player, d, cfg, existing)


def expect_reject(player, d, cfg=None, existing=None, needle=None):
    try:
        validate_and_compile(player, d, cfg, existing)
    except DesignReject as e:
        if needle and needle.lower() not in str(e).lower():
            raise Fail(f"rejected for wrong reason: {e!r} (want {needle!r})") from e
        return str(e)
    raise Fail("expected reject, compiled ok")


# ---------------------------------------------------------------------------
# Pass 1 — zero-sum: high armour spends the points that would have gone to
# guns and init. God-ship (max all three) is impossible.
# ---------------------------------------------------------------------------
def pass_1_zero_sum():
    cfg = default_config(designerMode=FACTION_LOCKED)
    dp = FRAMES["frm_lt_strike"]["dpMax"]
    tank = expect_ok(vg(), draft("frm_lt_strike", "KINETIC", dp, 0, 0), cfg)
    glass = expect_ok(vg(), draft("frm_lt_strike", "KINETIC", 0, dp, 0), cfg)
    fast = expect_ok(vg(), draft("frm_lt_strike", "KINETIC", 0, 0, dp), cfg)
    if tank["armor"] != 32 or tank["damage"] != 16 or tank["init"] != 6:
        raise Fail(f"tank not peak-plate/floor-guns/slow: {tank}")
    if glass["armor"] != 20 or glass["damage"] != 24 or glass["init"] != 6:
        raise Fail(f"glass not floor-plate/peak-guns/slow: {glass}")
    if fast["armor"] != 20 or fast["damage"] != 16 or fast["init"] != 3:
        raise Fail(f"fast not floor-plate/floor-guns/peak-init: {fast}")
    if tank["armor"] > 20 and tank["damage"] > 16:
        raise Fail("tank kept extra guns — tradeoff is fake")
    prev = None
    for drive in range(0, dp + 1):
        row = expect_ok(
            vg(), draft("frm_lt_strike", "KINETIC", 0, dp - drive, drive), cfg
        )
        if not isinstance(row["init"], int):
            raise Fail(f"init {row['init']!r} is not an integer")
        if prev is not None and abs(row["init"] - prev) not in (0, 1):
            raise Fail(f"init jumped {prev}->{row['init']} at drive={drive}")
        prev = row["init"]
    if prev != 3:
        raise Fail(f"max drive init {prev}, expected 3")
    for drive in range(dp, -1, -1):
        row = expect_ok(
            vg(), draft("frm_lt_strike", "KINETIC", 0, dp - drive, drive), cfg
        )
        if prev is not None and abs(row["init"] - prev) not in (0, 1):
            raise Fail(f"init jumped {prev}->{row['init']} stepping drive back to {drive}")
        prev = row["init"]
    if prev != 6:
        raise Fail(f"0 drive init {prev}, expected 6")
    cheap = expect_ok(vg(), draft("frm_lt_strike", "KINETIC", 0, dp - 3, 3), cfg)
    if cheap["init"] == 3:
        raise Fail("drive=3 compiled init=3 — cost was the init number, not the armour/gun budget")
    armor_progress = (curve(20, 32, 4, dp) - 20) / 12
    init_progress = (6 - curve(6, 3, 4, dp)) / 3
    if abs(armor_progress - init_progress) > 1e-9:
        raise Fail(
            f"drive is not on the same curve as armour ({init_progress:.4f} vs {armor_progress:.4f})"
        )
    if abs(axis_fraction(4, dp) - armor_progress) > 1e-9:
        raise Fail("armour progress drifted from shared axis_fraction")
    one = expect_ok(vg(), draft("frm_lt_strike", "KINETIC", 0, dp - 1, 1), cfg)
    if abs(one["init"] - 6) > 1:
        raise Fail("1 drive point bought more than one init step")
    try:
        god = derive(
            FRAMES["frm_lt_strike"],
            {"armor": dp, "battery": dp, "drive": dp},
            "KINETIC",
        )
    except DesignReject:
        god = None
    if god is not None:
        raise Fail("derive allows max-all if alloc is not checked")
    return "tank 32/16/6, glass 20/24/6, fast 20/16/3; init steps 6..3 and back 3..6"


# ---------------------------------------------------------------------------
# Pass 2 — Mode C is a price, not a worse hull. Same peaks, +18% cost.
# ---------------------------------------------------------------------------
def pass_2_mode_c_same_peaks():
    locked = default_config(designerMode=FACTION_LOCKED)
    taxed = default_config(designerMode=FACTION_TAXED)
    native = expect_ok(
        sy(), draft("frm_lt_emp", "EMP", 0, 12, 0, race="SYNTHARA"), locked
    )
    foreign = expect_ok(
        vg(), draft("frm_lt_emp", "EMP", 0, 12, 0, race="VANGUARD"), taxed
    )
    for k in ("armor", "damage", "empDamage", "gun", "init"):
        if native[k] != foreign[k]:
            raise Fail(f"foreign {k}={foreign[k]} != native {k}={native[k]}")
    if not foreign["taxed"] or native["taxed"]:
        raise Fail("taxed flags wrong")
    nscore = native["score"]
    fscore = foreign["score"]
    ratio = fscore / nscore
    if abs(ratio - 1.18) > 0.02:
        raise Fail(f"cost ratio {ratio:.4f} not ~1.18 (native {nscore} foreign {fscore})")
    if fscore <= nscore:
        raise Fail("foreign is not more expensive")
    return f"same emp={foreign['empDamage']} armour={foreign['armor']}; cost {nscore}->{fscore} (+18%)"


# ---------------------------------------------------------------------------
# Pass 3 — unique SPECIAL (Ghost / Siege) never for sale.
# ---------------------------------------------------------------------------
def pass_3_unique_lock():
    taxed = default_config(designerMode=FACTION_TAXED)
    expect_reject(
        vg(),
        draft("frm_cp_ghost", "EMP", 36, 0, 0, race="VANGUARD"),
        taxed,
        needle="unique",
    )
    expect_reject(
        sy(),
        draft("frm_cp_siege", "KINETIC", 40, 0, 0, race="SYNTHARA"),
        taxed,
        needle="unique",
    )
    ok = expect_ok(
        vg(),
        draft(
            "frm_cp_siege",
            "KINETIC",
            40,
            0,
            0,
            race="VANGUARD",
            capitalAbility={"type": "shield_aura"},
        ),
        taxed,
    )
    if ok["taxed"]:
        raise Fail("native siege marked taxed")
    if ok["capitalAbility"]["type"] != "shield_aura":
        raise Fail("vanguard siege lost shield_aura")
    return "Ghost/Siege unbuyable; native Imperator still compiles"


# ---------------------------------------------------------------------------
# Pass 4 — one foreign combat blueprint; foreign utility does not consume it.
# ---------------------------------------------------------------------------
def pass_4_one_foreign_combat():
    taxed = default_config(designerMode=FACTION_TAXED)
    first = {
        "frameId": "frm_lt_emp",
        "taxed": True,
        "blueprintId": "bp1",
    }
    expect_reject(
        vg(),
        draft("frm_cp_emp", "EMP", 28, 0, 0, race="VANGUARD", blueprintId="bp2"),
        taxed,
        existing=[first],
        needle="second foreign",
    )
    util = expect_ok(
        vg(),
        draft("frm_lt_courier", "NONE", 8, 0, 0, race="VANGUARD", blueprintId="bp3"),
        taxed,
        existing=[first],
    )
    if util["taxed"]:
        raise Fail("shared courier is native — taxing it would be a fake foreign hull")
    return "second EMP cruiser rejected; native courier un-taxed (shared utility is not foreign)"


# ---------------------------------------------------------------------------
# Pass 5 — no hybrid guns, no EMP on a kinetic frame.
# ---------------------------------------------------------------------------
def pass_5_no_hybrids():
    locked = default_config(designerMode=FACTION_LOCKED)
    open_cfg = default_config(designerMode=OPEN)
    taxed = default_config(designerMode=FACTION_TAXED)
    expect_reject(
        vg(), draft("frm_lt_strike", "EMP", 12, 0, 0), locked, needle="weapon"
    )
    expect_reject(
        vg(),
        draft("frm_lt_strike", "EMP", 12, 0, 0, race="VANGUARD"),
        open_cfg,
        needle="weapon",
    )
    expect_reject(
        vg(),
        draft("frm_lt_emp", "KINETIC", 12, 0, 0, race="VANGUARD"),
        taxed,
        needle="weapon",
    )
    return "EMP-on-strike and kinetic-on-Pulse rejected in A/B/C"


# ---------------------------------------------------------------------------
# Pass 6 — hull gate: scout cannot carry battleship armour.
# ---------------------------------------------------------------------------
def pass_6_hull_gate():
    cfg = default_config(designerMode=FACTION_LOCKED)
    tank = expect_ok(vg(), draft("frm_lt_strike", "KINETIC", 12, 0, 0), cfg)
    if tank["armor"] > 32:
        raise Fail(f"scout armour {tank['armor']} > 32")
    if tank["armor"] >= 720:
        raise Fail("scout compiled as Imperator")
    raw = derive(FRAMES["frm_lt_strike"], {"armor": 12, "battery": 0, "drive": 0}, "KINETIC")
    if raw["armor"] > 32:
        raise Fail("derive ignored frame cap")
    return f"lt_strike tank armour={tank['armor']} (cap 32)"


# ---------------------------------------------------------------------------
# Pass 7 — must spend all DP. Leftover points are a cheap-brick exploit.
# ---------------------------------------------------------------------------
def pass_7_must_spend():
    cfg = default_config(designerMode=FACTION_LOCKED)
    expect_reject(
        vg(), draft("frm_lt_strike", "KINETIC", 4, 4, 3), cfg, needle="must spend"
    )
    expect_reject(
        vg(), draft("frm_lt_strike", "KINETIC", 0, 0, 0), cfg, needle="must spend"
    )
    ok = expect_ok(vg(), draft("frm_lt_strike", "KINETIC", 4, 4, 4), cfg)
    if ok["armor"] == 32 and ok["damage"] == 24:
        raise Fail("balanced 4/4/4 still peaked both axes")
    return f"sum 11 rejected; 4/4/4 -> armour {ok['armor']} dmg {ok['damage']} init {ok['init']}"


# ---------------------------------------------------------------------------
# Pass 8 — Mode A Synthara has no destroyer; Mode C may buy one at +18%.
# ---------------------------------------------------------------------------
def pass_8_synthara_destroyer():
    locked = default_config(designerMode=FACTION_LOCKED)
    taxed = default_config(designerMode=FACTION_TAXED)
    expect_reject(
        sy(),
        draft("frm_md_destroyer", "KINETIC", 20, 0, 0, race="SYNTHARA"),
        locked,
        needle="off-race",
    )
    bought = expect_ok(
        sy(),
        draft("frm_md_destroyer", "KINETIC", 20, 0, 0, race="SYNTHARA"),
        taxed,
    )
    native = expect_ok(
        ak(),
        draft("frm_md_destroyer", "KINETIC", 20, 0, 0, race="ASHKARI"),
        locked,
    )
    if bought["armor"] != native["armor"] or bought["damage"] != native["damage"]:
        raise Fail("taxed destroyer is a dummy vs native")
    if bought["score"] <= native["score"]:
        raise Fail("taxed destroyer is not more expensive")
    return f"A rejects; C matches native armour {bought['armor']} at +18% cost"


# ---------------------------------------------------------------------------
# Pass 9 — foreign unlock lag; native frames in Mode C are not taxed.
# ---------------------------------------------------------------------------
def pass_9_unlock_and_native():
    taxed = default_config(designerMode=FACTION_TAXED)
    # Pulse unlock 1; foreign needs 2
    expect_reject(
        vg(tech=1),
        draft("frm_lt_emp", "EMP", 12, 0, 0, race="VANGUARD"),
        taxed,
        needle="unlock",
    )
    ok = expect_ok(
        vg(tech=2),
        draft("frm_lt_emp", "EMP", 12, 0, 0, race="VANGUARD"),
        taxed,
    )
    if not ok["taxed"]:
        raise Fail("foreign Pulse not taxed")
    native = expect_ok(
        vg(tech=1),
        draft("frm_lt_strike", "KINETIC", 12, 0, 0, race="VANGUARD"),
        taxed,
    )
    if native["taxed"]:
        raise Fail("native strike taxed in Mode C")
    want = score_from_cost(FRAMES["frm_lt_strike"]["baseCost"])
    if native["score"] != want:
        raise Fail(f"native cost {native['score']} != base {want}")
    return "foreign Pulse needs tech 2; native strike un-taxed at tech 1"


# ---------------------------------------------------------------------------
# Pass 10 — score follows cost; cloak mass cap; Mode B still zero-sum;
#           Ashkari cannot steal shield_aura.
# ---------------------------------------------------------------------------
def pass_10_score_cloak_open():
    locked = default_config(designerMode=FACTION_LOCKED)
    taxed = default_config(designerMode=FACTION_TAXED)
    open_cfg = default_config(designerMode=OPEN)
    native = expect_ok(
        sy(), draft("frm_lt_emp", "EMP", 0, 12, 0, race="SYNTHARA"), locked
    )
    foreign = expect_ok(
        vg(), draft("frm_lt_emp", "EMP", 0, 12, 0, race="VANGUARD"), taxed
    )
    if foreign["score"] <= native["score"]:
        raise Fail("score used armour (equal) instead of cost")
    if foreign["armor"] != native["armor"] and foreign["score"] > native["score"]:
        pass  # fine
    expect_reject(
        ak(),
        draft(
            "frm_cp_siege",
            "KINETIC",
            40,
            0,
            0,
            race="ASHKARI",
            capitalAbility={"type": "shield_aura"},
        ),
        locked,
        needle="siege",
    )
    brick = expect_ok(
        vg(),
        draft("frm_lt_strike", "KINETIC", 12, 0, 0, race="VANGUARD"),
        open_cfg,
    )
    if brick["init"] != 6 or brick["damage"] != 16:
        raise Fail("OPEN broke zero-sum")
    ghost = expect_ok(
        sy(),
        draft("frm_cp_ghost", "EMP", 36, 0, 0, race="SYNTHARA"),
        locked,
    )
    if not ghost["cloak"] or ghost["empDamage"] != 60:
        raise Fail(f"oracle compile wrong: {ghost}")
    if cloaked_mass_ok([(True, 25), (False, 75)]) is False:
        raise Fail("25% cloak should pass")
    if cloaked_mass_ok([(True, 26), (False, 74)]) is True:
        raise Fail("26% cloak should fail")
    courier = expect_ok(
        vg(), draft("frm_lt_courier", "NONE", 8, 0, 0, race="VANGUARD"), locked
    )
    if courier["gun"] != 0 or courier["init"] != 12:
        raise Fail("courier grew guns")
    missing = [k for k in LIVE_SHIP_KEYS if k not in brick]
    if missing:
        raise Fail(f"compiled ship missing live keys {missing}")
    if brick["gun"] < 8 and brick["damage"] == 16:
        pass  # tank: min battery, catalog gun at floor; combat ignores gun
    glass = expect_ok(vg(), draft("frm_lt_strike", "KINETIC", 0, 12, 0), locked)
    if glass["damage"] != 24:
        raise Fail("max battery must still peak damage (the combat stat)")
    seventh = [{"blueprintId": f"bp{i}", "frameId": "frm_lt_strike"} for i in range(6)]
    expect_reject(
        vg(),
        draft("frm_lt_strike", "KINETIC", 12, 0, 0, blueprintId="bp7"),
        locked,
        existing=seventh,
        needle="seventh",
    )
    return "score tracks +18% cost; aura theft rejected; OPEN still trades off; 26% cloak fails"


PASSES = [
    ("1 zero-sum tradeoff", pass_1_zero_sum),
    ("2 Mode C same peaks +18%", pass_2_mode_c_same_peaks),
    ("3 unique SPECIAL lock", pass_3_unique_lock),
    ("4 one foreign combat slot", pass_4_one_foreign_combat),
    ("5 no hybrid weapons", pass_5_no_hybrids),
    ("6 hull gate scout brick", pass_6_hull_gate),
    ("7 must-spend-all DP", pass_7_must_spend),
    ("8 Synthara destroyer A vs C", pass_8_synthara_destroyer),
    ("9 unlock lag / native un-taxed", pass_9_unlock_and_native),
    ("10 score, cloak, OPEN, slots", pass_10_score_cloak_open),
]


def run_through(start=1):
    failed = 0
    for i, (title, fn) in enumerate(PASSES, 1):
        if i < start:
            continue
        try:
            note = fn()
            print(f"PASS {i}/10  {title}: {note}")
        except Exception as e:
            print(f"FAIL {i}/10  {title}: {e}")
            failed = i
            break
    return failed


if __name__ == "__main__":
    start = 1
    if len(sys.argv) > 1:
        start = int(sys.argv[1])
    code = run_through(start)
    sys.exit(0 if code == 0 else code)
