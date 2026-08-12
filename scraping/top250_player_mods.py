# Scrape mod data for top 50 in each kyber division
# Dump json and calculate mod weightings

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
import time
from utils import ensure_comlink_running, get_comlink_client

# ---------- reuse everything from user_mod_data.py ----------
# (STAT_MAP, UNSCALED_DIVISOR, SET_MAP, SLOT_MAP, TIER_MAP,
#  decode_stat, decode_mod — identical to user_mod_data.py)

STAT_MAP = {
    1:  ('health',          'flat'),
    5:  ('speed',           'flat'),
    16: ('critical_damage', 'pct'),
    17: ('potency',         'pct'),
    18: ('tenacity',        'pct'),
    28: ('protection',      'flat'),
    41: ('offense',         'flat'),
    42: ('defense',         'flat'),
    48: ('offense_pct',     'pct'),
    49: ('defense_pct',     'pct'),
    53: ('critical_chance', 'pct'),
    55: ('health_pct',      'pct'),
    56: ('protection_pct',  'pct'),
}

UNSCALED_DIVISOR = {'flat': 1e8, 'pct': 1e6}

SET_MAP = {
    '1': 'health', '2': 'offense', '3': 'defense', '4': 'speed',
    '5': 'critical_chance', '6': 'critical_damage', '7': 'potency', '8': 'tenacity',
}

SLOT_MAP = {
    '1': 'square', '2': 'arrow', '3': 'diamond',
    '4': 'triangle', '5': 'circle', '6': 'cross',
}

TIER_MAP = {1: 'grey', 2: 'green', 3: 'blue', 4: 'purple', 5: 'gold'}


def decode_stat(stat_entry):
    stat_id = stat_entry['unitStatId']
    raw = float(stat_entry['unscaledDecimalValue'])
    if stat_id not in STAT_MAP:
        return (f'unknown_{stat_id}', raw)
    name, stat_type = STAT_MAP[stat_id]
    value = raw / UNSCALED_DIVISOR[stat_type]
    return (name, value)


def decode_mod(mod, character_id):
    def_id = mod['definitionId']
    p_name, p_value = decode_stat(mod['primaryStat']['stat'])

    secondaries = []
    for sec in mod.get('secondaryStat', []):
        s_name, s_value = decode_stat(sec['stat'])
        secondaries.append({'stat': s_name, 'value': s_value, 'rolls': sec.get('statRolls')})

    dots = int(def_id[1])

    return {
        'mod_id': mod['id'],
        'character': character_id,
        'set': SET_MAP.get(def_id[0], f'unknown_{def_id[0]}'),
        'dots': dots,
        'slot': SLOT_MAP.get(def_id[2], f'unknown_{def_id[2]}'),
        'tier_colour': TIER_MAP.get(mod['tier'], f'unknown_{mod["tier"]}'),
        'tier': mod['tier'],
        'level': mod['level'],
        'is_six_dot': dots == 6,
        'primary': {'stat': p_name, 'value': p_value},
        'secondaries': secondaries,
    }


# ---------- MAIN FUNCTION ----------

PLAYER_IDS_PATH = 'data/raw/gac_leaderboard_kyber_all.json'
SAVE_PATH = 'data/processed/top250_mods.json'

def fetch_top250_player_mods():
    """Loops through the saved top-250 Kyber player IDs, pulls each roster,
    decodes every mod, and saves one combined file."""
    ensure_comlink_running()
    comlink = get_comlink_client()

    with open(PLAYER_IDS_PATH) as f:
        player_ids = json.load(f)

    all_mods = []
    total = len(player_ids)

    for i, (num, player_id) in enumerate(player_ids.items(), start=1):
        try:
            player_data = comlink.get_player(player_id=player_id)
            roster = player_data['rosterUnit']

            for unit in roster:
                character_id = unit['definitionId'].split(':')[0]
                for mod in unit.get('equippedStatMod', []):
                    decoded = decode_mod(mod, character_id)
                    decoded['player_id'] = player_id
                    all_mods.append(decoded)

            print(f"[{i}/{total}] {player_data['name']}: {len(roster)} characters processed")

        except Exception as e:
            print(f"[{i}/{total}] Failed for player_id {player_id}: {e}")

        time.sleep(0.2)  # be polite to the rate limit

    print(f"\nTotal mods collected across {total} players: {len(all_mods)}")

    with open(SAVE_PATH, 'w') as f:
        json.dump(all_mods, f, indent=2)
    print(f"Saved to {SAVE_PATH}")

    return all_mods


if __name__ == "__main__":
    if os.path.exists(SAVE_PATH):
        answer = input("Saved top250 mod data already exists. Refresh it? (y/n): ")
        if answer.lower() == 'y':
            fetch_top250_player_mods()
        else:
            print("Using existing saved data.")
    else:
        print("No saved data found — fetching fresh.")
        fetch_top250_player_mods()