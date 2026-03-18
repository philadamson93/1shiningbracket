"""
DraftKings / Sportsbook Implied Probability Calculator for 2026 NCAA Tournament.

Contains hardcoded odds data from DraftKings, BetMGM, FanDuel, and other
sportsbooks (as of March 15-16, 2026 post-Selection Sunday). Converts
American odds to implied probabilities, removes vig, and outputs a CSV.

This is the "true probability" side of the leverage equation. Pair with
yahoo_pick_distribution.csv (public pick ownership) to find value.

Usage:
    python3 scrape_dk_odds.py

Output:
    dk_implied_odds.csv — team, seed, region, R1_implied, R2_implied,
                          S16_implied, E8_implied, F4_implied, championship_implied
    Prints summary table and leverage analysis to stdout

Data sources:
    - DraftKings championship futures (+330 Duke, etc.)
    - DraftKings/BetMGM/FanDuel Final Four odds (by region)
    - BetMGM Sweet 16 futures
    - First-round moneylines (for R1 implied probabilities)
    - ESPN BPI, KenPom, Bart Torvik, Nate Silver COOPER model consensus
    - SportsBettingDime Final Four odds (all 68 teams)

To update: Edit the TEAMS dict below when lines move. The rest is automatic.
"""

import csv
from datetime import datetime

# ============================================================
# FULL BRACKET + ODDS DATA
# ============================================================
# Each team entry:
#   "Team Name": {
#       "seed": int,
#       "region": str,
#       "r1_ml": int or None,          # R1 moneyline (American odds)
#       "champ_odds": int or None,      # Championship futures (American odds)
#       "ff_odds": int or None,         # Final Four futures (American odds)
#       "s16_implied_est": float,       # Sweet 16 implied % (0-1), from models/books
#       "e8_implied_est": float or None, # Elite 8 implied % (0-1), estimated
#   }
#
# NOTES:
# - r1_ml: negative = favorite, positive = underdog
# - champ_odds / ff_odds: always positive for underdogs, can be negative for heavy favs
# - s16_implied_est: midpoint of model consensus range from research
# - e8_implied_est: if None, will be interpolated from S16 and F4
# ============================================================

