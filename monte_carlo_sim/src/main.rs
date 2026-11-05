//! Live-catalog Monte Carlo / exhaustive matchup engine.
//! Combat rules copied from peg_combat.py (22 Oct 2026 live SHIP_DEFINITIONS).
//! Kinetic = count * damage * targetEfficiency (100 / 80 / 70, fallback 100).
//! EMP chance = 0.5 - empResistance/100; one group silenced per shooter.

use std::env;
use std::time::Instant;

#[derive(Clone, Copy, PartialEq, Eq)]
enum Class {
    Light = 0,
    Medium = 1,
    Heavy = 2,
    Special = 3,
}

#[derive(Clone, Copy)]
#[allow(dead_code)]
struct ShipDef {
    name: &'static str,
    faction: &'static str,
    class: Class,
    armor: f64,
    damage: f64,
    emp_damage: f64,
    emp_res: f64,
    init: u8,
    cost_m: f64,
    cost_c: f64,
    cost_e: f64,
    t1: Option<Class>,
    t2: Option<Class>,
    t3: Option<Class>,
    cloak: bool,
    is_imperator: bool,
    is_oblivion: bool,
}

impl ShipDef {
    fn cost(&self) -> f64 {
        self.cost_m + self.cost_c + self.cost_e
    }
}

const N: usize = 24;
const N_ARCH: usize = 25;
const BUDGET: f64 = 10_000_000.0;

const VG_CENT: usize = 0;
const VG_GUARD: usize = 1;
const VG_SENT: usize = 2;
#[allow(dead_code)]
const VG_TITAN: usize = 3;
#[allow(dead_code)]
const VG_COLO: usize = 4;
const VG_SOV: usize = 5;
const VG_IMP: usize = 6;
const ASH_FANG: usize = 7;
const ASH_TALON: usize = 8;
const ASH_VIPER: usize = 9;
const ASH_RAV: usize = 10;
const ASH_MAR: usize = 11;
const ASH_REAP: usize = 12;
const ASH_OBL: usize = 13;
const SYN_PULSE: usize = 14;
const SYN_ARC: usize = 15;
const SYN_NEX: usize = 16;
const SYN_MONO: usize = 17;
const SYN_OBEL: usize = 18;
const SYN_SING: usize = 19;
const SYN_ORA: usize = 20;
const VG_PICKET: usize = 21;
const ASH_JUG: usize = 22;
const SYN_LAT: usize = 23;

