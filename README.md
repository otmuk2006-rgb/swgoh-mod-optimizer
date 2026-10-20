# SWGOH Mod Optimiser

Live demo: https://swgoh-mod-optimizer.onrender.com

The demo is hosted on Render's free tier. The first request after a period of inactivity can take one to two minutes.

Example ally code (my account): `846-927-846`

## Overview

This project assigns mods to characters in *Star Wars: Galaxy of Heroes* (SWGOH). It optimises the whole roster at once by formulating the assignment as an integer linear program (ILP). The stat preferences used in the objective are estimated from the mods equipped by the top Grand Arena (GAC) players. Character importance is estimated from community tier ratings.

## Problem

Each character in SWGOH equips six mods, one per slot. A mod has a primary stat, up to four secondary stats, and a set type. Equipping two or four mods of the same set gives a set bonus. A developed account has several hundred characters and several thousand mods.

Existing tools optimise characters one at a time. The first character receives the best available mods, then the second character chooses from the remainder, and so on. The result depends on the order of characters and is generally not optimal. This project solves a single assignment problem over all selected characters instead.

## Method

The pipeline has five stages.

1. Estimate stat weightings `W_j` for each character from top players' mods.
2. Estimate a priority `p_j` for each character from tier ratings.
3. Score every mod for every character.
4. Solve the ILP.
5. Report the change in stats and mod fit.

### 1. Stat weightings

The weightings are estimated from data, not set by hand ([calculations/mod_weightings.py](calculations/mod_weightings.py)).

