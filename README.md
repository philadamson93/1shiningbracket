# March Madness Bracket Optimizer

Generate optimized brackets for NCAA tournament pools using simulation-based portfolio optimization.

The optimizer blends analytical team-strength probabilities from [Neil Paine's 6-model composite](https://neilpaine.substack.com/p/2026-ncaa-tournament-forecast) with DraftKings market odds, simulates thousands of tournament outcomes, generates opponent brackets from ESPN public pick data (172M+ brackets), and hill-climbs each of your bracket's 63 game picks to maximize expected payout in your specific pool. Multiple brackets across pools are diversified using a Kelly (log-wealth) portfolio objective — naturally allocating contrarian picks to large pools and chalk to small ones.

## Data Sources

| Source | What | Coverage |
|--------|------|----------|
| **ESPN Gambit API** | Public pick percentages (172M brackets) | 2023-2026 |
| **Neil Paine composite** | 6-model analytical probabilities | 2026 |
| **DraftKings** | Market-implied advancement odds | 2026 |
| **FiveThirtyEight** | Historical model probabilities | 2017-2023 |
| **mRchmadness** | Historical ESPN pick distributions | 2016-2025 |

## Installation

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/philadamson93/1shiningbracket.git
cd 1shiningbracket
uv sync
```

## Usage

### Command Line

```bash
# Refresh ESPN public pick data
uv run python3 src/scrape_espn_picks.py

# Generate brackets (quick ~5s, for iteration)
uv run python3 src/bracket_maker.py --sims 200

# Generate brackets (production ~5 min)
uv run python3 src/bracket_maker.py --sims 10000

# Output: output/final_brackets.json (10 brackets, one per pool)
```

### Streamlit UI

```bash
uv sync --extra ui
uv run streamlit run ui/app.py
```

The UI lets you:
- Configure pool size, payout structure, and number of brackets
- Generate optimized brackets with a progress indicator
- View color-coded bracket trees (green = value, red = fade)
- Explore the full leverage table (all 64 teams × 6 rounds)
- Run what-if analysis (flip any pick, see the EV impact)
- Compare brackets side-by-side in portfolio view
- Load previously saved brackets from `output/final_brackets.json`

### Inputs

**Pool configuration** — edit `pools.toml` in the project root:

```toml
# Each [[pool]] entry generates one optimized bracket.

[[pool]]
name = "My Pool"
field_size = 250
payout = [50, 15, 10, 7, 5, 2, 2, 1, 1]

[[pool]]
name = "Work Pool WTA"
field_size = 100
payout = [100]
```

| Field | Description | Default |
|-------|-------------|---------|
| `name` | Label for this pool | "My Pool" |
| `field_size` | Number of entries in your pool | 250 |
| `payout` | Prize % by finishing position (1st, 2nd, ...) | [50, 15, 10, 7, 5, 2, 2, 1, 1] |

**Model parameters** (CLI flags or UI sidebar):

| Flag | Description | Default |
|------|-------------|---------|
| `--sims` | Number of Monte Carlo tournament simulations | 2000 |
| `--sigma` | Model uncertainty in logit space (calibrated from 538 data) | 0.27 |
| `--model-weight` | Blend: 0 = pure market, 1 = pure model | 0.35 |
| `--wealth-base` | Kelly diversification: lower = "win at least 1 pool" | 0.3 |
| `--restarts` | Hill-climb restarts per bracket (shuffled game order) | 20 |
| `--opponents` | Opponent brackets per simulation | 1000 |
| `--seed` | Random seed for reproducibility | 42 |

## How It Works

1. **Blend** model probabilities (Paine) with market odds (DraftKings) for each team × round
2. **Simulate** M tournament outcomes from perturbed probabilities (model separation — truth ≠ model)
3. **Generate** N opponent brackets per outcome from ESPN public pick distribution
4. **Hill-climb with restarts** — each bracket runs multiple independent hill-climbs with shuffled game traversal order, keeping the best to escape local optima (Clair & Letscher 2007)
5. **Portfolio optimization**: each bracket maximizes marginal log-wealth contribution given prior brackets (Kelly criterion + Haugh & Singal 2021 greedy submodular selection)

Different pool sizes naturally produce different brackets — small pools favor chalk, large pools favor leverage (contrarian picks where model probability exceeds public pick rate).

The `--wealth-base` parameter controls the tradeoff between "maximize total EV" and "win at least one pool." At 1.0, the optimizer stacks leverage-heavy longshots. At 0.3 (default), it covers probable outcomes first, then adds leverage plays — producing a mix of 1-seed favorites and contrarian picks across the portfolio.

## Key Files

| File | Purpose |
|------|---------|
| `src/bracket_maker.py` | Main entry point — pool config, portfolio optimizer |
| `src/sim_engine.py` | Core engine — simulation, scoring, hill-climbing, Kelly EV |
| `src/data_loader.py` | Load and normalize all data sources |
| `src/calibrate_sigma.py` | Compute model error parameter from 538 historical data |
| `ui/app.py` | Streamlit interactive UI |
| `backtest/backtest_kelly.py` | Historical validation against actual outcomes (2018-2023) |
| `backtest/backtest_mc.py` | Monte Carlo backtest with confidence intervals |
| `output/final_brackets.json` | Generated brackets output |

## Historical Validation

Tested on 4 held-out years (2018, 2021, 2022, 2023) using 538 pre-tournament predictions and ESPN public picks, scored against actual tournament outcomes and a field of 10,000 simulated ESPN brackets. Multi-start hill-climbing with restarts.

| Year | Champion | Chalk Score | Optimizer Best | vs Chalk | Field Percentile | Hit Champion? |
|------|----------|-------------|---------------|----------|-----------------|---------------|
| 2018 | Villanova | 1140 | 1160 | +20 | 93.3% | Yes |
| 2021 | Baylor | 720 | 1450 | **+730** | **99.6%** | Yes |
| 2022 | Kansas | 780 | 830 | +50 | 83.9% | No |
| 2023 | UConn | 550 | 570 | +20 | 97.2% | No |
| **Average** | | | | **+205** | **93.5%** | **2/4** |

See `docs/RESULTS.md` for full analysis.

## References

- Clair & Letscher (2007) — "Optimal Strategies for Sports Betting Pools", *Operations Research*
- Haugh & Singal (2021) — "How to Play Fantasy Sports Strategically", *Management Science*
- Brill, Wyner & Barnett (2024) — "Entropy-Based Strategies for Multi-Bracket Pools", *Entropy*
