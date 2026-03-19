"""Tests for data_loader.py — name normalization, CSV loaders, blend, leverage."""

import csv
import math
import os
import pytest

from data_loader import (
    normalize_team_name, _load_wide_csv, _load_paine_csv,
    load_dk_odds, load_espn_api_picks, load_year_data,
    ROUND_MAP, STANDARD_ROUNDS, TEAM_ALIASES,
)
from sim_engine import blend_probs, BRACKET
from data_loader import compute_leverage


# ═══════════════════════════════════════════════════════════════════════════════
# NORMALIZE TEAM NAME
# ═══════════════════════════════════════════════════════════════════════════════


class TestNormalizeTeamName:

    def test_exact_match_canonical(self):
        assert normalize_team_name("Duke") == "Duke"

    def test_exact_match_alias(self):
        assert normalize_team_name("Connecticut") == "UConn"

    def test_case_insensitive_lower(self):
        assert normalize_team_name("duke") == "Duke"

    def test_case_insensitive_upper(self):
        assert normalize_team_name("DUKE") == "Duke"

    def test_unknown_returns_as_is(self):
        assert normalize_team_name("Completely Unknown") == "Completely Unknown"

    def test_michigan_state_alias(self):
        assert normalize_team_name("Michigan St.") == "Michigan State"

    def test_iowa_state_alias(self):
        assert normalize_team_name("Iowa St.") == "Iowa State"

    def test_full_name_alias(self):
        assert normalize_team_name("Iowa State Cyclones") == "Iowa State"

    def test_all_bracket_teams_normalize_to_self(self, all_bracket_teams):
        """Every team in the bracket should be its own canonical name."""
        failures = []
        for team in sorted(all_bracket_teams):
            result = normalize_team_name(team)
            if result != team:
                failures.append(f"{team} → {result}")
        assert not failures, f"Bracket teams that don't normalize to self:\n" + "\n".join(failures)

    def test_prefix_north_carolina_wilmington(self):
        result = normalize_team_name("North Carolina Wilmington Panthers")
        assert result == "North Carolina-Wilmington"

    def test_smu_all_aliases(self):
        for name in ["SMU", "Southern Methodist", "MOH/SMU", "M-OH/SMU", "SMU Mustangs"]:
            assert normalize_team_name(name) == "SMU", f"{name} → {normalize_team_name(name)}"

    def test_north_dakota_st_period(self):
        assert normalize_team_name("North Dakota St.") == "North Dakota St"

    def test_texas_tx_ncst(self):
        assert normalize_team_name("TX/NCST") == "Texas"


# ═══════════════════════════════════════════════════════════════════════════════
# _LOAD_WIDE_CSV
# ═══════════════════════════════════════════════════════════════════════════════


class TestLoadWideCsv:

    def test_round_name_mapping(self, tmp_path):
        f = tmp_path / "test.csv"
        f.write_text("name,round1,round2,round3,round4,round5,round6\n"
                      "Duke,0.97,0.85,0.70,0.50,0.30,0.12\n")
        data = _load_wide_csv(str(f))
        assert "Duke" in data
        assert set(data["Duke"].keys()) == {"R1", "R2", "S16", "E8", "F4", "Championship"}
        assert data["Duke"]["R1"] == pytest.approx(0.97)

    def test_percentage_conversion(self, tmp_path):
        f = tmp_path / "test.csv"
        f.write_text("name,round1\nDuke,55.0\n")
        data = _load_wide_csv(str(f))
        assert data["Duke"]["R1"] == pytest.approx(0.55)

    def test_missing_file_returns_empty(self):
        assert _load_wide_csv("/nonexistent/path.csv") == {}

    def test_team_names_normalized(self, tmp_path):
        f = tmp_path / "test.csv"
        f.write_text("name,round1\nConnecticut,0.50\n")
        data = _load_wide_csv(str(f))
        assert "UConn" in data


# ═══════════════════════════════════════════════════════════════════════════════
# _LOAD_PAINE_CSV
# ═══════════════════════════════════════════════════════════════════════════════


class TestLoadPaineCsv:

    def test_shifted_round_mapping(self, tmp_path):
        f = tmp_path / "paine.csv"
        f.write_text("name,round1,round2,round3,round4,round5,round6\n"
                      "Duke,1.0,0.99,0.87,0.72,0.55,0.24\n")
        data = _load_paine_csv(str(f))
        assert "Duke" in data
        # round2 → R1, round3 → R2, etc.
        assert data["Duke"]["R1"] == pytest.approx(0.99)
        assert data["Duke"]["R2"] == pytest.approx(0.87)
        assert data["Duke"]["S16"] == pytest.approx(0.72)
        assert data["Duke"]["E8"] == pytest.approx(0.55)
        assert data["Duke"]["Championship"] == pytest.approx(0.24)

    def test_f4_interpolation(self, tmp_path):
        f = tmp_path / "paine.csv"
        f.write_text("name,round1,round2,round3,round4,round5,round6\n"
                      "Test,1.0,0.99,0.80,0.60,0.36,0.04\n")
        data = _load_paine_csv(str(f))
        # F4 = sqrt(E8 * Championship) = sqrt(0.36 * 0.04) = sqrt(0.0144) ≈ 0.12
        expected = math.sqrt(0.36 * 0.04)
        assert data["Test"]["F4"] == pytest.approx(expected, abs=1e-4)

    def test_f4_fallback_no_championship(self, tmp_path):
        f = tmp_path / "paine.csv"
        # round6 (championship) is 0 → F4 = E8 * 0.5
        f.write_text("name,round1,round2,round3,round4,round5,round6\n"
                      "Test,1.0,0.90,0.70,0.50,0.36,0.0\n")
        data = _load_paine_csv(str(f))
        assert data["Test"]["F4"] == pytest.approx(0.36 * 0.5)

    def test_percentage_values_converted(self, tmp_path):
        f = tmp_path / "paine.csv"
        f.write_text("name,round1,round2,round3,round4,round5,round6\n"
                      "Test,100,99,87,72,55,24\n")
        data = _load_paine_csv(str(f))
        assert data["Test"]["R1"] == pytest.approx(0.99)


