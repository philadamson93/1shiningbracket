"""Tests for sim_engine.py — game tree, simulation, scoring, optimization."""

import random
import math
import pytest

from sim_engine import (
    build_game_tree, get_game_prob, simulate_tournament,
    score_bracket, score_bracket_with_tree, perturb_probs,
    make_chalk_bracket, generate_opponent, flip_game,
    build_feeds_into, build_locked_games, estimate_position,
    compute_kelly_ev, hill_climb, bracket_to_display, precompute_sims,
    BRACKET, REGIONS, SCORING, ROUND_NAMES,
)
import sim_engine


# ═══════════════════════════════════════════════════════════════════════════════
# BUILD GAME TREE
# ═══════════════════════════════════════════════════════════════════════════════


class TestBuildGameTree:

    def test_32_r1_matchups(self, game_tree):
        r1, _, _, _ = game_tree
        assert len(r1) == 32

    def test_31_feeder_games(self, game_tree):
        _, feeders, _, _ = game_tree
        assert len(feeders) == 31

    def test_63_game_rounds(self, game_tree):
        _, _, rounds, _ = game_tree
        assert len(rounds) == 63

    def test_63_game_points(self, game_tree):
        _, _, _, points = game_tree
        assert len(points) == 63

    def test_max_score_1920(self, game_tree):
        _, _, _, points = game_tree
        assert sum(points) == 1920

    def test_round_label_ordering(self, game_tree):
        _, _, rounds, _ = game_tree
        assert rounds[:32] == ["R1"] * 32
        assert rounds[32:48] == ["R2"] * 16
        assert rounds[48:56] == ["S16"] * 8
        assert rounds[56:60] == ["E8"] * 4
        assert rounds[60:62] == ["F4"] * 2
        assert rounds[62] == "Championship"

    def test_point_values(self, game_tree):
        _, _, _, points = game_tree
        assert all(p == 10 for p in points[:32])
        assert all(p == 20 for p in points[32:48])
        assert all(p == 40 for p in points[48:56])
        assert all(p == 80 for p in points[56:60])
        assert all(p == 160 for p in points[60:62])
        assert points[62] == 320

    def test_all_64_teams_in_r1(self, game_tree, all_bracket_teams):
        r1, _, _, _ = game_tree
        teams_in_r1 = set()
        for a, b in r1:
            teams_in_r1.add(a)
            teams_in_r1.add(b)
        assert teams_in_r1 == all_bracket_teams

    def test_championship_feeds_from_f4(self, game_tree):
        _, feeders, _, _ = game_tree
        assert feeders[62] == (60, 61)


# ═══════════════════════════════════════════════════════════════════════════════
# GET GAME PROB
# ═══════════════════════════════════════════════════════════════════════════════


class TestGetGameProb:

    def test_normalization(self):
        probs = {"A": {"R1": 0.8}, "B": {"R1": 0.2}}
        assert get_game_prob("A", "B", probs, "R1") == pytest.approx(0.8)

    def test_equal_teams(self):
        probs = {"A": {"R1": 0.5}, "B": {"R1": 0.5}}
        assert get_game_prob("A", "B", probs, "R1") == pytest.approx(0.5)

    def test_missing_team_uses_default(self):
        probs = {"A": {"R1": 0.8}}
        # B missing → 0.001 default
        result = get_game_prob("A", "B", probs, "R1")
        assert result == pytest.approx(0.8 / (0.8 + 0.001), rel=1e-3)

    def test_both_missing_returns_half(self):
        probs = {}
        # Both get 0.001 → 0.5
        assert get_game_prob("X", "Y", probs, "R1") == pytest.approx(0.5)

    def test_result_between_0_and_1(self, sample_probs, game_tree):
        r1, _, _, _ = game_tree
        for a, b in r1:
            p = get_game_prob(a, b, sample_probs, "R1")
            assert 0 < p < 1


# ═══════════════════════════════════════════════════════════════════════════════
# SIMULATE TOURNAMENT
# ═══════════════════════════════════════════════════════════════════════════════


