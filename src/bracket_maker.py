"""
Hill-climbing bracket generator with Kelly portfolio optimization.

Generates one optimized bracket per pool. Uses log-wealth (Kelly criterion)
portfolio objective: each bracket maximizes marginal E[log(wealth_base + total_payout)].

Pool configuration is read from pools.toml in the project root.

Usage:
    python3 src/bracket_maker.py                # Quick (M=200, ~5s)
    python3 src/bracket_maker.py --sims 10000   # Production (~4 min)
"""

import argparse
import os
import random
import json
import time
from collections import defaultdict
from pathlib import Path

from data_loader import load_year_data
from sim_engine import (
    build_game_tree, simulate_tournament, make_chalk_bracket,
    generate_opponent, score_bracket_with_tree, perturb_probs,
    blend_probs, estimate_position, bracket_to_display,
    build_feeds_into, build_locked_games, hill_climb, compute_kelly_ev,
    precompute_sims, BRACKET, REGIONS, SCORING, ROUND_NAMES,
)

# =============================================================================
# POOL CONFIGURATION
# =============================================================================

# Named presets for use in pools.toml or as fallback
PAYOUT_STEEP = {1: 0.60, 2: 0.20, 3: 0.075, 4: 0.05, 5: 0.025,
                6: 0.01, 7: 0.01, 8: 0.01, 9: 0.01}
PAYOUT_WTA = {1: 1.00}
PAYOUT_SPREAD = {1: 0.50, 2: 0.15, 3: 0.10, 4: 0.07, 5: 0.05,
                 6: 0.02, 7: 0.02, 8: 0.01, 9: 0.01}

DEFAULT_POOLS = [
    {"name": "My Pool", "field_size": 250, "payout": PAYOUT_SPREAD},
]


def load_pools(config_path="pools.toml"):
    """Load pool configuration from pools.toml. Falls back to DEFAULT_POOLS."""
    if not os.path.exists(config_path):
        return DEFAULT_POOLS

    try:
        import tomllib
    except ImportError:
        import tomli as tomllib

    with open(config_path, "rb") as f:
        config = tomllib.load(f)

    pools = []
    for entry in config.get("pool", []):
        payout_list = entry.get("payout", [50, 15, 10, 7, 5, 2, 2, 1, 1])
        payout = {i + 1: v / 100.0 for i, v in enumerate(payout_list)}
        pools.append({
            "name": entry.get("name", f"Pool {len(pools) + 1}"),
            "field_size": entry.get("field_size", 250),
            "payout": payout,
        })

    return pools if pools else DEFAULT_POOLS

# =============================================================================
# SIMULATION PARAMETERS
# =============================================================================

M_SIMS = 200
N_OPPONENTS = 400
SIGMA = 0.27
MODEL_WEIGHT = 0.35
WEALTH_BASE = 0.3       # Lower = more diversification. 0.3 ≈ "I want at least one bracket to cash"
RANDOM_SEED = 42


# =============================================================================
# PORTFOLIO CONSTRUCTION
# =============================================================================

def build_portfolio(pools, model_probs, public_probs, game_tree, precomputed,
                    wealth_base):
    """
    Greedy Kelly portfolio: for each pool, hill-climb one bracket to maximize
    marginal log-wealth given all prior brackets.
    """
    feeds_into = build_feeds_into(game_tree)
    locked = build_locked_games(model_probs, game_tree)

    results = []
    existing_payouts = [0.0] * len(precomputed)

    for i, pool in enumerate(pools):
        t0 = time.time()
        field_size = pool["field_size"]
        payout = pool["payout"]

        start = make_chalk_bracket(model_probs, game_tree)

        bracket, kelly_ev_val = hill_climb(
            start, game_tree, model_probs, precomputed,
            field_size, payout, existing_payouts, wealth_base,
            feeds_into, locked)

        # Incrementally update existing_payouts
        for si, (outcome, opp_scores) in enumerate(precomputed):
            sc = score_bracket_with_tree(bracket, outcome, game_tree)
            pos = estimate_position(sc, opp_scores, field_size)
            existing_payouts[si] += payout.get(pos, 0)

        results.append((bracket, pool, kelly_ev_val))
        elapsed = time.time() - t0

        d = bracket_to_display(bracket)
        print(f"  {pool['name']} (N={field_size}): champ={d['champion']:<16} "
              f"kelly={kelly_ev_val:.6f} ({elapsed:.1f}s)")

    return results


# =============================================================================
# OUTPUT
# =============================================================================