const DEFS: [ShipDef; N] = [
    // Vanguard
    ship("Centurion", "Vanguard", Class::Medium, 89.0, 44.0, 0.0, 10.0, 4, 2200.0, 1400.0, 900.0, Some(Class::Medium), Some(Class::Heavy), Some(Class::Light), false, false, false),
    ship("Guardian", "Vanguard", Class::Medium, 113.0, 58.0, 0.0, 14.0, 4, 3000.0, 1900.0, 1200.0, Some(Class::Heavy), Some(Class::Medium), Some(Class::Light), false, false, false),
    ship("Sentinel", "Vanguard", Class::Medium, 139.0, 72.0, 0.0, 16.0, 4, 3800.0, 2400.0, 1500.0, Some(Class::Light), Some(Class::Medium), Some(Class::Heavy), false, false, false),
    ship("Titan", "Vanguard", Class::Heavy, 250.0, 112.0, 0.0, 24.0, 5, 7800.0, 4900.0, 3500.0, Some(Class::Medium), Some(Class::Heavy), Some(Class::Light), false, false, false),
    ship("Colossus", "Vanguard", Class::Heavy, 340.0, 156.0, 0.0, 30.0, 6, 11200.0, 7600.0, 5400.0, Some(Class::Heavy), Some(Class::Medium), Some(Class::Light), false, false, false),
    ship("Sovereign", "Vanguard", Class::Heavy, 420.0, 200.0, 0.0, 35.0, 6, 14400.0, 9900.0, 7200.0, Some(Class::Medium), Some(Class::Heavy), Some(Class::Light), false, false, false),
    ship("Imperator", "Vanguard", Class::Special, 720.0, 170.0, 0.0, 45.0, 11, 34000.0, 22000.0, 17000.0, Some(Class::Heavy), Some(Class::Medium), Some(Class::Light), false, true, false),
    // Ashkari
    ship("Fang", "Ashkari", Class::Light, 24.0, 16.0, 0.0, 19.0, 3, 900.0, 500.0, 500.0, Some(Class::Medium), Some(Class::Light), Some(Class::Heavy), false, false, false),
    ship("Talon", "Ashkari", Class::Light, 31.0, 21.0, 0.0, 20.0, 3, 1250.0, 700.0, 700.0, Some(Class::Light), Some(Class::Medium), Some(Class::Heavy), false, false, false),
    ship("Viper", "Ashkari", Class::Light, 36.0, 24.0, 0.0, 21.0, 4, 1500.0, 850.0, 850.0, Some(Class::Medium), Some(Class::Heavy), Some(Class::Light), false, false, false),
    ship("Ravager", "Ashkari", Class::Medium, 54.0, 44.0, 0.0, 24.0, 4, 3200.0, 1800.0, 1800.0, Some(Class::Medium), Some(Class::Light), Some(Class::Heavy), false, false, false),
    ship("Marauder", "Ashkari", Class::Medium, 66.0, 54.0, 0.0, 26.0, 5, 4200.0, 2400.0, 2400.0, Some(Class::Light), Some(Class::Medium), Some(Class::Heavy), false, false, false),
    ship("Reaper", "Ashkari", Class::Medium, 80.0, 62.0, 0.0, 28.0, 5, 5200.0, 3000.0, 3000.0, Some(Class::Medium), Some(Class::Heavy), Some(Class::Light), false, false, false),
    ship("Oblivion", "Ashkari", Class::Special, 470.0, 250.0, 0.0, 100.0, 7, 30000.0, 18000.0, 19000.0, Some(Class::Heavy), Some(Class::Medium), Some(Class::Light), false, false, true),
    // Synthara
    ship("Pulse", "Synthara", Class::Light, 40.0, 0.0, 12.0, 12.0, 2, 900.0, 1000.0, 400.0, Some(Class::Heavy), Some(Class::Light), Some(Class::Medium), false, false, false),
    ship("Arc", "Synthara", Class::Light, 46.0, 0.0, 14.0, 14.0, 2, 1100.0, 1200.0, 500.0, Some(Class::Light), Some(Class::Heavy), Some(Class::Medium), false, false, false),
    ship("Nexus", "Synthara", Class::Light, 54.0, 0.0, 16.0, 16.0, 3, 1300.0, 1450.0, 600.0, Some(Class::Heavy), Some(Class::Medium), Some(Class::Light), false, false, false),
    ship("Monolith", "Synthara", Class::Heavy, 250.0, 0.0, 21.0, 40.0, 8, 7500.0, 8000.0, 3500.0, Some(Class::Heavy), Some(Class::Medium), Some(Class::Light), false, false, false),
    ship("Obelisk", "Synthara", Class::Heavy, 330.0, 0.0, 25.0, 50.0, 9, 10500.0, 11000.0, 5500.0, Some(Class::Medium), Some(Class::Heavy), Some(Class::Light), false, false, false),
    ship("Singularity", "Synthara", Class::Heavy, 420.0, 0.0, 29.0, 60.0, 9, 13000.0, 14000.0, 7500.0, Some(Class::Heavy), Some(Class::Medium), Some(Class::Light), false, false, false),
    ship("Oracle", "Synthara", Class::Special, 640.0, 0.0, 60.0, 80.0, 8, 24000.0, 29000.0, 12000.0, Some(Class::Heavy), Some(Class::Medium), Some(Class::Light), true, false, false),
    ship("Picket", "Vanguard", Class::Light, 40.0, 11.0, 0.0, 12.0, 5, 1100.0, 650.0, 450.0, Some(Class::Light), Some(Class::Medium), Some(Class::Heavy), false, false, false),
    ship("Juggernaut", "Ashkari", Class::Heavy, 175.0, 84.0, 0.0, 22.0, 6, 8200.0, 4600.0, 4600.0, Some(Class::Heavy), Some(Class::Medium), Some(Class::Light), false, false, false),
    ship("Lattice", "Synthara", Class::Medium, 70.0, 0.0, 12.0, 30.0, 2, 1750.0, 1900.0, 750.0, Some(Class::Medium), Some(Class::Heavy), Some(Class::Light), false, false, false),
];

