# Per-character progress data (gear/relic/level/rarity/alignment/power/
# stats) driving the gear/relic ring + badges on character portraits, and
# the sort options on the character selection page. See ui/extract_assets.py
# for where the ring/star images themselves came from.
#
# Ring logic, reverse-engineered from swgoh.gg's rendering (see
# ui/extract_assets.py for the full story): a character shows either a
# gear-tier ring (frames g1.webp..g13.webp — g12 and g13 share identical
# art) OR — once relic is actually unlocked — a pair of
# alignment-colored relic frame halves (relic_neutral/light/dark.webp,
# mirrored left/right) plus a small number badge for the relic tier itself.
# Confirmed against real roster data: every gear-13 character already has
# relic.currentTier >= 2, so "relic active" is a safe, exact predicate —
# relic.currentTier 0/1 always means gear < 13 in this data.

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import copy
import json
from utils import ensure_comlink_running, get_comlink_client, session_paths
from swgoh_comlink import StatCalc

ALIGNMENT_NAMES = {1: 'neutral', 2: 'light', 3: 'dark'}

# offered as sort options on the character selection page — same stat
# names calc_char_stats produces (see calculations/reporting.py)
SORTABLE_STATS = [
    'Speed', 'Health', 'Protection', 'Physical Damage', 'Special Damage',
    'Armor', 'Resistance', 'Potency', 'Tenacity',
    'Physical Critical Chance', 'Special Critical Chance', 'Critical Damage',
]


def _relic_raw_tier(unit):
    relic = unit.get('relic')
    return relic.get('currentTier', 0) if relic else 0


def fetch_reference_data():
    """(alignment_map, skill_defs) — static game data, same for every
    player. alignment_map: char_id -> forceAlignment (1=neutral, 2=light,
    3=dark). skill_defs: skill id -> its full tier definition list, used to
    tell whether a character's *current* tier on a given skill is a zeta or
    omicron tier (see count_zetas_omicrons)."""
    ensure_comlink_running()
    comlink = get_comlink_client()
    meta = comlink.get_game_metadata()
    game_data = comlink.get_game_data(
        version=meta['latestGamedataVersion'], include_pve_units=True, request_segment=0
    )
    alignment_map = {u['baseId']: u.get('forceAlignment', 1) for u in game_data['units'] if u.get('baseId')}
    skill_defs = {s['id']: s for s in game_data.get('skill', []) if s.get('id')}
    return alignment_map, skill_defs


def count_zetas_omicrons(unit_skills, skill_defs):
    """A character's skill list gives a 0-indexed tier already unlocked
    per skill; cross-reference against that skill's own tier definitions
    (isZetaTier/isOmicronTier) to count zeta/omicron skills.

    Bug fixed here: a skill can have zeta at tier 6 and omicron at tier 7
    (confirmed on MANDALORBOKATAN's leaderskill) — checking only the exact
    current tier index missed the zeta once a character progressed past it
    to omicron, so a character with both showed only one. Fix: a skill
    counts as "has zeta"/"has omicron" if *any* tier up to and including
    the current one was a zeta/omicron tier, not just the current one."""
    zeta_count = 0
    omicron_count = 0
    for skill in unit_skills:
        skill_def = skill_defs.get(skill.get('id'))
        if not skill_def:
            continue
        tiers = skill_def.get('tier', [])
        current_index = skill.get('tier', -1)
        if current_index < 0:
            continue
        achieved = tiers[:current_index + 1]
        if any(t.get('isZetaTier') for t in achieved):
            zeta_count += 1
        if any(t.get('isOmicronTier') for t in achieved):
            omicron_count += 1
    return zeta_count, omicron_count


def build_character_progress(session_dir=None, calc=None):
    """calc: an existing StatCalc instance to reuse, if the caller already
    has one (see ui/app.py's get_stat_calc()) — StatCalc fetches game data
    over the network on construction, so building a fresh one per visitor
    per request is wasteful and, under a memory-constrained deployment, a
    real risk. Falls back to constructing its own when run standalone
    (the CLI entry point / this file's own __main__ block)."""
    raw_dir, processed_dir = session_paths(session_dir)
    roster_path = os.path.join(raw_dir, 'my_roster.json')
    save_path = os.path.join(processed_dir, 'character_progress.json')

    with open(roster_path) as f:
        data = json.load(f)
    roster = data['rosterUnit'] if 'rosterUnit' in data else data

    alignment_map, skill_defs = fetch_reference_data()
    calc = calc or StatCalc()

    progress = {}
    failed = 0
    for unit in roster:
        char_id = unit['definitionId'].split(':')[0]
        gear = unit.get('currentTier', 0)
        relic_raw = _relic_raw_tier(unit)
        relic_active = gear == 13 and relic_raw >= 2
        zeta_count, omicron_count = count_zetas_omicrons(unit.get('skill', []), skill_defs)

        # power + full stats, using the character's real current mods —
        # skips ships/non-combat units, which don't have gear data at all
        power = None
        stats = {}
        try:
            computed = calc.calc_char_stats(copy.deepcopy(unit))
            power = computed.get('gp')
            final = computed.get('stats', {}).get('final', {})
            stats = {name: round(final[name], 2) for name in SORTABLE_STATS if name in final}
        except KeyError:
            failed += 1

        progress[char_id] = {
            'gear': gear,
            'relic_active': relic_active,
            'relic_tier': (relic_raw - 2) if relic_active else None,
            'level': unit.get('currentLevel', 1),
            'rarity': unit.get('currentRarity', 1),
            'alignment': ALIGNMENT_NAMES.get(alignment_map.get(char_id, 1), 'neutral'),
            'power': power,
            'stats': stats,
            'zeta_count': zeta_count,
            'omicron_count': omicron_count,
        }

    with open(save_path, 'w') as f:
        json.dump(progress, f, indent=2)
    print(f'Saved progress data for {len(progress)} characters to {save_path} ({failed} non-combat units skipped)')
    return progress


if __name__ == '__main__':
    build_character_progress()