TEAMS = {
    # =========== EAST REGION ===========
    "Duke": {
        "seed": 1, "region": "East",
        "r1_ml": -20000,       # vs Siena
        "champ_odds": 330,     # DK +330
        "ff_odds": -175,       # SBD -175
        "s16_implied_est": 0.94,
        "e8_implied_est": 0.80,
    },
    "Connecticut": {
        "seed": 2, "region": "East",
        "r1_ml": -4500,        # vs Furman
        "champ_odds": 1700,    # DK +1700
        "ff_odds": 400,        # DK/FD +400
        "s16_implied_est": 0.90,
        "e8_implied_est": 0.50,
    },
    "Michigan St.": {
        "seed": 3, "region": "East",
        "r1_ml": -1800,        # vs North Dakota State
        "champ_odds": 4000,    # DK +4000
        "ff_odds": 700,        # SBR +700
        "s16_implied_est": 0.87,
        "e8_implied_est": 0.40,
    },
    "Kansas": {
        "seed": 4, "region": "East",
        "r1_ml": -1200,        # vs Cal Baptist
        "champ_odds": 7500,    # DK ~+7500
        "ff_odds": 1500,       # est. +1500
        "s16_implied_est": 0.79,
        "e8_implied_est": 0.32,
    },
    "St. John's": {
        "seed": 5, "region": "East",
        "r1_ml": -425,         # vs Northern Iowa
        "champ_odds": 6000,    # DK +6000
        "ff_odds": 1400,       # est. +1400
        "s16_implied_est": 0.74,
        "e8_implied_est": 0.25,
    },
    "Louisville": {
        "seed": 6, "region": "East",
        "r1_ml": -225,         # vs South Florida
        "champ_odds": 12000,   # DK +12000
        "ff_odds": 2500,       # est. +2500
        "s16_implied_est": 0.62,
        "e8_implied_est": 0.18,
    },
    "UCLA": {
        "seed": 7, "region": "East",
        "r1_ml": -225,         # vs UCF
        "champ_odds": 18000,   # DK +18000
        "ff_odds": 3000,       # est. +3000
        "s16_implied_est": 0.50,
        "e8_implied_est": 0.12,
    },
    "Ohio St.": {
        "seed": 8, "region": "East",
        "r1_ml": -142,         # vs TCU
        "champ_odds": 50000,   # est. +50000
        "ff_odds": 4000,       # est. +4000
        "s16_implied_est": 0.42,
        "e8_implied_est": 0.10,
    },
    "TCU": {
        "seed": 9, "region": "East",
        "r1_ml": 120,          # vs Ohio State
        "champ_odds": 75000,   # est.
        "ff_odds": 6000,       # est.
        "s16_implied_est": 0.32,
        "e8_implied_est": 0.06,
    },
    "UCF": {
        "seed": 10, "region": "East",
        "r1_ml": 185,          # vs UCLA
        "champ_odds": 40000,   # est.
        "ff_odds": 8000,       # est.
        "s16_implied_est": 0.18,
        "e8_implied_est": 0.04,
    },
    "South Florida": {
        "seed": 11, "region": "East",
        "r1_ml": 185,          # vs Louisville
        "champ_odds": 50000,   # est.
        "ff_odds": 10000,      # est.
        "s16_implied_est": 0.12,
        "e8_implied_est": 0.03,
    },
    "Northern Iowa": {
        "seed": 12, "region": "East",
        "r1_ml": 330,          # vs St. John's
        "champ_odds": 100000,  # est.
        "ff_odds": 25000,      # est.
        "s16_implied_est": 0.06,
        "e8_implied_est": 0.015,
    },
    "California Baptist": {
        "seed": 13, "region": "East",
        "r1_ml": 750,          # vs Kansas
        "champ_odds": 150000,  # est.
        "ff_odds": 50000,      # est.
        "s16_implied_est": 0.03,
        "e8_implied_est": 0.008,
    },
    "N. Dak. St.": {
        "seed": 14, "region": "East",
        "r1_ml": 1000,         # vs Michigan State
        "champ_odds": 200000,  # est.
        "ff_odds": 75000,      # est.
        "s16_implied_est": 0.02,
        "e8_implied_est": 0.005,
    },
    "Furman": {
        "seed": 15, "region": "East",
        "r1_ml": 1700,         # vs UConn
        "champ_odds": 250000,  # est.
        "ff_odds": 100000,     # est.
        "s16_implied_est": 0.01,
        "e8_implied_est": 0.003,
    },
    "Siena": {
        "seed": 16, "region": "East",
        "r1_ml": 3500,         # vs Duke
        "champ_odds": 500000,  # est.
        "ff_odds": 250000,     # est.
        "s16_implied_est": 0.005,
        "e8_implied_est": 0.001,
    },

    # =========== WEST REGION ===========
    "Arizona": {
        "seed": 1, "region": "West",
        "r1_ml": -50000,       # vs LIU
        "champ_odds": 400,     # DK +400
        "ff_odds": -138,       # SBD -138
        "s16_implied_est": 0.96,
        "e8_implied_est": 0.82,
    },
    "Purdue": {
        "seed": 2, "region": "West",
        "r1_ml": -8000,        # vs Queens
        "champ_odds": 3500,    # DK +3500
        "ff_odds": 350,        # est. +350
        "s16_implied_est": 0.91,
        "e8_implied_est": 0.54,
    },
    "Gonzaga": {
        "seed": 3, "region": "West",
        "r1_ml": -3500,        # vs Kennesaw State
        "champ_odds": 6500,    # DK ~+6500
        "ff_odds": 500,        # est. +500
        "s16_implied_est": 0.87,
        "e8_implied_est": 0.43,
    },
    "Arkansas": {
        "seed": 4, "region": "West",
        "r1_ml": -2400,        # vs Hawaii  (confirmed: -1350 to -2400 range)
        "champ_odds": 6000,    # DK +6000
        "ff_odds": 900,        # est. +900
        "s16_implied_est": 0.74,
        "e8_implied_est": 0.28,
    },
    "Wisconsin": {
        "seed": 5, "region": "West",
        "r1_ml": -470,         # vs High Point
        "champ_odds": 8000,    # est. +8000
        "ff_odds": 1500,       # est. +1500
        "s16_implied_est": 0.66,
        "e8_implied_est": 0.21,
    },
    "BYU": {
        "seed": 6, "region": "West",
        "r1_ml": -300,         # vs TX/NC State (est.)
        "champ_odds": 25000,   # DK +25000
        "ff_odds": 3000,       # est. +3000
        "s16_implied_est": 0.52,
        "e8_implied_est": 0.12,
    },
    "Miami (FL)": {
        "seed": 7, "region": "West",
        "r1_ml": -155,         # vs Missouri
        "champ_odds": 15000,   # est. +15000
        "ff_odds": 3500,       # est. +3500
        "s16_implied_est": 0.46,
        "e8_implied_est": 0.10,
    },
    "Villanova": {
        "seed": 8, "region": "West",
        "r1_ml": 104,          # vs Utah State (Villanova is the underdog)
        "champ_odds": 50000,   # est.
        "ff_odds": 5000,       # est. +5000
        "s16_implied_est": 0.32,
        "e8_implied_est": 0.06,
    },
    "Utah St.": {
        "seed": 9, "region": "West",
        "r1_ml": -126,         # vs Villanova (Utah St. favored)
        "champ_odds": 50000,   # est.
        "ff_odds": 5000,       # est. +5000
        "s16_implied_est": 0.38,
        "e8_implied_est": 0.07,
    },
    "Missouri": {
        "seed": 10, "region": "West",
        "r1_ml": 130,          # vs Miami (FL)
        "champ_odds": 50000,   # est.
        "ff_odds": 10000,      # est.
        "s16_implied_est": 0.15,
        "e8_implied_est": 0.03,
    },
    "TX/NCST": {
        "seed": 11, "region": "West",
        "r1_ml": 240,          # First Four winner vs BYU (est.)
        "champ_odds": 75000,   # est.
        "ff_odds": 15000,      # est.
        "s16_implied_est": 0.08,
        "e8_implied_est": 0.02,
    },
    "High Point": {
        "seed": 12, "region": "West",
        "r1_ml": 360,          # vs Wisconsin
        "champ_odds": 100000,  # est.
        "ff_odds": 25000,      # est.
        "s16_implied_est": 0.05,
        "e8_implied_est": 0.012,
    },
    "Hawaii": {
        "seed": 13, "region": "West",
        "r1_ml": 1200,         # vs Arkansas
        "champ_odds": 150000,  # est.
        "ff_odds": 50000,      # est.
        "s16_implied_est": 0.025,
        "e8_implied_est": 0.006,
    },
    "Kennesaw St.": {
        "seed": 14, "region": "West",
        "r1_ml": 1280,         # vs Gonzaga
        "champ_odds": 200000,  # est.
        "ff_odds": 75000,      # est.
        "s16_implied_est": 0.02,
        "e8_implied_est": 0.004,
    },
    "Queens University": {
        "seed": 15, "region": "West",
        "r1_ml": 2200,         # vs Purdue
        "champ_odds": 250000,  # est.
        "ff_odds": 100000,     # est.
        "s16_implied_est": 0.01,
        "e8_implied_est": 0.003,
    },
    "LIU Brooklyn": {
        "seed": 16, "region": "West",
        "r1_ml": 5500,         # vs Arizona
        "champ_odds": 500000,  # est.
        "ff_odds": 250000,     # est.
        "s16_implied_est": 0.004,
        "e8_implied_est": 0.001,
    },

    # =========== SOUTH REGION ===========
    "Florida": {
        "seed": 1, "region": "South",
        "r1_ml": -10000,       # vs PV A&M/Lehigh (est.)
        "champ_odds": 650,     # DK +650
        "ff_odds": -103,       # SBD -103
        "s16_implied_est": 0.84,
        "e8_implied_est": 0.61,
    },
    "Houston": {
        "seed": 2, "region": "South",
        "r1_ml": -6000,        # vs Idaho
        "champ_odds": 1000,    # DK +1000
        "ff_odds": 230,        # DK +230
        "s16_implied_est": 0.90,
        "e8_implied_est": 0.58,
    },
    "Illinois": {
        "seed": 3, "region": "South",
        "r1_ml": -5000,        # vs Penn
        "champ_odds": 1900,    # DK +1900
        "ff_odds": 320,        # DK +320
        "s16_implied_est": 0.87,
        "e8_implied_est": 0.45,
    },
    "Nebraska": {
        "seed": 4, "region": "South",
        "r1_ml": -1000,        # vs Troy
        "champ_odds": 8000,    # est. +8000
        "ff_odds": 1500,       # est. +1500
        "s16_implied_est": 0.75,
        "e8_implied_est": 0.25,
    },
    "Vanderbilt": {
        "seed": 5, "region": "South",
        "r1_ml": -625,         # vs McNeese
        "champ_odds": 8000,    # est. +8000
        "ff_odds": 2000,       # est. +2000
        "s16_implied_est": 0.66,
        "e8_implied_est": 0.25,
    },
    "N. Carolina": {
        "seed": 6, "region": "South",
        "r1_ml": -145,         # vs VCU
        "champ_odds": 10000,   # est. +10000
        "ff_odds": 2500,       # est. +2500
        "s16_implied_est": 0.52,
        "e8_implied_est": 0.15,
    },
    "St. Mary's": {
        "seed": 7, "region": "South",
        "r1_ml": -135,         # vs Texas A&M
        "champ_odds": 15000,   # est. +15000
        "ff_odds": 3500,       # est. +3500
        "s16_implied_est": 0.46,
        "e8_implied_est": 0.10,
    },
    "Clemson": {
        "seed": 8, "region": "South",
        "r1_ml": 115,          # vs Iowa (Clemson is underdog)
        "champ_odds": 50000,   # est.
        "ff_odds": 5000,       # est.
        "s16_implied_est": 0.28,
        "e8_implied_est": 0.05,
    },
    "Iowa": {
        "seed": 9, "region": "South",
        "r1_ml": -135,         # vs Clemson (Iowa favored)
        "champ_odds": 30000,   # est.
        "ff_odds": 5000,       # est.
        "s16_implied_est": 0.35,
        "e8_implied_est": 0.07,
    },
    "Texas A&M": {
        "seed": 10, "region": "South",
        "r1_ml": 115,          # vs Saint Mary's
        "champ_odds": 50000,   # est.
        "ff_odds": 10000,      # est.
        "s16_implied_est": 0.15,
        "e8_implied_est": 0.03,
    },
    "VCU": {
        "seed": 11, "region": "South",
        "r1_ml": 120,          # vs North Carolina
        "champ_odds": 75000,   # est.
        "ff_odds": 15000,      # est.
        "s16_implied_est": 0.10,
        "e8_implied_est": 0.02,
    },
    "McNeese": {
        "seed": 12, "region": "South",
        "r1_ml": 455,          # vs Vanderbilt
        "champ_odds": 100000,  # est.
        "ff_odds": 25000,      # est.
        "s16_implied_est": 0.05,
        "e8_implied_est": 0.012,
    },
    "Troy": {
        "seed": 13, "region": "South",
        "r1_ml": 650,          # vs Nebraska
        "champ_odds": 150000,  # est.
        "ff_odds": 50000,      # est.
        "s16_implied_est": 0.03,
        "e8_implied_est": 0.006,
    },
    "Pennsylvania": {
        "seed": 14, "region": "South",
        "r1_ml": 2000,         # vs Illinois (est.)
        "champ_odds": 200000,  # est.
        "ff_odds": 75000,      # est.
        "s16_implied_est": 0.015,
        "e8_implied_est": 0.004,
    },
    "Idaho": {
        "seed": 15, "region": "South",
        "r1_ml": 2500,         # vs Houston
        "champ_odds": 250000,  # est.
        "ff_odds": 100000,     # est.
        "s16_implied_est": 0.01,
        "e8_implied_est": 0.003,
    },
    "PV/LEH": {
        "seed": 16, "region": "South",
        "r1_ml": 3000,         # vs Florida (est.)
        "champ_odds": 500000,  # est.
        "ff_odds": 250000,     # est.
        "s16_implied_est": 0.004,
        "e8_implied_est": 0.001,
    },

    # =========== MIDWEST REGION ===========
    "Michigan": {
        "seed": 1, "region": "Midwest",
        "r1_ml": -15000,       # vs UMBC/Howard (est.)
        "champ_odds": 350,     # DK +350
        "ff_odds": -150,       # FOX/DK -150
        "s16_implied_est": 0.94,
        "e8_implied_est": 0.78,
    },
    "Iowa St.": {
        "seed": 2, "region": "Midwest",
        "r1_ml": -10000,       # vs Tennessee State
        "champ_odds": 1500,    # DK +1500
        "ff_odds": 425,        # DK/FOX +425
        "s16_implied_est": 0.90,
        "e8_implied_est": 0.52,
    },
    "Virginia": {
        "seed": 3, "region": "Midwest",
        "r1_ml": -3000,        # vs Wright State
        "champ_odds": 7500,    # est. +7500
        "ff_odds": 600,        # est. +600
        "s16_implied_est": 0.85,
        "e8_implied_est": 0.38,
    },
    "Alabama": {
        "seed": 4, "region": "Midwest",
        "r1_ml": -850,         # vs Hofstra (est.)
        "champ_odds": 5000,    # est. +5000
        "ff_odds": 800,        # est. +800
        "s16_implied_est": 0.75,
        "e8_implied_est": 0.23,
    },
    "Texas Tech": {
        "seed": 5, "region": "Midwest",
        "r1_ml": -400,         # vs Akron
        "champ_odds": 8000,    # est. +8000
        "ff_odds": 1500,       # est. +1500
        "s16_implied_est": 0.64,
        "e8_implied_est": 0.19,
    },
    "Tennessee": {
        "seed": 6, "region": "Midwest",
        "r1_ml": -300,         # vs SMU/Miami OH (est.)
        "champ_odds": 10000,   # est. +10000
        "ff_odds": 2000,       # est. +2000
        "s16_implied_est": 0.52,
        "e8_implied_est": 0.16,
    },
    "Kentucky": {
        "seed": 7, "region": "Midwest",
        "r1_ml": -180,         # vs Santa Clara (sharp move to -4.5)
        "champ_odds": 15000,   # est. +15000
        "ff_odds": 2500,       # est. +2500
        "s16_implied_est": 0.48,
        "e8_implied_est": 0.12,
    },
    "Georgia": {
        "seed": 8, "region": "Midwest",
        "r1_ml": -135,         # vs Saint Louis
        "champ_odds": 50000,   # est.
        "ff_odds": 5000,       # est. +5000
        "s16_implied_est": 0.35,
        "e8_implied_est": 0.06,
    },
    "Saint Louis": {
        "seed": 9, "region": "Midwest",
        "r1_ml": 115,          # vs Georgia
        "champ_odds": 35000,   # BetMGM notable action
        "ff_odds": 5000,       # est. +5000
        "s16_implied_est": 0.30,
        "e8_implied_est": 0.05,
    },
    "Santa Clara": {
        "seed": 10, "region": "Midwest",
        "r1_ml": 130,          # vs Kentucky
        "champ_odds": 75000,   # est.
        "ff_odds": 10000,      # est.
        "s16_implied_est": 0.14,
        "e8_implied_est": 0.03,
    },
    "MOH/SMU": {
        "seed": 11, "region": "Midwest",
        "r1_ml": 240,          # vs Tennessee (est., First Four winner)
        "champ_odds": 100000,  # est.
        "ff_odds": 15000,      # est.
        "s16_implied_est": 0.07,
        "e8_implied_est": 0.015,
    },
    "Akron": {
        "seed": 12, "region": "Midwest",
        "r1_ml": 310,          # vs Texas Tech
        "champ_odds": 100000,  # est.
        "ff_odds": 25000,      # est.
        "s16_implied_est": 0.06,
        "e8_implied_est": 0.015,
    },
    "Hofstra": {
        "seed": 13, "region": "Midwest",
        "r1_ml": 575,          # vs Alabama
        "champ_odds": 150000,  # est.
        "ff_odds": 50000,      # est.
        "s16_implied_est": 0.03,
        "e8_implied_est": 0.007,
    },
    "Wright St.": {
        "seed": 14, "region": "Midwest",
        "r1_ml": 1400,         # vs Virginia
        "champ_odds": 200000,  # est.
        "ff_odds": 75000,      # est.
        "s16_implied_est": 0.02,
        "e8_implied_est": 0.005,
    },
    "Tennessee St.": {
        "seed": 15, "region": "Midwest",
        "r1_ml": 3000,         # vs Iowa State
        "champ_odds": 250000,  # est.
        "ff_odds": 100000,     # est.
        "s16_implied_est": 0.008,
        "e8_implied_est": 0.002,
    },
    "UMBC/HOW": {
        "seed": 16, "region": "Midwest",
        "r1_ml": 5000,         # vs Michigan (est.)
        "champ_odds": 500000,  # est.
        "ff_odds": 250000,     # est.
        "s16_implied_est": 0.004,
        "e8_implied_est": 0.001,
    },
}


