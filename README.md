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

1. Estimate stat weightings $W_{j,s}$ for each character from top players' mods.
2. Estimate a priority $p_j$ for each character from tier ratings.
3. Score every mod for every character, and value every set bonus on the same scale.
4. Solve the ILP.
5. Evaluate the change in mod fit.

### Notation

| Symbol | Meaning |
|---|---|
| $I$ | the player's mods |
| $J$ | the characters selected for optimisation |
| $S$ | stat types (speed, offense %, crit chance, ...) |
| $K$ | set types (speed, offense, health, ...) |
| $v_{i,s}$ | value of stat $s$ on mod $i$, as a primary or secondary stat (0 if absent) |
| $\ell_i$ | level of mod $i$ (maximum 15) |
| $k(i)$ | set type of mod $i$ |
| $\sigma(k)$ | stat increased by set $k$ |
| $r_k$ | number of mods needed to complete set $k$ |
| $b_k$ | full bonus of set $k$ |
| $v^{base}_j$ | base speed of character $j$ |

The set constants are:

| Set $k$ | $r_k$ | $b_k$ |
|---|---|---|
| Speed | 4 | $0.10 \cdot v^{base}_j$ |
| Offense | 4 | 15% |
| Critical damage | 4 | 30% |
| Health | 2 | 10% |
| Defense | 2 | 25% |
| Critical chance | 2 | 8% |
| Potency | 2 | 15% |
| Tenacity | 2 | 20% |

**Set bonus rule.** Let $M$ be the six mods on one character and $n_k(M)$ the number of them in set $k$. The bonus is

$$
\beta_k(M) =
\begin{cases}
b_k & \text{if } n_k(M) \ge r_k \text{ and the mods forming the set are level 15} \\
\tfrac{1}{2} b_k & \text{if } n_k(M) \ge r_k \text{ otherwise} \\
0 & \text{if } n_k(M) < r_k
\end{cases}
$$

**Stat total.** The total of stat $s$ from mods $M$, including set bonuses, is

$$
T_s(M) = \sum_{i \in M} v_{i,s} + \sum_{k \,:\, \sigma(k) = s} \beta_k(M)
$$

### 1. Stat weightings

The weightings are estimated from data, not set by hand ([calculations/mod_weightings.py](calculations/mod_weightings.py)).