const fn ship(
    name: &'static str,
    faction: &'static str,
    class: Class,
    armor: f64,
    damage: f64,
    emp_damage: f64,
    emp_res: f64,
    init: u8,
    cost_m: f64,
    cost_c: f64,
    cost_e: f64,
    t1: Option<Class>,
    t2: Option<Class>,
    t3: Option<Class>,
    cloak: bool,
    is_imperator: bool,
    is_oblivion: bool,
) -> ShipDef {
    ShipDef {
        name,
        faction,
        class,
        armor,
        damage,
        emp_damage,
        emp_res,
        init,
        cost_m,
        cost_c,
        cost_e,
        t1,
        t2,
        t3,
        cloak,
        is_imperator,
        is_oblivion,
    }
}

const ARCH_NAMES: [&str; N_ARCH] = [
    "VG Sentinel",
    "VG Centurion",
    "VG Guardian",
    "VG 4Imp+Sentinel",
    "VG 4Imp+Sent+Cent",
    "VG 4Imp+Sent+Guard",
    "VG all mediums",
    "VG Sovereign",
    "VG combined",
    "Ash Fang swarm",
    "Ash lights mix",
    "Ash Fang+Oblivion",
    "Ash balanced",
    "Ash Marauder",
    "Ash mediums",
    "Syn Pulse swarm",
    "Syn light EMP",
    "Syn Pulse+Oracle",
    "Syn balanced",
    "Syn heavy EMP",
    "Syn Oracle",
    "VG Picket swarm",
    "VG Picket+Sentinel",
    "Ash Juggernaut",
    "Syn Lattice swarm",
];

const ARCH_FAC: [&str; N_ARCH] = [
    "Vanguard", "Vanguard", "Vanguard", "Vanguard", "Vanguard", "Vanguard", "Vanguard", "Vanguard", "Vanguard",
    "Ashkari", "Ashkari", "Ashkari", "Ashkari", "Ashkari", "Ashkari",
    "Synthara", "Synthara", "Synthara", "Synthara", "Synthara", "Synthara",
    "Vanguard", "Vanguard", "Ashkari", "Synthara",
];

fn buy(counts: &mut [u32; N], idx: usize, spend: f64) {
    let n = (spend / DEFS[idx].cost()).max(0.0) as u32;
    counts[idx] = n;
}

