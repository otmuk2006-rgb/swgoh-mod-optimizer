# Pulls every character's gear level

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
from utils import ensure_comlink_running, get_comlink_client, session_paths


def fetch_gear_levels(ally_code, session_dir=None):
    """Pull gear level for every character in the given account's roster."""
    ensure_comlink_running()
    comlink = get_comlink_client()
    player_data = comlink.get_player(allycode=ally_code)

    gear_levels = {}
    for unit in player_data['rosterUnit']:
        char_id = unit['definitionId'].split(':')[0]
        gear_levels[char_id] = unit.get('currentTier', 0)  # gear level (not relic)

    print(f"Found gear levels for {len(gear_levels)} characters")

    _, processed_dir = session_paths(session_dir)
    save_path = os.path.join(processed_dir, 'gear_levels.json')
    with open(save_path, 'w') as f:
        json.dump(gear_levels, f, indent=2)
    print(f"Saved to {save_path}")

    return gear_levels


if __name__ == "__main__":
    _, _processed_dir = session_paths()
    _save_path = os.path.join(_processed_dir, 'gear_levels.json')
    if os.path.exists(_save_path):
        answer = input("Saved gear level data already exists. Refresh it? (y/n): ")
        if answer.lower() == 'y':
            ally = input("Enter your ally code: ")
            fetch_gear_levels(ally)
        else:
            print("Using existing saved data.")
    else:
        print("No saved data found — fetching fresh.")
        ally = input("Enter your ally code: ")
        fetch_gear_levels(ally)