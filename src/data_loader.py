"""
Unified data loader for March Madness bracket optimizer.

Loads model probabilities, public pick rates, and market odds
into a standard format regardless of source year or format.

Standard format: dict[team_name] = {
    "R1": prob, "R2": prob, "S16": prob, "E8": prob, "F4": prob, "Championship": prob
}
All values are 0-1 decimals (not percentages).
Team names are normalized to a canonical form.
"""

import csv
import os
import json
from typing import Optional

# =============================================================================
# ROUND NAME NORMALIZATION
# =============================================================================

# Map various round naming conventions to our standard
ROUND_MAP = {
    # 538 / mRchmadness format
    "round1": "R1",
    "round2": "R2",
    "round3": "S16",
    "round4": "E8",
    "round5": "F4",
    "round6": "Championship",
    # ESPN API format (already standard)
    "R1": "R1",
    "R2": "R2",
    "S16": "S16",
    "E8": "E8",
    "F4": "F4",
    "Championship": "Championship",
    # DK format
    "R1_implied": "R1",
    "S16_implied": "S16",
    "E8_implied": "E8",
    "F4_implied": "F4",
    "championship_implied": "Championship",
}

STANDARD_ROUNDS = ["R1", "R2", "S16", "E8", "F4", "Championship"]


# =============================================================================
# TEAM NAME NORMALIZATION
# =============================================================================