fn fleet_total(arch: usize, budget: f64) -> [u32; N] {
    let mut c = [0u32; N];
    let imp4 = 4.0 * DEFS[VG_IMP].cost();
    match arch {
        0 => buy(&mut c, VG_SENT, budget),
        1 => buy(&mut c, VG_CENT, budget),
        2 => buy(&mut c, VG_GUARD, budget),
        3 => {
            c[VG_IMP] = 4;
            buy(&mut c, VG_SENT, budget - imp4);
        }
        4 => {
            c[VG_IMP] = 4;
            let rem = budget - imp4;
            buy(&mut c, VG_SENT, rem * 0.5);
            buy(&mut c, VG_CENT, rem * 0.5);
        }
        5 => {
            c[VG_IMP] = 4;
            let rem = budget - imp4;
            buy(&mut c, VG_SENT, rem * 0.5);
            buy(&mut c, VG_GUARD, rem * 0.5);
        }
        6 => {
            buy(&mut c, VG_CENT, budget / 3.0);
            buy(&mut c, VG_GUARD, budget / 3.0);
            buy(&mut c, VG_SENT, budget / 3.0);
        }
        7 => buy(&mut c, VG_SOV, budget),
        8 => {
            c[VG_IMP] = 4;
            let rem = budget - imp4;
            buy(&mut c, VG_SENT, rem * 0.40);
            buy(&mut c, VG_CENT, rem * 0.30);
            buy(&mut c, VG_SOV, rem * 0.30);
        }
        9 => buy(&mut c, ASH_FANG, budget),
        10 => {
            buy(&mut c, ASH_FANG, budget * 0.50);
            buy(&mut c, ASH_TALON, budget * 0.25);
            buy(&mut c, ASH_VIPER, budget * 0.25);
        }
        11 => {
            buy(&mut c, ASH_FANG, budget * 2.0 / 3.0);
            buy(&mut c, ASH_OBL, budget / 3.0);
        }
        12 => {
            buy(&mut c, ASH_FANG, budget * 0.30);
            buy(&mut c, ASH_TALON, budget * 0.10);
            buy(&mut c, ASH_VIPER, budget * 0.10);
            buy(&mut c, ASH_MAR, budget * 0.20);
            buy(&mut c, ASH_REAP, budget * 0.20);
            buy(&mut c, ASH_OBL, budget * 0.10);
        }
        13 => buy(&mut c, ASH_MAR, budget),
        14 => {
            buy(&mut c, ASH_RAV, budget / 3.0);
            buy(&mut c, ASH_MAR, budget / 3.0);
            buy(&mut c, ASH_REAP, budget / 3.0);
        }
        15 => buy(&mut c, SYN_PULSE, budget),
        16 => {
            buy(&mut c, SYN_PULSE, budget * 0.50);
            buy(&mut c, SYN_ARC, budget * 0.25);
            buy(&mut c, SYN_NEX, budget * 0.25);
        }
        17 => {
            buy(&mut c, SYN_PULSE, budget * 2.0 / 3.0);
            buy(&mut c, SYN_ORA, budget / 3.0);
        }
        18 => {
            buy(&mut c, SYN_PULSE, budget * 0.30);
            buy(&mut c, SYN_ARC, budget * 0.10);
            buy(&mut c, SYN_NEX, budget * 0.10);
            buy(&mut c, SYN_MONO, budget * 0.15);
            buy(&mut c, SYN_OBEL, budget * 0.15);
            buy(&mut c, SYN_SING, budget * 0.10);
            buy(&mut c, SYN_ORA, budget * 0.10);
        }
        19 => {
            buy(&mut c, SYN_MONO, budget / 3.0);
            buy(&mut c, SYN_OBEL, budget / 3.0);
            buy(&mut c, SYN_SING, budget / 3.0);
        }
        20 => buy(&mut c, SYN_ORA, budget),
        21 => buy(&mut c, VG_PICKET, budget),
        22 => {
            buy(&mut c, VG_PICKET, budget * 0.5);
            buy(&mut c, VG_SENT, budget * 0.5);
        }
        23 => buy(&mut c, ASH_JUG, budget),
        _ => buy(&mut c, SYN_LAT, budget),
    }
    c
}

