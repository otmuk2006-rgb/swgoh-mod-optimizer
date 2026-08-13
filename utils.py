import hashlib
import hmac as hmac_lib
import os
import subprocess
import time
from json import dumps

from swgoh_comlink import SwgohComlink
from swgoh_comlink._base import SwgohComlinkBase

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# swgoh_comlink's own _construct_request_headers signs an empty dict payload
# (e.g. get_game_metadata() with no args, which sends payload={}) as if the
# body were the JSON string "" — but the actual request body httpx sends for
# a non-GET call is "{}" (see swgoh_comlink.py's `_request`, which always
# sets request_kwargs["json"] = payload for non-GET, no truthiness check).
# That mismatch makes Comlink's own HMAC check reject every request with a
# legitimately-empty-but-present dict payload, even with fully correct
# ACCESS_KEY/SECRET_KEY on both ends. Only line changed from upstream:
# `if payload:` -> `if payload is not None:`, matching what's actually sent.
def _patched_construct_request_headers(self, method, endpoint, payload=None):
    req_headers = {}
    if self.hmac:
        req_time = str(int(time.time() * 1000))
        req_headers = {"X-Date": f"{req_time}"}
        hmac_obj = hmac_lib.new(key=self.secret_key.encode(), digestmod=hashlib.sha256)
        hmac_obj.update(req_time.encode())
        hmac_obj.update(method.upper().encode())
        hmac_obj.update(f"/{endpoint}".encode())
        if payload is not None:
            payload_string = dumps(payload, separators=(",", ":"))
        else:
            payload_string = dumps("")
        payload_hash_digest = hashlib.md5(payload_string.encode()).hexdigest()
        hmac_obj.update(payload_hash_digest.encode())
        hmac_digest = hmac_obj.hexdigest()
        req_headers["Authorization"] = f"HMAC-SHA256 Credential={self.access_key},Signature={hmac_digest}"
    return req_headers


SwgohComlinkBase._construct_request_headers = _patched_construct_request_headers

# Global reference/community data (character names & tags, mod weightings,
# character priority, ...) — the same for every visitor, read-only at
# request time. Distinct from session_paths() below, which is per-user.
GLOBAL_DATA_DIR = os.path.join(BASE_DIR, 'data', 'processed')
GLOBAL_RAW_DIR = os.path.join(BASE_DIR, 'data', 'raw')

# In production this points at a sibling Comlink service, set via env var —
# on Render specifically, that's wired up in render.yaml via `fromService` /
# `hostport`, which per Render's own private-network docs may or may not
# include a URL scheme depending on how it resolves (their own docs example
# shows a bare "host:port" and note you may need to add the protocol
# yourself) — normalize it here so either shape works, rather than betting
# on one. Locally it defaults to the Windows .exe this file can also
# auto-start.
_raw_comlink_url = os.environ.get('COMLINK_URL', 'http://localhost:3000')
COMLINK_URL = _raw_comlink_url if '://' in _raw_comlink_url else f'http://{_raw_comlink_url}'
COMLINK_START_SCRIPT = os.path.join(BASE_DIR, "comlink", "start_comlink.bat")


def session_paths(session_dir=None):
    """(raw_dir, processed_dir) for one visitor's own roster/mod/run data —
    creates them if missing. `session_dir` is an absolute per-visitor
    directory the web app allocates per session (see ui/app.py); when None
    (the CLI entry point in main.py, and each module's own `if __name__ ==
    "__main__":` block), this resolves to the same data/raw + data/processed
    layout this project has always used, so local single-user usage is
    unchanged."""
    base = session_dir or os.path.join(BASE_DIR, 'data')
    raw_dir = os.path.join(base, 'raw')
    processed_dir = os.path.join(base, 'processed')
    os.makedirs(raw_dir, exist_ok=True)
    os.makedirs(processed_dir, exist_ok=True)
    return raw_dir, processed_dir


def get_comlink_client():
    """The one place a SwgohComlink client gets constructed — every call
    site in the app should go through this instead of bare SwgohComlink(),
    so COMLINK_URL only has to be correct in one place. ACCESS_KEY/
    SECRET_KEY are picked up automatically from the environment by the
    client itself if set (see swgoh_comlink._base.SwgohComlinkBase)."""
    return SwgohComlink(url=COMLINK_URL)


_last_comlink_error = None


def _comlink_is_up():
    """Must go through get_comlink_client(), not a raw httpx call — once
    ACCESS_KEY/SECRET_KEY are set (see render.yaml), Comlink requires every
    request to be HMAC-signed, including this health check. An unsigned
    ping gets rejected same as any other unsigned request, which made this
    always report "down" in production even with Comlink perfectly
    healthy — ensure_comlink_running() would then wait out its full
    timeout and raise, turning into a 500 on every /setup.

    Stashes the actual exception in _last_comlink_error — swallowing it
    entirely (just returning False) made every failure mode look
    identical from the outside ("not reachable"), whether the real cause
    was DNS, a timeout, an HTTP error status, or a signature rejection.
    ensure_comlink_running() surfaces this in its own error message."""
    global _last_comlink_error
    try:
        get_comlink_client().get_game_metadata()
        return True
    except Exception as exc:
        _last_comlink_error = f'{type(exc).__name__}: {exc}'
        return False


def ensure_comlink_running(timeout=20):
    """Make sure Comlink is reachable at COMLINK_URL.

    Locally on Windows, if it's not up yet, auto-start the bundled .exe via
    start_comlink.bat — this only ever makes sense on the developer's own
    machine. Anywhere else (production, Linux, containers), Comlink is a
    separately-managed always-on sibling service; there's nothing local to
    start, so just wait and fail with a clear message if it never comes up
    rather than trying to spawn a Windows batch file that can't exist there."""
    if _comlink_is_up():
        return

    if os.name == 'nt' and os.path.exists(COMLINK_START_SCRIPT):
        print("swgoh-comlink not running, starting it...")
        subprocess.run([COMLINK_START_SCRIPT], shell=True, check=True)
    else:
        print(f"Waiting for Comlink at {COMLINK_URL}...")

    deadline = time.time() + timeout
    while time.time() < deadline:
        if _comlink_is_up():
            print("swgoh-comlink is up.")
            return
        time.sleep(0.5)

    raise RuntimeError(
        f"Comlink not reachable at {COMLINK_URL} after {timeout}s "
        f"(last error: {_last_comlink_error}). "
        "If this is a production deploy, check the Comlink service is running and COMLINK_URL is set correctly."
    )