# Canonical team names and all known aliases
# Key = canonical name, Value = list of aliases
TEAM_ALIASES = {
    "Duke": ["Duke", "Duke Blue Devils"],
    "Michigan": ["Michigan", "Michigan Wolverines"],
    "Arizona": ["Arizona", "Arizona Wildcats"],
    "Florida": ["Florida", "Florida Gators"],
    "Houston": ["Houston", "Houston Cougars"],
    "Iowa State": ["Iowa State", "Iowa St.", "Iowa State Cyclones", "ISU"],
    "UConn": ["UConn", "Connecticut", "Connecticut Huskies", "UCONN"],
    "Illinois": ["Illinois", "Illinois Fighting Illini", "ILL"],
    "Purdue": ["Purdue", "Purdue Boilermakers"],
    "Michigan State": ["Michigan State", "Michigan St.", "Michigan St", "Michigan State Spartans", "Michigan St Spartans", "MSU"],
    "Gonzaga": ["Gonzaga", "Gonzaga Bulldogs"],
    "Virginia": ["Virginia", "Virginia Cavaliers", "UVA"],
    "Louisville": ["Louisville", "Louisville Cardinals"],
    "St. John's": ["St. John's", "St. John's Red Storm", "Saint John's"],
    "Kansas": ["Kansas", "Kansas Jayhawks", "KU"],
    "Alabama": ["Alabama", "Alabama Crimson Tide", "BAMA"],
    "Arkansas": ["Arkansas", "Arkansas Razorbacks"],
    "Vanderbilt": ["Vanderbilt", "Vanderbilt Commodores"],
    "North Carolina": ["North Carolina", "N. Carolina", "North Carolina Tar Heels", "UNC"],
    "Tennessee": ["Tennessee", "Tennessee Volunteers", "TENN"],
    "Kentucky": ["Kentucky", "Kentucky Wildcats", "UK"],
    "UCLA": ["UCLA", "UCLA Bruins"],
    "Ohio State": ["Ohio State", "Ohio St.", "Ohio State Buckeyes", "OSU"],
    "TCU": ["TCU", "TCU Horned Frogs"],
    "Iowa": ["Iowa", "Iowa Hawkeyes"],
    "Clemson": ["Clemson", "Clemson Tigers"],
    "Nebraska": ["Nebraska", "Nebraska Cornhuskers"],
    "VCU": ["VCU", "VCU Rams"],
    "Texas A&M": ["Texas A&M", "Texas A&M Aggies", "TAMU"],
    "Saint Mary's": ["Saint Mary's", "St. Mary's", "Saint Mary's Gaels"],
    "BYU": ["BYU", "BYU Cougars", "Brigham Young"],
    "Wisconsin": ["Wisconsin", "Wisconsin Badgers"],
    "Texas Tech": ["Texas Tech", "Texas Tech Red Raiders"],
    "Miami FL": ["Miami FL", "Miami (FL)", "Miami", "Miami Hurricanes", "Miami (Fl.)"],
    "UCF": ["UCF", "UCF Knights"],
    "South Florida": ["South Florida", "South Florida Bulls", "USF"],
    "Missouri": ["Missouri", "Missouri Tigers", "MIZZOU"],
    "Akron": ["Akron", "Akron Zips"],
    "Hofstra": ["Hofstra", "Hofstra Pride"],
    "Santa Clara": ["Santa Clara", "Santa Clara Broncos"],
    "SMU": ["SMU", "SMU Mustangs", "MOH/SMU"],
    "NC State": ["NC State", "N.C. State", "NC State Wolfpack", "TX/NCST"],
    "Villanova": ["Villanova", "Villanova Wildcats", "NOVA"],
    "Utah State": ["Utah State", "Utah St.", "Utah State Aggies"],
    "High Point": ["High Point", "High Point Panthers"],
    "Kennesaw State": ["Kennesaw State", "Kennesaw St.", "Kennesaw State Owls", "Kennesaw St Owls"],
    "Queens": ["Queens", "Queens University", "Queens Royals"],
    "Northern Iowa": ["Northern Iowa", "Northern Iowa Panthers", "UNI"],
    "Cal Baptist": ["Cal Baptist", "California Baptist", "California Baptist Lancers", "CBU"],
    "North Dakota St": ["North Dakota St", "North Dakota State", "N. Dak. St.", "NDSU", "North Dakota State Bison"],
    "Furman": ["Furman", "Furman Paladins"],
    "Siena": ["Siena", "Siena Saints"],
    "LIU": ["LIU", "LIU Brooklyn", "Long Island"],
    "Howard": ["Howard", "Howard Bison", "UMBC/HOW"],
    "Lehigh": ["Lehigh", "Lehigh Mountain Hawks", "PV/LEH"],
    "Troy": ["Troy", "Troy Trojans"],
    "Penn": ["Penn", "Pennsylvania", "Pennsylvania Quakers"],
    "Idaho": ["Idaho", "Idaho Vandals"],
    "McNeese": ["McNeese", "McNeese Cowboys", "McNeese State"],
    "Wright State": ["Wright State", "Wright St.", "Wright State Raiders", "Wright St Raiders"],
    "Tennessee State": ["Tennessee State", "Tennessee St.", "Tennessee State Tigers", "Tennessee St Tigers"],
    "Hawaii": ["Hawaii", "Hawai'i", "Hawaii Rainbow Warriors"],
    "Georgia": ["Georgia", "Georgia Bulldogs", "UGA"],
    "Saint Louis": ["Saint Louis", "St. Louis", "Saint Louis Billikens", "SLU"],
    "Marquette": ["Marquette", "Marquette Golden Eagles"],
    "Baylor": ["Baylor", "Baylor Bears"],
    "Texas": ["Texas", "Texas Longhorns"],
    "Creighton": ["Creighton", "Creighton Bluejays"],
    "Auburn": ["Auburn", "Auburn Tigers"],
    "LSU": ["LSU", "Louisiana State", "LSU Tigers"],
    "USC": ["USC", "Southern California", "USC Trojans"],
    "Loyola Chicago": ["Loyola Chicago", "Loyola (IL)", "Loyola-Chicago"],
    "Florida State": ["Florida State", "FSU", "Florida State Seminoles"],
    "San Diego State": ["San Diego State", "SDSU", "San Diego State Aztecs"],
    "FAU": ["FAU", "Florida Atlantic", "Florida Atlantic Owls"],
    "East Tennessee State": ["East Tennessee State", "ETSU"],
    "Middle Tennessee": ["Middle Tennessee", "Mid Tennessee", "MTSU"],
    "Mount St. Mary's": ["Mount St. Mary's", "MSM", "Mt. St. Mary's"],
    "New Mexico State": ["New Mexico State", "New Mexico St", "NMSU"],
    "Southern Methodist": ["Southern Methodist", "SMU", "SMU Mustangs"],
    "South Dakota State": ["South Dakota State", "South Dakota St", "S Dakota St", "SDSU"],
    "Northern Kentucky": ["Northern Kentucky", "N Kentucky", "NKU"],
    "Jacksonville State": ["Jacksonville State", "Jacksonville St", "J'Ville St"],
    "Kansas State": ["Kansas State", "KSU", "Kansas State Wildcats", "K-State"],
    "Florida Gulf Coast": ["Florida Gulf Coast", "FGCU"],
    "UC Santa Barbara": ["UC Santa Barbara", "UC-Santa Barbara", "UCSB"],
    "Eastern Washington": ["Eastern Washington", "E Washington", "EWU"],
    "Abilene Christian": ["Abilene Christian", "Abil Christian", "ACU"],
    "CSU Fullerton": ["CSU Fullerton", "Cal State Fullerton", "Fullerton"],
    "Stephen F. Austin": ["Stephen F. Austin", "SF Austin", "SFA"],
    "College of Charleston": ["College of Charleston", "Charleston"],
    "Montana State": ["Montana State", "Montana St"],
    "Boise State": ["Boise State", "Boise St"],
    "Louisiana": ["Louisiana", "Louisiana-Lafayette", "UL Lafayette"],
    "Rutgers": ["Rutgers", "Rutgers Scarlet Knights"],
    "Notre Dame": ["Notre Dame", "Notre Dame Fighting Irish"],
    "Indiana": ["Indiana", "Indiana Hoosiers", "IU"],
    "Pittsburgh": ["Pittsburgh", "Pitt", "Pittsburgh Panthers"],
    "Mississippi State": ["Mississippi State", "Miss State", "MSU Bulldogs"],
    "Wyoming": ["Wyoming", "Wyoming Cowboys"],
    "UAB": ["UAB", "UAB Blazers"],
    "Maryland-Baltimore County": ["Maryland-Baltimore County", "UMBC"],
    "Rhode Island": ["Rhode Island", "URI"],
    "Texas Southern": ["Texas Southern", "Texas Southern Tigers"],
    "Norfolk State": ["Norfolk State", "Norfolk St"],
    "Appalachian State": ["Appalachian State", "App State"],
    "Fairleigh Dickinson": ["Fairleigh Dickinson", "FDU"],
    "Oral Roberts": ["Oral Roberts", "ORU"],
    "Saint Peter's": ["Saint Peter's", "St. Peter's"],
    "Colgate": ["Colgate", "Colgate Raiders"],
    "North Carolina-Wilmington": ["North Carolina-Wilmington", "UNCW", "UNC Wilmington"],
    "North Carolina Central": ["North Carolina Central", "NC Central"],
    "North Carolina A&T": ["North Carolina A&T", "NC A&T"],
    "UC Davis": ["UC Davis", "UC-Davis"],
    "Texas A&M-CC": ["Texas A&M-CC", "Texas A&M Corpus Christi", "AMCC", "AMCC/SMO"],
    "Murray State": ["Murray State", "Murray St"],
    "Davidson": ["Davidson", "Davidson Wildcats"],
    "Colorado State": ["Colorado State", "Colorado St", "CSU"],
    "Xavier": ["Xavier", "Xavier Musketeers"],
    "Oregon": ["Oregon", "Oregon Ducks"],
    "West Virginia": ["West Virginia", "WVU", "West Virginia Mountaineers"],
    "Michigan": ["Michigan", "Michigan Wolverines"],
}

