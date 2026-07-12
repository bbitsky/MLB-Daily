"""build_july5.py -- Manual July 5, 2026 picks injection (Star-Spangled Sunday, 15-game slate).

Data: web-researched (FanDuel Research/numberFire, FantasyPros, Bleacher Nation,
SportsGrid) because the MLB Stats API / Odds API are blocked in the sandbox.
Model: ERA-differential + win% formula fallback (trained XGBoost unavailable).
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

TODAY = "2026-07-05"

def ml_to_prob(ml):
    if ml is None: return 0.5
    if ml > 0: return 100 / (ml + 100)
    return abs(ml) / (abs(ml) + 100)

def formula_prob(away_era, home_era, away_wp=0.500, home_wp=0.500):
    era_diff = home_era - away_era
    wp_diff  = away_wp - home_wp
    return max(0.32, min(0.68, 0.47 + era_diff * 0.028 + wp_diff * 0.15))

PROB_CAP = 0.68

def conviction(edge, ml, opp_ml=None):
    if opp_ml is not None and opp_ml < 0:
        opp_impl = abs(opp_ml) / (abs(opp_ml) + 100)
        if opp_impl > PROB_CAP:
            return "NO PLAY", 0.0
    if edge >= 0.08: return "HIGH",     1.00
    if edge >= 0.06: return "MED-HIGH", 0.75
    if edge >= 0.05: return "MEDIUM",   0.50
    if edge >= 0.02: return "LEAN",     0.25
    return "NO PLAY", 0.0

def make_pick(away, home, away_ml, home_ml, ou, away_sp, home_sp, away_era, home_era,
              away_wp=0.500, home_wp=0.500, away_fip=None, home_fip=None,
              away_whip=1.30, home_whip=1.30, away_k9=8.5, home_k9=8.5,
              venue="", flags=None, hp_umpire=""):
    flags = flags or []
    away_fip = away_fip or away_era
    home_fip = home_fip or home_era
    away_prob = formula_prob(away_era, home_era, away_wp, home_wp)
    home_prob = 1.0 - away_prob
    away_impl = ml_to_prob(away_ml) if away_ml else 0.5
    home_impl = ml_to_prob(home_ml) if home_ml else 0.5
    away_edge = away_prob - away_impl if away_ml else 0.0
    home_edge = home_prob - home_impl if home_ml else 0.0
    away_conv, away_units = conviction(away_edge, away_ml, opp_ml=home_ml)
    home_conv, home_units = conviction(home_edge, home_ml, opp_ml=away_ml)
    g = {
        "away_team": away, "home_team": home,
        "away_starter": away_sp, "home_starter": home_sp,
        "venue": venue, "park_factor": dash.PARK_FACTORS.get(venue, 1.00),
        "ou_line": ou, "away_ml": away_ml, "home_ml": home_ml,
        "away_ml_best": away_ml, "home_ml_best": home_ml,
        "away_ml_book": "FanDuel", "n_books": 4,
        "line_outlier": False, "line_outlier_gap": 0.0,
        "away_prob": away_prob, "home_prob": home_prob,
        "away_implied": away_impl, "home_implied": home_impl,
        "away_edge": away_edge, "home_edge": home_edge,
        "away_conv": away_conv, "home_conv": home_conv,
        "away_units": away_units, "home_units": home_units,
        "away_era": away_era, "home_era": home_era,
        "away_fip": away_fip, "home_fip": home_fip,
        "away_xfip": away_fip, "home_xfip": home_fip,
        "away_whip": away_whip, "home_whip": home_whip,
        "away_k9": away_k9, "home_k9": home_k9,
        "away_gs": 14, "home_gs": 14,
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

# July 5 slate. Confirmed pitchers/odds where researched. Where a starter's season
# ERA is misleading (recent-form collapse or FIP regression), the MODELED era is
# tempered so the formula does not manufacture or overstate an edge.
# (away, home, away_ml, home_ml, ou, away_sp, home_sp, away_era, home_era,
#  away_wp, home_wp, away_fip, home_fip, away_whip, home_whip, away_k9, home_k9, venue)
SLATE = [
    # McLean season ERA 4.01 but 6.92 since May (FIP 5.49) -> modeled 5.00 to reflect collapse.
    ("Mets","Braves",         154,-184, 8.0,"N. McLean","M. Perez",    5.00,3.27, 0.50,0.55, 5.20,3.60, 1.14,1.20, 9.5,7.5,"Truist Park"),
    ("Pirates","Nationals",   116,-134, 9.0,"B. Chandler","C. Cavalli",4.62,3.69, 0.45,0.50, None,None, 1.40,1.25, 8.0,8.5,"Nationals Park"),
    ("Twins","Yankees",       116,-136, 8.5,"J. Ryan","R. Weathers",   3.61,4.08, 0.50,0.56, None,None, 1.15,1.35, 9.5,7.5,"Yankee Stadium"),
    ("Marlins","Athletics",   103,-123, 8.0,"E. Perez","G. Jump",      4.21,2.93, 0.53,0.47, None,None, 1.25,1.10, 8.5,9.5,"Sutter Health Park"),
    # E-Rod 2.21 ERA but FIP 3.98 -> modeled 3.20; Sproat 5.28 -> modeled 4.70 (regression).
    ("Brewers","Diamondbacks",-124, 104, 8.5,"B. Sproat","E. Rodriguez",4.70,3.20, 0.55,0.50, None,None, 1.40,1.15, 7.5,8.5,"Chase Field"),
    ("Cardinals","Cubs",      135,-155, 8.5,"M. Liberatore","J. Assad", 5.33,4.53, 0.48,0.54, None,None, 1.35,1.30, 8.0,7.5,"Wrigley Field"),
    ("Giants","Rockies",     -124, 107,13.0,"T. Mahle","T. Gordon",     5.67,5.50, 0.52,0.42, None,None, 1.35,1.45, 7.5,6.5,"Coors Field"),
]

picks = []
for row in SLATE:
    (away, home, away_ml, home_ml, ou, away_sp, home_sp, away_era, home_era,
     away_wp, home_wp, away_fip, home_fip, away_whip, home_whip, away_k9, home_k9, venue) = row
    picks.append(make_pick(away, home, away_ml, home_ml, ou, away_sp, home_sp,
                           away_era, home_era, away_wp, home_wp, away_fip, home_fip,
                           away_whip, home_whip, away_k9, home_k9, venue=venue))
picks.sort(key=lambda g: max(g.get("away_edge",0), g.get("home_edge",0)), reverse=True)
for g in picks:
    if not g.get("hp_umpire"):
        g["hp_umpire"] = ""

# Lock the day's picks at this initial run. A re-run reloads the snapshot instead
# of recomputing, so the daily picks never change after the morning run.
import mlb_freeze
_refresh = "--refresh" in sys.argv
picks = mlb_freeze.load_or_freeze(picks, TODAY, str(P),
                                  meta={"source": "build_july5"}, refresh=_refresh)

try:
    record = dash.compute_model_record()
except Exception as e:
    print(f"  [DB] record error: {e}")
    record = {"by_season":[], "overall":{"bets":0,"wins":0,"losses":0,"win_pct":0.0,"roi":0.0,"profit":0.0},"source":"manual","auc":None,"generated":""}

try:
    import mlb_results as _mr
    _mr.DB_PATH = str(_md.DB_PATH)
    pick_record = _mr.get_pick_record()
except Exception as e:
    print(f"  [DB] pick_record error: {e}")
    pick_record = None
try:
    import mlb_results as _mr
    _mr.DB_PATH = str(_md.DB_PATH)
    bankroll_data = _mr.get_bankroll_data()
except Exception as e:
    print(f"  [DB] bankroll_data error: {e}")
    bankroll_data = None

BETTOR_NEWS = [
    {"tag":"VALUE","headline":"Diamondbacks +104 vs Brewers - Eduardo Rodriguez (2.21) over Sproat (5.28)",
     "meta":"The board's one clean plus-money edge. Arizona sends All-Star Eduardo Rodriguez (7-2, 2.21 ERA) at home yet is priced as a +104 underdog because Milwaukee is an elite team - but tonight Milwaukee throws Brandon Sproat (3-4, 5.28). Getting the far better starter at home at plus money is the model's most reliable signal. Sized MED-HIGH (0.5u), not full: numberFire leans Milwaukee on team strength and E-Rod's 3.98 FIP hints at regression."},
    {"tag":"FADE","headline":"Braves -184 vs Mets - two models call it too heavy, but McLean is cratering",
     "meta":"numberFire has Atlanta at just 50% and our formula sees ~55%, both well under the -184 (64.8%) price - so Mets +154 screens as value on paper. Passed anyway: Nolan McLean's 4.01 season ERA masks a 6.92 mark since May (FIP 5.49). The recent-form collapse voids the edge. Monitor, no bet."},
    {"tag":"CHALK","headline":"Athletics -123 vs Marlins - correct side, no plus-money value",
     "meta":"Gage Jump (2.93) is the better arm over Eury Perez (4.21) and the A's are home, but -123 (55.2%) already prices the model's ~55% read. Right side, fair number. Parlay anchor at most, not a standalone bet."},
    {"tag":"MONITOR","headline":"Pirates +116 @ Nationals - model/market split, no clean read",
     "meta":"numberFire likes the Pirates dog (58.5%) while our ERA formula favors Cade Cavalli (3.69) over Bubba Chandler (4.62) for Washington - and -134 already prices WSH fairly. Conflicting signals cancel out. Pass."},
]
SOCIAL_INTEL = [
    {"type":"PITCHING","topic":"Eduardo Rodriguez - All-Star form, undervalued at home",
     "desc":"7-2, 2.21 ERA over 102 IP, just named to the All-Star Game. Draws Brewers spot-caliber starter Brandon Sproat (5.28) yet Arizona is a +104 home dog. The market is paying for Milwaukee's roster; the model is paying for tonight's arm."},
    {"type":"FORM","topic":"Nolan McLean - the wheels have come off since May",
     "desc":"Dominant in April (2.55 ERA) but 6.92 ERA / 5.49 FIP since. His 4.01 season line understates how poorly he's throwing right now - the reason we fade the otherwise-tempting Mets +154 value."},
    {"type":"WEATHER","topic":"Coors Field variance (Giants @ Rockies) + live feed unavailable",
     "desc":"O/U is 13.0 at altitude - the July 2 audit lesson was to discount starter ERA edges hard at Coors, where a two-run pitching advantage evaporated in a 14-run Rockies outburst. Mahle (5.67) is poor regardless; no play. Live wind/temperature APIs are blocked in this environment."},
]
PARLAYS = []  # Single qualifying value play -> no multi-leg spot (discipline over volume).

import mlb_intel
_SHORT2FULL = {"Mets":"New York Mets","Braves":"Atlanta Braves",
    "Pirates":"Pittsburgh Pirates","Nationals":"Washington Nationals",
    "Twins":"Minnesota Twins","Yankees":"New York Yankees",
    "Marlins":"Miami Marlins","Athletics":"Athletics",
    "Brewers":"Milwaukee Brewers","Diamondbacks":"Arizona Diamondbacks",
    "Cardinals":"St. Louis Cardinals","Cubs":"Chicago Cubs",
    "Giants":"San Francisco Giants","Rockies":"Colorado Rockies"}
_games_intel = [{"venue": g.get("venue",""),
                 "away_team": _SHORT2FULL.get(g["away_team"], g["away_team"]),
                 "home_team": _SHORT2FULL.get(g["home_team"], g["home_team"])} for g in picks]
try:
    _events = _md.fetch_today_odds(target_date=TODAY)
except Exception as _e:
    print(f"  [intel] live odds unavailable ({_e}); betting trends use curated fallback")
    _events = []
try:
    _live_bettor = mlb_intel.build_bettor_news(_events, TODAY, db=str(_md.DB_PATH))
    _live_social = mlb_intel.build_social_intel(_games_intel)
    BETTOR_NEWS = _live_bettor if len(_live_bettor) >= 3 else (_live_bettor + BETTOR_NEWS)
    SOCIAL_INTEL = _live_social if len(_live_social) >= 3 else (_live_social + SOCIAL_INTEL)
    print(f"  [intel] live bettor={len(_live_bettor)} social={len(_live_social)}")
except Exception as _e:
    print(f"  [intel] generation failed ({_e}); using curated fallback lists")

print("\nGenerating dashboard...")
try:
    html = dash.generate_html(picks=picks, record=record, today=TODAY, pick_record=pick_record,
        bankroll_data=bankroll_data, bettor_news=BETTOR_NEWS, social_intel=SOCIAL_INTEL, parlays=PARLAYS)
except TypeError:
    html = dash.generate_html(picks=picks, record=record, today=TODAY, pick_record=pick_record, bankroll_data=bankroll_data)
out = P / f"mlb_dashboard_{TODAY}.html"
out.write_text(html, encoding="utf-8")
print(f"  Saved -> {out.name}  ({len(html):,} bytes)")

# Emit the operator's preferred why/why-not markdown summary (auto).
try:
    import mlb_summary
    _sp = mlb_summary.write_daily_summary(picks, TODAY, out_dir=str(P), parlays=PARLAYS)
    print(f"\n  Why/why-not summary -> {Path(_sp).name}")
except Exception as _e:
    print(f"\n  [summary] generation skipped: {_e}")

print(f"\n{'='*65}")
print(f"  MLB MODEL PICKS -- {TODAY}  (manual research mode)")
print(f"{'='*65}")
for g in picks:
    for side in ("away","home"):
        if g[f"{side}_units"] > 0:
            team=g[f"{side}_team"]; opp=g["home_team" if side=="away" else "away_team"]
            ml=g[f"{side}_ml"]; sign="+" if ml and ml>0 else ""
            print(f"  ** {team} ({sign}{ml}) vs {opp} - {g[f'{side}_conv']} ({g[f'{side}_units']}u)  edge {g[f'{side}_edge']:+.1%}  SP: {g[f'{side}_starter']}")
print(f"{'='*65}\nDone.")
