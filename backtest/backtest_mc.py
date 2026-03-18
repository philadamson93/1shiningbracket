"""
Monte Carlo backtest: run the Kelly optimizer N_TRIALS times with different
random seeds per year, scoring against actual outcomes. Produces confidence
intervals on field percentile.

Randomness across trials comes from shuffled hill-climb game traversal order.
All trials share the same large sim pool for stable EV estimates.

Usage:
    python3 backtest/backtest_mc.py                # 20 trials per year
    python3 backtest/backtest_mc.py --trials 50    # 50 trials per year
"""

import argparse
import bisect
import random
import sys
import time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from data_loader import load_year_data
from sim_engine import (
    simulate_tournament, make_chalk_bracket, generate_opponent,
    score_bracket_with_tree, perturb_probs, estimate_position,
    get_game_prob, SCORING, ROUND_NAMES,
    build_feeds_into, build_locked_games, hill_climb, compute_kelly_ev,
)
from backtest_kelly import (
    load_raw_538, build_year_bracket, extract_actual_outcome,
    precompute_for_year, KNOWN_CHAMPIONS, RAW_538_FILES,
)

# =============================================================================
# CONFIG
# =============================================================================

SIM_POOL_SIZE = 5000    # Shared sim pool per year (all trials use this)
N_OPPONENTS = 250
SIGMA = 0.27
FIELD_SIZE = 250
PAYOUT = {1: 0.60, 2: 0.20, 3: 0.10, 4: 0.05, 5: 0.03, 6: 0.02}
WEALTH_BASE = 1.0
NUM_BRACKETS = 10
N_FIELD = 10000         # Opponents for percentile scoring