class TestSimulateTournament:

    def test_deterministic_with_seed(self, sample_probs, game_tree):
        random.seed(123)
        o1 = simulate_tournament(sample_probs, game_tree)
        random.seed(123)
        o2 = simulate_tournament(sample_probs, game_tree)
        assert o1 == o2

    def test_all_63_filled(self, sample_outcome):
        assert len(sample_outcome) == 63
        assert all(t is not None for t in sample_outcome)

    def test_all_winners_valid_teams(self, sample_outcome, all_bracket_teams):
        for t in sample_outcome:
            assert t in all_bracket_teams, f"Unknown team in outcome: {t}"

    def test_different_seeds_differ(self, sample_probs, game_tree):
        random.seed(42)
        o1 = simulate_tournament(sample_probs, game_tree)
        random.seed(99)
        o2 = simulate_tournament(sample_probs, game_tree)
        assert o1 != o2

    def test_champion_is_last(self, sample_outcome):
        assert sample_outcome[62] is not None


# ═══════════════════════════════════════════════════════════════════════════════
# SCORE BRACKET
# ═══════════════════════════════════════════════════════════════════════════════


class TestScoreBracket:

    def test_perfect_bracket_1920(self, sample_outcome, game_tree):
        assert score_bracket_with_tree(sample_outcome, sample_outcome, game_tree) == 1920

    def test_all_wrong_scores_zero(self, sample_outcome, game_tree):
        wrong = ["ZZZZZ"] * 63
        assert score_bracket_with_tree(wrong, sample_outcome, game_tree) == 0

    def test_partial_scoring(self, sample_outcome, game_tree):
        # Copy outcome but change only the champion
        partial = list(sample_outcome)
        partial[62] = "ZZZZZ"
        score = score_bracket_with_tree(partial, sample_outcome, game_tree)
        assert score == 1920 - 320  # lost only the championship points

    def test_score_bracket_equivalence(self, chalk_bracket, sample_outcome, game_tree):
        s1 = score_bracket(chalk_bracket, sample_outcome)
        s2 = score_bracket_with_tree(chalk_bracket, sample_outcome, game_tree)
        assert s1 == s2

    def test_score_bracket_auto_inits_cache(self, chalk_bracket, sample_outcome, game_tree):
        """score_bracket should auto-initialize the cache if None."""
        saved = sim_engine._cached_game_tree
        try:
            sim_engine._cached_game_tree = None
            score = score_bracket(chalk_bracket, sample_outcome)
            expected = score_bracket_with_tree(chalk_bracket, sample_outcome, game_tree)
            assert score == expected
        finally:
            sim_engine._cached_game_tree = saved


# ═══════════════════════════════════════════════════════════════════════════════
# PERTURB PROBS
# ═══════════════════════════════════════════════════════════════════════════════


class TestPerturbProbs:

    def test_output_in_0_1(self, sample_probs):
        random.seed(42)
        perturbed = perturb_probs(sample_probs, 0.5)
        for team, rounds in perturbed.items():
            for rd, p in rounds.items():
                assert 0 < p < 1, f"{team} {rd} = {p}"

    def test_different_from_input_when_sigma_positive(self, sample_probs):
        random.seed(42)
        perturbed = perturb_probs(sample_probs, 0.5)
        diffs = 0
        for team in sample_probs:
            for rd in sample_probs[team]:
                if abs(perturbed[team][rd] - sample_probs[team][rd]) > 1e-6:
                    diffs += 1
        assert diffs > 0

    def test_same_when_sigma_zero(self, sample_probs):
        perturbed = perturb_probs(sample_probs, 0.0)
        for team in sample_probs:
            for rd in sample_probs[team]:
                orig = sample_probs[team][rd]
                # perturb_probs clamps to [0.001, 0.999] before logit transform,
                # so very small/large values get shifted to the clamp boundary
                clamped = max(0.001, min(0.999, orig))
                assert perturbed[team][rd] == pytest.approx(clamped, abs=1e-6)

    def test_preserves_team_structure(self, sample_probs):
        random.seed(42)
        perturbed = perturb_probs(sample_probs, 0.3)
        assert set(perturbed.keys()) == set(sample_probs.keys())
        for team in sample_probs:
            assert set(perturbed[team].keys()) == set(sample_probs[team].keys())

    def test_deterministic_with_seed(self, sample_probs):
        random.seed(42)
        p1 = perturb_probs(sample_probs, 0.3)
        random.seed(42)
        p2 = perturb_probs(sample_probs, 0.3)
        for team in p1:
            for rd in p1[team]:
                assert p1[team][rd] == p2[team][rd]


