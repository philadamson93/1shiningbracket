"""
March Madness Bracket Optimizer — Streamlit UI

Generate Kelly-optimal brackets for your NCAA tournament pools.

Usage:
    uv run --extra ui streamlit run ui/app.py
"""

import sys
import os
import json
import random
import math
from pathlib import Path
from collections import defaultdict

import streamlit as st
import pandas as pd

# ---------------------------------------------------------------------------
# Project root — ensure imports and data paths resolve
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
os.chdir(ROOT)

from sim_engine import (
    build_game_tree,
    make_chalk_bracket,
    score_bracket_with_tree,
    blend_probs,
    estimate_position,
    bracket_to_display,
    get_game_prob,
    precompute_sims,
    build_feeds_into,
    build_locked_games,
    hill_climb,
    compute_kelly_ev,
    flip_game,
    BRACKET,
    REGIONS,
    SCORING,
    ROUND_NAMES,
)
from bracket_maker import (
    build_portfolio,
    PAYOUT_STEEP,
    PAYOUT_WTA,
    PAYOUT_SPREAD,
)
from data_loader import load_year_data, STANDARD_ROUNDS

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="March Madness Bracket Optimizer",
    page_icon="\U0001F3C0",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Cached loaders
# ---------------------------------------------------------------------------


@st.cache_data
def load_data(year=2026):
    return load_year_data(year)


@st.cache_data
def cached_game_tree():
    return build_game_tree()


# ---------------------------------------------------------------------------
# Constants & helpers
# ---------------------------------------------------------------------------

PAYOUT_PRESETS = {
    "Top-Heavy (60/20/7.5/5/...)": PAYOUT_STEEP,
    "Winner-Take-All": PAYOUT_WTA,
    "Spread (50/15/10/7/...)": PAYOUT_SPREAD,
    "Custom": None,
}

DEFAULT_CUSTOM_PAYOUT = "60, 20, 10, 5, 3, 2"

# Build seed and region maps from the bracket structure
SEED_MAP = {}
TEAM_REGION = {}
for _region, _teams in BRACKET.items():
    for _team, _seed in _teams:
        SEED_MAP[_team] = _seed
        TEAM_REGION[_team] = _region


def fmt_seed(team):
    """Format team with seed, e.g. '(1) Duke'."""
    s = SEED_MAP.get(team, "?")
    return f"({s}) {team}"


def leverage_val(team, rd, our_probs, public_probs):
    """Compute leverage = blended_prob / public_prob."""
    our = our_probs.get(team, {}).get(rd, 0)
    pub = public_probs.get(team, {}).get(rd, 0)
    if pub > 0.001:
        return our / pub
    return None


def region_game_indices(region_idx):
    """Game indices for a region, grouped by round."""
    base_r1 = region_idx * 8
    base_r2 = 32 + region_idx * 4
    base_s16 = 48 + region_idx * 2
    return {
        "R1": list(range(base_r1, base_r1 + 8)),
        "R2": list(range(base_r2, base_r2 + 4)),
        "S16": list(range(base_s16, base_s16 + 2)),
        "E8": [56 + region_idx],
    }


def compute_stats(bracket, precomputed, game_tree, field_size):
    """Expected score, percentile, and win probability from precomputed sims."""
    if not precomputed:
        return {"avg_score": 0, "avg_pct": 0, "win_pct": 0,
                "scores": [], "positions": []}
    scores, positions, wins = [], [], 0
    for outcome, opp_scores in precomputed:
        sc = score_bracket_with_tree(bracket, outcome, game_tree)
        pos = estimate_position(sc, opp_scores, field_size)
        scores.append(sc)
        positions.append(pos)
        if pos == 1:
            wins += 1
    n = len(precomputed)
    return {
        "avg_score": sum(scores) / n,
        "avg_pct": 100 * (1 - sum(positions) / (n * field_size)),
        "win_pct": 100 * wins / n,
        "scores": scores,
        "positions": positions,
    }


def sim_champion_dist(precomputed):
    """Champion frequency distribution from simulated outcomes."""
    champs = defaultdict(int)
    for outcome, _ in precomputed:
        champs[outcome[62]] += 1
    n = len(precomputed)
    return dict(sorted(
        {t: c / n for t, c in champs.items()}.items(),
        key=lambda x: -x[1],
    ))


