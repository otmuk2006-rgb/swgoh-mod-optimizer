# Scrapes GAC leaderboards, top 50 from each Kyber division. Dumps player IDs into a json
# Limited sample of 250 unfortunately, and not top 1000 best. But it will do    

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils import ensure_comlink_running, get_comlink_client
import json

SAVE_PATH = 'data/raw/gac_leaderboard_kyber_all.json'

def fetch_all_kyber_divisions():
    """Pulls top 50 players from each of the 5 Kyber divisions (~250 total)."""
    ensure_comlink_running()
    comlink = get_comlink_client()

    all_players = []
    divisions = [25, 20, 15, 10, 5]  # Division 1 through Division 5

    for div in divisions:
        gac_lb = comlink.get_gac_leaderboard(leaderboard_type=6, league=100, division=div)
        players = gac_lb['leaderboard'][0]['player']
        print(f"Division {div}: {len(players)} players")
        all_players.extend(players)

    print(f"\nTotal Kyber players collected: {len(all_players)}")

    # clean down to just numbered player IDs
    player_ids = {i: p['id'] for i, p in enumerate(all_players, start=1)}

    with open(SAVE_PATH, 'w') as f:
        json.dump(player_ids, f, indent=2)
    print(f"Saved {len(player_ids)} player IDs to {SAVE_PATH}")

    return player_ids


if __name__ == "__main__":
    if os.path.exists(SAVE_PATH):
        answer = input("Saved leaderboard data already exists. Refresh it? (y/n): ")
        if answer.lower() == 'y':
            fetch_all_kyber_divisions()
        else:
            print("Using existing saved data.")
    else:
        print("No saved data found — fetching fresh.")
        fetch_all_kyber_divisions()