# Build reverse lookup: alias → canonical name
_ALIAS_TO_CANONICAL = {}
for canonical, aliases in TEAM_ALIASES.items():
    for alias in aliases:
        _ALIAS_TO_CANONICAL[alias.lower()] = canonical


def normalize_team_name(name: str) -> str:
    """Normalize a team name to its canonical form."""
    # Try exact match first
    canonical = _ALIAS_TO_CANONICAL.get(name.lower())
    if canonical:
        return canonical

    # Try exact-word prefix match. Prefer the longest matching alias
    # to avoid "Tennessee St Tigers" matching "Tennessee" instead of
    # "Tennessee St."
    name_lower = name.lower()
    best_match = None
    best_len = 0
    for alias, canon in _ALIAS_TO_CANONICAL.items():
        if name_lower == alias or name_lower.startswith(alias + " "):
            if len(alias) > best_len:
                best_match = canon
                best_len = len(alias)

    if best_match:
        return best_match

    # Return original if no match
    return name


# =============================================================================
# DATA LOADERS
# =============================================================================

def load_538_probs(year: int, data_dir: str = "data/historical") -> dict:
    """
    Load FiveThirtyEight model probabilities for a given year.
    Returns: dict[canonical_team_name] = {"R1": prob, ..., "Championship": prob}
    """
    filepath = os.path.join(data_dir, f"pred.538.men.{year}.csv")
    return _load_wide_csv(filepath)


def load_kenpom_probs(year: int, data_dir: str = "data/historical") -> dict:
    """Load KenPom model probabilities."""
    filepath = os.path.join(data_dir, f"pred.kenpom.men.{year}.csv")
    return _load_wide_csv(filepath)


def load_pop_picks(year: int, data_dir: str = "data/historical") -> dict:
    """
    Load ESPN population pick percentages from mRchmadness cache.
    Returns: dict[canonical_team_name] = {"R1": prob, ..., "Championship": prob}
    """
    filepath = os.path.join(data_dir, f"pred.pop.men.{year}.csv")
    return _load_wide_csv(filepath)


