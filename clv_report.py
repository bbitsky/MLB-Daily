"""clv_report.py -- Honest backtest at REAL closing prices + closing-line value.

Uses your trained model + historical closing moneylines (load_odds.py) to grade
the model at ACTUAL closing odds instead of the flat -110 assumption, and to show
whether the model's picks beat the market's closing number (CLV).

Run it after you have games AND odds for the same seasons:
    python mlb_data.py --build --seasons 2018 2019 2020   (you already have 2021)
    python mlb_train.py
    python clv_report.py
Only games with a matching closing line are counted.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import mlb_data, mlb_train, load_odds


def _implied(ml):
    ml = float(ml)
    return 100.0 / (ml + 100.0) if ml > 0 else abs(ml) / (abs(ml) + 100.0)

def _profit(ml):          # profit on a 1-unit winning bet
    ml = float(ml)
    return ml / 100.0 if ml > 0 else 100.0 / abs(ml)


def run(edge_threshold=0.03, out_of_sample=True):
    """Grade the model at real closing prices + closing-line value.

    out_of_sample=True (default) uses walk-forward predictions (train on prior
    seasons, predict the held-out season) so no game is graded by a model that
    trained on it. Falls back to the in-sample final model only if walk-forward
    is unavailable (single season), with a loud warning -- in-sample ROI/CLV is
    optimistic and must not be trusted.
    """
    df = mlb_data.load_dataset_from_db()
    oos = None
    if out_of_sample:
        try:
            oos = mlb_train.walk_forward_oos_probs(df)
        except Exception as e:
            print(f"  [clv] walk-forward failed ({e}); falling back to in-sample.")
            oos = None
    if oos is not None and oos.notna().any():
        df = df.loc[oos.dropna().index]
        probs = oos.dropna().values
        print("  Mode: OUT-OF-SAMPLE (walk-forward by season) -- honest estimate.")
    else:
        print("  " + "!"*64)
        print("  Mode: IN-SAMPLE fallback -- model predicts its own training games.")
        print("  ROI@close and AvgCLV below are OPTIMISTIC. Add >=2 seasons of data")
        print("  (python mlb_data.py --build --seasons ...) for an out-of-sample read.")
        print("  " + "!"*64)
        model, feats = mlb_train.load_model()
        X, y = mlb_train.build_features(df)
        df = df.loc[X.index]
        probs = model.predict_proba(X[feats])[:, 1]

    seasons, matched, missing = {}, 0, 0
    for (_, row), p_away in zip(df.iterrows(), probs):
        try:
            season = int(row["season"]); date = str(row["game_date"])[:10]
        except Exception:
            continue
        rec = load_odds.lookup(date, row["away_team"], row["home_team"])
        if not rec or rec.get("away_close") is None or rec.get("home_close") is None:
            missing += 1
            continue
        matched += 1
        a_ml, h_ml = rec["away_close"], rec["home_close"]
        a_imp, h_imp = _implied(a_ml), _implied(h_ml)
        tot = a_imp + h_imp
        a_fair, h_fair = a_imp / tot, h_imp / tot          # de-vigged market probs
        away_edge = p_away - a_fair
        home_edge = (1 - p_away) - h_fair
        if max(away_edge, home_edge) < edge_threshold:
            continue
        s = seasons.setdefault(season, {"bets": 0, "w": 0, "pl": 0.0, "clv": 0.0})
        away_win = int(row.get("away_win", 0)) == 1
        if away_edge >= home_edge:
            won = away_win; s["pl"] += _profit(a_ml) if won else -1.0
            s["clv"] += (p_away - a_imp)      # model prob vs market's implied (beat-the-number proxy)
        else:
            won = not away_win; s["pl"] += _profit(h_ml) if won else -1.0
            s["clv"] += ((1 - p_away) - h_imp)
        s["bets"] += 1; s["w"] += int(won)

    print(f"\n  Games matched to a closing line: {matched}  (no odds match: {missing})")
    print(f"  {'Season':7} {'Bets':>5} {'W-L':>10} {'Win%':>6} {'ROI@close':>10} {'AvgCLV':>8}")
    tot_bets = tot_w = 0; tot_pl = tot_clv = 0.0
    for yr in sorted(seasons):
        s = seasons[yr]; n = s["bets"]
        if not n:
            continue
        tot_bets += n; tot_w += s["w"]; tot_pl += s["pl"]; tot_clv += s["clv"]
        print(f"  {yr:7} {n:5d} {s['w']:5d}-{n-s['w']:<4d} {100*s['w']/n:5.1f}% "
              f"{100*s['pl']/n:+9.1f}% {100*s['clv']/n:+7.1f}%")
    if tot_bets:
        print(f"  {'ALL':7} {tot_bets:5d} {tot_w:5d}-{tot_bets-tot_w:<4d} "
              f"{100*tot_w/tot_bets:5.1f}% {100*tot_pl/tot_bets:+9.1f}% {100*tot_clv/tot_bets:+7.1f}%")
    print("\n  ROI@close = return per unit at ACTUAL closing prices.")
    print("  AvgCLV    = avg (model prob − market implied). Positive = model finds value the market doesn't.")


if __name__ == "__main__":
    run()
