"""
Fetch live sportsbook odds from The Odds API and produce dk_implied_odds.csv.

Pulls championship futures and R1 moneylines from DraftKings, BetMGM, and
BetRivers. Averages across books, removes vig, and interpolates intermediate
rounds (S16, E8, F4) from championship + R1 probabilities using historical
seed-based ratios.

Usage:
    python3 src/fetch_odds.py                         # uses ODDS_API_KEY env var
    python3 src/fetch_odds.py --api-key YOUR_KEY
    ODDS_API_KEY=xxx python3 src/fetch_odds.py

Output: data/dk_implied_odds.csv
"""

import argparse
import csv
import json
import math
import os
import sys
import urllib.request
from datetime import datetime

from data_loader import normalize_team_name

API_BASE = "https://api.the-odds-api.com/v4/sports"

# Historical seed-based advancement ratios (conditional on R1 win).
# Used to interpolate S16/E8/F4 from R1 and championship probabilities.
# Format: seed -> (R1, S16/R1, E8/R1, F4/R1, Champ/R1)
# These are P(reach round X) / P(win R1) from 1985-2025 data.
SEED_ROUND_RATIOS = {
    1:  (0.993, 0.876, 0.644, 0.393, 0.131),
    2:  (0.938, 0.725, 0.426, 0.224, 0.064),
    3:  (0.851, 0.564, 0.294, 0.141, 0.035),
    4:  (0.793, 0.504, 0.240, 0.101, 0.025),
    5:  (0.650, 0.385, 0.169, 0.062, 0.015),
    6:  (0.612, 0.343, 0.147, 0.065, 0.016),
    7:  (0.604, 0.298, 0.116, 0.050, 0.013),
    8:  (0.500, 0.240, 0.100, 0.040, 0.010),
    9:  (0.500, 0.240, 0.100, 0.040, 0.010),
    10: (0.396, 0.161, 0.076, 0.025, 0.008),
    11: (0.388, 0.144, 0.072, 0.026, 0.008),
    12: (0.350, 0.100, 0.057, 0.017, 0.003),
    13: (0.207, 0.048, 0.029, 0.010, 0.002),
    14: (0.149, 0.034, 0.027, 0.007, 0.001),
    15: (0.069, 0.022, 0.007, 0.003, 0.001),
    16: (0.012, 0.008, 0.002, 0.001, 0.000),
}

# Bracket structure: team -> (seed, region)
# Imported from sim_engine at runtime, but we need it for seed lookup.
BRACKET_SEEDS = {}


def fetch_json(url):
    """Fetch JSON from a URL."""
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def american_to_implied(odds):
    """Convert American odds to raw implied probability."""
    if odds > 0:
        return 100.0 / (odds + 100.0)
    else:
        return abs(odds) / (abs(odds) + 100.0)


def fetch_championship_futures(api_key):
    """Fetch championship winner odds from all available US books."""
    url = (f"{API_BASE}/basketball_ncaab_championship_winner/odds"
           f"?regions=us&markets=outrights&oddsFormat=american"
           f"&apiKey={api_key}")
    data = fetch_json(url)

    # Collect odds per team, averaged across books
    team_odds = {}
    for event in data:
        for bm in event.get("bookmakers", []):
            for mkt in bm.get("markets", []):
                for o in mkt.get("outcomes", []):
                    team = o["name"]
                    if team not in team_odds:
                        team_odds[team] = []
                    team_odds[team].append(o["price"])

    # Average implied probability across books, then normalize to sum=1
    team_probs = {}
    for team, odds_list in team_odds.items():
        avg_implied = sum(american_to_implied(o) for o in odds_list) / len(odds_list)
        team_probs[team] = avg_implied

    total = sum(team_probs.values())
    if total > 0:
        team_probs = {t: p / total for t, p in team_probs.items()}

    return team_probs


