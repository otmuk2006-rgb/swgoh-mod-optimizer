import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
import re
import time
import random
import shutil
import threading
import traceback
import uuid

from flask import Flask, render_template, request, redirect, url_for, jsonify, g, abort
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.middleware.proxy_fix import ProxyFix

from utils import ensure_comlink_running, session_paths, GLOBAL_DATA_DIR, BASE_DIR
from scraping.user_mod_data import fetch_user_mod_data
from scraping.char_gear import fetch_gear_levels
from calculations.character_progress import build_character_progress, SORTABLE_STATS
from calculations.mod_score import build_mod_scores
from optimiser.solver import solve
from calculations.reporting import (
    load_raw_roster, build_unit_lookup, build_raw_mod_lookup,
    build_character_stat_report, load_assignment,
)
from swgoh_comlink import StatCalc

app = Flask(__name__)
# Render/Railway/Fly all sit behind a reverse proxy that terminates TLS and
# forwards the real client IP — without this, request.is_secure is always
# False (breaks secure cookies) and request.remote_addr is the proxy's own
# address (breaks per-IP rate limiting).
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_for=1)

limiter = Limiter(app=app, key_func=get_remote_address, default_limits=[])

# Both community-data-refresh routes are slow, and /refresh/priority runs a
# real Selenium/Chrome scrape against swgoh.gg — not something to expose to
# random visitors of a live site. Off by default; refresh locally and
# redeploy the resulting JSON instead (see ui/extract_mod_icons.py-style
# provenance docs and the scraping/ scripts themselves for how).
ADMIN_REFRESH_ENABLED = os.environ.get('ADMIN_REFRESH_ENABLED', '').lower() == 'true'

CHARACTER_NAMES_PATH = os.path.join(GLOBAL_DATA_DIR, 'character_names.json')
CHARACTER_TAGS_PATH = os.path.join(GLOBAL_DATA_DIR, 'character_tags.json')

# translation from backend slot names to in-game shape names — display only,
# the backend keeps using square/arrow/diamond/triangle/circle/cross throughout
SHAPE_NAMES = {
    'square': 'Transmitter',
    'arrow': 'Receiver',
    'diamond': 'Processor',
    'triangle': 'Holo-Array',
    'circle': 'Data-Bus',
    'cross': 'Multiplexer',
}
SLOT_ORDER = ['square', 'arrow', 'diamond', 'triangle', 'circle', 'cross']
ROMAN_DOTS = {1: 'I', 2: 'II', 3: 'III', 4: 'IV', 5: 'V', 6: 'VI'}

DEFAULT_TIME_LIMIT = 60
MAX_TIME_LIMIT = 90  # hard server-side cap regardless of what a client submits

ALLY_CODE_RE = re.compile(r'^\d{9}$')

# ---------- per-visitor session state ----------
# Each visitor gets a random session_id cookie; SESSIONS holds their
# in-progress state (ally code, selections, run status/results), keyed by
# that id, entirely in-process — no Redis/DB. Deployed with a single
# gunicorn worker (see render.yaml) so every request and every background
# thread this app starts share the same process memory, which is what lets
# a background thread keep updating a visitor's status after its own
# request already returned a response. Doesn't horizontally scale past one
# instance, and state is lost on restart — acceptable for a low-traffic
# deploy; a Redis-backed store is the natural upgrade if that changes.
SESSION_COOKIE_NAME = 'sid'
SESSION_TTL_SECONDS = 6 * 60 * 60  # evict a session after 6h of inactivity

SESSIONS = {}
SESSION_LAST_SEEN = {}
SESSIONS_LOCK = threading.Lock()

# Community-data refresh status is genuinely global (one shared dataset
# used by every visitor), unlike everything in SESSIONS which is per-visitor.
REFRESH_STATE = {
    'weightings_refresh_status': 'idle',
    'weightings_refresh_error': None,
    'priority_refresh_status': 'idle',
    'priority_refresh_error': None,
}

# Only one ILP solve runs at a time — CBC is a real CPU-bound subprocess,
# and a cheap PaaS instance only has so much CPU to give it.
SOLVE_SEMAPHORE = threading.BoundedSemaphore(1)