def json_to_flat_bracket(entry):
    """Convert saved JSON bracket (display format) back to flat 63-element list."""
    bracket = [None] * 63
    regions_data = entry["regions"]
    for region_idx, region in enumerate(REGIONS):
        rd = regions_data[region]
        for j, team in enumerate(rd["R1"]):
            bracket[region_idx * 8 + j] = team
        for j, team in enumerate(rd["R2"]):
            bracket[32 + region_idx * 4 + j] = team
        for j, team in enumerate(rd["S16"]):
            bracket[48 + region_idx * 2 + j] = team
        bracket[56 + region_idx] = rd["E8"][0]
    cg = entry.get("championship_game", entry.get("F4_winners", []))
    bracket[60] = cg[0] if len(cg) > 0 else None
    bracket[61] = cg[1] if len(cg) > 1 else None
    bracket[62] = entry["champion"]
    return bracket


def render_bracket_html(bracket, game_tree):
    """Render a proper NCAA-style bracket using CSS Grid.

    Shows both teams in every matchup, with bracket connector lines between
    rounds.  Winners are bold on white; losers are dimmed.  The eventual
    champion's path gets a gold left-border accent.
    """
    r1_matchups, feeder_games, _, _ = game_tree
    champion = bracket[62]

    # ── Grid row positions (1-indexed) ──────────────────────────────────
    R1_POS  = [(2 * i + 1, 2 * i + 2) for i in range(8)]
    R2_POS  = [(2, 3), (6, 7), (10, 11), (14, 15)]
    S16_POS = [(4, 5), (12, 13)]
    E8_POS  = [(8, 9)]
    CONN_12 = [(2, 4), (6, 8), (10, 12), (14, 16)]
    CONN_23 = [(3, 7), (11, 15)]
    CONN_34 = [(5, 13)]

    ROW_H  = 26
    N_ROWS = 16
    TW     = 155   # team column width
    CW     = 16    # connector column width
    COLS   = f"{TW}px {CW}px {TW}px {CW}px {TW}px {CW}px {TW}px"

    css = f"""<style>
.bg{{display:grid;grid-template-rows:repeat({N_ROWS},{ROW_H}px);
grid-template-columns:{COLS};width:fit-content;margin-bottom:20px;row-gap:1px}}
.bt{{font-size:15px;font-weight:700;margin:16px 0 4px;color:#1a1a1a}}
.bl{{display:grid;grid-template-columns:{COLS};width:fit-content}}
.bh{{font-size:10px;font-weight:600;color:#999;text-transform:uppercase;
letter-spacing:.5px;text-align:center;padding-bottom:2px}}
.t{{display:flex;align-items:center;padding:0 6px;font-size:12px;
border:1px solid #e8e8e8;background:#f7f7f7;color:#bbb;font-weight:400;
white-space:nowrap;overflow:hidden;line-height:{ROW_H - 3}px}}
.t.w{{background:#fff;color:#222;font-weight:600;border-color:#d0d0d0}}
.t.cp{{border-left:3px solid #eab308;background:#fefce8}}
.t .s{{font-weight:700;width:20px;text-align:right;margin-right:5px;
flex-shrink:0}}
.t.w .s{{color:#666}}
.tt{{border-bottom:none;border-radius:3px 3px 0 0}}
.tb{{border-radius:0 0 3px 3px}}
.cn{{border:2px solid #ddd;border-left:none;border-radius:0 4px 4px 0;
margin:0 2px}}
.fw{{display:flex;gap:12px;align-items:center;flex-wrap:wrap;margin-top:8px}}
.fm{{border:1px solid #e0e0e0;border-radius:6px;overflow:hidden}}
.fm .t{{border:none;border-bottom:1px solid #f0f0f0;line-height:28px}}
.fm .t:last-child{{border-bottom:none}}
.cb{{background:linear-gradient(135deg,#fbbf24,#f59e0b);color:#78350f;
font-weight:700;font-size:15px;padding:8px 16px;border-radius:8px;
text-align:center;white-space:nowrap}}
.fa{{font-size:18px;color:#ccc}}</style>"""

    def td(team, is_top, col, row, winner):
        """One team cell in the grid."""
        is_w  = (team == winner)
        is_cp = is_w and (team == champion)
        cls = "t " + ("tt" if is_top else "tb")
        if is_w:
            cls += " w"
        if is_cp:
            cls += " cp"
        seed = SEED_MAP.get(team, "?")
        return (f'<div class="{cls}" style="grid-column:{col};'
                f'grid-row:{row}/{row + 1}">'
                f'<span class="s">{seed}</span>{team}</div>')

    P = [css]

    for ri, region in enumerate(REGIONS):
        games = region_game_indices(ri)

        # Region title + round labels
        P.append(f'<div class="bt">{region}</div><div class="bl">')
        for rd in ("R1", "R2", "S16", "E8"):
            P.append(f'<div class="bh">{rd}</div>')
            if rd != "E8":
                P.append("<div></div>")
        P.append("</div><div class=\"bg\">")

        # R1 — col 1
        for i, g in enumerate(games["R1"]):
            ta, tb = r1_matchups[g]
            w = bracket[g]
            r_top, r_bot = R1_POS[i]
            P.append(td(ta, True,  1, r_top, w))
            P.append(td(tb, False, 1, r_bot, w))

        # Connectors R1→R2 — col 2
        for s, e in CONN_12:
            P.append(f'<div class="cn" style="grid-column:2;'
                     f'grid-row:{s}/{e}"></div>')

        # R2 — col 3
        for i, g in enumerate(games["R2"]):
            ta, tb = bracket[feeder_games[g][0]], bracket[feeder_games[g][1]]
            w = bracket[g]
            r_top, r_bot = R2_POS[i]
            P.append(td(ta, True,  3, r_top, w))
            P.append(td(tb, False, 3, r_bot, w))

        # Connectors R2→S16 — col 4
        for s, e in CONN_23:
            P.append(f'<div class="cn" style="grid-column:4;'
                     f'grid-row:{s}/{e}"></div>')

        # S16 — col 5
        for i, g in enumerate(games["S16"]):
            ta, tb = bracket[feeder_games[g][0]], bracket[feeder_games[g][1]]
            w = bracket[g]
            r_top, r_bot = S16_POS[i]
            P.append(td(ta, True,  5, r_top, w))
            P.append(td(tb, False, 5, r_bot, w))

        # Connector S16→E8 — col 6
        for s, e in CONN_34:
            P.append(f'<div class="cn" style="grid-column:6;'
                     f'grid-row:{s}/{e}"></div>')

        # E8 — col 7
        g = games["E8"][0]
        ta, tb = bracket[feeder_games[g][0]], bracket[feeder_games[g][1]]
        w = bracket[g]
        r_top, r_bot = E8_POS[0]
        P.append(td(ta, True,  7, r_top, w))
        P.append(td(tb, False, 7, r_bot, w))

        P.append("</div>")  # close bg

    # ── Final Four + Championship ────────────────────────────────────
    ff   = [bracket[56], bracket[57], bracket[58], bracket[59]]
    ff_w = [bracket[60], bracket[61]]
    champ = bracket[62]

    def ff_td(team, winner, is_top):
        is_w  = (team == winner)
        is_cp = is_w and (team == champ)
        cls = "t " + ("tt" if is_top else "tb")
        if is_w:
            cls += " w"
        if is_cp:
            cls += " cp"
        seed = SEED_MAP.get(team, "?")
        return f'<div class="{cls}"><span class="s">{seed}</span>{team}</div>'

    # Use a 4-column grid: Semi1 | connector | Championship | connector | Semi2
    # but render as a clean mini-bracket
    P.append(f"""<div class="bt">Final Four & Championship</div>
<div style="display:grid;grid-template-columns:{TW}px {CW}px {TW}px {CW}px auto;
grid-template-rows:repeat(4,{ROW_H}px);width:fit-content;row-gap:1px;
align-items:stretch;margin-bottom:12px">
<div class="bh" style="grid-column:1;grid-row:1">Semi 1 (East v West)</div>
<div style="grid-column:2;grid-row:1"></div>
<div class="bh" style="grid-column:3;grid-row:1">Championship</div>
<div style="grid-column:4;grid-row:1"></div>
<div class="bh" style="grid-column:5;grid-row:1">Semi 2 (South v MW)</div>""")
    # Semi 1: rows 2-3
    P.append(ff_td(ff[0], ff_w[0], True).replace(
        'class="', f'style="grid-column:1;grid-row:2" class="'))
    P.append(ff_td(ff[1], ff_w[0], False).replace(
        'class="', f'style="grid-column:1;grid-row:3" class="'))
    # Connector semi1 → champ
    P.append(f'<div class="cn" style="grid-column:2;grid-row:2/4"></div>')
    # Championship: rows 2-3
    P.append(ff_td(ff_w[0], champ, True).replace(
        'class="', f'style="grid-column:3;grid-row:2" class="'))
    P.append(ff_td(ff_w[1], champ, False).replace(
        'class="', f'style="grid-column:3;grid-row:3" class="'))
    # Connector champ ← semi2
    P.append(f'<div class="cn" style="grid-column:4;grid-row:2/4;'
             f'border-right:none;border-left:2px solid #ddd;'
             f'border-radius:4px 0 0 4px"></div>')
    # Semi 2: rows 2-3
    P.append(ff_td(ff[2], ff_w[1], True).replace(
        'class="', f'style="grid-column:5;grid-row:2" class="'))
    P.append(ff_td(ff[3], ff_w[1], False).replace(
        'class="', f'style="grid-column:5;grid-row:3" class="'))
    # Champion banner: row 4, spanning all columns
    seed = SEED_MAP.get(champ, "?")
    P.append(f'<div class="cb" style="grid-column:1/6;grid-row:4;'
             f'margin-top:4px">'
             f'\U0001F3C6 Champion: ({seed}) {champ}</div>')
    P.append("</div>")

    return "\n".join(P)


