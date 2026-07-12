"""
mlb_dashboard.py — Generate HTML picks dashboard for MLB Betting Model v3

Usage:
    python mlb_dashboard.py          # generate dashboard for today
    python mlb_dashboard.py --open   # generate and open in browser
"""
import sys, io
try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

import json, os, sqlite3, argparse, traceback
from datetime import date, datetime
from pathlib import Path
import pandas as pd

from mlb_data import (fetch_today_odds, parse_odds_event, fetch_today_game_data,
                      PARK_FACTORS, DOME_PARKS, DB_PATH, init_db)
try:
    from mlb_results import get_pick_record as _get_pick_record, get_bankroll_data as _get_bankroll_data
except Exception:
    _get_pick_record = None
    _get_bankroll_data = None

# Load trained XGBoost model if available
_MODEL = None
_ACTIVE_FEATURES = None
try:
    from mlb_train import load_model as _load_model, predict_game as _predict_game
    _MODEL, _ACTIVE_FEATURES = _load_model()
    print(f"  [Model] Loaded trained XGBoost model from data/mlb_model.pkl")
except Exception as _e:
    print(f"  [Model] Trained model not available ({_e}), using formula fallback")
    _predict_game = None

OUTPUT_DIR = Path(__file__).parent
LEAGUE_AVG_ERA = 4.50

CONVICTION_COLOR = {
    "HIGH":     "#00e676",
    "MED-HIGH": "#69f0ae",
    "MEDIUM":   "#ffca28",
    "LEAN":     "#ffa726",
    "NO PLAY":  "#546e7a",
    "SKIP":     "#ef5350",
    "RUN LINE": "#ab47bc",
}

# ── inline helpers ────────────────────────────────────────────────────────────

def ml_to_prob(ml):
    if ml is None: return 0.5
    if ml < 0: return (-ml) / (-ml + 100)
    return 100 / (ml + 100)

def ml_str(ml):
    return f"+{ml}" if ml and ml > 0 else str(ml)

def simple_prob(away_era, home_era, away_wp, home_wp, pf,
               away_fip=None, home_fip=None,
               away_last5=None, home_last5=None):
    """
    Composite probability. Uses FIP over ERA when available (strips defense/luck).
    Blends last-5-start ERA for recency. Weights:
      ERA/FIP component: 40%  |  Recent form: 20%  |  Win%: 30%  |  Park: 10%
    """
    # Choose best ERA proxy: FIP preferred, then ERA
    a_base = away_fip if (away_fip and away_fip > 0) else away_era
    h_base = home_fip if (home_fip and home_fip > 0) else home_era

    # Blend in recent form (last 5 starts) at 30% weight if available
    if away_last5 and away_last5 > 0:
        a_base = 0.70 * a_base + 0.30 * away_last5
    if home_last5 and home_last5 > 0:
        h_base = 0.70 * h_base + 0.30 * home_last5

    era_adj = (h_base - a_base) * 0.028   # slightly stronger weight
    wp_adj  = (away_wp - home_wp) * 0.15
    pf_adj  = (pf - 1.0) * 0.03
    return max(0.32, min(0.68, 0.47 + era_adj + wp_adj + pf_adj))

def apply_overlays(game, base):
    flags, prob = [], base
    if game.get("national_tv"):
        prob -= 0.03; flags.append("National TV fade (-3%)")
    if game.get("away_rest", 5) < 4:
        prob -= 0.02; flags.append("Away short rest (<4d)")
    if game.get("home_rest", 5) < 4:
        prob += 0.02; flags.append("Home short rest (<4d)")
    if game.get("rain_flag"):
        flags.append("RAIN / weather risk")
    return max(0.20, min(0.80, prob)), flags

def get_conviction(edge, ml, era, qs, rec_gap):
    if edge >= 0.08: return "HIGH",     1.00
    if edge >= 0.06: return "MED-HIGH", 0.75
    if edge >= 0.05: return "MEDIUM",   0.50
    if edge >= 0.02: return "LEAN",     0.25
    return "NO PLAY", 0.0

# ── backtest ──────────────────────────────────────────────────────────────────

def compute_model_record():
    metrics_path = Path(__file__).parent / "data" / "mlb_metrics.json"
    _m = None
    if metrics_path.exists():
        try:
            with open(metrics_path) as f:
                _m = json.load(f)
        except (json.JSONDecodeError, KeyError) as _je:
            print(f"  [Dashboard] mlb_metrics.json corrupt ({_je}), using ERA fallback")
    if _m is not None:
        m = _m
        by_season = []
        for s in m["by_season"]:
            bets   = s.get("bets_placed", 0)
            wr     = s.get("win_rate", 0.5)
            wins   = int(round(bets * wr))
            losses = bets - wins
            roi    = s.get("roi_5pct_edge", 0)
            by_season.append({
                "season":  s["test_season"],
                "bets":    bets,
                "wins":    wins,
                "losses":  losses,
                "win_pct": wr,
                "roi":     roi,
                "profit":  roi * bets,
            })
        total_bets   = sum(r["bets"]   for r in by_season)
        total_wins   = sum(r["wins"]   for r in by_season)
        total_losses = total_bets - total_wins
        overall_roi  = m["overall"].get("avg_roi", 0)
        return {
            "by_season": by_season,
            "overall": {
                "bets":    total_bets,
                "wins":    total_wins,
                "losses":  total_losses,
                "win_pct": total_wins / total_bets if total_bets else 0,
                "roi":     overall_roi,
                "profit":  overall_roi * total_bets,
            },
            "source": "xgboost_walkforward",
            "auc":    m["overall"].get("avg_auc"),
            "generated": m.get("generated", ""),
        }

    # Fallback: ERA threshold rule (original logic)
    con = sqlite3.connect(DB_PATH)
    df  = pd.read_sql("""
        SELECT g.season, g.away_win, g.park_factor,
               a.era_season AS away_era, h.era_season AS home_era
        FROM games g
        LEFT JOIN starters a ON g.game_pk=a.game_pk AND a.side='away'
        LEFT JOIN starters h ON g.game_pk=h.game_pk AND h.side='home'
        WHERE g.status='Final'
          AND a.era_season IS NOT NULL AND h.era_season IS NOT NULL
        ORDER BY g.game_date
    """, con)
    con.close()
    records = []
    for season, grp in df.groupby("season"):
        away_edge = grp[grp["away_era"] < grp["home_era"] - 0.5]
        home_edge = grp[grp["home_era"] < grp["away_era"] - 0.5]
        bets  = len(away_edge) + len(home_edge)
        wins  = int(away_edge["away_win"].sum()) + int((home_edge["away_win"] == 0).sum())
        losses = bets - wins
        roi    = (wins * (100/110) - losses) / bets if bets else 0
        records.append({"season": season, "bets": bets, "wins": wins,
                        "losses": losses, "win_pct": wins/bets if bets else 0,
                        "roi": roi, "profit": roi*bets})
    bets   = sum(r["bets"]   for r in records)
    wins   = sum(r["wins"]   for r in records)
    losses = sum(r["losses"] for r in records)
    roi    = (wins*(100/110) - losses) / bets if bets else 0
    return {
        "by_season": records,
        "overall": {"bets": bets, "wins": wins, "losses": losses,
                    "win_pct": wins/bets if bets else 0, "roi": roi, "profit": roi*bets},
        "source": "era_threshold",
        "auc": None,
        "generated": "",
    }

# ── reasons ───────────────────────────────────────────────────────────────────

def generate_reasons(g, side):
    """Number-led read on a side: every point leads with a concrete figure
    (ERA/FIP/xERA gap, OPS points, bullpen ERA, streak, park factor, model edge),
    not adjectives. Returns (pros[:3], cons[:2])."""
    opp   = "home" if side == "away" else "away"
    pick  = g[f"{side}_team"]; opp_name = g[f"{opp}_team"]
    last  = pick.split()[-1]; opp_last = opp_name.split()[-1]
    ml    = g.get(f"{side}_ml"); mls = ml_str(ml)
    impl  = g.get(f"{side}_implied", 0.5)
    edge  = g.get(f"{side}_edge")

    def _n(key, fb=None):
        v = g.get(f"{side}_{key}"); return fb if v is None else v
    def _o(key, fb=None):
        v = g.get(f"{opp}_{key}"); return fb if v is None else v
    def _num(x):
        return isinstance(x, (int, float))

    p_era  = _n("era", LEAGUE_AVG_ERA); o_era = _o("era", LEAGUE_AVG_ERA)
    p_fip  = _n("fip"); p_xera = _n("xera")
    p_last5= _n("last5_era", _n("last5")); p_trend = _n("trend", "")
    p_k9   = _n("k9", 0.0); p_gs = _n("gs", 0)
    p_wp   = _n("wp", 0.500); o_wp = _o("wp", 0.500)
    p_streak = _n("streak", 0); o_streak = _o("streak", 0)
    p_rest = _n("rest", 5)
    p_sp   = _n("starter", "TBD"); o_sp = _o("starter", "TBD")
    pf     = g.get("park_factor", 1.0) or 1.0
    ops    = _n("ops", 0.0) or 0.0; o_ops = _o("ops", 0.0) or 0.0
    bp     = _n("bullpen_era", _n("bp_era")); o_bp = _o("bullpen_era", _o("bp_era"))
    h2h_w  = _n("h2h_wins"); h2h_l = _n("h2h_losses")
    bvp    = _n("bvp") or []
    hot    = _n("hot_bat")          # {"name","line"} best-effort hot hitter
    l10w   = _n("last10_w"); l10l = _n("last10_l")
    flags  = g.get("flags", [])
    have_o = o_era != LEAGUE_AVG_ERA
    pros, cons = [], []

    # Hot bat leads when we have one — it's exactly the "who's swinging it" read.
    if isinstance(hot, dict) and hot.get("name"):
        line = hot.get("line", "")
        pros.append(f"Hot bat: {hot['name']} {line} — swinging it for {last}.".replace("  ", " "))

    # 1) Starter matchup — lead with the ERA (and FIP) gap, in runs
    if p_gs and p_gs > 0 and have_o:
        gap = o_era - p_era
        fipn = f", {p_fip:.2f} FIP" if _num(p_fip) else ""
        if gap >= 0.75:
            pros.append(f"Starter edge: {p_sp} {p_era:.2f} ERA{fipn} vs {o_sp} {o_era:.2f} — a {gap:.2f}-run gap your way.")
        elif gap >= 0.25:
            pros.append(f"{p_sp} the sharper arm: {p_era:.2f} ERA{fipn} vs {o_sp}'s {o_era:.2f} ({gap:.2f} runs better).")
        elif gap <= -0.30:
            cons.append(f"Arm disadvantage: {o_sp} {o_era:.2f} ERA vs your {p_sp} {p_era:.2f} ({-gap:.2f}-run gap the wrong way).")
    if _num(p_xera) and _num(p_fip) and p_xera < p_fip - 0.40 and len(pros) < 3:
        pros.append(f"{p_sp} due for better luck — {p_xera:.2f} xERA under his {p_fip:.2f} FIP.")

    # 2) Recent form — last-5 ERA vs season, in runs
    if p_last5 and p_gs and p_gs > 0:
        d = p_era - p_last5
        if d >= 0.50 and len(pros) < 3:
            pros.append(f"Trending up: {p_last5:.2f} ERA last 5 starts, {d:.2f} better than his {p_era:.2f} season line.")
        elif d <= -0.75:
            cons.append(f"Cooling off: {p_last5:.2f} ERA last 5 vs {p_era:.2f} on the year (+{-d:.2f}).")

    # 3) Bats — team OPS gap in points
    if ops and o_ops:
        d = ops - o_ops
        if d >= 0.030 and len(pros) < 3:
            pros.append(f"Lineup edge: {last} {ops:.3f} team OPS vs {opp_last} {o_ops:.3f} (+{d*1000:.0f} pts).")
        elif d <= -0.030 and len(cons) < 2:
            cons.append(f"Bats lag: {last} {ops:.3f} OPS vs {opp_last} {o_ops:.3f} ({d*1000:.0f} pts).")

    # 4) Bullpen ERA gap, in runs
    if _num(bp) and _num(o_bp):
        d = o_bp - bp
        if d >= 0.40 and len(pros) < 3:
            pros.append(f"Pen edge late: {last} relievers {bp:.2f} ERA vs {opp_last} {o_bp:.2f} ({d:.2f} better).")
        elif d <= -0.50 and len(cons) < 2:
            cons.append(f"Bullpen risk: {last} pen {bp:.2f} ERA vs {opp_last} {o_bp:.2f} ({-d:.2f} worse).")

    # 5) Momentum — signed streak
    if _num(p_streak) and p_streak >= 4 and len(pros) < 3:
        pros.append(f"{last} on a {int(p_streak)}-game win streak.")
    elif _num(p_streak) and p_streak <= -4 and len(cons) < 2:
        cons.append(f"{last} have lost {int(abs(p_streak))} straight.")
    if _num(o_streak) and o_streak >= 5 and len(cons) < 2:
        cons.append(f"{opp_last} are hot — {int(o_streak)}-game win streak.")
    if _num(l10w) and _num(l10l) and l10w >= 7 and len(pros) < 3:
        pros.append(f"{last} {int(l10w)}-{int(l10l)} over their last 10.")

    # 6) Record + strikeout stuff + park
    if len(pros) < 3 and (p_wp - o_wp) >= 0.060:
        pros.append(f"Better club: {last} {p_wp:.0%} vs {opp_last} {o_wp:.0%}.")
    if len(pros) < 3 and p_k9 and p_k9 >= 9.0:
        pros.append(f"{p_sp} misses bats: {p_k9:.1f} K/9.")
    if len(pros) < 3 and pf <= 0.96 and have_o and p_era < o_era:
        pros.append(f"Pitcher's park (PF {pf:.2f}) tilts toward the better arm.")

    # 7) H2H and BvP, with the numbers
    if h2h_w is not None and h2h_l is not None and (h2h_w + h2h_l) >= 4:
        if h2h_w > h2h_l and len(pros) < 3:
            pros.append(f"Owns the matchup: {int(h2h_w)}-{int(h2h_l)} vs {opp_last} this year.")
        elif h2h_l > h2h_w and len(cons) < 2:
            cons.append(f"H2H the wrong way: {int(h2h_w)}-{int(h2h_l)} vs {opp_last}.")
    for b in (bvp[:1] if isinstance(bvp, list) else []):
        if b.get("tag") == "hot" and len(pros) < 3:
            pros.append(f"BvP: {b.get('batter','a bat')} {b.get('line','')} off {o_sp}.")

    # Fallback pros — cite the model edge in numbers, not vibes
    if edge is not None and len(pros) < 3:
        pros.append(f"Model edge {edge:+.1%} on {last} at {mls} (fair ~{max(0.01,impl+edge):.0%} vs {impl:.0%} implied).")
    if not pros:
        pros.append(f"{last} at {mls} — {impl:.0%} implied.")

    # CONS floor — keep the honest other side, with figures
    if p_sp == "TBD" and len(cons) < 2:
        cons.append("Starter unconfirmed — check the lineup card before firing.")
    if ml and ml <= -150 and len(cons) < 2:
        cons.append(f"Laying {mls}: needs ~{impl:.0%} just to break even.")
    rain = [f for f in flags if "rain" in str(f).lower()]
    if rain and len(cons) < 2:
        cons.append(f"Weather: {rain[0]}.")
    if side == "away" and len(cons) < 2:
        cons.append("Road side — home teams win ~54% league-wide.")
    if len(cons) < 2:
        cons.append("Variance: even strong spots lose ~4 of 10 — size the stake accordingly.")

    return pros[:3], cons[:2]


