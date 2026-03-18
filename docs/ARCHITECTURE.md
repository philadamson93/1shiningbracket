# Bracket Optimizer Architecture

**Last updated:** March 18, 2026
**Brackets due:** March 19, 12:15 PM ET

---

## The Core Insight

The simulation engine we built for backtesting IS the bracket generator. Instead of:

```
Old: hand-craft strategies → backtest to see which wins → use winning strategy to pick brackets
```

We should:

```
New: simulate many tournament outcomes → for each, score EVERY possible bracket approach →
     find the bracket PORTFOLIO that maximizes expected payout across all simulations
```

The simulation engine already does steps 1-3. We just need to close the loop: use the sim to directly search for optimal brackets rather than evaluating pre-defined strategies.

---

## System Architecture

```
┌─────────────────────────────────────────────────────────┐
│                     DATA LAYER                          │
│                                                         │
│  data_loader.py                                         │
│  ├── load_year_data(year) → {model, market, public}     │
│  ├── Model:  538 (2017-23) | Paine (2026)              │
│  ├── Market: DK odds (2026) | historical (partial)      │
│  └── Public: ESPN Gambit API (2023-26) | mRchmadness    │
│                                                         │
│  scrape_espn_picks.py   → data/espn_picks_YYYY.csv      │
│  scrape_dk_odds.py      → dk_implied_odds.csv           │
│  scrape_yahoo_picks.py  → yahoo_pick_distribution.csv   │
└─────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────┐
│                  SIMULATION ENGINE                       │
│                                                         │
│  sim_engine.py  (TO BUILD — extract from backtest_sim)  │
│                                                         │
│  Core functions:                                        │
│  ├── simulate_tournament(truth_probs, sigma)            │
│  │   → full 63-game outcome from perturbed probs        │
│  ├── generate_bracket(model_probs, public_picks, params)│
│  │   → 63 picks for one bracket                         │
│  ├── generate_opponent(public_picks)                    │
│  │   → 63 picks sampled from public distribution        │
│  ├── score_bracket(bracket, outcome)                    │
│  │   → integer score (ESPN standard scoring)            │
│  └── compute_payout(our_scores, opp_scores, payout_structure)  │
│      → finishing position and payout                    │
│                                                         │
│  Key design: MODEL SEPARATION                           │
│  - Tournament outcomes simulated from "truth" (perturbed│
│    model probs with calibrated sigma)                   │
│  - Our brackets picked from "model" (unperturbed)       │
│  - Opponents picked from "public" (ESPN distribution)   │
│  - The gap between model and truth IS model error       │
│  - The gap between model and public IS leverage          │
└─────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────┐
│                 BRACKET GENERATOR                        │
│                                                         │
│  bracket_maker.py  (TO BUILD — replaces bracket_optimizer)│
│                                                         │
│  Uses the sim engine to DIRECTLY SEARCH for optimal     │
│  brackets rather than evaluating pre-defined strategies. │
│                                                         │
│  Algorithm:                                             │
│  1. Pre-simulate M tournament outcomes + N opponents    │
│  2. Generate candidate bracket #1:                      │
│     a. Start with model-chalk bracket (all favorites)   │
│     b. Hill-climb: for each game, try flipping the pick │
│        → keep flip if it improves portfolio EV across    │
│        all M simulations                                │
│     c. Converge to locally optimal bracket #1           │
│  3. Generate bracket #2:                                │
│     a. Start from a DIFFERENT seed (random perturbation)│
│     b. Hill-climb with MARGINAL portfolio EV            │
│        (value of bracket #2 given bracket #1 exists)    │
│     c. This naturally diversifies — bracket #2 covers   │
│        different "worlds" than bracket #1                │
│  4. Repeat for brackets #3-10, each optimized for       │
│     marginal contribution to the portfolio              │
│                                                         │
│  This is Clair & Letscher (2007) hill-climbing +        │
│  Haugh & Singal (2021) greedy submodular portfolio.     │
│                                                         │
│  Params (all configurable):                             │
│  ├── FIELD_SIZE = 250                                   │
│  ├── NUM_BRACKETS = 10                                  │
│  ├── PAYOUT = {1: 0.60, 2: 0.20, 3: 0.10, 4: 0.05}   │
│  ├── M_SIMS = 1000                                     │
│  ├── N_OPPONENTS = 250                                  │
│  ├── SIGMA = calibrated from historical 538 error       │
│  └── MODEL_WEIGHT = blend of model vs market for picks  │
└─────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────┐
│                    VALIDATION                           │
│                                                         │
│  backtest_sim.py                                        │
│  - Uses sim_engine on historical years (2017-2023)      │
│  - Compares strategies under model separation            │
│  - Calibrates sigma from 538 historical errors          │
│  - Validates that hill-climbing beats pre-defined strats │
│                                                         │
│  backtest_harness.py                                    │
│  - Champion-only backtest (11 years, 2014-2025)         │
│  - Quick directional validation                         │
└─────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────┐
│                      OUTPUT                             │
│                                                         │
│  final_brackets.json                                    │
│  - 10 brackets, each with 63 game picks                 │
│  - Ready for manual entry into ESPN/pool platform       │
│                                                         │
│  portfolio_summary.md                                   │
│  - Champion distribution across 10 brackets             │
│  - FF/E8 exposure analysis                              │
│  - Expected EV from simulation                          │
│  - Leverage analysis per bracket                        │
└─────────────────────────────────────────────────────────┘
```