# ---------------------------------------------------------------------------
# Load core data
# ---------------------------------------------------------------------------

data = load_data()
game_tree = cached_game_tree()
r1_matchups, feeder_games, game_round, game_points = game_tree

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

with st.sidebar:
    st.title("\U0001F3C0 Bracket Optimizer")
    st.caption("Kelly-optimal March Madness brackets")

    st.divider()
    st.subheader("Pool Settings")

    field_size = st.slider("Field size", 10, 1000, 250, step=10,
                           help="Number of entries in your pool")
    payout_name = st.selectbox("Payout structure", list(PAYOUT_PRESETS.keys()))
    if payout_name == "Custom":
        custom_str = st.text_input(
            "Payout % by place (comma-separated)",
            value=DEFAULT_CUSTOM_PAYOUT,
            help="e.g. '60, 20, 10, 5, 3, 2' means 1st gets 60%, 2nd gets 20%, etc.",
        )
        try:
            parts = [float(x.strip()) for x in custom_str.split(",") if x.strip()]
            payout = {i + 1: v / 100 for i, v in enumerate(parts)}
            total = sum(payout.values())
            if total > 1.01:
                st.warning(f"Payout sums to {total*100:.0f}% (>100%)")
            elif total < 0.5:
                st.warning(f"Payout sums to {total*100:.0f}% — did you enter percentages?")
        except ValueError:
            st.error("Invalid input. Use comma-separated numbers like: 60, 20, 10, 5")
            payout = PAYOUT_STEEP
    else:
        payout = PAYOUT_PRESETS[payout_name]

    st.divider()
    mode = st.radio(
        "Mode",
        ["Single Bracket", "Portfolio (multiple brackets)"],
        help="Portfolio generates diversified brackets via Kelly criterion — "
             "each bracket is optimized for its marginal contribution to the set.",
    )
    if mode == "Portfolio (multiple brackets)":
        num_brackets = st.slider("Number of brackets", 2, 10, 3)
    else:
        num_brackets = 1

    st.divider()
    with st.expander("Advanced Parameters"):
        model_weight = st.slider("Model weight", 0.0, 1.0, 0.35, 0.05,
                                 help="0 = pure market (DK odds), 1 = pure model (Paine)")
        sigma = st.slider("Sigma (model uncertainty)", 0.10, 0.60, 0.27, 0.01,
                          help="Logit-space noise. 0.27 calibrated from 538 data.")
        m_sims = st.select_slider("Simulations",
                                  options=[50, 100, 200, 500, 1000, 2000],
                                  value=200,
                                  help="More = slower but more accurate")
        n_opp = st.slider("Opponents per sim", 100, 1000, 400, 50,
                          help="Should be >= field size")
        wealth_base = st.slider("Kelly wealth base", 0.1, 5.0, 1.0, 0.1,
                                help="Higher = less diversification across portfolio")
        rand_seed = st.number_input("Random seed", value=42, step=1)

    st.divider()
    generate = st.button("Generate", type="primary", use_container_width=True)

    if os.path.exists("output/final_brackets.json"):
        load_saved = st.button("Load Saved Brackets", use_container_width=True)
    else:
        load_saved = False

