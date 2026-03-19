"""
Core simulation engine for March Madness bracket optimization.

Flat 63-game bracket representation for fast scoring.
Model separation: truth (perturbed) != model (our picks) != public (opponents).

Usage:
    from sim_engine import *
    gt = build_game_tree()
    outcome = simulate_tournament(probs, gt)
    score = score_bracket(bracket, outcome)
"""

import random
import math
from data_loader import load_year_data, normalize_team_name

# =============================================================================
# BRACKET STRUCTURE (2026)
# =============================================================================

REGIONS = ["East", "West", "South", "Midwest"]

BRACKET = {
    "East": [
        ("Duke", 1), ("Siena", 16),
        ("Ohio State", 8), ("TCU", 9),
        ("St. John's", 5), ("Northern Iowa", 12),
        ("Kansas", 4), ("Cal Baptist", 13),
        ("Louisville", 6), ("South Florida", 11),
        ("Michigan State", 3), ("North Dakota St", 14),
        ("UCLA", 7), ("UCF", 10),
        ("UConn", 2), ("Furman", 15),
    ],
    "West": [
        ("Arizona", 1), ("LIU", 16),
        ("Villanova", 8), ("Utah State", 9),
        ("Wisconsin", 5), ("High Point", 12),
        ("Arkansas", 4), ("Hawaii", 13),
        ("BYU", 6), ("Texas", 11),  # Texas beat NC State in First Four
        ("Gonzaga", 3), ("Kennesaw State", 14),
        ("Miami FL", 7), ("Missouri", 10),
        ("Purdue", 2), ("Queens", 15),
    ],
    "South": [
        ("Florida", 1), ("Lehigh", 16),
        ("Clemson", 8), ("Iowa", 9),
        ("Vanderbilt", 5), ("McNeese", 12),
        ("Nebraska", 4), ("Troy", 13),
        ("North Carolina", 6), ("VCU", 11),
        ("Illinois", 3), ("Penn", 14),
        ("Saint Mary's", 7), ("Texas A&M", 10),
        ("Houston", 2), ("Idaho", 15),
    ],
    "Midwest": [
        ("Michigan", 1), ("Howard", 16),  # Howard beat UMBC in First Four
        ("Georgia", 8), ("Saint Louis", 9),
        ("Texas Tech", 5), ("Akron", 12),
        ("Alabama", 4), ("Hofstra", 13),
        ("Tennessee", 6), ("SMU", 11),
        ("Virginia", 3), ("Wright State", 14),
        ("Kentucky", 7), ("Santa Clara", 10),
        ("Iowa State", 2), ("Tennessee State", 15),
    ],
}

SCORING = {"R1": 10, "R2": 20, "S16": 40, "E8": 80, "F4": 160, "Championship": 320}

ROUND_NAMES = ["R1", "R2", "S16", "E8", "F4", "Championship"]


# =============================================================================
# GAME TREE
# =============================================================================

def build_game_tree():
    """
    Build the 63-game tree from the BRACKET structure.

    Returns: (r1_matchups, feeder_games, game_round, game_points)
        r1_matchups: list of 32 (team_a, team_b) tuples
        feeder_games: dict {game_idx: (feeder_a, feeder_b)} for games 32-62
        game_round: list of 63 round name strings
        game_points: list of 63 point values
    """
    # R1 matchups from bracket seedings
    r1_matchups = []
    for region in REGIONS:
        teams = BRACKET[region]
        for i in range(8):
            r1_matchups.append((teams[i * 2][0], teams[i * 2 + 1][0]))

    # Feeder structure
    feeder_games = {}

    # R2 (games 32-47) feeds from R1 (games 0-31)
    for region_idx in range(4):
        for j in range(4):
            r2_game = 32 + region_idx * 4 + j
            r1_a = region_idx * 8 + j * 2
            r1_b = region_idx * 8 + j * 2 + 1
            feeder_games[r2_game] = (r1_a, r1_b)

    # S16 (games 48-55) feeds from R2 (games 32-47)
    for region_idx in range(4):
        for j in range(2):
            s16_game = 48 + region_idx * 2 + j
            r2_a = 32 + region_idx * 4 + j * 2
            r2_b = 32 + region_idx * 4 + j * 2 + 1
            feeder_games[s16_game] = (r2_a, r2_b)

    # E8 (games 56-59) feeds from S16 (games 48-55)
    for region_idx in range(4):
        e8_game = 56 + region_idx
        s16_a = 48 + region_idx * 2
        s16_b = 48 + region_idx * 2 + 1
        feeder_games[e8_game] = (s16_a, s16_b)

    # F4 (games 60-61) feeds from E8 (games 56-59)
    feeder_games[60] = (56, 57)  # East vs West
    feeder_games[61] = (58, 59)  # South vs Midwest

    # Championship (game 62) feeds from F4
    feeder_games[62] = (60, 61)

    # Round labels and point values for each game
    game_round = []
    game_points = []
    round_sizes = [32, 16, 8, 4, 2, 1]  # games per round
    for rd_idx, rd_name in enumerate(ROUND_NAMES):
        pts = SCORING[rd_name]
        for _ in range(round_sizes[rd_idx]):
            game_round.append(rd_name)
            game_points.append(pts)

    return r1_matchups, feeder_games, game_round, game_points


