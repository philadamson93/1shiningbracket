# Code Review Findings — March Madness Bracket Optimizer

**Date:** 2026-03-19
**Scope:** Full codebase review — data sources, simulation logic, UI, tests

---

## CRITICAL: Data Source Name Mismatches

These are bugs that cause bracket teams to have **missing or fragmented probability data**, directly affecting bracket quality.

### 1. SMU data is split across 3 different keys (CRITICAL)

The bracket uses `"SMU"` as the Midwest 11-seed. But data flows in under three different names:

| Source | Raw name | Normalizes to | Bracket match? |
|--------|----------|---------------|----------------|
| Model (Paine) | `Southern Methodist` | `Southern Methodist` | NO |
| Market (DK) | `MOH/SMU` | `SMU` | YES — but then `normalize_team_name("SMU")` → `"Southern Methodist"` |
| Public (ESPN) | `M-OH/SMU` | `M-OH/SMU` (unmapped) | NO |

**Root cause:** `TEAM_ALIASES` has two entries that both claim `"SMU"`:
- Line 97: `"SMU": ["SMU", "SMU Mustangs", "MOH/SMU"]`
- Line 136: `"Southern Methodist": ["Southern Methodist", "SMU", "SMU Mustangs"]`

The second entry overwrites the first in `_ALIAS_TO_CANONICAL`, so `normalize("SMU")` → `"Southern Methodist"`, NOT `"SMU"`.

Additionally, `"M-OH/SMU"` (with hyphens) is not in any alias list — only `"MOH/SMU"` (without hyphens) is.

**Impact:** SMU's blended probability uses only partial data. Model data lives under `"Southern Methodist"`, market data under `"SMU"`, and public data under `"M-OH/SMU"`. The `blend_probs` function never merges them.

**Files:** `src/data_loader.py:97,136`, `src/sim_engine.py:60`

### 2. "North Dakota St." (Paine) ≠ "North Dakota St" (bracket) (HIGH)

The Paine CSV uses `"North Dakota St."` (with trailing period). The bracket uses `"North Dakota St"` (no period). The alias list includes `"North Dakota St"` and `"N. Dak. St."` but NOT `"North Dakota St."` (with period only after "St").

**Impact:** North Dakota State has zero model probability in the blended data. Falls back to 0.001 defaults in `get_game_prob`.

**Files:** `src/data_loader.py:106`

### 3. Texas has zero market data (HIGH)

The bracket has `"Texas"` as the West 11-seed (First Four winner over NC State). The DK scraper has `"TX/NCST"` for this slot, which normalizes to `"NC State"`, not `"Texas"`.

**Impact:** Texas has no DK odds data. Blended probability uses only model data for Texas.

**Files:** `src/scrape_dk_odds.py:266-273`, `src/data_loader.py`

### 4. Lehigh vs "Prairie View A&M Panthers" (MEDIUM)

ESPN has `"Prairie View A&M Panthers"` as the South 16-seed First Four team. The bracket uses `"Lehigh"` (the other First Four team). ESPN's `"Prairie View A&M Panthers"` doesn't normalize to anything — no alias exists. This means Lehigh's public pick data is missing from the ESPN source.

**Files:** `src/data_loader.py` (missing alias for Prairie View)

---

## HIGH: Alias System Bugs

### 5. Duplicate/conflicting alias entries

| Alias | Maps to (final) | Also claimed by | Bug? |
|-------|-----------------|-----------------|------|
| `"smu"` | `"Southern Methodist"` | `"SMU"` | YES — bracket uses `"SMU"` |
| `"smu mustangs"` | `"Southern Methodist"` | `"SMU"` | YES |
| `"sdsu"` | `"South Dakota State"` | `"San Diego State"` | Latent — neither in 2026 bracket |
| `"michigan"` (key) | `"Michigan"` | Duplicate dict key (line 66 + 178) | No data loss, but sloppy |

**Files:** `src/data_loader.py:97,130,136,137,66,178`

### 6. Prefix matching can return wrong canonical name

`normalize_team_name` falls back to prefix matching: `name.lower().startswith(alias + " ")`. This iterates `_ALIAS_TO_CANONICAL` in insertion order and returns on the FIRST match.

Verified bugs:
- `"Michigan State Basketball Team"` → `"Michigan"` (should be `"Michigan State"`)
- `"North Carolina Wilmington Panthers"` → `"North Carolina"` (should be `"North Carolina-Wilmington"`)

In practice, most names are in the exact-match alias list, so this rarely fires. But it's a correctness landmine.

**Files:** `src/data_loader.py:196-203`

---

## MEDIUM: Simulation & Scoring Logic

### 7. `score_bracket()` crashes if `_cached_game_tree` not initialized