# ---------------------------------------------------------------------------
# Blend probabilities (uses current sidebar model_weight)
# ---------------------------------------------------------------------------

our_probs = blend_probs(data["model"], data.get("market", {}), model_weight)
public_probs = data["public"]

# ---------------------------------------------------------------------------
# Generate brackets
# ---------------------------------------------------------------------------

if generate:
    with st.status("Generating bracket...", expanded=True) as status:
        st.write(f"Precomputing {m_sims} simulations x {n_opp} opponents...")
        random.seed(rand_seed)
        precomputed = precompute_sims(our_probs, public_probs, sigma, m_sims,
                                     n_opp, game_tree)
        st.session_state["precomputed"] = precomputed
        st.write("Precomputation complete.")

        feeds_into = build_feeds_into(game_tree)
        locked = build_locked_games(our_probs, game_tree)

        if num_brackets == 1:
            st.write("Hill climbing (single bracket)...")
            chalk = make_chalk_bracket(our_probs, game_tree)
            existing_payouts = [0.0] * len(precomputed)
            bracket, kelly_ev = hill_climb(
                chalk, game_tree, our_probs, precomputed,
                field_size, payout, existing_payouts, wealth_base,
                feeds_into, locked,
            )
            st.session_state["brackets"] = [
                (list(bracket),
                 {"name": "My Pool", "field_size": field_size, "payout": payout},
                 kelly_ev),
            ]
        else:
            st.write(f"Building {num_brackets}-bracket portfolio...")
            pools = [{"name": f"Bracket {i+1}", "field_size": field_size,
                      "payout": payout} for i in range(num_brackets)]
            results = build_portfolio(pools, our_probs, public_probs, game_tree,
                                     precomputed, wealth_base)
            st.session_state["brackets"] = [
                (list(b), p, kev) for b, p, kev in results
            ]

        status.update(label="Done!", state="complete")
    st.session_state["gen_probs"] = our_probs
    st.session_state["gen_public"] = public_probs
    st.session_state["gen_params"] = {
        "field_size": field_size, "sigma": sigma, "model_weight": model_weight,
        "m_sims": m_sims, "wealth_base": wealth_base,
    }
    st.rerun()

