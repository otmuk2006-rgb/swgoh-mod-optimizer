# Calculate the score of each individual mod i for character j, based on the mod's stats and the character's weightings for those stats.
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
from utils import GLOBAL_DATA_DIR, session_paths

# global/community reference data — same for every visitor
WEIGHTINGS_PATH = os.path.join(GLOBAL_DATA_DIR, 'mod_weightings.json')
MAX_STATS_PATH = os.path.join(GLOBAL_DATA_DIR, 'max_possible_stats.json')
BASE_SPEED_PATH = os.path.join(GLOBAL_DATA_DIR, 'base_speed.json')

# set bonus values in percentage-point form (matches decode_stat's units)
SET_BONUS_FULL = {
    'critical_chance': 8.0, 'critical_damage': 30.0, 'defense': 25.0,
    'health': 10.0, 'offense': 15.0, 'potency': 15.0, 'tenacity': 20.0,
}
SET_BONUS_MIN = {
    'critical_chance': 4.0, 'critical_damage': 15.0, 'defense': 12.5,
    'health': 5.0, 'offense': 7.5, 'potency': 7.5, 'tenacity': 10.0,
}
SPEED_SET_BONUS_FULL_FRACTION = 0.10
SPEED_SET_BONUS_MIN_FRACTION = 0.05

SET_STAT_KEY = {
    'critical_chance': 'critical_chance', 'critical_damage': 'critical_damage',
    'defense': 'defense_pct', 'health': 'health_pct', 'offense': 'offense_pct',
    'potency': 'potency', 'speed': 'speed', 'tenacity': 'tenacity',
}


def compute_mod_score(mod, W_j, max_stats_non_speed, max_speed_for_char):
    """score(i,j) = sum over stats s of (mod stat / max possible stat) * W_j[stat]"""
    score = 0.0

    stats_to_check = [(mod['primary']['stat'], mod['primary']['value'])]
    for sec in mod['secondaries']:
        stats_to_check.append((sec['stat'], sec['value']))

    for stat, value in stats_to_check:
        weight = W_j.get(stat)
        if weight is None:
            continue

        if stat == 'speed':
            max_val = max_speed_for_char
        else:
            max_val = max_stats_non_speed.get(stat)

        if not max_val:
            continue

        normalised = value / max_val
        score += normalised * weight

    return score


def compute_set_bonus_table(character_id, W_j, base_speed, max_stats_non_speed, max_speed_for_char):
    """B_{k,j} for every set k, both tiers (full/min), for one character.
    Normalised by the same max-possible stat as compute_mod_score — without
    that, a set bonus (raw stat units) and a mod's own stats (fraction of
    max) aren't comparable in the ILP objective, and the solver would
    complete sets even when off-set mods give clearly better stats."""
    bonuses = {}

    for set_name, stat_key in SET_STAT_KEY.items():
        weight = W_j.get(stat_key, 0)

        if set_name == 'speed':
            full_value = SPEED_SET_BONUS_FULL_FRACTION * base_speed if base_speed else 0
            min_value = SPEED_SET_BONUS_MIN_FRACTION * base_speed if base_speed else 0
            max_val = max_speed_for_char
        else:
            full_value = SET_BONUS_FULL[set_name]
            min_value = SET_BONUS_MIN[set_name]
            max_val = max_stats_non_speed.get(stat_key)

        if not max_val:
            bonuses[set_name] = {'full': 0.0, 'min': 0.0}
            continue

        bonuses[set_name] = {
            'full': full_value / max_val * weight,
            'min': min_value / max_val * weight,
        }

    return bonuses


def build_mod_scores(selected_characters, weight_overrides=None, session_dir=None):
    """Build the score matrix (mod, character) for every mod in the
    player's inventory against every selected character, plus the
    precomputed set bonus table per character.

    weight_overrides: optional dict of character_id -> {stat: value},
    takes precedence over mod_weightings.json for that character."""
    if weight_overrides is None:
        weight_overrides = {}

    _, processed_dir = session_paths(session_dir)
    score_save_path = os.path.join(processed_dir, 'mod_scores.json')
    bonus_save_path = os.path.join(processed_dir, 'set_bonus_values.json')

    with open(os.path.join(processed_dir, 'my_mods.json')) as f:
        my_mods = json.load(f)

    with open(WEIGHTINGS_PATH) as f:
        weightings = json.load(f)

    with open(MAX_STATS_PATH) as f:
        max_stats = json.load(f)

    with open(BASE_SPEED_PATH) as f:
        base_speeds = json.load(f)

    max_stats_non_speed = max_stats['non_speed_max']
    max_speed_per_char = max_stats['speed_max_per_character']

    scores = {}  # mod_id -> {character_id: score}
    set_bonuses = {}  # character_id -> {set_name: {'full': x, 'min': y}}

    for character_id in selected_characters:
        if character_id in weight_overrides:
            W_j = weight_overrides[character_id]
        else:
            char_weights_entry = weightings.get(character_id)
            if not char_weights_entry:
                continue
            W_j = char_weights_entry.get('raw_weights', {})

        base_speed = base_speeds.get(character_id)
        max_speed_for_char = max_speed_per_char.get(character_id)

        set_bonuses[character_id] = compute_set_bonus_table(
            character_id, W_j, base_speed, max_stats_non_speed, max_speed_for_char)

        for mod in my_mods:
            mod_id = mod['mod_id']
            score = compute_mod_score(mod, W_j, max_stats_non_speed, max_speed_for_char)

            if mod_id not in scores:
                scores[mod_id] = {}
            scores[mod_id][character_id] = score

    with open(score_save_path, 'w') as f:
        json.dump(scores, f, indent=2)
    print(f"Saved mod scores to {score_save_path}")

    with open(bonus_save_path, 'w') as f:
        json.dump(set_bonuses, f, indent=2)
    print(f"Saved set bonus values to {bonus_save_path}")

    return scores, set_bonuses


if __name__ == "__main__":
    # quick test with a couple of characters
    test_characters = ['HERMITYODA', 'DARTHBANE']
    build_mod_scores(test_characters)