# ═══════════════════════════════════════════════════════════════════════════════
# MAKE CHALK BRACKET
# ═══════════════════════════════════════════════════════════════════════════════


class TestMakeChalkBracket:

    def test_all_63_filled(self, chalk_bracket):
        assert len(chalk_bracket) == 63
        assert all(t is not None for t in chalk_bracket)

    def test_deterministic(self, sample_probs, game_tree):
        c1 = make_chalk_bracket(sample_probs, game_tree)
        c2 = make_chalk_bracket(sample_probs, game_tree)
        assert c1 == c2

    def test_picks_favorites_in_r1(self, sample_probs, game_tree):
        r1, _, _, _ = game_tree
        chalk = make_chalk_bracket(sample_probs, game_tree)
        for g in range(32):
            a, b = r1[g]
            pa = sample_probs[a]["R1"]
            pb = sample_probs[b]["R1"]
            if pa > pb:
                assert chalk[g] == a
            elif pb > pa:
                assert chalk[g] == b

    def test_champion_at_index_62(self, chalk_bracket):
        assert chalk_bracket[62] is not None


# ═══════════════════════════════════════════════════════════════════════════════
# GENERATE OPPONENT
# ═══════════════════════════════════════════════════════════════════════════════


class TestGenerateOpponent:

    def test_all_63_filled(self, sample_probs, game_tree):
        random.seed(42)
        opp = generate_opponent(sample_probs, game_tree)
        assert len(opp) == 63
        assert all(t is not None for t in opp)

    def test_stochastic(self, sample_probs, game_tree):
        random.seed(42)
        o1 = generate_opponent(sample_probs, game_tree)
        random.seed(99)
        o2 = generate_opponent(sample_probs, game_tree)
        assert o1 != o2

    def test_uses_given_probs(self, game_tree):
        """Heavy favorite probs → opponent almost always picks favorite."""
        heavy = {}
        for region, teams in BRACKET.items():
            for team, seed in teams:
                if seed <= 2:
                    heavy[team] = {rd: 0.999 for rd in ROUND_NAMES}
                else:
                    heavy[team] = {rd: 0.001 for rd in ROUND_NAMES}
        random.seed(42)
        opp = generate_opponent(heavy, game_tree)
        # All R1 winners should be seeds 1 or 2 (with 0.999 prob)
        r1, _, _, _ = game_tree
        for g in range(32):
            a, b = r1[g]
            seed_a = next(s for r in BRACKET.values() for t, s in r if t == a)
            seed_b = next(s for r in BRACKET.values() for t, s in r if t == b)
            winner_seed = next(s for r in BRACKET.values() for t, s in r if t == opp[g])
            # The team with seed ≤ 2 should nearly always win
            if seed_a <= 2 or seed_b <= 2:
                assert winner_seed <= 2


# ═══════════════════════════════════════════════════════════════════════════════
# FLIP GAME
# ═══════════════════════════════════════════════════════════════════════════════


class TestFlipGame:

    def test_flips_r1_game(self, chalk_bracket, game_tree, sample_probs, feeds_into):
        r1, _, _, _ = game_tree
        a, b = r1[0]
        original_winner = chalk_bracket[0]
        flipped = flip_game(chalk_bracket, 0, game_tree, sample_probs, feeds_into)
        expected = b if original_winner == a else a
        assert flipped[0] == expected

    def test_cascade_downstream(self, chalk_bracket, game_tree, sample_probs, feeds_into):
        flipped = flip_game(chalk_bracket, 0, game_tree, sample_probs, feeds_into)
        # At least the flipped game itself should differ
        assert flipped[0] != chalk_bracket[0]
        # If the R1 winner was in downstream games, those should update
        diffs = sum(1 for i in range(63) if flipped[i] != chalk_bracket[i])
        assert diffs >= 1

    def test_bracket_consistency(self, chalk_bracket, game_tree, sample_probs, feeds_into):
        """After flip, every non-R1 winner must be one of its feeder winners."""
        _, feeders, _, _ = game_tree
        flipped = flip_game(chalk_bracket, 0, game_tree, sample_probs, feeds_into)
        for g in range(32, 63):
            fa, fb = feeders[g]
            assert flipped[g] in (flipped[fa], flipped[fb]), \
                f"Game {g}: winner {flipped[g]} not in feeders ({flipped[fa]}, {flipped[fb]})"

    def test_no_cross_region_leakage(self, chalk_bracket, game_tree, sample_probs, feeds_into):
        """Flipping game 0 (East R1) should not affect Midwest games (24-31)."""
        flipped = flip_game(chalk_bracket, 0, game_tree, sample_probs, feeds_into)
        # Games 24-31 are Midwest R1, games 44-47 are Midwest R2, etc.
        for g in range(24, 32):
            assert flipped[g] == chalk_bracket[g]


