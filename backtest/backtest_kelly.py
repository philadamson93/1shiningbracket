"""
Historical validation: run the Kelly portfolio optimizer on 2018-2023 data
and score against actual tournament outcomes.

For each year:
1. Reconstruct bracket structure from 538 raw data (teams, regions, seeds)
2. Extract actual 63-game outcome from final forecast date
3. Run optimizer with that year's 538 model probs + ESPN/mRchmadness public picks
4. Score optimizer brackets, chalk bracket, and random opponents against actual outcome
5. Report: did the optimizer beat chalk? Beat the field?
"""

import csv
import math
import random
import sys
import time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from data_loader import load_year_data, normalize_team_name
from sim_engine import (
    simulate_tournament, make_chalk_bracket, generate_opponent,
    score_bracket_with_tree, perturb_probs, blend_probs, estimate_position,
    bracket_to_display, get_game_prob, compute_kelly_ev,
    build_feeds_into, build_locked_games, hill_climb,
    SCORING, ROUND_NAMES, REGIONS,
)

# =============================================================================
# CONFIG
# =============================================================================

RAW_538_FILES = {
    2018: "data/538_ncaa_forecasts_2018.csv",
    2021: "data/538_ncaa_forecasts_2021.csv",
    2022: "data/538_ncaa_forecasts_2022.csv",
    2023: "data/538_ncaa_forecasts_2023_final.csv",
}

KNOWN_CHAMPIONS = {
    2018: "Villanova", 2021: "Baylor", 2022: "Kansas", 2023: "UConn",
}

# Standard NCAA seed order within a region for bracket pairing
SEED_ORDER = [1, 16, 8, 9, 5, 12, 4, 13, 6, 11, 3, 14, 7, 10, 2, 15]

# 538 raw column → round reached
# rd2_win = won R1 game, rd3_win = won R2 game, etc.
ROUND_COL = ["rd2_win", "rd3_win", "rd4_win", "rd5_win", "rd6_win", "rd7_win"]
OUR_ROUNDS = ["R1", "R2", "S16", "E8", "F4", "Championship"]

M_SIMS = 1000
N_OPPONENTS = 250
SIGMA = 0.27
FIELD_SIZE = 250
PAYOUT = {1: 0.60, 2: 0.20, 3: 0.10, 4: 0.05, 5: 0.03, 6: 0.02}
WEALTH_BASE = 1.0
NUM_BRACKETS = 10
N_RESTARTS = 10             # Hill-climb restarts per bracket


# =============================================================================
# BRACKET RECONSTRUCTION
# =============================================================================

def load_raw_538(filepath, year):
    """
    Load raw 538 forecast file. Returns:
    - pre_rows: first forecast date (pre-tournament predictions)
    - post_rows: last forecast date (actual outcomes encoded)
    """
    rows = []
    with open(filepath) as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("gender", "mens") == "mens" or "gender" not in row:
                rows.append(row)

    dates = sorted(set(r["forecast_date"] for r in rows))
    first_date = dates[0]
    last_date = dates[-1]

    pre_rows = [r for r in rows if r["forecast_date"] == first_date]
    post_rows = [r for r in rows if r["forecast_date"] == last_date]

    return pre_rows, post_rows


def build_year_bracket(pre_rows):
    """
    Build bracket structure from 538 pre-tournament data.
    Returns: dict like sim_engine.BRACKET = {region: [(team, seed), ...]}
    with 16 teams per region in standard NCAA bracket order.
    """
    # Group by region, collect (seed, team_name)
    by_region = defaultdict(list)
    for row in pre_rows:
        region = row["team_region"]
        seed_str = row["team_seed"]
        try:
            seed = int(seed_str)
        except ValueError:
            seed = int(seed_str.rstrip("abcd"))  # play-in: "11a", "11b", etc.
        name = normalize_team_name(row["team_name"])
        by_region[region].append((seed, name))

    # For play-in seeds (multiple teams with same seed), keep one with higher rating
    bracket = {}
    region_names = sorted(by_region.keys())

    for region in region_names:
        teams = by_region[region]
        # Deduplicate by seed: keep highest-rated team per seed
        by_seed = {}
        for seed, name in teams:
            if seed not in by_seed:
                by_seed[seed] = name
            # If duplicate seed, the first one in data is fine (pre-tourney order)

        # Build bracket in standard seed order
        region_bracket = []
        for seed in SEED_ORDER:
            name = by_seed.get(seed, f"TBD-{seed}")
            region_bracket.append((name, seed))

        bracket[region] = region_bracket

    return bracket, region_names


