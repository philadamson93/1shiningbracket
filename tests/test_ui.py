"""
Automated tests for the Streamlit UI using AppTest.

Covers: welcome state, load saved brackets, bracket display, analysis,
leverage table, what-if, portfolio, generate (single + multi), reset.

Run:  uv run python3 -m pytest tests/test_ui.py -v
"""

import sys
import os
import json
import pytest

# Ensure project root on path
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

from streamlit.testing.v1 import AppTest

APP_PATH = "ui/app.py"
TIMEOUT = 60


# ═══════════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.fixture
def app():
    """Boot the app in welcome state."""
    at = AppTest.from_file(APP_PATH, default_timeout=TIMEOUT)
    at.run()
    return at


@pytest.fixture
def app_with_saved(app):
    """App with saved brackets loaded."""
    btn = _find_button(app, "Load Saved")
    assert btn is not None, "Load Saved Brackets button not found"
    btn.click().run()
    return app


def _find_button(at, label_substring):
    for b in at.button:
        if label_substring in b.label:
            return b
    return None


# ═══════════════════════════════════════════════════════════════════════════════
# 1. WELCOME STATE
# ═══════════════════════════════════════════════════════════════════════════════


class TestWelcomeState:
    """Tests for the initial welcome screen (no brackets loaded)."""

    def test_no_errors(self, app):
        assert len(app.exception) == 0, [e.value for e in app.exception]

    def test_header(self, app):
        headers = [h.value for h in app.header]
        assert "March Madness Bracket Optimizer" in headers

    def test_championship_table(self, app):
        assert len(app.dataframe) >= 1, "Championship table missing"

    def test_buttons_present(self, app):
        labels = [b.label for b in app.button]
        assert "Generate" in labels
        assert any("Load" in l for l in labels), f"Load button missing, got: {labels}"

    def test_sidebar_controls(self, app):
        # Sliders for field size, brackets, etc.
        assert len(app.slider) >= 2, "Missing sidebar sliders"

    def test_no_metrics_in_welcome(self, app):
        # No bracket metrics should show before generation
        assert len(app.metric) == 0


# ═══════════════════════════════════════════════════════════════════════════════
# 2. LOAD SAVED BRACKETS
# ═══════════════════════════════════════════════════════════════════════════════


class TestLoadSaved:
    """Tests for loading brackets from final_brackets.json."""

    def test_no_errors(self, app_with_saved):
        assert len(app_with_saved.exception) == 0, \
            [e.value for e in app_with_saved.exception]

    def test_metrics_appear(self, app_with_saved):
        metrics = {m.label: m.value for m in app_with_saved.metric}
        assert "Champion" in metrics
        assert "Kelly EV" in metrics

    def test_champion_is_valid_team(self, app_with_saved):
        from sim_engine import BRACKET
        all_teams = {t for region in BRACKET.values() for t, _ in region}
        champ_metric = next(m for m in app_with_saved.metric if m.label == "Champion")
        # Extract team name from "(seed) Team"
        team = champ_metric.value.split(") ")[1] if ")" in champ_metric.value else champ_metric.value
        assert team in all_teams, f"Champion '{team}' not in bracket"

    def test_all_tabs_present(self, app_with_saved):
        tab_labels = [t.label for t in app_with_saved.tabs]
        assert "Bracket" in tab_labels
        assert "Analysis" in tab_labels
        assert "Leverage" in tab_labels
        assert "What-If" in tab_labels
        assert "Portfolio" in tab_labels, "Portfolio tab should show for 10 brackets"

    def test_bracket_selector(self, app_with_saved):
        # Should have a selectbox for choosing between brackets
        selects = app_with_saved.selectbox
        assert len(selects) >= 1, "Bracket selector missing"

    def test_dataframes_rendered(self, app_with_saved):
        # Leverage table + portfolio tables (visual bracket mode = no region tables)
        assert len(app_with_saved.dataframe) >= 1, \
            f"Expected at least 1 dataframe, got {len(app_with_saved.dataframe)}"

    def test_portfolio_tab_contents(self, app_with_saved):
        subheaders = [s.value for s in app_with_saved.subheader]
        assert "Portfolio Overview" in subheaders
        assert "Champion Diversity" in subheaders
        assert "Final Four Exposure" in subheaders

    def test_analysis_tab_no_sims(self, app_with_saved):
        # With loaded brackets (no sims), analysis should show info message
        infos = [i.value for i in app_with_saved.info]
        assert any("simulation" in i.lower() or "generate" in i.lower()
                    for i in infos), f"Expected sim info message, got: {infos}"

    def test_reset_button(self, app_with_saved):
        btn = _find_button(app_with_saved, "Reset")
        assert btn is not None, "Reset button missing"

    def test_download_button_exists(self, app_with_saved):
        # download_button not directly inspectable via AppTest;
        # verify no error on the page that includes it
        assert len(app_with_saved.exception) == 0