def print_summary(results, model_probs, public_probs, game_tree):
    print(f"\n{'=' * 95}")
    print(f"KELLY-OPTIMIZED BRACKET PORTFOLIO ({len(results)} pools)")
    print(f"{'=' * 95}")

    print(f"\n{'#':<3} {'Pool':<12} {'N':>5} {'Champion':<16} "
          f"{'E8-E':<13} {'E8-W':<13} {'E8-S':<13} {'E8-MW':<13}")
    print("-" * 95)

    champ_counts = defaultdict(int)
    ff_counts = defaultdict(int)

    for i, (bracket, pool, kelly_ev_val) in enumerate(results):
        d = bracket_to_display(bracket)
        champ = d["champion"]
        e8s = [d["regions"][r]["E8"][0] for r in REGIONS]
        champ_counts[champ] += 1
        for t in d["F4"]:
            ff_counts[t] += 1
        print(f"{i+1:<3} {pool['name']:<12} {pool['field_size']:>5} {champ:<16} "
              f"{e8s[0]:<13} {e8s[1]:<13} {e8s[2]:<13} {e8s[3]:<13}")

    print(f"\nChampion Distribution:")
    for champ, count in sorted(champ_counts.items(), key=lambda x: -x[1]):
        model_p = model_probs.get(champ, {}).get("Championship", 0) * 100
        public_p = public_probs.get(champ, {}).get("Championship", 0) * 100
        lev = model_p / public_p if public_p > 0 else 0
        n = len(results)
        print(f"  {champ:<16} {count}/{n}  "
              f"(Model:{model_p:>5.1f}% Public:{public_p:>5.1f}% Lev:{lev:.1f}x)")

    n = len(results)
    print(f"\nFinal Four Exposure:")
    for team, count in sorted(ff_counts.items(), key=lambda x: -x[1])[:12]:
        print(f"  {team:<16} {count}/{n}")

    r1_matchups = game_tree[0]
    upset_counts = defaultdict(int)
    for bracket, pool, _ in results:
        for g in range(32):
            higher, lower = r1_matchups[g]
            if bracket[g] == lower:
                upset_counts[f"{lower} over {higher}"] += 1
    if upset_counts:
        print(f"\nR1 Upsets:")
        for upset, count in sorted(upset_counts.items(), key=lambda x: -x[1]):
            print(f"  {upset} ({count}/{n})")

    print(f"\nPortfolio covers {len(champ_counts)} unique champions")


def export_brackets(results, filepath="output/final_brackets.json"):
    export = []
    for i, (bracket, pool, kelly_ev_val) in enumerate(results):
        d = bracket_to_display(bracket)
        export.append({
            "number": i + 1,
            "pool": pool["name"],
            "field_size": pool["field_size"],
            "kelly_ev": round(kelly_ev_val, 6),
            "champion": d["champion"],
            "final_four": d["F4"],
            "championship_game": d["F4_winners"],
            "regions": d["regions"],
        })
    with open(filepath, "w") as f:
        json.dump(export, f, indent=2)
    print(f"\nExported {len(export)} brackets to {filepath}")


# =============================================================================
# CLI + MAIN
# =============================================================================

def parse_args():
    parser = argparse.ArgumentParser(
        description="Generate Kelly-optimized March Madness brackets")
    parser.add_argument("--sims", type=int, default=M_SIMS)
    parser.add_argument("--sigma", type=float, default=SIGMA)
    parser.add_argument("--model-weight", type=float, default=MODEL_WEIGHT)
    parser.add_argument("--wealth-base", type=float, default=WEALTH_BASE)
    parser.add_argument("--seed", type=int, default=RANDOM_SEED)
    parser.add_argument("--output", type=str, default="output/final_brackets.json")
    parser.add_argument("--pools", type=str, default="pools.toml",
                        help="Path to pool configuration file")
    return parser.parse_args()


def main():
    args = parse_args()
    if args.seed is not None:
        random.seed(args.seed)

    pools = load_pools(args.pools)

    print("=" * 95)
    print("MARCH MADNESS BRACKET MAKER — Kelly Portfolio Optimizer")
    print("=" * 95)
    print(f"Pools: {len(pools)} | Sims: {args.sims} | Sigma: {args.sigma} | "
          f"ModelWeight: {args.model_weight} | WealthBase: {args.wealth_base}")

    print(f"\nPool configuration:")
    for p in pools:
        payout_str = "/".join(f"{v*100:.0f}" for v in
                              sorted(p['payout'].values(), reverse=True))
        print(f"  {p['name']:<12} N={p['field_size']:<5} Payout: {payout_str}")

    print(f"\nLoading data...")
    data = load_year_data(2026)
    our_probs = blend_probs(data["model"], data["market"], args.model_weight)
    public = data["public"]
    print(f"  Model:  {data['sources'].get('model', 'N/A')} ({len(data['model'])} teams)")
    print(f"  Market: {data['sources'].get('market', 'N/A')} ({len(data['market'])} teams)")
    print(f"  Public: {data['sources'].get('public', 'N/A')} ({len(public)} teams)")
    print(f"  Blended: {len(our_probs)} teams")

    game_tree = build_game_tree()
    chalk = make_chalk_bracket(our_probs, game_tree)
    print(f"\nChalk champion: {chalk[62]}")

    print(f"\nPrecomputing simulations...")
    t0 = time.time()
    precomputed = precompute_sims(our_probs, public, args.sigma, args.sims,
                                  N_OPPONENTS, game_tree)
    print(f"  Done in {time.time()-t0:.1f}s")

    sim_champs = defaultdict(int)
    for outcome, _ in precomputed:
        sim_champs[outcome[62]] += 1
    print(f"\nSimulated champions (top 10):")
    for team, count in sorted(sim_champs.items(), key=lambda x: -x[1])[:10]:
        print(f"  {team:<16} {count}/{args.sims} ({count/args.sims*100:.1f}%)")

    print(f"\nOptimizing portfolio...")
    results = build_portfolio(pools, our_probs, public, game_tree,
                              precomputed, args.wealth_base)

    print_summary(results, our_probs, public, game_tree)
    export_brackets(results, args.output)

    print(f"\n{'=' * 95}")
    print(f"Done. Review {args.output}.")
    print(f"{'=' * 95}")


if __name__ == "__main__":
    main()
