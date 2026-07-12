"""build_july6.py -- Manual July 6, 2026 picks injection (Monday, 8-game slate).

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

TODAY = "2026-07-06"

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
    ("Philadelphia Phillies","Kansas City Royals",-172,144, 8.5,"C. Sanchez","N. Cameron", 0.6423, 1.62,None, 0.556,0.400,"Kauffman Stadium"),
    ("New York Yankees","Tampa Bay Rays",         100,-118, 8.0,"C. Schlittler","G. Jax",   0.4984, 1.50,None, 0.551,0.598,"Tropicana Field"),
    ("Houston Astros","Washington Nationals",     116,-134, 8.5,"M. Burrows","M. Mikolas",  0.4718, 5.58,5.44, 0.489,0.505,"Nationals Park"),
    ("New York Mets","Atlanta Braves",            110,-130, 8.0,"F. Peralta","R. Lopez",    0.4366, 4.81,3.31, 0.411,0.591,"Truist Park"),
    ("Milwaukee Brewers","St. Louis Cardinals",  -116,-102, 8.5,"S. Drohan","D. May",       0.5510, 3.12,None, 0.625,0.540,"Busch Stadium"),
    ("Arizona Diamondbacks","San Diego Padres",  -110,-106, 8.0,"B. Pfaadt","W. Buehler",   0.4298, None,None, 0.494,0.489,"Petco Park"),
    ("Toronto Blue Jays","San Francisco Giants", -110,-106, 7.5,"K. Gausman","L. Roupp",    0.4013, None,3.80, 0.467,0.416,"Oracle Park"),
    ("Colorado Rockies","Los Angeles Dodgers",    150,-178, 9.0,"K. Freeland","E. Lauer",   0.3573, None,None, 0.407,0.656,"Dodger Stadium"),
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
picks = mlb_freeze.load_or_freeze(picks, TODAY, str(P), meta={"source":"build_july6"}, refresh=_refresh)

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
    {"tag":"VALUE","headline":"Giants -106 vs Blue Jays -- numberFire's biggest model/market gap on the board",
     "meta":"San Francisco (37-52) is priced as a coin-flip home team (-106) but numberFire models the Giants at 59.9% behind Landen Roupp vs Toronto's Kevin Gausman -- an +8.4% edge, the only qualifying play tonight. Sized MEDIUM (0.5u), NOT up: SF is a weak team and the edge leans entirely on the pitching read, so it is a monitor-for-late-lineup/scratch spot. The week-1 audit (favorites 5-8) is why the mlb_edge ladder caps favorites at 0.5u."},
    {"tag":"NEAR-MISS","headline":"Padres -106 vs Diamondbacks -- +5.6% edge, just under the favorite threshold",
     "meta":"numberFire has San Diego at 57.0% at home (Buehler vs Pfaadt) while the market prices near pick'em (-106, 51.5%). That +5.6% edge would be a LEAN on an underdog, but the recalibrated ladder needs >=6% to back a FAVORITE (favorites went 5-8 / -27% ROI in week 1). Right side, fair number -- pass, or parlay anchor at most."},
    {"tag":"CHALK","headline":"Phillies -172 & Dodgers -178 -- correct favorites, no value",
     "meta":"Cristopher Sanchez (1.62 ERA) and the Dodgers are dominant, but numberFire (64.2% / 64.3%) essentially matches the vig-inflated prices (63.2% / 64.0%). Fair numbers on both -- no edge, no bet."},
    {"tag":"MONITOR","headline":"Yankees +100 with Schlittler (1.50) -- elite arm, but model says true pick'em",
     "meta":"New York throws MLB-ERA-leader Cam Schlittler at +100, tempting on paper, but numberFire has it 49.8/50.2 because Tampa Bay is the better team at home. No edge -- the market already accounts for the ace."},
]
SOCIAL_INTEL = [
    {"type":"PITCHING","topic":"Landen Roupp vs Kevin Gausman -- the night's key mismatch read",
     "desc":"numberFire's Giants number (59.9% at home, near pick'em price) is driven almost entirely by favoring Roupp over Gausman. It's the model's one standout edge -- but on a 37-52 team, so treat lineup/bullpen news as decisive before the 9:45 ET first pitch."},
    {"type":"FORM","topic":"Cristopher Sanchez & Cam Schlittler -- two aces headline the slate",
     "desc":"Sanchez owns the NL's lowest ERA (1.62); Schlittler leads MLB at 1.50. Both are correctly priced tonight (Phillies -172, Yankees +100) -- the market is not giving away either arm."},
    {"type":"WEATHER","topic":"No Coors game tonight; live wind/temperature feeds unavailable",
     "desc":"The Rockies are at Dodger Stadium (not altitude), so the July-2 Coors variance lesson doesn't apply to tonight's card. Live weather APIs remain blocked in this environment; no park-variance discount was triggered on the 8-game slate."},
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
