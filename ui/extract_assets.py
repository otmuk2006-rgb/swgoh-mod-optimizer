# Pulls character portraits from a locally-running swgoh-ae2 web API
# (https://github.com/swgoh-utils/swgoh-ae2) into ui/static/img/characters/,
# so the UI serves plain static files instead of depending on a live
# extractor service at runtime.
#
# PORTRAIT NAMING — SOLVED PROPERLY: Comlink's own unit game data has a
# `thumbnailName` field (e.g. "tex.charui_rey_tros") giving the exact,
# always-correct portrait asset for every character. No fuzzy matching, no
# guessing, no visual verification needed — this was a long detour earlier
# (a text-similarity matcher got ~90% right but produced real duplicate/wrong
# assignments, like a wrong guess for Lord Vader and Kylo Ren/Unmasked
# colliding on one image) before this field was found. Confirmed 340/340
# playable characters resolve via this field with zero ambiguity.
#
# CONFIRMED AE2 WORKFLOW (Docker didn't work on this machine — no hardware
# virtualization support — so this runs the plain ASP.NET Core web API
# directly via the .NET SDK instead, no container needed):
#   1. git clone https://github.com/swgoh-utils/swgoh-ae2.git
#      cd swgoh-ae2 && git submodule update --init --recursive
#      (plain `git clone` alone leaves the AssetStudio submodule empty and
#      the build fails with "type or namespace 'AssetStudio' could not be found")
#   2. dotnet run --project AssetWebApi/AssetWebApi.csproj -c Release --urls "http://localhost:3001"
#      (port 3000 is taken by Comlink in this project)
#
# MOD SHAPE ICONS / GEAR & RELIC RING FRAMES — NOT from ae2. Exhaustively
# searched ae2's full asset catalog for both; the only things that ever
# downloaded without error were a blank white mask (mod shapes) and nothing
# at all (ui_unit_tile and friends — these are Unity prefabs with layered
# live components, not flat textures, so this 2D-texture extractor
# architecturally can't pull them). The gear-tier ring images
# (ui/static/img/gear/g1.webp..g13.webp — note g12 and g13 are the exact
# same file server-side, confirmed by matching content hash in the URL;
# gear 12 and 13 genuinely share identical ring art in the real game) and
# the three
# alignment-colored relic frame halves (relic_neutral/light/dark.webp) were
# instead reverse-engineered from swgoh.gg's own rendered roster page
# (https://swgoh.gg/p/<allycode>/characters/) via Selenium — their frontend
# CSS bundle embeds these as inline base64 WebP per
# `.character-portrait__gframe--tier-N` / `--relic-frame-bg-url` rules. The
# star icon (star.png) came the same way. This is a one-off manual capture,
# not an automated re-scrape step here — swgoh.gg is Cloudflare-protected
# and these assets change rarely, so there's no ongoing pipeline for them.
# Mod shape icons remain CSS-drawn (see character_detail.html / style.css).
#
# gear/relic/level/rarity/alignment data for the ring math lives in
# calculations/character_progress.py (built from the raw roster pull +
# Comlink's forceAlignment field), not here.

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
import httpx
from utils import ensure_comlink_running, get_comlink_client
from swgoh_comlink import StatCalc

AE2_BASE_URL = 'http://localhost:3001'

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'img')
CHARACTERS_DIR = os.path.join(STATIC_DIR, 'characters')

PORTRAIT_ASSETS_PATH = 'data/processed/character_portrait_assets.json'


def fetch_current_asset_version():
    ensure_comlink_running()
    comlink = get_comlink_client()
    return comlink.get_game_metadata()['assetVersion']


def build_portrait_mapping():
    """char_id -> charui_ asset name, straight from Comlink's own
    thumbnailName field for every playable character. Always correct,
    always complete — safe to re-run any time (e.g. after a game update
    adds a character), no matching logic involved at all."""
    ensure_comlink_running()
    comlink = get_comlink_client()
    meta = comlink.get_game_metadata()
    game_data = comlink.get_game_data(
        version=meta['latestGamedataVersion'], include_pve_units=True, request_segment=0
    )

    calc = StatCalc()
    playable_ids = {cid for cid, d in calc._unit_data.items() if d.get('combatType') == 1}

    mapping = {}
    for unit in game_data['units']:
        char_id = unit.get('baseId')
        thumb = unit.get('thumbnailName')
        if char_id in playable_ids and thumb and thumb.startswith('tex.'):
            mapping[char_id] = thumb[len('tex.'):]

    with open(PORTRAIT_ASSETS_PATH, 'w') as f:
        json.dump(mapping, f, indent=2, sort_keys=True)
    print(f'Portrait mapping: {len(mapping)} / {len(playable_ids)} playable characters resolved')
    return mapping


def fetch_asset(asset_name, version):
    resp = httpx.get(f'{AE2_BASE_URL}/Asset/single',
                      params={'assetName': asset_name, 'version': version}, timeout=30)
    resp.raise_for_status()
    return resp.content


def export_character_portraits():
    portrait_assets = build_portrait_mapping()
    version = fetch_current_asset_version()

    os.makedirs(CHARACTERS_DIR, exist_ok=True)
    ok, failed = 0, 0
    for char_id, asset_name in portrait_assets.items():
        dest = os.path.join(CHARACTERS_DIR, f'{char_id}.png')
        if os.path.exists(dest):
            ok += 1
            continue
        try:
            data = fetch_asset(asset_name, version)
            with open(dest, 'wb') as f:
                f.write(data)
            ok += 1
        except httpx.HTTPError as exc:
            print(f'  FAILED {char_id} ({asset_name}): {exc}')
            failed += 1

    print(f'Portraits: {ok} saved/present, {failed} failed')


if __name__ == '__main__':
    export_character_portraits()