# ═══════════════════════════════════════════════════════════════════════════════
# 3. BRACKET SWITCHING
# ═══════════════════════════════════════════════════════════════════════════════


class TestBracketSwitching:
    """Test switching between brackets in portfolio mode."""

    def test_switch_to_second_bracket(self, app_with_saved):
        # Load saved has 10 brackets; switch to #2
        select = app_with_saved.selectbox[0]
        select.set_value(1).run()
        assert len(app_with_saved.exception) == 0, \
            [e.value for e in app_with_saved.exception]
        # Champion should update
        metrics = {m.label: m.value for m in app_with_saved.metric}
        assert "Champion" in metrics

    def test_switch_to_last_bracket(self, app_with_saved):
        select = app_with_saved.selectbox[0]
        # Get total options from saved brackets
        with open("final_brackets.json") as f:
            n = len(json.load(f))
        select.set_value(n - 1).run()
        assert len(app_with_saved.exception) == 0

    def test_different_brackets_may_have_different_champions(self, app_with_saved):
        with open("final_brackets.json") as f:
            saved = json.load(f)
        champions = {e["champion"] for e in saved}
        # Our portfolio should have some diversity
        assert len(champions) >= 2, "Portfolio has no champion diversity"


# ═══════════════════════════════════════════════════════════════════════════════
# 4. GENERATE SINGLE BRACKET
# ═══════════════════════════════════════════════════════════════════════════════


class TestGenerateSingle:
    """Test generating a single bracket (small sims for speed)."""

    @pytest.fixture
    def app_generated(self):
        at = AppTest.from_file(APP_PATH, default_timeout=TIMEOUT)
        at.run()
        # Set fast params via sidebar
        # Default is Single Bracket mode — just set small sims
        for s in at.select_slider:
            if s.label == "Simulations":
                s.set_value(50)
        at.run()
        # Click generate
        btn = _find_button(at, "Generate")
        assert btn is not None
        btn.click().run()
        return at

    def test_no_errors(self, app_generated):
        assert len(app_generated.exception) == 0, \
            [e.value for e in app_generated.exception]

    def test_metrics_present(self, app_generated):
        labels = {m.label for m in app_generated.metric}
        assert "Champion" in labels
        assert "Kelly EV" in labels
        assert "Avg Score" in labels
        assert "Win Rate" in labels

    def test_no_portfolio_tab(self, app_generated):
        tab_labels = [t.label for t in app_generated.tabs]
        assert "Portfolio" not in tab_labels

    def test_analysis_tab_has_charts(self, app_generated):
        subheaders = [s.value for s in app_generated.subheader]
        assert "Championship Probability: Model vs Simulated vs Public" in subheaders

    def test_what_if_has_game_selector(self, app_generated):
        # Should have game selector selectbox (in addition to bracket selector)
        # With 1 bracket, no bracket selector, so selectbox = game selector
        selects = app_generated.selectbox
        assert len(selects) >= 1, "Game selector missing in What-If tab"


# ═══════════════════════════════════════════════════════════════════════════════
# 5. GENERATE PORTFOLIO (2 brackets)
# ═══════════════════════════════════════════════════════════════════════════════


