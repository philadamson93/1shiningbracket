"""Integration tests — cross-source alignment, end-to-end with real data."""

import random
import pytest

from data_loader import (
    load_year_data, load_538_probs, load_pop_picks, _load_paine_csv,
    STANDARD_ROUNDS,
)
from sim_engine import (
    build_game_tree, make_chalk_bracket, simulate_tournament,
    score_bracket_with_tree, blend_probs, precompute_sims,
    build_feeds_into, build_locked_games, hill_climb, compute_kelly_ev,
    BRACKET, ROUND_NAMES,
)


# ═══════════════════════════════════════════════════════════════════════════════
# CROSS-SOURCE ALIGNMENT
# ═══════════════════════════════════════════════════════════════════════════════


class TestCrossSourceAlignment:

    def test_all_64_teams_in_blended_probs(self, blended_probs, all_bracket_teams):
        missing = all_bracket_teams - set(blended_probs.keys())
        assert len(missing) == 0, f"Teams missing from blended probs: {sorted(missing)}"

    def test_all_rounds_present(self, blended_probs, all_bracket_teams):
        for team in all_bracket_teams:
            if team not in blended_probs:
                continue
            rounds = set(blended_probs[team].keys())
            missing_rounds = set(STANDARD_ROUNDS) - rounds
            assert len(missing_rounds) == 0, \
                f"{team} missing rounds: {missing_rounds}"

    def test_probabilities_in_0_1(self, blended_probs):
        for team, rounds in blended_probs.items():
            for rd, val in rounds.items():
                assert 0 < val < 1, f"{team} {rd} = {val}"

    def test_probabilities_generally_decreasing(self, blended_probs, all_bracket_teams):
        """R1 >= R2 >= S16 >= E8 >= F4 >= Championship for most teams."""
        violations = 0
        for team in all_bracket_teams:
            if team not in blended_probs:
                continue
            probs = blended_probs[team]
            prev = 1.0
            for rd in STANDARD_ROUNDS:
                val = probs.get(rd, 0)
                if val > prev + 0.05:  # allow small tolerance
                    violations += 1
                prev = val
        # Allow a few violations (R2 interpolation can slightly exceed R1)
        assert violations < 20, f"{violations} monotonicity violations"


# ═══════════════════════════════════════════════════════════════════════════════
# LOAD YEAR DATA
# ═══════════════════════════════════════════════════════════════════════════════


class TestLoadYearData:

    def test_2026_has_model(self, real_2026_data):
        assert len(real_2026_data["model"]) > 0

    def test_2026_has_market(self, real_2026_data):
        assert len(real_2026_data["market"]) > 0

    def test_2026_has_public(self, real_2026_data):
        assert len(real_2026_data["public"]) > 0

    def test_2018_has_model_from_538(self):
        data = load_year_data(2018)
        assert "538" in data["sources"].get("model", "")

    def test_sources_dict_present(self, real_2026_data):
        assert "sources" in real_2026_data
        assert "model" in real_2026_data["sources"]


# ═══════════════════════════════════════════════════════════════════════════════
# END-TO-END
# ═══════════════════════════════════════════════════════════════════════════════


class TestEndToEnd:

    def test_chalk_from_real_data(self, blended_probs, game_tree, all_bracket_teams):
        chalk = make_chalk_bracket(blended_probs, game_tree)
        assert len(chalk) == 63
        assert all(t is not None for t in chalk)
        assert all(t in all_bracket_teams for t in chalk)
        # Champion should be a top seed
        champ = chalk[62]
        seed = next(s for r in BRACKET.values() for t, s in r if t == champ)
        assert seed <= 4, f"Chalk champion {champ} is seed {seed}"

    def test_simulate_and_score(self, blended_probs, game_tree):
        random.seed(42)
        outcome = simulate_tournament(blended_probs, game_tree)
        chalk = make_chalk_bracket(blended_probs, game_tree)
        score = score_bracket_with_tree(chalk, outcome, game_tree)
        assert 0 <= score <= 1920

    def test_precompute_and_hill_climb(self, blended_probs, game_tree):
        random.seed(42)
        precomputed = precompute_sims(blended_probs, blended_probs,
                                       0.3, 5, 10, game_tree)
        chalk = make_chalk_bracket(blended_probs, game_tree)
        feeds_into = build_feeds_into(game_tree)
        locked = build_locked_games(blended_probs, game_tree)
        payout = {1: 0.60, 2: 0.20, 3: 0.10}
        existing = [0.0] * len(precomputed)

        chalk_ev = compute_kelly_ev(chalk, precomputed, game_tree,
                                     50, payout, existing, 1.0)
        result, result_ev = hill_climb(
            chalk, game_tree, blended_probs, precomputed,
            50, payout, existing, 1.0, feeds_into, locked)
        assert result_ev >= chalk_ev
        assert len(result) == 63


# ═══════════════════════════════════════════════════════════════════════════════
# HISTORICAL DATA LOADING
# ═══════════════════════════════════════════════════════════════════════════════


class TestHistoricalDataLoading:

    def test_538_2018_loads(self):
        data = load_538_probs(2018)
        assert len(data) > 50

    def test_pop_2023_loads(self):
        data = load_pop_picks(2023)
        assert len(data) > 0

    def test_paine_2026_loads(self):
        data = _load_paine_csv("data/historical/pred.paine.men.2026.csv")
        assert len(data) > 60
        # Check F4 is interpolated
        for team, rounds in data.items():
            e8 = rounds.get("E8", 0)
            champ = rounds.get("Championship", 0)
            # F4 is interpolated only when E8 > 0
            if e8 > 0:
                assert "F4" in rounds, f"{team} missing F4 interpolation"
