"""build_july9.py -- Manual July 9, 2026 picks injection (Thursday).

Data: web-researched via FanDuel Research (July 9 odds page). Unlike July 8, an
INDEPENDENT per-game model feed WAS reachable: numberFire win probabilities are
published for every game, so away_prob = numberFire's projected win probability
(a real independent overlay). Moneylines + probable starters are from the same
board. Edges are therefore genuine (numberFire prob - market implied), not
market-devig. Sizing runs through the calibrated mlb_edge ladder. ERAs left None
(coerced to a neutral 4.15 placeholder for display; picks are prob-driven). Two
games had no posted moneyline (Yankees@Rays, Rockies@Giants) -> monitors only.
"""
import sys, shutil, tempfile, platform
from pathlib import Path

P = Path(__file__).parent
sys.path.insert(0, str(P))

orig_db = P / "data" / "mlb.db"
if platform.system() == "Linux" and " " in str(orig_db):
    tmp_dir = Path(tempfile.mkdtemp(prefix="mlb_db_"))
    tmp_db  = tmp_dir / "mlb.db"
    shutil.copy2(str(orig_db), str(tmp_db))
    import mlb_data as _md; _md.DB_PATH = str(tmp_db)
    import mlb_dashboard as _mdb; _mdb.DB_PATH = str(tmp_db)
    print(f"  [DB] shadow -> {tmp_db}")

import mlb_dashboard as dash
import mlb_data as _md
import mlb_edge as E

TODAY = "2026-07-09"

def ml_to_prob(ml):
    if ml is None: return 0.5
    return (100/(ml+100)) if ml > 0 else (abs(ml)/(abs(ml)+100))

def make_pick(away, home, away_ml, home_ml, ou, away_sp, home_sp,
              away_prob, away_era, home_era, away_wp, home_wp,
              venue="", flags=None, hp_umpire=""):
    flags = flags or []
    _NEUTRAL_ERA = 4.15
    if away_era is None: away_era = _NEUTRAL_ERA
    if home_era is None: home_era = _NEUTRAL_ERA
    home_prob = 1.0 - away_prob
    away_impl = ml_to_prob(away_ml); home_impl = ml_to_prob(home_ml)
    pf = dash.PARK_FACTORS.get(venue, 1.00)
    away_edge = E.adjusted_edge(away_prob - away_impl, pf)
    home_edge = E.adjusted_edge(home_prob - home_impl, pf)
    away_conv, away_units = E.conviction(away_edge, away_ml)
    home_conv, home_units = E.conviction(home_edge, home_ml)
    g = {
        "away_team": away, "home_team": home,
        "away_starter": away_sp, "home_starter": home_sp,
        "venue": venue, "park_factor": pf,
        "ou_line": ou, "away_ml": away_ml, "home_ml": home_ml,
        "away_ml_best": away_ml, "home_ml_best": home_ml,
        "away_ml_book": "FanDuel", "n_books": 1,
        "line_outlier": False, "line_outlier_gap": 0.0,
        "away_prob": away_prob, "home_prob": home_prob,
        "away_implied": away_impl, "home_implied": home_impl,
        "away_edge": away_edge, "home_edge": home_edge,
        "away_conv": away_conv, "home_conv": home_conv,
        "away_units": away_units, "home_units": home_units,
        "away_era": away_era, "home_era": home_era,
        "away_fip": away_era, "home_fip": home_era,
        "away_xfip": away_era, "home_xfip": home_era,
        "away_whip": 1.30, "home_whip": 1.30, "away_k9": 8.5, "home_k9": 8.5,
        "away_gs": 15, "home_gs": 15,
        "away_last5_era": away_era, "home_last5_era": home_era,
        "away_trend": "--", "home_trend": "--",
        "away_wp": away_wp, "home_wp": home_wp,
        "away_rest": 5, "home_rest": 5,
        "away_ops": 0.720, "home_ops": 0.720,
        "away_wrc_plus": 100, "home_wrc_plus": 100,
        "away_qs_rate": 0.50, "home_qs_rate": 0.50,
        "away_starts_detail": [], "home_starts_detail": [],
        "flags": flags, "hp_umpire": hp_umpire,
    }
    for side in ("away", "home"):
        if g[f"{side}_units"] > 0:
            try:
                g[f"{side}_pros"], g[f"{side}_cons"] = dash.generate_reasons(g, side)
            except Exception:
                g[f"{side}_pros"] = [f"{g[f'{side}_edge']:+.1%} model edge vs market"]
                g[f"{side}_cons"] = []
    return g