def _new_session_state():
    return {
        'ally_code': None,
        'all_character_ids': [],
        'selected_characters': set(),
        'locked_characters': set(),
        'priority_overrides': {},
        'weight_overrides': {},
        'time_limit': DEFAULT_TIME_LIMIT,
        'setup_status': 'idle',     # idle | pulling | done | error
        'setup_error': None,
        'run_status': 'idle',       # idle | scoring | queued | solving | done | error
        'run_error': None,
        'assignments': {},
    }


def _session_dir_for(session_id):
    return os.path.join(BASE_DIR, 'data', 'sessions', session_id)


def _evict_stale_sessions():
    cutoff = time.time() - SESSION_TTL_SECONDS
    with SESSIONS_LOCK:
        stale = [sid for sid, last in SESSION_LAST_SEEN.items() if last < cutoff]
        for sid in stale:
            SESSIONS.pop(sid, None)
            SESSION_LAST_SEEN.pop(sid, None)
    for sid in stale:
        shutil.rmtree(_session_dir_for(sid), ignore_errors=True)


@app.before_request
def _load_session():
    if request.path in ('/healthz', '/robots.txt'):
        return
    sid = request.cookies.get(SESSION_COOKIE_NAME)
    is_new = not sid
    with SESSIONS_LOCK:
        if not sid or sid not in SESSIONS:
            sid = uuid.uuid4().hex
            is_new = True
            SESSIONS[sid] = _new_session_state()
        SESSION_LAST_SEEN[sid] = time.time()
    g.session_id = sid
    g.session_is_new = is_new
    g.state = SESSIONS[sid]
    g.session_dir = _session_dir_for(sid)
    # cheap lazy eviction — avoids a separate scheduler/thread for an MVP
    if random.random() < 0.01:
        _evict_stale_sessions()


@app.after_request
def _set_session_cookie(response):
    if getattr(g, 'session_is_new', False):
        response.set_cookie(
            SESSION_COOKIE_NAME, g.session_id,
            max_age=SESSION_TTL_SECONDS, httponly=True,
            secure=request.is_secure, samesite='Lax',
        )
    return response


@app.route('/healthz')
def healthz():
    """Touches nothing else — Comlink reachability, session state, template
    rendering can all be broken without this failing, so the host's health
    check isn't coupled to any of that."""
    return 'ok', 200


@app.route('/robots.txt')
def robots_txt():
    """Not meant to show up in search results — shareable-by-link only.
    Belt-and-suspenders alongside the <meta name="robots"> tag in
    base.html: some crawlers check robots.txt before ever requesting a
    page, so this stops the very first request rather than relying on
    them reading the page first."""
    return 'User-agent: *\nDisallow: /\n', 200, {'Content-Type': 'text/plain'}


_stat_calc = None
_stat_calc_lock = threading.Lock()


def get_stat_calc():
    """StatCalc fetches game data over the network on construction — build it
    once and reuse it for every request rather than once per page load."""
    global _stat_calc
    with _stat_calc_lock:
        if _stat_calc is None:
            _stat_calc = StatCalc()
    return _stat_calc


def load_character_names():
    with open(CHARACTER_NAMES_PATH) as f:
        return json.load(f)


def display_name(char_id, names=None):
    names = names or load_character_names()
    return names.get(char_id, char_id)


# Character names used to collide (e.g. GLREY and REY both showing plain
# "Rey") because character_names.json was built by guessing a
# UNIT_{id}_NAME localization key pattern instead of using each unit's own
# authoritative nameKey (see scraping/enums_slugs.py). That's fixed at the
# source now — a full scan confirms zero collisions across all 340 playable
# characters. No curated overrides needed; this dict is intentionally
# empty, kept only so build_display_names() has a hook to use if the game
# ever reintroduces a genuine shared name.
DISPLAY_NAME_DISAMBIGUATION = {}