# =============================================================================
# PROBABILITY FUNCTIONS
# =============================================================================

def get_game_prob(team_a, team_b, probs, round_name):
    """
    P(team_a beats team_b) using advancement probability normalization.
    probs: dict[team] = {"R1": prob, "R2": prob, ...}
    """
    pa = probs.get(team_a, {}).get(round_name, 0.001)
    pb = probs.get(team_b, {}).get(round_name, 0.001)
    if pa + pb <= 0:
        return 0.5
    return pa / (pa + pb)


def perturb_probs(probs, sigma):
    """
    Perturb model probabilities in logit space with per-team correlated noise.

    Each team gets one noise draw applied to all rounds. This models
    "Duke is actually better/worse than the model thinks" — correlated
    across rounds, which is how real model error works.

    sigma: standard deviation in logit space (~0.3-0.5 typical)
    """
    perturbed = {}
    for team, rounds in probs.items():
        team_noise = random.gauss(0, sigma)
        perturbed[team] = {}
        for rd, prob in rounds.items():
            # Clamp input to avoid log(0)
            p = max(0.001, min(0.999, prob))
            logit = math.log(p / (1 - p))
            perturbed_logit = logit + team_noise
            perturbed[team][rd] = 1.0 / (1.0 + math.exp(-perturbed_logit))
    return perturbed


def blend_probs(model, market, model_weight=0.35):
    """
    Blend model and market probabilities.
    Interpolates missing R2 from market data geometrically: R2 ≈ sqrt(R1 × S16).
    """
    all_teams = set(list(model.keys()) + list(market.keys()))
    blended = {}
    for team in all_teams:
        m = model.get(team, {})
        k = market.get(team, {})

        # Interpolate missing R2 in market data
        if "R2" not in k and "R1" in k and "S16" in k:
            k = dict(k)
            k["R2"] = math.sqrt(k["R1"] * k["S16"])

        blended[team] = {}
        for rd in ROUND_NAMES:
            mp = m.get(rd, 0)
            kp = k.get(rd, 0)
            if mp > 0 and kp > 0:
                blended[team][rd] = model_weight * mp + (1 - model_weight) * kp
            elif mp > 0:
                blended[team][rd] = mp
            elif kp > 0:
                blended[team][rd] = kp
            # else: leave missing (team not in this round's data)
    return blended


# =============================================================================
# SIMULATION
# =============================================================================

def simulate_tournament(probs, game_tree):
    """
    Simulate a full tournament. Returns list of 63 team names (winners).
    probs: dict[team] = {"R1": prob, ...} — the "truth" probabilities.
    """
    r1_matchups, feeder_games, game_round, game_points = game_tree
    outcome = [None] * 63

    for g in range(63):
        if g < 32:
            team_a, team_b = r1_matchups[g]
        else:
            fa, fb = feeder_games[g]
            team_a = outcome[fa]
            team_b = outcome[fb]

        rd = game_round[g]
        prob_a = get_game_prob(team_a, team_b, probs, rd)
        outcome[g] = team_a if random.random() < prob_a else team_b

    return outcome


def make_chalk_bracket(probs, game_tree):
    """
    Generate the chalk (all-favorites) bracket. No randomness.
    Always picks the team with higher advancement probability.
    """
    r1_matchups, feeder_games, game_round, game_points = game_tree
    bracket = [None] * 63

    for g in range(63):
        if g < 32:
            team_a, team_b = r1_matchups[g]
        else:
            fa, fb = feeder_games[g]
            team_a = bracket[fa]
            team_b = bracket[fb]

        rd = game_round[g]
        prob_a = get_game_prob(team_a, team_b, probs, rd)
        bracket[g] = team_a if prob_a >= 0.5 else team_b

    return bracket


def generate_opponent(public_probs, game_tree):
    """
    Generate one opponent bracket by sampling from public pick distribution.
    Each game decided by the relative public pick % of the two teams.
    """
    r1_matchups, feeder_games, game_round, game_points = game_tree
    bracket = [None] * 63

    for g in range(63):
        if g < 32:
            team_a, team_b = r1_matchups[g]
        else:
            fa, fb = feeder_games[g]
            team_a = bracket[fa]
            team_b = bracket[fb]

        rd = game_round[g]
        prob_a = get_game_prob(team_a, team_b, public_probs, rd)
        bracket[g] = team_a if random.random() < prob_a else team_b

    return bracket


