"""build_july10.py -- Manual July 10, 2026 picks injection (Friday).

Autonomous nightly run. The MLB Stats / Odds APIs 403 in the sandbox and the
FanDuel/odds index pages are JS-rendered, so data was web-researched:
 - Probable starters + ERAs: FanGraphs SP chart (July 10, authoritative).
 - Moneylines / totals: Action Network per-game pages (rendered) + book snippets.
 - Independent model overlay: numberFire away win prob (via FanDuel Research)
   where reachable (6-7 games). For games where numberFire was NOT reachable,
   away_prob falls back to the no-vig market probability -> ~0 edge -> monitor
   only (same conservative fallback used on July 8). Those games cannot mint a
   value pick; edges only come from the true numberFire overlay games.
Sizing runs through the calibrated mlb_edge ladder. Picks are prob-driven.
DATA-QUALITY CAVEAT: no direct numberFire access in sandbox; a couple of nF
values are derived from the complementary (home) number. Treat edges as
lower-confidence than a normal live run and see the report caveats.
"""
import sys, shutil, tempfile, platform
from pathlib import Path

P = Path(__file__).parent
sys.path.insert(0, str(P))

orig_db = P / "data" / "mlb.db"
if platform.system() == "Linux" and " " in str(orig_db):
    tmp_dir = Path(tempfile.mkdtemp(prefix="mlb_db_"))
    tmp_db  = tmp_dir / "mlb.db"
    try:
        shutil.copy2(str(orig_db), str(tmp_db))
    except Exception as _e:
        print(f"  [DB] copy skipped: {_e}")
    import mlb_data as _md; _md.DB_PATH = str(tmp_db)
    import mlb_dashboard as _mdb; _mdb.DB_PATH = str(tmp_db)
    print(f"  [DB] shadow -> {tmp_db}")

import mlb_dashboard as dash
import mlb_data as _md
import mlb_edge as E

TODAY = "2026-07-10"

def ml_to_prob(ml):
    if ml is None: return 0.5
    return (100/(ml+100)) if ml > 0 else (abs(ml)/(abs(ml)+100))

def novig_away(away_ml, home_ml):
    ai = ml_to_prob(away_ml); hi = ml_to_prob(home_ml)
    if ai + hi == 0: return 0.5
    return ai / (ai + hi)