def build_display_names(char_ids, names=None):
    """Resolve char_id -> display name for a set of characters shown
    together, disambiguating any that would otherwise collide."""
    names = names or load_character_names()
    groups = {}
    for cid in char_ids:
        groups.setdefault(names.get(cid, cid), []).append(cid)

    resolved = {}
    for name, ids in groups.items():
        if len(ids) == 1:
            resolved[ids[0]] = name
            continue

        plain_assigned = False
        extra = 1
        for cid in sorted(ids):
            if cid in DISPLAY_NAME_DISAMBIGUATION:
                resolved[cid] = DISPLAY_NAME_DISAMBIGUATION[cid]
            elif not plain_assigned:
                resolved[cid] = name
                plain_assigned = True
            else:
                extra += 1
                resolved[cid] = f'{name} ({extra})'
    return resolved


def load_my_mods(session_dir):
    _, processed_dir = session_paths(session_dir)
    with open(os.path.join(processed_dir, 'my_mods.json')) as f:
        return json.load(f)


def mod_display_name(mod):
    """Approximate in-game mod naming — exact official nomenclature not
    confirmed, this is a readable stand-in (e.g. 'Mk V Gold Health Transmitter')."""
    dots_roman = ROMAN_DOTS.get(mod.get('dots'), '')
    tier = (mod.get('tier_colour') or '').title()
    set_name = (mod.get('set') or '').replace('_', ' ').title()
    shape = SHAPE_NAMES.get(mod.get('slot'), mod.get('slot', '').title())
    return f"Mk {dots_roman} {tier} {set_name} {shape}".strip()


_DEFAULT_PROGRESS = {
    'gear': 1, 'relic_active': False, 'relic_tier': None, 'level': 1, 'rarity': 1, 'alignment': 'neutral',
    'power': 0, 'stats': {}, 'zeta_count': 0, 'omicron_count': 0,
}

# power/gear/relic/level/rarity are always sortable; stat-based options are
# whatever calculations/character_progress.py actually computed
SORT_OPTIONS = [
    ('name', 'Name'),
    ('power', 'Power'),
    ('gear', 'Gear'),
    ('relic_tier', 'Relic Tier'),
    ('level', 'Level'),
    ('rarity', 'Stars'),
    ('zeta_count', 'Zeta Count'),
    ('omicron_count', 'Omicron Count'),
    ('alignment', 'Alignment (Light first)'),
    ('alignment_dark', 'Alignment (Dark first)'),
] + [(f'stat_{s}', s) for s in SORTABLE_STATS]


def load_character_progress(session_dir):
    _, processed_dir = session_paths(session_dir)
    path = os.path.join(processed_dir, 'character_progress.json')
    if not os.path.exists(path):
        return {}
    with open(path) as f:
        return json.load(f)


def load_character_tags():
    """(tags_by_character, all_tags). all_tags is every distinct tag,
    alphabetical, flat (no grouping) — see scraping/character_tags.py for
    where these come from (swgoh.gg's own curated category list, not a
    guessed subset of Comlink's raw categoryId dump). Global reference
    data, same for every visitor."""
    if not os.path.exists(CHARACTER_TAGS_PATH):
        return {}, []
    with open(CHARACTER_TAGS_PATH) as f:
        data = json.load(f)
    return data.get('tags_by_character', {}), data.get('all_tags', [])


_ALIGNMENT_RANK = {'light': 0, 'neutral': 1, 'dark': 2}
_ALIGNMENT_RANK_DARK_FIRST = {'dark': 0, 'neutral': 1, 'light': 2}


def character_grid_data(char_ids, session_dir, names=None, progress=None, tags_by_character=None):
    names = names or load_character_names()
    progress = progress if progress is not None else load_character_progress(session_dir)
    if tags_by_character is None:
        tags_by_character, _ = load_character_tags()
    resolved = build_display_names(char_ids, names)

    chars = []
    for cid in char_ids:
        p = progress.get(cid, _DEFAULT_PROGRESS)
        name = resolved[cid]
        stats = p.get('stats') or {}
        alignment = p['alignment']

        sort_values = {
            'name': name.lower(),
            'power': p.get('power') or 0,
            'gear': p['gear'],
            'relic_tier': p['relic_tier'] if p['relic_tier'] is not None else -1,
            'level': p['level'],
            'rarity': p['rarity'],
            'zeta_count': p.get('zeta_count') or 0,
            'omicron_count': p.get('omicron_count') or 0,
            'alignment': _ALIGNMENT_RANK.get(alignment, 1),
            'alignment_dark': _ALIGNMENT_RANK_DARK_FIRST.get(alignment, 1),
        }
        for stat_name in SORTABLE_STATS:
            sort_values[f'stat_{stat_name}'] = stats.get(stat_name, 0)

        chars.append({
            'id': cid,
            'name': name,
            'gear': p['gear'],
            'gear_ring': p['gear'],
            'relic_active': p['relic_active'],
            'relic_tier': p['relic_tier'],
            'level': p['level'],
            'rarity': p['rarity'],
            'alignment': alignment,
            'power': p.get('power') or 0,
            'stats': stats,
            'zeta_count': p.get('zeta_count') or 0,
            'omicron_count': p.get('omicron_count') or 0,
            'tags': tags_by_character.get(cid, []),
            'sort_values': sort_values,
        })
    chars.sort(key=lambda c: c['name'].lower())
    return chars


