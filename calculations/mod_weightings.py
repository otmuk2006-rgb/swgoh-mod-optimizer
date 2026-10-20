import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
from collections import defaultdict

MODS_PATH = 'data/processed/top250_mods.json'
BASE_SPEED_PATH = 'data/processed/base_speed.json'
SAVE_PATH = 'data/processed/mod_weightings.json'
MAX_OBSERVED_SAVE_PATH = 'data/processed/max_observed_stats.json'

# set bonus values in percentage-point form (matches decode_stat's units)
SET_BONUS_FULL = {
    'critical_chance': 8.0, 'critical_damage': 30.0, 'defense': 25.0,
    'health': 10.0, 'offense': 15.0, 'potency': 15.0, 'tenacity': 20.0,
}
SET_BONUS_MIN = {
    'critical_chance': 4.0, 'critical_damage': 15.0, 'defense': 12.5,
    'health': 5.0, 'offense': 7.5, 'potency': 7.5, 'tenacity': 10.0,
}
# speed handled separately, as a fraction multiplied by base speed
SPEED_SET_BONUS_FULL_FRACTION = 0.10
SPEED_SET_BONUS_MIN_FRACTION = 0.05

SET_REQUIREMENT = {
    'critical_chance': 2, 'critical_damage': 4, 'defense': 2,
    'health': 2, 'offense': 4, 'potency': 2, 'speed': 4, 'tenacity': 2,
}

SET_STAT_KEY = {
    'critical_chance': 'critical_chance', 'critical_damage': 'critical_damage',
    'defense': 'defense_pct', 'health': 'health_pct', 'offense': 'offense_pct',
    'potency': 'potency', 'speed': 'speed', 'tenacity': 'tenacity',
}


def sum_account_character_mods(mods, base_speed):
    """Given a list of mods for one account+character, sum all stats
    and add every completed set bonus. Set bonus strength depends on mod
    LEVEL (15 = max bonus, anything less = min bonus), not dots/rarity.
    base_speed is needed to convert the speed set bonus from a
    percentage into a flat number.

    Two-mod sets stack (6 health mods = 3 health bonuses), same rule as
    the game: n mods of a set complete n // required bonuses, of which
    (number at level 15) // required are full and the rest are min."""
    totals = defaultdict(float)

    for mod in mods:
        p = mod['primary']
        totals[p['stat']] += p['value']
        for sec in mod['secondaries']:
            totals[sec['stat']] += sec['value']

    set_counts = defaultdict(list)
    for mod in mods:
        set_counts[mod['set']].append(mod['level'] == 15)

    for set_name, level_15_list in set_counts.items():
        required = SET_REQUIREMENT.get(set_name)
        if required is None:
            continue

        completed = len(level_15_list) // required
        full_count = sum(level_15_list) // required
        min_count = completed - full_count
        if completed == 0:
            continue

        stat_key = SET_STAT_KEY[set_name]

        if set_name == 'speed':
            # speed set bonus is a % of base speed, converted to flat
            if base_speed is None:
                continue  # can't convert without base speed, skip
            totals[stat_key] += (full_count * SPEED_SET_BONUS_FULL_FRACTION
                                 + min_count * SPEED_SET_BONUS_MIN_FRACTION) * base_speed
        else:
            totals[stat_key] += (full_count * SET_BONUS_FULL[set_name]
                                 + min_count * SET_BONUS_MIN[set_name])

    return dict(totals)


def build_mod_weightings():
    """Character stat weightings W_j, normalised against the highest
    average actually observed across all characters in the top-250 sample
    for that stat — not a theoretical per-mod ceiling. This means the
    character with the single highest average for a given stat always
    weights exactly 1.0 on it, and every other character's weight for that
    stat is relative to that real, achieved benchmark rather than an
    abstract "if every mod rolled max" number that's rarely representative
    of what a real loadout looks like. Also saves that per-stat max as
    max_observed_stats.json, since anything comparing a mod set's own
    stats against W_j (e.g. the before/after fit report) needs to
    normalise onto this same basis to stay in the same units."""
    with open(MODS_PATH) as f:
        all_mods = json.load(f)

    with open(BASE_SPEED_PATH) as f:
        base_speeds = json.load(f)

    grouped = defaultdict(list)
    for mod in all_mods:
        key = (mod['player_id'], mod['character'])
        grouped[key].append(mod)

    account_totals = {}
    for (player_id, character), mods in grouped.items():
        base_speed = base_speeds.get(character)
        account_totals[(player_id, character)] = sum_account_character_mods(mods, base_speed)

    char_accumulator = defaultdict(list)
    for (player_id, character), totals in account_totals.items():
        char_accumulator[character].append(totals)

    avg_totals_by_char = {}
    for character, totals_list in char_accumulator.items():
        n = len(totals_list)
        avg_totals = defaultdict(float)
        for totals in totals_list:
            for stat, val in totals.items():
                avg_totals[stat] += val / n
        avg_totals_by_char[character] = (dict(avg_totals), n)

    max_observed = defaultdict(float)
    for character, (avg_totals, _n) in avg_totals_by_char.items():
        for stat, val in avg_totals.items():
            if val > max_observed[stat]:
                max_observed[stat] = val

    W = {}
    for character, (avg_totals, n) in avg_totals_by_char.items():
        weights = {}
        for stat, avg_val in avg_totals.items():
            denom = max_observed.get(stat)
            if denom:
                weights[stat] = avg_val / denom

        W[character] = {
            'raw_weights': weights,
            'sample_size': n,
        }

    with open(SAVE_PATH, 'w') as f:
        json.dump(W, f, indent=2)
    print(f"Built weightings for {len(W)} characters")

    with open(MAX_OBSERVED_SAVE_PATH, 'w') as f:
        json.dump(dict(max_observed), f, indent=2)
    print(f"Saved max observed stats to {MAX_OBSERVED_SAVE_PATH}")

    return W


if __name__ == "__main__":
    build_mod_weightings()