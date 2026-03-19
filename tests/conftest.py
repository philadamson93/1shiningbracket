"""Shared fixtures for the March Madness bracket optimizer test suite."""

import sys
import os
import random

import pytest

# ---------------------------------------------------------------------------
# Path setup — ensure src/ and project root are importable
# ---------------------------------------------------------------------------

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

import sim_engine
from sim_engine import (
    build_game_tree, make_chalk_bracket, simulate_tournament,
    build_feeds_into, precompute_sims, BRACKET, ROUND_NAMES,
)
from data_loader import load_year_data
from sim_engine import blend_probs


# ---------------------------------------------------------------------------
# Seed-based probability table for unit tests (no CSV dependency)
# ---------------------------------------------------------------------------

_SEED_PROB = {
    1:  {"R1": 0.97, "R2": 0.88, "S16": 0.72, "E8": 0.55, "F4": 0.35, "Championship": 0.15},
    2:  {"R1": 0.94, "R2": 0.78, "S16": 0.60, "E8": 0.40, "F4": 0.22, "Championship": 0.07},
    3:  {"R1": 0.90, "R2": 0.65, "S16": 0.48, "E8": 0.28, "F4": 0.14, "Championship": 0.04},
    4:  {"R1": 0.85, "R2": 0.58, "S16": 0.40, "E8": 0.22, "F4": 0.10, "Championship": 0.03},
    5:  {"R1": 0.72, "R2": 0.45, "S16": 0.28, "E8": 0.14, "F4": 0.06, "Championship": 0.015},
    6:  {"R1": 0.68, "R2": 0.40, "S16": 0.24, "E8": 0.12, "F4": 0.05, "Championship": 0.012},
    7:  {"R1": 0.64, "R2": 0.35, "S16": 0.20, "E8": 0.09, "F4": 0.04, "Championship": 0.008},
    8:  {"R1": 0.52, "R2": 0.25, "S16": 0.14, "E8": 0.06, "F4": 0.025, "Championship": 0.005},
    9:  {"R1": 0.48, "R2": 0.25, "S16": 0.14, "E8": 0.06, "F4": 0.025, "Championship": 0.005},
    10: {"R1": 0.36, "R2": 0.18, "S16": 0.09, "E8": 0.04, "F4": 0.015, "Championship": 0.003},
    11: {"R1": 0.32, "R2": 0.15, "S16": 0.07, "E8": 0.03, "F4": 0.012, "Championship": 0.003},
    12: {"R1": 0.28, "R2": 0.12, "S16": 0.05, "E8": 0.02, "F4": 0.007, "Championship": 0.001},
    13: {"R1": 0.15, "R2": 0.06, "S16": 0.025, "E8": 0.008, "F4": 0.003, "Championship": 0.0005},
    14: {"R1": 0.10, "R2": 0.04, "S16": 0.015, "E8": 0.005, "F4": 0.002, "Championship": 0.0003},
    15: {"R1": 0.06, "R2": 0.02, "S16": 0.007, "E8": 0.003, "F4": 0.001, "Championship": 0.0001},
    16: {"R1": 0.03, "R2": 0.01, "S16": 0.003, "E8": 0.001, "F4": 0.0003, "Championship": 0.0001},
}


def _build_sample_probs():
    """Build probability dict for all 64 bracket teams from seed-based table."""
    probs = {}
    for region, teams in BRACKET.items():
        for team, seed in teams:
            probs[team] = dict(_SEED_PROB[seed])
    return probs


# ---------------------------------------------------------------------------
# Session-scoped fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session", autouse=True)
def init_cached_game_tree():
    """Ensure sim_engine._cached_game_tree is set for score_bracket()."""
    sim_engine._cached_game_tree = build_game_tree()
    yield
    sim_engine._cached_game_tree = None


@pytest.fixture(scope="session")
def game_tree():
    return build_game_tree()


@pytest.fixture(scope="session")
def sample_probs():
    return _build_sample_probs()


@pytest.fixture(scope="session")
def chalk_bracket(sample_probs, game_tree):
    return make_chalk_bracket(sample_probs, game_tree)


@pytest.fixture(scope="session")
def sample_outcome(sample_probs, game_tree):
    random.seed(42)
    return simulate_tournament(sample_probs, game_tree)


@pytest.fixture(scope="session")
def feeds_into(game_tree):
    return build_feeds_into(game_tree)


@pytest.fixture(scope="session")
def small_precomputed(sample_probs, game_tree):
    random.seed(42)
    return precompute_sims(sample_probs, sample_probs, 0.3, 5, 10, game_tree)


@pytest.fixture(scope="session")
def real_2026_data():
    return load_year_data(2026)


@pytest.fixture(scope="session")
def blended_probs(real_2026_data):
    return blend_probs(
        real_2026_data["model"],
        real_2026_data.get("market", {}),
        0.35,
    )


@pytest.fixture(scope="session")
def all_bracket_teams():
    """Set of all 64 team names in the bracket."""
    return {t for region in BRACKET.values() for t, _ in region}