# StatCalc's `final` stats dict stores these as fractions (1.5 = 150% crit
# damage, 0.15 = 15% crit chance), not percentage points — display-only
# conversion, doesn't touch the underlying value used anywhere else. Armor
# and Resistance are stored the same fractional way, so they're included
# here too even though only the other four were explicitly asked for —
# leaving them as raw fractions next to properly-formatted percentages
# would look broken.
PERCENT_STATS = {
    'Armor', 'Resistance', 'Potency', 'Tenacity',
    'Physical Critical Chance', 'Special Critical Chance', 'Critical Damage',
}


def fmt(value, is_percent=False):
    if is_percent:
        return f'{value * 100:.2f}%'
    if abs(value - round(value)) < 0.005:
        return str(round(value))
    return f'{value:.2f}'


def build_stat_rows(stats):
    """One row per stat: total value plus the isolated mod contribution,
    for both before and after — e.g. Speed 210 (+59). Rows where neither
    side has a mod contribution are still shown (total only, no bracket)."""
    overall = stats['overall_stats']
    modded = stats['modded_stats']
    stat_names = sorted(set(overall['before']) | set(overall['after']))

    rows = []
    for name in stat_names:
        is_pct = name in PERCENT_STATS
        rows.append({
            'name': name,
            'before_total': fmt(overall['before'].get(name, 0), is_pct),
            'before_mod': fmt(modded['before'][name], is_pct) if modded['before'].get(name) else None,
            'after_total': fmt(overall['after'].get(name, 0), is_pct),
            'after_mod': fmt(modded['after'][name], is_pct) if modded['after'].get(name) else None,
        })
    return rows


# ---------- 1. setup ----------

@app.route('/')
def index():
    _, processed_dir = session_paths(g.session_dir)
    has_existing_data = os.path.exists(os.path.join(processed_dir, 'my_mods.json'))
    return render_template('setup.html', has_existing_data=has_existing_data)


def _finalize_selection_state(state, session_dir):
    """Shared by both the fresh-pull and use-existing-data paths — resets
    everything downstream of "which characters exist" so a re-setup
    doesn't leave a stale selection/run behind from a previous pull."""
    my_mods = load_my_mods(session_dir)
    state['all_character_ids'] = sorted(set(m['character'] for m in my_mods))
    state['selected_characters'] = set()
    state['locked_characters'] = set()
    state['priority_overrides'] = {}
    state['weight_overrides'] = {}
    state['run_status'] = 'idle'
    state['run_error'] = None
    state['assignments'] = {}


def _pull_roster(state, session_dir, ally_code):
    """Runs in a background thread — same reasoning as _run_solve: `state`
    and `session_dir` are handed in directly rather than looked up by
    session_id from inside the thread. This used to run synchronously
    inside the /setup request itself (fetch mods + fetch gear + compute
    stats for the whole roster, all before responding) — fine on a fast
    local machine, but on a slower/free-tier deployment it was taking long
    enough that the platform's own front-end proxy gave up and returned a
    502 before the app ever got to respond, independent of anything our
    own gunicorn timeout setting controls."""
    try:
        state['setup_status'] = 'pulling'
        ensure_comlink_running()
        fetch_user_mod_data(ally_code, session_dir=session_dir)
        fetch_gear_levels(ally_code, session_dir=session_dir)
        try:
            build_character_progress(session_dir=session_dir, calc=get_stat_calc())
        except Exception:
            # Non-essential (drives gear/relic rings + sort stats only) —
            # character_grid_data() already falls back gracefully via
            # _DEFAULT_PROGRESS, so don't fail the whole pull over it.
            print(f"Warning: build_character_progress failed:\n{traceback.format_exc()}")

        state['ally_code'] = ally_code
        _finalize_selection_state(state, session_dir)
        state['setup_status'] = 'done'
    except Exception as exc:
        state['setup_error'] = f'{exc}\n{traceback.format_exc()}'
        state['setup_status'] = 'error'


