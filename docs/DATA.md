# Data Inventory

**Last updated:** March 18, 2026

## Active Pipeline Data

### Model Probabilities (our best estimate of team strength)

| File | Source | Year | Format | Notes |
|------|--------|------|--------|-------|
| `data/historical/pred.paine.men.2026.csv` | Neil Paine composite | 2026 | name, round1-6 | Same methodology as 538 |
| `data/dk_implied_odds.csv` | DraftKings | 2026 | team, R1/S16/E8/F4/champ implied | No R2 column; interpolate R2≈sqrt(R1×S16) |
| `data/historical/pred.538.men.{2017-2023}.csv` | FiveThirtyEight | 2017-2023 | name, round1-6 | Pre-tournament cumulative advancement probs |
| `data/historical/pred.kenpom.men.{2018-2022}.csv` | KenPom | 2018-2022 | name, round1-6 | Alternative model |

### Public Pick Distributions (what the crowd picks)

| File | Source | Year | Format | Notes |
|------|--------|------|--------|-------|
| `data/espn_picks_2026_mens.csv` | ESPN Gambit API | 2026 | team, round, pick_pct, pick_count | ~172M brackets (refreshed 9:40 PM ET Mar 18) |
| `data/espn_picks_{2023-2025}_mens.csv` | ESPN Gambit API | 2023-2025 | same | Historical ESPN API |
| `data/historical/pred.pop.men.{2016-2025}.csv` | mRchmadness R package | 2016-2025 | name, round1-6 | ESPN cache, converted from RData |

### Actual Outcomes (for backtesting and sigma calibration)

| File | Source | Years | Content |
|------|--------|-------|---------|
| `data/538_ncaa_forecasts_2018.csv` | FiveThirtyEight | 2018 | Multi-date forecasts; final date has actual outcomes (rd{X}=1.0/0.0) |
| `data/538_ncaa_forecasts_2021.csv` | FiveThirtyEight | 2021 | Same structure |
| `data/538_ncaa_forecasts_2022.csv` | FiveThirtyEight | 2022 | Same; also `_pretourney` variant |
| `data/538_ncaa_forecasts_2023_final.csv` | FiveThirtyEight | 2023 | Same; also short `_2023.csv` (pre-tournament only) |
| `data/538_historical_ncaa_tournament_model_results.csv` | FiveThirtyEight | 2011-2014 | Game-level: favorite, underdog, probability, win_flag |
| `data/tidytuesday_team_results.csv` | TidyTuesday | All time | Team summary stats (games, wins, advancement counts) |

### Raw/Archive

| File | Source | Notes |
|------|--------|-------|
| `data/rdata/*.RData` | mRchmadness | Source RData files (already converted to CSV in historical/) |
| `data/brackets_2015.zip` | Bekt/espn-brackets | 2.9M raw ESPN brackets from 2015 |
| `data/data/brackets.txt` | Same | Unzipped, 553MB |
| `data/538_bracket_2014_00.csv` | FiveThirtyEight | Single bracket example |
| `data/538_historical_game_results.csv` | FiveThirtyEight | Duplicate of ncaa_tournament_model_results |
| `data/tidytuesday_public_picks.csv` | TidyTuesday | Small public pick dataset |
| `data/espn_picks_2026_mens_alt.csv` | ESPN API | Alternative scrape of 2026 data |

## Data Flow

```
Model:  pred.paine.men.2026.csv ─┐
                                  ├─ blend_probs() ─→ our_probs ─→ make_chalk_bracket()
Market: data/dk_implied_odds.csv ┘                                  ↓
                                                              hill-climb
                                                                  ↓
Truth:  our_probs + perturb_probs(sigma=0.27) ──→ simulate_tournament()
                                                                  ↓
Public: espn_picks_2026_mens.csv ──→ generate_opponent() ────→ precompute_sims()
```

## Column Mappings

### 538 Raw Forecast Files (rd1-rd7)
```
rd1_win = P(survive play-in)     → always 1.0 for non-playin teams
rd2_win = P(win R1 game)         → our "R1"
rd3_win = P(advance past R2)     → our "R2"
rd4_win = P(advance past S16)    → our "S16"
rd5_win = P(advance past E8)     → our "E8"
rd6_win = P(advance past F4)     → our "F4"
rd7_win = P(win championship)    → our "Championship"
```

### Cleaned Prediction Files (round1-round6)
```
round1 = P(advance past R1)      → our "R1"
round2 = P(advance past R2)      → our "R2"
round3 = P(advance past S16)     → our "S16"
round4 = P(advance past E8)      → our "E8"
round5 = P(advance past F4)      → our "F4"
round6 = P(win championship)     → our "Championship"
```

## Calibrated Parameters

| Parameter | Value | Source |
|-----------|-------|--------|
| SIGMA_LOGIT | 0.27 | src/calibrate_sigma.py: RMS calibration error from 1482 team×round observations (2018-2023) |
| MODEL_WEIGHT | 0.35 | Lean market (65%). Justified because sportsbooks price in injuries; the Paine composite does not. |

## Model vs Market Gaps (2026)

The Paine composite does **not** adjust for injuries or player availability. It averages
6 season-long rating systems (BPI, KenPom, Torvik, TeamRankings, Sports-Reference, JThom).
Sportsbooks reprice continuously as injury news breaks.

Key gaps attributable to injuries (as of March 19, 2026):

| Team | Model | Market | Gap | Likely cause |
|------|-------|--------|-----|-------------|
| Duke | 23.8% | 17.6% | +6.1% | Caleb Foster (broken foot), Patrick Ngongba (foot) both OUT |
| Louisville | higher | lower | | Mikel Brown Jr. OUT first weekend (back) |
| Gonzaga | higher | lower | | Braden Huff OUT since Jan (knee) |
| Purdue | 5.7% | 3.0% | +2.7% | No injury — genuine model/market disagreement |
| Illinois | 5.5% | 3.4% | +2.1% | No injury — genuine model/market disagreement |

MODEL_WEIGHT=0.35 (65% market) is the right call: the market is the more informed
source on injuries and late-breaking information.

## The Odds API

Live odds sourced from [The Odds API](https://the-odds-api.com/) (free tier, 500 credits/month).

```
# Championship futures (outrights) — DraftKings, BetMGM, BetRivers
GET https://api.the-odds-api.com/v4/sports/basketball_ncaab_championship_winner/odds
    ?regions=us&markets=outrights&oddsFormat=american&apiKey=KEY

# R1 game moneylines
GET https://api.the-odds-api.com/v4/sports/basketball_ncaab/odds
    ?regions=us&markets=h2h&oddsFormat=american&apiKey=KEY
```

Intermediate rounds (S16, E8, F4) are interpolated log-linearly between R1 and
championship using historical seed-based advancement ratios.

## ESPN Gambit API

```
GET https://gambit-api.fantasy.espn.com/apis/v1/propositions?challengeId={ID}

Known IDs: 239=2023, 240=2024, 257=2025, 277=2026 (men's)
No auth required. Returns team names, seeds, pick counts, pick percentages.
Filter by round: &filter={"filterPropositionScoringPeriodIds":{"value":[ROUND]}}
```

## Refresh Commands

```bash
python3 src/scrape_espn_picks.py        # Refresh ESPN public picks (run close to deadline)
ODDS_API_KEY=xxx python3 src/fetch_odds.py  # Pull live odds from DraftKings/BetMGM/BetRivers
python3 src/calibrate_sigma.py          # Recompute sigma (only if adding new historical data)
```