`sim_engine.py:287` — `score_bracket` unpacks the module-level `_cached_game_tree` which is `None` until `get_game_tree()` is called. Any caller that uses `score_bracket` before initializing the cache gets `TypeError: cannot unpack non-iterable NoneType object`.

The safe alternative `score_bracket_with_tree()` exists and is used in most places, but `score_bracket` is still exported and used in the `__main__` block (after manual init).

**Files:** `src/sim_engine.py:287,298`

### 8. `backtest_kelly.py` extracts actual outcomes with fallback bugs

**8a.** `extract_actual_outcome` line 196: Any team with non-zero, non-1.0 probability for `rd6_win` (Final Four) gets `reached = 5` (championship game). But this can include teams that didn't make the FF — the raw 538 file might have their last forecast before FF games were played, leaving probabilities as predictions, not outcomes.

**8b.** Line 226-228: When two teams have identical `max_round`, the function defaults to `team_a` instead of properly determining the winner. This can produce incorrect actual outcomes for scoring.

**Files:** `backtest/backtest_kelly.py:196,226`

### 9. `bracket_maker.py` `print_summary` hardcodes "/10"

Lines 159, 164, 176 all print `{count}/10`, but the number of brackets is variable (could be 1, 3, or any number from the pool config).

**Files:** `src/bracket_maker.py:159,164,176`

---

## MEDIUM: Data Quality Concerns

### 10. DK scraper mixes real odds with hand-estimated values

`scrape_dk_odds.py` has real DK/BetMGM/FanDuel odds for championship and FF futures, and real moneylines for R1. But `s16_implied_est` and `e8_implied_est` fields are described as "model consensus estimates" — many marked with `# est.` comments. These are hand-entered approximations, not from actual sportsbook markets.

Per the project's own rule: "Only use measured data; no uncalibrated estimates."

The S16 and E8 probability columns flow through normalization (S16 scaled to sum=4 per region, E8 scaled to sum=2) but the underlying values are still educated guesses.

**Files:** `src/scrape_dk_odds.py:61-62` (s16_implied_est, e8_implied_est throughout)

### 11. R1 vig removal uses fixed 2.5% assumption

Line 647: `r1_implied = min(0.999, max(0.001, r1_raw / 1.025))` — divides by a constant 1.025 (assumes 2.5% vig). But since both sides of every R1 moneyline are in the TEAMS dict, the actual vig could be computed per-game as `raw_a + raw_b` and properly removed.

**Files:** `src/scrape_dk_odds.py:647`

### 12. Missing R2 in DK odds — interpolated as geometric mean

DK CSV has R1, S16, E8, F4, Championship but no R2. `blend_probs` interpolates: `R2 = sqrt(R1 * S16)`. This is a reasonable approximation but isn't from measured data. R2 probabilities affect all second-round game simulations.

**Files:** `src/sim_engine.py:190-192`

---

## MEDIUM: ESPN Data Issues

### 13. ESPN bracket count display is wrong by ~16x

`scrape_espn_picks.py:93`: `total_brackets = sum(r["pick_count"] for r in rows if r["round"] == "R1") // 2`