# ============================================================
# HISTORICAL SEED-BASED PROBABILITIES (FALLBACK)
# ============================================================
# Used for teams missing explicit odds. Based on historical NCAA
# tournament data (1985-2025 averages).

SEED_HISTORICAL = {
    #  seed: (R1_win, R2_win, S16, E8, F4, Champ)
    1:  (0.993, 0.88, 0.87, 0.64, 0.39, 0.13),
    2:  (0.938, 0.72, 0.68, 0.40, 0.21, 0.06),
    3:  (0.851, 0.56, 0.48, 0.25, 0.12, 0.03),
    4:  (0.793, 0.50, 0.40, 0.19, 0.08, 0.02),
    5:  (0.650, 0.38, 0.25, 0.11, 0.04, 0.01),
    6:  (0.612, 0.34, 0.21, 0.09, 0.04, 0.01),
    7:  (0.604, 0.29, 0.18, 0.07, 0.03, 0.008),
    8:  (0.500, 0.22, 0.12, 0.05, 0.02, 0.005),
    9:  (0.500, 0.22, 0.12, 0.05, 0.02, 0.005),
    10: (0.396, 0.16, 0.08, 0.03, 0.01, 0.003),
    11: (0.388, 0.14, 0.07, 0.03, 0.01, 0.003),
    12: (0.350, 0.10, 0.05, 0.02, 0.006, 0.001),
    13: (0.207, 0.05, 0.02, 0.006, 0.002, 0.0005),
    14: (0.149, 0.03, 0.012, 0.004, 0.001, 0.0003),
    15: (0.069, 0.015, 0.005, 0.002, 0.0005, 0.0001),
    16: (0.012, 0.005, 0.002, 0.001, 0.0003, 0.0001),
}