fn fleet_income(arch: usize) -> [u32; N] {
    // 10M of 47/31/22 income, spent in the same shares as total-mineral fleets.
    let wallet_m = BUDGET * 0.47;
    let wallet_c = BUDGET * 0.31;
    let wallet_e = BUDGET * 0.22;
    let shares = fleet_total(arch, BUDGET);
    let mut out = [0u32; N];
    let mut spent_frac = [0.0f64; N];
    let mut tot_cost = 0.0;
    for i in 0..N {
        let v = shares[i] as f64 * DEFS[i].cost();
        spent_frac[i] = v;
        tot_cost += v;
    }
    if tot_cost <= 0.0 {
        return out;
    }
    for i in 0..N {
        if shares[i] == 0 {
            continue;
        }
        let f = spent_frac[i] / tot_cost;
        let d = &DEFS[i];
        let n_m = if d.cost_m > 0.0 { (wallet_m * f) / d.cost_m } else { f64::MAX };
        let n_c = if d.cost_c > 0.0 { (wallet_c * f) / d.cost_c } else { f64::MAX };
        let n_e = if d.cost_e > 0.0 { (wallet_e * f) / d.cost_e } else { f64::MAX };
        out[i] = n_m.min(n_c).min(n_e).max(0.0) as u32;
    }
    out
}

fn value(counts: &[u32; N]) -> f64 {
    let mut v = 0.0;
    for i in 0..N {
        v += counts[i] as f64 * DEFS[i].cost();
    }
    v
}

/// Python 3 bankers round (ties to even).
fn py_round(x: f64) -> i64 {
    if !x.is_finite() {
        return 0;
    }
    let sign = if x < 0.0 { -1.0 } else { 1.0 };
    let ax = x.abs();
    let n = ax.floor();
    let frac = ax - n;
    let r = if frac > 0.5 {
        n + 1.0
    } else if frac < 0.5 {
        n
    } else if (n as i64) % 2 == 0 {
        n
    } else {
        n + 1.0
    };
    (r * sign) as i64
}

fn aura(counts: &[u32; N]) -> f64 {
    (counts[VG_IMP] as f64 * 0.08).min(0.25)
}

fn collect_targets(
    enemy: &[u32; N],
    t1: Option<Class>,
    t2: Option<Class>,
    t3: Option<Class>,
    round: u32,
) -> (Vec<usize>, f64) {
    let cloak_ok = |i: usize| !(round == 1 && DEFS[i].cloak);
    let uncloaked_exist = (0..N).any(|i| enemy[i] > 0 && cloak_ok(i));
    let visible = |i: usize| enemy[i] > 0 && (!uncloaked_exist || cloak_ok(i));

    let matching = |cls: Class| -> Vec<usize> {
        let mut v = Vec::new();
        for i in 0..N {
            if visible(i) && DEFS[i].class == cls {
                v.push(i);
            }
        }
        if cls == Class::Heavy {
            // SPECIAL is screened until HEAVY is gone.
            if v.is_empty() {
                for i in 0..N {
                    if visible(i) && DEFS[i].class == Class::Special {
                        v.push(i);
                    }
                }
            }
        }
        v
    };

    for (p, cls) in [(0, t1), (1, t2), (2, t3)] {
        if let Some(cls) = cls {
            let m = matching(cls);
            if !m.is_empty() {
                let eff = if p == 0 { 1.0 } else if p == 1 { 0.80 } else { 0.70 };
                return (m, eff);
            }
        }
    }
    let mut fallback: Vec<usize> = (0..N).filter(|&i| visible(i)).collect();
    fallback.sort_by_key(|&i| if DEFS[i].class == Class::Special { 1 } else { 0 });
    (fallback, 1.0)
}