The top 50 players in each of the five Kyber divisions are taken from the GAC leaderboards, giving about 250 accounts. Data is accessed through [Comlink](https://github.com/swgoh-utils/swgoh-comlink), an API for SWGOH game data ([scraping/GAC_leaderboards.py](scraping/GAC_leaderboards.py)). All mods equipped by these players are downloaded and decoded ([scraping/top250_player_mods.py](scraping/top250_player_mods.py)).

Let $A_j$ be the sampled accounts that have character $j$, and $M_{a,j}$ the mods account $a$ has on $j$. The average total of stat $s$ on character $j$ is

$$
\bar{x}_{j,s} = \frac{1}{|A_j|} \sum_{a \in A_j} T_s(M_{a,j})
$$

Each stat is then divided by its largest average across all characters:

$$
m_s = \max_{j'} \bar{x}_{j',s}, \qquad W_{j,s} = \frac{\bar{x}_{j,s}}{m_s} \in [0, 1]
$$

The character with the highest average speed therefore has $W_{j,\text{speed}} = 1$. The other characters' speed weights are relative to that observed value. The values $m_s$ are saved, because stage 5 uses the same scale.

### 2. Character priority

When two characters compete for the same mod, priority decides between them. Each character's swgoh.gg meta page gives a tier as a leader, $t^{lead}_j$, and as a squad member, $t^{mem}_j$ ([scraping/character_priority_rankings.py](scraping/character_priority_rankings.py)). The tiers are mapped to numbers:

$$
\tau(\text{S}) = 1.0, \quad \tau(\text{A}) = 0.8, \quad \tau(\text{B}) = 0.6, \quad \tau(\text{C}) = 0.4, \quad \tau(\text{D}) = 0.2
$$

The tier score is the better of the two roles. A character with no tier receives 0.1. A short manual list replaces the tier for characters whose page was missing or misleading.

$$
p^{tier}_j = \max\left(\tau(t^{lead}_j),\ \tau(t^{mem}_j)\right)
$$

At solve time, characters below gear 13 in the user's roster are capped, since they are not used in competitive play:

$$
p_j =
\begin{cases}
\min(p^{tier}_j,\ 0.1) & \text{if } \text{gear}_j < 13 \\
p^{tier}_j & \text{otherwise}
\end{cases}
$$

The user can replace $p_j$ with any value in $[0, 1]$.

### 3. Mod scores and set bonus values

Each stat is normalised by $\mu_{j,s}$, the largest value of that stat a full six-mod loadout can give ([calculations/max_possible_stats.py](calculations/max_possible_stats.py)). Let $n^{P}_s$ be the number of slots where $s$ can be the primary stat, $P_s$ the maximum primary value and $Q_s$ the maximum secondary value. Then

$$
\mu_{j,s} = n^{P}_s P_s + (6 - n^{P}_s)\, Q_s + b_{k(s)}
$$

where $b_{k(s)}$ is the full bonus of the set for $s$, if one exists. Speed is a primary only on the arrow, so $\mu_{j,\text{speed}} = 32 + 5 \cdot 31 + 0.10 \cdot v^{base}_j$. This is the only stat that depends on the character.

The score of mod $i$ for character $j$ is ([calculations/mod_score.py](calculations/mod_score.py))

$$
\text{score}(i,j) = \sum_{s \in S} \frac{v_{i,s}}{\mu_{j,s}} \, W_{j,s}
$$

The value of completing set $k$ on character $j$ is computed on the same scale:

$$
B^{full}_{k,j} = \frac{b_k}{\mu_{j,\sigma(k)}} \, W_{j,\sigma(k)}, \qquad B^{min}_{k,j} = \tfrac{1}{2} B^{full}_{k,j}
$$

Because mod stats and set bonuses use the same units, the solver can compare them directly. A mod outside a set is chosen when its additional stats are worth more than the set bonus it would cost.

### 4. Integer linear program

The model is built with [PuLP](https://coin-or.github.io/pulp/) and solved with the CBC solver ([optimiser/solver.py](optimiser/solver.py)).

**Decision variables.**

- $x_{ij} \in \{0,1\}$: mod $i$ is assigned to character $j$.
- $z^{full}_{jk}, z^{min}_{jk} \in \{0,1\}$: character $j$ receives the full or half bonus of set $k$.

**Objective.** Mod stats and set bonuses are maximised together, each weighted by priority:

$$
\max \ \sum_{i \in I} \sum_{j \in J} p_j \, \text{score}(i,j) \, x_{ij}
\;+\; \sum_{j \in J} \sum_{k \in K} p_j \left( B^{full}_{k,j} \, z^{full}_{jk} + B^{min}_{k,j} \, z^{min}_{jk} \right)
$$

**Constraints.**

Each mod is assigned to at most one character:

$$
\sum_{j \in J} x_{ij} \le 1 \qquad \forall i \in I
$$

Each character has at most one mod in each slot $q$:

$$
\sum_{i \in I_q} x_{ij} \le 1 \qquad \forall j \in J,\ \forall q
$$

The full bonus requires $r_k$ level 15 mods of set $k$. The half bonus requires $r_k$ mods of set $k$ at any level:

$$
\sum_{\substack{i \,:\, k(i) = k \\ \ell_i = 15}} x_{ij} \ \ge\ r_k \, z^{full}_{jk},
\qquad
\sum_{i \,:\, k(i) = k} x_{ij} \ \ge\ r_k \, z^{min}_{jk}
\qquad \forall j, k
$$

A character receives at most one of the two bonuses for each set:

$$
z^{full}_{jk} + z^{min}_{jk} \le 1 \qquad \forall j, k
$$

Six-dot mods require gear 12. No variable $x_{ij}$ is created for such pairs.

**How the set constraints work.** If $z_{jk} = 1$, the right-hand side becomes $r_k$, so the character must have $r_k$ matching mods. If $z_{jk} = 0$, the constraint is always satisfied. Because the objective is maximised and $B^{full} > B^{min}$, the solver sets $z^{full}_{jk} = 1$ whenever the full bonus is achievable, and otherwise $z^{min}_{jk} = 1$ if the half bonus is achievable. This expresses the threshold rule $\beta_k$ using only linear constraints.

**Locked characters.** The user can lock characters so their mods do not change. Locked characters and their mods are removed before the model is built:

$$
J' = J \setminus J_{locked}, \qquad I' = I \setminus \{ i : i \text{ is equipped on a locked character} \}
$$

This gives the same optimum as fixing the variables. In a test with 60 characters, 20 of them locked, it reduced the number of variables by about 39% and the solve time by a factor of about 2.2.

**Solution method.** CBC uses branch and bound. It solves the linear relaxation ($0 \le x_{ij} \le 1$) to obtain an upper bound, branches on fractional variables, and discards branches whose bound is below the best integer solution found. The solve has a time limit of 60 seconds by default, capped at 90 seconds on the server. If the limit is reached, CBC returns the best solution found and the gap to the upper bound.

### 5. Evaluation

The results page lists the mods that moved and each character's stats before and after, computed with Comlink's `StatCalc`. It also reports the mod fit of each character ([calculations/reporting.py](calculations/reporting.py)).

Let $M_j$ be the mods on character $j$. Their stat totals are normalised with the same $m_s$ as in stage 1:

$$
\hat{t}_{j,s} = \frac{T_s(M_j)}{m_s}
$$

Mod fit is the cosine similarity between this vector and the weighting vector:

$$
\text{fit}_j = \frac{\hat{t}_j \cdot W_j}{\lVert \hat{t}_j \rVert \, \lVert W_j \rVert}
$$

It equals 1 when the proportions of stats match the weightings exactly, regardless of their size. The page reports the average over all characters with weightings, before and after optimisation:

$$
\overline{\text{fit}} = \frac{1}{|J_W|} \sum_{j \in J_W} \text{fit}_j
$$

Mod fit depends on the whole set of mods together, so it is not linear in $x_{ij}$. It is therefore used only for evaluation, not in the objective.

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

**Computation time.** The model has one binary variable for each eligible mod and character pair, so its size is about $|I| \cdot |J|$. In a test with 25 characters and about 1,500 mods, the model had about 37,000 binary variables. CBC did not prove optimality within 30 seconds, and the solution found was within about 2.5% of the upper bound. Integer programs are NP-hard in general, and the solve time grows quickly with the number of characters. Large selections cannot be solved to proven optimality within the time limit. The result is still a valid assignment, but it may not be the best one.

**Set stacking.** The model counts at most one bonus per set type per character. In the game, two-mod sets stack: six health mods give three health bonuses. The model therefore undervalues stacked two-mod sets. Allowing $z_{jk} \in \{0, 1, 2, 3\}$ for these sets would fix this.

**Team priority.** Priority is defined per character, not per team. A team-level model based on GAC squad usage was designed but not implemented, because no usable data source exists. The swgoh.gg squad pages are image-based and protected by Cloudflare, and Comlink does not provide battle history.