# ═══════════════════════════════════════════════════════════════════════════════
# LOAD DK ODDS
# ═══════════════════════════════════════════════════════════════════════════════


class TestLoadDkOdds:

    def test_loads_real_file(self):
        data = load_dk_odds("data/dk_implied_odds.csv")
        assert len(data) >= 60  # ~64 teams

    def test_round_map_columns(self):
        data = load_dk_odds("data/dk_implied_odds.csv")
        for team, rounds in data.items():
            for rd in rounds:
                assert rd in STANDARD_ROUNDS, f"{team}: unexpected round {rd}"

    def test_missing_file_returns_empty(self):
        assert load_dk_odds("nonexistent.csv") == {}


# ═══════════════════════════════════════════════════════════════════════════════
# LOAD ESPN API PICKS
# ═══════════════════════════════════════════════════════════════════════════════


class TestLoadEspnApiPicks:

    def test_loads_2026(self):
        data = load_espn_api_picks(2026)
        assert len(data) > 0

    def test_values_are_decimals(self):
        data = load_espn_api_picks(2026)
        for team, rounds in data.items():
            for rd, val in rounds.items():
                assert 0 <= val <= 1.0, f"{team} {rd} = {val} (not decimal)"

    def test_missing_year_returns_empty(self):
        assert load_espn_api_picks(1999) == {}


# ═══════════════════════════════════════════════════════════════════════════════
# BLEND PROBS
# ═══════════════════════════════════════════════════════════════════════════════


class TestBlendProbs:

    def test_both_sources_weighted(self):
        model = {"A": {"R1": 0.6}}
        market = {"A": {"R1": 0.4}}
        blended = blend_probs(model, market, model_weight=0.5)
        assert blended["A"]["R1"] == pytest.approx(0.5)

    def test_model_only_fallback(self):
        model = {"A": {"R1": 0.7}}
        market = {}
        blended = blend_probs(model, market, model_weight=0.5)
        assert blended["A"]["R1"] == pytest.approx(0.7)

    def test_market_only_fallback(self):
        model = {}
        market = {"A": {"R1": 0.4}}
        blended = blend_probs(model, market, model_weight=0.5)
        assert blended["A"]["R1"] == pytest.approx(0.4)

    def test_r2_interpolation(self):
        model = {}
        market = {"A": {"R1": 0.81, "S16": 0.36}}
        blended = blend_probs(model, market, model_weight=0.5)
        # R2 interpolated as sqrt(R1 * S16)
        expected = math.sqrt(0.81 * 0.36)
        assert blended["A"]["R2"] == pytest.approx(expected, abs=1e-4)

    def test_union_of_teams(self):
        model = {"A": {"R1": 0.8}, "B": {"R1": 0.6}}
        market = {"B": {"R1": 0.5}, "C": {"R1": 0.3}}
        blended = blend_probs(model, market, model_weight=0.5)
        assert set(blended.keys()) == {"A", "B", "C"}


# ═══════════════════════════════════════════════════════════════════════════════
# COMPUTE LEVERAGE
# ═══════════════════════════════════════════════════════════════════════════════


class TestComputeLeverage:

    def test_basic_leverage(self):
        result = compute_leverage(0.2, 0.2, 0.1, model_weight=0.5)
        assert result["true_prob"] == pytest.approx(0.2)
        assert result["leverage"] == pytest.approx(2.0)

    def test_zero_public_pick_floor(self):
        result = compute_leverage(0.2, 0.2, 0.0, model_weight=0.5)
        # Floored to 0.001
        assert result["leverage"] == pytest.approx(0.2 / 0.001)

    def test_model_only(self):
        result = compute_leverage(0.3, 0, 0.1, model_weight=0.5)
        assert result["true_prob"] == pytest.approx(0.3)
        assert result["leverage"] == pytest.approx(3.0)

    def test_market_only(self):
        result = compute_leverage(0, 0.4, 0.2, model_weight=0.5)
        assert result["true_prob"] == pytest.approx(0.4)
        assert result["leverage"] == pytest.approx(2.0)

    def test_both_zero_prob(self):
        result = compute_leverage(0, 0, 0.1, model_weight=0.5)
        assert result["leverage"] == 0