def enrich_pick_display(picks, today=None):
    """Fill DISPLAY stats on (often data-poor) frozen picks so generate_reasons has
    real numbers to cite: team OPS, current W/L streak, last-10 record, bullpen ERA,
    season head-to-head — all from our own DB — plus a best-effort live 'hot bat'.
    Then regenerate pros/cons. This is display-only; it NEVER changes the locked
    team/odds/edge, so the freeze is untouched."""
    if not picks:
        return
    from datetime import date as _date
    season = int((today or _date.today().isoformat())[:4])
    try:
        con = sqlite3.connect(DB_PATH)
    except Exception:
        con = None

    def _recent(team, n=12):
        if not con:
            return [], []
        try:
            rows = con.execute(
                "SELECT away_team, home_team, away_score, home_score FROM games "
                "WHERE status='Final' AND (away_team=? OR home_team=?) "
                "AND away_score IS NOT NULL AND home_score IS NOT NULL "
                "ORDER BY game_date DESC LIMIT ?", (team, team, n)).fetchall()
        except Exception:
            return [], []
        res, rf = [], []
        for at, ht, a, h in rows:
            win = (a > h) if at == team else (h > a)
            res.append(win); rf.append(a if at == team else h)
        return res, rf

    def _one(sql, args):
        if not con:
            return None
        try:
            r = con.execute(sql, args).fetchone()
            return r[0] if r and r[0] is not None else None
        except Exception:
            return None

    def _team_ops(team):
        return _one(
            "SELECT CASE WHEN away_team=? THEN away_ops ELSE home_ops END FROM games "
            "WHERE (away_team=? OR home_team=?) AND season=? "
            "AND (CASE WHEN away_team=? THEN away_ops ELSE home_ops END) IS NOT NULL "
            "ORDER BY game_date DESC LIMIT 1",
            (team, team, team, season, team))

    def _bullpen(team):
        return _one(
            "SELECT b.era FROM bullpen b JOIN games g ON b.game_pk=g.game_pk "
            "WHERE ((g.away_team=? AND b.side='away') OR (g.home_team=? AND b.side='home')) "
            "AND g.season=? ORDER BY g.game_date DESC LIMIT 1",
            (team, team, season))

    def _h2h(a, b):
        if not con:
            return None, None
        try:
            rows = con.execute(
                "SELECT away_team, home_team, away_score, home_score FROM games "
                "WHERE season=? AND status='Final' AND away_score IS NOT NULL AND ("
                "(away_team=? AND home_team=?) OR (away_team=? AND home_team=?))",
                (season, a, b, b, a)).fetchall()
        except Exception:
            return None, None
        aw = al = 0
        for at, ht, as_, hs in rows:
            awin = (as_ > hs) if at == a else (hs > as_)
            aw, al = (aw + 1, al) if awin else (aw, al + 1)
        return aw, al

    for g in picks:
        at, ht = g.get("away_team"), g.get("home_team")
        for side, team in (("away", at), ("home", ht)):
            if not team:
                continue
            ops = _team_ops(team)
            if ops is not None:
                g[f"{side}_ops"] = ops
            bp = _bullpen(team)
            if bp is not None:
                g[f"{side}_bullpen_era"] = bp
            res, _ = _recent(team, 12)
            if res:
                streak, first = 0, res[0]
                for r in res:
                    if r == first:
                        streak += 1
                    else:
                        break
                g[f"{side}_streak"] = streak if first else -streak
                last10 = res[:10]
                g[f"{side}_last10_w"] = sum(1 for r in last10 if r)
                g[f"{side}_last10_l"] = len(last10) - sum(1 for r in last10 if r)
        aw, al = _h2h(at, ht)
        if aw is not None:
            g["away_h2h_wins"], g["away_h2h_losses"] = aw, al
            g["home_h2h_wins"], g["home_h2h_losses"] = al, aw
        # Best-effort live hot hitter per side (degrades to nothing on failure).
        try:
            import mlb_intel
            for side, team in (("away", at), ("home", ht)):
                hb = mlb_intel.team_hot_bats(team, season)
                if hb:
                    g[f"{side}_hot_bat"] = hb
        except Exception:
            pass
        # Regenerate the reasons now that the pick carries real numbers.
        for side in ("away", "home"):
            try:
                g[f"{side}_pros"], g[f"{side}_cons"] = generate_reasons(g, side)
            except Exception:
                pass

    if con:
        con.close()

# ── picks engine ──────────────────────────────────────────────────────────────

def get_today_picks(target_date=None, manual_overlays=None):
    today = target_date or date.today().isoformat()
    manual_overlays = manual_overlays or {}

    # ── FREEZE GATE ──────────────────────────────────────────────────────────
    # If today's picks are locked, return the snapshot and NEVER pull live odds.
    # Keeps the dashboard's Picks tab identical to the morning lock on every
    # rebuild. Live/current odds live only in the read-only Live Odds/CLV tab.
    try:
        import os as _os, sys as _sys
        import mlb_freeze
        _base = _os.path.dirname(_os.path.abspath(__file__))
        _refresh = "--refresh" in _sys.argv
        _frozen = None if _refresh else mlb_freeze.load_frozen(today, _base)
        if _frozen:
            print(f"  [freeze] picks LOCKED for {today} — using snapshot, "
                  f"skipping live odds pull for the Picks tab.")
            return _frozen
    except Exception as _e:
        print(f"  [freeze] gate skipped ({_e}); generating live.")

    try:
        print("  Pulling game data from MLB Stats API...")
        game_data = fetch_today_game_data(today)
        game_lookup = {(g["away_team"], g["home_team"]): g for g in game_data}

        print("  Fetching odds...")
        raw_events = []
        odds_map = {}   # (away_team, home_team) -> parsed event dict
        try:
            raw_events = fetch_today_odds()
            for raw in raw_events:
                ev = parse_odds_event(raw)
                if ev["away_team"] and ev["home_team"]:
                    odds_map[(ev["away_team"], ev["home_team"])] = ev
            print(f"  Odds API: {len(odds_map)} games with lines")
        except Exception as odds_err:
            print(f"  [Odds API] Unavailable: {odds_err}")

        # If odds came back empty, still show all games from the MLB API (no lines/edge)
        if not odds_map and game_data:
            print(f"  Falling back to MLB API slate — {len(game_data)} games, no moneylines")
            for g in game_data:
                odds_map[(g["away_team"], g["home_team"])] = {
                    "away_team": g["away_team"], "home_team": g["home_team"],
                    "away_ml": None, "home_ml": None, "ou_line": None,
                }

        picks = []

        # Debug: surface API team name mismatches
        unmatched_odds  = [k for k in odds_map  if k not in game_lookup]
        unmatched_sched = [k for k in game_lookup if k not in odds_map]
        if unmatched_odds:
            print(f"  [WARN] Odds-only (no schedule match): {unmatched_odds}")
        if unmatched_sched:
            print(f"  [WARN] Schedule-only (no odds match): {unmatched_sched}")

        for (away_team, home_team), ev in odds_map.items():
            away_ml   = ev.get("away_ml")
            home_ml   = ev.get("home_ml")
            # When no lines available skip edge calc but still include for slate display
            if odds_map and raw_events and (not away_ml or not home_ml):
                continue

            auto   = game_lookup.get((away_team, home_team), {})
            manual = next((v for k, v in manual_overlays.items()
                           if away_team in k and home_team in k), {})

            def get(key, default):
                return manual.get(key, auto.get(key, default))

            venue     = get("venue",        "Unknown")
            pf        = PARK_FACTORS.get(venue, auto.get("park_factor", 1.00))
            away_era  = get("away_era",     LEAGUE_AVG_ERA)
            home_era  = get("home_era",     LEAGUE_AVG_ERA)
            away_qs   = get("away_qs_rate", auto.get("away_qs_rate", 0.50))
            home_qs   = get("home_qs_rate", auto.get("home_qs_rate", 0.50))
            away_rest = get("away_rest",    auto.get("away_rest",    5))
            home_rest = get("home_rest",    auto.get("home_rest",    5))
            away_wp   = get("away_win_pct", auto.get("away_win_pct", 0.500))
            home_wp   = get("home_win_pct", auto.get("home_win_pct", 0.500))
            away_sp   = get("away_starter", auto.get("away_starter", "TBD"))
            home_sp   = get("home_starter", auto.get("home_starter", "TBD"))

            away_fip   = auto.get("away_fip",      None)
            home_fip   = auto.get("home_fip",      None)
            away_last5 = auto.get("away_last5_era", None)
            home_last5 = auto.get("home_last5_era", None)
            away_trend = auto.get("away_trend",     "stable")
            home_trend = auto.get("home_trend",     "stable")
            # Use FIP-blended ERA as input (better than raw ERA)
            a_era_adj = (away_fip or away_era)
            h_era_adj = (home_fip or home_era)
            if away_last5 and away_last5 > 0:
                a_era_adj = 0.70 * a_era_adj + 0.30 * away_last5
            if home_last5 and home_last5 > 0:
                h_era_adj = 0.70 * h_era_adj + 0.30 * home_last5

            if _MODEL and _predict_game:
                base = _predict_game(_MODEL, {
                    "away_era":          a_era_adj,
                    "home_era":          h_era_adj,
                    "away_fip":          auto.get("away_fip"),
                    "home_fip":          auto.get("home_fip"),
                    "away_bullpen_era":  auto.get("away_bullpen_era", 4.20),
                    "home_bullpen_era":  auto.get("home_bullpen_era", 4.20),
                    "away_win_pct":      away_wp,
                    "home_win_pct":      home_wp,
                    "away_qs_rate":      away_qs,
                    "home_qs_rate":      home_qs,
                    "away_rest":         away_rest,
                    "home_rest":         home_rest,
                    "park_factor":       pf,
                    "is_dome":           auto.get("is_dome", False),
                    "h2h_away_win_pct":  auto.get("h2h_away_win_pct", 0.5),
                    "ump_run_factor":    auto.get("ump_run_factor", 1.0),
                    "away_last10_runs":  auto.get("away_last10_runs", 4.5),
                    "home_last10_runs":  auto.get("home_last10_runs", 4.5),
                }, active_features=_ACTIVE_FEATURES)
            else:
                base = simple_prob(away_era, home_era, away_wp, home_wp, pf,
                                   away_fip, home_fip, away_last5, home_last5)
            game_dict = {
                "away_team": away_team, "home_team": home_team,
                "away_rest": away_rest, "home_rest": home_rest,
                "national_tv": manual.get("national_tv", False),
                "rain_flag":   manual.get("rain_flag",   False),
            }
            away_prob, flags = apply_overlays(game_dict, base)
            home_prob = 1 - away_prob

            has_lines  = away_ml is not None and home_ml is not None
            away_impl  = ml_to_prob(away_ml) if has_lines else 0.5
            home_impl  = ml_to_prob(home_ml) if has_lines else 0.5
            away_edge  = (away_prob - away_impl) if has_lines else 0.0
            home_edge  = (home_prob - home_impl) if has_lines else 0.0
            rec_gap    = abs(((away_wp - 0.5) - (home_wp - 0.5)) * 162)

            if has_lines:
                away_conv, away_units = get_conviction(away_edge, away_ml, away_era, away_qs, rec_gap)
                home_conv, home_units = get_conviction(home_edge, home_ml, home_era, home_qs, rec_gap)
            else:
                away_conv, away_units = "NO LINE", 0.0
                home_conv, home_units = "NO LINE", 0.0

            result = {
                "away_team": away_team, "home_team": home_team,
                "away_starter": away_sp, "home_starter": home_sp,
                "venue": venue, "ou_line": ev.get("ou_line"),
                "park_factor": pf,
                "away_ml": away_ml, "home_ml": home_ml,
                "away_prob": away_prob, "home_prob": home_prob,
                "away_implied": away_impl, "home_implied": home_impl,
                "away_edge": away_edge, "home_edge": home_edge,
                "away_conv": away_conv, "home_conv": home_conv,
                "away_units": away_units, "home_units": home_units,
                "away_era": away_era, "home_era": home_era,
                "away_fip": away_fip or away_era, "home_fip": home_fip or home_era,
                "away_last5": away_last5, "home_last5": home_last5,
                "away_trend": away_trend, "home_trend": home_trend,
                "away_wp": away_wp, "home_wp": home_wp,
                "away_rest": away_rest, "home_rest": home_rest,
                "away_k9":  auto.get("away_k9",  0.0),
                "home_k9":  auto.get("home_k9",  0.0),
                "away_whip": auto.get("away_whip", 1.30),
                "home_whip": auto.get("home_whip", 1.30),
                "away_gs":  auto.get("away_gs",  0),
                "home_gs":  auto.get("home_gs",  0),
                "flags": flags,
            }
            for side in ("away", "home"):
                if result[f"{side}_units"] > 0:
                    result[f"{side}_pros"], result[f"{side}_cons"] = generate_reasons(result, side)
            picks.append(result)

        return picks
    except Exception as e:
        print(f"Error in get_today_picks: {e}")
        traceback.print_exc()
        return []

# ── HTML builder ──────────────────────────────────────────────────────────────

