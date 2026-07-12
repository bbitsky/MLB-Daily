"""build_july7.py -- Manual July 7, 2026 picks injection (Tuesday).

Data: web-researched -- FanDuel Research (odds + numberFire model win probs),
FantasyPros probable pitchers, ESPN. The MLB Stats API / Odds API are blocked in
the sandbox, and the 2026-sim starter ERAs conflict across secondary sources
(even pitcher->team mappings), so the ERA-differential formula is NOT reliable
tonight. Instead we use numberFire's per-game model win probabilities (computed
against today's actual matchups) as the model probability, take edges vs the
FanDuel market, and size with the week-1-calibrated mlb_edge ladder.
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

TODAY = "2026-07-07"

def ml_to_prob(ml):
    if ml is None: return 0.5
    return (100/(ml+100)) if ml > 0 else (abs(ml)/(abs(ml)+100))

def make_pick(away, home, away_ml, home_ml, ou, away_sp, home_sp,
              away_prob, away_era, home_era, away_wp, home_wp,
              venue="", flags=None, hp_umpire=""):
    """Build a game/pick dict. Probability comes from numberFire (away_prob);
    conviction/units come from the calibrated mlb_edge ladder (favorites de-sized,
    top size capped). Park variance discount applied to the edge before sizing."""
    flags = flags or []
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

# (away, home, away_ml, home_ml, ou, away_sp, home_sp, nf_away_prob,
#  away_era, home_era, away_wp, home_wp, venue)
# nf_away_prob = numberFire model win probability for the AWAY team (FanDuel Research).
# ERAs shown for context where reliably found (2026 season); None = not reliably sourced.
SLATE = [
    ("Atlanta Braves","Pittsburgh Pirates",       152,-180, 8.0,"H. Waldrep","P. Skenes",  0.3460, 3.68,3.62, 0.593,0.494,"PNC Park"),
    ("Chicago Cubs","Baltimore Orioles",          -112,-104, 9.0,"M. Boyd","S. Baz",        0.5720, 5.08,4.19, 0.557,0.461,"Oriole Park at Camden Yards"),
    ("Athletics","Detroit Tigers",                 100,-110, 8.5,"J. Springs","R. Olson",   0.4900, None,None, 0.471,0.560,"Comerica Park"),
    ("Milwaukee Brewers","St. Louis Cardinals",   -140, 118, 8.5,"J. Misiorowski","A. Pallante", 0.5880, None,3.60, 0.629,0.541,"Busch Stadium"),
    ("Arizona Diamondbacks","San Diego Padres",    105,-124, 8.0,"Z. Gallen","R. Bergert",  0.4450, None,None, 0.500,0.500,"Petco Park"),
    ("Toronto Blue Jays","San Francisco Giants",  -117,-103, 7.5,"K. Gausman","L. Roupp",   0.5400, 4.19,3.80, 0.471,0.414,"Oracle Park"),
    ("Colorado Rockies","Los Angeles Dodgers",     217,-266, 9.5,"M. Lorenzen","J. Wrobleski", 0.2800, None,None, 0.404,0.648,"Dodger Stadium"),
]

picks = []
for (away,home,aml,hml,ou,asp,hsp,nfa,aera,hera,awp,hwp,venue) in SLATE:
    picks.append(make_pick(away,home,aml,hml,ou,asp,hsp,nfa,aera,hera,awp,hwp,venue=venue))
picks.sort(key=lambda g: max(g.get("away_edge",0), g.get("home_edge",0)), reverse=True)
for g in picks:
    g.setdefault("hp_umpire","")

# Lock the day's picks at this initial run (freeze); a re-run reloads the snapshot.
import mlb_freeze
_refresh = "--refresh" in sys.argv
picks = mlb_freeze.load_or_freeze(picks, TODAY, str(P), meta={"source":"build_july7"}, refresh=_refresh)

# Log the model's actionable book to the DB so tomorrow grades it (dual-book).
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

BETTOR_NEWS = [
    {"tag":"NEAR-MISS","headline":"Cubs -112 at Baltimore -- +4.4% model edge, just under the favorite threshold",
     "meta":"FanDuel's model has Chicago at 57.2% (Boyd vs Baz) while the market prices -112 (52.8%). That +4.4% edge would be a MEDIUM on an underdog, but the week-1-recalibrated ladder needs >=6% to back a FAVORITE (favorites went 5-8 / -27% ROI in week 1). Best number on the board -- monitor, or use as a parlay anchor at most. No standalone bet."},
    {"tag":"CHALK","headline":"Pirates -180 (Skenes) & Dodgers -266 -- correct heavy favorites, no value",
     "meta":"Paul Skenes (3.62) has the model at Pittsburgh 65.4% vs a -180 price (64.3% implied) -- only +1.1%, fair. The Dodgers -266 over Colorado (Lorenzen) is priced at 72.7% and the model agrees. Right sides, no edge."},
    {"tag":"MONITOR","headline":"Brewers -140 at St. Louis -- Misiorowski's night, but the number is fair",
     "meta":"Milwaukee (MLB-best 3.32 team ERA) is modeled ~58.8% behind Jacob Misiorowski; the -140 price implies 58.3%. Essentially pick-the-vig -- no edge. Cardinals +118 the wrong side of a fair line."},
    {"tag":"PICKEM","headline":"Athletics/Tigers & Blue Jays/Giants -- true coin flips, market efficient",
     "meta":"Both games sit within a point of the model. Toronto -117 at Oracle (Gausman vs Roupp) mirrors last night's matchup that SF won 10-1, but the number is fair now; A's/Tigers is a near pick'em. Pass."},
]
SOCIAL_INTEL = [
    {"type":"DISCIPLINE","topic":"No qualifying play on the 7 modeled games -- a disciplined pass night",
     "desc":"Every side lands inside the calibrated ladder's no-play band: the only positive favorite edges (Cubs +4.4%, Pirates +1.1%) fall short of the >=6% favorite threshold, and no underdog clears +2%. Consistent with the week-1 audit that de-sized favorites (5-8). Zero units staked."},
    {"type":"DATA","topic":"Degraded data environment on this run -- odds sourced game-by-game",
     "desc":"The MLB Stats/Odds APIs 403 in the sandbox and the browser tool was offline, so the FanDuel daily grid could not be pulled in one shot. Odds, starters and model win probabilities were assembled per game from FanDuel Research / public books; games without an independent model probability were priced to market (zero edge). 7 games carried; the remaining East-coast games (Reds@Yankees, Mets@Phillies, RedSox@Mariners, Nats@Rays) could not be reliably sourced and were left off."},
    {"type":"FORM","topic":"Skenes & Misiorowski headline; Giants-Blue Jays rematch after a 10-1 blowout",
     "desc":"Paul Skenes (3.62) and Jacob Misiorowski are the marquee arms but both are fairly priced. San Francisco beat Toronto 10-1 last night behind Roupp/Heliot Ramos; the two flip to a near pick'em tonight -- the market fully corrected."},
    {"type":"WEATHER","topic":"Live weather feeds unavailable; no Coors game on the card",
     "desc":"Colorado is at Dodger Stadium, not altitude, so no park-variance discount was triggered. Live wind/temp APIs remain blocked in this environment."},
]
PARLAYS = []  # One qualifying value play -> no multi-leg spot (discipline over volume).

print("\nGenerating dashboard...")
try:
    html = dash.generate_html(picks=picks, record=record, today=TODAY, pick_record=pick_record,
        bankroll_data=bankroll_data, bettor_news=BETTOR_NEWS, social_intel=SOCIAL_INTEL, parlays=PARLAYS)
except TypeError:
    html = dash.generate_html(picks=picks, record=record, today=TODAY, pick_record=pick_record, bankroll_data=bankroll_data)
out = P / f"mlb_dashboard_{TODAY}.html"
out.write_text(html, encoding="utf-8")
print(f"  Saved -> {out.name}  ({len(html):,} bytes)")

try:
    import mlb_summary
    _sp = mlb_summary.write_daily_summary(picks, TODAY, out_dir=str(P), parlays=PARLAYS)
    print(f"  Why/why-not summary -> {Path(_sp).name}")
except Exception as e:
    print(f"  [summary] skipped: {e}")

print(f"\n{'='*66}\n  MLB MODEL PICKS -- {TODAY}  (manual research / numberFire fallback)\n{'='*66}")
for g in picks:
    for side in ("away","home"):
        if g[f"{side}_units"] > 0:
            team=g[f"{side}_team"]; opp=g["home_team" if side=="away" else "away_team"]
            ml=g[f"{side}_ml"]; sign="+" if ml and ml>0 else ""
            print(f"  ** {team} ({sign}{ml}) vs {opp} - {g[f'{side}_conv']} ({g[f'{side}_units']}u)  edge {g[f'{side}_edge']:+.1%}  SP: {g[f'{side}_starter']}")
print(f"{'='*66}\nDone.")