def fetch_r1_moneylines(api_key):
    """Fetch R1 game moneylines. Returns dict of team -> implied win prob."""
    url = (f"{API_BASE}/basketball_ncaab/odds"
           f"?regions=us&markets=h2h&oddsFormat=american"
           f"&apiKey={api_key}")
    data = fetch_json(url)

    team_r1 = {}
    for game in data:
        # Collect all book odds for each team in this game
        team_odds = {}
        for bm in game.get("bookmakers", []):
            for mkt in bm.get("markets", []):
                for o in mkt.get("outcomes", []):
                    team = o["name"]
                    if team not in team_odds:
                        team_odds[team] = []
                    team_odds[team].append(o["price"])

        if len(team_odds) != 2:
            continue

        # Average across books, then normalize the pair to remove vig
        teams = list(team_odds.keys())
        avg = []
        for t in teams:
            avg.append(sum(american_to_implied(o) for o in team_odds[t]) / len(team_odds[t]))

        total = sum(avg)
        if total > 0:
            for i, t in enumerate(teams):
                team_r1[t] = avg[i] / total

    return team_r1


def interpolate_rounds(team_name, seed, r1_prob, champ_prob):
    """
    Interpolate S16, E8, F4 probabilities from R1 and championship.

    Uses historical seed ratios as a shape prior, then scales to match
    the known R1 and championship endpoints.
    """
    ratios = SEED_ROUND_RATIOS.get(seed, SEED_ROUND_RATIOS[8])
    hist_r1, hist_s16_ratio, hist_e8_ratio, hist_f4_ratio, hist_champ_ratio = ratios

    # Historical conditional probs (given in field)
    # We want to scale these so R1 = r1_prob and Champ = champ_prob
    if hist_r1 > 0 and hist_champ_ratio > 0:
        # Log-linear interpolation between R1 and Championship
        # S16, E8, F4 are intermediate points
        log_r1 = math.log(max(r1_prob, 1e-6))
        log_champ = math.log(max(champ_prob, 1e-8))
        log_hist_r1 = math.log(max(hist_r1, 1e-6))
        log_hist_champ = math.log(max(hist_champ_ratio, 1e-8))

        # Position of each round in log space (0=R1, 1=Champ)
        # Using historical ratios to determine the position
        hist_rounds = [hist_r1, hist_s16_ratio, hist_e8_ratio, hist_f4_ratio, hist_champ_ratio]
        log_hist = [math.log(max(h, 1e-8)) for h in hist_rounds]

        if log_hist[0] != log_hist[4]:
            results = {}
            round_names = ["R1", "S16", "E8", "F4", "Championship"]
            for i, rd in enumerate(round_names):
                # Linear interpolation in log space
                t = (log_hist[i] - log_hist[0]) / (log_hist[4] - log_hist[0])
                log_p = log_r1 + t * (log_champ - log_r1)
                results[rd] = min(0.999, max(1e-6, math.exp(log_p)))
            return results

    # Fallback: simple geometric interpolation
    s16 = r1_prob ** 0.6 * champ_prob ** 0.4 if r1_prob > 0 and champ_prob > 0 else 0
    e8 = r1_prob ** 0.4 * champ_prob ** 0.6 if r1_prob > 0 and champ_prob > 0 else 0
    f4 = r1_prob ** 0.2 * champ_prob ** 0.8 if r1_prob > 0 and champ_prob > 0 else 0

    return {
        "R1": r1_prob,
        "S16": s16,
        "E8": e8,
        "F4": f4,
        "Championship": champ_prob,
    }


def build_seed_map():
    """Build team -> seed mapping from sim_engine.BRACKET."""
    try:
        from sim_engine import BRACKET
        seed_map = {}
        for region, teams in BRACKET.items():
            for team, seed in teams:
                seed_map[team] = (seed, region)
        return seed_map
    except ImportError:
        return {}