# =============================================================================
# SCORING
# =============================================================================

def score_bracket(bracket, outcome):
    """Score a bracket against a tournament outcome. Returns integer points."""
    global _cached_game_tree
    if _cached_game_tree is None:
        _cached_game_tree = build_game_tree()
    _, _, _, game_points = _cached_game_tree
    return sum(game_points[g] for g in range(63) if bracket[g] == outcome[g])


def score_bracket_with_tree(bracket, outcome, game_tree):
    """Score a bracket against a tournament outcome (explicit game_tree)."""
    _, _, _, game_points = game_tree
    return sum(game_points[g] for g in range(63) if bracket[g] == outcome[g])


# Module-level cache for game tree (built once)
_cached_game_tree = None

def get_game_tree():
    """Get or build the cached game tree."""
    global _cached_game_tree
    if _cached_game_tree is None:
        _cached_game_tree = build_game_tree()
    return _cached_game_tree


# =============================================================================
# PRECOMPUTATION
# =============================================================================

def precompute_sims(model_probs, public_probs, sigma, M, N, game_tree):
    """
    Pre-simulate M tournament outcomes with N opponent scores each.

    For each simulation:
      1. Perturb model probs → truth
      2. Simulate tournament from truth → outcome
      3. Generate N opponent brackets from public probs, score each
      4. Sort opponent scores descending

    Returns: list of (outcome, sorted_opp_scores)
    """
    results = []
    for m in range(M):
        truth = perturb_probs(model_probs, sigma)
        outcome = simulate_tournament(truth, game_tree)

        opp_scores = []
        for _ in range(N):
            opp = generate_opponent(public_probs, game_tree)
            opp_scores.append(score_bracket_with_tree(opp, outcome, game_tree))
        opp_scores.sort(reverse=True)

        results.append((outcome, opp_scores))

        if (m + 1) % 100 == 0:
            print(f"  Precomputed {m + 1}/{M} simulations")

    return results


def estimate_position(our_score, opp_scores, field_size=250):
    """
    Estimate finishing position via binary search in sorted opponent scores.
    opp_scores: sorted descending.
    """
    lo, hi = 0, len(opp_scores)
    while lo < hi:
        mid = (lo + hi) // 2
        if opp_scores[mid] > our_score:
            lo = mid + 1
        else:
            hi = mid
    beats_us = lo

    if len(opp_scores) > 0:
        pct_beaten_by = beats_us / len(opp_scores)
    else:
        pct_beaten_by = 0

    return max(1, int(pct_beaten_by * field_size) + 1)


# =============================================================================
# OPTIMIZATION PRIMITIVES (shared by bracket_maker and backtest)
# =============================================================================

def build_feeds_into(game_tree):
    """Build static feeds_into map once per game tree."""
    _, feeder_games, _, _ = game_tree
    fi = {}
    for g, (fa, fb) in feeder_games.items():
        fi.setdefault(fa, []).append(g)
        fi.setdefault(fb, []).append(g)
    return fi


def build_locked_games(probs, game_tree, threshold=0.85):
    """Identify R1 games too lopsided to flip (e.g. 1v16)."""
    r1_matchups = game_tree[0]
    locked = set()
    for g in range(32):
        a, b = r1_matchups[g]
        p = get_game_prob(a, b, probs, "R1")
        if p > threshold or p < (1 - threshold):
            locked.add(g)
    return locked


def flip_game(bracket, game_idx, game_tree, probs, feeds_into):
    """
    Flip game_idx to the other team and cascade downstream.
    Uses pre-built feeds_into for speed. Returns new bracket list.
    """
    r1_matchups, feeder_games, game_round, _ = game_tree
    new = list(bracket)

    if game_idx < 32:
        a, b = r1_matchups[game_idx]
    else:
        fa, fb = feeder_games[game_idx]
        a, b = new[fa], new[fb]

    new[game_idx] = b if new[game_idx] == a else a

    # BFS cascade downstream
    queue = list(feeds_into.get(game_idx, []))
    visited = set()
    while queue:
        g = queue.pop(0)
        if g in visited:
            continue
        visited.add(g)
        fa, fb = feeder_games[g]
        ta, tb = new[fa], new[fb]
        if new[g] not in (ta, tb):
            rd = game_round[g]
            p = get_game_prob(ta, tb, probs, rd)
            new[g] = ta if p >= 0.5 else tb
        for ng in feeds_into.get(g, []):
            queue.append(ng)
    return new