def build_game_tree_for_year(bracket, region_names):
    """
    Build game tree from a historical bracket structure.
    Same logic as sim_engine.build_game_tree() but with arbitrary bracket.

    Returns: (r1_matchups, feeder_games, game_round, game_points)
    """
    r1_matchups = []
    for region in region_names:
        teams = bracket[region]
        for i in range(8):
            r1_matchups.append((teams[i * 2][0], teams[i * 2 + 1][0]))

    feeder_games = {}
    for region_idx in range(4):
        for j in range(4):
            feeder_games[32 + region_idx * 4 + j] = (
                region_idx * 8 + j * 2, region_idx * 8 + j * 2 + 1)
    for region_idx in range(4):
        for j in range(2):
            feeder_games[48 + region_idx * 2 + j] = (
                32 + region_idx * 4 + j * 2, 32 + region_idx * 4 + j * 2 + 1)
    for region_idx in range(4):
        feeder_games[56 + region_idx] = (
            48 + region_idx * 2, 48 + region_idx * 2 + 1)
    feeder_games[60] = (56, 57)
    feeder_games[61] = (58, 59)
    feeder_games[62] = (60, 61)

    game_round = []
    game_points = []
    round_sizes = [32, 16, 8, 4, 2, 1]
    for rd_idx, rd_name in enumerate(ROUND_NAMES):
        pts = SCORING[rd_name]
        for _ in range(round_sizes[rd_idx]):
            game_round.append(rd_name)
            game_points.append(pts)

    return r1_matchups, feeder_games, game_round, game_points


def extract_actual_outcome(post_rows, bracket, region_names, year):
    """
    Extract the actual 63-game outcome from final forecast data.

    On the final date, rd{X}_win = 1.0 means team advanced past that round.
    We walk through the bracket structure and determine each game's winner.
    """
    # Build lookup: team_name → max round reached (0-6)
    max_round = {}
    for row in post_rows:
        name = normalize_team_name(row["team_name"])
        reached = 0
        for i, col in enumerate(ROUND_COL):
            val = float(row.get(col, 0))
            if val == 1.0:
                reached = i + 1  # 1=past R1, 2=past R2, etc.
            elif val > 0 and val < 1.0:
                # Championship game not yet played — use known champion
                if i == 5:  # rd7_win = championship
                    champion = KNOWN_CHAMPIONS.get(year, "")
                    if name == champion:
                        reached = 6
                elif i == 4:  # rd6_win = made championship game
                    # Check if this team made the championship game
                    # (val > 0 means they're still alive at this point)
                    reached = 5
        max_round[name] = reached

    # Walk through bracket to determine each game's winner
    game_tree = build_game_tree_for_year(bracket, region_names)
    r1_matchups, feeder_games, game_round, game_points = game_tree

    outcome = [None] * 63
    for g in range(63):
        if g < 32:
            team_a, team_b = r1_matchups[g]
        else:
            fa, fb = feeder_games[g]
            team_a = outcome[fa]
            team_b = outcome[fb]

        if team_a is None or team_b is None:
            outcome[g] = team_a or team_b
            continue

        # The team that advanced further wins
        ra = max_round.get(team_a, 0)
        rb = max_round.get(team_b, 0)

        if ra > rb:
            outcome[g] = team_a
        elif rb > ra:
            outcome[g] = team_b
        else:
            # Both reached same round — one of them lost at this stage
            # The one whose advancement at THIS round = 1.0 wins
            outcome[g] = team_a  # fallback

    return outcome, game_tree


