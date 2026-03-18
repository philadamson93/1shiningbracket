"""
Calibrate sigma — the model prediction error parameter.

Uses two data sources:
1. Raw 538 forecast CSVs (2018-2023): contain pre-tournament predictions AND
   actual outcomes (probabilities become 1.0/0.0 as rounds are played).
2. Cleaned 538 advancement probs (data/historical/pred.538.men.YYYY.csv):
   pre-tournament cumulative advancement probabilities.

Compares pre-tournament predictions vs actual outcomes for each team×round.
Computes sigma in both probability space and logit space.

Output: recommended sigma for sim_engine.perturb_probs()
"""

import csv
import math
from collections import defaultdict

# Raw 538 forecast files (multi-date, contain actual outcomes)
RAW_538_FILES = {
    2018: "data/538_ncaa_forecasts_2018.csv",
    2021: "data/538_ncaa_forecasts_2021.csv",
    2022: "data/538_ncaa_forecasts_2022.csv",
    2023: "data/538_ncaa_forecasts_2023_final.csv",
}

# Known champions (final outcomes not in the forecast files)
KNOWN_CHAMPIONS = {
    2018: "Villanova",
    2021: "Baylor",
    2022: "Kansas",
    2023: "Connecticut",
}

# 538 raw columns → our round names
# rd1_win = play-in survival (1.0 for non-playin teams)
# rd2_win = R1, rd3_win = R2, ..., rd7_win = Championship
RAW_COL_MAP = {
    "rd2_win": "R1",
    "rd3_win": "R2",
    "rd4_win": "S16",
    "rd5_win": "E8",
    "rd6_win": "F4",
    "rd7_win": "Championship",
}

# Cleaned pre-tournament prediction files
PRED_FILES = {
    2017: "data/historical/pred.538.men.2017.csv",
    2018: "data/historical/pred.538.men.2018.csv",
    2021: "data/historical/pred.538.men.2021.csv",
    2022: "data/historical/pred.538.men.2022.csv",
    2023: "data/historical/pred.538.men.2023.csv",
}

PRED_COL_MAP = {
    "round1": "R1", "round2": "R2", "round3": "S16",
    "round4": "E8", "round5": "F4", "round6": "Championship",
}


def extract_actuals_from_raw(filepath, year):
    """
    Extract actual tournament outcomes from raw 538 forecast file.

    On the final forecast date, round probabilities are:
    - 1.0 = team actually advanced (confirmed result)
    - 0.0 = team was eliminated (confirmed result)
    - 0 < p < 1 = still a prediction (game hasn't happened yet)

    Returns: dict[team_name] = {"R1": 0_or_1, "R2": 0_or_1, ...}
    """
    rows = []
    with open(filepath) as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("gender", "mens") == "mens" or "gender" not in row:
                if row.get("playin_flag", "0") == "0":
                    rows.append(row)

    # Get the last (most complete) forecast date
    dates = sorted(set(r["forecast_date"] for r in rows))
    last_date = dates[-1]
    final_rows = [r for r in rows if r["forecast_date"] == last_date]

    actuals = {}
    for row in final_rows:
        team = row["team_name"]
        team_actuals = {}
        for raw_col, our_round in RAW_COL_MAP.items():
            val = float(row.get(raw_col, 0))
            if val == 1.0:
                team_actuals[our_round] = 1
            elif val == 0.0:
                team_actuals[our_round] = 0
            else:
                # Still a prediction (championship game not yet played)
                # Use known champion data
                if our_round == "Championship":
                    champion = KNOWN_CHAMPIONS.get(year, "")
                    team_actuals[our_round] = 1 if team == champion else 0
                # F4 might also be unresolved on some dates, but usually
                # the last forecast date has F4 results
                else:
                    team_actuals[our_round] = None  # unknown
        actuals[team] = team_actuals

    return actuals