def make_pick(away, home, away_ml, home_ml, ou, away_sp, home_sp,
              away_prob, away_era, home_era, away_wp=0.5, home_wp=0.5,
              venue="", flags=None, hp_umpire="", nf_real=True):
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
    if not nf_real:   # no independent overlay -> never bet, monitor only
        away_units = home_units = 0
        away_conv = home_conv = "MONITOR"
    g = {
        "away_team": away, "home_team": home,
        "away_starter": away_sp, "home_starter": home_sp,
        "venue": venue, "park_factor": pf,
        "ou_line": ou, "away_ml": away_ml, "home_ml": home_ml,
        "away_ml_best": away_ml, "home_ml_best": home_ml,
        "away_ml_book": "consensus", "n_books": 1,
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

# (away, home, away_ml, home_ml, ou, away_sp, home_sp, nf_away(None=no overlay),
#  away_era, home_era, venue)
SLATE = [
    ("Boston Red Sox","New York Mets",           113,-134, 7.5,"S. Gray","N. McLean",      None,   2.61, 3.78,"Citi Field"),
    ("Athletics","Chicago White Sox",            140,-170, 9.0,"A. Civale","S. Burke",      None,   5.10, 3.56,"Rate Field"),
    ("Kansas City Royals","Baltimore Orioles",   125,-151, 9.5,"L. Avila","B. Young",       None,   5.40, 3.38,"Oriole Park at Camden Yards"),
    ("Milwaukee Brewers","Pittsburgh Pirates",   108,-126, 8.5,"B. Sproat","B. Ashcraft",   0.438,  5.28, 3.24,"PNC Park"),
    ("Colorado Rockies","San Francisco Giants",  140,-166, 8.5,"T. Gordon","R. Ray",        None,   6.69, 3.45,"Oracle Park"),
    ("Arizona Diamondbacks","Los Angeles Dodgers",210,-255, 7.0,"E. Rodriguez","S. Ohtani", 0.283,  2.21, 1.79,"Dodger Stadium"),
    ("Atlanta Braves","St. Louis Cardinals",    -164, 138, 8.0,"C. Sale","K. Leahy",        0.533,  2.27, 3.86,"Busch Stadium"),
    ("Chicago Cubs","Cincinnati Reds",          -113,-106, 9.5,"S. Imanaga","H. Greene",     None,   4.28, 4.60,"Great American Ball Park"),
    ("New York Yankees","Washington Nationals", -167, 137,10.0,"R. Weathers","Z. Littell",   None,   4.08, 5.02,"Nationals Park"),
    ("Cleveland Guardians","Miami Marlins",      100,-118, 7.5,"P. Messick","S. Alcantara",  0.401,  2.80, 4.00,"loanDepot park"),
    ("Houston Astros","Texas Rangers",          -138, 118, 8.5,"H. Brown","C. Quantrill",    0.438,  3.38, 3.35,"Globe Life Field"),
    ("Toronto Blue Jays","San Diego Padres",    -104,-112, 8.0,"S. Bieber","JP Sears",       0.481,  9.00, 6.97,"Petco Park"),
    ("Seattle Mariners","Tampa Bay Rays",       -110,-110, 8.0,"L. Castillo","N. Martinez",  None,   4.79, 2.61,"Tropicana Field"),
    ("Los Angeles Angels","Minnesota Twins",     110,-130, 8.5,"G. Rodriguez","Z. Matthews", 0.393,  8.06, 4.43,"Target Field"),
]
# Monitor-only (no posted moneyline): Philadelphia Phillies (A. Nola 6.04) @
# Detroit Tigers (J. Flaherty 4.60), Comerica Park.

picks = []
for (away,home,aml,hml,ou,asp,hsp,nf,aera,hera,venue) in SLATE:
    nf_real = nf is not None
    aprob = nf if nf_real else novig_away(aml, hml)
    picks.append(make_pick(away,home,aml,hml,ou,asp,hsp,aprob,aera,hera,
                           venue=venue, nf_real=nf_real))
picks.sort(key=lambda g: max(g.get("away_edge",0), g.get("home_edge",0)), reverse=True)
for g in picks:
    g.setdefault("hp_umpire","")

try:
    import mlb_freeze
    _refresh = "--refresh" in sys.argv
    picks = mlb_freeze.load_or_freeze(picks, TODAY, str(P), meta={"source":"build_july10"}, refresh=_refresh)
except Exception as e:
    print(f"  [freeze] skipped: {e}")

try:
    cands = []
    for g in picks:
        for side in ("away","home"):
            if g.get(f"{side}_units",0) > 0:
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

print("\nGenerating dashboard...")
try:
    html = dash.generate_html(picks=picks, record=record, today=TODAY, pick_record=pick_record, bankroll_data=bankroll_data)
    out = P / f"mlb_dashboard_{TODAY}.html"; out.write_text(html, encoding="utf-8")
    print(f"  Saved -> {out.name}  ({len(html):,} bytes)")
except Exception as e:
    print(f"  [dash] {e}")

print(f"\n{'='*66}\n  MLB MODEL PICKS -- {TODAY}  (numberFire overlay where available)\n{'='*66}")
any_pick = False
for g in picks:
    for side in ("away","home"):
        if g.get(f"{side}_units",0) > 0:
            any_pick = True
            team=g[f"{side}_team"]; opp=g["home_team" if side=="away" else "away_team"]
            ml=g[f"{side}_ml"]; sign="+" if ml and ml>0 else ""
            print(f"  ** {team} ({sign}{ml}) vs {opp} - {g[f'{side}_conv']} ({g[f'{side}_units']}u)  edge {g[f'{side}_edge']:+.1%}")
if not any_pick:
    print("  (no qualifying value picks)")
print(f"{'='*66}\nDone.")
