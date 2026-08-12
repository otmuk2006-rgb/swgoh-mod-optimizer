# Character tags for the "filter by tag" control on the character selection
# page — a flat, alphabetical list, no grouping (e.g. "Jedi", "Rebel",
# "Tank", "Gungan" all side by side).
#
# NOT sourced from Comlink's `categoryId` field directly, despite that
# looking like the obvious source. First attempt did exactly that (~1000
# raw categoryId values per unit, resolved to display text via the game's
# own `CATEGORY_<x>_DESC` localization keys) and it was wrong in both
# directions: it invented at least one tag that isn't a real in-game/
# swgoh.gg filter category at all ("species_human" resolves to a real loc
# string "Human", but Human was never actually a filterable category), it
# was missing several real ones with no obvious group prefix
# (character_fleetcommander, raid_order66_allowed, unaligned_force_user —
# none of which start with role_/affiliation_/species_/profession_, so a
# prefix-based filter silently dropped them), and it got display text wrong
# for others (affiliation_republic resolved to "Republic", but the actual
# filter label is "Galactic Republic"; profession_bountyhunter resolved to
# the plural "Bounty Hunters" against the real singular "Bounty Hunter").
# There's no Comlink enum that exposes a curated "these categoryId values
# are real player-facing tags" list to check against.
#
# So instead this scrapes swgoh.gg's own /characters/ listing
# (Selenium — Cloudflare-protected, same as the meta-ranking scrape in
# enums_slugs.py), which both a) ships the exact same curated tag list
# used by its own "Categories" filter modal (48 entries, confirmed by
# reading the modal's `<a href="?cat=...">` links directly) and b) prints
# each character's own real tags as plain text on their card
# (`.unit-card__cats`, bullet-separated — note the sibling
# `data-unit-tags` HTML attribute on the same card is NOT the full set,
# it silently omits role tags like Attacker/Healer/Support/Tank for
# reasons unknown, confirmed by direct comparison against the visible
# text for the same card). Every one of the 340 playable characters'
# `.unit-card__cats` tag set was cross-checked and is a subset of the
# same 48-entry master list — no unresolved leftovers.
#
# Each card is matched back to this project's own char_id via the
# `/units/<slug>/` href against the slug map already built and verified in
# enums_slugs.py's Step 2 (data/processed/character_meta_rankings.json) —
# matched 340/340 with zero name-string fuzzy matching needed.

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
import re
import time
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup

CHARACTERS_URL = 'https://swgoh.gg/characters/'
META_RANKINGS_PATH = 'data/processed/character_meta_rankings.json'
NAMES_PATH = 'data/processed/character_names.json'
SAVE_PATH = 'data/processed/character_tags.json'


def _fetch_characters_page():
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()))
    driver.get(CHARACTERS_URL)
    time.sleep(3)
    html = driver.page_source
    driver.quit()
    return html


def build_character_tags():
    with open(META_RANKINGS_PATH) as f:
        meta = json.load(f)
    slug_to_id = {v['slug']: k for k, v in meta.items()}

    with open(NAMES_PATH) as f:
        names = json.load(f)
    name_to_id = {v.lower(): k for k, v in names.items()}

    html = _fetch_characters_page()
    soup = BeautifulSoup(html, 'html.parser')
    cards = soup.select('.js-unit-search__result')

    tags_by_character = {}
    all_tag_names = set()
    unmatched = []

    for card in cards:
        link = card.select_one('a[href^="/units/"]')
        href = link['href'] if link else ''
        slug_match = re.match(r'/units/([^/]+)/', href)
        slug = slug_match.group(1) if slug_match else None
        char_id = slug_to_id.get(slug)
        if not char_id:
            char_id = name_to_id.get((card.get('data-unit-name') or '').lower())
        if not char_id:
            unmatched.append(card.get('data-unit-name'))
            continue

        cats_div = card.select_one('.unit-card__cats')
        if not cats_div:
            continue
        tag_names = sorted({
            t.strip() for t in re.split(r'[••]', cats_div.get_text()) if t.strip()
        })
        if tag_names:
            tags_by_character[char_id] = tag_names
            all_tag_names.update(tag_names)

    if unmatched:
        print(f'Warning: {len(unmatched)} swgoh.gg cards could not be matched to a char_id: {unmatched}')

    with open(SAVE_PATH, 'w') as f:
        json.dump({'tags_by_character': tags_by_character, 'all_tags': sorted(all_tag_names)}, f, indent=2, sort_keys=True)

    print(f'Tags: {len(all_tag_names)} distinct tags across {len(tags_by_character)} characters')
    return tags_by_character, sorted(all_tag_names)


if __name__ == '__main__':
    build_character_tags()
