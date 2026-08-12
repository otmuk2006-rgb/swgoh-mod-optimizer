import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
import re
import time
from utils import ensure_comlink_running, get_comlink_client
from swgoh_comlink import StatCalc
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup

NAMES_PATH = 'data/processed/character_names.json'
SLUGS_SAVE_PATH = 'data/processed/character_meta_rankings.json'
FAILED_PATH = 'data/processed/failed_character_slugs.json'

MANUAL_SLUG_FIXES = {
    'CC2224':              'cc-2224-cody',
    'CHIRRUTIMWE':         'chirrut-imwe',
    'CLONESERGEANTPHASEI': 'clone-sergeant-phase-i',
    'HOTHLEIA':            'rebel-officer-leia-organa',
    'LUKESKYWALKER':       'luke-skywalker-farmboy',
    'PADMEAMIDALA':        'padme-amidala',
}

SKIP_CHARACTERS = {
    'TIEADVANCED',
    'TIEINTERCEPTOR',
    'XANADUBLOOD',
}


# ========== STEP 1: enum ID -> display name (from Comlink localization) ==========

def build_character_name_map():
    """enum_id (baseId) -> display name, resolved via each unit's own
    authoritative nameKey field rather than guessing a UNIT_{id}_NAME
    localization key pattern. The pattern guess breaks whenever a unit's
    real key differs from its own id — either because the name is
    deliberately shared with a different unit (R2D2_LEGENDARY's nameKey is
    UNIT_R2D2_NAME, same as base R2-D2, so it never got a "R2D2_LEGENDARY"
    entry at all) or because the game moved a character onto a newer key
    (many now use a "_V2" suffix) while an orphaned old key with a stale
    name still lingers in the localization dump, silently shown instead.
    Confirmed 12 owned characters hit one of these two failure modes."""
    ensure_comlink_running()
    comlink = get_comlink_client()

    metadata = comlink.get_game_metadata()
    localization_id = metadata['latestLocalizationBundleVersion']

    localization = comlink.get_localization(
        localization_id=localization_id,
        locale='ENG_US',
        unzip=True
    )

    loc_map = {}
    for line in localization['Loc_ENG_US.txt'].split('\n'):
        if '|' not in line:
            continue
        key, _, value = line.partition('|')
        loc_map[key] = value

    game_data = comlink.get_game_data(
        version=metadata['latestGamedataVersion'], include_pve_units=True, request_segment=0
    )

    character_names = {}
    for unit in game_data['units']:
        base_id = unit.get('baseId')
        name_key = unit.get('nameKey')
        if base_id and name_key and name_key in loc_map:
            character_names[base_id] = loc_map[name_key]

    print(f"Step 1: Found {len(character_names)} character names")

    with open(NAMES_PATH, 'w') as f:
        json.dump(character_names, f, indent=2)
    print(f"Step 1: Saved to {NAMES_PATH}")

    return character_names


# ========== STEP 2: enum ID -> verified swgoh.gg slug ==========

def name_to_slug(display_name):
    slug = display_name.lower()
    slug = slug.replace("'", "")
    replacements = {'é': 'e', 'è': 'e', 'ê': 'e', 'á': 'a', 'à': 'a', 'ñ': 'n'}
    for accented, plain in replacements.items():
        slug = slug.replace(accented, plain)
    slug = re.sub(r'[^a-z0-9\s-]', '', slug)
    slug = re.sub(r'\s+', '-', slug.strip())
    return slug


def get_slug_for_character(char_id, display_name):
    if char_id in MANUAL_SLUG_FIXES:
        return MANUAL_SLUG_FIXES[char_id]
    return name_to_slug(display_name)


def scrape_character_meta(driver, slug):
    """Try to load a character's meta page. Returns (title, soup) if
    successful, or (None, soup) if it failed."""
    url = f"https://swgoh.gg/units/{slug}/meta/"
    driver.get(url)
    time.sleep(2)

    soup = BeautifulSoup(driver.page_source, 'html.parser')
    title = soup.title.string if soup.title else None

    if title is None or "not found" in title.lower() or "404" in title:
        return None, soup
    return title, soup


def build_verified_slugs(character_names):
    """For every character, confirm their swgoh.gg slug actually works,
    filtering to real playable characters only (excludes ships/NPCs)."""

    calc = StatCalc()
    playable_character_ids = {
        char_id for char_id, data in calc._unit_data.items()
        if data.get('combatType') == 1
    }

    filtered_names = {
        char_id: name for char_id, name in character_names.items()
        if char_id in playable_character_ids and char_id not in SKIP_CHARACTERS
    }
    print(f"\nStep 2: Filtered down to {len(filtered_names)} playable characters")

    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()))

    succeeded = {}
    failed = {}

    total = len(filtered_names)
    for i, (char_id, display_name) in enumerate(filtered_names.items(), start=1):
        slug = get_slug_for_character(char_id, display_name)
        title, soup = scrape_character_meta(driver, slug)

        if title:
            succeeded[char_id] = {'name': display_name, 'slug': slug, 'title': title}
            print(f"[{i}/{total}] OK: {char_id} -> {slug}")
        else:
            failed[char_id] = {'name': display_name, 'attempted_slug': slug}
            print(f"[{i}/{total}] FAILED: {char_id} -> {slug}")

    driver.quit()

    print(f"\nStep 2: Succeeded: {len(succeeded)}")
    print(f"Step 2: Failed: {len(failed)}")

    with open(SLUGS_SAVE_PATH, 'w') as f:
        json.dump(succeeded, f, indent=2)
    with open(FAILED_PATH, 'w') as f:
        json.dump(failed, f, indent=2)

    print(f"Step 2: Saved successes to {SLUGS_SAVE_PATH}")
    print(f"Step 2: Saved failures to {FAILED_PATH}")

    return succeeded, failed


# ========== MAIN — runs both steps in order ==========

def run_full_pipeline():
    character_names = build_character_name_map()
    build_verified_slugs(character_names)


if __name__ == "__main__":
    run_full_pipeline()