"""build_july12.py -- Manual July 12, 2026 picks injection (Sunday).

Nightly automated fallback build: MLB Stats API / Odds API are proxy-blocked in
the sandbox and the trained model is unavailable (xgboost not installed, games
table empty), so win probabilities come from mlb_edge.formula_prob (ERA
differential) -- the documented model fallback. Pitchers/odds gathered via web
research (FantasyPros probable-pitchers grid + per-game odds previews).
"""
import os, sys, shutil, tempfile
from pathlib import Path
P = Path(__file__).parent; sys.path.insert(0, str(P))
_off = str(Path(tempfile.mkdtemp(prefix="mlb_j12_")) / "mlb.db")
try: shutil.copy2(str(P/"data"/"mlb.db"), _off)
except Exception as e: print("  [DB] seed skipped:", e)
os.environ["MLB_DB_PATH"] = _off
import mlb_dashboard as dash
import mlb_data as _md
import mlb_edge as E
TODAY = "2026-07-12"

def ml_to_prob(ml):
    if ml is None: return 0.5
    return (100/(ml+100)) if ml > 0 else (abs(ml)/(abs(ml)+100))
def novig_away(a,h):
    ai=ml_to_prob(a); hi=ml_to_prob(h)
    return 0.5 if ai+hi==0 else ai/(ai+hi)

def make_pick(away,home,away_ml,home_ml,ou,away_sp,home_sp,away_prob,away_era,home_era,venue="",game_time="",nf_real=True):
    if away_era is None: away_era=4.15
    if home_era is None: home_era=4.15
    home_prob=1.0-away_prob
    ai=ml_to_prob(away_ml); hi=ml_to_prob(home_ml)
    pf=dash.PARK_FACTORS.get(venue,1.00)
    ae=E.adjusted_edge(away_prob-ai,pf); he=E.adjusted_edge(home_prob-hi,pf)
    ac,au=E.conviction(ae,away_ml); hc,hu=E.conviction(he,home_ml)
    if not nf_real:
        au=hu=0; ac=hc="MONITOR"
    g={"away_team":away,"home_team":home,"away_starter":away_sp,"home_starter":home_sp,
       "venue":venue,"park_factor":pf,"game_time":game_time,"ou_line":ou,
       "away_ml":away_ml,"home_ml":home_ml,"away_ml_best":away_ml,"home_ml_best":home_ml,
       "away_ml_book":"consensus","n_books":1,"line_outlier":False,"line_outlier_gap":0.0,
       "away_prob":away_prob,"home_prob":home_prob,"away_implied":ai,"home_implied":hi,
       "away_edge":ae,"home_edge":he,"away_conv":ac,"home_conv":hc,"away_units":au,"home_units":hu,
       "away_era":away_era,"home_era":home_era,"away_fip":away_era,"home_fip":home_era,
       "away_xfip":away_era,"home_xfip":home_era,"away_whip":1.30,"home_whip":1.30,
       "away_k9":8.5,"home_k9":8.5,"away_gs":15,"home_gs":15,
       "away_last5_era":away_era,"home_last5_era":home_era,"away_trend":"--","home_trend":"--",
       "away_wp":0.5,"home_wp":0.5,"away_rest":5,"home_rest":5,"away_ops":0.720,"home_ops":0.720,
       "away_wrc_plus":100,"home_wrc_plus":100,"away_qs_rate":0.50,"home_qs_rate":0.50,
       "away_starts_detail":[],"home_starts_detail":[],"flags":[],"hp_umpire":""}
    for s in ("away","home"):
        if g[s+"_units"]>0:
            try: g[s+"_pros"],g[s+"_cons"]=dash.generate_reasons(g,s)
            except Exception: g[s+"_pros"]=[f"{g[s+'_edge']:+.1%} model edge"]; g[s+"_cons"]=[]
    return g

