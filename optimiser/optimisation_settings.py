
def get_optimisation_settings(all_character_ids):
    """Interactive setup for a single optimiser run. Returns a dict with
    selected characters, locked characters, priority overrides, and
    weight overrides."""

    # ---- 1. Character selection ----
    print("\n--- Character Selection ---")
    mode = input("Optimise (a) whole roster or (s) select specific characters? [a/s]: ").strip().lower()

    if mode == 'a':
        selected = set(all_character_ids)
        exclude = input("Any characters to exclude? Comma-separated IDs, or blank: ").strip()
        if exclude:
            excluded_ids = {c.strip().upper() for c in exclude.split(',')}
            selected -= excluded_ids
    else:
        chosen = input("Enter character IDs to optimise, comma-separated: ").strip()
        selected = {c.strip().upper() for c in chosen.split(',')}

    # ---- 2. Locked characters ----
    print("\n--- Locked Characters ---")
    print("Locked characters keep their current mods untouched — those mods")
    print("won't be taken or reassigned to anyone else.")
    locked_input = input("Enter character IDs to lock, comma-separated, or blank: ").strip()
    locked = {c.strip().upper() for c in locked_input.split(',')} if locked_input else set()

    # ---- 3. Character priority source ----
    print("\n--- Character Priority ---")
    print("Character priority (p_j) determines how much the optimiser")
    print("favours giving good mods to this character over others.")
    priority_mode = input("Use (d) data-driven rankings from swgoh.gg, or (c) set your own? [d/c]: ").strip().lower()

    priorities = {}
    if priority_mode == 'd':
        pass  # no overrides — solver.py loads character_priority.json and applies the gear floor
    else:
        for char_id in selected:
            val = input(f"Priority for {char_id} (0.0 - 1.0): ").strip()
            priorities[char_id] = float(val)

    # ---- 4. Mod weighting source ----
    print("\n--- Mod Weightings ---")
    print("Mod weightings (W_j) determine which stats each character values.")
    weight_mode = input("Use (d) data-driven weights from top 250 GAC players, or (c) set your own? [d/c]: ").strip().lower()

    weights = {}
    if weight_mode == 'd':
        pass  # no overrides — mod_score.py falls back to mod_weightings.json per character
    else:
        for char_id in selected:
            print(f"\nEnter weights for {char_id} (leave blank to skip a stat):")
            char_weights = {}
            for stat in ['speed', 'health', 'health_pct', 'protection', 'protection_pct',
                         'offense', 'offense_pct', 'defense', 'defense_pct',
                         'critical_chance', 'critical_damage', 'potency', 'tenacity']:
                val = input(f"  {stat}: ").strip()
                if val:
                    char_weights[stat] = float(val)
            weights[char_id] = char_weights

    return {
        'selected_characters': selected,
        'locked_characters': locked,
        'manual_priorities': priorities,
        'weights': weights,
    }


if __name__ == "__main__":
    test_roster = ['HERMITYODA', 'DARTHBANE', 'JEDIMASTERKENOBI']
    settings = get_optimisation_settings(test_roster)
    print("\n--- Final settings ---")
    print(settings)