@app.route('/setup', methods=['POST'])
@limiter.limit('10 per minute')
def setup():
    state = g.state
    ally_code = request.form.get('ally_code', '').strip().replace('-', '').replace(' ', '')
    use_existing = request.form.get('use_existing') == '1'

    _, processed_dir = session_paths(g.session_dir)
    mods_path = os.path.join(processed_dir, 'my_mods.json')

    if use_existing:
        if not os.path.exists(mods_path):
            return render_template('setup.html', has_existing_data=False,
                                    error='No mod data found yet — enter an ally code to pull your roster.')
        _finalize_selection_state(state, g.session_dir)
        return redirect(url_for('select_characters'))

    if not ally_code:
        return render_template('setup.html', has_existing_data=os.path.exists(mods_path),
                                error='Enter an ally code, or choose to use existing data.')
    if not ALLY_CODE_RE.match(ally_code):
        return render_template('setup.html', has_existing_data=os.path.exists(mods_path),
                                error='Ally code should be 9 digits (e.g. 123456789).')

    state['setup_status'] = 'pulling'
    state['setup_error'] = None
    thread = threading.Thread(target=_pull_roster, args=(state, g.session_dir, ally_code), daemon=True)
    thread.start()
    return render_template('pulling.html')


@app.route('/setup/status')
def setup_status():
    state = g.state
    return jsonify({'status': state['setup_status'], 'error': state['setup_error']})


# ---------- 2. character selection ----------

@app.route('/select-characters', methods=['GET', 'POST'])
def select_characters():
    state = g.state
    if not state['all_character_ids']:
        return redirect(url_for('index'))

    if request.method == 'POST':
        selected = set()
        locked = set()
        for char_id in state['all_character_ids']:
            char_state = request.form.get(f'state_{char_id}', 'none')
            if char_state in ('selected', 'locked'):
                selected.add(char_id)
            if char_state == 'locked':
                locked.add(char_id)

        if not selected:
            names = load_character_names()
            chars = character_grid_data(state['all_character_ids'], g.session_dir, names)
            _, all_tags = load_character_tags()
            return render_template('select_characters.html', characters=chars, error='Select at least one character.',
                                    selected=selected, locked=locked, sort_options=SORT_OPTIONS, all_tags=all_tags)

        state['selected_characters'] = selected
        state['locked_characters'] = locked
        return redirect(url_for('config'))

    names = load_character_names()
    chars = character_grid_data(state['all_character_ids'], g.session_dir, names)
    _, all_tags = load_character_tags()
    return render_template('select_characters.html', characters=chars, error=None,
                            selected=state['selected_characters'], locked=state['locked_characters'],
                            sort_options=SORT_OPTIONS, all_tags=all_tags)


# ---------- 3. weighting / priority config ----------