# ============================================================
# CONVERSION FUNCTIONS
# ============================================================

def american_to_implied(odds: int) -> float:
    """
    Convert American odds to raw implied probability (includes vig).
    Positive odds: 100 / (odds + 100)
    Negative odds: |odds| / (|odds| + 100)
    """
    if odds > 0:
        return 100.0 / (odds + 100.0)
    else:
        return abs(odds) / (abs(odds) + 100.0)


def remove_vig_group(probs: list[float]) -> list[float]:
    """
    Normalize a group of raw implied probabilities so they sum to 1.0.
    This removes the sportsbook's vig/juice.
    """
    total = sum(probs)
    if total == 0:
        return probs
    return [p / total for p in probs]


def compute_team_probabilities(team_name: str, data: dict) -> dict:
    """
    Compute fair (vig-removed) implied probabilities for a single team.
    Returns dict with R1, R2, S16, E8, F4, championship implied probs.
    """
    seed = data["seed"]
    hist = SEED_HISTORICAL.get(seed, SEED_HISTORICAL[16])

    # --- Round 1 (from moneyline) ---
    r1_ml = data.get("r1_ml")
    if r1_ml is not None:
        r1_raw = american_to_implied(r1_ml)
        # Approximate vig removal: a 2-team market typically has ~5% vig
        # For heavy favorites, vig removal barely changes the number.
        # For close games, both sides sum to ~1.05; divide by that.
        # We'll use a simple approach: cap at 0.999 and floor at 0.001
        r1_implied = min(0.999, max(0.001, r1_raw / 1.025))
    else:
        r1_implied = hist[0]

    # --- Championship (from futures) ---
    champ_odds = data.get("champ_odds")
    if champ_odds is not None:
        champ_raw = american_to_implied(champ_odds)
        # Futures markets typically have 30-50% overround for 68-team field.
        # We'll normalize in a batch step later, but compute raw first.
        champ_implied_raw = champ_raw
    else:
        champ_implied_raw = hist[5]

    # --- Final Four (from futures) ---
    ff_odds = data.get("ff_odds")
    if ff_odds is not None:
        ff_raw = american_to_implied(ff_odds)
        # Regional FF markets have ~4 realistic teams summing to ~1.15-1.25
        # We'll do batch normalization later
        ff_implied_raw = ff_raw
    else:
        ff_implied_raw = hist[4]

    # --- Sweet 16 (from model consensus / estimate) ---
    s16_est = data.get("s16_implied_est")
    if s16_est is not None:
        s16_implied = s16_est
    else:
        s16_implied = hist[2]

    # --- Elite 8 (from model consensus / estimate, or interpolated) ---
    e8_est = data.get("e8_implied_est")
    if e8_est is not None:
        e8_implied = e8_est
    else:
        # Interpolate: E8 ~ midpoint of S16 and FF
        e8_implied = (s16_implied + ff_implied_raw) / 2.0

    # --- Round of 32 (R2) ---
    # R2 = make it past R1 and R2. Approximate from S16 / (S16 conditional on R2).
    # Simpler: R2 ~= sqrt(R1 * S16) -- geometric mean of R1 win and S16 reach.
    # Or: R2 = R1 * (historical R2 win rate for seed)
    # Best approach: R2 = S16 / P(win R2 game | reach R2).
    # For top seeds, P(win R2) ~ S16/R1; we can back it out.
    # Simplest: if we know R1 and S16, then R2 is implicit via:
    #   P(reach S16) = P(win R1) * P(win R2 | reach R2)
    #   => P(win R2 | reach R2) = S16 / R1
    #   => P(reach R2) = P(win R1) [just need to win R1]
    # Actually "R2" means "reach Round of 32" = same as winning R1.
    # What we want for the CSV: probability of reaching each round.
    # R1 = probability of winning R1 game (= reaching R32)
    # R2 = probability of reaching Sweet 16 = what we call S16
    # Let me redefine to be clearer:
    #   R64_win = win first game = r1_implied
    #   R32_win = reach Sweet 16 = s16_implied
    #   S16_win = reach Elite 8  = e8_implied
    #   E8_win  = reach Final Four = ff_implied
    #   F4_win  = reach Championship game
    #   Championship_win = win title = champ_implied
    #
    # We'll output "probability of reaching round X":
    #   R1 (win R64)  -> r1_implied
    #   R2 (reach R32 = win R64) -> r1_implied  [same thing]
    #   S16 (reach S16) -> s16_implied
    #   E8 (reach E8)  -> e8_implied
    #   F4 (reach F4)  -> ff_implied_raw
    #   Championship (win title) -> champ_implied_raw

    return {
        "team": team_name,
        "seed": seed,
        "region": data["region"],
        "R1_implied": r1_implied,
        "S16_implied": s16_implied,
        "E8_implied": e8_implied,
        "F4_implied": ff_implied_raw,
        "championship_implied": champ_implied_raw,
    }