def load_espn_api_picks(year: int, data_dir: str = "data") -> dict:
    """
    Load ESPN Gambit API pick percentages.
    Returns: dict[canonical_team_name] = {"R1": prob, ..., "Championship": prob}
    """
    filepath = os.path.join(data_dir, f"espn_picks_{year}_mens.csv")
    if not os.path.exists(filepath):
        return {}

    data = {}
    with open(filepath) as f:
        reader = csv.DictReader(f)
        for row in reader:
            team = normalize_team_name(row["team"])
            rd = ROUND_MAP.get(row["round"], row["round"])
            pct = float(row["pick_pct"]) / 100.0  # Convert percentage to decimal

            if team not in data:
                data[team] = {}
            data[team][rd] = pct
    return data


def load_yahoo_picks(filepath: str = "yahoo_pick_distribution.csv") -> dict:
    """
    Load Yahoo Bracket Mayhem pick percentages.
    Returns: dict[canonical_team_name] = {"R1": prob, ..., "Championship": prob}
    """
    if not os.path.exists(filepath):
        return {}

    data = {}
    with open(filepath) as f:
        reader = csv.DictReader(f)
        for row in reader:
            team = normalize_team_name(row["team"])
            rd = ROUND_MAP.get(row["round_label"], row["round_label"])
            pct = float(row["pick_pct"]) / 100.0

            if team not in data:
                data[team] = {}
            data[team][rd] = pct
    return data


def load_dk_odds(filepath: str = "data/dk_implied_odds.csv") -> dict:
    """
    Load DraftKings implied odds.
    Returns: dict[canonical_team_name] = {"R1": prob, ..., "Championship": prob}
    """
    if not os.path.exists(filepath):
        return {}

    data = {}
    with open(filepath) as f:
        reader = csv.DictReader(f)
        for row in reader:
            team = normalize_team_name(row["team"])
            data[team] = {}
            for csv_col, std_round in ROUND_MAP.items():
                if csv_col in row and row[csv_col]:
                    val = float(row[csv_col])
                    # DK values are already 0-1 decimals
                    data[team][std_round] = val
    return data


def _load_paine_csv(filepath: str) -> dict:
    """
    Load Paine composite CSV. Column mapping is SHIFTED by 1 from 538:
      round1 = P(in field / survive play-in) — SKIP
      round2 = P(win R1 game)                → R1
      round3 = P(advance past R2)            → R2
      round4 = P(advance past S16)           → S16
      round5 = P(advance past E8)            → E8
      round6 = P(win championship)           → Championship
    F4 is interpolated: F4 ≈ sqrt(E8 × Championship)
    """
    paine_round_map = {
        "round2": "R1",
        "round3": "R2",
        "round4": "S16",
        "round5": "E8",
        "round6": "Championship",
    }
    if not os.path.exists(filepath):
        return {}

    data = {}
    with open(filepath) as f:
        reader = csv.DictReader(f)
        for row in reader:
            team = normalize_team_name(row.get("name", ""))
            if not team:
                continue

            team_data = {}
            for col, std_round in paine_round_map.items():
                val = row.get(col)
                if val:
                    try:
                        prob = float(val)
                        if prob > 1.0:
                            prob /= 100.0
                        team_data[std_round] = prob
                    except (ValueError, TypeError):
                        pass

            # Interpolate F4: geometric mean of E8 and Championship
            e8 = team_data.get("E8", 0)
            champ = team_data.get("Championship", 0)
            if e8 > 0 and champ > 0:
                import math
                team_data["F4"] = math.sqrt(e8 * champ)
            elif e8 > 0:
                team_data["F4"] = e8 * 0.5  # rough approximation

            if team_data:
                data[team] = team_data
    return data


def _load_wide_csv(filepath: str) -> dict:
    """
    Load a wide-format CSV (one row per team, columns per round).
    Handles both 538 and mRchmadness formats.
    """
    if not os.path.exists(filepath):
        return {}

    data = {}
    with open(filepath) as f:
        reader = csv.DictReader(f)
        for row in reader:
            team = normalize_team_name(row.get("name", ""))
            if not team:
                continue

            team_data = {}
            for col, val in row.items():
                if col in ROUND_MAP:
                    std_round = ROUND_MAP[col]
                    try:
                        prob = float(val)
                        # Values should be 0-1 decimals already
                        if prob > 1.0:
                            prob /= 100.0
                        team_data[std_round] = prob
                    except (ValueError, TypeError):
                        pass
            if team_data:
                data[team] = team_data
    return data


