# SWGOH Mod Optimiser

Live demo: https://swgoh-mod-optimizer.onrender.com

The demo is hosted on Render's free tier. The first request after a period of inactivity can take one to two minutes.

Example ally code (my account): `846-927-846`

## Overview

This project assigns mods to characters in *Star Wars: Galaxy of Heroes* (SWGOH). It optimises the whole roster at once by formulating the assignment as an integer linear program (ILP). The stat preferences used in the objective are estimated from the mods equipped by the top Grand Arena (GAC) players. Character importance is estimated from community tier ratings.

## Problem

Each character in SWGOH equips six mods, one per slot. A mod has a primary stat, up to four secondary stats, and a set type. Equipping two or four mods of the same set gives a set bonus, for example +10% speed for four speed mods. The bonus is halved if any mod in the set is below level 15. A developed account has several hundred characters and several thousand mods.

Currently, mod assignment happens either through an in game algorithm that assigns mods individually (producing sub-optimal outcomes), or through assigning mods by hand (which is effective, but takes a very long time). 

## Method

The pipeline has five stages.

1. Estimate the stat weightings of each character from top players' mods.
2. Estimate the priority of each character from tier ratings.
3. Score every mod for every character, and value every set bonus on the same scale.
4. Solve the ILP.
5. Evaluate the change in mod fit.

### 1. Stat weightings

The weightings describe which stats each character needs. They are estimated from data, not set by hand ([calculations/mod_weightings.py](calculations/mod_weightings.py)).

