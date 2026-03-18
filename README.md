# March Madness Bracket Optimizer

Generate optimized brackets for NCAA tournament pools using simulation-based portfolio optimization.

The optimizer simulates thousands of tournament outcomes, generates opponent brackets from ESPN public pick data (172M+ brackets), and hill-climbs each of your bracket's 63 game picks to maximize expected payout in your specific pool. Multiple brackets across pools are diversified using a Kelly (log-wealth) portfolio objective — naturally allocating contrarian picks to large pools and chalk to small ones.

## Data Sources

| Source | What | Coverage |
|--------|------|----------|
| **ESPN Gambit API** | Public pick percentages (172M brackets) | 2023-2026 |
| **Neil Paine composite** | 6-model analytical probabilities | 2026 |
| **DraftKings** | Market-implied advancement odds | 2026 |
| **FiveThirtyEight** | Historical model probabilities | 2017-2023 |
| **mRchmadness** | Historical ESPN pick distributions | 2016-2025 |

## Usage

### Command Line

```bash
# Refresh ESPN public pick data
python3 src/scrape_espn_picks.py

# Generate brackets (quick ~5s, for iteration)
python3 src/bracket_maker.py --sims 200

# Generate brackets (production ~5 min)
python3 src/bracket_maker.py --sims 10000

# Output: output/final_brackets.json (10 brackets, one per pool)
```

### Streamlit UI

```bash
pip install streamlit pandas
streamlit run ui/app.py
```

The UI lets you:
- Configure pool size, payout structure, and number of brackets
- Generate optimized brackets with a progress indicator
- View color-coded bracket trees (green = value, red = fade)
- Explore the full leverage table (all 64 teams × 6 rounds)
- Run what-if analysis (flip any pick, see the EV impact)
- Compare brackets side-by-side in portfolio view
- Load previously saved brackets from `final_brackets.json`

### Inputs

**Pool configuration** (edit `POOLS` list in `src/bracket_maker.py` or use the UI sidebar):

| Parameter | Description | Default |
|-----------|-------------|---------|
| `field_size` | Number of entries in your pool | 250 |
| `payout` | Prize distribution by finishing position | 60/20/10/5/3/2 |

**Model parameters** (CLI flags or UI sidebar):

| Flag | Description | Default |
|------|-------------|---------|
| `--sims` | Number of Monte Carlo tournament simulations | 200 |
| `--sigma` | Model uncertainty in logit space (calibrated from 538 data) | 0.27 |
| `--model-weight` | Blend: 0 = pure market, 1 = pure model | 0.35 |
| `--wealth-base` | Kelly diversification: lower = "win at least 1 pool" | 0.3 |
| `--seed` | Random seed for reproducibility | 42 |

## How It Works

1. **Blend** model probabilities (Paine) with market odds (DraftKings) for each team × round
2. **Simulate** M tournament outcomes from perturbed probabilities (model separation — truth ≠ model)
3. **Generate** N opponent brackets per outcome from ESPN public pick distribution
4. **Hill-climb** each bracket: flip individual game picks, keep if expected payout improves (Clair & Letscher 2007)
5. **Portfolio optimization**: each bracket maximizes marginal log-wealth contribution given prior brackets (Kelly criterion + Haugh & Singal 2021 greedy submodular selection)

Different pool sizes naturally produce different brackets — small pools favor chalk, large pools favor leverage (contrarian picks where model probability exceeds public pick rate).

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

Tested on 4 held-out years (2018, 2021, 2022, 2023) using 538 pre-tournament predictions and ESPN public picks, scored against actual tournament outcomes and a field of 50,000 simulated ESPN brackets.

| Year | Champion | Chalk Score | Optimizer Best | vs Chalk | ESPN Percentile |
|------|----------|-------------|---------------|----------|----------------|
| 2018 | Villanova | 1220 | 1280 | +60 | 95.9% |
| 2021 | Baylor | 720 | 930 | +210 | 83.0% |
| 2022 | Kansas | 820 | 780 | -40 | 76.1% |
| 2023 | UConn | 470 | 470 | +0 | 97.1% |

See `docs/RESULTS.md` for full analysis.

## References

- Clair & Letscher (2007) — "Optimal Strategies for Sports Betting Pools", *Operations Research*
- Haugh & Singal (2021) — "How to Play Fantasy Sports Strategically", *Management Science*
- Brill, Wyner & Barnett (2024) — "Entropy-Based Strategies for Multi-Bracket Pools", *Entropy*
