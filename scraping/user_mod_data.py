import os
import json
from utils import ensure_comlink_running, get_comlink_client, session_paths

# ---------- VERIFIED MAPPINGS ----------

# stat_id : (name, type)  -- type determines the unscaled divisor
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

# unscaledDecimalValue divisors for full precision
UNSCALED_DIVISOR = {
    'flat': 1e8,
    'pct':  1e6,
}

# definitionId first digit = set
SET_MAP = {
    '1': 'health', '2': 'offense', '3': 'defense', '4': 'speed',
    '5': 'critical_chance', '6': 'critical_damage', '7': 'potency', '8': 'tenacity',
}

# definitionId last digit = slot/shape
SLOT_MAP = {
    '1': 'square', '2': 'arrow', '3': 'diamond',
    '4': 'triangle', '5': 'circle', '6': 'cross',
}

# tier field = colour
TIER_MAP = {
    1: 'grey', 2: 'green', 3: 'blue', 4: 'purple', 5: 'gold',
}


def decode_stat(stat_entry):
    """Use unscaledDecimalValue for maximum precision."""
    stat_id = stat_entry['unitStatId']
    raw = float(stat_entry['unscaledDecimalValue'])
    if stat_id not in STAT_MAP:
        return (f'unknown_{stat_id}', raw)
    name, stat_type = STAT_MAP[stat_id]
    value = raw / UNSCALED_DIVISOR[stat_type]
    return (name, value)


def decode_mod(mod, character_id):
    """Turn one raw Comlink mod into a clean dictionary."""
    def_id = mod['definitionId']

    # primary stat
    p_name, p_value = decode_stat(mod['primaryStat']['stat'])

    # secondary stats
    secondaries = []
    for sec in mod.get('secondaryStat', []):
        s_name, s_value = decode_stat(sec['stat'])
        secondaries.append({
            'stat': s_name,
            'value': s_value,
            'rolls': sec.get('statRolls'),
        })

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

def fetch_user_mod_data(ally_code, session_dir=None):
    """Pull and decode the given ally code's mod data. Returns the list of mods."""
    ensure_comlink_running()
    comlink = get_comlink_client()
    player_data = comlink.get_player(allycode=ally_code)

    roster = player_data['rosterUnit']
    print(f"Player: {player_data['name']}")
    print(f"Total characters: {len(roster)}")

    raw_dir, processed_dir = session_paths(session_dir)

    roster_path = os.path.join(raw_dir, 'my_roster.json')
    with open(roster_path, 'w') as f:
        json.dump(player_data, f, indent=2)
    print(f"Saved to {roster_path}")

    all_mods = []
    for unit in roster:
        character_id = unit['definitionId'].split(':')[0]
        for mod in unit.get('equippedStatMod', []):
            all_mods.append(decode_mod(mod, character_id))

    print(f"Total mods extracted: {len(all_mods)}")

    mods_path = os.path.join(processed_dir, 'my_mods.json')
    with open(mods_path, 'w') as f:
        json.dump(all_mods, f, indent=2)
    print(f"Saved to {mods_path}")

    print("\n--- First 3 mods ---")
    for m in all_mods[:3]:
        print(json.dumps(m, indent=2))

    return all_mods


# Only runs when this file is executed directly, not when imported elsewhere
if __name__ == "__main__":
    ally = input("Enter your ally code: ")
    fetch_user_mod_data(ally)