# Load saved brackets from JSON
if load_saved:
    with open("output/final_brackets.json") as f:
        saved = json.load(f)
    brackets_list = []
    for entry in saved:
        flat = json_to_flat_bracket(entry)
        pool = {"name": entry.get("pool", "Saved"),
                "field_size": entry.get("field_size", 250),
                "payout": PAYOUT_SPREAD}
        brackets_list.append((flat, pool, entry.get("kelly_ev", 0)))
    st.session_state["brackets"] = brackets_list
    st.session_state["precomputed"] = []
    st.session_state["gen_probs"] = our_probs
    st.session_state["gen_public"] = public_probs
    st.rerun()


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN CONTENT
# ═══════════════════════════════════════════════════════════════════════════════


if "brackets" not in st.session_state:
    # ------------------------------------------------------------------
    # WELCOME STATE — no brackets generated yet
    # ------------------------------------------------------------------
    st.header("March Madness Bracket Optimizer")
    st.markdown("""
Configure your pool in the sidebar and click **Generate** to create an
optimized bracket.

**How it works:**
- **Model separation** — simulated "truth" differs from the picking model
  to avoid circular chalk bias
- **Kelly criterion** — maximizes expected log-wealth, naturally producing
  contrarian picks in large pools and chalk in small ones
- **Hill climbing** — iteratively flips game picks to improve expected value
  (Clair & Letscher 2007 + Haugh & Singal 2021)

**Data sources:** Paine 6-model composite, DraftKings odds, ESPN Gambit API
(132M+ brackets).
    """)

    # Championship probability preview
    st.subheader("2026 Championship Probabilities")
    rows = []
    for team in our_probs:
        cp = our_probs[team].get("Championship", 0)
        if cp < 0.005:
            continue
        rows.append({
            "Team": fmt_seed(team),
            "Region": TEAM_REGION.get(team, ""),
            "Model": f"{data['model'].get(team, {}).get('Championship', 0):.1%}",
            "Market": f"{data.get('market', {}).get(team, {}).get('Championship', 0):.1%}",
            "Public": f"{public_probs.get(team, {}).get('Championship', 0):.1%}",
            "Blended": f"{cp:.1%}",
        })
    rows.sort(key=lambda r: float(r["Blended"].rstrip("%")), reverse=True)
    st.dataframe(rows, use_container_width=True, hide_index=True)

