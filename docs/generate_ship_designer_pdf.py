#!/usr/bin/env python3
"""Generate the Player Ship Designer proposal PDF (three rulesets, v1.4)."""
from pathlib import Path

from fpdf import FPDF

OUT = Path(__file__).resolve().parent / "Pegasus_Ship_Designer_Proposal.pdf"


class ProposalPDF(FPDF):
    def header(self):
        if self.page_no() == 1:
            return
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(90, 90, 90)
        self.set_x(self.l_margin)
        self.cell(
            0,
            8,
            "Pegasus Galaxy  |  Ship Designer v1.4  |  A locked  |  B open  |  C off-race +18%",
            align="L",
        )
        self.ln(10)
        self.set_x(self.l_margin)

    def footer(self):
        self.set_y(-12)
        self.set_x(self.l_margin)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(110, 110, 110)
        self.cell(
            0,
            8,
            f"Page {self.page_no()}/{{nb}}  |  Human design spec + AI coding-agent contract",
            align="C",
        )

    def multi_cell(self, w, h=None, text="", *args, **kwargs):
        remaining = self.w - self.r_margin - self.get_x()
        if (w == 0 or w is None) and remaining < 8:
            self.set_x(self.l_margin)
        return super().multi_cell(w, h, text, *args, **kwargs)

    def h2(self, text):
        self.ln(2)
        self.set_x(self.l_margin)
        self.set_font("Helvetica", "B", 12)
        self.set_text_color(14, 75, 117)
        self.multi_cell(0, 7, text)
        self.ln(1)
        self.set_x(self.l_margin)

    def h3(self, text):
        self.ln(1)
        self.set_x(self.l_margin)
        self.set_font("Helvetica", "B", 10.5)
        self.set_text_color(30, 41, 59)
        self.multi_cell(0, 6, text)
        self.ln(0.5)
        self.set_x(self.l_margin)

    def p(self, text):
        self.set_x(self.l_margin)
        self.set_font("Helvetica", "", 10)
        self.set_text_color(30, 30, 30)
        self.multi_cell(0, 5.2, text)
        self.ln(1.5)
        self.set_x(self.l_margin)

    def bullet(self, text, indent=6):
        self.set_x(self.l_margin + indent)
        self.set_font("Helvetica", "", 10)
        self.set_text_color(30, 30, 30)
        self.multi_cell(0, 5.1, "- " + text)
        self.ln(0.4)
        self.set_x(self.l_margin)

    def note(self, text):
        self.set_x(self.l_margin)
        self.set_font("Helvetica", "I", 9.5)
        self.set_text_color(51, 65, 85)
        self.multi_cell(0, 5, text)
        self.ln(1.5)
        self.set_x(self.l_margin)

    def code(self, text):
        self.set_x(self.l_margin)
        self.set_fill_color(241, 245, 249)
        self.set_font("Courier", "", 8)
        self.set_text_color(15, 23, 42)
        self.multi_cell(0, 4.2, text, fill=True)
        self.ln(2)
        self.set_x(self.l_margin)

    def table(self, headers, rows, col_widths=None):
        self.set_x(self.l_margin)
        usable = self.w - self.l_margin - self.r_margin
        if col_widths is None:
            col_widths = [usable / len(headers)] * len(headers)
        else:
            s = sum(col_widths)
            if s > usable + 0.1:
                col_widths = [w * usable / s for w in col_widths]
        self.set_font("Helvetica", "B", 8)
        self.set_fill_color(15, 23, 42)
        self.set_text_color(255, 255, 255)
        self.set_x(self.l_margin)
        for w, h in zip(col_widths, headers):
            self.cell(w, 6, h, border=1, fill=True)
        self.ln()
        self.set_font("Helvetica", "", 7.5)
        self.set_text_color(30, 30, 30)
        fill = False
        for row in rows:
            if self.get_y() > 270:
                self.add_page()
            self.set_fill_color(248, 250, 252)
            self.set_x(self.l_margin)
            for w, cell in zip(col_widths, row):
                self.cell(w, 5.4, str(cell), border=1, fill=fill)
            self.ln()
            fill = not fill
        self.ln(2)
        self.set_x(self.l_margin)