---

## Implementation Status

| Module | File | Status | Notes |
|--------|------|--------|-------|
| Data loader | `data_loader.py` | **DONE** | Loads all sources, normalizes names/rounds |
| ESPN scraper | `scrape_espn_picks.py` | **DONE** | Gambit API, 2023-2026 |
| DK scraper | `scrape_dk_odds.py` | **DONE** | Hardcoded odds, vig-stripped |
| Yahoo scraper | `scrape_yahoo_picks.py` | **DONE** (deprecated) | Replaced by ESPN |
| Sim engine | `sim_engine.py` | **TO BUILD** | Extract from backtest_sim.py, add sigma |
| Bracket maker | `bracket_maker.py` | **TO BUILD** | Hill-climbing + portfolio optimization |
| Backtest (sim) | `backtest_sim.py` | **NEEDS REFACTOR** | Add model separation, use sim_engine |
| Backtest (champ) | `backtest_harness.py` | **DONE** | 11-year champion-only |
| Old optimizer | `bracket_optimizer.py` | **DEPRECATED** | Replaced by bracket_maker |
| Old generator | `bracket_generator.py` | **DEPRECATED** | Replaced by bracket_maker |

---

## Key Parameters to Calibrate

| Parameter | What It Controls | How to Calibrate |
|-----------|-----------------|-----------------|
| **sigma** | Model error magnitude. Controls chalk↔leverage tradeoff in sim. | Compute RMS error of 538 predictions vs actual outcomes (2017-2023). We have both. |
| **MODEL_WEIGHT** | Blend of model (538/Paine) vs market (DK) for OUR picks. | User preference: lean DK (~0.35 model). Backtest can also inform. |
| **FIELD_SIZE** | Pool size. Risk scaling. | Direct input: 250. |
| **PAYOUT** | Pool payout structure. Drives chalk vs leverage preference. | Direct input: 60/20/10/5. |
| **M_SIMS** | Simulation count. More = more stable EV estimates. | 200 for iteration (~2.5 min), 1000 for final (~13 min). |
| **N_OPPONENTS** | Opponent count per sim. | 250 (= field size). |
| **NUM_BRACKETS** | How many brackets to submit. | 10. |

---

## The Hill-Climbing Bracket Maker (Key Algorithm)

```python
def make_portfolio(M_sims, model, public, truth, params):
    # Pre-simulate M tournament outcomes + opponents (expensive, do once)
    sims = [(simulate_tournament(truth, sigma),
             [generate_opponent(public) for _ in range(N_opponents)])
            for _ in range(M_sims)]

    portfolio = []

    for k in range(NUM_BRACKETS):
        # Start from model-chalk bracket
        bracket = chalk_bracket(model)

        # Hill-climb: try flipping each of 63 game picks
        improved = True
        while improved:
            improved = False
            for game in range(63):
                # Try flipping this game's pick
                flipped = flip_pick(bracket, game)

                # Compute MARGINAL portfolio EV with flipped bracket
                ev_current = marginal_portfolio_ev(bracket, portfolio, sims)
                ev_flipped = marginal_portfolio_ev(flipped, portfolio, sims)

                if ev_flipped > ev_current:
                    bracket = flipped
                    improved = True

        portfolio.append(bracket)

    return portfolio
```

**Why this works:**
- Bracket #1 hill-climbs to the single best bracket (maximizes individual EV)
- Bracket #2 hill-climbs for MARGINAL value given #1 exists → naturally picks different champions/FF
- Each subsequent bracket covers scenarios the portfolio doesn't yet cover
- The sim's model separation (truth ≠ model) ensures leverage matters
- 63 binary flips × ~5-10 iterations = ~500 evaluations per bracket, each scored across M sims