The top 50 players in each of the five Kyber divisions are taken from the GAC leaderboards, giving about 250 accounts. Data is accessed through [Comlink](https://github.com/swgoh-utils/swgoh-comlink), an API for SWGOH game data. All mods equipped by these players are downloaded ([scraping/top250_player_mods.py](scraping/top250_player_mods.py)). For each account and character, the stats of the six mods are summed, including any completed set bonus. These totals are averaged across accounts, giving $\bar{x}_{j,s}$, the average amount of stat $s$ on character $j$.

Each stat is then divided by its largest average across all characters:

$$
W_{j,s} = \frac{\bar{x}_{j,s}}{\max_{j'} \bar{x}_{j',s}}
$$

Each weight lies between 0 and 1. The character with the highest average speed has a speed weight of 1, and the other characters' speed weights are relative to that observed value.

### 2. Character priority

When two characters compete for the same mod, priority $p_j$ decides between them. It is taken from the swgoh.gg meta page of each character ([scraping/character_priority_rankings.py](scraping/character_priority_rankings.py)). Each page rates the character as a leader and as a squad member. The better of the two tiers is converted to a score: S = 1.0, A = 0.8, B = 0.6, C = 0.4 and D = 0.2.

Characters below gear 13 in the user's roster are capped at 0.1, because they are rarely used in competitive play. The user can also set any priority by hand.

### 3. Mod scores

Each stat on a mod is divided by $\mu_{j,s}$, the largest amount of that stat a full set of six mods can give. This puts different stats, such as flat speed and percentage offense, on a common scale. The score of mod $i$ for character $j$ is the weighted sum of its normalised stats ([calculations/mod_score.py](calculations/mod_score.py)):

$$
\text{score}(i,j) = \sum_{s} \frac{v_{i,s}}{\mu_{j,s}} \, W_{j,s}
$$

where $v_{i,s}$ is the value of stat $s$ on mod $i$.

The value of a set bonus is computed in the same way. If set $k$ gives a bonus $b_k$ to stat $s$, its value to character $j$ is

$$
B_{k,j} = \frac{b_k}{\mu_{j,s}} \, W_{j,s}
$$

with half this value for the reduced bonus. Because mod stats and set bonuses use the same units, the solver can compare them directly. A mod outside a set is chosen when its additional stats are worth more than the set bonus it would cost.

### 4. Integer linear program

The model is built with [PuLP](https://coin-or.github.io/pulp/) and solved with the CBC solver ([optimiser/solver.py](optimiser/solver.py)).

The decision variable $x_{ij}$ equals 1 if mod $i$ is assigned to character $j$, and 0 otherwise. The integer variable $z_{jk}$ is the number of times character $j$ completes set $k$. Two-mod sets stack, so $z_{jk}$ can be up to 3 for these sets: six health mods give three health bonuses. Four-mod sets can be completed only once. There are separate variables for the full and the reduced bonus.

The objective maximises the total value of the assigned mods and completed sets, each weighted by the character's priority:

$$
\max \ \sum_{i,j} p_j \, \text{score}(i,j) \, x_{ij} \;+\; \sum_{j,k} p_j \, B_{k,j} \, z_{jk}
$$

Mod stats and set bonuses are optimised together, not in separate steps.

The main constraints are:

- Each mod is assigned to at most one character.
- Each character has at most one mod in each of the six slots.
- Six-dot mods can only be assigned to characters at gear 12 or above.
- A set bonus can only be claimed if enough mods of that set are assigned:

$$
\sum_{i \in \text{set } k} x_{ij} \ \ge\ r_k \, z_{jk}
$$

Here $r_k$ is the number of mods the set requires (2 or 4). Each completed set needs its own $r_k$ mods, so claiming $z_{jk}$ bonuses requires at least $r_k z_{jk}$ mods of that set. Full bonuses are limited in the same way by the number of level 15 mods, and full and reduced bonuses together cannot exceed the number of complete sets. Because the objective is maximised, the solver claims as many full bonuses as the level 15 mods allow, and reduced bonuses for the remaining complete sets. This is the same rule the game uses, expressed with linear constraints only.

The user can lock characters so that their mods do not change. Locked characters and their mods are removed before the model is built. This gives the same result as adding variables for them and fixing their values, but the model is smaller and faster to solve.

CBC solves the model by branch and bound. It solves a relaxed version in which the variables can take fractional values, which gives an upper bound on the objective. It then branches on fractional variables and discards branches that cannot improve on the best solution found. The solve has a time limit of 60 seconds by default, capped at 90 seconds on the server. If the limit is reached, CBC returns the best solution found so far.

### 5. Evaluation

The results page lists the mods that moved and each character's stats before and after, computed with Comlink's `StatCalc`. It also reports the mod fit of the roster before and after optimisation ([calculations/reporting.py](calculations/reporting.py)).

Mod fit is the cosine similarity between a character's total mod stats $t_j$, normalised in the same way as the weightings, and their weighting vector $W_j$:

$$
\text{fit}_j = \frac{t_j \cdot W_j}{\lVert t_j \rVert \, \lVert W_j \rVert}
$$

It equals 1 when the proportions of stats match the weightings exactly, regardless of their size. Mod fit depends on all six mods together, so it is not linear in $x_{ij}$. It is therefore used only for evaluation, not in the objective.

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

**Sample size.** The weightings are based on the top 50 players from each of the five Kyber divisions, about 250 accounts. This is the maximum the GAC leaderboard endpoint exposes. A better sample would be the top 1,000 players of Kyber 1. The current sample includes weaker accounts and gives few observations for less popular characters, so their weightings are less reliable.

**Seasonal changes.** The best way to mod a character changes over time. New characters, balance changes and temporary GAC and event modifiers change which characters are used and which stats they need. The weightings and priorities describe the meta at the time the data was collected. They become outdated unless the data is refreshed regularly.

**Behavioural data as the standard.** The weightings describe what top players do, not what is optimal. This is a reasonable target for most accounts. It is less suitable for very late-game accounts whose mods are better than those in the sample. These players can afford stat profiles the sample rarely reaches, so imitating the sample average may not give their best assignment.

**Computation time.** The model has one binary variable for each mod and character pair, so its size grows with the number of mods multiplied by the number of characters. An account with a few thousand mods produces tens of thousands of variables even for a moderate selection of characters. Integer programs are NP-hard in general, and the solve time grows quickly with the number of characters. Large selections cannot be solved to proven optimality within the time limit. The result is still a valid assignment, but it may not be the best one.

**Team priority.** Priority is defined per character, not per team. A team-level model based on GAC squad usage was designed but not implemented, because no usable data source exists. The swgoh.gg squad pages are image-based and protected by Cloudflare, and Comlink does not provide battle history.
