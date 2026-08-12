import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
from collections import defaultdict

MODS_PATH = 'data/processed/top250_mods.json'
MAX_STATS_PATH = 'data/processed/max_possible_stats.json'
BASE_SPEED_PATH = 'data/processed/base_speed.json'
SAVE_PATH = 'data/processed/mod_weightings.json'

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
    and add any completed set bonus. Set bonus strength depends on mod
    LEVEL (15 = max bonus, anything less = min bonus), not dots/rarity.
    base_speed is needed to convert the speed set bonus from a
    percentage into a flat number."""
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
        if required is None or len(level_15_list) < required:
            continue

        all_level_15 = all(level_15_list[:required])
        stat_key = SET_STAT_KEY[set_name]

        if set_name == 'speed':
            # speed set bonus is a % of base speed, converted to flat
            if base_speed is None:
                continue  # can't convert without base speed, skip
            fraction = SPEED_SET_BONUS_FULL_FRACTION if all_level_15 else SPEED_SET_BONUS_MIN_FRACTION
            totals[stat_key] += fraction * base_speed
        else:
            bonus = SET_BONUS_FULL[set_name] if all_level_15 else SET_BONUS_MIN[set_name]
            totals[stat_key] += bonus

    return dict(totals)


def build_mod_weightings():
    with open(MODS_PATH) as f:
        all_mods = json.load(f)

    with open(MAX_STATS_PATH) as f:
        max_stats = json.load(f)

    with open(BASE_SPEED_PATH) as f:
        base_speeds = json.load(f)

    non_speed_max = max_stats['non_speed_max']
    speed_max_per_char = max_stats['speed_max_per_character']

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

    W = {}
    for character, totals_list in char_accumulator.items():
        n = len(totals_list)
        avg_totals = defaultdict(float)
        for totals in totals_list:
            for stat, val in totals.items():
                avg_totals[stat] += val / n

        weights = {}
        for stat, avg_val in avg_totals.items():
            if stat == 'speed':
                max_val = speed_max_per_char.get(character)
            else:
                max_val = non_speed_max.get(stat)

            if max_val:
                weights[stat] = avg_val / max_val

        W[character] = {
            'raw_weights': weights,
            'sample_size': n,
        }

    with open(SAVE_PATH, 'w') as f:
        json.dump(W, f, indent=2)

    print(f"Built weightings for {len(W)} characters")
    return W


if __name__ == "__main__":
    build_mod_weightings()