def compute_kelly_ev(bracket, precomputed, game_tree, field_size, payout,
                     existing_payouts, wealth_base):
    """
    Marginal Kelly log-wealth contribution of a bracket.
    Returns: (1/M) * sum_m [log(base + existing + new) - log(base + existing)]
    """
    total = 0.0
    _, _, _, game_points = game_tree
    for sim_idx, (outcome, opp_scores) in enumerate(precomputed):
        score = sum(game_points[g] for g in range(63)
                    if bracket[g] == outcome[g])
        pos = estimate_position(score, opp_scores, field_size)
        pv = payout.get(pos, 0)
        ex = existing_payouts[sim_idx]
        total += math.log(wealth_base + ex + pv) - math.log(wealth_base + ex)
    return total / len(precomputed)


def hill_climb(bracket, game_tree, probs, precomputed,
               field_size, payout, existing_payouts, wealth_base,
               feeds_into, locked, shuffle=False):
    """
    Hill-climb: try flipping each unlocked game, keep if Kelly EV improves.
    If shuffle=True, randomize game traversal order (for MC trials).
    """
    current = list(bracket)
    current_ev = compute_kelly_ev(current, precomputed, game_tree,
                                  field_size, payout, existing_payouts,
                                  wealth_base)

    game_order = [g for g in range(63) if g not in locked]

    for _ in range(10):
        if shuffle:
            random.shuffle(game_order)
        improved = False
        for g in game_order:
            flipped = flip_game(current, g, game_tree, probs, feeds_into)
            flipped_ev = compute_kelly_ev(flipped, precomputed, game_tree,
                                         field_size, payout, existing_payouts,
                                         wealth_base)
            if flipped_ev > current_ev:
                current = flipped
                current_ev = flipped_ev
                improved = True
        if not improved:
            break

    return current, current_ev


# =============================================================================
# DISPLAY CONVERSION
# =============================================================================

def bracket_to_display(bracket, game_tree=None):
    """
    Convert flat 63-element bracket to nested dict for display/export.

    Returns: {
        "regions": {region: {"R1": [...], "R2": [...], "S16": [...], "E8": [...]}},
        "F4": [4 teams],
        "F4_winners": [2 teams],
        "champion": str
    }
    """
    display = {"regions": {}}

    # Regional games
    game_idx = 0
    for region in REGIONS:
        rd = {}
        rd["R1"] = list(bracket[game_idx:game_idx + 8])
        game_idx += 8
        display["regions"][region] = rd

    # R2 (games 32-47)
    game_idx = 32
    for region in REGIONS:
        display["regions"][region]["R2"] = list(bracket[game_idx:game_idx + 4])
        game_idx += 4

    # S16 (games 48-55)
    game_idx = 48
    for region in REGIONS:
        display["regions"][region]["S16"] = list(bracket[game_idx:game_idx + 2])
        game_idx += 2

    # E8 (games 56-59)
    game_idx = 56
    for region in REGIONS:
        display["regions"][region]["E8"] = [bracket[game_idx]]
        game_idx += 1

    # F4
    display["F4"] = [bracket[56], bracket[57], bracket[58], bracket[59]]
    display["F4_winners"] = [bracket[60], bracket[61]]
    display["champion"] = bracket[62]

    return display


def print_bracket_summary(bracket):
    """Print a one-line summary of a bracket."""
    d = bracket_to_display(bracket)
    e8s = [d["regions"][r]["E8"][0] for r in REGIONS]
    print(f"  Champ: {d['champion']:<16} FF: {d['F4_winners']}  E8: {e8s}")


if __name__ == "__main__":
    # Quick self-test
    gt = build_game_tree()
    r1_matchups, feeder_games, game_round, game_points = gt
    print(f"R1 matchups: {len(r1_matchups)}")
    print(f"Feeder games: {len(feeder_games)}")
    print(f"Game rounds: {len(game_round)}")
    print(f"Game points: {len(game_points)}")
    print(f"Max possible score: {sum(game_points)}")

    # Test with 2026 data
    data = load_year_data(2026)
    probs = data["model"]
    print(f"\nModel source: {data['sources'].get('model', 'N/A')}")
    print(f"Teams with model probs: {len(probs)}")

    # Initialize cache
    _cached_game_tree = gt

    # Chalk bracket
    chalk = make_chalk_bracket(probs, gt)
    print(f"\nChalk champion: {chalk[62]}")
    print(f"Chalk score vs itself: {score_bracket(chalk, chalk)}")

    # Simulate one tournament
    random.seed(42)
    outcome = simulate_tournament(probs, gt)
    print(f"\nSim champion: {outcome[62]}")
    print(f"Chalk score vs sim: {score_bracket(chalk, outcome)}")

    # Perturbed sim
    truth = perturb_probs(probs, 0.4)
    outcome2 = simulate_tournament(truth, gt)
    print(f"Perturbed sim champion: {outcome2[62]}")

    print("\nOK")