# ═══════════════════════════════════════════════════════════════════════════════
# BUILD FEEDS INTO
# ═══════════════════════════════════════════════════════════════════════════════


class TestBuildFeedsInto:

    def test_r1_games_feed_r2(self, feeds_into):
        for g in range(32):
            assert g in feeds_into, f"R1 game {g} has no downstream"
            for downstream in feeds_into[g]:
                assert 32 <= downstream <= 47

    def test_game_62_no_downstream(self, feeds_into):
        assert 62 not in feeds_into

    def test_all_non_r1_games_fed(self, game_tree, feeds_into):
        _, feeders, _, _ = game_tree
        # Every game 32-62 should appear as a downstream of some feeder
        all_downstream = set()
        for targets in feeds_into.values():
            all_downstream.update(targets)
        for g in range(32, 63):
            assert g in all_downstream


# ═══════════════════════════════════════════════════════════════════════════════
# BUILD LOCKED GAMES
# ═══════════════════════════════════════════════════════════════════════════════


class TestBuildLockedGames:

    def test_lopsided_locked(self, sample_probs, game_tree):
        locked = build_locked_games(sample_probs, game_tree, threshold=0.85)
        # 1-vs-16 matchups: seed 1 has R1=0.97 >> 16's 0.03 → prob > 0.97
        assert 0 in locked  # First game is a 1-vs-16

    def test_close_matchups_unlocked(self, sample_probs, game_tree):
        locked = build_locked_games(sample_probs, game_tree, threshold=0.85)
        # 8-vs-9: both have R1 ~ 0.50 → prob ≈ 0.52 → not locked
        # Game index for 8v9 in East is game 1 (teams[2],teams[3])
        r1, _, _, _ = game_tree
        for g in range(32):
            a, b = r1[g]
            sa = next(s for r in BRACKET.values() for t, s in r if t == a)
            sb = next(s for r in BRACKET.values() for t, s in r if t == b)
            if {sa, sb} == {8, 9}:
                assert g not in locked, f"8-vs-9 game {g} should not be locked"

    def test_returns_set_of_ints(self, sample_probs, game_tree):
        locked = build_locked_games(sample_probs, game_tree)
        assert isinstance(locked, set)
        for g in locked:
            assert isinstance(g, int)
            assert 0 <= g < 32


# ═══════════════════════════════════════════════════════════════════════════════
# ESTIMATE POSITION
# ═══════════════════════════════════════════════════════════════════════════════


class TestEstimatePosition:

    def test_beats_all(self):
        assert estimate_position(2000, [100, 50, 25], field_size=100) == 1

    def test_beats_none(self):
        pos = estimate_position(0, [1000, 500, 250], field_size=100)
        # max(1, int(1.0 * 100) + 1) = 101 — capped to field_size+1
        # because all 3 opponents beat us: pct_beaten_by = 3/3 = 1.0
        assert pos == 101

    def test_middle(self):
        opp = list(range(100, 0, -1))  # [100, 99, ..., 1]
        pos = estimate_position(50, opp, field_size=100)
        assert 40 <= pos <= 60

    def test_empty_opponents(self):
        assert estimate_position(100, [], field_size=250) == 1


# ═══════════════════════════════════════════════════════════════════════════════
# COMPUTE KELLY EV
# ═══════════════════════════════════════════════════════════════════════════════