def build():
    pdf = ProposalPDF(format="A4")
    pdf.alias_nb_pages()
    pdf.set_auto_page_break(auto=True, margin=16)
    pdf.add_page()
    pdf.set_x(pdf.l_margin)

    pdf.set_font("Helvetica", "B", 22)
    pdf.set_text_color(15, 23, 42)
    pdf.multi_cell(0, 10, "Pegasus Galaxy")
    pdf.set_x(pdf.l_margin)
    pdf.set_font("Helvetica", "B", 16)
    pdf.set_text_color(14, 116, 144)
    pdf.multi_cell(0, 8, "Player Ship Designer")
    pdf.set_x(pdf.l_margin)
    pdf.set_font("Helvetica", "", 12)
    pdf.set_text_color(51, 65, 85)
    pdf.multi_cell(
        0,
        7,
        "Three rulesets: locked races, open/cosmetic races, taxed off-race hulls",
    )
    pdf.ln(2)
    pdf.set_font("Helvetica", "", 10)
    pdf.multi_cell(
        0,
        5.2,
        "Proposal v1.4  |  21 September 2026\n"
        "For: human design review AND an AI coding agent.\n"
        "Grounding: 35 official hulls in peg_combat.SHIP_DEFINITIONS "
        "(Vanguard, Synthara, Ashkari).\n"
        "Always a tradeoff: armour, guns, and init share one budget. "
        "A brick cannot also be a glass cannon. "
        "Off-race hulls in Mode C are the same ship as native, at +18% cost, "
        "one extra unlock level, and only one foreign combat blueprint. "
        "Do not stack a stat nerf on top of the price. Nobody buys a worse hull for more money.",
    )
    pdf.ln(1)
    pdf.note(
        "Coding-agent read order: Sec 3 invariants -> Sec 4-6 modes -> "
        "Sec 7 critic passes (esp. 4, 5, 11) -> Sec 9 zero-sum DP -> "
        "Sec 13 validate_and_compile -> Sec 16 tests. "
        "Humans: Sec 1-7 and the worked examples in Sec 9."
    )

    pdf.h2("Contents")
    for line in [
        "1. Goal",
        "2. Live catalog",
        "3. Shared fairness invariants",
        "4. MODE A - Race locked",
        "5. MODE B - No races / cosmetic only",
        "6. MODE C - Off-race hulls allowed, taxed",
        "7. Ten actor-critic passes (fairness + tradeoffs)",
        "8. Frames and hard caps",
        "9. Zero-sum Design Points (armour vs guns vs init vs weapon type)",
        "10. Weapons, cloak, EMP, capital abilities",
        "11. Economy, intel, blueprints",
        "12. Combat compatibility",
        "13. Schemas",
        "14. Validation algorithm",
        "15. Files / MCP / GUI",
        "16. Tests and exploit checklist",
        "17. Migration",
        "18. Triple-check and fairness theorem",
        "19. Final conclusions and recommendations",
    ]:
        pdf.bullet(line, indent=4)

    pdf.h2("1. Goal")
    pdf.p(
        "Replace premade named hulls as the only source of combat stats. Players design "
        "and field their own ships. The builder balances stats so there is always a "
        "tradeoff: points spent on high armour cannot also be spent on init or on the "
        "battery. Choosing a foreign weapon type in Mode C costs more to produce; "
        "the hull itself is not worse. "
        "Light, Medium, and Capital stay in today's power band. One compiler; three "
        "config modes."
    )
    pdf.bullet(
        "MODE A FACTION_LOCKED (default live Pegasus): race chosen at signup. "
        "Design only inside that race's frames and unique capital hull."
    )
    pdf.bullet(
        "MODE B OPEN: races absent or paint-only. Choose weapon type by choosing "
        "the matching frame, still inside hull gates."
    )
    pdf.bullet(
        "MODE C FACTION_TAXED (the new middle): race is real, but you MAY build "
        "generic frames from other races as the real hull, at +18% cost. "
        "Unique SPECIAL hulls (Ghost/cloak, Siege abilities) stay native-only. "
        "One foreign combat blueprint. No stat tax."
    )
    pdf.p(
        "Three live races, not two: Vanguard, Synthara, Ashkari. Do not invent a fourth. "
        "Do not trust client compiled.armor."
    )

    pdf.h2("2. Live catalog")
    pdf.p("Every Mode A lock and every Mode C tax is copied from SHIP_DEFINITIONS.")
    pdf.table(
        ["Race", "Combat guns", "EMP guns", "Cloak", "Capital ability", "Utility"],
        [
            ["Vanguard", "Kinetic only", "None", "No", "Imperator shield_aura", "Miners + haulers"],
            ["Synthara", "None (0 kinetic)", "Yes, Light+Capital", "Oracle only", "Oracle disruption_field", "Miners + haulers"],
            ["Ashkari", "Kinetic only", "None", "No", "Oblivion siege_barrier", "Miners + haulers"],
        ],
        [28, 36, 38, 26, 42, 20],
    )
    pdf.table(
        ["Band", "Categories", "Class", "Armor", "Kinetic", "EMP", "Init", "Cost sum"],
        [
            ["Light", "Fighter, Corvette", "LIGHT", "20-80", "0-24", "0-16", "3-12", "1.9k-9k"],
            ["Medium", "Frigate, Destroyer", "MEDIUM", "54-200", "0-72", "0", "4-12", "4.5k-20k"],
            ["Capital", "Cruiser, Battleship", "HEAVY", "220-420", "0-200", "0-42", "5-12", "16k-44k"],
            ["Siege/Ghost", "Battleship SPECIAL", "SPECIAL", "470-720", "0-250", "0-60", "7-11", "65k-73k"],
        ],
        [26, 38, 22, 24, 24, 18, 16, 22],
    )
    pdf.p(
        "Hard facts: no hull mixes kinetic+EMP; no Medium EMP hull exists; cloak exists "
        "on exactly one SPECIAL battleship (Synthara Oracle); each race has at most one "
        "capital ability hull; combat Light init is already 3-6 so a 'slow brick' can sit "
        "at 6 without leaving the band; utility ships have 0 guns and init 12."
    )

    pdf.h2("3. Shared fairness invariants (all three modes)")
    pdf.bullet("I1 Hull gate: compiled stats cannot exceed the chosen frame caps, even at 100% DP into one slider.")
    pdf.bullet("I2 ZERO-SUM: on combat frames, armorPts + batteryPts + drivePts MUST equal frame.dpMax. No leftover, no dump-stat. Same spendable native and foreign.")
    pdf.bullet("I3 Curve denominator is always frame.dpMax. Mode C foreign uses the same DP as native. Fairness is price + slot cap + unique lock, not a weaker hull.")
    pdf.bullet("I4 Peak-one: maxing armour forces guns AND init to the frame floor. Maxing guns forces armour and init to the floor. Always a visible tradeoff.")
    pdf.bullet("I5 Weapon type is categorical (KINETIC | EMP | NONE), never a hybrid, never a fourth slider. Foreign weapon type = Mode C frame pick at +18% cost, or Mode B's other frame.")
    pdf.bullet("I6 Init: whole integers, up or down. Paid with the SAME Design Point curve as armour and guns (f = pts/dpMax, exponent 1.6), then rounded. You do not pay 3 DP because init is 3, or 1 DP per init tick. Filling drive costs the same budget as filling armour; compiled init is just the integer on that curve. Lower is faster. Bounds are initSlow / initFast.")
    pdf.bullet("I7 Band split: combat Light max kinetic 24 < combat Medium min kinetic 44. Combat Light armour <= 54. Courier 80 is utility-only.")
    pdf.bullet("I8 Scout cannot cloak. Cloak is Ghost SPECIAL only.")
    pdf.bullet("I9 Unique SPECIAL never cross-builds, even in Mode C: Ghost and Siege stay native.")
    pdf.bullet("I10 Cost from frame.baseCost * foreignMult * siegeTax. Score uses cost, not armour. Compiler emits today's ship dict.")
    pdf.bullet("I11 Scans show frameId, band, class, weaponType, cloak, builderRace, frameNativeRace, taxed. Names are paint.")
    pdf.bullet("I12 Max 6 live blueprints per planet. Freeze on first production. Mode C: at most 1 of those 6 may be a foreign combat frame.")

    pdf.h2("4. MODE A - Race locked, player-built ships")
    pdf.p(
        "Player.race is set at account/planet creation (VANGUARD | SYNTHARA | ASHKARI) "
        "and cannot change. Designer lists only native frames. Stock Codex hulls remain "
        "cloneable templates. Off-race frames are hidden and rejected."
    )
    pdf.h3("Vanguard")
    pdf.bullet("Combat frames: kinetic only. EMP frames hidden. Ghost hidden.")
    pdf.bullet("Siege ability locked to shield_aura (Imperator).")
    pdf.bullet("Templates: Centurion, Guardian, Sentinel, Titan, Colossus, Sovereign, Imperator, plus utility.")
    pdf.h3("Synthara")
    pdf.bullet("Combat frames: EMP only. Kinetic hidden. No Medium combat line (live catalog has none).")
    pdf.bullet("Ghost (cloak + EMP + disruption_field baked) is their unique. No Siege.")
    pdf.bullet("Templates: Pulse, Arc, Nexus, Monolith, Obelisk, Singularity, Oracle, plus utility.")
    pdf.h3("Ashkari")
    pdf.bullet("Kinetic only. No EMP, no cloak. Siege ability locked to siege_barrier (Oblivion).")
    pdf.bullet("Templates: Fang, Talon, Viper, Ravager, Marauder, Reaper, Oblivion, plus utility.")
    pdf.note(
        "Mode A identity: you will never meet a cloaked Vanguard fighter or an Ashkari EMP interceptor. "
        "You WILL meet a Vanguard strike that dumped every point into armour and therefore fires last with Fang-floor guns."
    )

    pdf.h2("5. MODE B - No races, or cosmetic races only")
    pdf.p(
        "Private server / later era / sandbox. player.race is optional paint. "
        "It does not gate frames. You choose weapon type by picking the EMP frame or "
        "the kinetic frame, not by overlaying EMP onto a Fang armour curve."
    )
    pdf.bullet("Free: frame pick (weapon type), doctrine, DP split inside that frame, cosmetic label.")
    pdf.bullet("Still gated: hull caps, no hybrids, Ghost XOR Siege, cloak Ghost-only, Medium EMP only if allowMediumEmp (default false).")
    pdf.bullet("Zero-sum still applies. A Mode B brick still cannot also max guns and init.")
    pdf.bullet("If cosmeticRaces=false, hide race UI and store race=NONE.")

    pdf.h2("6. MODE C - Off-race hulls allowed, premium price")
    pdf.p(
        "Race is still real, but each race MAY build generic ships of another race's type. "
        "You get the real hull: same peaks, same DP, same tradeoffs. You pay more money and "
        "unlock later, and you may only field one foreign combat design. It is not Mode B. "
        "Unique identity hulls stay locked so cloak and siege auras cannot be bought."
    )
    pdf.h3("What you may buy foreign")
    pdf.bullet("Generic combat: frm_lt_strike, frm_lt_emp, frm_md_gun, frm_md_destroyer, frm_cp_cruiser, frm_cp_emp, frm_cp_battle.")
    pdf.bullet("Utility: courier, miners, haulers. Same +18% so a Vanguard Pulse Courier is not a free extra.")
    pdf.h3("What you may NOT buy foreign")
    pdf.bullet("frm_cp_ghost (Oracle cloak + disruption_field).")
    pdf.bullet("frm_cp_siege (Imperator shield_aura / Oblivion siege_barrier).")
    pdf.bullet("frm_md_emp unless allowMediumEmp, and even then it is Mode B-only by default.")
    pdf.h3("The premium (price and access, not a worse ship)")
    pdf.bullet("foreignCostMult = 1.18. Same stats as native, 18% more metal/crystal/eonium. Early/mid this hurts; late it is a specialist tax people will actually pay.")
    pdf.bullet("foreignDpTax = 0. Do not reintroduce. +40% AND fewer DP made Mode C dead content: nobody buys a worse Pulse for more money.")
    pdf.bullet("foreignUnlockDelta = +1. Need one extra Shipyard or Hulls level vs the native race of that frame. Time cost, not combat nerf.")
    pdf.bullet("maxForeignCombatBlueprints = 1. A Vanguard EMP wing is a counter, not a Synthara navy. Native Synthara still fields up to 6 EMP combat designs.")
    pdf.bullet("Scans mark taxed=true and show frameNativeRace. Renaming a foreign Pulse to 'Centurion' does not hide EMP.")
    pdf.h3("Worked Mode C example")
    pdf.p(
        "Vanguard wants EMP lights. Native Synthara Pulse: armour 40, emp 12, guns 6, init 5, cost ~2.3k. "
        "Vanguard foreign frm_lt_emp: same dpMax 12, same sliders, can compile the same Pulse (or a tankier/slower variant). "
        "Cost ~2.7k (+18%). Unlocks one construction level later. Occupies the single foreign combat slot. "
        "Native Synthara still wins emp-per-credit and can field many EMP blueprints. Vanguard paid for a real counter, not a dummy."
    )
    pdf.p(
        "Synthara wants a destroyer (they have none live). Foreign frm_md_destroyer: same peaks as native Marauder/Reaper band, "
        "+18% cost, +1 unlock, one slot. Ashkari/Vanguard still mass medium cheaper. Synthara bought a real medium line as a luxury, "
        "not a 75%-stat stopgap they would never produce."
    )
    pdf.note(
        "Mode C audience: live-like races, with one expensive counter. Full mix = Mode B. Pure identity = Mode A. "
        "Do not ship Mode C as the silent default. If playtests show 18% is still ignored late-game, raise cost, do not cut DP."
    )

    pdf.h2("7. Ten actor-critic passes")
    pdf.h3("Pass 1 - Tiny live ranges make tradeoffs fake")
    pdf.p("Actor: DP pool already exists; armour vs guns vs init.")
    pdf.p(
        "Critic: lt_strike armour 20-32 and init 3-4. A 4/4/4 split sits near the middle of a tiny band, "
        "so every custom light feels like a stock hull. Unused DP also lets you keep frame mins at 70% cost "
        "and field cheap almost-stock bricks."
    )
    pdf.p(
        "Fix: MUST spend exactly spendable DP (I2). InitSlow on combat lights is 6 (in-band: Nexus is 6), "
        "InitFast stays at the live best (Fang 3). Max armour now means you fire with the slow lights, not "
        "almost-as-fast as Fang. Caps still never exceed live max."
    )

    pdf.h3("Pass 2 - God ship = max armour AND max guns")
    pdf.p("Actor: Independent sliders with separate caps.")
    pdf.p("Critic: If sliders do not steal from each other, the rational design is max everything. Cost scaling does not stop that; it just makes the god ship expensive.")
    pdf.p(
        "Fix: Three combat pools, sum MUST equal spendable. Max armour compiles guns to frame min and init to initSlow. "
        "UI is three sliders that steal. Preview must show the other two falling as you raise armour."
    )

    pdf.h3("Pass 3 - Weapon type as a fourth slider")
    pdf.p("Actor: Spend DP on 'weapon type' so EMP vs kinetic is a point cost.")
    pdf.p(
        "Critic: Weapon type is categorical. Half-EMP is a hybrid, which live combat never has and which deletes "
        "the EMP-vs-kinetic counter. A slider labelled weapon type would either be a hidden hybrid or a no-op."
    )
    pdf.p(
        "Fix: Weapon type is a FRAME pick. Native: 0 surcharge. Mode C foreign frame: +18% cost, same DP. "
        "Mode B: you pick frm_lt_emp or frm_lt_strike; you do not bolt EMP onto Fang's 20-armour curve."
    )

    pdf.h3("Pass 4 - Mode C as cost-only tax")
    pdf.p("Actor: Allow all frames, multiply cost by 1.5 (or 1.4) AND cut DP.")
    pdf.p(
        "Critic (v1.2): Late-game metal is abundant, so cost alone looked weak. Critic (v1.3, player): "
        "nobody buys a hull that is both more expensive AND worse. +40% and -25% DP is dead content, not balance."
    )
    pdf.p(
        "Fix: Same stats as native. foreignCostMult=1.18 (buyable specialist tax). foreignUnlockDelta=+1 "
        "(time, not combat). Unique SPECIAL still locked. One foreign combat blueprint. Identity is slot+unique, "
        "not a sadder Pulse. If 18% is ignored late, raise the price, do not cut DP."
    )

    pdf.h3("Pass 5 - DP tax (retracted)")
    pdf.p("Actor: spendable = 0.75 * dpMax so foreign cannot peak.")
    pdf.p(
        "Critic: That is the same as selling a dummy. Players skip Mode C. Also if f = pts/spendable the peak "
        "nerf fails anyway; if f = pts/dpMax the hull is just worse and still costs more."
    )
    pdf.p(
        "Fix: foreignDpTax = 0. spendable = frame.dpMax for everyone. f = pts / dpMax. Tests C5/C6 now assert "
        "EQUAL peaks at equal alloc, and cost * 1.18."
    )

    pdf.h3("Pass 6 - Buying Oracle / Imperator / Oblivion")
    pdf.p("Actor: Those are just expensive frames; tax them too.")
    pdf.p("Critic: Then every Mode C empire fields cloak. Scan meta dies. shield_aura stacking plus cloak is the actual god fleet.")
    pdf.p("Fix: I9. Ghost and Siege are native-only in A and C. Mode B may unlock them because Mode B already admitted race is paint.")

    pdf.h3("Pass 7 - Unlimited foreign blueprints")
    pdf.p("Actor: Tax is enough; let them fill all 6 slots with foreign hulls.")
    pdf.p("Critic: Six taxed Pulses plus native Imperator is still a mixed-doctrine navy. Mode C identity is gone.")
    pdf.p("Fix: maxForeignCombatBlueprints = 1. Foreign utility does not count against that 1. Native slots remain 5+.")

    pdf.h3("Pass 8 - Utility as a dump-stat on combat frames")
    pdf.p("Actor: Four pools (armour/battery/drive/utility) so cargo or empResist can soak leftover points.")
    pdf.p("Critic: Everyone puts 0 in utility, which is leftover DP by another name, and combat hulls become 3-axis gods again. empResist-as-dump also lets kinetic races buy Synthara-like resists.")
    pdf.p(
        "Fix: Combat frames have exactly three pools. empResistance is compiled from the FRAME, not a slider "
        "(Pulse resist 12, Fang resist 0 - native identity). Cargo only on utility frames."
    )

    pdf.h3("Pass 9 - Synthara Mode C destroyer is a silent content expansion")
    pdf.p("Actor: Fairness means every race can fill Light/Medium/Capital.")
    pdf.p("Critic: Live Synthara has no medium combat line. Giving them a free destroyer in Mode A rewrites the Codex. Giving it away cheap in Mode C does the same.")
    pdf.p("Fix: Mode A: still no. Mode C: allowed as foreign frm_md_destroyer with native peaks, +18% cost, +1 unlock, one slot. Native Marauder/Reaper/Sentinel stay cheaper to mass.")

    pdf.h3("Pass 10 - Fairness theorem")
    pdf.p("Actor: After nine patches, is a god ship still possible?")
    pdf.p(
        "Critic leftover risks: (1) stacking many cheap min-stat hulls if must-spend is waived; (2) Mode B everyone Ghost; "
        "(3) renaming foreign EMP to a kinetic stock name; (4) editing a frozen tank into a glass cannon after launch; "
        "(5) scoring by armour so bricks farm rank."
    )
    pdf.p(
        "Fix: must-spend stays; Mode B Ghost still 25% fleet-mass cloak cap; scans send frame+weaponType+taxed; freeze on produce; "
        "score from cost. Theorem: for any generic frame F, a Mode C compile can MATCH the native compile of F "
        "on every combat axis, and costs 18% more. Native always wins same-frame credits-per-stat. "
        "Mode C cannot mass mixed doctrine (1 combat slot) and cannot buy cloak/siege."
    )

    pdf.h2("8. Shared hull bands, frames, hard caps")
    pdf.p("Same frame table for all modes. Mode A filters by allowedFrameIds. Mode C adds taxed generic frames. Mode B shows all legal frames.")
    pdf.table(
        ["Frame", "Band", "Class", "A native", "C foreign?", "B"],
        [
            ["frm_lt_strike", "Light", "FIGHTER LIGHT", "V / Ash", "Yes, taxed", "Yes"],
            ["frm_lt_emp", "Light", "FIGHTER LIGHT", "Synthara", "Yes, taxed", "Yes"],
            ["frm_lt_courier", "Light", "CORVETTE LIGHT", "All", "Yes, taxed", "Yes util"],
            ["frm_md_gun", "Medium", "FRIGATE MEDIUM", "V / Ash", "Yes, taxed", "Yes"],
            ["frm_md_destroyer", "Medium", "DESTROYER MEDIUM", "V / Ash", "Yes, taxed", "Yes"],
            ["frm_md_emp", "Medium", "DESTROYER MEDIUM", "Hidden", "No (B flag)", "Flag"],
            ["frm_md_miner/hauler", "Medium", "FRIGATE MEDIUM", "All", "Yes, taxed", "Yes util"],
            ["frm_cp_cruiser", "Capital", "CRUISER HEAVY", "V / Ash", "Yes, taxed", "Yes"],
            ["frm_cp_emp", "Capital", "CRUISER HEAVY", "Synthara", "Yes, taxed", "Yes"],
            ["frm_cp_battle", "Capital", "BATTLESHIP HEAVY", "V / Ash", "Yes, taxed", "Yes"],
            ["frm_cp_ghost", "SPECIAL", "BATTLESHIP SPECIAL", "Synthara", "NEVER", "If unlock"],
            ["frm_cp_siege", "SPECIAL", "BATTLESHIP SPECIAL", "V or Ash", "NEVER", "If unlock"],
        ],
        [36, 22, 40, 28, 28, 36],
    )
    pdf.table(
        ["Frame", "Armor", "Dmg", "EMP", "Guns", "InitFast-Slow", "DP", "Base M/C/E"],
        [
            ["lt_strike", "20-32", "16-24", "0", "8-11", "3-6", "12", "900/500/500"],
            ["lt_emp", "40-54", "0", "12-16", "6-8", "5-6", "12", "1100/900/800"],
            ["lt_courier", "80", "0", "0", "0", "12", "8", "3000/3000/3000"],
            ["md_gun", "54-94", "44-58", "0", "15-17", "4-6", "18", "1800/1400/1300"],
            ["md_destroyer", "66-116", "54-72", "0", "17-19", "4-6", "20", "2800/2500/2400"],
            ["md_emp (B)", "66-116", "0", "20-28", "15-19", "4-6", "20", "3000/2800/2600"],
            ["cp_cruiser", "250-340", "112-156", "0", "25-30", "5-8", "28", "7000/5000/4200"],
            ["cp_emp", "250-330", "0", "30-36", "20-24", "8-10", "28", "8000/6000/5000"],
            ["cp_battle", "340-420", "156-200", "0", "30-34", "6-9", "32", "12000/9000/8000"],
            ["cp_ghost", "640", "0", "60", "30", "8", "36", "22000/22000/21000"],
            ["cp_siege", "470-720", "170-250", "0", "42-55", "7-11", "40", "25000/22000/20000"],
        ],
        [30, 22, 22, 16, 16, 24, 12, 48],
    )
    pdf.note(
        "InitFast-Slow: first number is live-best (max drive), second is designer-slow (0 drive). "
        "lt_strike slow 6 matches live Nexus; it does not invent a new band. Ghost/Siege keep live init; "
        "they are unique hulls, not a point-buy toy."
    )

    pdf.h2("9. Zero-sum Design Points")
    pdf.p(
        "Combat frames expose three integer sliders: armour, battery, drive. "
        "Utility frames expose armour, cargo, drive (guns forced 0, init 12). "
        "There is no fourth combat slider."
    )
    pdf.code(
        "spendable = frame.dpMax          # foreignDpTax stays 0. Same DP native and foreign.\n"
        "assert armorPts + batteryPts + drivePts == spendable   # also enforced inside derive()\n"
        "f(axis) = axisPts / frame.dpMax                 # same budget share for armour, guns, init\n"
        "value  = M + (X - M) * (1 - (1 - f) ** 1.6)\n"
        "init   = round(initSlow + (initFast - initSlow) * (1 - (1 - f_drive) ** 1.6))\n"
        "# init is an integer on that curve. Cost is drivePts, not the init number.\n"
        "KINETIC: damage from battery, empDamage=0\n"
        "EMP:     empDamage from battery, damage=0\n"
        "NONE:    batteryPts must be 0"
    )
    pdf.h3("Worked native lt_strike (dpMax 12, spendable 12)")
    pdf.table(
        ["Build", "Alloc A/B/D", "Armor", "Dmg", "Init", "What you paid"],
        [
            ["Tank / god armour", "12 / 0 / 0", "32", "16", "6", "Max plate. Fang-floor guns. Fires last among lights."],
            ["Glass cannon", "0 / 12 / 0", "20", "24", "6", "Viper-peak guns. Fang-floor plate. Still slow."],
            ["Interceptor", "0 / 0 / 12", "20", "16", "3", "Fang-fast. Fang-floor guns and plate."],
            ["Balanced", "4 / 4 / 4", "26", "20", "5", "Mid all three. No peak. Not a god ship."],
            ["Stock-ish", "6 / 6 / 0", "28", "21", "6", "Plate+guns, no drive: mid tank that is slow."],
        ],
        [32, 28, 18, 16, 14, 82],
    )
    pdf.p(
        "Read the table as the contract: you may have 32 armour on a strike, and then you do not also have "
        "24 damage or init 3. Weapon type for this frame is kinetic; to get EMP you pick frm_lt_emp (Mode B) "
        "or pay Mode C tax. You never overlay EMP onto this armour curve."
    )
    pdf.h3("Worked Mode C Vanguard foreign Pulse")
    pdf.p(
        "Same dpMax 12, same sliders, same peaks as native Synthara. All-battery: emp 16, armour 40, init 6. "
        "Cost 2800 -> 3304 (+18%). Unlocks one tech level later. Occupies the single foreign combat slot. "
        "Native Synthara still wins emp-per-credit (they can field six EMP designs; Vanguard can field one). "
        "The hull is a real Pulse, not a dummy."
    )

    pdf.h2("10. Weapons, cloak, EMP, capital abilities")
    pdf.table(
        ["Feature", "Mode A", "Mode C", "Mode B"],
        [
            ["Pick weapon type", "No. Race+frame.", "Yes, by taxed foreign frame", "Yes, by frame pick"],
            ["Hybrid gun", "No", "No", "No"],
            ["High armour cost", "Loses guns+init", "Loses guns+init (same as native)", "Loses guns+init"],
            ["Cloak", "Synthara Ghost only", "Synthara Ghost only", "Anyone, Ghost frame"],
            ["shield_aura", "Vanguard Siege", "Vanguard Siege", "Siege radio"],
            ["siege_barrier", "Ashkari Siege", "Ashkari Siege", "Siege radio"],
            ["Medium EMP", "No", "No", "allowMediumEmp default false"],
            ["Race change", "Never", "Never", "Anytime (paint)"],
        ],
        [36, 48, 52, 54],
    )
    pdf.p(
        "Cloak fleet rule (all modes): cloaked mass <= 25% of launched fleet mass. "
        "Mode A/C Ghost bakes disruption_field with cloak (Oracle translation). "
        "Mode B Ghost: same bake, not a second tick-box. Ghost XOR Siege on one blueprint."
    )
    pdf.note(
        "GUN IS NOT USED IN COMBAT TODAY. peg_combat.py and docs/calc.html both fire "
        "count * damage * targetEfficiency (EMP: count * empDamage). The gun field is stored "
        "on the hull and shown as 'Gun Rating' in the Codex, but it is never multiplied into "
        "damage. A fallback gun*2.5 exists only when damage is missing. Do not give gun its "
        "own Design Point slider: that would be a dump-stat (players would put 0 in gun and "
        "max the stats the engine actually reads). Compile gun from the battery slider so the "
        "catalog still looks like live hulls. If the live server later implements "
        "count*gun*damage, split gun onto the DP budget then; do not change simulate_combat "
        "to * gun until a live trace proves it. Fang 16 dmg vs 20 armour only makes sense if "
        "damage is already the ship's round output."
    )

    pdf.h2("11. Economy, intel, blueprints")
    pdf.code(
        "foreign = (mode==TAXED and frame not in native allowedFrameIds)\n"
        "mult = (1.18 if foreign else 1.0) * (1.08 if siege ability else 1.0)\n"
        "cost[r] = round(frame.baseCost[r] * mult)\n"
        "# foreignDpTax = 0. Must-spend-all: no 0.70 floor exploit. Cost is the frame, doctrine is the sliders."
    )
    pdf.bullet("Blueprints: 6 per planet, DRAFT then FROZEN. Produce only FROZEN. Scrap only at 0 units.")
    pdf.bullet("Mode A: blueprint.race == player.race; frame native.")
    pdf.bullet("Mode C: blueprint.race == player.race always (you are still Vanguard). blueprint.taxed if foreign. At most one taxed combat blueprint.")
    pdf.bullet("Mode B: cosmeticRace optional; compiled.faction = cosmetic or NONE.")
    pdf.bullet("Scans: frameId, band, class, weaponType, cloak, builderRace, frameNativeRace, taxed, compiled stats, name.")
    pdf.bullet("Score from cost. Clone stock hull consumes a slot.")

    pdf.h2("12. Combat compatibility")
    pdf.code(
        "id, name, faction, category, shipClass, armor, damage, empDamage,\n"
        "empResistance, gun, init, cloak, cost{metal,crystal,eonium},\n"
        "asteroidCapacity, resourceCapacity, capitalAbility,\n"
        "targetClass1, targetClass2, targetClass3"
    )
    pdf.p(
        "simulate_combat unchanged: kinetic = count * damage * targetEfficiency; "
        "EMP = count * empDamage. Hulls +5% armour/lvl, home +10%, PDS, 30% salvage, "
        "Imperator aura max 25%. empResistance is a real combat stat (chance = 0.5 - resist/100; "
        "100 = immune) and sits on the DP budget. gun is compiled for the catalog but is not "
        "read by the firing loop. Cost metal/crystal/eonium are the three live minerals; "
        "score = sum/9 in the calc, designer score uses the same three-resource total."
    )

    pdf.h2("13. Schemas")
    pdf.h3("config")
    pdf.code(
        "{\n"
        '  "designerMode": "FACTION_LOCKED",  // or FACTION_TAXED or OPEN\n'
        '  "cosmeticRaces": false,\n'
        '  "allowMediumEmp": false,\n'
        '  "foreignCostMult": 1.18,\n'
        '  "foreignDpTax": 0,\n'
        '  "foreignUnlockDelta": 1,\n'
        '  "maxForeignCombatBlueprints": 1\n'
        "}"
    )
    pdf.h3("race profile")
    pdf.code(
        "{\n"
        '  "id": "VANGUARD",\n'
        '  "nativeFrameIds": ["frm_lt_strike","frm_lt_courier","frm_md_gun",\n'
        '    "frm_md_destroyer","frm_md_miner","frm_md_hauler","frm_cp_cruiser",\n'
        '    "frm_cp_miner","frm_cp_battle","frm_cp_siege"],\n'
        '  "weaponLock": "KINETIC",\n'
        '  "siegeAbility": "shield_aura",\n'
        '  "allowsGhost": false,\n'
        '  "uniqueFrameIds": ["frm_cp_siege"]\n'
        "}"
    )
    pdf.p(
        "SYNTHARA native: lt_emp, cp_emp, cp_ghost, utility; weaponLock EMP; allowsGhost true; unique=[frm_cp_ghost]. "
        "ASHKARI like Vanguard but siege_barrier. uniqueFrameIds are never legal as foreign in Mode C."
    )
    pdf.h3("blueprint")
    pdf.code(
        "{\n"
        '  "blueprintId": "bp_...", "frameId": "frm_lt_emp",\n'
        '  "status": "DRAFT", "name": "Borrowed Pulse",\n'
        '  "race": "VANGUARD", "taxed": true, "frameNativeRace": "SYNTHARA",\n'
        '  "weaponType": "EMP", "doctrine": "ANTI_LIGHT",\n'
        '  "alloc": {"armor": 0, "battery": 12, "drive": 0},\n'
        '  "compiled": { }\n'
        "}"
    )

    pdf.h2("14. Validation algorithm")
    pdf.code(
        "function validate_and_compile(player, draft, cfg, existingBps):\n"
        "  frame = FRAMES[draft.frameId] or reject\n"
        "  assert unlocked(player, frame.unlock)\n"
        "  native = draft.frameId in RACES[player.race].nativeFrameIds\n"
        "  unique = draft.frameId in ANY race.uniqueFrameIds\n"
        "  if cfg.designerMode == 'FACTION_LOCKED':\n"
        "      assert native and draft.race == player.race\n"
        "      assert draft.weaponType == frame.weaponAllowed[0]\n"
        "  elif cfg.designerMode == 'FACTION_TAXED':\n"
        "      assert draft.race == player.race\n"
        "      if not native:\n"
        "          assert not unique                 # no bought Oracle/Imperator\n"
        "          assert frame.band != 'md_emp' or cfg.allowMediumEmp\n"
        "          assert combat_foreign <= cfg.maxForeignCombatBlueprints\n"
        "          assert tech >= frame.unlock + cfg.foreignUnlockDelta\n"
        "          foreign = True\n"
        "      else:\n"
        "          foreign = False\n"
        "          if frame.id == 'frm_cp_siege':\n"
        "              assert draft.capitalAbility.type == prof.siegeAbility\n"
        "  else:  # OPEN\n"
        "      assert draft.weaponType in frame.weaponAllowedOpen\n"
        "      if frame.id == 'frm_md_emp': assert cfg.allowMediumEmp\n"
        "      foreign = False\n"
        "  spendable = frame.dpMax          # ignore foreignDpTax; it must stay 0\n"
        "  assert sum(alloc) == spendable   # derive() asserts this too\n"
        "  compiled = derive(frame, alloc, denominator=frame.dpMax)  # clamp [M,X]\n"
        "  compiled.cost *= (cfg.foreignCostMult if foreign else 1)\n"
        "  compiled.cloak = (frame.id == 'frm_cp_ghost')\n"
        "  compiled.taxed = foreign\n"
        "  return compiled"
    )

    pdf.h2("15. Files / MCP / GUI")
    pdf.bullet("docs/ship_designer_rules.py (executable compile/validate), docs/test_ship_designer_fairness.py (10 sequential passes).")
    pdf.bullet("MCP: list_ship_frames (A: native; C: native + generic foreign tagged taxed; B: all), list_blueprints, save_blueprint_draft, finalize_blueprint, scrap_blueprint; produce_ships(blueprintId).")
    pdf.bullet("GUI: three sliders that steal. Live preview of armour/guns/init. Mode A hides foreign. Mode C shows foreign with a +18% badge, same stats, greyed unique SPECIAL. Mode B is a frame picker, not a fighter-cloak checkbox.")
    pdf.bullet("peg_combat.py: no fork. Unknown IDs resolve from compiled snapshot on the fleet/scan payload.")

    pdf.h2("16. Tests and exploit checklist")
    pdf.h3("Mode A")
    pdf.bullet("A1 Vanguard weapon EMP -> reject.")
    pdf.bullet("A2 Vanguard frm_cp_ghost -> reject.")
    pdf.bullet("A3 Ashkari siege shield_aura -> reject.")
    pdf.bullet("A4 Synthara frm_md_destroyer -> reject.")
    pdf.bullet("A5 Synthara Ghost: cloak true, damage 0, emp 60, SPECIAL.")
    pdf.bullet("A6 lt_strike alloc 12/0/0: armour 32, damage 16, init 6. Not 32/24/3.")
    pdf.bullet("A7 lt_strike alloc 4/4/3 (sum 11) -> reject (must spend 12).")
    pdf.h3("Mode B")
    pdf.bullet("B1 OPEN + lt_strike + EMP -> reject (wrong frame).")
    pdf.bullet("B2 OPEN + cosmetic Vanguard + Ghost -> allow if unlocked.")
    pdf.bullet("B3 OPEN + md_emp when allowMediumEmp false -> reject.")
    pdf.bullet("B4 OPEN lt_strike 12/0/0 still init 6, damage 16 (zero-sum survives OPEN).")
    pdf.h3("Mode C")
    pdf.bullet("C1 Vanguard frm_lt_emp allowed, taxed true, cost * 1.18, emp/armour equal to native Pulse.")
    pdf.bullet("C2 Vanguard frm_cp_ghost -> reject (unique).")
    pdf.bullet("C3 Vanguard frm_cp_siege native shield_aura still allowed (not foreign).")
    pdf.bullet("C4 Second foreign combat blueprint -> reject. Native courier is not foreign.")
    pdf.bullet("C5 Vanguard Pulse all-battery: emp == 16 (same as native). Stat nerf is a bug.")
    pdf.bullet("C6 Same hull all-armour: armour == 54, same as native.")
    pdf.bullet("C7 Synthara frm_md_destroyer allowed taxed; peaks == native destroyer; Mode A still rejects this.")
    pdf.bullet("C8 Native Vanguard strike un-taxed in Mode C. Foreign Pulse needs unlock+1.")
    pdf.h3("Shared")
    pdf.bullet("S1 lt_strike 12 all armour -> armour <= 32, not 720.")
    pdf.bullet("S2 Courier guns > 0 -> reject.")
    pdf.bullet("S3 Cloaked mass > 25% of launch -> reject.")
    pdf.bullet("S4 Seventh blueprint -> reject. Produce DRAFT -> reject.")
    pdf.bullet("S5 simulate_combat stock Fang vs compiled Ashkari strike -> no throw.")
    pdf.bullet("S6 Score uses cost; taxed Pulse scores higher than native Pulse, not by armour.")
    pdf.h3("Exploits closed")
    pdf.bullet("Billion-armour scout: clamp. Cloaked fighter: no frame. Hybrid: no. Leftover DP cheap brick: must-spend (also inside derive). Mode C whale Oracle: unique lock. Mode C six Pulses: 1-slot cap. Worse-and-pricier dummy: foreignDpTax=0. Rename Centurion: scans send frame+weaponType+taxed. Edit after launch: freeze. Rank via armour: score uses cost.")

    pdf.h2("17. Migration")
    pdf.bullet("Phase A: stock IDs still produce. Designer optional. designerMode=FACTION_LOCKED.")
    pdf.bullet("Phase B: stock hulls are clone templates of that race (they sit at one legal alloc, not a fourth power band).")
    pdf.bullet("Phase C: bots keep using main-vanguard-centurion aliases.")
    pdf.p(
        "FACTION_TAXED and OPEN are server flags. Do not flip live Pegasus off FACTION_LOCKED without a season "
        "announcement. Mode C is a product choice, not a silent default."
    )

    pdf.h2("18. Triple-check")
    pdf.h3("Check A - Live races")
    pdf.p(
        "Three races, kinetic vs EMP split, one cloak hull, three different capital abilities, no hybrid guns, "
        "no Medium EMP, utility init 12. Mode A reproduces that map. Custom ships only move numbers inside a "
        "race's box, and moving armour UP moves guns and init DOWN."
    )
    pdf.h3("Check B - Open is not anything")
    pdf.p(
        "You may choose weapon type by choosing the matching frame. You may not put 720 armour on a fighter, "
        "cloak a courier, mount EMP and kinetic together, or max armour and max guns on the same hull."
    )
    pdf.h3("Check C - Off-race is a buyable counter, not a dummy")
    pdf.p(
        "You may buy a foreign generic frame. You pay 18% more and unlock one level later. "
        "You get the same peaks as native. You cannot buy Ghost or Siege. You may only field one "
        "foreign combat blueprint. Native always wins credits-per-stat (fairness theorem). "
        "Executable proof: python docs/test_ship_designer_fairness.py (10/10)."
    )
    pdf.h3("Check D - Agent can implement")
    pdf.p(
        "One compiler, one validate() with a three-way mode branch, one frame table, three race profiles. "
        "GUI never sends compiled.armor. Tests A* B* C* S* are concrete. Remaining feel tweaks are JSON caps."
    )
    pdf.h3("Accepted tensions")
    pdf.bullet("Courier armour 80 > strike 32: different frames, courier has no guns.")
    pdf.bullet("Synthara has no Medium combat in Mode A: copied from live catalog. Mode C sells a real destroyer at +18%, one slot.")
    pdf.bullet("Ghost is barely customizable: Oracle is unique today and stays unique in A/C.")
    pdf.bullet("InitSlow 6 on a kinetic light is slower than live Fang/Talon. That is the brick tax, still in-band.")
    pdf.bullet("Must-spend-all means a tank and a glass cannon of the same frame cost the same. Doctrine is free; frame is the price. Foreign is the surcharge.")
    pdf.bullet("gun is a catalog field, not a combat multiplier, in the current engine.")

    pdf.h2("19. Final conclusions and recommendations")
    pdf.h3("What to ship")
    pdf.bullet("Default: designerMode=FACTION_LOCKED (Mode A). Race stays Vanguard / Synthara / Ashkari as live. Players design inside that race's frames. Zero-sum DP: armour vs battery (damage XOR emp) vs drive (init) vs empResistance.")
    pdf.bullet("Mode C FACTION_TAXED: off-race generic hulls at +18% cost, +1 unlock, same peaks, one foreign combat blueprint. Unique Ghost/Siege stay native. Do not stack a stat nerf on the price.")
    pdf.bullet("Mode B OPEN: private/sandbox only. Cosmetic races. Same hull gates. Not a silent live default.")
    pdf.h3("Combat formula (do not invent gun*damage)")
    pdf.bullet("Keep kinetic as count * damage * targetEfficiency and EMP as count * empDamage. That is what peg_combat.py and calc.html implement, and it matches live hull numbers (Fang 16 vs armour 20).")
    pdf.bullet("gun is not currently implemented in the game combat loop. Compile it for Codex parity; do not spend Design Points on it; do not multiply it into firepower until a live-server trace says otherwise.")
    pdf.h3("Always a tradeoff")
    pdf.bullet("Must spend exactly dpMax. Max armour => min battery and worst init. Init steps up or down in whole numbers on the same 1.6 curve as armour, not 'init 3 costs 3 points'.")
    pdf.bullet("Scout cannot carry battleship armour. No hybrid kinetic+EMP. Cloak Ghost-only. Six blueprints, freeze on produce.")
    pdf.h3("Implementation order")
    pdf.bullet("1. Server compiler from docs/ship_designer_rules.py. Client never submits compiled.armor or compiled.damage.")
    pdf.bullet("2. Encode tests: python docs/test_ship_designer_fairness.py must stay 10/10, plus A/B/C/S list in Sec 16.")
    pdf.bullet("3. GUI: three (or four, if resist is shown) sliders that steal. Preview live stats. Hide gun as a power slider; show it as 'rating (unused in combat)'.")
    pdf.bullet("4. Mode A only on live Pegasus. Mode C/B behind config.")
    pdf.h3("Do not")
    pdf.bullet("Do not implement raw stat text fields. Do not trust client compiled stats. Do not flip live to OPEN. Do not sell Oracle/Imperator as taxed foreign hulls. Do not change simulate_combat to count*gun*damage.")
    pdf.ln(3)
    pdf.set_x(pdf.l_margin)
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(15, 23, 42)
    pdf.multi_cell(0, 6, "Decision")
    pdf.set_x(pdf.l_margin)
    pdf.set_font("Helvetica", "", 10)
    pdf.multi_cell(
        0,
        5.2,
        "Ship Mode A + zero-sum designer as the live proposal. Keep gun as unused catalog paint. "
        "Offer Mode C (+18%, same peaks, one slot) as an explicit flag. Keep OPEN for sandbox. "
        "This PDF plus docs/ship_designer_rules.py and docs/test_ship_designer_fairness.py are the "
        "implementation contract.",
    )

    pdf.output(OUT)
    print("Wrote", OUT, "bytes", OUT.stat().st_size)


if __name__ == "__main__":
    build()