# (away, home, away_ml, home_ml, ou, away_sp, home_sp, away_prob(numberFire),
#  away_era, home_era, away_wp, home_wp, venue)
SLATE = [
    ("Chicago Cubs","Baltimore Orioles",           108,-126, 9.0,"D. Peterson","T. Rogers",   0.6136, None,None, 0.560,0.386,"Oriole Park at Camden Yards"),
    ("Atlanta Braves","Pittsburgh Pirates",        -118, 100, 8.0,"B. Elder","M. Keller",      0.4998, None,None, 0.583,0.505,"PNC Park"),
    ("Kansas City Royals","New York Mets",          128,-152, 8.0,"M. Wacha","S. Manaea",       0.4008, None,None, 0.413,0.418,"Citi Field"),
    ("Cleveland Guardians","Minnesota Twins",      -134, 114, 8.5,"G. Williams","B. Ober",      0.4854, None,None, 0.516,0.489,"Target Field"),
    ("Boston Red Sox","Chicago White Sox",         -104,-112, 8.5,"P. Sandoval","A. Kay",       0.4091, None,None, 0.461,0.522,"Rate Field"),
    ("Athletics","Detroit Tigers",                  118,-138, 8.5,"J. Perkins","F. Valdez",     0.4477, None,None, 0.451,0.451,"Comerica Park"),
    ("Seattle Mariners","Miami Marlins",           -142, 120, 8.0,"B. Miller","J. Junk",        0.5232, None,None, 0.516,0.548,"loanDepot park"),
    ("Philadelphia Phillies","Cincinnati Reds",    -164, 138, 9.5,"J. Luzardo","B. Singer",     0.6414, None,None, 0.554,0.456,"Great American Ball Park"),
    ("Milwaukee Brewers","St. Louis Cardinals",    -126, 108, 8.0,"F. Henderson","A. Pallante", 0.4639, None,None, 0.637,0.522,"Busch Stadium"),
    ("Los Angeles Angels","Texas Rangers",          120,-142, 7.5,"R. Detmers","N. Eovaldi",    0.4319, None,None, 0.391,0.505,"Globe Life Field"),
    ("Arizona Diamondbacks","San Diego Padres",     108,-126, 7.5,"M. Kelly","G. Canning",      0.4677, None,None, 0.495,0.495,"Petco Park"),
]

picks = []
for (away,home,aml,hml,ou,asp,hsp,nfa,aera,hera,awp,hwp,venue) in SLATE:
    picks.append(make_pick(away,home,aml,hml,ou,asp,hsp,nfa,aera,hera,awp,hwp,venue=venue))
picks.sort(key=lambda g: max(g.get("away_edge",0), g.get("home_edge",0)), reverse=True)
for g in picks:
    g.setdefault("hp_umpire","")

import mlb_freeze
_refresh = "--refresh" in sys.argv
picks = mlb_freeze.load_or_freeze(picks, TODAY, str(P), meta={"source":"build_july9"}, refresh=_refresh)

try:
    cands = []
    for g in picks:
        for side in ("away","home"):
            if g[f"{side}_units"] > 0:
                cands.append({"pick_team": g[f"{side}_team"], "ml": g[f"{side}_ml"],
                    "my_prob": g[f"{side}_prob"], "implied_prob": g[f"{side}_implied"],
                    "edge": g[f"{side}_edge"], "conviction": g[f"{side}_conv"],
                    "units": g[f"{side}_units"], "bet": 1})
    n = E.log_picks(str(_md.DB_PATH), TODAY, cands)
    print(f"  [log] wrote {n} model pick(s) to DB for {TODAY}")
except Exception as e:
    print(f"  [log] skipped: {e}")

try:
    record = dash.compute_model_record()
except Exception as e:
    print(f"  [DB] record error: {e}"); record = {"by_season":[], "overall":{"bets":0,"wins":0,"losses":0,"win_pct":0.0,"roi":0.0,"profit":0.0},"source":"manual","auc":None,"generated":""}
try:
    import mlb_results as _mr; _mr.DB_PATH = str(_md.DB_PATH)
    pick_record = _mr.get_pick_record(); bankroll_data = _mr.get_bankroll_data()
except Exception as e:
    print(f"  [DB] record error: {e}"); pick_record = None; bankroll_data = None

print("\nGenerating dashboard... (see render for full news/intel payload)")
try:
    html = dash.generate_html(picks=picks, record=record, today=TODAY, pick_record=pick_record, bankroll_data=bankroll_data)
    out = P / f"mlb_dashboard_{TODAY}.html"; out.write_text(html, encoding="utf-8")
    print(f"  Saved -> {out.name}  ({len(html):,} bytes)")
except Exception as e:
    print(f"  [dash] {e}")

print(f"\n{'='*66}\n  MLB MODEL PICKS -- {TODAY}  (numberFire model overlay)\n{'='*66}")
for g in picks:
    for side in ("away","home"):
        if g[f"{side}_units"] > 0:
            team=g[f"{side}_team"]; opp=g["home_team" if side=="away" else "away_team"]
            ml=g[f"{side}_ml"]; sign="+" if ml and ml>0 else ""
            print(f"  ** {team} ({sign}{ml}) vs {opp} - {g[f'{side}_conv']} ({g[f'{side}_units']}u)  edge {g[f'{side}_edge']:+.1%}")
print(f"{'='*66}\nDone.")