else:
    # ------------------------------------------------------------------
    # RESULTS STATE — brackets available
    # ------------------------------------------------------------------
    brackets = st.session_state["brackets"]
    precomputed = st.session_state.get("precomputed", [])
    gen_probs = st.session_state.get("gen_probs", our_probs)
    gen_public = st.session_state.get("gen_public", public_probs)

    # Bracket selector (portfolio mode)
    if len(brackets) > 1:
        names = [f"#{i+1} {b[1]['name']} — Champion: {fmt_seed(b[0][62])}"
                 for i, b in enumerate(brackets)]
        sel = st.selectbox("Select bracket", range(len(brackets)),
                           format_func=lambda i: names[i])
    else:
        sel = 0

    bracket, pool_info, kelly_ev = brackets[sel]
    fs = pool_info["field_size"]

    # Stats (only if we have precomputed sims)
    stats = compute_stats(bracket, precomputed, game_tree, fs) if precomputed else None

    # Summary metrics
    display = bracket_to_display(bracket, game_tree)
    cols = st.columns(5)
    cols[0].metric("Champion", fmt_seed(bracket[62]))
    cols[1].metric("Kelly EV", f"{kelly_ev:.4f}")
    if stats:
        cols[2].metric("Avg Score", f"{stats['avg_score']:.0f}")
        cols[3].metric("Avg Percentile", f"{stats['avg_pct']:.0f}th")
        cols[4].metric("Win Rate", f"{stats['win_pct']:.1f}%")

    # Tabs
    tab_names = ["Bracket", "Analysis", "Leverage", "What-If"]
    if len(brackets) > 1:
        tab_names.append("Portfolio")
    tabs = st.tabs(tab_names)

    # ==================================================================
    # TAB 1: BRACKET
    # ==================================================================
    with tabs[0]:
        view_mode = st.radio("View", ["Visual", "Detail"],
                             horizontal=True, label_visibility="collapsed")

        if view_mode == "Visual":
            # Color-coded bracket tree
            bracket_html = render_bracket_html(bracket, game_tree)
            st.html(bracket_html)
        else:
            # Final Four & Championship
            st.subheader("Final Four & Championship")
            ff = display["F4"]
            ff_w = display["F4_winners"]
            champ = display["champion"]

            semi1, arrow1, final, arrow2, semi2 = st.columns([2, 1, 2, 1, 2])
            with semi1:
                st.markdown(f"**Semifinal 1** (East vs West)")
                st.markdown(f"- {fmt_seed(ff[0])}")
                st.markdown(f"- {fmt_seed(ff[1])}")
            with arrow1:
                st.markdown("&nbsp;")
                st.markdown(f"**{fmt_seed(ff_w[0])}** \u2192")
            with final:
                st.markdown("**Championship**")
                st.markdown(f"### \U0001F3C6 {fmt_seed(champ)}")
            with arrow2:
                st.markdown("&nbsp;")
                st.markdown(f"\u2190 **{fmt_seed(ff_w[1])}**")
            with semi2:
                st.markdown(f"**Semifinal 2** (South vs Midwest)")
                st.markdown(f"- {fmt_seed(ff[2])}")
                st.markdown(f"- {fmt_seed(ff[3])}")

            st.divider()

            # Region-by-region detail tables
            for region_idx, region in enumerate(REGIONS):
                games = region_game_indices(region_idx)
                e8_winner = bracket[56 + region_idx]

                with st.expander(
                    f"**{region}** \u2014 Winner: {fmt_seed(e8_winner)}",
                    expanded=False,
                ):
                    for rd_name in ["R1", "R2", "S16", "E8"]:
                        st.markdown(f"**{rd_name}** ({SCORING[rd_name]} pts)")
                        rows = []
                        for g in games[rd_name]:
                            if g < 32:
                                ta, tb = r1_matchups[g]
                            else:
                                fa, fb = feeder_games[g]
                                ta, tb = bracket[fa], bracket[fb]

                            pick = bracket[g]
                            our_p = gen_probs.get(pick, {}).get(rd_name, 0)
                            pub_p = gen_public.get(pick, {}).get(rd_name, 0)
                            lev = leverage_val(pick, rd_name, gen_probs, gen_public)

                            rows.append({
                                "Matchup": f"{fmt_seed(ta)}  vs  {fmt_seed(tb)}",
                                "Pick": fmt_seed(pick),
                                "Advance %": f"{our_p:.0%}",
                                "Public %": f"{pub_p:.0%}",
                                "Leverage": (f"{lev:.2f}x" if lev
                                             else "\u2014"),
                            })
                        st.dataframe(rows, use_container_width=True,
                                     hide_index=True)

        # Download bracket as JSON
        bracket_json = json.dumps(
            bracket_to_display(bracket, game_tree), indent=2
        )
        st.download_button("Download bracket JSON", bracket_json,
                           "bracket.json", "application/json")

    # ==================================================================
    # TAB 2: ANALYSIS
    # ==================================================================
    with tabs[1]:
        if not precomputed:
            st.info("No simulation data. Click **Generate** to run simulations.")
        else:
            # Champion distribution comparison
            st.subheader("Championship Probability: Model vs Simulated vs Public")
            champ_dist = sim_champion_dist(precomputed)
            top_teams = list(champ_dist.keys())[:12]
            df_champ = pd.DataFrame({
                "Simulated": [champ_dist.get(t, 0) for t in top_teams],
                "Model (blended)": [gen_probs.get(t, {}).get("Championship", 0)
                                    for t in top_teams],
                "Public": [gen_public.get(t, {}).get("Championship", 0)
                           for t in top_teams],
            }, index=[fmt_seed(t) for t in top_teams])
            st.bar_chart(df_champ)

            # Score distribution
            st.subheader("Score Distribution (Your Bracket vs Simulations)")
            if stats and stats["scores"]:
                df_scores = pd.DataFrame({"Score": stats["scores"]})
                st.bar_chart(df_scores["Score"].value_counts().sort_index())
                c1, c2, c3 = st.columns(3)
                c1.metric("Min Score", min(stats["scores"]))
                c2.metric("Median Score",
                          sorted(stats["scores"])[len(stats["scores"]) // 2])
                c3.metric("Max Score", max(stats["scores"]))

            # Round-by-round expected points
            st.subheader("Round-by-Round Expected Points")
            rd_totals = defaultdict(float)
            for outcome, _ in precomputed:
                for g in range(63):
                    if bracket[g] == outcome[g]:
                        rd_totals[game_round[g]] += game_points[g]
            n = len(precomputed)
            games_per_round = {"R1": 32, "R2": 16, "S16": 8, "E8": 4,
                               "F4": 2, "Championship": 1}
            rd_rows = []
            for rd in ROUND_NAMES:
                avg = rd_totals.get(rd, 0) / n
                mx = SCORING[rd] * games_per_round[rd]
                rd_rows.append({
                    "Round": rd,
                    "Avg Points": f"{avg:.0f}",
                    "Max Possible": mx,
                    "Hit Rate": f"{avg / mx:.0%}" if mx else "\u2014",
                })
            st.dataframe(rd_rows, use_container_width=True, hide_index=True)

    # ==================================================================
    # TAB 3: LEVERAGE TABLE
    # ==================================================================
    with tabs[2]:
        st.subheader("Leverage Table \u2014 All Teams x Rounds")
        st.caption("Leverage = Blended Prob / Public Pick %. "
                   "Values >1.3 are undervalued by the public; <0.8 are overvalued.")

        lev_rows = []
        for team in sorted(gen_probs.keys()):
            if gen_probs.get(team, {}).get("R1", 0) < 0.01:
                continue
            row = {"Team": fmt_seed(team), "Region": TEAM_REGION.get(team, "")}
            for rd in STANDARD_ROUNDS:
                our_p = gen_probs.get(team, {}).get(rd, 0)
                pub_p = gen_public.get(team, {}).get(rd, 0)
                if our_p > 0.001 and pub_p > 0.001:
                    row[rd] = round(our_p / pub_p, 2)
                else:
                    row[rd] = None
            lev_rows.append(row)
        df_lev = pd.DataFrame(lev_rows)
        st.dataframe(df_lev, use_container_width=True, hide_index=True)

    # ==================================================================
    # TAB 4: WHAT-IF (flip a pick)
    # ==================================================================
    with tabs[3]:
        st.subheader("What-If Analysis")
        st.caption("See how flipping a single game pick affects your bracket.")

        if not precomputed:
            st.info("No simulation data. Click **Generate** to enable What-If.")
        else:
            # Build game descriptions
            game_descs = []
            for g in range(63):
                if g < 32:
                    ta, tb = r1_matchups[g]
                else:
                    fa, fb = feeder_games[g]
                    ta, tb = bracket[fa], bracket[fb]
                pick = bracket[g]
                alt = tb if pick == ta else ta
                rd = game_round[g]
                game_descs.append({
                    "idx": g, "rd": rd,
                    "ta": ta, "tb": tb,
                    "pick": pick, "alt": alt,
                    "label": (f"Game {g+1} ({rd}): "
                              f"{fmt_seed(ta)} vs {fmt_seed(tb)} "
                              f"\u2014 picked {pick}"),
                })

            selected = st.selectbox(
                "Select a game to flip",
                range(len(game_descs)),
                format_func=lambda i: game_descs[i]["label"],
            )

            gd = game_descs[selected]
            st.markdown(f"**Current:** {fmt_seed(gd['pick'])}  \u2192  "
                        f"**Flip to:** {fmt_seed(gd['alt'])}")

            feeds_into = build_feeds_into(game_tree)
            flipped = flip_game(bracket, gd["idx"], game_tree, gen_probs,
                                feeds_into)

            if flipped is not None:
                fl_stats = compute_stats(flipped, precomputed, game_tree, fs)
                existing_payouts = [0.0] * len(precomputed)
                fl_ev = compute_kelly_ev(
                    flipped, precomputed, game_tree, fs,
                    pool_info["payout"], existing_payouts, wealth_base,
                )

                mc1, mc2, mc3, mc4 = st.columns(4)
                mc1.metric("Avg Score", f"{fl_stats['avg_score']:.0f}",
                           delta=f"{fl_stats['avg_score'] - stats['avg_score']:+.1f}")
                mc2.metric("Avg Percentile", f"{fl_stats['avg_pct']:.0f}th",
                           delta=f"{fl_stats['avg_pct'] - stats['avg_pct']:+.1f}")
                mc3.metric("Win Rate", f"{fl_stats['win_pct']:.1f}%",
                           delta=f"{fl_stats['win_pct'] - stats['win_pct']:+.2f}%")
                mc4.metric("Kelly EV", f"{fl_ev:.4f}",
                           delta=f"{fl_ev - kelly_ev:+.4f}")

                # Show cascading changes
                changes = []
                for i in range(63):
                    if flipped[i] != bracket[i]:
                        changes.append(
                            f"- Game {i+1} ({game_round[i]}): "
                            f"{bracket[i]} \u2192 **{flipped[i]}**"
                        )
                if len(changes) > 1:
                    st.markdown("**Cascading changes:**")
                    st.markdown("\n".join(changes))

                if st.button("Apply this flip"):
                    updated = list(brackets)
                    updated[sel] = (list(flipped), pool_info, fl_ev)
                    st.session_state["brackets"] = updated
                    st.rerun()
            else:
                st.info("This game cannot be flipped.")

    # ==================================================================
    # TAB 5: PORTFOLIO (only with multiple brackets)
    # ==================================================================
    if len(brackets) > 1 and len(tabs) > 4:
        with tabs[4]:
            st.subheader("Portfolio Overview")
            port_rows = []
            for i, (b, p, kev) in enumerate(brackets):
                d = bracket_to_display(b, game_tree)
                port_rows.append({
                    "#": i + 1,
                    "Pool": p["name"],
                    "Champion": fmt_seed(b[62]),
                    "Final Four": ", ".join(fmt_seed(t) for t in d["F4"]),
                    "Kelly EV": f"{kev:.4f}",
                })
            st.dataframe(port_rows, use_container_width=True, hide_index=True)

            # Champion diversity
            st.subheader("Champion Diversity")
            champ_counts = defaultdict(int)
            for b, _, _ in brackets:
                champ_counts[b[62]] += 1
            div_data = pd.DataFrame([
                {"Champion": fmt_seed(t), "Brackets": c}
                for t, c in sorted(champ_counts.items(), key=lambda x: -x[1])
            ])
            st.dataframe(div_data, use_container_width=True, hide_index=True)

            # Final Four exposure
            st.subheader("Final Four Exposure")
            ff_counts = defaultdict(int)
            for b, _, _ in brackets:
                for g in [56, 57, 58, 59]:
                    ff_counts[b[g]] += 1
            ff_data = pd.DataFrame([
                {"Team": fmt_seed(t), "Region": TEAM_REGION.get(t, ""),
                 "Appearances": c}
                for t, c in sorted(ff_counts.items(), key=lambda x: -x[1])
            ])
            st.dataframe(ff_data, use_container_width=True, hide_index=True)

    # New bracket / reset button
    st.divider()
    if st.button("Reset (new bracket)"):
        for key in ["brackets", "precomputed", "gen_probs", "gen_public",
                     "gen_params"]:
            st.session_state.pop(key, None)
        st.rerun()
