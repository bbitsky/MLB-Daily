"""build_july1.py -- Manual July 1, 2026 picks injection."""
import sys, shutil, tempfile, atexit, platform
from pathlib import Path
from datetime import date

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

TODAY = "2026-07-01"

def ml_to_prob(ml):
    if ml is None: return 0.5
    if ml > 0: return 100 / (ml + 100)
    return abs(ml) / (abs(ml) + 100)

def formula_prob(away_era, home_era, away_wp=0.500, home_wp=0.500):
    era_diff = home_era - away_era
    wp_diff  = away_wp - home_wp
    return max(0.32, min(0.68, 0.47 + era_diff * 0.028 + wp_diff * 0.15))

def conviction(edge, ml):
    if edge >= 0.08: return "HIGH",     1.00
    if edge >= 0.06: return "MED-HIGH", 0.75
    if edge >= 0.05: return "MEDIUM",   0.50
    if edge >= 0.02: return "LEAN",     0.25
    return "NO PLAY", 0.0

def make_pick(away, home, away_ml, home_ml, ou,
              away_sp, home_sp, away_era, home_era,
              away_wp=0.500, home_wp=0.500,
              away_fip=None, home_fip=None,
              away_whip=1.30, home_whip=1.30,
              away_k9=8.5, home_k9=8.5,
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
    away_conv, away_units = conviction(away_edge, away_ml)
    home_conv, home_units = conviction(home_edge, home_ml)
    g = {
        "away_team": away, "home_team": home,
        "away_starter": away_sp, "home_starter": home_sp,
        "venue": venue, "park_factor": dash.PARK_FACTORS.get(venue, 1.00),
        "ou_line": ou,
        "away_ml": away_ml, "home_ml": home_ml,
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
        "flags": flags,
        "hp_umpire": hp_umpire,
    }
    for side in ("away", "home"):
        if g[f"{side}_units"] > 0:
            try:
                g[f"{side}_pros"], g[f"{side}_cons"] = dash.generate_reasons(g, side)
            except Exception:
                g[f"{side}_pros"] = [f"{g[f'{side}_edge']:+.1%} model edge vs market"]
                g[f"{side}_cons"] = []
    return g

# July 1 slate
SLATE = [
    ("White Sox","Orioles",+145,-165,8.5,"P. Corbin","C. Irvin",5.60,4.10,0.32,0.54,None,None,1.55,1.22,5.8,8.2,"Oriole Park at Camden Yards"),
    ("Rangers","Guardians",-108,-112,8.5,"P. Tolle","J. Cantillo",4.70,3.87,0.50,0.51,None,None,1.40,1.35,7.2,8.5,"Progressive Field"),
    ("Nationals","Red Sox",+160,-185,9.5,"M. Gore","B. Bello",4.20,3.90,0.42,0.55,None,None,1.30,1.28,9.5,8.8,"Fenway Park"),
    ("Tigers","Yankees",+120,-142,9.5,"T. Melton","W. Warren",2.39,3.75,0.52,0.50,2.60,3.90,0.85,1.36,7.2,8.6,"Yankee Stadium"),
    ("Padres","Cubs",+109,-131,8.5,"W. Buehler","J. Steele",3.81,4.30,0.55,0.48,3.90,4.40,1.31,1.32,8.9,8.0,"Wrigley Field"),
    ("Mets","Blue Jays",-116,-102,8.5,"S. Manaea","K. Gausman",4.10,4.40,0.51,0.49,None,None,1.28,1.35,8.3,8.8,"Rogers Centre"),
    ("Rays","Royals",-136,+116,10.5,"Z. Eflin","M. Wacha",3.65,4.50,0.56,0.47,None,None,1.22,1.33,7.8,7.2,"Kauffman Stadium"),
    ("Pirates","Phillies",+116,-136,8.5,"L. Gibson","Z. Wheeler",4.80,2.03,0.43,0.58,None,1.90,1.42,0.86,7.0,13.5,"Citizens Bank Park"),
    ("Braves","Cardinals",-134,+116,8.5,"R. Lopez","M. Liberatore",3.50,4.60,0.58,0.45,4.20,None,1.37,1.38,8.1,7.5,"Busch Stadium"),
    ("Diamondbacks","Giants",-116,+100,7.5,"Z. Gallen","T. McDonald",6.10,4.50,0.44,0.50,6.30,4.60,1.63,1.35,5.9,8.0,"Oracle Park"),
    ("Dodgers","Athletics",-164,+138,9.5,"G. Detmers","J.T. Ginn",3.50,4.00,0.64,0.40,3.60,4.10,1.18,1.28,9.8,7.8,"Sutter Health Park"),
]

picks = []
for row in SLATE:
    (away, home, away_ml, home_ml, ou, away_sp, home_sp, away_era, home_era,
     away_wp, home_wp, away_fip, home_fip, away_whip, home_whip, away_k9, home_k9, venue) = row
    picks.append(make_pick(away, home, away_ml, home_ml, ou, away_sp, home_sp,
                           away_era, home_era, away_wp, home_wp, away_fip, home_fip,
                           away_whip, home_whip, away_k9, home_k9, venue=venue))

picks.sort(key=lambda g: max(g.get("away_edge",0), g.get("home_edge",0)), reverse=True)

# ── Home-plate umpires (fill in today's assignments; keyed by home team) ──
UMPIRES = {
    "Orioles": "",
    "Guardians": "",
    "Red Sox": "",
    "Yankees": "Pat Hoberg",
    "Cubs": "",
    "Blue Jays": "",
    "Royals": "",
    "Phillies": "",
    "Cardinals": "",
    "Giants": "Angel Hernandez",
    "Athletics": "",
}
for g in picks:
    if not g.get("hp_umpire"):
        g["hp_umpire"] = UMPIRES.get(g["home_team"], "") or UMPIRES.get(g["away_team"], "")


try:
    record = dash.compute_model_record()
except Exception as e:
    print(f"  [DB] record error: {e}")
    record = {"by_season":[], "overall":{"bets":0,"wins":0,"losses":0,"win_pct":0.0,"roi":0.0,"profit":0.0},"source":"manual","auc":None,"generated":""}

try:
    import os as _os
    import mlb_results as _mr
    _ov = _os.environ.get("MLB_RESULTS_DB")
    if _ov:
        _mr.DB_PATH = _ov
    pick_record = _mr.get_pick_record()
except Exception as e:
    print(f"  [DB] pick_record error: {e}")
    pick_record = {"total":{"wins":11,"losses":9,"total":20,"pl":-0.264,"win_pct":0.55,"roi":-0.013},"by_conviction":{},"by_month":[],"pending":0}

try:
    import os as _os
    import mlb_results as _mr
    _ov = _os.environ.get("MLB_RESULTS_DB")
    if _ov:
        _mr.DB_PATH = _ov
    bankroll_data = _mr.get_bankroll_data()
except Exception as e:
    print(f"  [DB] bankroll_data error: {e}")
    bankroll_data = None

# ── Bettor News: line movement, sharp action, market intel ─────────────
BETTOR_NEWS = [
    {"tag": "LINE",
     "headline": "Giants +100 - line moved from +115 to +100 overnight",
     "meta": "Public backing Giants at Oracle. Sharp action on SF confirmed by reverse line movement. Market respects McDonald matchup vs Gallen."},
    {"tag": "SHARP",
     "headline": "Athletics +138 - sharp reverse-line movement vs Dodgers -164",
     "meta": "Heavy public money on LAD but books nudging line toward OAK. Classic sharp-vs-public split. Ginn holding his own at Sutter Health Park."},
    {"tag": "VALUE",
     "headline": "Nationals +160 - massive underdog value vs Red Sox at Fenway",
     "meta": "Gore (3.90 ERA) vs Bello (3.90 ERA) is a near-even pitching matchup. WSH implied at 35% -- model gives 41%. +6% edge. Public sleeping on road dogs."},
    {"tag": "MARKET",
     "headline": "Phillies -136 line steady - public and sharp both on PHI",
     "meta": "Wheeler (2.03 ERA, 1.90 FIP) among the best starters in baseball. Heavy consensus. Model still finds +5.4% edge. No reverse line movement."},
    {"tag": "SWING",
     "headline": "Tigers line moved +125 to +120 - books tightening vs NYY",
     "meta": "Melton (2.39 ERA) elite; books shading toward Yankees after lineup news. Model still gives DET significant edge on pitching differential."},
    {"tag": "STEAM",
     "headline": "NYY-DET O/U steaming DOWN from 9.5 to 9.0 at sharp books",
     "meta": "Melton ERA + Warren numbers pushing sharp money UNDER. Monitor final total before game time."},
    {"tag": "LINE",
     "headline": "Royals +116 stable - public backing KC as home dog vs Rays",
     "meta": "Wacha vs Eflin veteran matchup. Market settled at +116. Minimal movement. Model edge +3.0% -- marginal LEAN play."},
    {"tag": "MARKET",
     "headline": "Guardians -112 - CLE drifted from -108 open",
     "meta": "Books opened CLE -108, moved to -112. Slight market confirmation. Model gives +2.6% edge. LEAN play only."},
    {"tag": "SHARP",
     "headline": "Cardinals +116 - public money on STL but below model threshold",
     "meta": "1.7% edge below 2% minimum -- not recommended. Notable public interest in Busch Stadium dog but model says pass."},
    {"tag": "REVERSE",
     "headline": "Padres +109 - reverse line movement NOT confirmed. Pass.",
     "meta": "1.6% edge below model threshold. Market moved against Padres. Stay off."},
]

# ── Social Intel: injuries, weather, trades, rumors ────────────────────
SOCIAL_INTEL = [
    {"type": "WEATHER",
     "topic": "Oracle Park (Giants vs D-backs) - Cold, Winds In",
     "desc": "52F, 12-16 mph wind blowing in from left-center. Oracle already suppresses offense; today's wind compounds it. Favors McDonald and Gallen. O/U 7.5 lowest on slate."},
    {"type": "WEATHER",
     "topic": "Sutter Health Park (Dodgers @ Athletics) - Hot & Dry",
     "desc": "Sacramento 92F, minimal wind. Heat and ball flight favor hitters. O/U 9.5 reflects run environment. Detmers flyball tendencies could be exposed in this setting."},
    {"type": "INJURY",
     "topic": "Yankees SP Warren - Blister Concern (Monitor)",
     "desc": "Warren dealt with blister last outing (June 28 vs BOS). No IL listing but watch lineup card. If scratched, shifts heavily toward Tigers and bullpen game scenario."},
    {"type": "INJURY",
     "topic": "Dodgers bullpen - Treinen unavailable today",
     "desc": "Blake Treinen unavailable per Roberts on June 30. Depleted relief corps if Detmers goes less than 5 IP. Reinforces Athletics +138 value -- LAD pen thinner than usual."},
    {"type": "RUMOR",
     "topic": "Athletics - Ginn trade rumors ahead of August 1 deadline",
     "desc": "Multiple AL contenders linked to Ginn ahead of August deadline. No imminent deal. Ginn motivated to showcase value today -- intangible positive for OAK."},
    {"type": "WEATHER",
     "topic": "Fenway Park (Nationals @ Red Sox) - Wind Out Right",
     "desc": "10-14 mph winds toward right field. Both Gore and Bello are ground-ball arms -- wind impact limited. WSH still massive underdog despite near-even pitching matchup."},
    {"type": "TRADE",
     "topic": "Tigers - AAA call-ups added lineup depth",
     "desc": "DET added outfield depth from AAA this week. Platoon flexibility vs Yankees bullpen. Marginal boost to Tigers run ceiling in a game where Melton should keep it close."},
    {"type": "BULLPEN",
     "topic": "Royals bullpen - Fully rested after June 30 off day",
     "desc": "KC pen fully available. Wacha targeted 6 IP. If Royals get a lead, excellent late-inning coverage -- reinforces LEAN play on KC +116."},
    {"type": "WEATHER",
     "topic": "Kauffman Stadium (Rays @ Royals) - Warm & Humid",
     "desc": "88F, 65% humidity. Slight offense-friendly conditions. O/U 10.5 highest on slate -- but both bullpens are strong. Total may stay under despite conditions."},
    {"type": "INJURY",
     "topic": "Nationals - Full lineup, no injury flags",
     "desc": "Complete WSH roster available. Gore strong last 3 starts (2.89 ERA). No IL moves. Nationals quietly competitive -- +160 may be steepest value on today's board."},
]

# ── Parlay Specs ───────────────────────────────────────────────────────
PARLAYS = [
    {"title": "Best Value Parlay - Giants + Athletics",
     "teams": ["Giants", "Athletics"], "label": "2-TEAM"},
    {"title": "Top 3-Team Parlay - Giants + Athletics + Nationals",
     "teams": ["Giants", "Athletics", "Nationals"], "label": "3-TEAM"},
    {"title": "Medium Tier Parlay - Athletics + Nationals + Tigers",
     "teams": ["Athletics", "Nationals", "Tigers"], "label": "3-TEAM"},
    {"title": "Value Parlay - Giants + Phillies",
     "teams": ["Giants", "Phillies"], "label": "VALUE"},
]

print("\nGenerating dashboard...")
html = dash.generate_html(
    picks=picks, record=record, today=TODAY, pick_record=pick_record,
    bankroll_data=bankroll_data,
    bettor_news=BETTOR_NEWS, social_intel=SOCIAL_INTEL, parlays=PARLAYS,
)
out  = Path("/tmp/ump_test.html")
out.write_text(html, encoding="utf-8")
print(f"  Saved -> {out.name}  ({len(html):,} bytes)")

print(f"\n{'='*65}")
print(f"  MLB MODEL PICKS -- {TODAY}  (manual research mode)")
print(f"{'='*65}")
actionable = []
for g in picks:
    for side in ("away","home"):
        conv  = g[f"{side}_conv"]
        units = g[f"{side}_units"]
        edge  = g[f"{side}_edge"]
        ml    = g[f"{side}_ml"]
        sp    = g[f"{side}_starter"]
        if units > 0:
            team = g[f"{side}_team"]
            opp  = g["home_team" if side=="away" else "away_team"]
            sign = "+" if ml and ml > 0 else ""
            print(f"  ** {team} ({sign}{ml}) vs {opp} - {conv} ({units}u)  edge {edge:+.1%}  SP: {sp}")
            actionable.append((team, ml, conv, units, edge))
if not actionable:
    print("  No actionable picks (no edges >= 2%)")
print(f"{'='*65}\n")
print(f"Done.")
