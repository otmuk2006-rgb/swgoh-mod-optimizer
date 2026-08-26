# Character stats before/after re-modding, and which mods moved where.

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
import copy
import math
from swgoh_comlink import StatCalc
from utils import session_paths, GLOBAL_DATA_DIR
from calculations.mod_weightings import sum_account_character_mods

# global/community reference data — same for every visitor
WEIGHTINGS_PATH = os.path.join(GLOBAL_DATA_DIR, 'mod_weightings.json')
MAX_OBSERVED_PATH = os.path.join(GLOBAL_DATA_DIR, 'max_observed_stats.json')
BASE_SPEED_PATH = os.path.join(GLOBAL_DATA_DIR, 'base_speed.json')


# ---------- roster / mod lookups ----------

def load_raw_roster(session_dir=None):
    raw_dir, _ = session_paths(session_dir)
    with open(os.path.join(raw_dir, 'my_roster.json')) as f:
        data = json.load(f)
    return data['rosterUnit'] if 'rosterUnit' in data else data


def build_unit_lookup(roster):
    """character_id -> raw roster unit (Comlink format)."""
    return {unit['definitionId'].split(':')[0]: unit for unit in roster}


def build_raw_mod_lookup(roster):
    """mod_id -> raw mod dict (Comlink format), scanned off every unit's equippedStatMod."""
    lookup = {}
    for unit in roster:
        for mod in unit.get('equippedStatMod', []):
            lookup[mod['id']] = mod
    return lookup


# ---------- mod transfer report ----------

def load_assignment(session_dir=None):
    """Returns (assignments {char_id: [mod_id,...]}, selected_characters set())."""
    _, processed_dir = session_paths(session_dir)
    with open(os.path.join(processed_dir, 'final_assignment.json')) as f:
        data = json.load(f)
    return data['assignments'], set(data['selected_characters'])


def build_mod_transfer_report(session_dir=None):
    """Which mods moved characters, including the mod's own stats,
    keyed by the character on the 'gained'/'lost' end of the move.

    A mod that simply doesn't appear in the new assignment is only a real
    loss if its original owner was actually part of this optimisation run —
    otherwise nothing was ever decided about it, so it's left out."""
    _, processed_dir = session_paths(session_dir)
    with open(os.path.join(processed_dir, 'my_mods.json')) as f:
        old_mods = json.load(f)
    mods_by_id = {m['mod_id']: m for m in old_mods}

    new_assignment, selected_characters = load_assignment(session_dir)

    old_owner = {mod_id: m['character'] for mod_id, m in mods_by_id.items()}
    new_owner = {}
    for char_id, mod_ids in new_assignment.items():
        for mod_id in mod_ids:
            new_owner[mod_id] = char_id

    transfers = {}
    all_mod_ids = set(old_owner) | set(new_owner)

    for mod_id in all_mod_ids:
        old_char = old_owner.get(mod_id)
        new_char = new_owner.get(mod_id)
        if old_char == new_char:
            continue
        if new_char is None and old_char not in selected_characters:
            continue  # old_char wasn't part of this run — mod is untouched, not lost

        mod = mods_by_id.get(mod_id, {})
        mod_summary = {
            'mod_id': mod_id,
            'set': mod.get('set'),
            'slot': mod.get('slot'),
            'tier_colour': mod.get('tier_colour'),
            'level': mod.get('level'),
            'dots': mod.get('dots'),
            'primary': mod.get('primary'),
            'secondaries': mod.get('secondaries'),
        }

        if old_char:
            transfers.setdefault(old_char, {'gained': [], 'lost': []})
            transfers[old_char]['lost'].append({**mod_summary, 'to': new_char})

        if new_char:
            transfers.setdefault(new_char, {'gained': [], 'lost': []})
            transfers[new_char]['gained'].append({**mod_summary, 'from': old_char})

    return transfers


# ---------- mod fit (cosine similarity) ----------
#
# How well a character's mod set (their own summed stats, including any
# completed set bonus) fits that character's weightings W_j — a measure of
# "right shape", independent of magnitude. Not used to drive the ILP (see
# optimiser/solver.py's own docs for why a whole-set cosine objective isn't
# linear), only to evaluate an already-decided assignment before vs after.