class TestComputeKellyEv:

    def test_returns_float(self, chalk_bracket, small_precomputed, game_tree):
        payout = {1: 1.0}
        existing = [0.0] * len(small_precomputed)
        ev = compute_kelly_ev(chalk_bracket, small_precomputed, game_tree,
                              250, payout, existing, 1.0)
        assert isinstance(ev, float)

    def test_deterministic(self, chalk_bracket, small_precomputed, game_tree):
        payout = {1: 1.0}
        existing = [0.0] * len(small_precomputed)
        ev1 = compute_kelly_ev(chalk_bracket, small_precomputed, game_tree,
                               250, payout, existing, 1.0)
        ev2 = compute_kelly_ev(chalk_bracket, small_precomputed, game_tree,
                               250, payout, existing, 1.0)
        assert ev1 == ev2

    def test_nonzero_ev(self, chalk_bracket, small_precomputed, game_tree):
        payout = {1: 0.60, 2: 0.20, 3: 0.10, 4: 0.05, 5: 0.03, 6: 0.02}
        existing = [0.0] * len(small_precomputed)
        ev = compute_kelly_ev(chalk_bracket, small_precomputed, game_tree,
                              10, payout, existing, 1.0)
        # With field_size=10 and generous payout, a reasonable bracket should have positive EV
        assert ev != 0.0


# ═══════════════════════════════════════════════════════════════════════════════
# HILL CLIMB
# ═══════════════════════════════════════════════════════════════════════════════


class TestHillClimb:

    def test_output_ev_geq_input(self, sample_probs, game_tree,
                                  small_precomputed, feeds_into):
        chalk = make_chalk_bracket(sample_probs, game_tree)
        locked = build_locked_games(sample_probs, game_tree)
        payout = {1: 0.60, 2: 0.20, 3: 0.10}
        existing = [0.0] * len(small_precomputed)

        initial_ev = compute_kelly_ev(chalk, small_precomputed, game_tree,
                                       50, payout, existing, 1.0)
        result, result_ev = hill_climb(
            chalk, game_tree, sample_probs, small_precomputed,
            50, payout, existing, 1.0, feeds_into, locked)
        assert result_ev >= initial_ev

    def test_returns_valid_bracket(self, sample_probs, game_tree,
                                    small_precomputed, feeds_into,
                                    all_bracket_teams):
        chalk = make_chalk_bracket(sample_probs, game_tree)
        locked = build_locked_games(sample_probs, game_tree)
        payout = {1: 1.0}
        existing = [0.0] * len(small_precomputed)
        result, _ = hill_climb(
            chalk, game_tree, sample_probs, small_precomputed,
            50, payout, existing, 1.0, feeds_into, locked)
        assert len(result) == 63
        assert all(t in all_bracket_teams for t in result)

    def test_locked_games_unchanged(self, sample_probs, game_tree,
                                     small_precomputed, feeds_into):
        chalk = make_chalk_bracket(sample_probs, game_tree)
        locked = build_locked_games(sample_probs, game_tree)
        payout = {1: 1.0}
        existing = [0.0] * len(small_precomputed)
        result, _ = hill_climb(
            chalk, game_tree, sample_probs, small_precomputed,
            50, payout, existing, 1.0, feeds_into, locked)
        for g in locked:
            assert result[g] == chalk[g], f"Locked game {g} was changed"


# ═══════════════════════════════════════════════════════════════════════════════
# BRACKET TO DISPLAY
# ═══════════════════════════════════════════════════════════════════════════════


class TestBracketToDisplay:

    def test_champion_matches(self, chalk_bracket):
        d = bracket_to_display(chalk_bracket)
        assert d["champion"] == chalk_bracket[62]

    def test_four_regions(self, chalk_bracket):
        d = bracket_to_display(chalk_bracket)
        assert set(d["regions"].keys()) == set(REGIONS)

    def test_r1_has_8_per_region(self, chalk_bracket):
        d = bracket_to_display(chalk_bracket)
        for region in REGIONS:
            assert len(d["regions"][region]["R1"]) == 8

    def test_f4_has_4_teams(self, chalk_bracket):
        d = bracket_to_display(chalk_bracket)
        assert len(d["F4"]) == 4

    def test_f4_winners_has_2(self, chalk_bracket):
        d = bracket_to_display(chalk_bracket)
        assert len(d["F4_winners"]) == 2
