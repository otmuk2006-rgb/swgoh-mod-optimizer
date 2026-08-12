import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
from swgoh_comlink import StatCalc

SAVE_PATH = 'data/processed/base_speed.json'

def fetch_base_speed_for_character(calc, character_id):
    """Build a minimal gear-13, level-85, no-mod unit and return base speed."""
    unit = {
        "defId": character_id,
        "rarity": 7,
        "level": 85,
        "gear": 13,
        "equipped": [],
        "skills": [],
    }
    calc.calc_char_stats(unit)
    return unit["stats"]["final"].get("Speed")


def fetch_all_base_speeds():
    calc = StatCalc()
    character_ids = list(calc._unit_data.keys())
    print(f"Found {len(character_ids)} characters in game data")

    base_speeds = {}
    for i, char_id in enumerate(character_ids, start=1):
        try:
            speed = fetch_base_speed_for_character(calc, char_id)
            base_speeds[char_id] = speed
            if i % 50 == 0:
                print(f"[{i}/{len(character_ids)}] processed...")
        except Exception as e:
            print(f"[{i}/{len(character_ids)}] Failed for {char_id}: {e}")

    with open(SAVE_PATH, 'w') as f:
        json.dump(base_speeds, f, indent=2)
    print(f"\nSaved {len(base_speeds)} base speeds to {SAVE_PATH}")

    return base_speeds


if __name__ == "__main__":
    if os.path.exists(SAVE_PATH):
        answer = input("Saved base speed data already exists. Refresh it? (y/n): ")
        if answer.lower() == 'y':
            fetch_all_base_speeds()
        else:
            print("Using existing saved data.")
    else:
        print("No saved data found — fetching fresh.")
        fetch_all_base_speeds()