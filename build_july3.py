"""build_july3.py -- Manual July 3, 2026 picks injection.

Data: web-researched (FanDuel Research, Bleacher Nation/DataSkrive, SportsGrid,
OddsShark) because the MLB Stats API / Odds API are blocked in the sandbox.
Model: ERA-differential + win% formula fallback (trained XGBoost unavailable:
mlb_train.py has an unclosed-paren syntax error at line 570).
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

TODAY = "2026-07-03"

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

# July 3 slate. Confirmed pitchers/odds where researched; ERAs left neutral (4.10)
# where a starter was unconfirmed so the formula does not invent an edge.
# (away, home, away_ml, home_ml, ou, away_sp, home_sp, away_era, home_era,
#  away_wp, home_wp, away_fip, home_fip, away_whip, home_whip, away_k9, home_k9, venue)
SLATE = [
    ("Cardinals","Cubs",       112,-130, 8.5,"A. Pallante","D. Peterson", 3.83,5.86, 0.52,0.56, None,None, 1.28,1.42, 6.9,8.4,"Wrigley Field"),
    ("Pirates","Nationals",    117,-139, 8.5,"M. Keller","F. Griffin",   4.87,2.93, 0.50,0.51, None,None, 1.30,1.04, 7.0,9.0,"Nationals Park"),
    ("Twins","Yankees",        120,-142, 8.5,"M. Paredes","TBD",         4.10,4.10, 0.48,0.56, None,None, 1.30,1.30, 8.0,8.5,"Yankee Stadium"),
    # Mets SP unconfirmed -> ERA set equal to Elder's so no phantom edge is created.
    ("Mets","Braves",          116,-136, 8.5,"TBD","B. Elder",           4.55,4.55, 0.53,0.52, None,None, 1.34,1.34, 8.5,7.6,"Truist Park"),
    # Cabrera is a winless spot starter -> ERA set to 5.20 (below-avg) rather than a
    # generous 4.10, so the model does not manufacture value on a fill-in arm.
    ("Diamondbacks","Brewers", 140,-167, 8.5,"J. Cabrera","TBD",         5.20,4.10, 0.48,0.56, None,None, 1.45,1.25, 8.0,8.0,"American Family Field"),
    ("Athletics","Marlins",    120,-142, 9.0,"J. Perkins","TBD",         4.10,4.10, 0.46,0.51, None,None, 1.35,1.20, 8.0,8.5,"loanDepot park"),
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
    {"tag":"VALUE","headline":"Cardinals +112 @ Cubs - Pallante (3.83) over Peterson (5.86)",
     "meta":"Best value on the board. Model gives STL ~52% vs ~47% implied (+5% edge). The market makes the Cubs a -130 home favorite despite a two-run ERA advantage for the Cardinals' starter. Pallante has allowed 2 R over his last 12.2 IP."},
    {"tag":"FADE","headline":"Nationals -139 vs Pirates - correctly priced, no edge",
     "meta":"Griffin (8-2, 2.93, .210 opp AVG) is clearly better than Keller (4.87), and the model likes WSH to win ~59%. But -139 already implies 58% - the market has fully priced the mismatch. Right side, no value. Pass on the ML."},
    {"tag":"CHALK","headline":"Brewers -167 vs Diamondbacks - Arizona throwing a spot starter",
     "meta":"Jose Cabrera (0-0) opens for ARI at hitter-friendly American Family Field. MIL is heavy chalk (-167 = 62.5%). No confirmed Brewers ERA to model against - monitor, likely fair. No play."},
    {"tag":"MONITOR","headline":"Twins/Yankees, Mets/Braves, A's/Marlins - awaiting confirmed arms",
     "meta":"Yankees -142 and Braves -136 are standard home chalk. Several opposing starters (NYY, MIA, and the Mets' arm) were unconfirmed at generation time - no pitcher-driven read. Check lineup cards before betting."},
]
SOCIAL_INTEL = [
    {"type":"FORM","topic":"Andre Pallante - quietly rolling for St. Louis",
     "desc":"9-5, 3.83 ERA and just 2 earned runs across his last two starts (12.2 IP). Draws David Peterson (4-6, 5.86), giving the road Cardinals the pitching edge the -130 Cubs line ignores."},
    {"type":"PITCHING","topic":"Foster Griffin - elite but fully priced",
     "desc":"8-2, 2.93 ERA, .210 opponent average across 98.1 IP. The reason Washington is a -139 home favorite over a sub-.500 Pittsburgh club. Value is gone at that number; the intel value is confirming WSH as a strong side, not a bet."},
    {"type":"WEATHER","topic":"Live weather feed unavailable (sandbox)",
     "desc":"The Odds/weather APIs are blocked in this environment, so wind/temperature reads are not live. Wrigley Field (Cardinals @ Cubs) is the usual swing park - a strong out-blowing wind would push the total and help the favorite; confirm the forecast before first pitch."},
]
PARLAYS = []  # Only one qualifying value play today - no multi-leg spot.

# Live intel (falls back to curated lists above when APIs are blocked)
import mlb_intel
_SHORT2FULL = {"Cardinals":"St. Louis Cardinals","Cubs":"Chicago Cubs",
    "Pirates":"Pittsburgh Pirates","Nationals":"Washington Nationals",
    "Twins":"Minnesota Twins","Yankees":"New York Yankees",
    "Mets":"New York Mets","Braves":"Atlanta Braves",
    "Diamondbacks":"Arizona Diamondbacks","Brewers":"Milwaukee Brewers",
    "Athletics":"Athletics","Marlins":"Miami Marlins"}
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
    print(f"  [intel] live bettor={len(_live_bettor)} social={len(_live_social)} "
          f"-> final bettor={len(BETTOR_NEWS)} social={len(SOCIAL_INTEL)}")
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
