# Figure out max possible stats for each stat type

import json

MAX_SECONDARY = {
    'critical_chance':  11.75,
    'defense':          80,
    'defense_pct':      20.0,
    'health':           2700,
    'health_pct':       10.0,
    'offense':          251,
    'offense_pct':      8.5,
    'potency':          15.0,
    'protection':       4600,
    'protection_pct':   15.0,
    'speed':            31,
    'tenacity':         15.0,
}

MAX_PRIMARY = {
    'accuracy':          30.0,
    'critical_avoidance': 35.0,
    'critical_chance':   20.0,
    'critical_damage':   42.0,
    'defense_pct':       20.0,
    'health_pct':        16.0,
    'offense_pct':       8.5,
    'potency':           30.0,
    'protection_pct':    24.0,
    'speed':             32,
    'tenacity':          35.0,
}

# used for non-speed stats — set bonus expressed in percentage points
SET_BONUS_MAX = {
    'critical_chance': 8.0,
    'critical_damage': 30.0,
    'defense_pct':      25.0,
    'health_pct':       10.0,
    'offense_pct':      15.0,
    'potency':          15.0,
    'tenacity':         20.0,
}

# how many times each set bonus fits in 6 mods — two-mod sets stack 3x
SET_BONUS_STACKS = {
    'critical_chance': 3,
    'critical_damage': 1,
    'defense_pct':      3,
    'health_pct':       3,
    'offense_pct':      1,
    'potency':          3,
    'tenacity':         3,
}

# speed's set bonus is a fraction (0.10 = 10%), since it multiplies against
# a flat base speed number rather than joining other percentage-point values
SPEED_SET_BONUS_FRACTION = 0.10

SLOT_PRIMARIES = {
    'square':   ['offense_pct'],
    'diamond':  ['defense_pct'],
    'circle':   ['health_pct', 'protection_pct'],
    'arrow':    ['speed', 'accuracy', 'critical_avoidance', 'health_pct', 'protection_pct', 'offense_pct', 'defense_pct'],
    'triangle': ['critical_chance', 'critical_damage', 'health_pct', 'protection_pct', 'offense_pct', 'defense_pct'],
    'cross':    ['tenacity', 'potency', 'health_pct', 'protection_pct', 'offense_pct', 'defense_pct'],
}

NON_SPEED_STATS = ['health', 'health_pct', 'protection', 'protection_pct',
                    'offense', 'offense_pct', 'defense', 'defense_pct',
                    'critical_chance', 'critical_damage', 'potency', 'tenacity']


def calc_max_non_speed_stat(stat):
    """Max achievable for any stat except speed, across a full 6-mod loadout."""
    slots_with_primary = [slot for slot, opts in SLOT_PRIMARIES.items() if stat in opts]
    num_primary_slots = len(slots_with_primary)
    num_secondary_slots = 6 - num_primary_slots

    primary_value = MAX_PRIMARY.get(stat, 0) * num_primary_slots
    secondary_value = MAX_SECONDARY.get(stat, 0) * num_secondary_slots
    set_bonus = SET_BONUS_MAX.get(stat, 0) * SET_BONUS_STACKS.get(stat, 1)

    return primary_value + secondary_value + set_bonus


def calc_max_speed(base_speed):
    """Max speed achievable, given a character's base speed (for set bonus conversion)."""
    primary_slots = 1  # only arrow
    secondary_slots = 5

    flat_from_mods = (MAX_PRIMARY['speed'] * primary_slots) + (MAX_SECONDARY['speed'] * secondary_slots)
    flat_from_set = SPEED_SET_BONUS_FRACTION * base_speed

    return flat_from_mods + flat_from_set


def build_max_possible_dict():
    """Builds MAX_POSSIBLE for all non-speed stats (character-independent)."""
    return {stat: calc_max_non_speed_stat(stat) for stat in NON_SPEED_STATS}


def save_max_possible_stats():
    """Builds MAX_POSSIBLE for every stat (speed and non-speed) and saves
    the combined result to data/processed/max_possible_stats.json."""
    max_possible = build_max_possible_dict()
    print("Non-speed max possible (same for all characters):")
    for stat, val in max_possible.items():
        print(f"  {stat}: {val}")

    with open('data/processed/base_speed.json') as f:
        base_speeds = json.load(f)

    max_speed_per_char = {char: calc_max_speed(spd) for char, spd in base_speeds.items() if spd is not None}

    print(f"\nSpeed max computed for {len(max_speed_per_char)} characters")
    print("Example (first 3):")
    for char, val in list(max_speed_per_char.items())[:3]:
        print(f"  {char}: {val}")

    output = {
        'non_speed_max': max_possible,
        'speed_max_per_character': max_speed_per_char,
    }
    with open('data/processed/max_possible_stats.json', 'w') as f:
        json.dump(output, f, indent=2)
    print("\nSaved to data/processed/max_possible_stats.json")

    return output


if __name__ == "__main__":
    save_max_possible_stats()