fn fire(
    shooter: usize,
    atk: bool,
    round: u32,
    atk_c: &mut [u32; N],
    def_c: &mut [u32; N],
    atk_emp: &mut [bool; N],
    def_emp: &mut [bool; N],
    atk_aura_abs: &mut f64,
    def_aura_abs: &mut f64,
) {
    let (own, enemy, own_emp, enemy_emp) = if atk {
        (&*atk_c, &*def_c, &*atk_emp, &mut *def_emp)
    } else {
        (&*def_c, &*atk_c, &*def_emp, &mut *atk_emp)
    };
    if own[shooter] == 0 || own_emp[shooter] {
        return;
    }
    let s = &DEFS[shooter];
    let n = own[shooter] as f64;
    let (targets, eff) = collect_targets(enemy, s.t1, s.t2, s.t3, round);
    if targets.is_empty() {
        return;
    }

    let enemy_aura = if atk { aura(def_c) } else { aura(atk_c) };

    if s.damage > 0.0 {
        let mut remaining = n * s.damage * eff;
        let absorbed = remaining * enemy_aura;
        remaining -= absorbed;
        if atk {
            *def_aura_abs += absorbed;
        } else {
            *atk_aura_abs += absorbed;
        }
        for &t in &targets {
            if remaining <= 0.0 {
                break;
            }
            let live = if atk { def_c[t] } else { atk_c[t] };
            if live == 0 {
                continue;
            }
            let armor = DEFS[t].armor;
            let mut killed = ((remaining / armor).floor() as u32).min(live);
            if killed == 0 && remaining > armor * 0.75 {
                killed = 1;
            }
            if killed == 0 {
                break;
            }
            let used = killed as f64 * armor;
            if atk {
                def_c[t] -= killed;
            } else {
                atk_c[t] -= killed;
            }
            remaining -= used;
            if DEFS[t].is_oblivion {
                let reflected = used * 0.15;
                let mut sk = ((reflected / s.armor).floor() as u32).min(if atk { atk_c[shooter] } else { def_c[shooter] });
                if sk == 0 && reflected > s.armor * 0.75 {
                    sk = 1;
                }
                if atk {
                    atk_c[shooter] = atk_c[shooter].saturating_sub(sk);
                } else {
                    def_c[shooter] = def_c[shooter].saturating_sub(sk);
                }
            }
        }
    }

    if s.emp_damage > 0.0 {
        for &t in &targets {
            let live = if atk { def_c[t] } else { atk_c[t] };
            if live == 0 || enemy_emp[t] {
                continue;
            }
            if DEFS[t].emp_res >= 100.0 {
                continue;
            }
            let chance = (0.5 - DEFS[t].emp_res / 100.0).clamp(0.0, 1.0);
            let expected = py_round(live as f64 * chance);
            if expected > 0 {
                enemy_emp[t] = true;
            }
            break;
        }
    }
}

fn simulate(mut atk: [u32; N], mut def: [u32; N], rounds: u32) -> (f64, f64) {
    let atk0 = value(&atk);
    let def0 = value(&def);
    for round in 1..=rounds {
        if value(&atk) <= 0.0 || value(&def) <= 0.0 {
            break;
        }
        let mut atk_emp = [false; N];
        let mut def_emp = [false; N];
        let mut atk_abs = 0.0;
        let mut def_abs = 0.0;
        for init in 1u8..=12 {
            for i in 0..N {
                if DEFS[i].init == init {
                    fire(i, true, round, &mut atk, &mut def, &mut atk_emp, &mut def_emp, &mut atk_abs, &mut def_abs);
                }
            }
            for i in 0..N {
                if DEFS[i].init == init {
                    fire(i, false, round, &mut atk, &mut def, &mut atk_emp, &mut def_emp, &mut atk_abs, &mut def_abs);
                }
            }
        }
        if atk_abs > 0.0 && atk[VG_IMP] > 0 {
            let lost = py_round(atk_abs / DEFS[VG_IMP].armor).max(0) as u32;
            atk[VG_IMP] = atk[VG_IMP].saturating_sub(lost.min(atk[VG_IMP]));
        }
        if def_abs > 0.0 && def[VG_IMP] > 0 {
            let lost = py_round(def_abs / DEFS[VG_IMP].armor).max(0) as u32;
            def[VG_IMP] = def[VG_IMP].saturating_sub(lost.min(def[VG_IMP]));
        }
    }
    (atk0 - value(&atk), def0 - value(&def))
}