def write_csv(rows, filepath):
    """Write results to CSV in the same format as the old scrape_dk_odds.py."""
    fieldnames = [
        "team", "seed", "region",
        "R1_implied", "S16_implied", "E8_implied",
        "F4_implied", "championship_implied",
    ]
    with open(filepath, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in sorted(rows, key=lambda x: -x["championship_implied"]):
            out = {}
            for k in fieldnames:
                v = row[k]
                if isinstance(v, float):
                    out[k] = round(v, 6)
                else:
                    out[k] = v
            writer.writerow(out)
    print(f"Wrote {len(rows)} teams to {filepath}")


def main():
    parser = argparse.ArgumentParser(description="Fetch live sportsbook odds")
    parser.add_argument("--api-key", type=str,
                        default=os.environ.get("ODDS_API_KEY", ""),
                        help="The Odds API key (or set ODDS_API_KEY env var)")
    parser.add_argument("--output", type=str, default="data/dk_implied_odds.csv")
    args = parser.parse_args()

    if not args.api_key:
        print("ERROR: No API key. Pass --api-key or set ODDS_API_KEY env var.")
        print("Sign up free at https://the-odds-api.com/")
        sys.exit(1)

    seed_map = build_seed_map()
    if not seed_map:
        print("WARNING: Could not load bracket structure from sim_engine.")

    print(f"Fetching championship futures...")
    champ_probs = fetch_championship_futures(args.api_key)
    print(f"  {len(champ_probs)} teams")

    print(f"Fetching R1 moneylines...")
    r1_probs = fetch_r1_moneylines(args.api_key)
    print(f"  {len(r1_probs)} teams")

    # Match API team names to our canonical names
    print(f"\nBuilding implied probability table...")
    rows = []
    matched = 0
    for api_name, champ_p in champ_probs.items():
        canonical = normalize_team_name(api_name)

        # Look up seed and region
        seed_info = seed_map.get(canonical)
        if seed_info:
            seed, region = seed_info
        else:
            seed, region = 0, ""

        # Find R1 moneyline
        r1_p = None
        for r1_name, r1_val in r1_probs.items():
            if normalize_team_name(r1_name) == canonical:
                r1_p = r1_val
                break

        if r1_p is None:
            # Use historical seed average for R1
            hist = SEED_ROUND_RATIOS.get(seed, SEED_ROUND_RATIOS[8])
            r1_p = hist[0]

        # Interpolate intermediate rounds
        round_probs = interpolate_rounds(canonical, seed, r1_p, champ_p)

        rows.append({
            "team": canonical,
            "seed": seed,
            "region": region,
            "R1_implied": round_probs["R1"],
            "S16_implied": round_probs["S16"],
            "E8_implied": round_probs["E8"],
            "F4_implied": round_probs["F4"],
            "championship_implied": round_probs["Championship"],
        })
        if seed_info:
            matched += 1

    print(f"  Matched {matched}/{len(rows)} teams to bracket")

    # Normalize per-region: S16 should sum to 4, E8 and F4 should sum to 1
    regions = set(r["region"] for r in rows if r["region"])
    for region in regions:
        region_rows = [r for r in rows if r["region"] == region]

        # Normalize to match model/public cumulative advancement semantics:
        # S16 = P(reach E8) = 2 per region, E8 = P(win region) = 1, F4 = P(reach champ game) = 0.5
        for col, target in [("S16_implied", 2.0), ("E8_implied", 1.0), ("F4_implied", 0.5)]:
            total = sum(r[col] for r in region_rows)
            if total > 0:
                scale = target / total
                for r in region_rows:
                    r[col] = min(0.999, r[col] * scale)

    # Ensure monotonic: R1 >= S16 >= E8 >= F4 >= Championship
    for r in rows:
        r["S16_implied"] = min(r["S16_implied"], r["R1_implied"])
        r["E8_implied"] = min(r["E8_implied"], r["S16_implied"])
        r["F4_implied"] = min(r["F4_implied"], r["E8_implied"])
        r["championship_implied"] = min(r["championship_implied"], r["F4_implied"])

    # Verify
    for region in regions:
        region_rows = [r for r in rows if r["region"] == region]
        e8_sum = sum(r["E8_implied"] for r in region_rows)
        f4_sum = sum(r["F4_implied"] for r in region_rows)
        print(f"  {region}: E8 sum={e8_sum:.3f}, F4 sum={f4_sum:.3f}")

    # Write CSV
    write_csv(rows, args.output)

    # Print summary
    print(f"\n{'Team':<22} {'Seed':>4} {'R1%':>7} {'S16%':>7} {'E8%':>7} {'F4%':>7} {'Champ%':>7}")
    print(f"  {'-'*22} {'-'*4} {'-'*7} {'-'*7} {'-'*7} {'-'*7} {'-'*7}")
    for row in sorted(rows, key=lambda x: -x["championship_implied"])[:20]:
        print(
            f"  {row['team']:<22} {row['seed']:4d} "
            f"{row['R1_implied']*100:6.1f}% "
            f"{row['S16_implied']*100:6.1f}% "
            f"{row['E8_implied']*100:6.1f}% "
            f"{row['F4_implied']*100:6.1f}% "
            f"{row['championship_implied']*100:6.2f}%"
        )

    print(f"\nTimestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Output: {args.output}")


if __name__ == "__main__":
    main()