def load_predictions(filepath):
    """Load pre-tournament 538 advancement probabilities."""
    preds = {}
    with open(filepath) as f:
        reader = csv.DictReader(f)
        for row in reader:
            team = row.get("name", "")
            if not team:
                continue
            team_preds = {}
            for col, our_round in PRED_COL_MAP.items():
                val = row.get(col)
                if val:
                    team_preds[our_round] = float(val)
            preds[team] = team_preds
    return preds


def compute_sigma():
    """
    Main calibration: compare pre-tournament predictions to actual outcomes.

    For each (team, round, year):
      predicted = 538 pre-tournament advancement probability
      actual = 1 if team reached that round, 0 otherwise
      error = actual - predicted

    Compute RMS error and logit-space sigma.
    """
    all_errors = []
    round_errors = defaultdict(list)
    year_errors = defaultdict(list)

    for year in sorted(PRED_FILES.keys()):
        preds = load_predictions(PRED_FILES[year])
        if not preds:
            print(f"  {year}: No prediction data, skipping")
            continue

        # Get actuals (from raw files if available)
        actuals = None
        if year in RAW_538_FILES:
            actuals = extract_actuals_from_raw(RAW_538_FILES[year], year)

        if not actuals:
            print(f"  {year}: No actuals data, skipping")
            continue

        # Match predictions to actuals by team name (fuzzy)
        n_matched = 0
        for pred_team, pred_rounds in preds.items():
            # Try to find matching team in actuals
            actual_team = None
            pred_lower = pred_team.lower()
            for at in actuals:
                if at.lower() == pred_lower or pred_lower in at.lower() or at.lower() in pred_lower:
                    actual_team = at
                    break

            if not actual_team:
                continue

            n_matched += 1
            for rd in ["R1", "R2", "S16", "E8", "F4", "Championship"]:
                predicted = pred_rounds.get(rd)
                actual = actuals[actual_team].get(rd)
                if predicted is not None and actual is not None:
                    error = actual - predicted
                    all_errors.append({
                        "year": year,
                        "team": pred_team,
                        "round": rd,
                        "predicted": predicted,
                        "actual": actual,
                        "error": error,
                    })
                    round_errors[rd].append(error)
                    year_errors[year].append(error)

        print(f"  {year}: matched {n_matched} teams")

    return all_errors, round_errors, year_errors