@app.route('/config', methods=['GET', 'POST'])
def config():
    state = g.state
    if not state['selected_characters']:
        return redirect(url_for('select_characters'))

    names = load_character_names()
    selected_chars = character_grid_data(state['selected_characters'], g.session_dir, names)

    if request.method == 'POST':
        priority_overrides = {}
        priority_chars = request.form.getlist('priority_char')
        priority_values = request.form.getlist('priority_value')
        for char_id, value in zip(priority_chars, priority_values):
            if char_id and value:
                try:
                    priority_overrides[char_id] = max(0.0, min(1.0, float(value)))
                except ValueError:
                    pass

        weight_overrides = {}
        weight_file = request.files.get('weight_file')
        if weight_file and weight_file.filename:
            try:
                weight_overrides = json.load(weight_file.stream)
            except (json.JSONDecodeError, UnicodeDecodeError):
                return render_template('config.html', characters=selected_chars,
                                        error='Weight override file is not valid JSON.',
                                        admin_refresh_enabled=ADMIN_REFRESH_ENABLED)

        try:
            time_limit = int(request.form.get('time_limit') or DEFAULT_TIME_LIMIT)
        except ValueError:
            time_limit = DEFAULT_TIME_LIMIT

        state['priority_overrides'] = priority_overrides
        state['weight_overrides'] = weight_overrides
        state['time_limit'] = max(5, min(MAX_TIME_LIMIT, time_limit))
        # reset so /run actually kicks off a fresh solve rather than
        # showing whatever the previous run left behind (re-modding flow)
        state['run_status'] = 'idle'
        state['run_error'] = None
        state['assignments'] = {}

        return redirect(url_for('run'))

    return render_template('config.html', characters=selected_chars, error=None,
                            admin_refresh_enabled=ADMIN_REFRESH_ENABLED)


# ---------- 3b. refresh data-driven sources ----------
# Both of these are slow (minutes), hit external services (Comlink for
# weightings, Selenium/swgoh.gg for priority — the latter can also be
# fragile, see the project handoff notes on Cloudflare), and operate on
# shared community data, not anything visitor-specific. Gated off in
# production (ADMIN_REFRESH_ENABLED) — refresh locally, redeploy the
# resulting JSON. Run in the background with polling rather than blocking
# the request when enabled.

def _refresh_weightings():
    try:
        REFRESH_STATE['weightings_refresh_status'] = 'running'
        from scraping.GAC_leaderboards import fetch_all_kyber_divisions
        from scraping.top250_player_mods import fetch_top250_player_mods
        from scraping.unit_base_speed import fetch_all_base_speeds
        from calculations.max_possible_stats import save_max_possible_stats
        from calculations.mod_weightings import build_mod_weightings

        fetch_all_kyber_divisions()
        fetch_top250_player_mods()
        fetch_all_base_speeds()
        save_max_possible_stats()
        build_mod_weightings()
        REFRESH_STATE['weightings_refresh_status'] = 'done'
    except Exception as exc:
        REFRESH_STATE['weightings_refresh_error'] = f'{exc}\n{traceback.format_exc()}'
        REFRESH_STATE['weightings_refresh_status'] = 'error'


def _refresh_priority():
    try:
        REFRESH_STATE['priority_refresh_status'] = 'running'
        from scraping.enums_slugs import run_full_pipeline
        from scraping.character_priority_rankings import run_priority_scrape

        run_full_pipeline()
        run_priority_scrape()
        REFRESH_STATE['priority_refresh_status'] = 'done'
    except Exception as exc:
        REFRESH_STATE['priority_refresh_error'] = f'{exc}\n{traceback.format_exc()}'
        REFRESH_STATE['priority_refresh_status'] = 'error'


@app.route('/refresh/weightings', methods=['POST'])
def refresh_weightings():
    if not ADMIN_REFRESH_ENABLED:
        abort(404)
    if REFRESH_STATE['weightings_refresh_status'] != 'running':
        REFRESH_STATE['weightings_refresh_error'] = None
        threading.Thread(target=_refresh_weightings, daemon=True).start()
    return redirect(url_for('config'))


@app.route('/refresh/weightings/status')
def refresh_weightings_status():
    if not ADMIN_REFRESH_ENABLED:
        abort(404)
    return jsonify({'status': REFRESH_STATE['weightings_refresh_status'], 'error': REFRESH_STATE['weightings_refresh_error']})


@app.route('/refresh/priority', methods=['POST'])
def refresh_priority():
    if not ADMIN_REFRESH_ENABLED:
        abort(404)
    if REFRESH_STATE['priority_refresh_status'] != 'running':
        REFRESH_STATE['priority_refresh_error'] = None
        threading.Thread(target=_refresh_priority, daemon=True).start()
    return redirect(url_for('config'))


@app.route('/refresh/priority/status')
def refresh_priority_status():
    if not ADMIN_REFRESH_ENABLED:
        abort(404)
    return jsonify({'status': REFRESH_STATE['priority_refresh_status'], 'error': REFRESH_STATE['priority_refresh_error']})


