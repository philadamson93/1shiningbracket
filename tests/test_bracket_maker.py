"""Tests for bracket_maker.py — pool loading, portfolio construction."""

import pytest

from bracket_maker import load_pools, build_portfolio, DEFAULT_POOLS
from sim_engine import (
    build_game_tree, make_chalk_bracket, precompute_sims, BRACKET,
)


# ═══════════════════════════════════════════════════════════════════════════════
# LOAD POOLS
# ═══════════════════════════════════════════════════════════════════════════════


class TestLoadPools:

    def test_loads_from_file(self):
        pools = load_pools("pools.toml")
        assert len(pools) >= 1

    def test_pool_has_required_keys(self):
        pools = load_pools("pools.toml")
        for p in pools:
            assert "name" in p
            assert "field_size" in p
            assert "payout" in p

    def test_payout_is_dict(self):
        pools = load_pools("pools.toml")
        for p in pools:
            assert isinstance(p["payout"], dict)
            for pos, frac in p["payout"].items():
                assert isinstance(pos, int)
                assert isinstance(frac, float)

    def test_fallback_when_file_missing(self):
        pools = load_pools("nonexistent_file.toml")
        assert pools == DEFAULT_POOLS

    def test_payout_values_are_fractions(self):
        pools = load_pools("pools.toml")
        for p in pools:
            for pos, frac in p["payout"].items():
                assert 0 < frac <= 1.0, f"Payout {pos}={frac} not a fraction"


# ═══════════════════════════════════════════════════════════════════════════════
# BUILD PORTFOLIO
# ═══════════════════════════════════════════════════════════════════════════════


class TestBuildPortfolio:

    def test_returns_correct_count(self, sample_probs, game_tree,
                                    small_precomputed):
        pools = [
            {"name": "Pool A", "field_size": 50,
             "payout": {1: 0.60, 2: 0.20, 3: 0.10}},
            {"name": "Pool B", "field_size": 50,
             "payout": {1: 0.60, 2: 0.20, 3: 0.10}},
        ]
        results = build_portfolio(pools, sample_probs, sample_probs,
                                   game_tree, small_precomputed, 1.0)
        assert len(results) == 2

    def test_each_bracket_has_63_entries(self, sample_probs, game_tree,
                                          small_precomputed):
        pools = [{"name": "Test", "field_size": 50,
                  "payout": {1: 1.0}}]
        results = build_portfolio(pools, sample_probs, sample_probs,
                                   game_tree, small_precomputed, 1.0)
        bracket, _, _ = results[0]
        assert len(bracket) == 63
        assert all(t is not None for t in bracket)

    def test_each_bracket_valid_teams(self, sample_probs, game_tree,
                                       small_precomputed, all_bracket_teams):
        pools = [{"name": "Test", "field_size": 50,
                  "payout": {1: 1.0}}]
        results = build_portfolio(pools, sample_probs, sample_probs,
                                   game_tree, small_precomputed, 1.0)
        bracket, _, _ = results[0]
        for t in bracket:
            assert t in all_bracket_teams