# =============================================================================
# HILL-CLIMBING (uses shared sim_engine.hill_climb with restarts)
# =============================================================================

def hill_climb_with_restarts(start_bracket, game_tree, probs, precomputed,
                              field_size, payout, existing_payouts, wealth_base,
                              n_restarts=N_RESTARTS):
    """Multi-start hill-climb: run n_restarts times, keep best."""
    feeds_into = build_feeds_into(game_tree)
    locked = build_locked_games(probs, game_tree)

    best_bracket = None
    best_ev = float("-inf")

    for r in range(n_restarts):
        bracket, ev = hill_climb(
            start_bracket, game_tree, probs, precomputed,
            field_size, payout, existing_payouts, wealth_base,
            feeds_into, locked, shuffle=(r > 0))
        if ev > best_ev:
            best_bracket = bracket
            best_ev = ev

    return best_bracket


def precompute_for_year(model_probs, public_probs, sigma, M, N, game_tree):
    """Precompute sims for one year."""
    results = []
    for _ in range(M):
        truth = perturb_probs(model_probs, sigma)
        outcome = simulate_tournament(truth, game_tree)
        opp_scores = []
        for _ in range(N):
            opp = generate_opponent(public_probs, game_tree)
            opp_scores.append(score_bracket_with_tree(opp, outcome, game_tree))
        opp_scores.sort(reverse=True)
        results.append((outcome, opp_scores))
    return results


# =============================================================================
# MAIN BACKTEST
# =============================================================================

