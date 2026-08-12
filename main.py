import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils import ensure_comlink_running

def main(refresh_community_data=False):
    ensure_comlink_running()

    ally_code = input("Enter your ally code: ")

    # ---------- Step 1: personal mod data (always fresh) ----------
    print("\nStep 1: Pulling your personal mod data...")
    from scraping.user_mod_data import fetch_user_mod_data
    fetch_user_mod_data(ally_code)

    from scraping.char_gear import fetch_gear_levels
    fetch_gear_levels(ally_code)

    # ---------- Step 2: community weight data (mod weightings) ----------
    if refresh_community_data or not os.path.exists('data/processed/mod_weightings.json'):
        print("\nStep 2: Refreshing community mod weight data (slow)...")

        from scraping.GAC_leaderboards import fetch_all_kyber_divisions
        fetch_all_kyber_divisions()

        from scraping.top250_player_mods import fetch_top250_player_mods
        fetch_top250_player_mods()

        from scraping.unit_base_speed import fetch_all_base_speeds
        fetch_all_base_speeds()

        from calculations.max_possible_stats import save_max_possible_stats
        save_max_possible_stats()

        from calculations.mod_weightings import build_mod_weightings
        build_mod_weightings()
    else:
        print("\nStep 2: Using cached mod weightings")

    # ---------- Step 3: character priority ----------
    if refresh_community_data or not os.path.exists('data/processed/character_priority.json'):
        print("\nStep 3: Refreshing character priority rankings (slow)...")

        from scraping.enums_slugs import run_full_pipeline as run_enums_slugs
        run_enums_slugs()

        from scraping.character_priority_rankings import run_priority_scrape
        run_priority_scrape()
    else:
        print("\nStep 3: Using cached character priority rankings")

    # ---------- Step 4: optimisation settings ----------
    print("\nStep 4: Optimisation settings...")
    from optimiser.optimisation_settings import get_optimisation_settings

    import json
    with open('data/processed/my_mods.json') as f:
        my_mods = json.load(f)
    all_character_ids = sorted(set(m['character'] for m in my_mods))

    settings = get_optimisation_settings(all_character_ids)

    # ---------- Step 5: mod scoring ----------
    print("\nStep 5: Scoring mods for selected characters...")
    from calculations.mod_score import build_mod_scores
    build_mod_scores(settings['selected_characters'], weight_overrides=settings['weights'])

    # ---------- Step 6: run the ILP solver ----------
    print("\nStep 6: Running ILP solver...")
    from optimiser.solver import solve
    solve(
        selected_characters=settings['selected_characters'],
        locked_characters=settings['locked_characters'],
        priority_overrides=settings['manual_priorities'],
    )

    print("\nDone. Final assignment saved to data/processed/final_assignment.json")


if __name__ == "__main__":
    refresh = input("Refresh community data (mod weightings, priority rankings)? This is slow. (y/n): ")
    main(refresh_community_data=(refresh.lower() == 'y'))