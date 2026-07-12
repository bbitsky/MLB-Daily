"""mlb_summary.py -- Reusable "why / why-not bet" daily summary generator.

Produces the end-of-run markdown summary in the format the operator prefers
(established 2026-07-05): lead with THE pick(s), a tight why-it's-the-pick
paragraph (including why it's sized that way), an "everything else filtered out"
list with a reason per game, a parlay note, and caveats.

Both the automated path (mlb_daily.py) and the nightly-fallback build scripts
(build_julyN.py) call `build_daily_summary(...)` so the shape is identical every
day and never depends on hand-writing it.
"""
from __future__ import annotations

# Park factor at/above which starter-ERA edges are treated as a variance trap
# (Coors lesson, July 2 2026). Mirrors mlb_edge.park_discount threshold.
PARK_TRAP_PF = 1.28


def _ml(ml):
    if ml is None:
        return "—"
    return f"+{ml}" if ml > 0 else f"{ml}"


def _best_side(g):
    """Return the side ('away'/'home') the model favors and its metrics."""
    a_edge = g.get("away_edge", 0.0) or 0.0
    h_edge = g.get("home_edge", 0.0) or 0.0
    side = "away" if a_edge >= h_edge else "home"
    return side, {
        "team": g[f"{side}_team"],
        "opp": g["home_team"] if side == "away" else g["away_team"],
        "ml": g.get(f"{side}_ml"),
        "prob": g.get(f"{side}_prob", 0.5),
        "impl": g.get(f"{side}_implied", 0.5),
        "edge": g.get(f"{side}_edge", 0.0) or 0.0,
        "conv": g.get(f"{side}_conv", "NO PLAY"),
        "units": g.get(f"{side}_units", 0.0) or 0.0,
        "pros": g.get(f"{side}_pros", []),
        "cons": g.get(f"{side}_cons", []),
    }


def _matchup_line(g):
    return (f"{g.get('away_starter','TBD')} ({g.get('away_era', float('nan')):.2f}) "
            f"vs {g.get('home_starter','TBD')} ({g.get('home_era', float('nan')):.2f})")


def _play_sides(picks):
    """All (game, side, metrics) with units > 0, ranked by edge desc."""
    out = []
    for g in picks:
        for side in ("away", "home"):
            if (g.get(f"{side}_units", 0.0) or 0.0) > 0:
                out.append((g, side, {
                    "team": g[f"{side}_team"],
                    "opp": g["home_team"] if side == "away" else g["away_team"],
                    "ml": g.get(f"{side}_ml"),
                    "prob": g.get(f"{side}_prob", 0.5),
                    "impl": g.get(f"{side}_implied", 0.5),
                    "edge": g.get(f"{side}_edge", 0.0) or 0.0,
                    "conv": g.get(f"{side}_conv", ""),
                    "units": g.get(f"{side}_units", 0.0),
                    "pros": g.get(f"{side}_pros", []),
                    "cons": g.get(f"{side}_cons", []),
                }))
    out.sort(key=lambda t: t[2]["edge"], reverse=True)
    return out


def _filter_reason(g):
    """Classify why a no-play game is a no-play. Returns (category, detail)."""
    pf = g.get("park_factor", 1.0) or 1.0
    venue = g.get("venue", "")
    flags = g.get("flags", []) or []
    side, m = _best_side(g)

    if pf >= PARK_TRAP_PF:
        return ("PARK", f"Park-variance discount ({venue}, PF {pf:.2f}): starter-ERA "
                        f"edges are unreliable here (July-2 Coors lesson). Skip.")
    if flags:
        return ("FLAG", f"{flags[0]} — the form/matchup flag voids the paper edge. "
                        f"Monitor, no bet.")
    # Fairly-priced correct side vs a genuinely conflicting/absent edge
    if 0.0 <= m["edge"] < 0.02:
        if m["ml"] is not None and m["ml"] < 0:
            return ("CHALK", f"Correct side ({m['team']} {_ml(m['ml'])}) but the price "
                             f"already prices the ~{m['prob']:.0%} read. Parlay anchor at "
                             f"most, not a standalone bet.")
        return ("FAIR", f"Model ~{m['prob']:.0%} vs {_ml(m['ml'])} implied {m['impl']:.0%} "
                        f"— roughly fair. No edge, pass.")
    return ("PASS", "Conflicting or absent edge — no clean read. Pass.")