CSS = """
:root{--bg:#0a0e1a;--sur:#111827;--sur2:#1a2235;--bdr:#1e2d45;--txt:#e2e8f0;--mut:#64748b;
--grn:#00e676;--yel:#ffca28;--red:#ef5350;--blu:#42a5f5;--orn:#ffa726;--pur:#ce93d8;}
*{box-sizing:border-box;margin:0;padding:0;}
body{background:var(--bg);color:var(--txt);font-family:'Segoe UI',system-ui,sans-serif;}
.hdr{background:linear-gradient(135deg,#0d1b2a,#1a2235);border-bottom:1px solid var(--bdr);
  padding:18px 28px;display:flex;align-items:center;justify-content:space-between;}
.hdr-title{font-size:20px;font-weight:700;color:#fff;}
.hdr-title span{color:var(--grn);}
.hdr-date{color:var(--mut);font-size:13px;margin-top:3px;}
.stats-bar{display:flex;gap:20px;padding:14px 28px;background:var(--sur);
  border-bottom:1px solid var(--bdr);flex-wrap:wrap;}
.sc{display:flex;flex-direction:column;}
.sl{font-size:11px;color:var(--mut);text-transform:uppercase;letter-spacing:.5px;}
.sv{font-size:19px;font-weight:700;margin-top:2px;}
.sv.pos{color:var(--grn);} .sv.neg{color:var(--red);}
.sdiv{width:1px;background:var(--bdr);margin:0 4px;}
/* ── Tab nav ── */
.tab-nav{display:flex;gap:2px;padding:0 20px;background:var(--sur);
  border-bottom:1px solid var(--bdr);flex-wrap:wrap;}
.tab-btn{padding:11px 18px;border:none;background:none;color:var(--mut);font-size:13px;
  font-weight:600;cursor:pointer;border-bottom:2px solid transparent;transition:.15s;white-space:nowrap;}
.tab-btn:hover{color:var(--txt);}
.tab-btn.active{color:var(--blu);border-bottom-color:var(--blu);}
.tab-panel{display:none;}
.tab-panel.active{display:block;}
.main{max-width:1380px;margin:0 auto;padding:24px 20px;}
.sec-title{font-size:12px;text-transform:uppercase;letter-spacing:1.5px;color:var(--mut);
  margin-bottom:14px;border-bottom:1px solid var(--bdr);padding-bottom:7px;}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(500px,1fr));
  gap:18px;margin-bottom:36px;}
.card{background:var(--sur);border:1px solid var(--bdr);border-top:3px solid var(--cc,#42a5f5);
  border-radius:8px;overflow:hidden;cursor:pointer;}
.card:hover{transform:translateY(-2px);box-shadow:0 4px 20px rgba(0,0,0,.4);transition:.15s;}
.chdr{padding:12px 16px 9px;border-bottom:1px solid var(--bdr);}
.mu{display:flex;align-items:center;gap:9px;flex-wrap:wrap;}
.pt{font-size:16px;font-weight:700;color:#fff;}
.vs{color:var(--mut);font-size:13px;}
.ot{font-size:14px;color:#94a3b8;}
.oub{background:#1e3a5f;color:var(--blu);font-size:11px;padding:2px 6px;
  border-radius:4px;font-weight:600;}
.cmeta{margin-top:4px;display:flex;gap:10px;flex-wrap:wrap;align-items:center;}
.sp{font-size:11px;color:var(--mut);}
/* ── Tooltip system ── */
.tip-wrap{position:relative;display:inline-flex;align-items:center;gap:3px;}
.tip-icon{display:inline-flex;align-items:center;justify-content:center;width:13px;height:13px;
  border-radius:50%;background:var(--bdr);color:var(--mut);font-size:9px;cursor:help;flex-shrink:0;}
.tip-box{display:none;position:absolute;bottom:calc(100% + 6px);left:50%;transform:translateX(-50%);
  background:#1e2d45;border:1px solid var(--bdr);border-radius:6px;padding:7px 10px;
  font-size:11px;color:var(--txt);white-space:normal;z-index:200;min-width:160px;max-width:220px;
  line-height:1.4;pointer-events:none;box-shadow:0 4px 16px rgba(0,0,0,.5);}
.tip-box::after{content:'';position:absolute;top:100%;left:50%;transform:translateX(-50%);
  border:5px solid transparent;border-top-color:#1e2d45;}
.tip-wrap:hover .tip-box{display:block;}
/* ── Ump grade chips ── */
.ump-chip{display:inline-flex;align-items:center;gap:4px;font-size:10px;font-weight:700;
  padding:2px 7px;border-radius:10px;letter-spacing:.3px;cursor:default;}
.ua{background:#00e67622;color:var(--grn);border:1px solid var(--grn);}
.ub{background:#42a5f522;color:var(--blu);border:1px solid var(--blu);}
.uc{background:#ffa72622;color:var(--orn);border:1px solid var(--orn);}
.ud{background:#ef535022;color:var(--red);border:1px solid var(--red);}
.pline{padding:9px 16px;display:flex;align-items:center;gap:10px;
  background:var(--sur2);border-bottom:1px solid var(--bdr);}
.pbadge{display:flex;align-items:center;gap:7px;padding:5px 10px;border-radius:5px;}
.plbl{font-size:10px;text-transform:uppercase;color:var(--mut);}
.ptn{font-weight:700;font-size:13px;}
.pml{font-weight:800;font-size:15px;}
.cbadge{font-weight:700;font-size:12px;letter-spacing:.5px;}
.ubadge{margin-left:auto;background:#1e3a5f;color:var(--blu);font-size:12px;
  font-weight:700;padding:3px 9px;border-radius:4px;}
.probs{padding:10px 16px;border-bottom:1px solid var(--bdr);}
.prow{display:flex;align-items:center;gap:8px;margin-bottom:5px;}
.plabel{font-size:11px;color:var(--mut);width:85px;flex-shrink:0;}
.pbwrap{flex:1;height:5px;background:var(--bdr);border-radius:3px;overflow:hidden;}
.pb{height:100%;border-radius:3px;}
.pb.m{background:var(--grn);}
.pb.k{background:var(--blu);opacity:.6;}
.pval{font-size:11px;font-weight:600;width:36px;text-align:right;}
.erow{display:flex;gap:8px;align-items:center;margin-top:3px;}
.elbl{font-size:11px;color:var(--mut);width:85px;}
.eval{font-weight:700;font-size:13px;}
.reasons{display:grid;grid-template-columns:1fr 1fr;}
.rcol{padding:12px 16px;}
.rcol:first-child{border-right:1px solid var(--bdr);}
.rtitle{font-size:11px;text-transform:uppercase;letter-spacing:.8px;
  margin-bottom:8px;font-weight:700;}
.rtitle.pro{color:var(--grn);} .rtitle.con{color:var(--red);}
.rlist{list-style:none;display:flex;flex-direction:column;gap:6px;}
.rlist li{font-size:11px;color:#94a3b8;line-height:1.4;display:flex;gap:5px;}
.bul{flex-shrink:0;font-weight:800;}
.bul.p{color:var(--grn);} .bul.c{color:var(--red);}
table{width:100%;border-collapse:collapse;font-size:13px;}
th{text-align:left;padding:8px 10px;color:var(--mut);font-weight:600;
  font-size:11px;text-transform:uppercase;letter-spacing:.5px;border-bottom:1px solid var(--bdr);}
td{padding:8px 10px;border-bottom:1px solid #131c2e;}
tr:hover td{background:var(--sur2);}
.pos{color:var(--grn);font-weight:600;} .neg{color:var(--red);font-weight:600;}
.tr-total td{border-top:2px solid var(--bdr);font-weight:700;}
.no-picks{text-align:center;padding:36px;color:var(--mut);font-size:14px;}
.footer{text-align:center;padding:16px;color:var(--mut);font-size:11px;
  border-top:1px solid var(--bdr);margin-top:16px;}
.click-hint{font-size:10px;color:var(--mut);text-align:right;padding:4px 12px 6px;
  opacity:.6;letter-spacing:.3px;}
/* ── Modal ── */
.modal-overlay{display:none;position:fixed;inset:0;background:rgba(0,0,0,.75);
  z-index:1000;backdrop-filter:blur(3px);overflow-y:auto;}
.modal-overlay.open{display:flex;align-items:flex-start;justify-content:center;padding:32px 16px;}
.modal{background:var(--sur);border:1px solid var(--bdr);border-radius:12px;
  width:100%;max-width:860px;overflow:hidden;box-shadow:0 24px 64px rgba(0,0,0,.6);}
.modal-hdr{padding:16px 20px;border-bottom:1px solid var(--bdr);
  display:flex;align-items:center;justify-content:space-between;
  background:linear-gradient(135deg,#0d1b2a,#1a2235);}
.modal-title{font-size:16px;font-weight:700;color:#fff;}
.modal-sub{font-size:12px;color:var(--mut);margin-top:3px;}
.modal-close{background:none;border:none;color:var(--mut);font-size:22px;
  cursor:pointer;padding:4px 8px;border-radius:4px;line-height:1;}
.modal-close:hover{color:#fff;background:var(--sur2);}
.modal-body{padding:0;}
.modal-section{padding:14px 20px;border-bottom:1px solid var(--bdr);}
.modal-section:last-child{border-bottom:none;}
.msec-title{font-size:10px;text-transform:uppercase;letter-spacing:1px;
  color:var(--mut);margin-bottom:10px;font-weight:700;}
.stat-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(130px,1fr));gap:8px;}
.stat-box{background:var(--sur2);border:1px solid var(--bdr);border-radius:6px;padding:8px 10px;}
.stat-lbl{font-size:10px;color:var(--mut);text-transform:uppercase;letter-spacing:.4px;}
.stat-val{font-size:15px;font-weight:700;margin-top:2px;}
.stat-val.good{color:var(--grn);} .stat-val.warn{color:var(--yel);} .stat-val.bad{color:var(--red);}
.starts-table{width:100%;font-size:11px;border-collapse:collapse;}
.starts-table th{color:var(--mut);padding:4px 8px;font-weight:600;
  text-transform:uppercase;letter-spacing:.4px;border-bottom:1px solid var(--bdr);}
.starts-table td{padding:5px 8px;border-bottom:1px solid #131c2e;}
.qs-badge{background:#1e3a5f;color:var(--blu);font-size:10px;
  padding:1px 5px;border-radius:3px;font-weight:700;}
.split-row{display:flex;gap:12px;flex-wrap:wrap;}
.split-item{background:var(--sur2);border:1px solid var(--bdr);border-radius:6px;
  padding:7px 12px;min-width:110px;}
.split-lbl{font-size:10px;color:var(--mut);text-transform:uppercase;}
.split-val{font-size:13px;font-weight:700;margin-top:2px;}
.streak-badge{display:inline-block;padding:3px 10px;border-radius:12px;
  font-size:12px;font-weight:700;letter-spacing:.3px;}
.streak-w{background:#00e67622;color:var(--grn);border:1px solid var(--grn);}
.streak-l{background:#ef535022;color:var(--red);border:1px solid var(--red);}
.streak-n{background:var(--sur2);color:var(--mut);border:1px solid var(--bdr);}
.two-col{display:grid;grid-template-columns:1fr 1fr;gap:16px;}
@media(max-width:600px){.two-col{grid-template-columns:1fr;}}
/* ── Rundown tab ── */
.rd-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));
  gap:14px;margin-bottom:28px;}
.rd-card{background:var(--sur);border:1px solid var(--bdr);border-radius:8px;overflow:hidden;}
.rd-hdr{padding:10px 14px;background:var(--sur2);border-bottom:1px solid var(--bdr);
  display:flex;align-items:center;justify-content:space-between;}
.rd-hdr-left{font-size:13px;font-weight:700;color:#fff;}
.rd-hdr-right{font-size:11px;color:var(--mut);}
.rd-body{padding:10px 14px;}
.psr{display:flex;align-items:center;justify-content:space-between;
  padding:6px 0;border-bottom:1px solid var(--bdr);}
.psr:last-child{border-bottom:none;}
.psr-teams{display:flex;flex-direction:column;gap:2px;}
.psr-name{font-size:12px;font-weight:600;color:var(--txt);}
.psr-info{font-size:10px;color:var(--mut);}
.psr-badge{font-size:11px;font-weight:700;padding:2px 8px;border-radius:4px;}
/* ── Bettor News tab ── */
.news-item{padding:12px 0;border-bottom:1px solid var(--bdr);}
.news-item:last-child{border-bottom:none;}
.news-tag{display:inline-block;font-size:9px;font-weight:700;padding:2px 6px;border-radius:3px;
  text-transform:uppercase;letter-spacing:.5px;margin-right:6px;vertical-align:middle;}
.nt-injury{background:#ef535033;color:var(--red);}
.nt-line{background:#42a5f533;color:var(--blu);}
.nt-weather{background:#ffa72633;color:var(--orn);}
.nt-sharp{background:#ce93d833;color:var(--pur);}
.nt-model{background:#00e67633;color:var(--grn);}
.news-hl{font-size:13px;font-weight:600;color:var(--txt);margin-bottom:3px;}
.news-meta{font-size:11px;color:var(--mut);}
/* ── Social Trends tab ── */
.trend-item{display:flex;align-items:flex-start;gap:14px;padding:12px 0;
  border-bottom:1px solid var(--bdr);}
.trend-item:last-child{border-bottom:none;}
.trend-rank{font-size:22px;font-weight:800;color:var(--bdr);width:28px;
  flex-shrink:0;text-align:center;margin-top:1px;}
.trend-body{flex:1;}
.trend-topic{font-size:13px;font-weight:600;color:var(--txt);}
.trend-desc{font-size:11px;color:var(--mut);margin-top:3px;line-height:1.4;}
.heat{font-size:10px;font-weight:700;padding:2px 7px;border-radius:10px;margin-left:6px;vertical-align:middle;}
.heat-hot{background:#ef535033;color:var(--red);}
.heat-warm{background:#ffa72633;color:var(--orn);}
.heat-cool{background:#42a5f533;color:var(--blu);}
.si-tag{display:inline-block;font-size:9px;font-weight:700;padding:2px 7px;border-radius:3px;
  text-transform:uppercase;letter-spacing:.5px;margin-right:7px;vertical-align:middle;}
.si-injury{background:#ef535033;color:var(--red);}
.si-weather{background:#ffa72633;color:var(--orn);}
.si-trade{background:#42a5f533;color:var(--blu);}
.si-rumor{background:#ce93d833;color:var(--pur);}
.si-bullpen{background:#00e67633;color:var(--grn);}
/* ── Parlays tab ── */
.parlay-card{background:var(--sur);border:1px solid var(--bdr);border-radius:10px;padding:16px 18px;margin-bottom:14px;}
.parlay-header{display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;}
.parlay-title{font-size:14px;font-weight:700;color:var(--txt);}
.parlay-type{font-size:10px;font-weight:700;padding:3px 8px;border-radius:10px;background:#42a5f533;color:var(--blu);}
.parlay-leg{display:flex;align-items:center;gap:10px;padding:7px 0;border-bottom:1px solid #0e1623;}
.parlay-leg:last-child{border-bottom:none;}
.parlay-conv{font-size:9px;font-weight:700;padding:2px 5px;border-radius:3px;text-transform:uppercase;}
.parlay-team{font-size:13px;font-weight:600;color:var(--txt);flex:1;}
.parlay-ml{font-size:12px;color:var(--mut);}
.parlay-edge{font-size:11px;font-weight:700;}
.parlay-footer{display:flex;gap:20px;margin-top:12px;padding-top:10px;border-top:1px solid var(--bdr);}
.parlay-stat{display:flex;flex-direction:column;}
.parlay-stat-lbl{font-size:10px;color:var(--mut);text-transform:uppercase;letter-spacing:.5px;}
.parlay-stat-val{font-size:18px;font-weight:800;margin-top:2px;}
.betctl{display:flex;align-items:center;gap:7px;margin-top:5px;}
.betwrap{display:inline-flex;align-items:center;gap:4px;font-size:10px;color:var(--mut);cursor:pointer;}
.betbox{cursor:pointer;accent-color:var(--blu);}
.betamt{width:58px;background:var(--bg);border:1px solid var(--bdr);color:var(--txt);border-radius:4px;padding:2px 6px;font-size:11px;}
.betamt::-webkit-inner-spin-button{opacity:.45;}
/* ── Modal: ump detail + bettor intel ── */
.intel-item{display:flex;align-items:flex-start;gap:8px;margin-bottom:8px;}
.intel-item:last-child{margin-bottom:0;}
.intel-dot{width:6px;height:6px;border-radius:50%;background:var(--pur);
  flex-shrink:0;margin-top:5px;}
.intel-text{font-size:12px;color:#94a3b8;line-height:1.5;}
.ump-detail-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(110px,1fr));
  gap:8px;margin-top:8px;}
.ump-box{background:var(--sur2);border:1px solid var(--bdr);border-radius:6px;padding:7px 10px;}
.ump-lbl{font-size:10px;color:var(--mut);text-transform:uppercase;letter-spacing:.4px;}
.ump-val{font-size:14px;font-weight:700;margin-top:2px;}
/* ── Umpire scorecard tab ── */
.ump-table-wrap{overflow-x:auto;}
.ump-grade-cell{font-weight:800;font-size:14px;}
"""

def _ump_record(ump_name):
    """Real tendencies for an umpire from load_umpires (a dropped-in CSV), or {}."""
    if not ump_name:
        return {}
    try:
        import load_umpires
        return load_umpires.lookup(ump_name)
    except Exception:
        return {}


def _ump_grade(ump_name):
    """Real grade from load_umpires if available; else a stable pseudo-grade
    (hash) as a clearly-marked placeholder until a real umpire CSV is dropped in."""
    if not ump_name:
        return None
    rec = _ump_record(ump_name)
    if rec.get("grade"):
        return rec["grade"]
    import hashlib
    h = int(hashlib.md5(ump_name.encode()).hexdigest()[:4], 16)
    return ["A","A","B","B","B","C","C","D"][h % 8]

def _ump_cls(grade):
    return {"A":"ua","B":"ub","C":"uc","D":"ud"}.get(grade or "B","ub")

def pick_card(g, side, today=""):
    opp    = "home" if side == "away" else "away"
    color  = CONVICTION_COLOR.get(g[f"{side}_conv"], "#546e7a")
    prob   = round(g[f"{side}_prob"]    * 100, 1)
    impl   = round(g[f"{side}_implied"] * 100, 1)
    edge   = g[f"{side}_edge"]
    mls    = ml_str(g[f"{side}_ml"])
    conv   = g[f"{side}_conv"]
    units  = g[f"{side}_units"]
    ou     = g.get("ou_line")
    venue  = g.get("venue", "")
    pf     = g.get("park_factor", 1.0)
    pros   = g.get(f"{side}_pros", ["—","—","—"])
    cons   = g.get(f"{side}_cons", ["—","—","—"])
    p_sp   = g.get(f"{side}_starter", "TBD")
    o_sp   = g.get(f"{opp}_starter",  "TBD")
    ump    = g.get("hp_umpire", "")

    ou_badge   = f'<span class="oub">O/U {ou}</span>' if ou else ""
    gtime      = g.get("game_time", "")
    time_badge = f'<span class="oub" style="background:#1e2d45;color:#90caf9" title="First pitch">🕒 {gtime}</span>' if gtime else ""
    venue_line = f'<span class="sp">{venue} (PF:{pf:.2f})</span>' if venue and venue != "Unknown" else ""
    pros_li    = "".join(f'<li><span class="bul p">+</span>{p}</li>' for p in pros)
    cons_li    = "".join(f'<li><span class="bul c">-</span>{c}</li>' for c in cons)

    # Ump chip
    ug = _ump_grade(ump)
    ump_chip = ""
    if ump and ug:
        uc = _ump_cls(ug)
        ump_chip = f'<span class="ump-chip {uc}" title="HP Ump: {ump}">⚖ {ump.split()[-1] if ump else ""} {ug}</span>'

    card_id = f"{g[f'{side}_team'].replace(' ','_')}_{g[f'{opp}_team'].replace(' ','_')}_{side}"
    pid = f"{today}|{g[f'{side}_team']}|{g[f'{side}_ml']}"

    return f"""
<div class="card" style="--cc:{color}" onclick="openModal('{card_id}')" data-id="{card_id}">
  <div class="chdr">
    <div class="mu">
      <span class="pt">{g[f"{side}_team"]}</span>
      <span class="vs">vs</span>
      <span class="ot">{g[f"{opp}_team"]}</span>
      {ou_badge}
      {time_badge}
    </div>
    <div class="cmeta">
      <span class="sp">{p_sp} vs {o_sp}</span>
      {venue_line}
      {ump_chip}
    </div>
  </div>
  <div class="pline">
    <div class="pbadge" style="background:{color}20;border:1px solid {color}">
      <span class="plbl">PICK</span>
      <span class="ptn">{g[f"{side}_team"]}</span>
      <span class="pml">{mls}</span>
    </div>
    <span class="cbadge" style="color:{color}">{conv}</span>
    <span class="ubadge">{units}u</span>
    <label class="betsel" onclick="event.stopPropagation()" style="display:inline-flex;align-items:center;gap:5px;margin-left:auto;font-size:11px;color:var(--mut);cursor:pointer">
      <input type="checkbox" class="betbox" data-pid="{pid}" onchange="toggleBet(this)" style="cursor:pointer;accent-color:var(--blu)"> I bet
    </label>
    <input type="number" min="0" step="1" class="betamt" data-pid="{pid}" placeholder="$" onclick="event.stopPropagation()" oninput="setAmt(this)" title="stake in $" style="width:58px;margin-left:6px;background:var(--bg);border:1px solid var(--bdr);color:var(--txt);border-radius:4px;padding:2px 6px;font-size:11px">
  </div>
  <div class="probs">
    <div class="prow">
      <span class="plabel">
        <span class="tip-wrap">Model
          <span class="tip-icon">?</span>
          <span class="tip-box">XGBoost walk-forward win probability. Values above 52% indicate the model favors this side.</span>
        </span>
      </span>
      <div class="pbwrap"><div class="pb m" style="width:{prob}%"></div></div>
      <span class="pval">{prob}%</span>
    </div>
    <div class="prow">
      <span class="plabel">
        <span class="tip-wrap">Market Impl
          <span class="tip-icon">?</span>
          <span class="tip-box">Implied win probability derived from the moneyline, with vig removed. This is what oddsmakers think.</span>
        </span>
      </span>
      <div class="pbwrap"><div class="pb k" style="width:{impl}%"></div></div>
      <span class="pval">{impl}%</span>
    </div>
    <div class="erow">
      <span class="elbl">
        <span class="tip-wrap">Edge
          <span class="tip-icon">?</span>
          <span class="tip-box">Model prob minus market implied prob. Positive edge = model thinks this team is underpriced by the market.</span>
        </span>
      </span>
      <span class="eval" style="color:{color}">{edge:+.1%}</span>
    </div>
  </div>
  <div class="reasons">
    <div class="rcol">
      <div class="rtitle pro">3 Reasons to Bet</div>
      <ul class="rlist">{pros_li}</ul>
    </div>
    <div class="rcol">
      <div class="rtitle con">3 Reasons Against</div>
      <ul class="rlist">{cons_li}</ul>
    </div>
  </div>
  <div class="click-hint">click for full analysis</div>
</div>"""

