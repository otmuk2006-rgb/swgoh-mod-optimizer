import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
import pulp
from pulp import LpProblem, LpMaximize, LpVariable, lpSum, COIN_CMD, PULP_CBC_CMD, value
from utils import GLOBAL_DATA_DIR, session_paths

# global/community reference data — same for every visitor
PRIORITY_PATH = os.path.join(GLOBAL_DATA_DIR, 'character_priority.json')


def _find_cbc_path():
    """Locate pulp's bundled CBC binary directly, bypassing pulp's own
    architecture auto-detection — on Windows-on-ARM64 it looks for an
    'arm64' build that pulp doesn't actually ship, only i32/i64. The i64
    (x64) build runs fine under Windows' built-in x64 emulation."""
    if os.name != 'nt':
        return None  # let pulp auto-detect on non-Windows platforms

    win_dir = os.path.join(os.path.dirname(pulp.__file__), 'solverdir', 'cbc', 'win')
    for arch in ('i64', 'arm64', 'i32'):
        candidate = os.path.join(win_dir, arch, 'cbc.exe')
        if os.path.exists(candidate):
            return candidate
    return None


SET_REQUIREMENT = {
    'critical_chance': 2, 'critical_damage': 4, 'defense': 2,
    'health': 2, 'offense': 4, 'potency': 2, 'speed': 4, 'tenacity': 2,
}


GEAR_FLOOR_LEVEL = 13
GEAR_FLOOR_PRIORITY = 0.1


def load_priorities(gear_levels):
    """Tier-based priorities from character_priority.json, capped at
    GEAR_FLOOR_PRIORITY for characters below gear 13 in this roster.
    The cap is applied here, per solve, not baked into the JSON — that file
    is shared by every visitor, so it can't know anyone's gear levels."""
    with open(PRIORITY_PATH) as f:
        priority_data = json.load(f)

    priorities = {}
    for char_id, info in priority_data.items():
        p_j = info['priority_score']
        if gear_levels.get(char_id, 0) < GEAR_FLOOR_LEVEL:
            p_j = min(p_j, GEAR_FLOOR_PRIORITY)
        priorities[char_id] = p_j
    return priorities