There are 64 R1 rows (32 games × 2 outcomes). Sum of all counts = 32 × total_brackets. Dividing by 2 gives 16 × actual. The formula should divide by 64 (or just take one game's two-team sum).

Verified: sum = 494,522,596. Formula gives 247M. Actual per-game total ~15.5M brackets.

This only affects the printed summary, not the pick percentages.

**Files:** `src/scrape_espn_picks.py:93`

---

## LOW: Code Quality

### 14. `bracket_to_display` accepts `game_tree` parameter but never uses it

The function signature is `bracket_to_display(bracket, game_tree=None)` but the body uses hardcoded index arithmetic. Multiple callers pass `game_tree` unnecessarily.

**Files:** `src/sim_engine.py:481`

### 15. `backtest_kelly.py` rebuilds `feeds_into` on every `flip_game` call

Lines 285-288 rebuild the `feeds_into` dict from scratch inside `flip_game`, which is called thousands of times during hill-climbing. The main `sim_engine.py` has `build_feeds_into()` to cache this. The backtest's version is O(63) per call × thousands of calls = wasted computation.

**Files:** `backtest/backtest_kelly.py:285-288`

### 16. Bare relative imports in src/ modules

`sim_engine.py:16`: `from data_loader import ...` — works only if Python's path includes `src/`. The backtest and UI files manually add `sys.path.insert(0, ...)` but this is fragile. Running `python3 src/sim_engine.py` from the project root fails.

**Files:** `src/sim_engine.py:16`, `src/bracket_maker.py:23`

### 17. UI What-If uses current sidebar params, not generation params

The What-If tab computes Kelly EV using the current `wealth_base` slider value, but the original bracket's Kelly EV was computed with potentially different params during generation. If the user changes Advanced Parameters after generating, the comparison is misleading.

**Files:** `ui/app.py:815-818`

---

## NO TEST SUITE

There are **zero tests** anywhere in the codebase. The following functions are critical and untested:

### Must-test (data correctness)
- `normalize_team_name` — alias lookup, prefix matching, edge cases
- `load_dk_odds` / `load_espn_api_picks` / `_load_paine_csv` — CSV parsing + normalization
- Cross-source alignment: all 64 bracket teams present in blended probs
- `blend_probs` — R2 interpolation, fallback logic when one source is missing

### Must-test (simulation correctness)
- `build_game_tree` — 63 games, correct feeder structure, round assignment
- `get_game_prob` — normalization, default fallback for missing teams
- `simulate_tournament` — deterministic with seed, 63 non-None outcomes
- `score_bracket` / `score_bracket_with_tree` — known bracket vs known outcome
- `perturb_probs` — probabilities stay in (0,1), symmetry
- `flip_game` — cascade correctness, bracket consistency after flip

### Must-test (optimization)
- `estimate_position` — boundary conditions, field_size edge cases
- `compute_kelly_ev` — known simple cases
- `hill_climb` — improves or stays same (never worsens)
- `make_chalk_bracket` — always picks favorite

### Must-test (UI)
- `json_to_flat_bracket` — round-trip with `bracket_to_display`
- `compute_stats` — with known precomputed data
- `render_bracket_html` — produces valid HTML, all 63 games present

---

## UI Testing Strategy

### Automated (headless)
Streamlit provides `streamlit.testing.v1.AppTest` for headless testing:
```python
from streamlit.testing.v1 import AppTest
at = AppTest.from_file("ui/app.py")
at.run()
# Check initial state renders without errors
assert not at.exception
# Interact with sidebar widgets
at.slider[0].set_value(100)  # field_size
at.button[0].click()  # Generate
at.run()
assert "brackets" in at.session_state
```

Best for: smoke tests, regression, widget interaction flows.

### Interactive (manual checklist)
1. **Welcome state:** Championship probability table renders, all top teams present
2. **Generate single bracket:** Click Generate → bracket displays, all 63 games filled
3. **Bracket Visual view:** All 4 regions render, connectors display, champion banner shows
4. **Bracket Detail view:** Expand each region, verify matchups/seeds correct
5. **Analysis tab:** Champion distribution chart, score histogram, round-by-round table
6. **Leverage tab:** All bracket teams present, leverage values reasonable (0.5-3.0x)
7. **What-If tab:** Flip a game → see cascading changes, metrics update
8. **What-If Apply:** Apply flip → bracket updates, Visual view reflects change
9. **Portfolio mode:** Generate 3+ brackets → different champions, Portfolio tab shows diversity
10. **Load Saved:** Load from JSON → bracket renders correctly
11. **Download JSON:** Download → file valid JSON, re-loadable
12. **Parameter changes:** Change sigma/model_weight → Generate → different bracket
13. **Custom payout:** Enter custom percentages → validates correctly

### Browser automation (Playwright/Selenium)
For full E2E coverage of the Streamlit app, Playwright is the best option:
```python
from playwright.sync_api import sync_playwright
# Navigate to http://localhost:8501
# Interact with Streamlit widgets via their DOM selectors
# Screenshot comparison for bracket rendering
```

Best for: visual regression, cross-browser testing.

---

## Summary of Fix Priority

| # | Severity | Issue | Est. Effort |
|---|----------|-------|-------------|
| 1 | CRITICAL | SMU alias collision → data fragmentation | Small — fix aliases |
| 2 | CRITICAL | "North Dakota St." missing alias | Tiny — add alias |
| 3 | HIGH | Texas ↔ TX/NCST DK mismatch | Small — fix DK entry or alias |
| 4 | MEDIUM | Lehigh/Prairie View ESPN mismatch | Small — add alias |
| 5 | HIGH | All alias collisions (SMU, SDSU) | Small — deduplicate |
| 6 | HIGH | Prefix matching returns wrong team | Medium — fix algorithm |
| 7 | MEDIUM | score_bracket cache crash | Tiny — guard or deprecate |
| 8 | MEDIUM | Backtest actual outcome fallbacks | Medium — improve logic |
| 9 | LOW | Hardcoded "/10" in print_summary | Tiny |
| 10 | MEDIUM | S16/E8 hand-estimates in DK scraper | Large — need real data source |
| 11 | LOW | R1 vig removal approximation | Small — use both sides |
| 13 | LOW | ESPN bracket count display | Tiny |
| — | HIGH | **No tests at all** | Medium — write test suite |