# ---------- 4. run ----------

def _run_solve(state, session_dir):
    """Runs in a background thread — `state` and `session_dir` are handed
    in directly at thread-start rather than looked up by session_id from
    inside the thread, so a session-eviction sweep racing this can't pull
    the rug out from under it."""
    try:
        state['run_status'] = 'scoring'
        build_mod_scores(list(state['selected_characters']), weight_overrides=state['weight_overrides'], session_dir=session_dir)

        state['run_status'] = 'queued'
        acquired = SOLVE_SEMAPHORE.acquire(timeout=300)
        if not acquired:
            state['run_error'] = 'The optimizer is busy with another request — please try again shortly.'
            state['run_status'] = 'error'
            return
        try:
            state['run_status'] = 'solving'
            assignments = solve(
                selected_characters=state['selected_characters'],
                locked_characters=state['locked_characters'],
                priority_overrides=state['priority_overrides'],
                time_limit=state['time_limit'],
                session_dir=session_dir,
            )
        finally:
            SOLVE_SEMAPHORE.release()

        state['assignments'] = assignments
        state['run_status'] = 'done'
    except Exception as exc:
        state['run_error'] = f'{exc}\n{traceback.format_exc()}'
        state['run_status'] = 'error'


@app.route('/run')
@limiter.limit('10 per minute')
def run():
    state = g.state
    if not state['selected_characters']:
        return redirect(url_for('select_characters'))

    if state['run_status'] == 'idle':
        state['run_status'] = 'scoring'
        thread = threading.Thread(target=_run_solve, args=(state, g.session_dir), daemon=True)
        thread.start()

    return render_template('running.html')


@app.route('/run/status')
def run_status():
    state = g.state
    return jsonify({'status': state['run_status'], 'error': state['run_error']})


# ---------- 5 & 6. results ----------

@app.route('/results')
def results():
    state = g.state
    if state['run_status'] != 'done':
        return redirect(url_for('run'))

    # locked characters keep their exact current mods (solver.py forces
    # this) — they're still passed into solve() so their mods are reserved
    # and unavailable to everyone else, so they show up in
    # state['assignments'] same as any actually-remodded character. But
    # nothing about their own loadout changed, so listing them here read as
    # "these got remodded too", which was misleading.
    remodded_ids = [cid for cid in state['assignments'] if cid not in state['locked_characters']]
    chars = character_grid_data(remodded_ids, g.session_dir)
    mod_counts = {cid: len(mods) for cid, mods in state['assignments'].items()}
    for c in chars:
        c['mod_count'] = mod_counts[c['id']]

    return render_template('results.html', characters=chars)


@app.route('/results/<char_id>')
def character_detail(char_id):
    state = g.state
    if state['run_status'] != 'done':
        return redirect(url_for('run'))

    names = load_character_names()
    new_mod_ids = state['assignments'].get(char_id, [])

    roster = load_raw_roster(g.session_dir)
    unit_lookup = build_unit_lookup(roster)
    raw_mod_lookup = build_raw_mod_lookup(roster)
    unit = unit_lookup.get(char_id)

    if unit is None:
        return render_template('character_detail.html', name=display_name(char_id, names),
                                char_id=char_id, stat_rows=None, mods=[],
                                error='No roster data found for this character (stale roster pull?).')

    calc = get_stat_calc()
    stats = build_character_stat_report(calc, unit, new_mod_ids, raw_mod_lookup)
    stat_rows = build_stat_rows(stats)

    my_mods = load_my_mods(g.session_dir)
    mods_by_id = {m['mod_id']: m for m in my_mods}
    mods_by_slot = {}
    for mod_id in new_mod_ids:
        mod = mods_by_id.get(mod_id)
        if mod:
            mods_by_slot[mod['slot']] = {**mod, 'display_name': mod_display_name(mod)}

    mod_cards = [{'slot': slot, 'shape_name': SHAPE_NAMES[slot], 'mod': mods_by_slot.get(slot)}
                 for slot in SLOT_ORDER]

    return render_template('character_detail.html', name=display_name(char_id, names),
                            char_id=char_id, stat_rows=stat_rows, mods=mod_cards, error=None)


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