def cosine_similarity(vec_a, vec_b):
    keys = set(vec_a) | set(vec_b)
    dot = sum(vec_a.get(k, 0) * vec_b.get(k, 0) for k in keys)
    norm_a = math.sqrt(sum(v * v for v in vec_a.values()))
    norm_b = math.sqrt(sum(v * v for v in vec_b.values()))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def compute_character_fit(mod_ids, mods_by_id, base_speed, W_j, max_observed):
    """Cosine similarity between one character's total mod-contributed
    stat vector (their given mod_ids, summed, plus any completed set
    bonus — same mechanic as mod_weightings.sum_account_character_mods)
    and their own weight vector W_j. Both must be normalised onto the
    same basis for the comparison to mean anything — max_observed is the
    exact same per-stat denominator mod_weightings.py used to build W_j
    in the first place, so this stays consistent with however W_j was
    last built."""
    mods = [mods_by_id[mid] for mid in mod_ids if mid in mods_by_id]
    totals = sum_account_character_mods(mods, base_speed)

    stat_vector = {}
    for stat, val in totals.items():
        denom = max_observed.get(stat)
        if denom:
            stat_vector[stat] = val / denom

    return cosine_similarity(stat_vector, W_j)


def compute_average_mod_fit(session_dir=None):
    """{'per_character': {char_id: {'before': x, 'after': y}, ...},
    'average_before': x, 'average_after': y} across every character in
    the run — characters with no weightings entry (unmodded/unranked
    characters) are skipped entirely rather than counted as a 0."""
    _, processed_dir = session_paths(session_dir)

    with open(os.path.join(processed_dir, 'my_mods.json')) as f:
        old_mods = json.load(f)
    mods_by_id = {m['mod_id']: m for m in old_mods}

    old_mod_ids_by_char = {}
    for m in old_mods:
        old_mod_ids_by_char.setdefault(m['character'], []).append(m['mod_id'])

    new_assignment, selected_characters = load_assignment(session_dir)

    with open(WEIGHTINGS_PATH) as f:
        weightings = json.load(f)
    with open(MAX_OBSERVED_PATH) as f:
        max_observed = json.load(f)
    with open(BASE_SPEED_PATH) as f:
        base_speeds = json.load(f)

    # Whole roster, not just this run's selection: every character with
    # mods currently equipped, plus anyone selected this run (covers a
    # freshly-selected character that started with zero mods). Characters
    # this run never touched get after == before — nothing happened to
    # them, so the average shouldn't pretend otherwise. Deliberately keyed
    # off selected_characters (not new_assignment's keys) to decide who
    # was "part of this run" — a free (non-locked) character the solver
    # left with zero mods is still a real, intentional outcome of the
    # run, not the same as never having been selected at all.
    all_characters = set(old_mod_ids_by_char) | selected_characters

    per_character = {}
    for char_id in all_characters:
        char_weights_entry = weightings.get(char_id)
        if not char_weights_entry:
            continue
        W_j = char_weights_entry.get('raw_weights', {})
        if not W_j:
            continue

        base_speed = base_speeds.get(char_id)
        before_ids = old_mod_ids_by_char.get(char_id, [])
        after_ids = new_assignment.get(char_id, []) if char_id in selected_characters else before_ids

        before = compute_character_fit(before_ids, mods_by_id, base_speed, W_j, max_observed)
        after = compute_character_fit(after_ids, mods_by_id, base_speed, W_j, max_observed)
        per_character[char_id] = {'before': before, 'after': after}

    if not per_character:
        return {'per_character': {}, 'average_before': None, 'average_after': None}

    average_before = sum(v['before'] for v in per_character.values()) / len(per_character)
    average_after = sum(v['after'] for v in per_character.values()) / len(per_character)

    return {
        'per_character': per_character,
        'average_before': average_before,
        'average_after': average_after,
    }


# ---------- stat calculation ----------

def compute_stats(calc, unit, mod_ids, raw_mod_lookup):
    """Run StatCalc on a copy of unit equipped with exactly the given mod IDs.
    Returns (mod_contribution, overall) — both renamed-stat-name -> value dicts."""
    unit_copy = copy.deepcopy(unit)
    unit_copy['equippedStatMod'] = [raw_mod_lookup[mid] for mid in mod_ids if mid in raw_mod_lookup]
    calc.calc_char_stats(unit_copy)
    stats = unit_copy['stats']
    return stats.get('mods', {}), stats['final']


