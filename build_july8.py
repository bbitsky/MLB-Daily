"""build_july8.py -- Manual July 8, 2026 picks injection (Wednesday).

Data: web-researched -- RotoWire live board (moneylines + probable starters),
FanGraphs/FantasyPros probables grid. The MLB Stats API / Odds API 403 in the
sandbox; FanDuel Research, numberFire and DraftKings sportsbook were all blocked
this run, and public pages (ESPN, Covers) served stale July-7 caches -- so NO
independent per-game model win-probability feed was available tonight. Rather than
fabricate edges, each game is priced to the DE-VIGGED FAIR two-sided market
(away_prob = fair implied), giving zero constructed edge and a disciplined
no-qualifying-play slate. Sizing still runs through the week-1-calibrated mlb_edge
ladder. A Windows-side data pull + trained-model run would restore true edges.
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

TODAY = "2026-07-08"

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

# (away, home, away_ml, home_ml, ou, away_sp, home_sp, away_prob,
#  away_era, home_era, away_wp, home_wp, venue)
# DATA NOTE (2026-07-08): FanDuel Research / numberFire / DraftKings were all blocked
# in this run and public pages (ESPN, Covers) were serving stale July-7 caches, so no
# independent per-game model win-probability feed was available tonight. Live moneylines
# and probable starters were pulled from the RotoWire live board (best-of-book).
# With no independent model feed, away_prob = the DE-VIGGED FAIR probability of the live
# two-sided market (zero constructed edge). This intentionally yields a disciplined,
# no-qualifying-play slate rather than fabricating edges without model inputs.
# ERAs left None (2026-sim ERAs conflict across secondary sources; not reliably paired).
SLATE = [
    ("Toronto Blue Jays","San Francisco Giants",  -109,-102, 6.5,"D. Cease","L. Webb",       0.5081, None,None, 0.462,0.422,"Oracle Park"),
    ("Chicago Cubs","Baltimore Orioles",           111,-124, 9.0,"C. Rea","D. Kremer",       0.4613, None,None, 0.556,0.462,"Oriole Park at Camden Yards"),
    ("Athletics","Detroit Tigers",                 138,-154, 8.5,"J. Springs","T. Melton",   0.4093, None,None, 0.456,0.444,"Comerica Park"),
    ("New York Yankees","Tampa Bay Rays",          110,-122, 7.5,"G. Cole","S. McClanahan",  0.4643, None,None, 0.556,0.591,"George M. Steinbrenner Field"),
    ("Seattle Mariners","Miami Marlins",          -127, 118, 8.5,"G. Kirby","T. Phillips",   0.5495, None,None, 0.516,0.538,"loanDepot park"),
    ("Atlanta Braves","Pittsburgh Pirates",        105,-116, 8.5,"G. Holmes","J. Jones",     0.4760, None,None, 0.584,0.505,"PNC Park"),
    ("Houston Astros","Washington Nationals",      118,-131, 9.0,"S. Arrighetti","F. Griffin", 0.4472, None,None, 0.484,0.511,"Nationals Park"),
    ("Kansas City Royals","New York Mets",         124,-146, 9.0,"S. Kolek","C. Scott",      0.4293, None,None, 0.407,0.418,"Citi Field"),
    ("Boston Red Sox","Chicago White Sox",         107,-119, 8.0,"J. Bennett","D. Martin",   0.4706, None,None, 0.455,0.528,"Rate Field"),
    ("Cleveland Guardians","Minnesota Twins",      117,-130, 8.5,"S. Cecconi","C. Prielipp", 0.4491, None,None, 0.516,0.484,"Target Field"),
    ("Milwaukee Brewers","St. Louis Cardinals",   -134, 123, 8.0,"K. Harrison","M. McGreevy", 0.5609, None,None, 0.629,0.534,"Busch Stadium"),
    ("Los Angeles Angels","Texas Rangers",         140,-153, 7.5,"W. Urena","M. Gore",       0.4080, None,None, 0.396,0.500,"Globe Life Field"),
    ("Colorado Rockies","Los Angeles Dodgers",     205,-225, 9.5,"R. Feltner","R. Sasaki",   0.3214, None,None, 0.402,0.652,"Dodger Stadium"),
    ("Arizona Diamondbacks","San Diego Padres",    125,-139, 7.5,"J. Cabrera","M. King",     0.4332, None,None, 0.500,0.489,"Petco Park"),
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
picks = mlb_freeze.load_or_freeze(picks, TODAY, str(P), meta={"source":"build_july8"}, refresh=_refresh)

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
    {"tag":"NO-FEED","headline":"No independent model feed tonight -- slate priced to the de-vigged market",
     "meta":"FanDuel Research, numberFire and DraftKings were all blocked this run and ESPN/Covers served stale July-7 caches. Live moneylines + starters came from the RotoWire board, but with no independent win-probability feed each game is priced to its de-vigged fair line -- zero constructed edge by design. 0 units staked; this is a data-driven pass, not a read on the games."},
    {"tag":"MARQUEE","headline":"Cole, Webb, Gore, Sasaki, King headline -- but all fairly priced to us tonight",
     "meta":"Gerrit Cole (@TBR), Logan Webb (vs TOR), MacKenzie Gore (vs LAA), Roki Sasaki (vs COL) and Michael King (vs ARI) are the arms to watch. Without a model overlay we can't claim the market is wrong on any of them, so they're monitors, not bets."},
    {"tag":"CHALK","headline":"Dodgers -225 (Sasaki vs Rockies) & Rangers -153 (deGrom... Gore) -- heavy favorites, no stated edge",
     "meta":"LAD -225 over Colorado prices at ~69% and Texas -153 at ~60%. Both look like correct favorites, but with no independent model we take no position on whether they're mispriced. Pass."},
    {"tag":"NO-LINE","headline":"Phillies @ Reds not posted -- starter uncertainty (Keller/King vs Burns)",
     "meta":"The RotoWire board showed no moneyline for Philadelphia @ Cincinnati at pull time (probable-starter uncertainty). The game is left off the actionable slate rather than priced on a guess."},
]
SOCIAL_INTEL = [
    {"type":"DISCIPLINE","topic":"14 games carried, priced to market -- a disciplined, zero-edge pass night",
     "desc":"Because no independent per-game win-probability feed was reachable (FanDuel/numberFire/DraftKings blocked; ESPN/Covers cached to July 7), every game was priced to its de-vigged fair line. That produces small negative edges on both sides of every game -- nothing clears the calibrated favorite (>=6%) or underdog (>=2%) thresholds. Zero units staked."},
    {"type":"DATA","topic":"Degraded data environment -- live board via RotoWire, model feed unavailable",
     "desc":"MLB Stats/Odds APIs 403 in the sandbox. Live moneylines and probable starters were pulled from the RotoWire live board (best-of-book) via the browser; FanGraphs supplied the probables grid. FanDuel Research, numberFire and the DraftKings sportsbook were all blocked, so no independent model win-probability could be attached -- hence the market-devig fallback. Phillies@Reds had no posted line and was left off."},
    {"type":"FORM","topic":"Starter conflicts across sources on four teams",
     "desc":"Live board vs the probables grid disagreed on the Mariners (Kirby/Woo), Marlins (Phillips/Junk), Cardinals (McGreevy/Pallante) and Phillies (King/Keller). The RotoWire live board -- the odds source -- was used where it disagreed. None of it changes a market-priced, no-play conclusion."},
    {"type":"WEATHER","topic":"Live weather feeds unavailable; no altitude game on the card",
     "desc":"Colorado plays at Dodger Stadium, not Coors, so no park-variance discount was triggered. Live wind/temp APIs remain blocked in this environment."},
]
PARLAYS = []  # No qualifying value legs (market-devig slate) -> no multi-leg spot.

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

print(f"\n{'='*66}\n  MLB MODEL PICKS -- {TODAY}  (market-devig fallback)\n{'='*66}")
for g in picks:
    for side in ("away","home"):
        if g[f"{side}_units"] > 0:
            team=g[f"{side}_team"]; opp=g["home_team" if side=="away" else "away_team"]
            ml=g[f"{side}_ml"]; sign="+" if ml and ml>0 else ""
            print(f"  ** {team} ({sign}{ml}) vs {opp} - {g[f'{side}_conv']} ({g[f'{side}_units']}u)  edge {g[f'{side}_edge']:+.1%}  SP: {g[f'{side}_starter']}")
print(f"{'='*66}\nDone.")