def run_one_trial(model_probs, game_tree, sim_pool,
                  actual_outcome, field_scores,
                  feeds_into, locked):
    """
    One trial: build 10-bracket Kelly portfolio using shuffled hill-climb,
    score against actuals, return best percentile.
    """
    existing_payouts = [0.0] * len(sim_pool)
    opt_brackets = []

    for k in range(NUM_BRACKETS):
        start = make_chalk_bracket(model_probs, game_tree)
        bracket, _ = hill_climb(
            start, game_tree, model_probs, sim_pool,
            FIELD_SIZE, PAYOUT, existing_payouts, WEALTH_BASE,
            feeds_into, locked, shuffle=True)
        opt_brackets.append(bracket)

        # Incremental update
        for si, (outcome, opp_scores) in enumerate(sim_pool):
            sc = score_bracket_with_tree(bracket, outcome, game_tree)
            pos = estimate_position(sc, opp_scores, FIELD_SIZE)
            existing_payouts[si] += PAYOUT.get(pos, 0)

    # Score against actual
    opt_scores = [score_bracket_with_tree(b, actual_outcome, game_tree)
                  for b in opt_brackets]
    best_score = max(opt_scores)
    champions = [b[62] for b in opt_brackets]
    champ_hit = actual_outcome[62] in champions
    pctile = bisect.bisect_left(field_scores, best_score) / len(field_scores) * 100

    return best_score, pctile, champ_hit, champions


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--trials", type=int, default=20)
    parser.add_argument("--pool-size", type=int, default=SIM_POOL_SIZE)
    args = parser.parse_args()

    print("=" * 90)
    print(f"MONTE CARLO BACKTEST — {args.trials} trials/year, {args.pool_size} shared sims")
    print(f"K={NUM_BRACKETS} brackets | Sigma={SIGMA} | Field={N_FIELD} opponents")
    print("=" * 90)

    all_year_results = {}

    for year in sorted(RAW_538_FILES.keys()):
        print(f"\n{'─' * 90}")
        print(f"  {year}")
        print(f"{'─' * 90}")

        data = load_year_data(year)
        model_probs = data["model"]
        public_probs = data["public"]
        if not model_probs or not public_probs:
            print(f"  SKIP — missing data")
            continue

        print(f"  Model: {data['sources'].get('model')} | Public: {data['sources'].get('public')}")

        pre_rows, post_rows = load_raw_538(RAW_538_FILES[year], year)
        bracket, region_names = build_year_bracket(pre_rows)
        actual_outcome, game_tree = extract_actual_outcome(
            post_rows, bracket, region_names, year)
        actual_champ = actual_outcome[62]

        chalk = make_chalk_bracket(model_probs, game_tree)
        chalk_score = score_bracket_with_tree(chalk, actual_outcome, game_tree)
        print(f"  Actual champ: {actual_champ} | Chalk: {chalk[62]} ({chalk_score} pts)")

        # Field (one-time)
        print(f"  Generating {N_FIELD} field opponents...")
        random.seed(0)
        field_scores = sorted(
            score_bracket_with_tree(
                generate_opponent(public_probs, game_tree), actual_outcome, game_tree)
            for _ in range(N_FIELD))

        # Shared sim pool (one-time)
        print(f"  Precomputing {args.pool_size} shared sims...")
        random.seed(42)
        sim_pool = precompute_for_year(
            model_probs, public_probs, SIGMA, args.pool_size, N_OPPONENTS, game_tree)

        # Static structures
        feeds_into = build_feeds_into(game_tree)
        locked = build_locked_games(model_probs, game_tree)

        # Trials
        print(f"  Running {args.trials} trials...")
        t0 = time.time()
        trial_results = []

        for trial in range(args.trials):
            random.seed(2000 + trial * 137)
            best_score, pctile, champ_hit, champions = run_one_trial(
                model_probs, game_tree, sim_pool,
                actual_outcome, field_scores, feeds_into, locked)
            trial_results.append({
                "score": best_score, "pctile": pctile,
                "champ_hit": champ_hit, "unique_champs": len(set(champions)),
            })
            if (trial + 1) % 5 == 0:
                elapsed = time.time() - t0
                rate = (trial + 1) / elapsed
                print(f"    {trial+1}/{args.trials} "
                      f"(score={best_score}, pctile={pctile:.1f}%) "
                      f"[{(args.trials-trial-1)/rate:.0f}s left]")

        elapsed = time.time() - t0
        scores = sorted(r["score"] for r in trial_results)
        pctiles = sorted(r["pctile"] for r in trial_results)
        hits = sum(r["champ_hit"] for r in trial_results)
        n = len(scores)

        print(f"\n  {year} results ({elapsed:.1f}s):")
        print(f"    Score:  median={scores[n//2]} mean={sum(scores)/n:.0f} "
              f"[{scores[max(0,int(n*0.1))]}-{scores[min(n-1,int(n*0.9))]}]")
        print(f"    Pctile: median={pctiles[n//2]:.1f}% mean={sum(pctiles)/n:.1f}% "
              f"[{pctiles[max(0,int(n*0.1))]:.1f}-{pctiles[min(n-1,int(n*0.9))]:.1f}%]")
        print(f"    vs Chalk: median {scores[n//2]-chalk_score:+d}")
        print(f"    Champion hit: {hits}/{n} ({hits/n*100:.0f}%)")

        all_year_results[year] = {
            "actual_champ": actual_champ, "chalk_score": chalk_score,
            "median_score": scores[n//2], "mean_pctile": sum(pctiles)/n,
            "p10_pctile": pctiles[max(0,int(n*0.1))],
            "median_pctile": pctiles[n//2],
            "p90_pctile": pctiles[min(n-1,int(n*0.9))],
            "champ_hit_rate": hits/n,
        }

    # Summary
    print(f"\n{'=' * 90}")
    print(f"SUMMARY")
    print(f"{'=' * 90}")
    print(f"{'Year':<6} {'Champ':<14} {'Chalk':>6} {'Median':>7} "
          f"{'vs Chalk':>9} {'Pctile 10/50/90':>20} {'Hit%':>5}")
    print("-" * 75)
    for year in sorted(all_year_results):
        r = all_year_results[year]
        print(f"{year:<6} {r['actual_champ']:<14} {r['chalk_score']:>6} "
              f"{r['median_score']:>7} {r['median_score']-r['chalk_score']:>+9} "
              f"{r['p10_pctile']:>5.1f}/{r['median_pctile']:.1f}/{r['p90_pctile']:.1f}% "
              f"{r['champ_hit_rate']*100:>4.0f}%")

    avg = sum(r["median_pctile"] for r in all_year_results.values()) / len(all_year_results)
    print(f"\nOverall median percentile: {avg:.1f}%")


if __name__ == "__main__":
    main()