# =============================================================================
# UNIFIED LOADER: Get all three columns for a year
# =============================================================================

def load_year_data(year: int) -> dict:
    """
    Load all available data for a given year.

    Returns: {
        "model": dict[team] = {"R1": prob, ...},     # 538 or KenPom
        "market": dict[team] = {"R1": prob, ...},     # DK or historical sportsbook
        "public": dict[team] = {"R1": prob, ...},     # ESPN or Yahoo
        "sources": {"model": str, "market": str, "public": str}
    }
    """
    result = {"model": {}, "market": {}, "public": {}, "sources": {}}

    # Model probabilities (prefer 538, fall back to Paine composite, then KenPom)
    model_data = load_538_probs(year)
    if model_data:
        result["model"] = model_data
        result["sources"]["model"] = f"538 ({year})"
    else:
        # Try Paine composite. IMPORTANT: Paine format is shifted by 1 round:
        # round1 = P(in field / survive play-in), NOT P(win R1 game).
        # round2 = P(win R1), round3 = P(advance past R2), ...
        # round6 = P(win championship). F4 = P(make championship game) is missing.
        paine_path = os.path.join("data/historical", f"pred.paine.men.{year}.csv")
        if os.path.exists(paine_path):
            model_data = _load_paine_csv(paine_path)
            if model_data:
                result["model"] = model_data
                result["sources"]["model"] = f"Paine composite ({year})"
        if not model_data:
            model_data = load_kenpom_probs(year)
            if model_data:
                result["model"] = model_data
                result["sources"]["model"] = f"KenPom ({year})"

    # Market probabilities (DK for 2026, historical for others)
    if year == 2026:
        result["market"] = load_dk_odds()
        result["sources"]["market"] = "DraftKings 2026"
    # TODO: load historical sportsbook odds when available

    # Public picks (prefer ESPN API, fall back to mRchmadness, then Yahoo)
    public_data = load_espn_api_picks(year)
    if public_data:
        result["public"] = public_data
        result["sources"]["public"] = f"ESPN Gambit API ({year})"
    else:
        public_data = load_pop_picks(year)
        if public_data:
            result["public"] = public_data
            result["sources"]["public"] = f"mRchmadness ESPN cache ({year})"

    if year == 2026:
        # Also load Yahoo as supplementary
        yahoo = load_yahoo_picks()
        if yahoo and not result["public"]:
            result["public"] = yahoo
            result["sources"]["public"] = "Yahoo Bracket Mayhem 2026"

    return result


def compute_leverage(model_prob: float, market_prob: float,
                     public_pick: float, model_weight: float = 0.5) -> dict:
    """
    Compute leverage using blended true probability.

    Returns: {
        "true_prob": blended probability,
        "leverage": true_prob / public_pick,
        "leverage_model": model_prob / public_pick,
        "leverage_market": market_prob / public_pick,
    }
    """
    if public_pick < 0.001:
        public_pick = 0.001

    # Blend model and market
    if model_prob > 0 and market_prob > 0:
        true_prob = model_weight * model_prob + (1 - model_weight) * market_prob
    elif model_prob > 0:
        true_prob = model_prob
    else:
        true_prob = market_prob

    return {
        "true_prob": true_prob,
        "leverage": true_prob / public_pick if true_prob > 0 else 0,
        "leverage_model": model_prob / public_pick if model_prob > 0 else 0,
        "leverage_market": market_prob / public_pick if market_prob > 0 else 0,
    }


# =============================================================================
# DIAGNOSTICS
# =============================================================================

def print_year_summary(year: int):
    """Print a summary of available data for a year."""
    data = load_year_data(year)
    print(f"\n{'='*70}")
    print(f"  {year} Data Summary")
    print(f"{'='*70}")
    for col in ["model", "market", "public"]:
        source = data["sources"].get(col, "NOT AVAILABLE")
        n_teams = len(data[col])
        if n_teams > 0:
            sample = list(data[col].items())[0]
            n_rounds = len(sample[1])
            print(f"  {col:8s}: {source} ({n_teams} teams, {n_rounds} rounds)")
        else:
            print(f"  {col:8s}: {source}")


if __name__ == "__main__":
    print("March Madness Data Loader — Coverage Report")
    for year in [2016, 2017, 2018, 2019, 2021, 2022, 2023, 2024, 2025, 2026]:
        print_year_summary(year)
