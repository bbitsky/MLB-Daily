"""build_july2.py -- Manual July 2, 2026 picks injection (getaway-day slate)."""
import sys, shutil, tempfile, atexit, platform
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

TODAY = "2026-07-02"

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

# July 2 slate (getaway-day card). Odds/pitchers: FanDuel Research 7-2-2026.
SLATE = [
    ("Pirates","Phillies", 104,-122, 9.5,"J. Jones","A. Rangel", 5.76,4.50, 0.44,0.56, None,None, 1.42,1.30, 8.0,7.4,"Citizens Bank Park"),
    ("Reds","Brewers",     136,-162, 9.0,"A. Abbott","S. Drohan", 3.88,3.12, 0.48,0.62, None,None, 1.30,1.20, 6.8,5.5,"American Family Field"),
    ("Marlins","Rockies", -126, 108,12.0,"M. Meyer","K. Freeland", 2.53,7.25, 0.51,0.38, None,None, 1.08,1.61, 7.5,6.0,"Coors Field"),
    ("Rays","Royals",     -118, 100,10.5,"TBD","TBD",             4.10,4.10, 0.55,0.47, None,None, 1.30,1.35, 8.0,7.5,"Kauffman Stadium"),
]

picks = []
for row in SLATE:
    (away, home, away_ml, home_ml, ou, away_sp, home_sp, away_era, home_era,
     away_wp, home_wp, away_fip, home_fip, away_whip, home_whip, away_k9, home_k9, venue) = row
    picks.append(make_pick(away, home, away_ml, home_ml, ou, away_sp, home_sp,
                           away_era, home_era, away_wp, home_wp, away_fip, home_fip,
                           away_whip, home_whip, away_k9, home_k9, venue=venue))
picks.sort(key=lambda g: max(g.get("away_edge",0), g.get("home_edge",0)), reverse=True)

UMPIRES = {"Phillies":"", "Brewers":"", "Rockies":"", "Royals":""}
for g in picks:
    if not g.get("hp_umpire"):
        g["hp_umpire"] = UMPIRES.get(g["home_team"], "")

try:
    record = dash.compute_model_record()
except Exception as e:
    print(f"  [DB] record error: {e}")
    record = {"by_season":[], "overall":{"bets":0,"wins":0,"losses":0,"win_pct":0.0,"roi":0.0,"profit":0.0},"source":"manual","auc":None,"generated":""}

try:
    import mlb_results as _mr
    _mr.DB_PATH = str(tmp_db)
    pick_record = _mr.get_pick_record()
except Exception as e:
    print(f"  [DB] pick_record error: {e}")
    pick_record = None

try:
    import mlb_results as _mr
    _mr.DB_PATH = str(tmp_db)
    bankroll_data = _mr.get_bankroll_data()
except Exception as e:
    print(f"  [DB] bankroll_data error: {e}")
    bankroll_data = None

BETTOR_NEWS = [
    {"tag":"VALUE","headline":"Marlins -126 @ Rockies - Meyer (2.53, 9-0) vs Freeland (7.25, 1-7)",
     "meta":"Largest pitching mismatch on the slate. Model gives MIA 62% vs 56% implied (+6.4% edge). Caveat: Coors Field (PF 1.38) inflates variance - size accordingly."},
    {"tag":"LEAN","headline":"Phillies -122 vs Pirates - Rangel over Jones (5.76 ERA)",
     "meta":"Model PHI 58% vs 55% implied (+3.4%). Harper/Schwarber core at Citizens Bank Park. FanDuel model agrees (PHI 55.2%). LEAN only."},
    {"tag":"FADE","headline":"Brewers -162 vs Reds - no edge despite heavy chalk",
     "meta":"Drohan (3.12) over Abbott (3.88) but -162 prices MIL at 62%; model has 57%. Overpriced favorite. Pass."},
    {"tag":"MARKET","headline":"Rays -118 @ Royals - pitchers unconfirmed at generation time",
     "meta":"FanDuel model favors TB (55.9%). No starter ERAs confirmed for this getaway game - no model play. Monitor lineup cards."},
]
SOCIAL_INTEL = [
    {"type":"WEATHER","topic":"Coors Field (Marlins @ Rockies) - Thin Air, O/U 12.0",
     "desc":"Highest total on the board (12.0). Meyer's ground-ball profile travels better to altitude than most, but any pitcher edge is muted at Coors. Favor MIA moneyline over the run line."},
    {"type":"NOTE","topic":"Getaway-day slate - light card",
     "desc":"Thursday July 2 is a short getaway-day schedule (mostly early afternoon starts). Fewer spots means fewer edges - discipline over volume."},
    {"type":"FORM","topic":"Max Meyer - undefeated, elite 2026",
     "desc":"Meyer 9-0, 2.53 ERA, 112 K. Among NL ERA leaders. Freeland (1-7, 7.25) is one of the worst qualified ERAs in baseball. Clear talent gap even accounting for park."},
]
PARLAYS = [
    {"title":"Value 2-Team - Marlins + Phillies","teams":["Marlins","Phillies"],"label":"VALUE"},
]

# ── Live intel: weather + betting trends (falls back to curated lists) ────────
import mlb_data as _md
import mlb_intel
_SHORT2FULL = {"Pirates":"Pittsburgh Pirates","Phillies":"Philadelphia Phillies",
    "Reds":"Cincinnati Reds","Brewers":"Milwaukee Brewers","Marlins":"Miami Marlins",
    "Rockies":"Colorado Rockies","Rays":"Tampa Bay Rays","Royals":"Kansas City Royals"}
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
    # Use pure live intel when it's rich (>=3 items); otherwise prepend whatever
    # live data we got to the curated fallback so the sections stay substantial.
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
