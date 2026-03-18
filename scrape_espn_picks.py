"""
Scrape ESPN Tournament Challenge pick distribution via the Gambit API.

This replaces the Yahoo scraper as our primary source of public pick data.
ESPN has ~130-323M brackets vs Yahoo's ~3M.

Known challenge IDs:
  239 = 2023 men's
  240 = 2024 men's
  257 = 2025 men's
  277 = 2026 men's

Usage:
    python3 scrape_espn_picks.py              # Scrape 2026 (default)
    python3 scrape_espn_picks.py --year 2025  # Scrape specific year
    python3 scrape_espn_picks.py --all        # Scrape all available years
"""

import json
import csv
import sys
import urllib.request
from datetime import datetime

CHALLENGE_IDS = {
    2023: 239,
    2024: 240,
    2025: 257,
    2026: 277,
}

ROUND_MAP = {1: "R1", 2: "R2", 3: "S16", 4: "E8", 5: "F4", 6: "Championship"}


def fetch_espn_picks(challenge_id: int) -> list:
    """Fetch all pick data from ESPN Gambit API."""
    url = f"https://gambit-api.fantasy.espn.com/apis/v1/propositions?challengeId={challenge_id}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def parse_picks(data: list) -> list:
    """Parse Gambit API response into flat rows."""
    rows = []
    for item in data:
        period = item.get("scoringPeriodId", 0)
        round_name = ROUND_MAP.get(period, f"Rd{period}")

        for outcome in item.get("possibleOutcomes", []):
            counters = outcome.get("choiceCounters", [])
            pct = counters[0]["percentage"] * 100 if counters else 0
            count = counters[0]["count"] if counters else 0

            # Extract seed from mappings
            seed = outcome.get("regionSeed", "")

            rows.append({
                "team": outcome.get("description", ""),
                "abbrev": outcome.get("abbrev", ""),
                "seed": seed,
                "round": round_name,
                "pick_pct": round(pct, 4),
                "pick_count": count,
            })
    return rows


def save_csv(rows: list, filepath: str):
    """Save rows to CSV."""
    with open(filepath, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["team", "abbrev", "seed", "round", "pick_pct", "pick_count"])
        writer.writeheader()
        writer.writerows(rows)


def scrape_year(year: int):
    """Scrape and save ESPN pick data for a given year."""
    if year not in CHALLENGE_IDS:
        print(f"ERROR: No challenge ID known for {year}. Known years: {list(CHALLENGE_IDS.keys())}")
        return

    cid = CHALLENGE_IDS[year]
    print(f"Fetching {year} (challengeId={cid})...")

    data = fetch_espn_picks(cid)
    rows = parse_picks(data)

    filepath = f"data/espn_picks_{year}_mens.csv"
    save_csv(rows, filepath)

    # Summary
    total_brackets = sum(r["pick_count"] for r in rows if r["round"] == "R1") // 2
    champs = sorted(
        [(r["team"][:30], r["seed"], r["pick_pct"]) for r in rows if r["round"] == "Championship"],
        key=lambda x: -x[2]
    )

    print(f"  Saved {len(rows)} rows to {filepath}")
    print(f"  ~{total_brackets:,} brackets")
    print(f"  Top champions:")
    for t, s, p in champs[:8]:
        print(f"    {t:<30} ({s}) {p:.1f}%")
    print()


def main():
    args = sys.argv[1:]

    if "--all" in args:
        for year in sorted(CHALLENGE_IDS.keys()):
            scrape_year(year)
    elif "--year" in args:
        idx = args.index("--year")
        year = int(args[idx + 1])
        scrape_year(year)
    else:
        # Default: scrape current year (2026)
        scrape_year(2026)

    print(f"Done. Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


if __name__ == "__main__":
    main()