def solve(selected_characters, locked_characters=None, priority_overrides=None, time_limit=None, session_dir=None):
    """
    selected_characters: set of character IDs to optimise
    locked_characters: set of character IDs whose current mods must stay put
    priority_overrides: optional dict of character_id -> custom p_j, overrides the default
    time_limit: optional max seconds to let CBC search — returns the best solution
        found so far (not necessarily proven optimal) if the limit is hit
    session_dir: this visitor's own data directory (roster/mods/gear/scores)
        — see utils.session_paths(). None uses the shared local data/
        layout, for the CLI entry point in main.py.

    Locked characters' mods never enter the ILP at all — they're fixed
    outside it and their mods are removed from the free pool, rather than
    creating decision variables for them and then constraining those to
    their known values. Same optimal solution either way (a mod pinned to
    a locked character could never have gone elsewhere regardless), but
    measured ~39% fewer variables and ~2.2x faster on a 60-character/
    20-locked test — CBC's own presolve strips the constrained-away
    variables back out, but building and handing over the larger model
    costs real time before that ever happens.
    """
    if locked_characters is None:
        locked_characters = set()
    if priority_overrides is None:
        priority_overrides = {}

    free_characters = set(selected_characters) - set(locked_characters)

    _, processed_dir = session_paths(session_dir)

    with open(os.path.join(processed_dir, 'my_mods.json')) as f:
        all_mods = json.load(f)

    with open(os.path.join(processed_dir, 'mod_scores.json')) as f:
        scores = json.load(f)  # {mod_id: {character_id: score}}

    with open(os.path.join(processed_dir, 'set_bonus_values.json')) as f:
        set_bonuses = json.load(f)  # {character_id: {set_name: {'full':x,'min':y}}}

    with open(os.path.join(processed_dir, 'gear_levels.json')) as f:
        gear_levels = json.load(f)

    # user overrides win over the gear floor
    default_priorities = load_priorities(gear_levels)
    priorities = {**default_priorities, **priority_overrides}

    # locked characters' current mods are fixed outcomes, not decisions —
    # pull them out of the pool before the ILP ever sees them
    locked_mod_ids = {m['mod_id'] for m in all_mods if m['character'] in locked_characters}
    free_mods = [m for m in all_mods if m['mod_id'] not in locked_mod_ids]
    mod_lookup = {m['mod_id']: m for m in free_mods}
    mod_ids = list(mod_lookup.keys())

    # ---------- decision variables ----------
    x = {}
    for mod_id in mod_ids:
        mod = mod_lookup[mod_id]
        is_six_dot = mod['dots'] == 6

        for char_id in free_characters:
            if char_id not in scores.get(mod_id, {}):
                continue

            char_gear = gear_levels.get(char_id, 0)
            if is_six_dot and char_gear < 12:
                continue  # can't assign 6-dot mods below gear 12

            x[(mod_id, char_id)] = LpVariable(f"x_{mod_id}_{char_id}", cat='Binary')

    z = {}
    for char_id in free_characters:
        for set_name in SET_REQUIREMENT:
            z[(char_id, set_name, 'full')] = LpVariable(f"z_{char_id}_{set_name}_full", cat='Binary')
            z[(char_id, set_name, 'min')] = LpVariable(f"z_{char_id}_{set_name}_min", cat='Binary')

    prob = LpProblem("mod_assignment", LpMaximize)

    # ---------- objective ----------
    objective_terms = []

    for (mod_id, char_id), var in x.items():
        p_j = priorities.get(char_id, 0.1)
        score = scores[mod_id][char_id]
        objective_terms.append(var * p_j * score)

    for char_id in free_characters:
        p_j = priorities.get(char_id, 0.1)
        char_bonuses = set_bonuses.get(char_id, {})
        for set_name in SET_REQUIREMENT:
            bonus_info = char_bonuses.get(set_name, {})
            full_val = bonus_info.get('full', 0)
            min_val = bonus_info.get('min', 0)
            objective_terms.append(z[(char_id, set_name, 'full')] * p_j * full_val)
            objective_terms.append(z[(char_id, set_name, 'min')] * p_j * min_val)

    prob += lpSum(objective_terms)

    # ---------- constraints ----------

    # each mod assigned to at most one character
    for mod_id in mod_ids:
        relevant_vars = [x[(mod_id, char_id)] for char_id in free_characters
                          if (mod_id, char_id) in x]
        if relevant_vars:
            prob += lpSum(relevant_vars) <= 1

    # one mod per slot type per character
    all_slots = set(m['slot'] for m in free_mods)
    for char_id in free_characters:
        for slot in all_slots:
            slot_vars = [x[(mod_id, char_id)] for mod_id in mod_ids
                         if (mod_id, char_id) in x and mod_lookup[mod_id]['slot'] == slot]
            if slot_vars:
                prob += lpSum(slot_vars) <= 1

    # set bonus linking constraints — checks mod LEVEL == 15, not dots
    for char_id in free_characters:
        for set_name, required in SET_REQUIREMENT.items():
            full_mods = [mod_id for mod_id in mod_ids
                         if (mod_id, char_id) in x
                         and mod_lookup[mod_id]['set'] == set_name
                         and mod_lookup[mod_id]['level'] == 15]
            any_level_mods = [mod_id for mod_id in mod_ids
                               if (mod_id, char_id) in x
                               and mod_lookup[mod_id]['set'] == set_name]

            if full_mods:
                prob += lpSum(x[(mod_id, char_id)] for mod_id in full_mods) >= required * z[(char_id, set_name, 'full')]
            else:
                prob += z[(char_id, set_name, 'full')] == 0

            if any_level_mods:
                prob += lpSum(x[(mod_id, char_id)] for mod_id in any_level_mods) >= required * z[(char_id, set_name, 'min')]
            else:
                prob += z[(char_id, set_name, 'min')] == 0

            prob += z[(char_id, set_name, 'full')] + z[(char_id, set_name, 'min')] <= 1

    # ---------- solve ----------
    cbc_path = _find_cbc_path()
    solver_kwargs = {'msg': 1}
    if time_limit is not None:
        solver_kwargs['timeLimit'] = time_limit
    prob.solve(COIN_CMD(path=cbc_path, **solver_kwargs) if cbc_path else PULP_CBC_CMD(**solver_kwargs))

    print(f"\nStatus: {prob.status}")
    print(f"Total objective value: {value(prob.objective):.4f}")

    # ---------- extract results ----------
    assignments = {}
    for (mod_id, char_id), var in x.items():
        if value(var) == 1:
            assignments.setdefault(char_id, []).append(mod_id)

    # locked characters never entered the ILP — their result is just
    # "whatever they already had"
    for char_id in locked_characters:
        assignments[char_id] = [m['mod_id'] for m in all_mods if m['character'] == char_id]

    print("\n--- Assignments ---")
    for char_id, mods in assignments.items():
        print(f"{char_id}: {len(mods)} mods")

    output = {
        # characters actually considered by this solve — lets downstream
        # reporting tell "not part of this run" apart from "genuinely benched"
        'selected_characters': sorted(selected_characters),
        'assignments': assignments,
    }
    assignment_path = os.path.join(processed_dir, 'final_assignment.json')
    with open(assignment_path, 'w') as f:
        json.dump(output, f, indent=2)
    print(f"\nSaved to {assignment_path}")

    return assignments


if __name__ == "__main__":
    _, _processed_dir = session_paths()
    with open(os.path.join(_processed_dir, 'my_mods.json')) as f:
        all_mods = json.load(f)
    all_characters = sorted(set(m['character'] for m in all_mods))

    print(f"Optimising full roster: {len(all_characters)} characters")
    solve(selected_characters=set(all_characters))