def build_character_stat_report(calc, unit, new_mod_ids, raw_mod_lookup):
    """base_stats = base + gear only (no mods, unaffected by re-modding).
    modded_stats = the isolated mod contribution, before/after re-modding.
    overall_stats = base + gear + mods combined, before/after re-modding."""
    old_mod_ids = [m['id'] for m in unit.get('equippedStatMod', [])]

    _, base_stats = compute_stats(calc, unit, [], raw_mod_lookup)
    before_mods, before_overall = compute_stats(calc, unit, old_mod_ids, raw_mod_lookup)
    after_mods, after_overall = compute_stats(calc, unit, new_mod_ids, raw_mod_lookup)

    return {
        'base_stats': base_stats,
        'modded_stats': {'before': before_mods, 'after': after_mods},
        'overall_stats': {'before': before_overall, 'after': after_overall},
    }


# ---------- full report ----------

def build_report(session_dir=None):
    roster = load_raw_roster(session_dir)
    unit_lookup = build_unit_lookup(roster)
    raw_mod_lookup = build_raw_mod_lookup(roster)

    new_assignment, _ = load_assignment(session_dir)

    transfers = build_mod_transfer_report(session_dir)
    calc = StatCalc()

    report = {}
    for char_id, changes in transfers.items():
        unit = unit_lookup.get(char_id)
        if unit is None:
            print(f"Warning: no roster data for {char_id}, skipping stat calc")
            report[char_id] = {'mods_gained': changes['gained'], 'mods_lost': changes['lost']}
            continue

        stats = build_character_stat_report(
            calc, unit, new_assignment.get(char_id, []), raw_mod_lookup
        )

        report[char_id] = {
            'mods_gained': changes['gained'],
            'mods_lost': changes['lost'],
            **stats,
        }

    _, processed_dir = session_paths(session_dir)
    save_path = os.path.join(processed_dir, 'mod_change_report.json')
    with open(save_path, 'w') as f:
        json.dump(report, f, indent=2)
    print(f"Saved mod change report to {save_path}")

    return report


# ---------- printing ----------

def format_mod(mod):
    parts = [f"{mod['tier_colour']} {mod['set']} {mod['slot']} (lvl {mod['level']}, {mod['dots']}-dot)"]
    primary = mod.get('primary') or {}
    parts.append(f"primary: {primary.get('stat')} {primary.get('value')}")
    secondaries = mod.get('secondaries') or []
    if secondaries:
        parts.append("secondaries: " + ", ".join(f"{s['stat']} {s['value']}" for s in secondaries))
    return " | ".join(parts)


def print_stat_block(label, before, after):
    print(f"  {label}:")
    for stat in sorted(set(before) | set(after)):
        b = before.get(stat, 0)
        a = after.get(stat, 0)
        if round(b, 2) == round(a, 2):
            continue
        print(f"    {stat}: {b:.2f} -> {a:.2f} ({a - b:+.2f})")


def print_report(report):
    for char_id, info in report.items():
        print(f"\n===== {char_id} =====")

        gained = info.get('mods_gained', [])
        lost = info.get('mods_lost', [])

        if gained:
            print(f"  Gained {len(gained)} mod(s):")
            for mod in gained:
                origin = mod.get('from') or 'unassigned'
                print(f"    + [{mod['mod_id']}] from {origin} — {format_mod(mod)}")

        if lost:
            print(f"  Lost {len(lost)} mod(s):")
            for mod in lost:
                dest = mod.get('to') or 'benched'
                print(f"    - [{mod['mod_id']}] to {dest} — {format_mod(mod)}")

        if 'base_stats' not in info:
            continue

        print("  Base stats (base + gear, no mods — unaffected by re-modding):")
        for stat in sorted(info['base_stats']):
            print(f"    {stat}: {info['base_stats'][stat]:.2f}")

        print_stat_block(
            "Modded stats (mod contribution only)",
            info['modded_stats']['before'], info['modded_stats']['after'],
        )
        print_stat_block(
            "Overall stats (base + gear + mods)",
            info['overall_stats']['before'], info['overall_stats']['after'],
        )


if __name__ == "__main__":
    full_report = build_report()
    print_report(full_report)