def run_backtest():
    random.seed(42)

    print("=" * 90)
    print("HISTORICAL VALIDATION — Kelly Portfolio Optimizer vs Chalk vs Field")
    print(f"M={M_SIMS} sims | N={N_OPPONENTS} opponents | K={NUM_BRACKETS} brackets | Sigma={SIGMA}")
    print("=" * 90)

    all_results = []

    for year in sorted(RAW_538_FILES.keys()):
        print(f"\n{'─' * 90}")
        print(f"  {year}")
        print(f"{'─' * 90}")

        # Load data
        data = load_year_data(year)
        model_probs = data["model"]
        public_probs = data["public"]
        if not model_probs or not public_probs:
            print(f"  SKIP — missing model or public data")
            continue

        print(f"  Model:  {data['sources'].get('model', 'N/A')} ({len(model_probs)} teams)")
        print(f"  Public: {data['sources'].get('public', 'N/A')} ({len(public_probs)} teams)")

        # Reconstruct bracket + actual outcome
        pre_rows, post_rows = load_raw_538(RAW_538_FILES[year], year)
        bracket, region_names = build_year_bracket(pre_rows)
        actual_outcome, game_tree = extract_actual_outcome(
            post_rows, bracket, region_names, year)

        actual_champ = actual_outcome[62]
        known_champ = KNOWN_CHAMPIONS.get(year, "?")
        print(f"  Actual champion: {actual_champ} (expected: {known_champ})")
        if actual_champ != known_champ:
            print(f"  WARNING: champion mismatch!")

        # Score chalk bracket against actual
        chalk = make_chalk_bracket(model_probs, game_tree)
        chalk_score = score_bracket_with_tree(chalk, actual_outcome, game_tree)
        chalk_champ = chalk[62]
        print(f"  Chalk: {chalk_champ} ({chalk_score} pts)")

        # Score public chalk (ESPN favorite picks)
        pub_chalk = make_chalk_bracket(public_probs, game_tree)
        pub_score = score_bracket_with_tree(pub_chalk, actual_outcome, game_tree)
        pub_champ = pub_chalk[62]
        print(f"  Public chalk: {pub_champ} ({pub_score} pts)")

        # Generate opponents to establish baseline
        opp_scores = []
        for _ in range(1000):
            opp = generate_opponent(public_probs, game_tree)
            opp_scores.append(score_bracket_with_tree(opp, actual_outcome, game_tree))
        opp_median = sorted(opp_scores)[500]
        opp_p90 = sorted(opp_scores)[900]
        opp_max = max(opp_scores)
        print(f"  Field: median={opp_median} p90={opp_p90} max={opp_max}")

        # Run optimizer: generate K brackets with Kelly portfolio
        print(f"  Running optimizer (K={NUM_BRACKETS}, M={M_SIMS}, restarts={N_RESTARTS})...")
        t0 = time.time()
        precomputed = precompute_for_year(
            model_probs, public_probs, SIGMA, M_SIMS, N_OPPONENTS, game_tree)

        portfolio = []
        portfolio_payouts = []  # (bracket, field_size, payout)
        opt_brackets = []

        for k in range(NUM_BRACKETS):
            existing = [0.0] * len(precomputed)
            for pb, pf, pp in portfolio_payouts:
                for si, (out, ops) in enumerate(precomputed):
                    sc = score_bracket_with_tree(pb, out, game_tree)
                    ps = estimate_position(sc, ops, FIELD_SIZE)
                    existing[si] += pp.get(ps, 0)

            start = make_chalk_bracket(model_probs, game_tree)
            optimized = hill_climb_with_restarts(
                start, game_tree, model_probs, precomputed,
                FIELD_SIZE, PAYOUT, existing, WEALTH_BASE)
            opt_brackets.append(optimized)
            portfolio_payouts.append((optimized, FIELD_SIZE, PAYOUT))

        elapsed = time.time() - t0

        # Score optimizer brackets against ACTUAL outcome
        opt_scores = []
        opt_champs = []
        for b in opt_brackets:
            sc = score_bracket_with_tree(b, actual_outcome, game_tree)
            opt_scores.append(sc)
            opt_champs.append(b[62])

        best_opt = max(opt_scores)
        best_idx = opt_scores.index(best_opt)

        # Percentile of best bracket in field
        beats = sum(1 for s in opp_scores if best_opt > s)
        percentile = beats / len(opp_scores) * 100

        print(f"  Optimizer ({elapsed:.1f}s):")
        print(f"    Champions: {opt_champs}")
        print(f"    Scores: {opt_scores}")
        print(f"    Best: {best_opt} pts (bracket {best_idx+1}, champ={opt_champs[best_idx]})")
        print(f"    Field percentile: {percentile:.1f}%")
        print(f"    vs Chalk: {best_opt - chalk_score:+d} pts")

        # Did any bracket pick the actual champion?
        champ_hit = actual_champ in opt_champs
        print(f"    Picked actual champion: {'YES' if champ_hit else 'NO'} ({actual_champ})")

        all_results.append({
            "year": year,
            "actual_champ": actual_champ,
            "chalk_score": chalk_score,
            "chalk_champ": chalk_champ,
            "pub_score": pub_score,
            "best_opt_score": best_opt,
            "opt_champs": opt_champs,
            "percentile": percentile,
            "champ_hit": champ_hit,
            "opp_median": opp_median,
        })

    # Summary
    print(f"\n{'=' * 90}")
    print(f"SUMMARY")
    print(f"{'=' * 90}")
    print(f"{'Year':<6} {'Champ':<15} {'Chalk':>6} {'Public':>7} {'Optimizer':>10} "
          f"{'vs Chalk':>9} {'Pctile':>7} {'Hit?':>5}")
    print("-" * 70)
    for r in all_results:
        print(f"{r['year']:<6} {r['actual_champ']:<15} {r['chalk_score']:>6} "
              f"{r['pub_score']:>7} {r['best_opt_score']:>10} "
              f"{r['best_opt_score']-r['chalk_score']:>+9} "
              f"{r['percentile']:>6.1f}% {'Y' if r['champ_hit'] else 'N':>4}")

    avg_pctile = sum(r["percentile"] for r in all_results) / len(all_results) if all_results else 0
    champ_hits = sum(1 for r in all_results if r["champ_hit"])
    print(f"\nAvg field percentile: {avg_pctile:.1f}%")
    print(f"Champion hits: {champ_hits}/{len(all_results)}")
    print(f"{'=' * 90}")


if __name__ == "__main__":
    run_backtest()