**Runtime estimate:**
- Per flip evaluation: score 1 bracket across M=1000 sims = 1000 × 0.003ms = 3ms
- Per bracket: 63 flips × 10 iterations × 3ms = ~2s
- 10 brackets: ~20s (plus precomputation)
- Total with precomputation: ~15 min for M=1000

---

## Session Resumption Guide

**To continue from ANY point, read these files in order:**
1. `ARCHITECTURE.md` (this file) — system design, what exists vs what's needed
2. `STATUS.md` — detailed task list with checkboxes
3. `PLAN.md` — research findings, design decisions, backtest results

**To generate final brackets:**
1. `python3 scrape_espn_picks.py` — refresh public pick data
2. Build `sim_engine.py` (extract from backtest_sim.py)
3. Build `bracket_maker.py` (hill-climbing + portfolio)
4. Calibrate sigma from 538 historical errors
5. Run `bracket_maker.py` → `final_brackets.json`
6. Enter brackets into pool platforms before 12:15 PM ET March 19

**Key files for code:**
- `data_loader.py` — all data loading, name normalization
- `backtest_sim.py` — simulation backtest (needs model separation fix)
- `bracket_optimizer.py` — old approach (deprecated, reference only)
- `data/historical/` — 538, KenPom, ESPN pick CSVs for 2016-2025
- `data/espn_picks_2026_mens.csv` — current year ESPN data

---

## Academic References (Essential Reading for Implementation)

### 1. Clair & Letscher (2007) — "Optimal Strategies for Sports Betting Pools"
- **Journal:** Operations Research, Vol 55(6), pp. 1163-1177
- **PDF:** https://www.stat.berkeley.edu/~aldous/157/Papers/clair.pdf
- **Key contribution:** Proved that maximizing EXPECTED RETURN (not expected score) is the correct objective. Showed EV-optimized brackets beat score-optimized by orders of magnitude in large pools. Introduced the HILL-CLIMBING algorithm: start from any bracket, flip one game pick at a time, keep if it improves expected return. Uses normal approximation for opponent score distributions.
- **Directly applicable:** Our `bracket_maker.py` hill-climbing is this algorithm.