fn print_matrix(title: &str, fleets: &[[u32; N]; N_ARCH], rounds: u32) {
    println!("\n=== {title}  rounds={rounds}  budget≈{BUDGET:.0} ===");
    println!(
        "{:<22} {:>10} {:>10} {:>10} {:>10}",
        "archetype", "win%", "loss%", "draw%", "avg net M"
    );
    let mut fac_w = [0u64; 3];
    let mut fac_n = [0u64; 3];
    let fac_i = |f: &str| match f {
        "Vanguard" => 0,
        "Ashkari" => 1,
        _ => 2,
    };
    let mut rows: Vec<(usize, f64, f64, f64, f64)> = Vec::new();
    for i in 0..N_ARCH {
        let mut w = 0u64;
        let mut l = 0u64;
        let mut d = 0u64;
        let mut net = 0.0;
        let mut n = 0u64;
        for j in 0..N_ARCH {
            if i == j {
                continue;
            }
            let (atk_lost, def_lost) = simulate(fleets[i], fleets[j], rounds);
            let nv = def_lost - atk_lost;
            net += nv;
            n += 1;
            if nv > BUDGET * 0.05 {
                w += 1;
            } else if nv < -BUDGET * 0.05 {
                l += 1;
            } else {
                d += 1;
            }
            let fi = fac_i(ARCH_FAC[i]);
            fac_n[fi] += 1;
            if nv > BUDGET * 0.05 {
                fac_w[fi] += 1;
            }
        }
        let tot = n as f64;
        rows.push((i, w as f64 / tot * 100.0, l as f64 / tot * 100.0, d as f64 / tot * 100.0, net / tot / 1e6));
    }
    rows.sort_by(|a, b| b.1.partial_cmp(&a.1).unwrap());
    for (i, wr, lr, dr, nv) in &rows {
        println!(
            "{:<22} {:>9.1}% {:>9.1}% {:>9.1}% {:>+10.2}  {}",
            ARCH_NAMES[*i], wr, lr, dr, nv, ARCH_FAC[*i]
        );
    }
    println!("\nFaction attacker win rate (excluding mirrors, ±5% of budget = draw):");
    for (name, i) in [("Vanguard", 0), ("Ashkari", 1), ("Synthara", 2)] {
        let wr = fac_w[i] as f64 / fac_n[i].max(1) as f64 * 100.0;
        println!("  {name:<10} {wr:>5.1}%");
    }
}

fn print_head_to_head(fleets: &[[u32; N]; N_ARCH], rounds: u32) {
    println!("\nSelected 1v1 nets (attacker, millions), rounds={rounds}:");
    let picks = [3usize, 9, 21, 22, 23, 15, 24];
    print!("{:<22}", "");
    for &j in &picks {
        print!(" {:>14}", ARCH_NAMES[j]);
    }
    println!();
    for &i in &picks {
        print!("{:<22}", ARCH_NAMES[i]);
        for &j in &picks {
            if i == j {
                print!(" {:>14}", "—");
                continue;
            }
            let (al, dl) = simulate(fleets[i], fleets[j], rounds);
            print!(" {:>+13.2}m", (dl - al) / 1e6);
        }
        println!();
    }
}

fn check_vs_fixtures() {
    println!("check_id\trust_net\tatk_lost\tdef_lost");
    let cases: [(&str, usize, usize); 8] = [
        ("VG_SENT vs ASH_FANG", 0, 9),
        ("VG_4IMP_SENT vs ASH_FANG", 3, 9),
        ("VG_4IMP_SENT vs SYN_PULSE", 3, 15),
        ("VG_SENT vs SYN_PULSE", 0, 15),
        ("ASH_FANG vs VG_SENT", 9, 0),
        ("ASH_BAL vs VG_4IMP_SC", 12, 4),
        ("SYN_PULSE vs ASH_FANG", 15, 9),
        ("VG_GUARD vs SYN_HEAVY", 2, 19),
    ];
    let fleets: [[u32; N]; N_ARCH] = core::array::from_fn(|i| fleet_total(i, BUDGET));
    for (name, a, b) in cases {
        let (al, dl) = simulate(fleets[a], fleets[b], 1);
        println!("{name}\t{:.0}\t{:.0}\t{:.0}", dl - al, al, dl);
    }
}

