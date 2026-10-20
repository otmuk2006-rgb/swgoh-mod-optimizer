# SWGOH Mod Optimiser

**Live demo:** https://swgoh-mod-optimizer.onrender.com
*(hosted on a free tier, so the first load after a quiet period can take a minute or two while the servers wake up)*

**Try it with my account — ally code `846-927-846`**

A web app that reassigns every mod across a *Star Wars: Galaxy of Heroes* roster at once, by formulating the problem as an **integer linear program (ILP)** and solving it exactly. The weights the ILP optimises against are not hand-written config: they are **inferred from what the top ~250 Grand Arena players actually equip**, and character importance is inferred from community tier data.

---

## The problem

In SWGOH every character equips six *mods* (one per slot: square, arrow, diamond, triangle, circle, cross). Each mod has a primary stat, up to four secondary stats, and belongs to a *set*; equipping 2 or 4 mods of the same set grants a bonus (e.g. 4 Speed mods = +10% base speed). A serious account owns hundreds of characters and thousands of mods.

Existing tools optimise **one character at a time**: give the best mods to character A, then the best of what's left to character B, and so on. That greedy approach is order-dependent and can be badly sub-optimal — the perfect arrow for your 3rd character may already have been taken by your 1st, who only needed it slightly.

This project instead treats it as a single **global assignment problem**: choose which mod goes on which character, for every character simultaneously, to maximise total roster value.

## How it works

```
 Comlink (official game API)            swgoh.gg tier pages
          │                                     │
          ▼                                     ▼
 Top ~250 Kyber GAC players' mods      Per-character meta tiers
          │                                     │
          ▼                                     ▼
  Stat weightings  W_j                 Character priority  p_j
          │                                     │
          └──────────────┬──────────────────────┘
                         ▼
   Your roster + mods ─► score(i, j) for every mod i × character j
                         ▼
               ILP (PuLP + CBC solver)
                         ▼
     Optimal assignment + before/after report
```

### 1. Learning what each character wants — stat weightings `W_j`

Rather than hard-coding "Darth Vader wants speed and offense", the weightings are learned from data:

1. Pull the GAC leaderboards for the top 50 players in each of the 5 Kyber divisions (~250 accounts) via [Comlink](https://github.com/swgoh-utils/swgoh-comlink) ([scraping/GAC_leaderboards.py](scraping/GAC_leaderboards.py)).
2. Download every mod those players have equipped ([scraping/top250_player_mods.py](scraping/top250_player_mods.py)) and decode Comlink's raw stat encoding.
3. For each account × character, sum all mod stats, **including completed set bonuses** — bonus strength depends on whether the mods are level 15 (full bonus) or not (half bonus), and the speed set is converted from a percentage of that character's base speed into a flat number.
4. Average those totals per character across all accounts.
5. Normalise each stat by the **highest average observed for any character** — so the character that stacks the most speed on average gets a speed weight of exactly 1.0, and everyone else is relative to that real, achieved benchmark ([calculations/mod_weightings.py](calculations/mod_weightings.py)).

### 2. How much each character matters — priority `p_j`

When two characters want the same mod, the solver needs to know who matters more. Priority comes from swgoh.gg's per-character meta pages (tier as a leader and as a squad member), mapped to a score — S = 1.0, A = 0.8, B = 0.6, C = 0.4, D = 0.2 — and taking the better of the two roles ([scraping/character_priority_rankings.py](scraping/character_priority_rankings.py)). Characters below gear 13 are floored to 0.1, and unowned characters get 0. Users can override any priority in the UI.

### 3. Scoring every mod for every character

For mod `i` and character `j` ([calculations/mod_score.py](calculations/mod_score.py)):

$$\text{score}(i,j) = \sum_{s \in \text{stats}(i)} \frac{\text{value}_{i,s}}{\text{max}_s} \cdot W_{j,s}$$

where `max_s` is the highest value that stat can roll on a mod (speed uses a per-character maximum, since it depends on base speed). Set bonuses are scored separately as `B_{k,j}` — the value of completing set `k` on character `j`, at full and at half strength.

### 4. The integer linear program

Implemented with [PuLP](https://coin-or.github.io/pulp/) and solved by the CBC branch-and-bound solver ([optimiser/solver.py](optimiser/solver.py)).

**Decision variables**
- `x_ij ∈ {0,1}` — mod `i` is assigned to character `j`
- `z_jk^full`, `z_jk^min ∈ {0,1}` — character `j` completes set `k` at full / half strength

**Objective**

$$\max \sum_{i,j} p_j \cdot \text{score}(i,j) \cdot x_{ij} \;+\; \sum_{j,k} p_j \left( B^{full}_{k,j}\, z^{full}_{jk} + B^{min}_{k,j}\, z^{min}_{jk} \right)$$

**Constraints**
- Each mod goes to at most one character: `Σ_j x_ij ≤ 1`
- Each character gets at most one mod per slot: `Σ_{i ∈ slot} x_ij ≤ 1`
- A set bonus can only be claimed if enough mods of that set are equipped (2 or 4 depending on the set): `Σ_{i ∈ set k} x_ij ≥ required_k · z_jk` — and the *full* bonus only counts level-15 mods
- A character can't claim both the full and half bonus for the same set: `z^full + z^min ≤ 1`
- 6-dot mods can't be equipped below gear 12 (enforced by never creating those variables)

**Locked characters** — users can lock characters whose mods should not move. Rather than adding variables and pinning them, locked characters and their mods are removed from the model entirely before it's built. This gives the same optimum but, on a 60-character / 20-locked test, ~39% fewer variables and a ~2.2× faster solve.

Solves are time-limited (60 s default, 90 s cap on the server); if the limit is hit, CBC returns the best solution found so far.

### 5. Evaluating the result

The results page shows, for each character, which mods moved where and the before/after stats (computed with Comlink's `StatCalc`). It also reports an **average "mod fit"** across the roster — the cosine similarity between each character's total mod-stat vector and their learned weighting `W_j`, measuring whether their mods have the *right shape* of stats regardless of magnitude ([calculations/reporting.py](calculations/reporting.py)). This is deliberately only an evaluation metric: a cosine objective isn't linear, so it can't drive the ILP directly.

## The web app

A Flask app ([ui/app.py](ui/app.py)) walks through six steps, shown as a clickable breadcrumb:

1. **Setup** — enter an ally code; the app pulls that roster and its mods live from Comlink
2. **Select characters** — searchable/filterable portrait grid (by faction tag, gear, relic, power, stats)
3. **Config** — tweak per-character stat weightings or priorities, lock characters, set the solver time limit
4. **Run** — the ILP solves in a background thread while the page polls for status
5. **Results** — roster overview with the before/after mod-fit score
6. **Character detail** — that character's new mods and before/after stats

Engineering notes:
- **Per-visitor sessions** — each visitor gets their own data directory and in-memory state; only one CPU-heavy solve runs at a time
- **Rate limiting** with Flask-Limiter, and a hard server-side cap on solver time
- **Deployment** — two services on Render ([render.yaml](render.yaml)): the Flask app under gunicorn, and the official Comlink Docker image, with Comlink's HMAC request signing turned on so only this app can query it
- Community data (weightings, priorities, images) is refreshed **offline** and committed as JSON, since the priority scrape drives a real Chrome browser and shouldn't run on a public server

## Running it locally

**Requirements:** Python 3 and [Docker](https://www.docker.com/) (for Comlink).

1. **Start Comlink** — the game-data API the app talks to:
   ```bash
   docker run -d --name swgoh-comlink -p 3000:3000 \
     -e APP_NAME=swgoh-mod-optimizer \
     ghcr.io/swgoh-utils/swgoh-comlink:latest
   ```
   The app expects it at `http://localhost:3000`; set the `COMLINK_URL` environment variable to point elsewhere.

2. **Install dependencies:**
   ```bash
   git clone https://github.com/otmuk2006-rgb/swgoh-mod-optimizer.git
   cd swgoh-mod-optimizer
   python -m venv venv
   source venv/bin/activate        # Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. **Run the web app** (from the repo root):
   ```bash
   python ui/app.py
   ```
   Open http://localhost:5000 and enter an ally code — e.g. mine, `846927846`.

### Command-line version

`python main.py` runs the same pipeline in the terminal: it asks for an ally code and lets you pick characters, weightings and locks interactively, then writes the result to `data/processed/final_assignment.json`.

### Refreshing the community data (optional, slow)

The committed JSON in `data/processed/` is enough to run the app. To rebuild it from scratch, answer `y` to the refresh prompt in `python main.py`. This re-downloads the top-250 players' mods (several minutes) and re-scrapes swgoh.gg with Selenium, which needs Google Chrome installed and can be blocked by swgoh.gg's Cloudflare protection.

## Project structure

```
scraping/       Data collection — Comlink (rosters, mods, leaderboards) and swgoh.gg (tiers, tags)
calculations/   Stat weightings, mod scores, character stats, before/after reporting
optimiser/      The ILP model and solver settings
ui/             Flask app, templates, JS, CSS, and character/mod images
data/processed/ Pre-computed community data the app reads at runtime
utils.py        Comlink client setup and per-session data paths
main.py         Command-line entry point
render.yaml     Deployment config
```

## Limitations and possible next steps

- The weighting sample is the top ~250 Kyber players — the most the GAC leaderboard endpoint exposes — rather than a broader top-1000.
- Priority is per-character, not per-team. I worked out a team-level priority model (scoring whole squads from GAC usage with Bayesian shrinkage), but swgoh.gg's squad pages are image-based and behind stronger Cloudflare protection, and Comlink doesn't expose battle history, so there was no data source to build it on.
- Session state is held in memory on a single worker. That's fine for current traffic; a Redis-backed store would be the next step to scale out.