### 2. Haugh & Singal (2021) — "How to Play Fantasy Sports Strategically"
- **Journal:** Management Science, Vol 67(1), pp. 72-92
- **PDF:** http://www.columbia.edu/~mh2078/DFS_Revision_1_May2019.pdf
- **Key contribution:** Multi-entry portfolio optimization is MONOTONE SUBMODULAR → greedy selection achieves (1-1/e) ≈ 63% of optimal. Uses Dirichlet-multinomial to model opponents. Demonstrated 350% ROI.
- **Directly applicable:** Our greedy marginal-EV portfolio selection (bracket #2 optimized given #1 exists) has theoretical guarantees from this paper.

### 3. Brill, Wyner & Barnett (2024) — "Entropy-Based Strategies for Multi-Bracket Pools"
- **Journal:** Entropy, 26(8):615
- **PDF:** https://pmc.ncbi.nlm.nih.gov/articles/PMC11354004/
- **arXiv:** https://arxiv.org/abs/2308.14339
- **Key contribution:** Optimal bracket entropy increases with field size N and number of entries K. Provides the mathematical framework for why more brackets → more contrarian.

### 4. Hunter, Vielma & Zaman (2016) — "Picking Winners Using Integer Programming"
- **arXiv:** https://arxiv.org/abs/1604.01455
- **Key contribution:** Submodular portfolio optimization for top-heavy contests. Python implementation reference.
- **GitHub:** https://github.com/jnederlo/dfs_optimizers (Python implementation of their approach)

### 5. Aldous — "Prediction Tournament Paradox"
- **Source:** UC Berkeley, referenced in research_optimization_methods.md
- **Key insight:** The best forecaster is NOT the most likely pool winner. The winner is someone whose predictions diverged from consensus in the direction reality went. This IS the leverage thesis mathematically.

---

## Reusable Open-Source Code

### For sim_engine.py (tournament simulation)
- **`kylebarlow/marchmadness`** — https://github.com/kylebarlow/marchmadness
  - Python. Monte Carlo simulated annealing for bracket optimization.
  - Uses 538 ELO format input. Has `generate_bracket()` and `score_bracket()` functions.
  - Good reference for the bracket data structure and scoring logic.

- **`kindofdoon/march_madness`** — https://github.com/kindofdoon/march_madness
  - Python. 5000 tournaments/second. Builds bracket in REVERSE order (champion first).
  - Good reference for fast simulation.

- **`mglerner/MarchMadnessMonteCarlo`** — https://github.com/mglerner/MarchMadnessMonteCarlo
  - Python. Temperature parameter (higher = more random). Regional + combined simulation.

### For bracket_maker.py (portfolio optimization)
- **`dpmaloney/march_madness_bracket_optimizer`** — https://github.com/dpmaloney/march_madness_bracket_optimizer
  - Python. Explicitly handles pool size + payout structure + public pick percentages.
  - Closest to what we're building. Examine for architecture reference.

- **`dlm1223/march-madness`** — https://github.com/dlm1223/march-madness
  - **R** (not Python, but best algorithmic reference). 4-stage pipeline:
    1. `1-simulate-tournament.R` — Monte Carlo tournament sim
    2. `2-simulate-brackets.R` — Simulate opponents from ESPN pick %s
    3. `3-calculate-payouts.R` — Score against each other
    4. `4-optimize-brackets.R` — Return optimal bracket(s) for target percentile
  - **Port this to Python** for our bracket_maker.py.

- **`chanzer0/NBA-DFS-Tools`** — https://github.com/chanzer0/NBA-DFS-Tools
  - Python. Production GPP simulator with ownership projections and field simulation.
  - Architecture maps to our problem (replace "lineup" with "bracket", "player ownership" with "team pick %").

### For data (already downloaded)
- **FiveThirtyEight data repo** — https://github.com/fivethirtyeight/data/tree/master/march-madness-predictions
  - Round-by-round model probabilities 2016-2023. Downloaded to `data/` and `data/historical/`.
- **mRchmadness R package** — https://github.com/elishayer/mRchmadness
  - ESPN pick distributions 2016-2025 cached as RData. Converted to CSV in `data/historical/`.
  - Also contains `scrape.population.distribution()` function that calls ESPN Gambit API.
- **Bekt/espn-brackets** — https://github.com/Bekt/espn-brackets
  - 2.9 million raw ESPN brackets from 2015. Downloaded to `data/brackets_2015.zip`.

### ESPN Gambit API (discovered by us)
```
GET https://gambit-api.fantasy.espn.com/apis/v1/propositions?challengeId={ID}

Known IDs: 239=2023 men, 240=2024 men, 257=2025 men, 277=2026 men
No auth required. Returns JSON with team names, seeds, pick counts, pick percentages.
Filter by round: add &filter={"filterPropositionScoringPeriodIds":{"value":[ROUND]}}
```

---

## Public GitHub Repository

### Setup
```
git init
uv init
uv add pyreadr  # for reading historical RData files
# No other external deps — stdlib only for core pipeline
```

### Repo Structure
```
march-madness-optimizer/
├── README.md                    # Blog post (full write-up of methodology + design decisions)
├── pyproject.toml               # uv-managed dependencies
├── .python-version
│
├── src/
│   ├── data_loader.py           # Unified data loading + team name normalization
│   ├── sim_engine.py            # Tournament simulation (model separation, sigma)
│   ├── bracket_maker.py         # Hill-climbing bracket generator + portfolio optimization
│   ├── scrape_espn_picks.py     # ESPN Gambit API scraper (public picks)
│   └── scrape_dk_odds.py        # DraftKings odds compiler
│
├── backtest/
│   ├── backtest_sim.py          # Full-bracket simulation backtest
│   ├── backtest_harness.py      # Champion-only backtest (11 years)
│   └── calibrate_sigma.py       # Compute model error from 538 historical data
│
├── data/
│   ├── historical/              # 538, KenPom, ESPN pick CSVs (2016-2025)
│   ├── espn_picks_2026_mens.csv
│   ├── dk_implied_odds.csv
│   └── README.md                # Data provenance + how to refresh
│
├── ui/                          # Streamlit interactive UI
│   └── app.py
│
├── output/
│   ├── final_brackets.json
│   └── portfolio_summary.md
│
└── docs/
    ├── ARCHITECTURE.md          # This file
    ├── PLAN.md                  # Research findings + design decisions
    └── STATUS.md                # Implementation status
```

### User-Facing README.md (= Blog Post)

The README doubles as the full methodology write-up. Sections:

1. **What This Does** — Generate N optimized brackets for a March Madness pool of any size with any payout structure. Uses simulation-based optimization with real public pick data from ESPN (130M+ brackets) and model probabilities from analytical composites.

2. **Quick Start**
   ```bash
   git clone https://github.com/USER/march-madness-optimizer
   cd march-madness-optimizer
   uv sync
   uv run python src/scrape_espn_picks.py        # Pull latest ESPN pick data
   uv run python src/bracket_maker.py             # Generate optimized brackets
   # Or launch the UI:
   uv run streamlit run ui/app.py
   ```

3. **Configure Your Pool** — Edit params at top of `bracket_maker.py` or use the UI:
   - `FIELD_SIZE`: number of people in your pool (2 to 10,000)
   - `NUM_BRACKETS`: how many entries you're submitting (1 to 25)
   - `PAYOUT`: your pool's payout structure (winner-take-all, 60/20/10/5, flat, custom)
   - `MODEL_WEIGHT`: how much to trust models vs sportsbook odds (0.0 to 1.0)

4. **The Leverage Concept** — Real 2026 numbers: Duke picked by 25% of ESPN brackets but only has 24% model probability → 0.96x leverage (FADE). Illinois picked by 1.1% but has 5.5% model probability → 5.0x leverage (VALUE). With tables and the three-column comparison.

5. **Why This Works (The Math)** — Clair & Letscher proved expected-return-optimized brackets beat expected-score-optimized by orders of magnitude. The hill-climbing algorithm. Model separation. Marginal portfolio EV. Submodular greedy selection.

6. **The Single-Event Problem** — The tournament happens once. Why EV is still correct for a portfolio of entries. Ole Peters / ergodicity. The resolution: bounded-loss contests don't have the ruin dynamic.

7. **Backtesting** — 5 years of full round-by-round validation (2017-2023) with 538 model probs + ESPN public picks. Champion-only backtest on 11 years. Results by strategy.

8. **How the Simulation Works** — Model separation (truth ≠ model ≠ public). Sigma calibration. M simulated tournaments × N opponents. Hill-climbing 63 game picks. Precomputed opponent scores.

9. **Data Sources** — ESPN Gambit API (how we discovered it, the `root.App.main` trick for Yahoo), 538 GitHub data, mRchmadness package, KenPom, Neil Paine composite. How to refresh for future years.

10. **Limitations & Honest Caveats** — N=5 real backtest years. Model source drift. Public pick platform differences. The chalk↔leverage tradeoff depends on sigma which is uncertain.

### Interactive UI (Streamlit)

`ui/app.py` — A web interface where users can:

1. **Configure pool** — Sliders/inputs for field size, number of entries, payout structure (editable table), model weight
2. **View the bracket** with leverage scores per matchup
   - Each game: team names, model prob, ESPN pick %, leverage score
   - Color-coded: green (value >1.3x), red (fade <0.8x), grey (fair)
   - Toggle between model/market/blended views
3. **Fill out a bracket manually** — Click to pick winners, auto-cascade
   - Shows your bracket's "uniqueness score" vs ESPN public
   - Shows estimated EV for your specific pool configuration
4. **Run optimizer** — "Generate Optimal Brackets" button
   - Progress bar for simulation
   - Output: 10 brackets with portfolio summary
5. **Portfolio view** — All brackets side by side
   - Highlight differences (only late rounds differ)
   - Champion distribution, FF exposure
6. **Sensitivity analysis** — "What if field size were 500?" re-optimizes live
7. **Backtest results** — Pre-computed historical validation charts

Tech: `uv add streamlit plotly` for UI + charts. Single `app.py` file importing from `src/`.

---

## Sigma Calibration Plan

To make the simulation realistic, we need sigma = typical model prediction error.

**Data we have:** 538 pre-tournament advancement probabilities AND actual outcomes for 2017-2023.

**Method:**
```python
# For each year, for each team, for each round:
#   predicted = 538 probability of advancing
#   actual = 1 if team actually advanced, 0 otherwise
#   error = actual - predicted

# Compute RMS error across all (team, round, year) observations
# This gives us sigma ≈ typical absolute prediction error

# Also compute Brier score = mean((predicted - actual)^2)
# A well-calibrated model has Brier score ≈ predicted * (1 - predicted)
```

**Expected result:** sigma ≈ 0.05-0.10 for game-level predictions (based on ~72% model accuracy). Lower for heavy favorites (1-seeds in R1), higher for coin-flip games (8v9 matchups).

**We already have this data** in `data/historical/pred.538.men.YYYY.csv` + actual results from our backtest data. Just need to compute the errors.