fn print_cost_mix() {
    println!("Live combat hull mineral mix (vs claimed planetary 47/31/22):");
    for fac in ["Vanguard", "Ashkari", "Synthara"] {
        let mut m = 0.0;
        let mut c = 0.0;
        let mut e = 0.0;
        for d in &DEFS {
            if d.faction == fac {
                m += d.cost_m;
                c += d.cost_c;
                e += d.cost_e;
            }
        }
        let t = m + c + e;
        println!(
            "  {fac:<10} M {:4.1}%  C {:4.1}%  E {:4.1}%   metal-vs-47 {:+.1} pp",
            m / t * 100.0,
            c / t * 100.0,
            e / t * 100.0,
            m / t * 100.0 - 47.0
        );
    }
}

fn main() {
    let args: Vec<String> = env::args().collect();
    if args.iter().any(|a| a == "check") {
        check_vs_fixtures();
        return;
    }

    println!("Pegasus live-catalog matchup engine");
    println!("Source: peg_combat.SHIP_DEFINITIONS  |  kinetic=count*damage*eff  |  EMP=0.5-res/100");
    println!("Replaced stale Aetheris/gun-scaled EMP engine.");
    print_cost_mix();

    let total: [[u32; N]; N_ARCH] = core::array::from_fn(|i| fleet_total(i, BUDGET));
    let income: [[u32; N]; N_ARCH] = core::array::from_fn(fleet_income);

    let t0 = Instant::now();
    print_matrix("EQUAL TOTAL MINERALS 10M  (1 round / 1 tick)", &total, 1);
    print_head_to_head(&total, 1);
    print_matrix("EQUAL TOTAL MINERALS 10M  (5 rounds)", &total, 5);
    print_head_to_head(&total, 5);
    print_matrix("INCOME-LIMITED 47/31/22 wallet of 10M  (1 round)", &income, 1);
    print_head_to_head(&income, 1);
    println!("\nElapsed {:?}", t0.elapsed());
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn fang_vs_sentinel_fang_ahead() {
        let fleets: [[u32; N]; N_ARCH] = core::array::from_fn(|i| fleet_total(i, BUDGET));
        let (al, dl) = simulate(fleets[0], fleets[9], 1); // Sent attacks Fang
        let net = dl - al;
        assert!(net < 0.0, "Sentinel should lose mineral trade into Fang, net={net}");
    }

    #[test]
    fn four_imp_sent_beats_fang() {
        let fleets: [[u32; N]; N_ARCH] = core::array::from_fn(|i| fleet_total(i, BUDGET));
        let (al, dl) = simulate(fleets[3], fleets[9], 1);
        assert!(dl - al > 0.0);
    }

    #[test]
    fn mono_sentinel_stalemates_pulse() {
        let fleets: [[u32; N]; N_ARCH] = core::array::from_fn(|i| fleet_total(i, BUDGET));
        let (al, dl) = simulate(fleets[0], fleets[15], 1);
        assert_eq!(al, 0.0);
        assert_eq!(dl, 0.0);
    }

    #[test]
    fn vanguard_picket_is_light() {
        assert_eq!(DEFS[VG_PICKET].name, "Picket");
        assert_eq!(DEFS[VG_PICKET].faction, "Vanguard");
        assert!(matches!(DEFS[VG_PICKET].class, Class::Light));
        assert!(DEFS[VG_PICKET].damage > 0.0);
    }
}