# (away, home, away_ml, home_ml, ou, away_sp, home_sp, away_era, home_era, venue, time)
SLATE=[
 ("Athletics","Chicago White Sox",-115,103,9.0,"J. Ginn","N. Schultz",3.10,6.00,"Rate Field","2:10 PM ET"),
 ("Arizona Diamondbacks","Los Angeles Dodgers",240,-303,8.5,"M. Bratt","E. Sheehan",3.00,4.91,"Dodger Stadium","4:10 PM ET"),
 ("Atlanta Braves","St. Louis Cardinals",-140,120,8.5,"J. Ritchie","D. May",4.60,4.85,"Busch Stadium","2:15 PM ET"),
 ("Kansas City Royals","Baltimore Orioles",134,-158,9.0,"S. Lugo","S. Baz",3.85,4.35,"Oriole Park at Camden Yards","1:35 PM ET"),
 ("Boston Red Sox","New York Mets",112,-132,8.0,"P. Tolle","Z. Thornton",3.14,3.20,"Citi Field","1:40 PM ET"),
 ("Chicago Cubs","Cincinnati Reds",-135,115,9.0,"M. Boyd","A. Abbott",4.57,3.52,"Great American Ball Park","1:40 PM ET"),
 ("Cleveland Guardians","Miami Marlins",105,-115,8.0,"J. Cantillo","T. Phillips",4.00,4.70,"loanDepot park","1:40 PM ET"),
 ("Colorado Rockies","San Francisco Giants",128,-152,8.5,"M. Lorenzen","T. McDonald",6.46,5.46,"Oracle Park","4:05 PM ET"),
 ("Philadelphia Phillies","Detroit Tigers",-108,-112,7.5,"Z. Wheeler","T. Skubal",2.28,3.06,"Comerica Park","1:40 PM ET"),
 ("Houston Astros","Texas Rangers",110,-130,8.0,"C. Javier","M. Gore",4.60,3.95,"Globe Life Field","2:35 PM ET"),
 ("Los Angeles Angels","Minnesota Twins",112,-135,8.5,"J. Soriano","T. Bradley",3.90,4.05,"Target Field","2:10 PM ET"),
 ("Milwaukee Brewers","Pittsburgh Pirates",100,-120,8.0,"R. Gasser","P. Skenes",4.20,2.10,"PNC Park","12:15 PM ET"),
 ("Seattle Mariners","Tampa Bay Rays",122,-145,7.5,"E. Hancock","I. Seymour",4.45,3.55,"Rays home","1:40 PM ET"),
 ("Toronto Blue Jays","San Diego Padres",-126,104,8.0,"K. Gausman","G. Marquez",4.32,5.02,"Petco Park","4:10 PM ET"),
 ("New York Yankees","Washington Nationals",-190,160,9.0,"W. Warren","C. Cavalli",3.95,4.90,"Nationals Park","1:35 PM ET"),
]
picks=[]
for (a,h,aml,hml,ou,asp,hsp,aera,hera,venue,gt) in SLATE:
    ap=E.formula_prob(aera,hera)   # ERA-differential fallback -> AWAY win prob
    picks.append(make_pick(a,h,aml,hml,ou,asp,hsp,ap,aera,hera,venue=venue,game_time=gt,nf_real=True))
picks.sort(key=lambda g:max(g.get("away_edge",0),g.get("home_edge",0)),reverse=True)
try:
    import mlb_freeze
    picks=mlb_freeze.load_or_freeze(picks,TODAY,str(P),meta={"source":"build_july12"},refresh=("--refresh" in sys.argv))
except Exception as e: print("  [freeze]",e)
try:
    cands=[]
    for g in picks:
        for s in ("away","home"):
            if g.get(s+"_units",0)>0:
                cands.append({"pick_team":g[s+"_team"],"ml":g[s+"_ml"],"my_prob":g[s+"_prob"],"implied_prob":g[s+"_implied"],"edge":g[s+"_edge"],"conviction":g[s+"_conv"],"units":g[s+"_units"],"bet":1})
    print("  [log] wrote", E.log_picks(str(_md.DB_PATH),TODAY,cands), "pick(s)")
except Exception as e: print("  [log] skipped:",e)
try: record=dash.compute_model_record()
except Exception as e:
    print("  [rec]",e); record={"by_season":[],"overall":{"bets":0,"wins":0,"losses":0,"win_pct":0.0,"roi":0.0,"profit":0.0},"source":"manual","auc":None,"generated":""}
try:
    import mlb_results as _mr; _mr.DB_PATH=str(_md.DB_PATH)
    pr=_mr.get_pick_record(); bd=_mr.get_bankroll_data()
except Exception as e:
    print("  [rec]",e); pr=None; bd=None
try:
    html=dash.generate_html(picks=picks,record=record,today=TODAY,pick_record=pr,bankroll_data=bd)
    out=P/f"mlb_dashboard_{TODAY}.html"; out.write_text(html,encoding="utf-8")
    print("  Saved ->",out.name,f"({len(html):,} bytes)")
except Exception as e: print("  [dash]",e)
print("\n"+"="*60+f"\n  MLB PICKS -- {TODAY}\n"+"="*60)
ap=False
for g in picks:
    for s in ("away","home"):
        if g.get(s+"_units",0)>0:
            ap=True; tm=g[s+"_team"]; opp=g["home_team" if s=="away" else "away_team"]
            ml=g[s+"_ml"]; sg="+" if ml and ml>0 else ""
            print(f"  ** {tm} ({sg}{ml}) vs {opp} - {g[s+'_conv']} ({g[s+'_units']}u)  edge {g[s+'_edge']:+.1%}")
if not ap: print("  (no qualifying value picks)")
print("="*60)