def normalize_championship_probs(rows: list[dict]) -> list[dict]:
    """
    Normalize championship implied probabilities so all 64 teams sum to 1.0.
    (68 teams but First Four reduces to 64 before R1.)
    This removes the futures market vig.
    """
    total = sum(r["championship_implied"] for r in rows)
    if total > 0:
        for r in rows:
            r["championship_implied"] = r["championship_implied"] / total
    return rows


def normalize_ff_probs_by_region(rows: list[dict]) -> list[dict]:
    """
    Normalize Final Four implied probabilities within each region so
    each region sums to 1.0 (exactly one team from each region makes the FF).
    """
    regions = set(r["region"] for r in rows)
    for region in regions:
        region_rows = [r for r in rows if r["region"] == region]
        total = sum(r["F4_implied"] for r in region_rows)
        if total > 0:
            for r in region_rows:
                r["F4_implied"] = r["F4_implied"] / total
    return rows


def normalize_s16_probs_by_pod(rows: list[dict]) -> list[dict]:
    """
    Light normalization: ensure S16 probs are reasonable within region.
    S16 has 4 spots per region (from 4 pods of 4 teams).
    We won't over-normalize here since S16 estimates are already
    from calibrated models, but we'll do a sanity cap.
    """
    regions = set(r["region"] for r in rows)
    for region in regions:
        region_rows = sorted(
            [r for r in rows if r["region"] == region],
            key=lambda x: x["seed"]
        )
        total_s16 = sum(r["S16_implied"] for r in region_rows)
        # Each region sends 4 teams to S16; expected sum ~ 4.0
        # If total is way off, scale it
        if total_s16 > 0:
            target = 4.0
            scale = target / total_s16
            for r in region_rows:
                r["S16_implied"] = min(0.999, r["S16_implied"] * scale)
    return rows