def build_daily_summary(picks, today, record=None, parlays=None,
                        model_source="ERA-differential + win% formula fallback "
                                     "(trained XGBoost unavailable)",
                        extra_caveats=None):
    """Return the preferred why/why-not markdown summary for the day's slate."""
    L = []
    L.append(f"## Why / Why-Not Bet — {today}")
    L.append("")

    plays = _play_sides(picks)

    # 1. Lead with THE pick(s)
    if plays:
        for g, side, m in plays:
            L.append(f"**{m['team']} {_ml(m['ml'])} vs {m['opp']} — {m['conv']} "
                     f"({m['units']}u)**  ·  model {m['prob']:.1%} vs {m['impl']:.1%} "
                     f"implied · edge {m['edge']:+.1%}")
            why = "; ".join(m["pros"][:3]) if m["pros"] else _matchup_line(g)
            sizing = ("Sized down — " + "; ".join(m["cons"][:2])) if m["cons"] else ""
            para = f"{why}. {sizing}".strip()
            if not para.endswith("."):
                para += "."
            L.append("")
            L.append(para)
            L.append("")
    else:
        L.append("**No qualifying edge today.** Nothing clears the value threshold; "
                 "the disciplined play is no bet.")
        L.append("")

    # 2. Everything else filtered out
    filtered = [g for g in picks
                if not ((g.get("away_units", 0) or 0) > 0 or (g.get("home_units", 0) or 0) > 0)]
    if filtered:
        L.append("**Everything else got filtered out:**")
        L.append("")
        for g in filtered:
            cat, detail = _filter_reason(g)
            L.append(f"- **{g['away_team']} @ {g['home_team']}** ({cat}) — {detail} "
                     f"[{_matchup_line(g)}]")
        L.append("")

    # 3. Parlay note
    if parlays:
        L.append(f"**Parlay:** {len(parlays)} qualifying combo(s) — see parlay section.")
    else:
        n_plays = len(plays)
        if n_plays <= 1:
            L.append("**Parlay:** None — one edge (or none), discipline favors the "
                     "single straight over manufacturing a multi-leg.")
        else:
            L.append("**Parlay:** No multi-leg cleared the EV threshold; straights only.")
    L.append("")

    # 4. Caveats
    caveats = [f"Model: {model_source}.",
               "Lines move — confirm the price is still live before staking."]
    if extra_caveats:
        caveats.extend(extra_caveats)
    L.append("**Caveats:** " + " ".join(caveats))
    L.append("")

    return "\n".join(L)


def write_daily_summary(picks, today, out_dir=".", **kw):
    """Build the summary and append/write it to mlb_report_{today}.md. Returns path."""
    import os
    md = build_daily_summary(picks, today, **kw)
    path = os.path.join(str(out_dir), f"mlb_report_{today}.md")
    # Append the summary block if the report already exists, else create it.
    mode = "a" if os.path.exists(path) else "w"
    with open(path, mode, encoding="utf-8") as f:
        if mode == "a":
            f.write("\n\n---\n\n")
        f.write(md)
    return path


if __name__ == "__main__":
    # Smoke test with a minimal synthetic slate.
    demo = [
        {"away_team": "Brewers", "home_team": "Diamondbacks",
         "away_ml": -124, "home_ml": 104, "venue": "Chase Field", "park_factor": 1.00,
         "away_starter": "B. Sproat", "home_starter": "E. Rodriguez",
         "away_era": 4.70, "home_era": 3.20,
         "away_prob": 0.435, "home_prob": 0.565, "away_implied": 0.554, "home_implied": 0.490,
         "away_edge": -0.119, "home_edge": 0.074,
         "home_conv": "MED-HIGH", "home_units": 0.5, "away_units": 0.0,
         "home_pros": ["E-Rod (2.21/3.20 modeled) is the far better arm at home",
                       "+104 plus-money on the superior starter"],
         "home_cons": ["numberFire leans Milwaukee on team strength",
                       "E-Rod 3.98 FIP hints at regression"], "flags": []},
        {"away_team": "Giants", "home_team": "Rockies",
         "away_ml": -124, "home_ml": 107, "venue": "Coors Field", "park_factor": 1.35,
         "away_starter": "T. Mahle", "home_starter": "T. Gordon",
         "away_era": 5.67, "home_era": 5.50,
         "away_prob": 0.49, "home_prob": 0.51, "away_implied": 0.554, "home_implied": 0.483,
         "away_edge": -0.064, "home_edge": 0.027,
         "away_units": 0.0, "home_units": 0.0, "flags": []},
        {"away_team": "Mets", "home_team": "Braves",
         "away_ml": 154, "home_ml": -184, "venue": "Truist Park", "park_factor": 1.02,
         "away_starter": "N. McLean", "home_starter": "M. Perez",
         "away_era": 5.00, "home_era": 3.27,
         "away_prob": 0.45, "home_prob": 0.55, "away_implied": 0.394, "home_implied": 0.648,
         "away_edge": 0.056, "home_edge": -0.098,
         "away_units": 0.0, "home_units": 0.0,
         "flags": ["McLean 4.01 season ERA hides 6.92/5.49 FIP since May — form collapse"]},
    ]
    print(build_daily_summary(demo, "2026-07-05"))