class TestGeneratePortfolio:
    """Test generating a 2-bracket portfolio."""

    @pytest.fixture
    def app_portfolio(self):
        at = AppTest.from_file(APP_PATH, default_timeout=TIMEOUT)
        at.run()
        # Switch to portfolio mode via radio
        for r in at.radio:
            if r.label == "Mode":
                r.set_value("Portfolio (multiple brackets)")
        for s in at.select_slider:
            if s.label == "Simulations":
                s.set_value(50)
        at.run()
        btn = _find_button(at, "Generate")
        btn.click().run()
        return at

    def test_no_errors(self, app_portfolio):
        assert len(app_portfolio.exception) == 0, \
            [e.value for e in app_portfolio.exception]

    def test_portfolio_tab_appears(self, app_portfolio):
        tab_labels = [t.label for t in app_portfolio.tabs]
        assert "Portfolio" in tab_labels

    def test_bracket_selector_present(self, app_portfolio):
        selects = app_portfolio.selectbox
        assert len(selects) >= 1


# ═══════════════════════════════════════════════════════════════════════════════
# 6. LEVERAGE TABLE
# ═══════════════════════════════════════════════════════════════════════════════


class TestLeverageTable:
    """Test the leverage table tab contents."""

    def test_leverage_subheader(self, app_with_saved):
        subheaders = [s.value for s in app_with_saved.subheader]
        assert any("Leverage" in s for s in subheaders)

    def test_leverage_has_dataframe(self, app_with_saved):
        # At minimum: championship table (welcome) + region tables + leverage
        assert len(app_with_saved.dataframe) >= 3


# ═══════════════════════════════════════════════════════════════════════════════
# 7. RESET
# ═══════════════════════════════════════════════════════════════════════════════


class TestReset:
    """Test the reset button returns to welcome state."""

    def test_reset_clears_brackets(self, app_with_saved):
        btn = _find_button(app_with_saved, "Reset")
        btn.click().run()
        assert len(app_with_saved.exception) == 0
        # Should be back to welcome state with header
        headers = [h.value for h in app_with_saved.header]
        assert "March Madness Bracket Optimizer" in headers
        # No metrics
        assert len(app_with_saved.metric) == 0


# ═══════════════════════════════════════════════════════════════════════════════
# 8. DATA INTEGRITY
# ═══════════════════════════════════════════════════════════════════════════════


class TestDataIntegrity:
    """Test that loaded data is consistent and complete."""

    def test_all_bracket_teams_have_model_probs(self):
        from sim_engine import BRACKET
        from data_loader import load_year_data
        from sim_engine import blend_probs
        data = load_year_data(2026)
        probs = blend_probs(data["model"], data.get("market", {}), 0.35)
        bracket_teams = {t for region in BRACKET.values() for t, _ in region}
        missing = bracket_teams - set(probs.keys())
        assert len(missing) == 0, f"Teams missing from blended probs: {missing}"

    def test_saved_brackets_valid(self):
        from sim_engine import BRACKET, build_game_tree, bracket_to_display
        all_teams = {t for region in BRACKET.values() for t, _ in region}
        gt = build_game_tree()
        with open("final_brackets.json") as f:
            saved = json.load(f)
        for i, entry in enumerate(saved):
            assert "champion" in entry, f"Bracket {i}: missing champion"
            assert "regions" in entry, f"Bracket {i}: missing regions"
            assert entry["champion"] in all_teams, \
                f"Bracket {i}: champion '{entry['champion']}' not in bracket"
            # Roundtrip test
            from ui.app import json_to_flat_bracket
            flat = json_to_flat_bracket(entry)
            assert all(t is not None for t in flat), \
                f"Bracket {i}: has None entries after conversion"
            d = bracket_to_display(flat, gt)
            assert d["champion"] == entry["champion"], \
                f"Bracket {i}: roundtrip champion mismatch"

    def test_game_tree_structure(self):
        from sim_engine import build_game_tree
        r1, feeders, rounds, points = build_game_tree()
        assert len(r1) == 32
        assert len(feeders) == 31  # games 32-62
        assert len(rounds) == 63
        assert len(points) == 63
        assert sum(points) == 1920  # max possible score

    def test_seed_map_complete(self):
        from sim_engine import BRACKET
        all_teams = {t for region in BRACKET.values() for t, _ in region}
        assert len(all_teams) == 64, f"Expected 64 teams, got {len(all_teams)}"
