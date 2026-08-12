import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import time
import json
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup

SUCCESS_PATH = 'data/processed/character_meta_rankings.json'
PRIORITY_SAVE_PATH = 'data/processed/character_priority.json'
GEAR_LEVELS_PATH = 'data/processed/gear_levels.json'

TIER_VALUES = {'S': 1.0, 'A': 0.8, 'B': 0.6, 'C': 0.4, 'D': 0.2}
MINIMUM_FLOOR = 0.1

MANUAL_TIER_OVERRIDES = {
    'aayla-secura': 'B', 'admiral-piett': 'B', 'boss-nass': 'A', 'cobb-vanth': 'A',
    'commander-luke-skywalker': 'B', 'cx-2': 'A', 'darth-bane': 'S',
    'grand-inquisitor': 'A', 'gungan-boomadier': 'B', 'gungan-phalanx': 'B',
    'jedi-master-kenobi': 'S', 'luminara-unduli': 'C', 'ugnaught': 'D',
    'marrok': 'A', 'shin-hati': 'A', 'rey': 'S', 'sith-eternal-emperor': 'S',
    'the-mandalorian-beskar-armor': 'A', 'wampa': 'A',
}


def parse_grid(lines, start_idx):
    try:
        header_idx = lines.index('Overall', start_idx + 2)
    except ValueError:
        return None
    idx = header_idx + 1 + 2
    row_labels = ['Both', '5v5', '3v3']
    grid = {}
    for row in row_labels:
        if idx >= len(lines) or lines[idx] != row:
            break
        idx += 1
        overall = lines[idx]; idx += 1
        offense = lines[idx]; idx += 1
        defense = lines[idx]; idx += 1
        grid[row] = {'overall': overall, 'offense': offense, 'defense': defense}
    return grid


def fetch_character_meta(driver, slug):
    url = f"https://swgoh.gg/units/{slug}/meta/"
    driver.get(url)
    time.sleep(2.5)
    soup = BeautifulSoup(driver.page_source, 'html.parser')
    text = soup.get_text(separator='\n', strip=True)
    lines = text.split('\n')

    result = {'slug': slug, 'as_leader': None, 'as_member': None}
    if 'As a Leader' in lines:
        result['as_leader'] = parse_grid(lines, lines.index('As a Leader'))
    if 'As a Member' in lines:
        result['as_member'] = parse_grid(lines, lines.index('As a Member'))
    return result


def overall_tier_from_grid(grid):
    if not grid or 'Both' not in grid:
        return None
    return TIER_VALUES.get(grid['Both'].get('overall'))


def compute_priority(result):
    leader_score = overall_tier_from_grid(result.get('as_leader'))
    member_score = overall_tier_from_grid(result.get('as_member'))
    candidates = [v for v in [leader_score, member_score] if v is not None]
    return max(candidates) if candidates else MINIMUM_FLOOR


def apply_manual_overrides(priorities):
    for slug, tier_letter in MANUAL_TIER_OVERRIDES.items():
        matched = False
        for char_id, info in priorities.items():
            if info.get('slug') == slug:
                info['priority_score'] = TIER_VALUES[tier_letter]
                info['manually_overridden'] = True
                matched = True
                break
        if not matched:
            print(f"Warning: override slug '{slug}' not found — check spelling")
    return priorities


def apply_gear_floor(priorities):
    if not os.path.exists(GEAR_LEVELS_PATH):
        print("Warning: gear_levels.json not found, skipping gear floor")
        return priorities
    with open(GEAR_LEVELS_PATH) as f:
        gear_levels = json.load(f)

    floored_count = 0
    excluded_count = 0
    for char_id, info in priorities.items():
        if char_id not in gear_levels:
            info['priority_score'] = 0.0
            info['not_owned'] = True
            excluded_count += 1
        elif gear_levels[char_id] < 13 and info['priority_score'] > MINIMUM_FLOOR:
            info['priority_score'] = MINIMUM_FLOOR
            info['gear_floored'] = True
            floored_count += 1

    print(f"Excluded {excluded_count} unowned characters (priority = 0)")
    print(f"Floored {floored_count} owned characters below gear 13 (priority = {MINIMUM_FLOOR})")
    return priorities


def run_priority_scrape():
    with open(SUCCESS_PATH) as f:
        succeeded = json.load(f)   # enum_id -> {name, slug, title}

    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()))

    priorities = {}
    total = len(succeeded)

    for i, (char_id, info) in enumerate(succeeded.items(), start=1):
        slug = info['slug']
        try:
            result = fetch_character_meta(driver, slug)
            score = compute_priority(result)
            priorities[char_id] = {          # enum ID as the key — restored
                'slug': slug,
                'priority_score': score,
                'raw': result,
            }
            print(f"[{i}/{total}] {char_id} ({slug}): {score}")
        except Exception as e:
            print(f"[{i}/{total}] FAILED {char_id}: {e}")
            priorities[char_id] = {'slug': slug, 'priority_score': MINIMUM_FLOOR, 'error': str(e)}

    driver.quit()

    priorities = apply_manual_overrides(priorities)
    priorities = apply_gear_floor(priorities)

    with open(PRIORITY_SAVE_PATH, 'w') as f:
        json.dump(priorities, f, indent=2)
    print(f"\nSaved {len(priorities)} entries to {PRIORITY_SAVE_PATH}")
    return priorities


if __name__ == "__main__":
    if os.path.exists(PRIORITY_SAVE_PATH):
        answer = input("Saved character priority data already exists. Refresh it? (y/n): ")
        if answer.lower() == 'y':
            run_priority_scrape()
        else:
            print("Using existing saved data.")
    else:
        print("No saved data found — fetching fresh.")
        run_priority_scrape()