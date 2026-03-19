"""Tests for scrape_dk_odds.py — odds conversion, vig removal, monotonicity."""

import pytest

from scrape_dk_odds import (
    american_to_implied, remove_vig_group, ensure_monotonic,
    compute_team_probabilities, normalize_championship_probs,
    normalize_ff_probs_by_region, TEAMS,
)


# ═══════════════════════════════════════════════════════════════════════════════
# AMERICAN TO IMPLIED
# ═══════════════════════════════════════════════════════════════════════════════


class TestAmericanToImplied:

    def test_positive_odds(self):
        # +200 → 100 / (200+100) = 1/3
        assert american_to_implied(200) == pytest.approx(1 / 3, rel=1e-4)

    def test_negative_odds(self):
        # -200 → 200 / (200+100) = 2/3
        assert american_to_implied(-200) == pytest.approx(2 / 3, rel=1e-4)

    def test_heavy_favorite(self):
        result = american_to_implied(-10000)
        assert result > 0.98

    def test_heavy_underdog(self):
        result = american_to_implied(10000)
        assert result < 0.02

    def test_even_money_positive(self):
        assert american_to_implied(100) == pytest.approx(0.5)

    def test_even_money_negative(self):
        assert american_to_implied(-100) == pytest.approx(0.5)


# ═══════════════════════════════════════════════════════════════════════════════
# REMOVE VIG GROUP
# ═══════════════════════════════════════════════════════════════════════════════


class TestRemoveVigGroup:

    def test_sums_to_one(self):
        result = remove_vig_group([0.55, 0.55])
        assert sum(result) == pytest.approx(1.0)

    def test_preserves_ratios(self):
        result = remove_vig_group([0.6, 0.3])
        assert result[0] / result[1] == pytest.approx(2.0, rel=1e-4)

    def test_all_zeros(self):
        result = remove_vig_group([0, 0, 0])
        assert result == [0, 0, 0]

    def test_single_element(self):
        result = remove_vig_group([0.7])
        assert result == [pytest.approx(1.0)]


# ═══════════════════════════════════════════════════════════════════════════════
# ENSURE MONOTONIC
# ═══════════════════════════════════════════════════════════════════════════════


class TestEnsureMonotonic:

    def test_already_monotonic_unchanged(self):
        rows = [{"R1_implied": 0.95, "S16_implied": 0.80, "E8_implied": 0.50,
                 "F4_implied": 0.30, "championship_implied": 0.10}]
        result = ensure_monotonic(rows)
        assert result[0]["S16_implied"] == 0.80
        assert result[0]["championship_implied"] == 0.10

    def test_fixes_non_monotonic(self):
        rows = [{"R1_implied": 0.80, "S16_implied": 0.90,  # wrong!
                 "E8_implied": 0.50, "F4_implied": 0.30,
                 "championship_implied": 0.10}]
        result = ensure_monotonic(rows)
        assert result[0]["S16_implied"] == 0.80  # capped to R1

    def test_cascading_fix(self):
        rows = [{"R1_implied": 0.50, "S16_implied": 0.60, "E8_implied": 0.70,
                 "F4_implied": 0.80, "championship_implied": 0.90}]
        result = ensure_monotonic(rows)
        assert result[0]["S16_implied"] == 0.50
        assert result[0]["E8_implied"] == 0.50
        assert result[0]["F4_implied"] == 0.50
        assert result[0]["championship_implied"] == 0.50


# ═══════════════════════════════════════════════════════════════════════════════
# COMPUTE TEAM PROBABILITIES
# ═══════════════════════════════════════════════════════════════════════════════


class TestComputeTeamProbabilities:

    def test_returns_expected_keys(self):
        result = compute_team_probabilities("Duke", TEAMS["Duke"])
        expected_keys = {"team", "seed", "region", "R1_implied", "S16_implied",
                         "E8_implied", "F4_implied", "championship_implied"}
        assert set(result.keys()) == expected_keys

    def test_duke_probabilities_reasonable(self):
        result = compute_team_probabilities("Duke", TEAMS["Duke"])
        assert result["R1_implied"] > 0.95  # 1-seed heavy favorite
        assert result["championship_implied"] > 0.05


# ═══════════════════════════════════════════════════════════════════════════════
# NORMALIZATION FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════════


class TestNormalization:

    def _make_rows(self):
        rows = []
        for team_name, data in TEAMS.items():
            rows.append(compute_team_probabilities(team_name, data))
        return rows

    def test_championship_sums_to_one(self):
        rows = self._make_rows()
        rows = normalize_championship_probs(rows)
        total = sum(r["championship_implied"] for r in rows)
        assert total == pytest.approx(1.0, abs=0.01)

    def test_ff_sums_to_one_per_region(self):
        rows = self._make_rows()
        rows = normalize_ff_probs_by_region(rows)
        for region in ["East", "West", "South", "Midwest"]:
            region_rows = [r for r in rows if r["region"] == region]
            total = sum(r["F4_implied"] for r in region_rows)
            assert total == pytest.approx(1.0, abs=0.01), \
                f"{region} FF sum = {total}"