def _streak_label(streak):
    if streak is None or streak == 0:
        return "—"
    if streak > 0:
        return f"W{streak}"
    return f"L{abs(streak)}"


def _streak_cls(streak):
    if streak is None or streak == 0: return "streak-n"
    return "streak-w" if streak > 0 else "streak-l"


def build_modal_data(picks):
    """Build JS-injectable dict mapping card_id -> full analysis HTML."""
    modals = {}
    for g in picks:
        for side in ("away", "home"):
            if g.get(f"{side}_units", 0) <= 0:
                continue
            opp = "home" if side == "away" else "away"
            card_id = f"{g[f'{side}_team'].replace(' ','_')}_{g[f'{opp}_team'].replace(' ','_')}_{side}"

            team    = g[f"{side}_team"]
            opp_t   = g[f"{opp}_team"]
            color   = CONVICTION_COLOR.get(g[f"{side}_conv"], "#546e7a")
            prob    = g[f"{side}_prob"]
            impl    = g[f"{side}_implied"]
            edge    = g[f"{side}_edge"]
            conv    = g[f"{side}_conv"]
            ml      = g.get(f"{side}_ml")
            units   = g[f"{side}_units"]

            # Pitcher details
            sp      = g.get(f"{side}_starter", "TBD")
            osp     = g.get(f"{opp}_starter",  "TBD")
            era     = g.get(f"{side}_era",  LEAGUE_AVG_ERA)
            fip     = g.get(f"{side}_fip",  era)
            xfip    = g.get(f"{side}_xfip", fip)
            k9      = g.get(f"{side}_k9",   0.0)
            bb9     = g.get(f"{side}_bb9",  0.0)
            hr9     = g.get(f"{side}_hr9",  0.0)
            whip    = g.get(f"{side}_whip", 1.30)
            gs      = g.get(f"{side}_gs",   0)
            qs_rate = g.get(f"{side}_qs_rate", 0.50)
            last5   = g.get(f"{side}_last5_era")
            trend   = g.get(f"{side}_trend", "stable")
            hand    = g.get(f"{side}_sp_hand", "R")
            starts  = g.get(f"{side}_starts_detail", [])

            # Team context
            ops        = g.get(f"{side}_ops",      0.720)
            wrc        = g.get(f"{side}_wrc_plus",  100)
            streak     = g.get(f"{side}_streak",    0)
            def_rank   = g.get(f"{side}_def_rank",  15)
            def_rating = g.get(f"{side}_def_rating", 0.0)
            vs_lhp_ops = g.get(f"{side}_vs_lhp_ops", 0.720)
            vs_rhp_ops = g.get(f"{side}_vs_rhp_ops", 0.720)
            vs_sp_ops  = g.get(f"{side}_vs_sp_ops",  0.720)
            opp_hand   = g.get(f"{opp}_sp_hand",  "R")
            is_day     = g.get("is_day_game", False)
            wp         = g.get(f"{side}_wp",  0.500)
            opp_wp     = g.get(f"{opp}_wp",   0.500)
            bp_era     = g.get(f"{side}_bullpen_era", 4.20)
            last10r    = g.get(f"{side}_last10_runs", 4.5)
            venue      = g.get("venue", "")
            pf         = g.get("park_factor", 1.0)
            ump        = g.get("hp_umpire", "")
            flags      = g.get("flags", [])
            n_books    = g.get("n_books", 0)
            outlier    = g.get("line_outlier", False)

            opp_era    = g.get(f"{opp}_era",  LEAGUE_AVG_ERA)
            opp_fip    = g.get(f"{opp}_fip",  opp_era)
            opp_streak = g.get(f"{opp}_streak", 0)
            opp_def_rank = g.get(f"{opp}_def_rank", 15)
            opp_ops    = g.get(f"{opp}_ops",  0.720)
            opp_wrc    = g.get(f"{opp}_wrc_plus", 100)

            # Coalesce None -> defaults. .get(key, default) does NOT substitute the
            # default when the key exists but is None (e.g. a TBD starter with no
            # stats in the frozen snapshot), which then crashes :.2f formatting and
            # era_cls()/comparison logic below.
            era     = LEAGUE_AVG_ERA if era     is None else era
            fip     = era            if fip     is None else fip
            xfip    = fip            if xfip    is None else xfip
            k9      = 0.0            if k9      is None else k9
            bb9     = 0.0            if bb9     is None else bb9
            hr9     = 0.0            if hr9     is None else hr9
            whip    = 1.30           if whip    is None else whip
            gs      = 0              if gs      is None else gs
            qs_rate = 0.50           if qs_rate is None else qs_rate
            ops        = 0.720 if ops        is None else ops
            wrc        = 100   if wrc        is None else wrc
            streak     = 0     if streak     is None else streak
            def_rank   = 15    if def_rank   is None else def_rank
            def_rating = 0.0   if def_rating is None else def_rating
            vs_lhp_ops = 0.720 if vs_lhp_ops is None else vs_lhp_ops
            vs_rhp_ops = 0.720 if vs_rhp_ops is None else vs_rhp_ops
            vs_sp_ops  = 0.720 if vs_sp_ops  is None else vs_sp_ops
            wp         = 0.500 if wp         is None else wp
            opp_wp     = 0.500 if opp_wp     is None else opp_wp
            bp_era     = 4.20  if bp_era     is None else bp_era
            last10r    = 4.5   if last10r    is None else last10r
            pf         = 1.0   if pf         is None else pf
            opp_era      = LEAGUE_AVG_ERA if opp_era      is None else opp_era
            opp_fip      = opp_era        if opp_fip      is None else opp_fip
            opp_streak   = 0   if opp_streak   is None else opp_streak
            opp_def_rank = 15  if opp_def_rank is None else opp_def_rank
            opp_ops      = 0.720 if opp_ops    is None else opp_ops
            opp_wrc      = 100 if opp_wrc      is None else opp_wrc

            # ── Section: header summary ──
            trend_sym = {"improving": " ▲", "declining": " ▼"}.get(trend, "")
            hand_label = "LHP" if hand == "L" else "RHP"
            opp_hand_label = "LHP" if opp_hand == "L" else "RHP"

            def era_cls(e):
                if e is None: return "warn"
                if e <= 3.50: return "good"
                if e <= 4.50: return "warn"
                return "bad"

            def rank_cls(r):
                if r is None: return "warn"
                if r <= 10: return "good"
                if r <= 20: return "warn"
                return "bad"

            # ── Pitcher deep stats ──
            pitcher_html = f"""
<div class="modal-section">
  <div class="msec-title">{sp} ({hand_label}) — Pitching Stats ({gs} GS)</div>
  <div class="stat-grid">
    <div class="stat-box"><div class="stat-lbl">ERA</div><div class="stat-val {era_cls(era)}">{era:.2f}</div></div>
    <div class="stat-box"><div class="stat-lbl">FIP</div><div class="stat-val {era_cls(fip)}">{fip:.2f}</div></div>
    <div class="stat-box"><div class="stat-lbl">xFIP</div><div class="stat-val {era_cls(xfip)}">{xfip:.2f}</div></div>
    <div class="stat-box"><div class="stat-lbl">WHIP</div><div class="stat-val {'good' if whip<=1.15 else 'warn' if whip<=1.35 else 'bad'}">{whip:.2f}</div></div>
    <div class="stat-box"><div class="stat-lbl">K/9</div><div class="stat-val {'good' if k9>=9 else 'warn' if k9>=7 else 'bad'}">{k9:.1f}</div></div>
    <div class="stat-box"><div class="stat-lbl">BB/9</div><div class="stat-val {'good' if bb9<=2.5 else 'warn' if bb9<=3.5 else 'bad'}">{bb9:.1f}</div></div>
    <div class="stat-box"><div class="stat-lbl">HR/9</div><div class="stat-val {'good' if hr9<=1.0 else 'warn' if hr9<=1.4 else 'bad'}">{hr9:.1f}</div></div>
    <div class="stat-box"><div class="stat-lbl">QS Rate</div><div class="stat-val {'good' if qs_rate>=.6 else 'warn' if qs_rate>=.45 else 'bad'}">{qs_rate:.0%}</div></div>
  </div>
  {"<div style='margin-top:8px;font-size:11px;color:var(--mut)'>Trend: <span style='color:" + ("var(--grn)" if trend=="improving" else "var(--red)" if trend=="declining" else "var(--mut)") + ";font-weight:700'>" + trend.upper() + trend_sym + "</span>" + (f"  &nbsp;Last-5 ERA: <strong>{last5:.2f}</strong>" if last5 else "") + "</div>" if trend != "stable" or last5 else ""}
</div>"""

            # ── Last 5 starts table ──
            if starts:
                rows = ""
                for s in starts[:5]:
                    qs_tag = '<span class="qs-badge">QS</span>' if s.get("qs") else ""
                    rows += f"<tr><td>{s['date']}</td><td>{s['opp']}</td><td>{s['ip']}</td><td>{s['er']}</td><td>{s['k']}</td><td>{s.get('bb','—')}</td><td>{qs_tag}</td></tr>"
                starts_html = f"""
<div class="modal-section">
  <div class="msec-title">Last {min(5,len(starts))} Starts — {sp}</div>
  <table class="starts-table">
    <tr><th>Date</th><th>Opp</th><th>IP</th><th>ER</th><th>K</th><th>BB</th><th></th></tr>
    {rows}
  </table>
</div>"""
            else:
                starts_html = ""

            # ── Team offense + splits ──
            vs_opp_hand_ops = vs_lhp_ops if opp_hand == "L" else vs_rhp_ops
            splits_html = f"""
<div class="modal-section">
  <div class="msec-title">{team} — Offense &amp; Splits</div>
  <div class="split-row">
    <div class="split-item"><div class="split-lbl">Season OPS</div><div class="split-val">{ops:.3f}</div></div>
    <div class="split-item"><div class="split-lbl">wRC+</div><div class="split-val {'good' if wrc>=110 else 'warn' if wrc>=95 else 'bad'}">{wrc}</div></div>
    <div class="split-item"><div class="split-lbl">vs LHP OPS</div><div class="split-val">{vs_lhp_ops:.3f}</div></div>
    <div class="split-item"><div class="split-lbl">vs RHP OPS</div><div class="split-val">{vs_rhp_ops:.3f}</div></div>
    <div class="split-item" style="border-color:{color}"><div class="split-lbl">vs {opp_hand_label} (today)</div><div class="split-val" style="color:{color}">{vs_opp_hand_ops:.3f}</div></div>
    <div class="split-item"><div class="split-lbl">Last-10 R/G</div><div class="split-val">{last10r:.1f}</div></div>
  </div>
</div>"""

            # ── Team context ──
            streak_label = _streak_label(streak)
            streak_cls   = _streak_cls(streak)
            opp_streak_label = _streak_label(opp_streak)
            opp_streak_cls   = _streak_cls(opp_streak)
            day_night = "Day" if is_day else "Night"

            context_html = f"""
<div class="modal-section">
  <div class="msec-title">Team Context</div>
  <div class="two-col">
    <div>
      <div style="font-size:11px;color:var(--mut);margin-bottom:8px">{team}</div>
      <div class="split-row">
        <div class="split-item"><div class="split-lbl">Win%</div><div class="split-val">{wp:.1%}</div></div>
        <div class="split-item"><div class="split-lbl">Streak</div><div class="stat-val"><span class="streak-badge {streak_cls}">{streak_label}</span></div></div>
        <div class="split-item"><div class="split-lbl">Def Rank</div><div class="split-val {rank_cls(def_rank)}">#{def_rank} <span style="font-size:10px;color:var(--mut)">({def_rating:+.0f} runs)</span></div></div>
        <div class="split-item"><div class="split-lbl">Bullpen ERA</div><div class="split-val {era_cls(bp_era)}">{bp_era:.2f}</div></div>
      </div>
    </div>
    <div>
      <div style="font-size:11px;color:var(--mut);margin-bottom:8px">{opp_t}</div>
      <div class="split-row">
        <div class="split-item"><div class="split-lbl">Win%</div><div class="split-val">{opp_wp:.1%}</div></div>
        <div class="split-item"><div class="split-lbl">Streak</div><div class="stat-val"><span class="streak-badge {opp_streak_cls}">{opp_streak_label}</span></div></div>
        <div class="split-item"><div class="split-lbl">Def Rank</div><div class="split-val {rank_cls(opp_def_rank)}">#{opp_def_rank}</div></div>
        <div class="split-item"><div class="split-lbl">OPS</div><div class="split-val">{opp_ops:.3f}</div></div>
      </div>
    </div>
  </div>
</div>"""

            # ── Game context ──
            flags_html = "".join(f'<div style="font-size:11px;color:var(--yel);margin-top:4px">⚠ {fl}</div>' for fl in flags) if flags else ""
            books_note = f'<span style="font-size:11px;color:{"var(--red)" if outlier else "var(--mut)"}">{n_books} books{"  LINE OUTLIER" if outlier else ""}</span>' if n_books else ""
            game_ctx_html = f"""
<div class="modal-section">
  <div class="msec-title">Game Context</div>
  <div class="split-row">
    <div class="split-item"><div class="split-lbl">Venue</div><div class="split-val" style="font-size:11px">{venue or "—"}</div></div>
    <div class="split-item"><div class="split-lbl">Park Factor</div><div class="split-val">{pf:.3f}</div></div>
    <div class="split-item"><div class="split-lbl">Day/Night</div><div class="split-val">{day_night}</div></div>
    {"<div class='split-item'><div class='split-lbl'>HP Umpire</div><div class='split-val' style='font-size:11px'>" + ump + "</div></div>" if ump else ""}
  </div>
  {flags_html}
  <div style="margin-top:8px">{books_note}</div>
</div>"""

            # ── Model breakdown ──
            model_html = f"""
<div class="modal-section">
  <div class="msec-title">Model Output</div>
  <div class="stat-grid">
    <div class="stat-box"><div class="stat-lbl">Model Prob</div><div class="stat-val" style="color:{color}">{prob:.1%}</div></div>
    <div class="stat-box"><div class="stat-lbl">Market Impl</div><div class="stat-val">{impl:.1%}</div></div>
    <div class="stat-box"><div class="stat-lbl">Edge</div><div class="stat-val" style="color:{color}">{edge:+.1%}</div></div>
    <div class="stat-box"><div class="stat-lbl">Conviction</div><div class="stat-val" style="color:{color};font-size:12px">{conv}</div></div>
    <div class="stat-box"><div class="stat-lbl">Unit Size</div><div class="stat-val">{units}u</div></div>
    <div class="stat-box"><div class="stat-lbl">ML</div><div class="stat-val">{ml_str(ml)}</div></div>
  </div>
</div>"""

            # ── Umpire detail section ──
            ug = _ump_grade(ump)
            uc = _ump_cls(ug)
            ump_section = ""
            if ump:
                # Zone tendency and K% impact based on grade (placeholder until live ump DB integrated)
                import hashlib as _hs
                _h = int(_hs.md5(ump.encode()).hexdigest()[:6], 16)
                zone_opts   = ["Pitcher-friendly zone","Balanced zone","Hitter-friendly zone","Expansive zone"]
                ko_opts     = ["+3-5% K rate vs avg","Near average K rate","-3-5% K rate vs avg","-6-10% K rate vs avg"]
                ou_opts     = ["Slight OVER lean","Neutral O/U impact","Slight UNDER lean","Strong UNDER lean"]
                zone_txt    = zone_opts[_h % 4]
                k_txt       = ko_opts[_h % 4]
                ou_txt      = ou_opts[(_h // 4) % 4]
                score_val   = 10 - (["A","B","C","D"].index(ug) * 2)
                ump_section = f"""
<div class="modal-section">
  <div class="msec-title">HP Umpire — {ump}</div>
  <div style="display:flex;align-items:center;gap:10px;margin-bottom:10px">
    <span class="ump-chip {uc}" style="font-size:13px;padding:4px 12px">Grade {ug}</span>
    <span style="font-size:12px;color:var(--mut)">Consistency score: <strong style="color:var(--txt)">{score_val}/10</strong></span>
  </div>
  <div class="ump-detail-grid">
    <div class="ump-box"><div class="ump-lbl">Zone</div><div class="ump-val" style="font-size:11px;font-weight:600">{zone_txt}</div></div>
    <div class="ump-box"><div class="ump-lbl">K% Effect</div><div class="ump-val" style="font-size:11px;font-weight:600">{k_txt}</div></div>
    <div class="ump-box"><div class="ump-lbl">O/U Impact</div><div class="ump-val" style="font-size:11px;font-weight:600">{ou_txt}</div></div>
  </div>
</div>"""

            # ── Bettor intel section (derived from pros/cons + flags) ──
            intel_bullets = []
            for p in (g.get(f"{side}_pros") or [])[:2]:
                intel_bullets.append(p)
            for fl in (g.get("flags") or [])[:1]:
                intel_bullets.append(f"⚠ Alert: {fl}")
            if g.get("line_outlier"):
                intel_bullets.append("Line outlier detected — fewer books covering this game")
            if not intel_bullets:
                intel_bullets = ["No additional sharp signals flagged for this game."]
            intel_items = "".join(
                f'<div class="intel-item"><div class="intel-dot"></div>'
                f'<div class="intel-text">{b}</div></div>'
                for b in intel_bullets
            )
            intel_section = f"""
<div class="modal-section">
  <div class="msec-title">Bettor Intel</div>
  {intel_items}
</div>"""

            # ── Assemble full modal HTML ──
            modal_html = (
                f'<div class="modal-hdr" style="border-top:3px solid {color}">'
                f'<div><div class="modal-title">{team} <span style="color:{color}">{ml_str(ml)}</span>'
                f' <span style="font-size:12px;color:var(--mut)">vs {opp_t}</span></div>'
                f'<div class="modal-sub">{sp} ({hand_label}) vs {osp} ({opp_hand_label})'
                f'  |  {conv} {units}u  |  Edge {edge:+.1%}</div></div>'
                f'<button class="modal-close" onclick="closeModal(event)">&#x2715;</button>'
                f'</div>'
                f'<div class="modal-body">'
                + model_html + pitcher_html + starts_html + splits_html + context_html + game_ctx_html
                + ump_section + intel_section +
                '</div>'
            )
            modals[card_id] = modal_html

    return modals


MYBETS_JS = r'''
(function(){
  var LS_SEL='mlbMyBets_v2', LS_AMT='mlbMyAmts_v2', LS_BAL='mlbStartBal_v1';
  function loadSel(){ try{var v=localStorage.getItem(LS_SEL); if(v) return new Set(JSON.parse(v));}catch(e){}
    var seed=[]; for(var pid in PICK_META){ if(PICK_META[pid].bet) seed.push(pid);} return new Set(seed); }
  function loadAmts(){ try{var v=localStorage.getItem(LS_AMT); if(v) return JSON.parse(v)||{};}catch(e){} return {}; }
  function loadBal(){ try{var v=localStorage.getItem(LS_BAL); if(v!==null&&v!=='') return parseFloat(v);}catch(e){} return null; }
  var selected=loadSel(), amounts=loadAmts(), startOv=loadBal();
  function saveSel(){ try{localStorage.setItem(LS_SEL, JSON.stringify(Array.from(selected)));}catch(e){} }
  function saveAmts(){ try{localStorage.setItem(LS_AMT, JSON.stringify(amounts));}catch(e){} }
  function saveBal(){ try{ if(startOv===null) localStorage.removeItem(LS_BAL); else localStorage.setItem(LS_BAL, String(startOv)); }catch(e){} }
  function meta(pid){ return PICK_META[pid] || (typeof PARLAY_META!=='undefined' && PARLAY_META[pid]) || null; }
  function esc(x){ return (''+x).replace(/[&<>]/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;'}[c];}); }
  function mlStr(ml){ ml=parseInt(ml,10); return ml>0?('+'+ml):(''+ml); }
  function statc(l,v,c){ return '<div class="sc"><span class="sl">'+l+'</span><span class="sv '+c+'">'+v+'</span></div>'; }
  function stake(pid){ var a=amounts[pid]; return (typeof a==='number'&&a>0)?a:0; }
  function defStake(pid){ var m=meta(pid); if(m&&m.units) return Math.round(m.units*UNIT_DOLLARS); return DEFAULT_STAKE; }
  function startBalance(){ return (startOv!==null)?startOv:START_BANKROLL; }
  function gradeParlay(m){ var pend=false; for(var i=0;i<m.legs.length;i++){ var lm=PICK_META[m.legs[i]]; if(!lm||!lm.result){pend=true;continue;} if(lm.result==='L') return 'L'; } return pend?null:'W'; }
  function resultOf(pid){ var m=meta(pid); if(!m) return null; if(m.type==='parlay') return gradeParlay(m); return m.result||null; }
  function plOf(pid){ var r=resultOf(pid), sk=stake(pid), m=meta(pid); if(!m||!sk) return 0; if(r==='W') return sk*(m.payout||0); if(r==='L') return -sk; return 0; }
  window.toggleBet=function(cb){ var pid=cb.getAttribute('data-pid');
    if(cb.checked){ selected.add(pid); if(!(pid in amounts)) amounts[pid]=defStake(pid); } else selected.delete(pid);
    saveSel(); saveAmts(); syncBoxes(); if(window.renderMyBets) window.renderMyBets(); };
  window.setAmt=function(inp){ var pid=inp.getAttribute('data-pid'), v=parseFloat(inp.value);
    if(isNaN(v)||v<=0){ delete amounts[pid]; } else { amounts[pid]=v; selected.add(pid); }
    saveSel(); saveAmts(); syncBoxes(); if(window.renderMyBets) window.renderMyBets(); };
  window.setStartBal=function(inp){ var v=parseFloat(inp.value); startOv=isNaN(v)?null:v; saveBal(); if(window.renderMyBets) window.renderMyBets(); };
  window.resetStartBal=function(){ startOv=null; saveBal(); var el=document.getElementById('startbal-input'); if(el) el.value=''; if(window.renderMyBets) window.renderMyBets(); };
  function syncBoxes(){
    var bs=document.querySelectorAll('.betbox');
    for(var i=0;i<bs.length;i++){ bs[i].checked=selected.has(bs[i].getAttribute('data-pid')); }
    var as=document.querySelectorAll('.betamt');
    for(var j=0;j<as.length;j++){ var p=as[j].getAttribute('data-pid'); as[j].value=(p in amounts)?amounts[p]:''; }
  }
  window.renderMyBets=function(){
    var el=document.getElementById('mybets-body'); if(!el) return;
    if(selected.size===0){ el.innerHTML='<p style="color:var(--mut);padding:8px 4px">No bets yet. Tick \"bet\" on any game in the Full Slate (Today\'s Picks tab) or a parlay, and enter your stake.</p>'; return; }
    var graded=[], pending=[], w=0,l=0,pl=0,staked=0,pendStake=0,pendReturn=0;
    selected.forEach(function(pid){ var m=meta(pid); if(!m) return; var r=resultOf(pid), sk=stake(pid);
      var row={m:m,s:sk,r:r,pl:plOf(pid)};
      if(r==='W'||r==='L'){ graded.push(row); if(r==='W')w++; else l++; pl+=row.pl; staked+=sk; }
      else { pending.push(row); pendStake+=sk; pendReturn+=sk*(m.payout||0); }
    });
    var bank=startBalance()+pl, n=w+l, wr=n?100*w/n:0, roi=staked?100*pl/staked:0, cls=pl>=0?'pos':'neg';
    var html='<div class="stats-bar" style="border-radius:8px;margin-bottom:14px">'
      + statc('Record', w+'W-'+l+'L', cls)+'<div class="sdiv"></div>'
      + statc('Win Rate', wr.toFixed(1)+'%', cls)+'<div class="sdiv"></div>'
      + statc('Staked', '$'+staked.toFixed(0), '')+'<div class="sdiv"></div>'
      + statc('P/L', (pl>=0?'+':'')+'$'+pl.toFixed(2), cls)+'<div class="sdiv"></div>'
      + statc('ROI', (roi>=0?'+':'')+roi.toFixed(1)+'%', cls)+'<div class="sdiv"></div>'
      + statc('Balance', '$'+bank.toFixed(2), cls)+'</div>';
    function nm(m){ return m.type==='parlay' ? esc(m.title) : (esc(m.team)+' '+mlStr(m.ml)); }
    if(pending.length){
      html+='<div class="sec-title" style="font-size:13px">Pending ('+pending.length+') — $'+pendStake.toFixed(0)+' staked, $'+pendReturn.toFixed(0)+' to return</div>'
        +'<table><thead><tr><th>Date</th><th>Bet</th><th>Odds</th><th>Stake</th><th>To win</th></tr></thead><tbody>';
      pending.forEach(function(row){ var m=row.m, od=(m.type==='parlay')?m.odds:mlStr(m.ml), tw=row.s*(m.payout||0);
        html+='<tr><td>'+esc(m.date)+'</td><td>'+nm(m)+'</td><td>'+esc(od)+'</td><td>$'+row.s.toFixed(0)+'</td><td>$'+tw.toFixed(2)+'</td></tr>'; });
      html+='</tbody></table>';
    }
    if(graded.length){
      graded.sort(function(a,b){ return a.m.date<b.m.date?1:-1; });
      html+='<div class="sec-title" style="font-size:13px;margin-top:16px">Settled ('+graded.length+')</div>'
        +'<table><thead><tr><th>Date</th><th>Bet</th><th>Odds</th><th>Stake</th><th>Result</th><th>P/L $</th></tr></thead><tbody>';
      graded.forEach(function(row){ var m=row.m, rc=row.r==='W'?'pos':'neg', od=(m.type==='parlay')?m.odds:mlStr(m.ml);
        html+='<tr><td>'+esc(m.date)+'</td><td>'+nm(m)+'</td><td>'+esc(od)+'</td><td>$'+row.s.toFixed(0)+'</td><td class="'+rc+'">'+row.r+'</td><td class="'+rc+'">'+(row.pl>=0?'+':'')+'$'+row.pl.toFixed(2)+'</td></tr>'; });
      html+='</tbody></table>';
    }
    el.innerHTML=html;
  };
  window.saveMyBets=function(){
    var data={ version:2, generated:new Date().toISOString(), startBalance:startBalance(),
      picks:Array.from(selected).map(function(pid){ var m=meta(pid)||{}; return {pid:pid, type:m.type||'single', date:m.date, team:m.team, ml:m.ml, title:m.title, amount:stake(pid)}; }) };
    var blob=new Blob([JSON.stringify(data,null,2)], {type:'application/json'});
    var a=document.createElement('a'); a.href=URL.createObjectURL(blob); a.download='my_bets.json'; document.body.appendChild(a); a.click(); a.remove();
  };
  window.clearMyBets=function(){ selected=new Set(); amounts={}; saveSel(); saveAmts(); syncBoxes(); window.renderMyBets(); };
  function init(){ var el=document.getElementById('startbal-input'); if(el&&startOv!==null) el.value=startOv; syncBoxes(); window.renderMyBets(); }
  if(document.readyState!=='loading') init();
  else document.addEventListener('DOMContentLoaded', init);
})();
'''


def _ml_implied(ml):
    if ml is None:
        return None
    ml = float(ml)
    return 100.0 / (ml + 100.0) if ml > 0 else abs(ml) / (abs(ml) + 100.0)


def build_liveodds_html(picks, live_odds=None):
    """Read-only Live Odds / CLV panel. Compares each pick's LOCKED entry price
    (from the frozen morning snapshot) to current odds supplied in `live_odds`
    (map: 'Away@Home' -> {'away_ml':..,'home_ml':..}). This panel NEVER changes
    the Picks tab — it only reports line movement/CLV against the locked entry.
    """
    live_odds = live_odds or {}
    have_live = bool(live_odds)

    def _mlfmt(ml):
        if ml is None:
            return "—"
        return f"+{ml}" if ml > 0 else f"{ml}"

    rows = []
    for g in picks:
        key = f"{g.get('away_team')}@{g.get('home_team')}"
        cur = live_odds.get(key, {})
        for side in ("away", "home"):
            team = g.get(f"{side}_team")
            entry = g.get(f"{side}_ml")
            curr = cur.get(f"{side}_ml")
            is_bet = (g.get(f"{side}_units", 0) or 0) > 0
            # CLV in implied-probability points: positive = the market moved toward
            # your side after you locked (you beat the closing line).
            clv_txt, clv_cls = "—", ""
            ei, ci = _ml_implied(entry), _ml_implied(curr)
            if ei is not None and ci is not None:
                clv_pp = (ci - ei) * 100.0
                clv_txt = f"{clv_pp:+.1f} pp"
                clv_cls = "pos" if clv_pp > 0 else ("neg" if clv_pp < 0 else "")
            move_txt = "—"
            if entry is not None and curr is not None:
                d = curr - entry
                move_txt = "no move" if d == 0 else f"{'+' if d>0 else ''}{d}"
            star = " ⭐" if is_bet else ""
            tr_cls = ' class="tr-total"' if is_bet else ""
            rows.append(
                f"<tr{tr_cls}><td>{team}{star}</td><td>{_mlfmt(entry)}</td>"
                f"<td>{_mlfmt(curr)}</td><td>{move_txt}</td>"
                f"<td class=\"{clv_cls}\">{clv_txt if is_bet else ''}</td></tr>")

    note = ("Current odds and CLV populate when the rebuild runs with a live odds "
            "feed. In this environment the live feed is unavailable, so only the "
            "locked entry prices are shown.") if not have_live else \
           ("CLV is shown for your locked bets (⭐): positive = the market moved "
            "toward your side after you locked = you beat the line.")

    return (f"<p style=\"font-size:12px;color:var(--mut);margin:0 0 12px\">"
            f"Entry prices are <b>locked</b> at the morning run and never change. "
            f"{note}</p>"
            f"<table><thead><tr><th>Team</th><th>Locked Entry</th><th>Current</th>"
            f"<th>Move</th><th>CLV (bets)</th></tr></thead>"
            f"<tbody>{''.join(rows)}</tbody></table>")


def generate_html(picks, record, today, pick_record=None, bankroll_data=None, bettor_news=None, social_intel=None, parlays=None, live_odds=None):
    ov = record["overall"]
    by_s = record["by_season"]
    liveodds_html = build_liveodds_html(picks, live_odds)

    # Fill any missing HP umpire: dropped-in assignments CSV first, then a LIVE
    # pull from the MLB Stats API officials (same-day assignments) for anything
    # still blank. Tendencies come from load_umpires.db_tendencies (our game log).
    try:
        import load_umpires
        _assign = load_umpires.todays_assignments(today)
        if _assign:
            for _g in picks:
                if not _g.get("hp_umpire"):
                    _g["hp_umpire"] = _assign.get(
                        f"{_g.get('away_team')}@{_g.get('home_team')}", "")
        load_umpires.fill_live_assignments(picks)
    except Exception:
        pass

    # Enrich (often data-poor) frozen picks with real team OPS / streak / last-10 /
    # bullpen ERA / H2H from the DB + a best-effort hot bat, then refresh the reason
    # bullets. Display-only — the locked team/odds/edge are never touched.
    try:
        enrich_pick_display(picks, today)
    except Exception:
        pass

    source = record.get("source", "era_threshold")
    auc    = record.get("auc")
    generated = record.get("generated", "")

    if source == "xgboost_walkforward":
        backtest_label = "XGBoost Walk-Forward CV"
        if auc is not None:
            backtest_label += f" (AUC {auc:.3f})"
        if generated:
            try:
                gen_dt = datetime.fromisoformat(generated)
                backtest_label += f" — trained {gen_dt.strftime('%Y-%m-%d %H:%M')}"
            except Exception:
                pass
    else:
        backtest_label = "ERA Rule Baseline"

    # Guard: if there's no backtest data (empty games table / missing metrics),
    # don't render a misleading "0-0". Show an explicit unavailable state instead.
    backtest_unavailable = ov.get("bets", 0) == 0
    if backtest_unavailable:
        backtest_label = "Backtest unavailable — rebuild DB &amp; retrain"
        bt_wl = bt_wr = bt_roi = bt_profit = "—"
        bt_games = "0"
        bt_header = backtest_label
        bt_note = ("No backtest record: the games table is empty or model metrics "
                   "are missing. Run mlb_data.py --build, the backfills, then "
                   "mlb_train.py, and regenerate this dashboard.")
    else:
        bt_wl     = f"{ov['wins']}-{ov['losses']}"
        bt_wr     = f"{ov['win_pct']:.1%}"
        bt_roi    = f"{ov['roi']:+.1%}"
        bt_profit = f"{ov['profit']:+.0f}u"
        bt_games  = f"{ov['bets']:,}"
        bt_header = f"{backtest_label}: {bt_wl} ({bt_wr} win rate)"
        bt_note   = f"{backtest_label}. Flat -110 juice. 2018-2026 regular season."

    order = {"HIGH":0,"MED-HIGH":1,"MEDIUM":2,"LEAN":3}
    actionable = []
    for g in picks:
        for side in ("away","home"):
            if g[f"{side}_units"] > 0 and g[f"{side}_conv"] not in ("NO PLAY","SKIP","RUN LINE"):
                actionable.append((order.get(g[f"{side}_conv"],9), -g[f"{side}_edge"], g, side))
    actionable.sort()

    cards_html = "\n".join(pick_card(g, s, today) for _,_,g,s in actionable) if actionable else \
        '<div class="no-picks">No plays with sufficient edge today.</div>'

    n_plays     = len(actionable)
    total_units = sum(g[f"{s}_units"] for _,_,g,s in actionable)
    roi_cls     = "" if backtest_unavailable else ("pos" if ov["roi"] > 0 else "neg")

    # Build modal data JSON (only for actionable picks)
    modal_data  = build_modal_data(picks)
    modal_json  = json.dumps(modal_data, ensure_ascii=False)

    # ── actual pick record section ──────────────────────────────────
    pr_html = ""
    if pick_record and pick_record.get("total") and pick_record["total"].get("total", 0) > 0:
        pr = pick_record["total"]
        pr_cls = "pos" if pr["pl"] >= 0 else "neg"
        conv_rows = ""
        for conv in ["HIGH", "MED-HIGH", "MEDIUM", "LEAN"]:
            c = pick_record.get("by_conviction", {}).get(conv)
            if c and c["total"] > 0:
                cc = "pos" if c["pl"] >= 0 else "neg"
                conv_rows += (
                    f"<tr><td>{conv}</td><td>{c['total']}</td>"
                    f"<td>{c['wins']}-{c['losses']}</td>"
                    f"<td class='{cc}'>{c['win_pct']:.1%}</td>"
                    f"<td class='{cc}'>{c['pl']:+.2f}u</td></tr>"
                )
        month_rows = ""
        for m in pick_record.get("by_month", []):
            mc = "pos" if m["pl"] >= 0 else "neg"
            month_rows += (
                f"<tr><td>{m['month']}</td><td>{m['wins']+m['losses']}</td>"
                f"<td>{m['wins']}-{m['losses']}</td>"
                f"<td class='{mc}'>{m['win_pct']:.1%}</td>"
                f"<td class='{mc}'>{m['pl']:+.2f}u</td></tr>"
            )
        pending_txt = f" &nbsp;({pick_record['pending']} pending)" if pick_record.get("pending",0) else ""
        pr_html = f"""
  <div style="margin-bottom:32px">
    <div class="sec-title">My Pick Record (Live){pending_txt}</div>
    <div class="stats-bar" style="border-radius:8px;margin-bottom:14px">
      <div class="sc"><span class="sl">Record</span><span class="sv">{pr['wins']}W-{pr['losses']}L</span></div>
      <div class="sdiv"></div>
      <div class="sc"><span class="sl">Win Rate</span><span class="sv {pr_cls}">{pr['win_pct']:.1%}</span></div>
      <div class="sdiv"></div>
      <div class="sc"><span class="sl">P/L</span><span class="sv {pr_cls}">{pr['pl']:+.2f}u</span></div>
      <div class="sdiv"></div>
      <div class="sc"><span class="sl">ROI</span><span class="sv {pr_cls}">{pr['roi']:+.1%}</span></div>
    </div>
    <div style="display:flex;gap:20px;flex-wrap:wrap">
      <div style="flex:1;min-width:240px">
        <table><thead><tr><th>Conviction</th><th>Bets</th><th>W-L</th><th>Win%</th><th>P/L</th></tr></thead>
        <tbody>{conv_rows}</tbody></table>
      </div>
      <div style="flex:1;min-width:240px">
        <table><thead><tr><th>Month</th><th>Bets</th><th>W-L</th><th>Win%</th><th>P/L</th></tr></thead>
        <tbody>{month_rows}</tbody></table>
      </div>
    </div>
  </div>"""
    elif pick_record is not None:
        pending_n = pick_record.get("pending", 0)
        pr_html = f"""  <div style="margin-bottom:32px">
    <div class="sec-title">My Pick Record (Live)</div>
    <p style="color:var(--mut);font-size:13px;padding:0 4px">{"" if pending_n == 0 else f"{pending_n} picks logged, results pending."} Run <code>run_results.bat</code> each morning to auto-log results.</p>
  </div>"""

    # ── bankroll tracker ───────────────────────────────────────────
    bankroll_html = ""
    if bankroll_data and bankroll_data.get("bets", 0) > 0:
        bd = bankroll_data
        cur_br   = bd["current"]
        start_br = bd["starting"]
        pl_d     = bd["total_pl_dollars"]
        roi_d    = bd["roi_pct"]
        br_cls   = "pos" if pl_d >= 0 else "neg"
        unit_d   = bd["unit_dollars"]
        daily    = bd["daily"]
        labels   = [d["date"] for d in daily]
        values   = [d["bankroll"] for d in daily]
        labels_js = "[" + ",".join(f'"{l}"' for l in labels) + "]"
        values_js = "[" + ",".join(str(v) for v in values) + "]"
        recent_rows = ""
        for b in reversed(bd["history"][-20:]):
            rc   = "pos" if b["result"] == "W" else "neg"
            sign = "+" if b["pl_dollars"] >= 0 else ""
            recent_rows += (
                f"<tr><td>{b['date']}</td><td>{b['label']}</td>"
                f"<td><span style='color:{CONVICTION_COLOR.get(b['conviction'],'#aaa')}'>{b['conviction']}</span></td>"
                f"<td>{b['units']}u</td><td class='{rc}'>{b['result']}</td>"
                f"<td class='{rc}'>{sign}${b['pl_dollars']:.2f}</td>"
                f"<td class='{rc}'>${b['bankroll']:.2f}</td></tr>"
            )
        bankroll_html = f"""
  <div style="margin-bottom:32px">
    <div class="sec-title">Bankroll Tracker — $500 Starting</div>
    <div class="stats-bar" style="border-radius:8px;margin-bottom:18px">
      <div class="sc"><span class="sl">Bankroll</span><span class="sv {br_cls}">${cur_br:.2f}</span></div>
      <div class="sdiv"></div>
      <div class="sc"><span class="sl">P/L</span><span class="sv {br_cls}">{'+' if pl_d>=0 else ''}${pl_d:.2f}</span></div>
      <div class="sdiv"></div>
      <div class="sc"><span class="sl">ROI</span><span class="sv {br_cls}">{roi_d:+.1%}</span></div>
      <div class="sdiv"></div>
      <div class="sc"><span class="sl">Record</span><span class="sv">{bd['wins']}W-{bd['losses']}L</span></div>
    </div>
    <canvas id="bankrollChart" style="width:100%;max-height:220px;margin-bottom:18px"></canvas>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.0/chart.umd.min.js"></script>
    <script>
    (function(){{
      var ctx=document.getElementById('bankrollChart').getContext('2d');
      var labels={labels_js},values={values_js};
      var color=values[values.length-1]>={start_br}?'#00e676':'#ef5350';
      window.__bankrollChart = new Chart(ctx,{{type:'line',data:{{labels:labels,datasets:[
        {{label:'Bankroll',data:values,borderColor:color,backgroundColor:color+'22',
         borderWidth:2,pointRadius:labels.length<30?4:2,fill:true,tension:0.3}},
        {{label:'Starting',data:Array(labels.length).fill({start_br}),
         borderColor:'#546e7a',borderWidth:1,borderDash:[6,4],pointRadius:0,fill:false}}
      ]}},options:{{responsive:true,
        plugins:{{legend:{{labels:{{color:'#cfd8dc',font:{{size:12}}}}}}}},
        scales:{{x:{{ticks:{{color:'#78909c',maxTicksLimit:10}},grid:{{color:'#263238'}}}},
                 y:{{ticks:{{color:'#78909c',callback:v=>'$'+v}},grid:{{color:'#263238'}}}}}}
      }}}});
    }})();
    </script>
    <table><thead><tr><th>Date</th><th>Pick</th><th>Conv</th><th>Size</th><th>Result</th><th>P/L $</th><th>Bankroll</th></tr></thead>
    <tbody>{recent_rows}</tbody></table>
  </div>"""
    elif bankroll_data is not None:
        bankroll_html = """
  <div style="margin-bottom:32px">
    <div class="sec-title">Bankroll Tracker — $500 Starting</div>
    <p style="color:var(--mut);font-size:13px;padding:0 4px">No resolved bets yet. Run <code>run_results.bat</code> each morning.</p>
  </div>"""

    # ── Yesterday recap + Weekly report (built from bankroll history) ──
    yesterday_html = ""
    weekly_html = ""
    if bankroll_data and bankroll_data.get("history"):
        from datetime import date as _date, timedelta as _td
        hist   = bankroll_data["history"]
        all_d  = sorted({h["date"] for h in hist})
        last_d = all_d[-1]

        # ---- Yesterday (most recent resolved day) ----
        yday   = [h for h in hist if h["date"] == last_d]
        yw     = sum(1 for h in yday if h["result"] == "W")
        yl     = sum(1 for h in yday if h["result"] == "L")
        y_un   = sum(h["units"] for h in yday)
        y_plu  = sum(h["pl_units"] for h in yday)
        y_pld  = sum(h["pl_dollars"] for h in yday)
        y_roi  = (y_plu / y_un) if y_un else 0.0
        y_cls  = "pos" if y_pld >= 0 else "neg"
        try:
            y_lbl = _date.fromisoformat(last_d).strftime("%A, %B %-d")
        except Exception:
            y_lbl = last_d
        if yw > 0 and yl == 0:
            tag = "<span style='color:#00e676'>Clean sweep</span>"
        elif yl > 0 and yw == 0:
            tag = "<span style='color:#ef5350'>Rough day</span>"
        else:
            tag = f"{yw}-{yl}"
        y_rows = ""
        for h in yday:
            rc   = "pos" if h["result"] == "W" else "neg"
            sign = "+" if h["pl_dollars"] >= 0 else ""
            y_rows += (
                f"<tr><td>{h['label']}</td>"
                f"<td><span style='color:{CONVICTION_COLOR.get(h['conviction'],'#aaa')}'>{h['conviction']}</span></td>"
                f"<td>{h['units']}u</td><td class='{rc}'>{h['result']}</td>"
                f"<td class='{rc}'>{sign}${h['pl_dollars']:.2f}</td></tr>"
            )
        yesterday_html = f"""
  <div style="margin-bottom:32px">
    <div class="sec-title">Yesterday — {y_lbl} &nbsp;({tag})</div>
    <div class="stats-bar" style="border-radius:8px;margin-bottom:14px">
      <div class="sc"><span class="sl">Record</span><span class="sv {y_cls}">{yw}W-{yl}L</span></div>
      <div class="sdiv"></div>
      <div class="sc"><span class="sl">Units</span><span class="sv {y_cls}">{y_plu:+.2f}u</span></div>
      <div class="sdiv"></div>
      <div class="sc"><span class="sl">P/L</span><span class="sv {y_cls}">{'+' if y_pld>=0 else ''}${y_pld:.2f}</span></div>
      <div class="sdiv"></div>
      <div class="sc"><span class="sl">ROI</span><span class="sv {y_cls}">{y_roi:+.1%}</span></div>
    </div>
    <table><thead><tr><th>Pick</th><th>Conv</th><th>Size</th><th>Result</th><th>P/L $</th></tr></thead>
    <tbody>{y_rows}</tbody></table>
  </div>"""

        # ---- Weekly: rolling last 7 days ending on last resolved day ----
        try:
            ld_dt    = _date.fromisoformat(last_d)
            wk_start = ld_dt - _td(days=6)
            wk = [h for h in hist if wk_start.isoformat() <= h["date"] <= last_d]
        except Exception:
            wk = hist
        day_stats = {}
        for h in wk:
            d = day_stats.setdefault(h["date"], {"w":0,"l":0,"u":0.0,"plu":0.0,"pld":0.0})
            d["w"]   += 1 if h["result"] == "W" else 0
            d["l"]   += 1 if h["result"] == "L" else 0
            d["u"]   += h["units"]
            d["plu"] += h["pl_units"]
            d["pld"] += h["pl_dollars"]
        wk_rows = ""
        tw = tl = 0
        tu = tplu = tpld = 0.0
        best = worst = None
        for d in sorted(day_stats):
            s   = day_stats[d]
            tw += s["w"]; tl += s["l"]
            tu += s["u"]; tplu += s["plu"]; tpld += s["pld"]
            droi = (s["plu"]/s["u"]) if s["u"] else 0.0
            dc   = "pos" if s["pld"] >= 0 else "neg"
            try:
                dlbl = _date.fromisoformat(d).strftime("%a %-m/%-d")
            except Exception:
                dlbl = d
            wk_rows += (
                f"<tr><td>{dlbl}</td><td>{s['w']}-{s['l']}</td>"
                f"<td>{s['u']:.2f}u</td>"
                f"<td class='{dc}'>{s['plu']:+.2f}u</td>"
                f"<td class='{dc}'>{'+' if s['pld']>=0 else ''}${s['pld']:.2f}</td>"
                f"<td class='{dc}'>{droi:+.1%}</td></tr>"
            )
            if best  is None or s["pld"] > day_stats[best]["pld"]:  best  = d
            if worst is None or s["pld"] < day_stats[worst]["pld"]: worst = d
        t_roi = (tplu/tu) if tu else 0.0
        t_wpct = (tw/(tw+tl)) if (tw+tl) else 0.0
        t_cls = "pos" if tpld >= 0 else "neg"
        def _fmt_bw(d):
            if not d: return "—"
            s = day_stats[d]
            try: dl = _date.fromisoformat(d).strftime("%a %-m/%-d")
            except Exception: dl = d
            return f"{dl} ({s['w']}-{s['l']}, {'+' if s['pld']>=0 else ''}${s['pld']:.2f})"
        bw_cls = "pos" if best  and day_stats[best]["pld"]  >= 0 else "neg"
        ww_cls = "neg" if worst and day_stats[worst]["pld"] <  0 else "pos"
        try:
            wk_range = f"{wk_start.strftime('%b %-d')} – {ld_dt.strftime('%b %-d')}"
        except Exception:
            wk_range = "last 7 days"
        weekly_html = f"""
  <div style="margin-bottom:28px">
    <div class="sec-title">Weekly Report — {wk_range}</div>
    <div class="stats-bar" style="border-radius:8px;margin-bottom:14px">
      <div class="sc"><span class="sl">Record</span><span class="sv {t_cls}">{tw}W-{tl}L</span></div>
      <div class="sdiv"></div>
      <div class="sc"><span class="sl">Win Rate</span><span class="sv {t_cls}">{t_wpct:.1%}</span></div>
      <div class="sdiv"></div>
      <div class="sc"><span class="sl">Units</span><span class="sv {t_cls}">{tplu:+.2f}u</span></div>
      <div class="sdiv"></div>
      <div class="sc"><span class="sl">P/L</span><span class="sv {t_cls}">{'+' if tpld>=0 else ''}${tpld:.2f}</span></div>
      <div class="sdiv"></div>
      <div class="sc"><span class="sl">ROI</span><span class="sv {t_cls}">{t_roi:+.1%}</span></div>
    </div>
    <table><thead><tr><th>Day</th><th>W-L</th><th>Staked</th><th>P/L (u)</th><th>P/L $</th><th>ROI</th></tr></thead>
    <tbody>{wk_rows}
      <tr class="tr-total"><td>7-DAY</td><td>{tw}-{tl}</td><td>{tu:.2f}u</td>
      <td class="{t_cls}">{tplu:+.2f}u</td>
      <td class="{t_cls}">{'+' if tpld>=0 else ''}${tpld:.2f}</td>
      <td class="{t_cls}">{t_roi:+.1%}</td></tr>
    </tbody></table>
    <div style="display:flex;gap:20px;flex-wrap:wrap;margin-top:14px">
      <div style="flex:1;min-width:240px"><span class="sl">Best day</span><br><span class="{bw_cls}" style="font-size:13px">{_fmt_bw(best)}</span></div>
      <div style="flex:1;min-width:240px"><span class="sl">Worst day</span><br><span class="{ww_cls}" style="font-size:13px">{_fmt_bw(worst)}</span></div>
    </div>
  </div>"""

    season_rows = ""
    for r in by_s:
        rc = "pos" if r["roi"] > 0 else "neg"
        season_rows += (f"<tr><td>{r['season']}</td><td>{r['bets']}</td>"
                        f"<td>{r['wins']}-{r['losses']}</td>"
                        f"<td class='{rc}'>{r['win_pct']:.1%}</td>"
                        f"<td class='{rc}'>{r['roi']:+.1%}</td>"
                        f"<td class='{rc}'>{r['profit']:+.0f}u</td></tr>")

    game_rows = ""
    for g in picks:
        def pcell(side):
            u = g[f"{side}_units"]
            team = g[f"{side}_team"]; ml = g.get(f"{side}_ml")
            if u > 0:
                c = CONVICTION_COLOR.get(g[f"{side}_conv"],"#546e7a")
                lbl = (f'<span style="color:{c}">{g[f"{side}_conv"]} {u}u '
                       f'({g[f"{side}_edge"]:+.1%})</span>')
            else:
                lbl = '<span style="color:#546e7a">—</span>'
            if ml is None:
                return lbl
            pid = f"{today}|{team}|{ml}"
            ctrl = (f'<div class="betctl">'
                    f'<label class="betwrap"><input type="checkbox" class="betbox" data-pid="{pid}" '
                    f'onchange="toggleBet(this)"> bet</label>'
                    f'<input type="number" min="0" step="1" class="betamt" data-pid="{pid}" '
                    f'placeholder="$" oninput="setAmt(this)"></div>')
            return f'{lbl}{ctrl}'
        game_rows += (f"<tr><td>{g['away_team']}</td><td>{ml_str(g['away_ml'])}</td>"
                      f"<td>{pcell('away')}</td><td>{g['home_team']}</td>"
                      f"<td>{ml_str(g['home_ml'])}</td><td>{pcell('home')}</td>"
                      f"<td>{g['ou_line'] or '—'}</td></tr>")


    # ── Build Rundown tab: one card per game ──────────────────────
    import hashlib as _hs
    rd_cards = []
    for g in picks:
        away   = g["away_team"]
        home   = g["home_team"]
        a_sp   = g.get("away_starter", "TBD")
        h_sp   = g.get("home_starter", "TBD")
        ou     = g.get("ou_line")
        venue  = g.get("venue", "")
        pf     = g.get("park_factor", 1.0)
        ump    = g.get("hp_umpire", "")
        ug     = _ump_grade(ump)
        uc     = _ump_cls(ug)
        ump_span = (f'<span class="ump-chip {uc}" style="font-size:10px">'
                    f'⚖ {ump.split()[-1]} {ug}</span>') if ump and ug else ""
        ou_span  = f'<span class="oub">O/U {ou}</span>' if ou else ""
        gtime_r  = g.get("game_time", "")
        gtime_span = f'<span class="oub" style="background:#1e2d45;color:#90caf9" title="First pitch">🕒 {gtime_r}</span>' if gtime_r else ""
        a_prob   = round(g.get("away_prob", 0.5) * 100, 1)
        h_prob   = round(g.get("home_prob", 0.5) * 100, 1)
        a_ml     = ml_str(g.get("away_ml"))
        h_ml     = ml_str(g.get("home_ml"))
        a_conv   = g.get("away_conv", "")
        h_conv   = g.get("home_conv", "")
        def side_badge(conv, units):
            if units > 0 and conv not in ("NO PLAY","SKIP","RUN LINE",""):
                col = CONVICTION_COLOR.get(conv, "#546e7a")
                return f'<span class="psr-badge" style="background:{col}22;color:{col};border:1px solid {col}">{conv}</span>'
            return '<span style="font-size:10px;color:#546e7a">—</span>'
        a_badge = side_badge(a_conv, g.get("away_units", 0))
        h_badge = side_badge(h_conv, g.get("home_units", 0))
        rd_cards.append(f"""
<div class="rd-card">
  <div class="rd-hdr">
    <div class="rd-hdr-left">{away} @ {home}</div>
    <div style="display:flex;gap:6px;align-items:center">{gtime_span}{ou_span}{ump_span}</div>
  </div>
  <div class="rd-body">
    <div class="psr">
      <div class="psr-teams">
        <div class="psr-name">{away} <span style="color:#546e7a;font-weight:400;font-size:11px">{a_ml}</span></div>
        <div class="psr-info">{a_sp} · Model: {a_prob}%</div>
      </div>
      {a_badge}
    </div>
    <div class="psr">
      <div class="psr-teams">
        <div class="psr-name">{home} <span style="color:#546e7a;font-weight:400;font-size:11px">{h_ml}</span></div>
        <div class="psr-info">{h_sp} · Model: {h_prob}%</div>
      </div>
      {h_badge}
    </div>
    {f'<div style="font-size:10px;color:#546e7a;margin-top:6px">{venue} · PF {pf:.2f}</div>' if venue and venue!="Unknown" else ""}
  </div>
</div>""")
    rd_html = "\n".join(rd_cards) if rd_cards else '<p style="color:var(--mut);padding:20px">No games today.</p>'

    # ── Build Bettor News tab ──────────────────────────────────────
    news_items = []
    # Use manually-injected bettor_news if provided (from build_july1.py or API)
    TAG_MAP = {
        "LINE":   "nt-line",
        "SHARP":  "nt-sharp",
        "STEAM":  "nt-sharp",
        "MARKET": "nt-line",
        "PUBLIC": "nt-model",
        "MODEL":  "nt-model",
        "SWING":  "nt-weather",
        "REVERSE":"nt-sharp",
        "VALUE":  "nt-model",
        "INJURY": "nt-injury",
        "WEATHER":"nt-weather",
    }
    if bettor_news:
        for item in bettor_news:
            tag = item.get("tag", "LINE").upper()
            cls = TAG_MAP.get(tag, "nt-line")
            hl  = item.get("headline", "")
            meta= item.get("meta", "")
            news_items.append(
                f'<div class="news-item">'
                f'<div class="news-hl"><span class="news-tag {cls}">{tag}</span>{hl}</div>'
                f'<div class="news-meta">{meta}</div>'
                f'</div>'
            )
    # Always append picks-based model signals as secondary items
    for g in picks:
        for side in ("away", "home"):
            conv  = g.get(f"{side}_conv", "")
            units = g.get(f"{side}_units", 0)
            team  = g[f"{side}_team"]
            opp_t = g["home_team" if side == "away" else "away_team"]
            edge  = g.get(f"{side}_edge", 0)
            pros  = g.get(f"{side}_pros", [])
            flags = g.get("flags", [])
            if units > 0 and conv not in ("NO PLAY","SKIP",""):
                col = CONVICTION_COLOR.get(conv, "#546e7a")
                news_items.append(
                    f'<div class="news-item">'
                    f'<div class="news-hl"><span class="news-tag nt-model">MODEL</span>'
                    f'<strong style="color:{col}">{team}</strong> {conv} vs {opp_t}'
                    f' — edge {edge:+.1%} | {pros[0] if pros else ""}</div>'
                    f'<div class="news-meta">Conviction: {conv} · Units: {units}u · Model edge vs market implied</div>'
                    f'</div>'
                )
            for fl in flags:
                _fh = int(_hs.md5((fl+team).encode()).hexdigest()[:4], 16)
                tag_cls = ["nt-weather","nt-injury","nt-line","nt-sharp"][_fh % 4]
                tag_lbl = ["WEATHER","INJURY","LINE","SHARP"][_fh % 4]
                news_items.append(
                    f'<div class="news-item">'
                    f'<div class="news-hl"><span class="news-tag {tag_cls}">{tag_lbl}</span>{fl}</div>'
                    f'<div class="news-meta">{team} vs {opp_t}</div>'
                    f'</div>'
                )
    if not news_items:
        news_items = ['<div class="news-item"><div class="news-hl" style="color:var(--mut)">No market intel available today.</div></div>']
    news_html = "\n".join(news_items[:25])

    # ── Build Social Trends tab (injuries, weather, trades, rumors) ──────
    SI_TAG_MAP = {
        "INJURY":  ("si-injury",  "🚑"),
        "WEATHER": ("si-weather", "⛅"),
        "TRADE":   ("si-trade",   "🔄"),
        "RUMOR":   ("si-rumor",   "📡"),
        "BULLPEN": ("si-bullpen", "💪"),
        "LINEUP":  ("si-trade",   "📋"),
        "SCRATCH": ("si-injury",  "⚠️"),
    }
    trend_items = []
    if social_intel:
        for rank, item in enumerate(social_intel, 1):
            typ   = item.get("type","WEATHER").upper()
            cls, icon = SI_TAG_MAP.get(typ, ("si-trade","📌"))
            topic = item.get("topic", "")
            desc  = item.get("desc", "")
            trend_items.append(
                f'<div class="trend-item">'
                f'<div class="trend-rank" style="font-size:18px">{icon}</div>'
                f'<div class="trend-body">'
                f'<div class="trend-topic"><span class="si-tag {cls}">{typ}</span>{topic}</div>'
                f'<div class="trend-desc">{desc}</div>'
                f'</div></div>'
            )
    else:
        # Fallback: derive weather/park info from picks slate
        for rank, g in enumerate(picks[:6], 1):
            away2, home2 = g["away_team"], g["home_team"]
            pf2   = g.get("park_factor", 1.0)
            venue = g.get("venue", "")
            ou2   = g.get("ou_line", "")
            a_sp  = g.get("away_starter","TBD")
            h_sp  = g.get("home_starter","TBD")
            pf_lbl = "Hitter-friendly" if pf2 > 1.02 else ("Pitcher-friendly" if pf2 < 0.98 else "Neutral park")
            trend_items.append(
                f'<div class="trend-item">'
                f'<div class="trend-rank" style="font-size:18px">⛅</div>'
                f'<div class="trend-body">'
                f'<div class="trend-topic"><span class="si-tag si-weather">PARK</span>{away2} @ {home2}'
                f'<span class="heat heat-{"warm" if pf2>1.02 else "cool"}">'
                f'{"🌡 HITTER" if pf2>1.02 else "📊 PITCHER"}</span></div>'
                f'<div class="trend-desc">{venue} · PF {pf2:.3f} ({pf_lbl}) · {a_sp} vs {h_sp} · O/U {ou2}</div>'
                f'</div></div>'
            )
    if not trend_items:
        trend_items = ['<div class="trend-item"><div class="trend-rank">—</div><div class="trend-body"><div class="trend-desc" style="color:var(--mut)">No social intel available today.</div></div></div>']
    trends_html = "\n".join(trend_items[:12])

    # ── Build Parlays tab ─────────────────────────────────────────
    def _ml_to_prob(ml):
        if ml is None: return 0.5
        if ml > 0: return 100 / (ml + 100)
        return abs(ml) / (abs(ml) + 100)

    def _prob_to_ml(p):
        p = max(0.01, min(0.99, p))
        if p >= 0.5:
            return round(-(p / (1 - p)) * 100)
        return round((1 - p) / p * 100)

    def _parlay_odds_str(legs):
        """legs = list of (team, ml, edge, conv). Returns (american_odds_str, impl_prob, fair_prob)."""
        impl_combined = 1.0
        fair_combined = 1.0
        for team, ml, edge, conv in legs:
            impl_prob = _ml_to_prob(ml)
            fair_prob = impl_prob + edge
            impl_combined *= impl_prob
            fair_combined *= fair_prob
        ml_out = _prob_to_ml(impl_combined)
        sign = "+" if ml_out > 0 else ""
        return f"{sign}{ml_out}", impl_combined, fair_combined

    # Build parlay legs from actionable picks (already sorted by edge)
    parlay_legs = []
    for g in picks:
        for s in ("away", "home"):
            if g.get(f"{s}_units", 0) > 0:
                parlay_legs.append({
                    "team": g[f"{s}_team"],
                    "opp":  g["home_team" if s=="away" else "away_team"],
                    "ml":   g.get(f"{s}_ml"),
                    "edge": g.get(f"{s}_edge", 0),
                    "conv": g.get(f"{s}_conv", ""),
                    "sp":   g.get(f"{s}_starter","TBD"),
                })
    parlay_legs.sort(key=lambda x: x["edge"], reverse=True)

    def _leg_html(leg):
        conv = leg["conv"]
        col  = CONVICTION_COLOR.get(conv, "#546e7a")
        ml   = leg["ml"]
        sign = "+" if ml and ml > 0 else ""
        edge_col = "var(--grn)" if leg["edge"] > 0 else "var(--red)"
        return (
            f'<div class="parlay-leg">'
            f'<span class="parlay-conv" style="background:{col}33;color:{col}">{conv}</span>'
            f'<span class="parlay-team">{leg["team"]} <span style="font-size:11px;color:var(--mut)">vs {leg["opp"]}</span></span>'
            f'<span class="parlay-ml" style="margin-right:8px">{sign}{ml}</span>'
            f'<span class="parlay-edge" style="color:{edge_col}">{leg["edge"]:+.1%}</span>'
            f'</div>'
        )

    _parlay_meta = {}
    _parlay_idx = [0]
    def _make_parlay_card(title, legs_list, label="PARLAY"):
        if not legs_list: return ""
        raw_legs = [(l["team"], l["ml"], l["edge"], l["conv"]) for l in legs_list]
        odds_str, impl_p, fair_p = _parlay_odds_str(raw_legs)
        edge_pct = (fair_p - impl_p) / impl_p if impl_p > 0 else 0
        edge_col = "var(--grn)" if edge_pct > 0 else "var(--red)"
        payout = (abs(int(odds_str.replace("+",""))) / 100) if "+" in odds_str else (100 / abs(int(odds_str.replace("+",""))))
        _ppid = f"parlay|{today}|{_parlay_idx[0]}"; _parlay_idx[0] += 1
        _parlay_meta[_ppid] = {"title":title,"label":label,"payout":round(payout,4),
                               "legs":[f"{today}|{l['team']}|{l['ml']}" for l in legs_list],
                               "odds":odds_str,"date":today,"type":"parlay"}
        return (
            f'<div class="parlay-card">'
            f'<div class="parlay-header">'
            f'<div class="parlay-title">{title}</div>'
            f'<div style="display:flex;align-items:center;gap:10px">'
            f'<label class="betwrap" style="font-size:11px"><input type="checkbox" class="betbox" data-pid="{_ppid}" onchange="toggleBet(this)"> bet</label>'
            f'<input type="number" min="0" step="1" class="betamt" data-pid="{_ppid}" placeholder="$" oninput="setAmt(this)">'
            f'<div class="parlay-type">{label}</div>'
            f'</div>'
            f'</div>'
            + "".join(_leg_html(l) for l in legs_list) +
            f'<div class="parlay-footer">'
            f'<div class="parlay-stat"><span class="parlay-stat-lbl">Parlay Odds</span>'
            f'<span class="parlay-stat-val" style="color:var(--blu)">{odds_str}</span></div>'
            f'<div class="parlay-stat"><span class="parlay-stat-lbl">Model Edge</span>'
            f'<span class="parlay-stat-val" style="color:{edge_col}">{edge_pct:+.1%}</span></div>'
            f'<div class="parlay-stat"><span class="parlay-stat-lbl">Win Prob</span>'
            f'<span class="parlay-stat-val" style="color:var(--mut)">{fair_p:.1%}</span></div>'
            f'</div></div>'
        )

    parlay_cards = []
    # Use manually-injected parlays if provided
    if parlays:
        for p in parlays:
            leg_objs = [l for l in parlay_legs if l["team"] in p.get("teams", [])]
            if len(leg_objs) >= 2:
                parlay_cards.append(_make_parlay_card(p["title"], leg_objs, p.get("label","PARLAY")))
    else:
        # Auto-generate 2-team and 3-team parlays from top picks
        if len(parlay_legs) >= 2:
            parlay_cards.append(_make_parlay_card(
                f"Top 2-Team Parlay — {parlay_legs[0]['team']} + {parlay_legs[1]['team']}",
                parlay_legs[:2], "2-TEAM"
            ))
        if len(parlay_legs) >= 3:
            parlay_cards.append(_make_parlay_card(
                f"Top 3-Team Parlay — {' + '.join(l['team'] for l in parlay_legs[:3])}",
                parlay_legs[:3], "3-TEAM"
            ))
        if len(parlay_legs) >= 4:
            parlay_cards.append(_make_parlay_card(
                f"Power Parlay — {' + '.join(l['team'] for l in parlay_legs[:4])}",
                parlay_legs[:4], "4-TEAM"
            ))
        # Plus a LEAN-inclusive version
        if len(parlay_legs) >= 2:
            high_med = [l for l in parlay_legs if l["conv"] in ("HIGH","MED-HIGH","MEDIUM")]
            if len(high_med) >= 2:
                parlay_cards.append(_make_parlay_card(
                    f"Value Parlay — Medium+ conviction only",
                    high_med[:3], "VALUE"
                ))
    if not parlay_cards:
        parlay_cards = ['<div style="color:var(--mut);padding:20px">Not enough picks for parlays today.</div>']
    parlays_html = "\n".join(parlay_cards)

    # ── Build Umpires tab ─────────────────────────────────────────
    ump_rows = []
    seen_umps = set()
    used_ump_placeholder = False
    for g in picks:
        ump2  = g.get("hp_umpire","")
        if not ump2 or ump2 in seen_umps:
            continue
        seen_umps.add(ump2)
        away2 = g["away_team"]
        home2 = g["home_team"]
        ug2   = _ump_grade(ump2)
        uc2   = _ump_cls(ug2)
        rec2  = _ump_record(ump2)
        if rec2:                                  # REAL data from load_umpires
            zone_txt  = rec2.get("zone", "Balanced")
            ou_txt    = rec2.get("ou_lean", "Neutral")
            score_v   = rec2.get("score", 10 - (["A","B","C","D"].index(ug2) * 2))
            score_disp = f"{score_v}/10"
        else:                                     # placeholder (hash) — marked *
            _h2   = int(_hs.md5(ump2.encode()).hexdigest()[:6], 16)
            zone_opts  = ["Pitcher-friendly","Balanced","Hitter-friendly","Expansive"]
            ou_opts    = ["Over lean","Neutral","Under lean","Strong under"]
            zone_txt   = zone_opts[_h2 % 4]
            ou_txt     = ou_opts[(_h2 // 4) % 4]
            score_v    = 10 - (["A","B","C","D"].index(ug2) * 2)
            score_disp = f"{score_v}/10*"
            used_ump_placeholder = True
        grade_colors = {"A":"grn","B":"blu","C":"orn","D":"red"}
        gcol = grade_colors.get(ug2, "blu")
        ump_rows.append(
            f'<tr>'
            f'<td>{ump2}</td>'
            f'<td>{away2} @ {home2}</td>'
            f'<td class="ump-grade-cell" style="color:var(--{gcol})">{ug2}</td>'
            f'<td>{score_disp}</td>'
            f'<td>{zone_txt}</td>'
            f'<td>{ou_txt}</td>'
            f'</tr>'
        )
    if used_ump_placeholder:
        ump_rows.append('<tr><td colspan="6" style="color:var(--mut);font-size:11px">'
                        '* placeholder (name-hashed) — drop umpire*.csv in the folder for real '
                        'grades/tendencies (see load_umpires.py).</td></tr>')
    if not ump_rows:
        ump_rows = ['<tr><td colspan="6" style="color:var(--mut);text-align:center">No umpire data available. Drop an ump_assign*.csv (assignments) and umpire*.csv (tendencies) in the folder.</td></tr>']
    umps_table = f"""
<div class="ump-table-wrap">
<table>
  <thead><tr><th>HP Umpire</th><th>Game</th><th>Grade</th><th>Score</th><th>Zone Tendency</th><th>O/U Impact</th></tr></thead>
  <tbody>{"".join(ump_rows)}</tbody>
</table>
</div>
<p style="font-size:11px;color:var(--mut);margin-top:10px">Grades: A=Consistent/fair · B=Average · C=Inconsistent · D=Erratic. Zone and O/U impact derived from historical tendencies.</p>"""

    import json as _json_mb
    def _payout_mult(ml):
        try: ml = int(ml)
        except Exception: return 0.0
        if not ml: return 0.0
        return (ml/100.0) if ml > 0 else (100.0/abs(ml))
    _pm = {}
    if bankroll_data and bankroll_data.get("history"):
        for _h in bankroll_data["history"]:
            _pid = f"{_h['date']}|{_h['team']}|{_h['ml']}"
            _pm[_pid] = {"date":_h["date"],"team":_h["team"],"ml":_h["ml"],
                         "conv":_h.get("conviction",""),"units":_h.get("units",0),
                         "payout":round(_payout_mult(_h["ml"]),4),
                         "result":_h.get("result"),"pl":_h.get("pl_dollars",0),"bet":_h.get("bet",0)}
    # Every game side with a moneyline is bettable (you may pick a game on your own).
    for _g in picks:
        for _sd in ("away","home"):
            _t = _g.get(f"{_sd}_team"); _ml = _g.get(f"{_sd}_ml")
            if not _t or _ml is None: continue
            _pid = f"{today}|{_t}|{_ml}"
            _opp = _g.get("home_team" if _sd=="away" else "away_team","")
            _pm.setdefault(_pid, {"date":today,"team":_t,"ml":_ml,"opp":_opp,
                                  "conv":_g.get(f"{_sd}_conv","") or "","units":_g.get(f"{_sd}_units",0) or 0,
                                  "payout":round(_payout_mult(_ml),4),
                                  "result":None,"pl":0.0,"bet":0})
    pick_meta_json = _json_mb.dumps(_pm, ensure_ascii=False)
    parlay_meta_json = _json_mb.dumps(_parlay_meta, ensure_ascii=False)
    _pr_pl_u = (pick_record.get("total",{}).get("pl",0) if pick_record else 0) or 0
    start_bankroll = round(500 + _pr_pl_u*25, 2)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>MLB Model -- {today}</title>
<style>{CSS}</style>
</head>
<body>
<div class="hdr">
  <div>
    <div class="hdr-title">MLB Betting Model <span>v3</span></div>
    <div class="hdr-date">Generated {datetime.now().strftime("%B %d, %Y  %I:%M %p").replace(" 0"," ")}</div>
  </div>
  <div style="text-align:right">
    <div style="font-size:13px;color:#94a3b8">{n_plays} plays &nbsp;|&nbsp; {total_units:.2f}u in action</div>
    <div style="font-size:12px;color:var(--mut);margin-top:2px">{bt_header}</div>
  </div>
</div>
<div class="stats-bar">
  <div class="sc"><span class="sl">Backtest W-L</span><span class="sv">{bt_wl}</span></div>
  <div class="sdiv"></div>
  <div class="sc"><span class="sl">Win Rate</span><span class="sv pos">{bt_wr}</span></div>
  <div class="sdiv"></div>
  <div class="sc"><span class="sl">ROI</span><span class="sv {roi_cls}">{bt_roi}</span></div>
  <div class="sdiv"></div>
  <div class="sc"><span class="sl">Profit</span><span class="sv {roi_cls}">{bt_profit}</span></div>
  <div class="sdiv"></div>
  <div class="sc"><span class="sl">Games Analyzed</span><span class="sv">{bt_games}</span></div>
  <div class="sdiv"></div>
  <div class="sc"><span class="sl">Today Plays</span><span class="sv" style="color:var(--blu)">{n_plays}</span></div>
  <div class="sdiv"></div>
  <div class="sc"><span class="sl">Units Today</span><span class="sv" style="color:var(--blu)">{total_units:.2f}u</span></div>
</div>
<div class="tab-nav">
  <button class="tab-btn active" onclick="switchTab('picks',this)">Today's Picks</button>
  <button class="tab-btn" onclick="switchTab('rundown',this)">Today's Rundown</button>
  <button class="tab-btn" onclick="switchTab('results',this)">Results</button>
  <button class="tab-btn" onclick="switchTab('weekly',this)">Weekly</button>
  <button class="tab-btn" onclick="switchTab('mybets',this)">My Bets</button>
  <button class="tab-btn" onclick="switchTab('parlays',this)">Parlays</button>
  <button class="tab-btn" onclick="switchTab('news',this)">Bettor News</button>
  <button class="tab-btn" onclick="switchTab('trends',this)">Social Trends</button>
  <button class="tab-btn" onclick="switchTab('umps',this)">Umpires</button>
  <button class="tab-btn" onclick="switchTab('liveodds',this)">Live Odds / CLV</button>
</div>
<div id="tab-picks" class="tab-panel active">
<div class="main">
  <div class="sec-title">Today's Picks — {today}</div>
  <div class="grid">{cards_html}</div>
  <div style="margin-bottom:32px">
    <div class="sec-title">Full Slate — All Games</div>
    <table>
      <thead><tr><th>Away</th><th>ML</th><th>Away Pick</th>
        <th>Home</th><th>ML</th><th>Home Pick</th><th>O/U</th></tr></thead>
      <tbody>{game_rows}</tbody>
    </table>
  </div>
  <div>
    <div class="sec-title">{backtest_label} — By Season</div>
    <table>
      <thead><tr><th>Season</th><th>Bets</th><th>W-L</th><th>Win%</th><th>ROI</th><th>Profit</th></tr></thead>
      <tbody>{season_rows}
        <tr class="tr-total">
          <td>ALL</td><td>{bt_games}</td><td>{bt_wl}</td>
          <td class="pos">{bt_wr}</td>
          <td class="{roi_cls}">{bt_roi}</td>
          <td class="{roi_cls}">{bt_profit}</td>
        </tr>
      </tbody>
    </table>
    <p style="font-size:11px;color:var(--mut);margin-top:9px">
      {bt_note}
    </p>
  </div>
</div>
</div>
<div id="tab-rundown" class="tab-panel">
<div class="main">
  <div class="sec-title">Today's Rundown — All {len(picks)} Games</div>
  <div class="rd-grid">{rd_html}</div>
</div>
</div>
<div id="tab-results" class="tab-panel">
<div class="main">
  {yesterday_html}
  {bankroll_html}
  {pr_html}
</div>
</div>
<div id="tab-weekly" class="tab-panel">
<div class="main">
  {weekly_html}
</div>
</div>
<div id="tab-mybets" class="tab-panel">
<div class="main">
  <div class="sec-title">My Bets — the games you check</div>
  <p style="font-size:12px;color:var(--mut);margin-bottom:12px">Tick &quot;bet&quot; on any game in the Full Slate (or a parlay) and type your stake in $. Everything saves in your browser instantly and totals live below. Use Save to write to the database via sync_bets.py.</p>
  <div style="display:flex;gap:14px;align-items:center;margin-bottom:14px;flex-wrap:wrap">
    <label style="font-size:12px;color:var(--mut)">Daily starting balance $<input id="startbal-input" type="number" step="1" oninput="setStartBal(this)" placeholder="{start_bankroll}" style="width:100px;margin-left:6px;background:var(--bg);border:1px solid var(--bdr);color:var(--txt);border-radius:6px;padding:5px 8px;font-size:13px"></label>
    <button onclick="resetStartBal()" style="background:none;color:var(--mut);border:1px solid var(--mut);border-radius:6px;padding:5px 10px;font-size:11px;cursor:pointer">Reset to carryover</button>
  </div>
  <div style="display:flex;gap:10px;margin-bottom:16px">
    <button onclick="saveMyBets()" style="background:var(--blu);color:#fff;border:none;border-radius:6px;padding:8px 14px;font-size:12px;cursor:pointer">Save my bets to file</button>
    <button onclick="clearMyBets()" style="background:none;color:var(--mut);border:1px solid var(--mut);border-radius:6px;padding:8px 14px;font-size:12px;cursor:pointer">Clear all</button>
  </div>
  <div id="mybets-body"></div>
</div>
</div>
<div id="tab-parlays" class="tab-panel">
<div class="main">
  <div class="sec-title">Parlay Builder — {today}</div>
  <p style="font-size:12px;color:var(--mut);margin-bottom:16px">Auto-generated from today's model picks. Parlays shown in edge-descending order. Model edge = fair combined probability vs market implied probability.</p>
  {parlays_html}
</div>
</div>
<div id="tab-news" class="tab-panel">
<div class="main">
  <div class="sec-title">Bettor News &amp; Market Intel — {today}</div>
  <p style="font-size:12px;color:var(--mut);margin-bottom:12px">Line movement, sharp action, steam moves, and market observations.</p>
  {news_html}
</div>
</div>
<div id="tab-trends" class="tab-panel">
<div class="main">
  <div class="sec-title">Social Intel — Injuries, Weather &amp; Rumors — {today}</div>
  {trends_html}
</div>
</div>
<div id="tab-umps" class="tab-panel">
<div class="main">
  <div class="sec-title">Home Plate Umpires — {today}</div>
  {umps_table}
</div>
</div>
<div id="tab-liveodds" class="tab-panel">
<div class="main">
  <div class="sec-title">Live Odds / CLV — {today} <span style="font-size:12px;color:var(--mut)">(read-only · does not affect locked picks)</span></div>
  {liveodds_html}
</div>
</div>
<div class="modal-overlay" id="modalOverlay" onclick="overlayClick(event)">
  <div class="modal" id="modalContent"></div>
</div>
<script>
var MODAL_DATA = {modal_json};
function switchTab(id, btn) {{
  document.querySelectorAll('.tab-panel').forEach(function(p) {{ p.classList.remove('active'); }});
  document.querySelectorAll('.tab-btn').forEach(function(b) {{ b.classList.remove('active'); }});
  document.getElementById('tab-' + id).classList.add('active');
  btn.classList.add('active');
  if (id === 'results' && window.__bankrollChart) {{
    setTimeout(function(){{ window.__bankrollChart.resize(); }}, 30);
  }}
  if (id === 'mybets' && window.renderMyBets) {{ window.renderMyBets(); }}
}}
function openModal(id) {{
  var html = MODAL_DATA[id];
  if (!html) return;
  document.getElementById('modalContent').innerHTML = html;
  document.getElementById('modalOverlay').classList.add('open');
  document.body.style.overflow = 'hidden';
}}
function closeModal(e) {{
  if (e) e.stopPropagation();
  document.getElementById('modalOverlay').classList.remove('open');
  document.body.style.overflow = '';
}}
function overlayClick(e) {{
  if (e.target === document.getElementById('modalOverlay')) closeModal();
}}
document.addEventListener('keydown', function(e) {{
  if (e.key === 'Escape') closeModal();
}});
</script>
<script>
var PICK_META = {pick_meta_json};
var PARLAY_META = {parlay_meta_json};
var START_BANKROLL = {start_bankroll}, UNIT_DOLLARS = 25, DEFAULT_STAKE = 25;
{MYBETS_JS}
</script>
<div class="footer">MLB Betting Model v3 &nbsp;|&nbsp; bitskyb@gmail.com &nbsp;|&nbsp; Not financial advice.</div>
</body>
</html>"""


# -- main ----------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--open", action="store_true")
    parser.add_argument("--date", default=None)
    parser.add_argument("--deploy", action="store_true")
    args = parser.parse_args()

    today = args.date or date.today().isoformat()
    print(f"Generating MLB dashboard for {today}...")

    picks = get_today_picks(today)
    print(f"  {len(picks)} games processed")

    print("  Computing backtest record...")
    record = compute_model_record()
    ov = record["overall"]
    src = record.get("source", "era_threshold")
    print(f"  Backtest ({src}): {ov['wins']}-{ov['losses']} ({ov['win_pct']:.1%}, {ov['roi']:+.1%} ROI)")

    pick_record   = _get_pick_record()   if _get_pick_record   else None
    bankroll_data = _get_bankroll_data() if _get_bankroll_data else None

    bettor_news = social_intel = None
    try:
        import mlb_intel
        season = int(today[:4])
        try:
            mlb_intel.attach_bvp(picks, season)
        except Exception as _e:
            print(f"  [intel] BvP skipped: {_e}")
        bettor_news, social_intel = mlb_intel.generate_intel(today, games=picks, db=str(DB_PATH))
        print(f"  [intel] bettor={len(bettor_news or [])} social={len(social_intel or [])}")
    except Exception as _e:
        print(f"  [intel] skipped: {_e}")

    html = generate_html(picks, record, today, pick_record=pick_record, bankroll_data=bankroll_data,
                         bettor_news=bettor_news, social_intel=social_intel)
    out  = OUTPUT_DIR / f"mlb_dashboard_{today}.html"
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"\n  Saved: {out}")

    if args.open:
        import webbrowser
        webbrowser.open(str(out))

    if args.deploy:
        try:
            import subprocess
            result = subprocess.run(
                ["python", str(OUTPUT_DIR / "deploy_dashboard.py"), str(out)],
                capture_output=True, text=True, cwd=str(OUTPUT_DIR)
            )
            print(result.stdout)
            if result.returncode != 0:
                print(f"  [Deploy] Error: {result.stderr}")
        except Exception as e:
            print(f"  [Deploy] Failed: {e}")