def normalize_e8_probs_by_region(rows: list[dict]) -> list[dict]:
    """
    Normalize E8 probabilities within each region to sum to 2.0
    (2 teams from each region make the Elite 8).
    """
    regions = set(r["region"] for r in rows)
    for region in regions:
        region_rows = [r for r in rows if r["region"] == region]
        total = sum(r["E8_implied"] for r in region_rows)
        if total > 0:
            target = 2.0
            scale = target / total
            for r in region_rows:
                r["E8_implied"] = min(0.999, r["E8_implied"] * scale)
    return rows


def ensure_monotonic(rows: list[dict]) -> list[dict]:
    """
    Ensure probabilities are monotonically decreasing across rounds
    for each team: R1 >= S16 >= E8 >= F4 >= Championship.
    """
    for r in rows:
        # R1 should be highest
        r["S16_implied"] = min(r["S16_implied"], r["R1_implied"])
        r["E8_implied"] = min(r["E8_implied"], r["S16_implied"])
        r["F4_implied"] = min(r["F4_implied"], r["E8_implied"])
        r["championship_implied"] = min(r["championship_implied"], r["F4_implied"])
    return rows


def write_csv(rows: list[dict], filepath: str):
    """Write results to CSV."""
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


def print_summary(rows: list[dict]):
    """Print formatted summary table to stdout."""
    sorted_rows = sorted(rows, key=lambda x: -x["championship_implied"])

    print(f"\n{'='*100}")
    print(f"  2026 NCAA TOURNAMENT — SPORTSBOOK IMPLIED PROBABILITIES (VIG-REMOVED)")
    print(f"  Data: DraftKings, BetMGM, FanDuel, ESPN BPI, KenPom consensus")
    print(f"  Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*100}")
    print(f"  {'Team':<22} {'Seed':>4} {'Region':<10} {'R1%':>7} {'S16%':>7} {'E8%':>7} {'F4%':>7} {'Champ%':>7}")
    print(f"  {'-'*22} {'-'*4} {'-'*10} {'-'*7} {'-'*7} {'-'*7} {'-'*7} {'-'*7}")

    for row in sorted_rows:
        print(
            f"  {row['team']:<22} {row['seed']:4d} {row['region']:<10} "
            f"{row['R1_implied']*100:6.1f}% "
            f"{row['S16_implied']*100:6.1f}% "
            f"{row['E8_implied']*100:6.1f}% "
            f"{row['F4_implied']*100:6.1f}% "
            f"{row['championship_implied']*100:6.2f}%"
        )

    # Sanity checks
    print(f"\n{'='*100}")
    print(f"  SANITY CHECKS")
    print(f"{'='*100}")

    total_champ = sum(r["championship_implied"] for r in rows) * 100
    print(f"  Championship probs sum: {total_champ:.1f}% (should be ~100%)")

    for region in ["East", "West", "South", "Midwest"]:
        region_rows = [r for r in rows if r["region"] == region]
        ff_sum = sum(r["F4_implied"] for r in region_rows) * 100
        s16_sum = sum(r["S16_implied"] for r in region_rows)
        e8_sum = sum(r["E8_implied"] for r in region_rows)
        print(
            f"  {region:10s} — FF sum: {ff_sum:5.1f}% | "
            f"S16 spots: {s16_sum:.2f} (expect ~4) | "
            f"E8 spots: {e8_sum:.2f} (expect ~2)"
        )