def main():
    print("=" * 70)
    print("SIGMA CALIBRATION — 538 Pre-Tournament Prediction Error")
    print("=" * 70)
    print(f"\nExtracting actuals from raw 538 forecasts...")

    all_errors, round_errors, year_errors = compute_sigma()

    if not all_errors:
        print("ERROR: No matched prediction/actual pairs found!")
        return

    # Overall metrics
    errors = [e["error"] for e in all_errors]
    sq_errors = [e ** 2 for e in errors]
    rms = math.sqrt(sum(sq_errors) / len(sq_errors))
    mean_abs = sum(abs(e) for e in errors) / len(errors)
    bias = sum(errors) / len(errors)

    print(f"\n--- OVERALL ({len(all_errors)} team×round observations) ---")
    print(f"  RMS error (prob space):     {rms:.4f}")
    print(f"  Mean absolute error:        {mean_abs:.4f}")
    print(f"  Bias (actual - predicted):  {bias:+.4f}")

    # Per-round breakdown
    print(f"\n--- BY ROUND ---")
    print(f"  {'Round':<15} {'N':>5} {'RMS':>8} {'MAE':>8} {'Bias':>8}")
    round_order = ["R1", "R2", "S16", "E8", "F4", "Championship"]
    for rd in round_order:
        errs = round_errors.get(rd, [])
        if not errs:
            continue
        sq = [e ** 2 for e in errs]
        rms_rd = math.sqrt(sum(sq) / len(sq))
        mae_rd = sum(abs(e) for e in errs) / len(errs)
        bias_rd = sum(errs) / len(errs)
        print(f"  {rd:<15} {len(errs):>5} {rms_rd:>7.4f} {mae_rd:>7.4f} {bias_rd:>+7.4f}")

    # Per-year
    print(f"\n--- BY YEAR ---")
    print(f"  {'Year':<6} {'N':>5} {'RMS':>8} {'Bias':>8}")
    for year in sorted(year_errors.keys()):
        errs = year_errors[year]
        sq = [e ** 2 for e in errs]
        rms_yr = math.sqrt(sum(sq) / len(sq))
        bias_yr = sum(errs) / len(errs)
        print(f"  {year:<6} {len(errs):>5} {rms_yr:>7.4f} {bias_yr:>+7.4f}")

    # Logit-space sigma computation
    # For advancement probabilities (not game-level), the binary outcome (0/1)
    # means RMS error in prob space is high (~0.40) due to inherent randomness.
    # What we want for sigma is: how much should we perturb the model?
    #
    # Approach: group predictions by probability bin, compare predicted vs
    # observed frequency. The deviation = calibration error.
    bins = [(0, 0.05), (0.05, 0.15), (0.15, 0.30), (0.30, 0.50),
            (0.50, 0.70), (0.70, 0.85), (0.85, 0.95), (0.95, 1.01)]
    print(f"\n--- CALIBRATION BY PROBABILITY BIN ---")
    print(f"  {'Bin':<12} {'N':>5} {'Predicted':>10} {'Actual':>8} {'Gap':>8}")
    bin_gaps = []
    for lo, hi in bins:
        bin_data = [e for e in all_errors if lo <= e["predicted"] < hi]
        if len(bin_data) < 5:
            continue
        avg_pred = sum(e["predicted"] for e in bin_data) / len(bin_data)
        avg_actual = sum(e["actual"] for e in bin_data) / len(bin_data)
        gap = avg_actual - avg_pred
        bin_gaps.append(gap)
        print(f"  {lo:.2f}-{hi:.2f}  {len(bin_data):>5} {avg_pred:>9.1%} {avg_actual:>7.1%} {gap:>+7.4f}")

    # Calibration error = RMS of bin gaps
    if bin_gaps:
        cal_error = math.sqrt(sum(g ** 2 for g in bin_gaps) / len(bin_gaps))
    else:
        cal_error = 0.05

    # Convert calibration error to logit-space sigma
    # At p=0.5, d(logit)/dp = 4, so logit_sigma ≈ 4 * prob_sigma
    # But we want sigma that accounts for both calibration error AND
    # genuine uncertainty about team strength.
    # Empirically: logit_sigma ≈ 0.3-0.5 produces realistic upset rates.
    sigma_logit = max(0.15, min(0.6, 4.0 * cal_error + 0.1))

    print(f"\n--- SIGMA COMPUTATION ---")
    print(f"  Calibration error (RMS of bin gaps): {cal_error:.4f}")
    print(f"  Logit-space sigma:                   {sigma_logit:.3f}")
    print(f"    (formula: max(0.15, min(0.6, 4 * {cal_error:.4f} + 0.1)))")

    # Also check: what fraction of predictions are "wrong" by more than X%?
    large_errors = sum(1 for e in all_errors if abs(e["error"]) > 0.3)
    huge_errors = sum(1 for e in all_errors if abs(e["error"]) > 0.5)
    print(f"\n  Predictions off by >30%: {large_errors}/{len(all_errors)} ({large_errors/len(all_errors):.1%})")
    print(f"  Predictions off by >50%: {huge_errors}/{len(all_errors)} ({huge_errors/len(all_errors):.1%})")

    print(f"\n{'=' * 70}")
    print(f"RECOMMENDATION: SIGMA_LOGIT = {sigma_logit:.2f}")
    print(f"Use in bracket_maker.py: SIGMA = {sigma_logit:.2f}")
    print(f"{'=' * 70}")

    # Also report the old game-level analysis for comparison
    old_file = "data/538_historical_ncaa_tournament_model_results.csv"
    try:
        games = []
        with open(old_file) as f:
            for row in csv.DictReader(f):
                games.append(row)
        n_correct = sum(1 for g in games if int(g["favorite_win_flag"]) == 1)
        print(f"\n(For reference: old game-level data has {len(games)} games, {n_correct/len(games):.1%} favorite accuracy)")
    except:
        pass


if __name__ == "__main__":
    main()