1. The top 50 players in each of the five Kyber divisions are taken from the GAC leaderboards (about 250 accounts). The data is accessed through [Comlink](https://github.com/swgoh-utils/swgoh-comlink), an API for SWGOH game data ([scraping/GAC_leaderboards.py](scraping/GAC_leaderboards.py)).
2. All mods equipped by these players are downloaded and decoded ([scraping/top250_player_mods.py](scraping/top250_player_mods.py)).
3. For each account and character, the stats of all six mods are summed. Completed set bonuses are included. A set gives its full bonus if its mods are level 15 and half the bonus otherwise. The speed set bonus is a percentage of base speed, so it is converted to a flat value for each character.
4. The totals are averaged across accounts for each character.
5. Each stat is divided by the highest average for that stat across all characters. The character with the highest average speed therefore has a speed weight of 1.0.

### 2. Character priority

When two characters compete for the same mod, the solver uses priority to decide between them. Priorities are taken from the swgoh.gg meta page of each character ([scraping/character_priority_rankings.py](scraping/character_priority_rankings.py)). Each page gives a tier for the character as a leader and as a squad member. The higher of the two is converted to a score:

| Tier | S | A | B | C | D |
|---|---|---|---|---|---|
| `p_j` | 1.0 | 0.8 | 0.6 | 0.4 | 0.2 |

Characters below gear 13 receive a priority of 0.1. Characters the player does not own receive 0. The user can override any priority.

### 3. Mod scores

The score of mod `i` for character `j` is ([calculations/mod_score.py](calculations/mod_score.py)):

$$\text{score}(i,j) = \sum_{s \in \text{stats}(i)} \frac{\text{value}_{i,s}}{\text{max}_s} \cdot W_{j,s}$$

Here `max_s` is the highest value stat `s` can have on a mod. For speed, the maximum depends on the character's base speed. The value of set bonuses is computed separately. `B_kj` is the value to character `j` of completing set `k`, at full or half strength.

### 4. Integer linear program

The model is built with [PuLP](https://coin-or.github.io/pulp/) and solved with the CBC solver ([optimiser/solver.py](optimiser/solver.py)).

Decision variables:

- `x_ij ∈ {0,1}`: mod `i` is assigned to character `j`.
- `z_jk^full, z_jk^min ∈ {0,1}`: character `j` completes set `k` at full or half strength.

Objective:

$$\max \sum_{i,j} p_j \cdot \text{score}(i,j) \cdot x_{ij} \;+\; \sum_{j,k} p_j \left( B^{full}_{k,j}\, z^{full}_{jk} + B^{min}_{k,j}\, z^{min}_{jk} \right)$$

Constraints:

- Each mod is assigned to at most one character: `Σ_j x_ij ≤ 1`.
- Each character has at most one mod per slot: `Σ_{i ∈ slot} x_ij ≤ 1`.
- A set bonus requires enough mods of that set (two or four): `Σ_{i ∈ set k} x_ij ≥ required_k · z_jk`. Only level 15 mods count towards the full bonus.
- A character cannot claim both bonuses for the same set: `z^full + z^min ≤ 1`.
- Six-dot mods require gear 12. Variables for invalid pairs are not created.

The user can lock characters so that their mods do not change. Locked characters and their mods are removed before the model is built. This gives the same optimum as constraining the variables. In a test with 60 characters, 20 of them locked, it reduced the number of variables by about 39% and the solve time by a factor of about 2.2.

The solve has a time limit of 60 seconds by default, capped at 90 seconds on the server. If the limit is reached, CBC returns the best solution found so far.

### 5. Evaluation

The results page lists the mods that moved and each character's stats before and after. Stats are computed with Comlink's `StatCalc`. The page also reports the average mod fit of the roster ([calculations/reporting.py](calculations/reporting.py)). Mod fit is the cosine similarity between a character's total mod stats and their weighting vector `W_j`. It measures whether the mix of stats is correct, independent of their size. Cosine similarity is not linear, so it is used only for evaluation and not in the objective.

## Web application

The Flask app ([ui/app.py](ui/app.py)) has six steps:

1. Setup: enter an ally code. The roster and mods are loaded from Comlink.
2. Character selection: a grid of characters with filters for faction, gear, relic, power and stats.
3. Configuration: edit weightings and priorities, lock characters and set the time limit.
4. Run: the solver runs in a background thread and the page polls its status.
5. Results: an overview of the roster with the mod fit before and after.
6. Character detail: the new mods and stats for one character.

Implementation details:

- Each visitor has a separate data directory and session state. Only one solve runs at a time.
- Requests are rate limited with Flask-Limiter.
- The app is deployed on Render as two services ([render.yaml](render.yaml)): the Flask app under gunicorn, and the Comlink Docker image. Comlink uses HMAC request signing, so only this app can query it.
- Community data (weightings, priorities and images) is updated offline and committed as JSON. The priority scraper runs a Chrome browser and is not run on the public server.

## Running locally

Requirements: Python 3 and [Docker](https://www.docker.com/).

1. Start Comlink:
   ```bash
   docker run -d --name swgoh-comlink -p 3000:3000 \
     -e APP_NAME=swgoh-mod-optimizer \
     ghcr.io/swgoh-utils/swgoh-comlink:latest
   ```
   The app expects Comlink at `http://localhost:3000`. Set the `COMLINK_URL` environment variable to use another address.

2. Install the dependencies:
   ```bash
   git clone https://github.com/otmuk2006-rgb/swgoh-mod-optimizer.git
   cd swgoh-mod-optimizer
   python -m venv venv
   source venv/bin/activate        # Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. Start the web app from the repository root:
   ```bash
   python ui/app.py
   ```
   Open http://localhost:5000 and enter an ally code, for example `846927846`.

### Command-line version

`python main.py` runs the same pipeline in the terminal. It asks for an ally code, characters, weightings and locked characters. The result is written to `data/processed/final_assignment.json`.

### Updating the community data

The JSON files in `data/processed/` are sufficient to run the app. To rebuild them, run `python main.py` and answer `y` to the refresh prompt. This downloads the top players' mods again, which takes several minutes. It also scrapes swgoh.gg with Selenium. This step requires Google Chrome and can be blocked by Cloudflare.

## Repository structure

```
scraping/       Data collection from Comlink and swgoh.gg
calculations/   Weightings, mod scores, character stats and reporting
optimiser/      ILP model and solver settings
ui/             Flask app, templates, JavaScript, CSS and images
data/processed/ Precomputed community data used at runtime
utils.py        Comlink client and session data paths
main.py         Command-line entry point
render.yaml     Deployment configuration
```

## Limitations

- The weightings are based on about 250 accounts. The GAC leaderboard endpoint does not expose more players.
- Priority is defined per character, not per team. I designed a team-level model based on GAC squad usage with Bayesian shrinkage. It was not implemented because no usable data source exists. The swgoh.gg squad pages are image-based and protected by Cloudflare, and Comlink does not provide battle history.
- Session state is stored in memory on a single worker. A Redis store would be needed to run more than one instance.