def print_region_summary(rows: list[dict]):
    """Print region-by-region breakdown."""
    for region in ["East", "West", "South", "Midwest"]:
        region_rows = sorted(
            [r for r in rows if r["region"] == region],
            key=lambda x: x["seed"]
        )
        print(f"\n{'='*80}")
        print(f"  {region.upper()} REGION")
        print(f"{'='*80}")
        print(f"  {'Team':<22} {'Seed':>4}  {'R1%':>7} {'S16%':>7} {'E8%':>7} {'F4%':>7} {'Champ%':>7}")
        print(f"  {'-'*22} {'-'*4}  {'-'*7} {'-'*7} {'-'*7} {'-'*7} {'-'*7}")
        for row in region_rows:
            print(
                f"  {row['team']:<22} {row['seed']:4d}  "
                f"{row['R1_implied']*100:6.1f}% "
                f"{row['S16_implied']*100:6.1f}% "
                f"{row['E8_implied']*100:6.1f}% "
                f"{row['F4_implied']*100:6.1f}% "
                f"{row['championship_implied']*100:6.2f}%"
            )


def print_leverage_vs_yahoo(rows: list[dict]):
    """
    Compare DK implied probs to Yahoo pick distribution.
    Reads yahoo_pick_distribution.csv if available.
    """
    import os
    yahoo_path = os.path.join(os.path.dirname(__file__) or ".", "yahoo_pick_distribution.csv")
    if not os.path.exists(yahoo_path):
        print(f"\n  [Yahoo pick data not found at {yahoo_path} — skipping leverage analysis]")
        return

    # Read Yahoo data
    yahoo_data = {}  # {(team, round_label): pick_pct}
    with open(yahoo_path, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            key = (row["team"], row["round_label"])
            yahoo_data[key] = float(row["pick_pct"])

    # Map our round names to Yahoo round labels
    round_map = {
        "S16": "S16",
        "E8": "E8",
        "F4": "F4",
        "championship": "Championship",
    }

    print(f"\n{'='*110}")
    print(f"  LEVERAGE ANALYSIS: DK Implied vs Yahoo Public Pick%")
    print(f"  Leverage > 1.3 = UNDEROWNED VALUE | Leverage < 0.7 = OVEROWNED FADE")
    print(f"{'='*110}")
    print(
        f"  {'Team':<22} {'Round':<8} {'Yahoo%':>8} {'DK Impl%':>9} "
        f"{'Leverage':>9}  {'Signal':<15}"
    )
    print(
        f"  {'-'*22} {'-'*8} {'-'*8} {'-'*9} "
        f"{'-'*9}  {'-'*15}"
    )

    leverage_rows = []
    for row in rows:
        team = row["team"]
        for our_round, yahoo_round in round_map.items():
            if our_round == "championship":
                dk_pct = row["championship_implied"]
            else:
                dk_pct = row[f"{our_round}_implied"]

            yahoo_key = (team, yahoo_round)
            if yahoo_key in yahoo_data:
                yahoo_pct = yahoo_data[yahoo_key] / 100.0
                if yahoo_pct > 0.001:
                    leverage = dk_pct / yahoo_pct
                    leverage_rows.append({
                        "team": team,
                        "round": yahoo_round,
                        "yahoo_pct": yahoo_pct,
                        "dk_pct": dk_pct,
                        "leverage": leverage,
                    })

    # Sort by most underowned (highest leverage) first
    leverage_rows.sort(key=lambda x: -x["leverage"])

    # Print top underowned (VALUE)
    print(f"\n  --- TOP 25 UNDEROWNED (VALUE) ---")
    for lr in leverage_rows[:25]:
        signal = ""
        if lr["leverage"] > 2.0:
            signal = "STRONG VALUE"
        elif lr["leverage"] > 1.5:
            signal = "VALUE"
        elif lr["leverage"] > 1.3:
            signal = "mild value"
        print(
            f"  {lr['team']:<22} {lr['round']:<8} "
            f"{lr['yahoo_pct']*100:7.2f}% {lr['dk_pct']*100:8.2f}% "
            f"{lr['leverage']:8.2f}x  {signal:<15}"
        )

    # Print top overowned (FADE)
    print(f"\n  --- TOP 25 OVEROWNED (FADE) ---")
    leverage_rows.sort(key=lambda x: x["leverage"])
    for lr in leverage_rows[:25]:
        signal = ""
        if lr["leverage"] < 0.4:
            signal = "STRONG FADE"
        elif lr["leverage"] < 0.6:
            signal = "FADE"
        elif lr["leverage"] < 0.7:
            signal = "mild fade"
        if signal:
            print(
                f"  {lr['team']:<22} {lr['round']:<8} "
                f"{lr['yahoo_pct']*100:7.2f}% {lr['dk_pct']*100:8.2f}% "
                f"{lr['leverage']:8.2f}x  {signal:<15}"
            )


def main():
    print(f"2026 NCAA Tournament — Sportsbook Implied Probability Calculator")
    print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Teams loaded: {len(TEAMS)}")

    # Step 1: Compute raw probabilities for each team
    rows = []
    for team_name, data in TEAMS.items():
        row = compute_team_probabilities(team_name, data)
        rows.append(row)

    # Step 2: Normalize championship probabilities (remove futures vig)
    rows = normalize_championship_probs(rows)

    # Step 3: Normalize Final Four probabilities by region
    rows = normalize_ff_probs_by_region(rows)

    # Step 4: Normalize S16 probabilities by region (light touch)
    rows = normalize_s16_probs_by_pod(rows)

    # Step 5: Normalize E8 probabilities by region
    rows = normalize_e8_probs_by_region(rows)

    # Step 6: Ensure monotonic decrease across rounds
    rows = ensure_monotonic(rows)

    # Step 7: Print results
    print_summary(rows)
    print_region_summary(rows)

    # Step 8: Write CSV
    csv_path = "data/dk_implied_odds.csv"
    write_csv(rows, csv_path)

    # Step 9: Leverage analysis vs Yahoo
    print_leverage_vs_yahoo(rows)

    print(f"\n{'='*100}")
    print(f"  OUTPUT: {csv_path}")
    print(f"  To update odds: edit the TEAMS dict at the top of this script.")
    print(f"  Re-run anytime for updated calculations.")
    print(f"{'='*100}")


if __name__ == "__main__":
    main()
