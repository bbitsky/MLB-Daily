"""
mlb_train.py — Feature engineering + model training for MLB Betting Model v3

Features used (all derivable from MLB Stats API + pybaseball at game time):
  - FIP differential (away_fip - home_fip), falls back to ERA diff
  - ERA differential (away_era - home_era)
  - Away/home team win%
  - Bullpen ERA differential
  - Park factor, is_dome, umpire run factor
  - Away starter QS rate, Home starter QS rate
  - Away team rest advantage
  - H2H win%, last 10 games runs scored
  - Implied probability from closing moneyline (for calibration only — not a feature)

Model: Logistic Regression (baseline) + XGBoost (primary)
Backtest: walk-forward by season (train on N seasons, test on N+1)
"""

import json
import numpy as np


class NumpyEncoder(json.JSONEncoder):
    """JSON encoder that handles numpy scalar and array types."""
    def default(self, obj):
        if isinstance(obj, np.integer):
            return int(obj)
        if isinstance(obj, np.floating):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        return super().default(obj)
import pandas as pd
import joblib
import sqlite3
from datetime import datetime
from pathlib import Path
from sklearn.linear_model import LogisticRegression
from sklearn.calibration import CalibratedClassifierCV
from sklearn.metrics import log_loss, brier_score_loss, roc_auc_score
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline
import xgboost as xgb

from mlb_data import load_dataset_from_db, DB_PATH

MODEL_PATH = Path(__file__).parent / "data" / "mlb_model.pkl"
SCALER_PATH = Path(__file__).parent / "data" / "mlb_scaler.pkl"


# ─────────────────────────────────────────────
# FEATURE ENGINEERING
# ─────────────────────────────────────────────

LEAGUE_AVG_ERA = 4.20  # approximate MLB average ERA

FEATURES = [
    "fip_diff", "away_fip_norm", "home_fip_norm",
    "xfip_diff", "away_xfip_norm", "home_xfip_norm",
    "era_diff", "away_era_norm", "home_era_norm",
    "bullpen_era_diff", "away_bullpen_era_norm", "home_bullpen_era_norm",
    "win_pct_diff",
    "ops_diff",
    "vs_sp_ops_diff",            # team OPS vs opp starter's handedness
    "h2h_away_win_pct",
    "away_last10_runs", "home_last10_runs",
    "park_factor", "is_dome", "ump_run_factor",
    "rest_diff", "away_short_rest", "home_short_rest",
    "streak_diff",               # away_streak - home_streak (+N away on win streak)
    "away_streak_norm", "home_streak_norm",
    "def_rank_diff",             # home_def_rank - away_def_rank (positive = away better defense)
    "is_day_game",
]


def build_features(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series]:
    """
    Transform raw game DataFrame into model-ready features.
    Returns (X, y) where y=1 means away team won.
    """
    df = df.copy()

    # Drop rows with missing critical fields
    df = df.dropna(subset=["away_era", "home_era", "away_win"])

    # ── ERA features ──
    df["era_diff"]      = df["away_era"] - df["home_era"]     # positive = away disadvantage
    df["away_era_norm"] = (df["away_era"] - LEAGUE_AVG_ERA) / 1.5
    df["home_era_norm"] = (df["home_era"] - LEAGUE_AVG_ERA) / 1.5

    # ── FIP features (fall back to ERA when missing) ──
    away_fip = df.get("away_fip", pd.Series(np.nan, index=df.index)).fillna(df["away_era"])
    home_fip = df.get("home_fip", pd.Series(np.nan, index=df.index)).fillna(df["home_era"])
    df["fip_diff"]      = away_fip - home_fip
    df["away_fip_norm"] = (away_fip - LEAGUE_AVG_ERA) / 1.5
    df["home_fip_norm"] = (home_fip - LEAGUE_AVG_ERA) / 1.5

    # ── xFIP features (fall back to FIP, then ERA when missing) ──
    away_xfip = df.get("away_xfip", pd.Series(np.nan, index=df.index)).fillna(away_fip)
    home_xfip = df.get("home_xfip", pd.Series(np.nan, index=df.index)).fillna(home_fip)
    df["xfip_diff"]      = away_xfip - home_xfip
    df["away_xfip_norm"] = (away_xfip - LEAGUE_AVG_ERA) / 1.5
    df["home_xfip_norm"] = (home_xfip - LEAGUE_AVG_ERA) / 1.5

    # ── OPS differential (team offense) ──
    away_ops = df.get("away_ops", pd.Series(0.720, index=df.index)).fillna(0.720)
    home_ops = df.get("home_ops", pd.Series(0.720, index=df.index)).fillna(0.720)
    df["ops_diff"] = away_ops - home_ops   # positive = away offense advantage

    # ── Win% features ──
    df["away_win_pct"] = df.get("away_w", pd.Series(0, index=df.index)).fillna(0) / \
        np.maximum(
            df.get("away_w", pd.Series(1, index=df.index)).fillna(1) +
            df.get("away_l", pd.Series(1, index=df.index)).fillna(1),
            1
        )
    df["home_win_pct"] = df.get("home_w", pd.Series(0, index=df.index)).fillna(0) / \
        np.maximum(
            df.get("home_w", pd.Series(1, index=df.index)).fillna(1) +
            df.get("home_l", pd.Series(1, index=df.index)).fillna(1),
            1
        )
    df["win_pct_diff"] = df["away_win_pct"] - df["home_win_pct"]

    # ── Bullpen ERA features ──
    away_bullpen_era = df.get("away_bullpen_era", pd.Series(np.nan, index=df.index)).fillna(LEAGUE_AVG_ERA)
    home_bullpen_era = df.get("home_bullpen_era", pd.Series(np.nan, index=df.index)).fillna(LEAGUE_AVG_ERA)
    df["bullpen_era_diff"]       = away_bullpen_era - home_bullpen_era
    df["away_bullpen_era_norm"]  = (away_bullpen_era - LEAGUE_AVG_ERA) / 1.5
    df["home_bullpen_era_norm"]  = (home_bullpen_era - LEAGUE_AVG_ERA) / 1.5

    # ── Park factor ──
    df["park_factor"] = df["park_factor"].fillna(1.0)

    # ── Dome ──
    df["is_dome"] = df["is_dome"].fillna(0).astype(int)

    # ── QS rate ──
    df["away_qs_rate"] = df.get("away_qs_rate", pd.Series(0.5, index=df.index)).fillna(0.5)
    df["home_qs_rate"] = df.get("home_qs_rate", pd.Series(0.5, index=df.index)).fillna(0.5)
    df["qs_diff"]      = df["away_qs_rate"] - df["home_qs_rate"]

    # ── Rest days ──
    df["away_rest"] = df.get("away_rest", pd.Series(5, index=df.index)).fillna(5)
    df["home_rest"] = df.get("home_rest", pd.Series(5, index=df.index)).fillna(5)
    df["rest_diff"] = df["away_rest"] - df["home_rest"]
    df["away_short_rest"] = (df["away_rest"] <= 1).astype(int)  # true back-to-back only
    df["home_short_rest"] = (df["home_rest"] <= 1).astype(int)

    # ── H2H win% ──
    df["h2h_away_win_pct"] = df.get("h2h_away_win_pct", pd.Series(0.5, index=df.index)).fillna(0.5)

    # ── Umpire run factor ──
    df["ump_run_factor"] = df.get("ump_run_factor", pd.Series(1.0, index=df.index)).fillna(1.0)

    # ── Last 10 runs scored ──
    df["away_last10_runs"] = df.get("away_last10_runs", pd.Series(4.5, index=df.index)).fillna(4.5)
    df["home_last10_runs"] = df.get("home_last10_runs", pd.Series(4.5, index=df.index)).fillna(4.5)

    # ── vs SP handedness OPS split ──
    # Positive = away offense has bigger OPS advantage vs today's pitcher hand
    away_vs_sp_ops = df.get("away_vs_sp_ops", pd.Series(0.720, index=df.index)).fillna(0.720)
    home_vs_sp_ops = df.get("home_vs_sp_ops", pd.Series(0.720, index=df.index)).fillna(0.720)
    df["vs_sp_ops_diff"] = away_vs_sp_ops - home_vs_sp_ops

    # ── Win streak features ──
    # Signed: +N = win streak of N, -N = loss streak of N
    away_streak = df.get("away_streak", pd.Series(0, index=df.index)).fillna(0)
    home_streak = df.get("home_streak", pd.Series(0, index=df.index)).fillna(0)
    df["streak_diff"]      = away_streak - home_streak
    df["away_streak_norm"] = away_streak / 10.0   # normalize to ~[-1, +1]
    df["home_streak_norm"] = home_streak / 10.0

    # ── Defensive rank features ──
    # Rank 1 = best defense; normalize so better defense = higher value
    away_def_rank = df.get("away_def_rank", pd.Series(15, index=df.index)).fillna(15)
    home_def_rank = df.get("home_def_rank", pd.Series(15, index=df.index)).fillna(15)
    # def_rank_diff: positive = home has better defense (lower rank number)
    df["def_rank_diff"] = home_def_rank - away_def_rank

    # ── Day/night game ──
    df["is_day_game"] = df.get("is_day_game", pd.Series(0, index=df.index)).fillna(0).astype(int)

    X = df[FEATURES].astype(float)
    y = df["away_win"].astype(int)
    return X, y


def compute_record_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add rolling win% features by computing cumulative records within each season.
    Works on the full historical DataFrame sorted by date.
    Resets team records at the start of each new season.
    """
    df = df.copy().sort_values("game_date")

    away_w_list, away_l_list = [], []
    home_w_list, home_l_list = [], []

    current_season = None
    records: dict[str, list[int]] = {}

    for _, row in df.iterrows():
        season = row["season"]

        # Reset records at each new season boundary
        if season != current_season:
            current_season = season
            records = {}

        at = row["away_team"]
        ht = row["home_team"]

        if at not in records: records[at] = [0, 0]
        if ht not in records: records[ht] = [0, 0]

        away_w_list.append(records[at][0])
        away_l_list.append(records[at][1])
        home_w_list.append(records[ht][0])
        home_l_list.append(records[ht][1])

        # Update after appending (records reflect state BEFORE this game)
        if row["away_win"] == 1:
            records[at][0] += 1
            records[ht][1] += 1
        else:
            records[at][1] += 1
            records[ht][0] += 1

    df["away_w"] = away_w_list
    df["away_l"] = away_l_list
    df["home_w"] = home_w_list
    df["home_l"] = home_l_list
    return df


# ─────────────────────────────────────────────
# MODEL TRAINING
# ─────────────────────────────────────────────

def train_model(df: pd.DataFrame, model_type: str = "xgboost") -> dict:
    """
    Train and evaluate the model using walk-forward season validation.
    Returns trained model + scaler + metrics.
    """
    df = compute_record_features(df)
    seasons = sorted(df["season"].unique())

    if len(seasons) < 2:
        print("⚠️  Need at least 2 seasons for walk-forward validation. Training on all data.")
        X, y = build_features(df)
        model = _fit_model(X, y, model_type)
        return {"model": model, "seasons": seasons, "metrics": {}}

    print(f"\nWalk-forward validation across seasons: {seasons}")
    print("─" * 50)

    all_metrics = []

    # Walk-forward: train on [0..i-1], test on [i]
    for i in range(1, len(seasons)):
        train_seasons = seasons[:i]
        test_season   = seasons[i]

        train_df = df[df["season"].isin(train_seasons)]
        test_df  = df[df["season"] == test_season]

        X_train, y_train = build_features(train_df)
        X_test,  y_test  = build_features(test_df)

        # Sanity check: warn and drop zero-variance features (no signal to learn)
        zero_var_cols = [c for c in X_train.columns if X_train[c].std() < 1e-6]
        if zero_var_cols:
            print(f"  ⚠️  Dropping zero-variance features: {zero_var_cols}")
            X_train = X_train.drop(columns=zero_var_cols)
            X_test  = X_test.drop(columns=zero_var_cols)

        # First fold only: show feature value ranges to confirm data is populated
        if i == 1:
            print(f"\n  Feature value ranges (first fold):")
            for col in X_train.columns:
                print(f"    {col}: mean={X_train[col].mean():.3f}, std={X_train[col].std():.3f}, "
                      f"min={X_train[col].min():.3f}, max={X_train[col].max():.3f}")
            print()

        model = _fit_model(X_train, y_train, model_type)

        probs = np.array(model.predict_proba(X_test))[:, 1]
        preds = (probs >= 0.5).astype(int)

        acc    = (preds == y_test).mean()
        ll     = log_loss(y_test, probs)
        brier  = brier_score_loss(y_test, probs)
        auc    = roc_auc_score(y_test, probs)
        roi    = _simulate_roi(probs, y_test.values, threshold=0.05)

        metrics = {
            "test_season":   test_season,
            "train_seasons": train_seasons,
            "n_train":       len(X_train),
            "n_test":        len(X_test),
            "accuracy":      acc,
            "log_loss":      ll,
            "brier":         brier,
            "auc":           auc,
            "roi_5pct_edge": roi["roi"],
            "bets_placed":   roi["bets"],
            "win_rate":      roi["win_rate"],
        }
        all_metrics.append(metrics)

        print(f"  Train {[str(s) for s in train_seasons]} → Test {test_season}: "
              f"Acc={acc:.3f} | AUC={auc:.3f} | Brier={brier:.3f} | "
              f"ROI={roi['roi']:+.1%} ({roi['bets']} bets, {roi['win_rate']:.1%} win rate)")

    # Final model trained on ALL data
    print("\nTraining final model on all available data...")
    X_all, y_all = build_features(df)
    # Drop zero-variance features from full dataset too
    zero_var_all = [c for c in X_all.columns if X_all[c].std() < 1e-6]
    if zero_var_all:
        print(f"  Dropping zero-variance features from final model: {zero_var_all}")
        X_all = X_all.drop(columns=zero_var_all)
    active_features = list(X_all.columns)
    final_model = _fit_model(X_all, y_all, model_type)

    # Save model + active feature list together
    MODEL_PATH.parent.mkdir(exist_ok=True)
    joblib.dump({"model": final_model, "features": active_features}, MODEL_PATH)
    print(f"✅ Model saved to {MODEL_PATH}")
    print(f"   Active features ({len(active_features)}): {active_features}")

    # Print feature importance if XGBoost
    if model_type == "xgboost" and hasattr(final_model, "feature_importances_"):
        importances = pd.Series(
            final_model.feature_importances_,
            index=active_features
        ).sort_values(ascending=False)
        print("\nFeature importance (XGBoost):")
        for feat, imp in importances.items():
            bar = "█" * int(imp * 100)
            print(f"  {feat:30s} {imp:.4f}  {bar}")

    metrics_df = pd.DataFrame(all_metrics)
    print(f"\n{'─'*50}")
    print(f"Average accuracy:  {metrics_df['accuracy'].mean():.3f}")
    print(f"Average AUC:       {metrics_df['auc'].mean():.3f}")
    print(f"Average ROI:       {metrics_df['roi_5pct_edge'].mean():+.1%}")
    print(f"Total test games:  {metrics_df['n_test'].sum()}")

    # Save metrics to JSON
    metrics_out = {
        "generated": datetime.now().isoformat(),
        "by_season": all_metrics,
        "overall": {
            "avg_accuracy": float(metrics_df["accuracy"].mean()),
            "avg_auc": float(metrics_df["auc"].mean()),
            "avg_roi": float(metrics_df["roi_5pct_edge"].mean()),
            "total_test_games": int(metrics_df["n_test"].sum()),
        }
    }
    metrics_path = Path(__file__).parent / "data" / "mlb_metrics.json"
    with open(metrics_path, "w") as f:
        json.dump(metrics_out, f, indent=2, cls=NumpyEncoder)
    print(f"  Metrics saved to {metrics_path}")

    return {
        "model":   final_model,
        "seasons": seasons,
        "metrics": metrics_df.to_dict("records"),
    }


def _fit_model(X: pd.DataFrame, y: pd.Series, model_type: str = "xgboost"):
    """Fit and return the chosen model."""
    if model_type == "logistic":
        model = Pipeline([
            ("scaler", StandardScaler()),
            ("clf",    CalibratedClassifierCV(
                LogisticRegression(C=1.0, max_iter=1000, random_state=42),
                cv=5
            )),
        ])
        model.fit(X, y)
        return model

    elif model_type == "xgboost":
        model = xgb.XGBClassifier(
            n_estimators=300,
            max_depth=4,
            learning_rate=0.05,
            subsample=0.8,
            colsample_bytree=0.8,
            eval_metric="logloss",
            random_state=42,
            verbosity=0,
        )
        model.fit(X, y)
        return model

    else:
        raise ValueError(f"Unknown model type: {model_type}")


def _simulate_roi(probs: np.ndarray, outcomes: np.ndarray,
                  threshold: float = 0.05, avg_ml: float = -110) -> dict:
    """
    Simulate flat-unit betting on games where edge ≥ threshold.
    Assumes -110 avg moneyline (can be made dynamic).
    """
    # Implied prob from -110
    implied = 110 / (110 + 100)  # 0.524

    bets = 0
    wins = 0
    profit = 0.0

    for prob, outcome in zip(probs, outcomes):
        edge = prob - implied
        if edge >= threshold:
            bets += 1
            if outcome == 1:
                wins += 1
                profit += 100 / 110  # win $100 on $110 bet → net +0.909u
            else:
                profit -= 1.0

    roi    = profit / bets if bets > 0 else 0.0
    win_rate = wins / bets if bets > 0 else 0.0
    return {"roi": roi, "bets": bets, "wins": wins, "win_rate": win_rate}


# ─────────────────────────────────────────────
# PREDICT (for daily picks)
# ─────────────────────────────────────────────

def load_model():
    """Load the trained model from disk. Returns (model, active_features)."""
    if not MODEL_PATH.exists():
        raise FileNotFoundError(
            f"No trained model found at {MODEL_PATH}. "
            "Run: python mlb_train.py"
        )
    obj = joblib.load(MODEL_PATH)
    if isinstance(obj, dict):
        return obj["model"], obj["features"]
    # Legacy format: raw model, use full FEATURES list
    return obj, FEATURES


def predict_game(model, game_features: dict, active_features: list = None) -> float:
    """
    Predict away team win probability for a single game.
    game_features: dict matching the feature columns in build_features()
    active_features: list of features the model was trained on (from load_model)
    Returns float 0-1 (away win probability).
    """
    if active_features is None:
        active_features = FEATURES
    row = {}
    away_era = game_features.get("away_era", LEAGUE_AVG_ERA)
    home_era = game_features.get("home_era", LEAGUE_AVG_ERA)

    # FIP: fall back to ERA if not provided
    away_fip = game_features.get("away_fip", away_era)
    home_fip = game_features.get("home_fip", home_era)
    if away_fip is None or (isinstance(away_fip, float) and np.isnan(away_fip)):
        away_fip = away_era
    if home_fip is None or (isinstance(home_fip, float) and np.isnan(home_fip)):
        home_fip = home_era

    away_bullpen_era = game_features.get("away_bullpen_era", LEAGUE_AVG_ERA)
    home_bullpen_era = game_features.get("home_bullpen_era", LEAGUE_AVG_ERA)
    if away_bullpen_era is None: away_bullpen_era = LEAGUE_AVG_ERA
    if home_bullpen_era is None: home_bullpen_era = LEAGUE_AVG_ERA

    park_factor = game_features.get("park_factor", 1.0)
    away_qs   = game_features.get("away_qs_rate", 0.5)
    home_qs   = game_features.get("home_qs_rate", 0.5)
    away_rest = game_features.get("away_rest", 5)
    home_rest = game_features.get("home_rest", 5)
    away_wp   = game_features.get("away_win_pct", 0.5)
    home_wp   = game_features.get("home_win_pct", 0.5)

    # xFIP: fall back to FIP, then ERA if not provided
    away_xfip = game_features.get("away_xfip", away_fip)
    home_xfip = game_features.get("home_xfip", home_fip)
    if away_xfip is None or (isinstance(away_xfip, float) and np.isnan(away_xfip)):
        away_xfip = away_fip
    if home_xfip is None or (isinstance(home_xfip, float) and np.isnan(home_xfip)):
        home_xfip = home_fip

    away_ops = game_features.get("away_ops", 0.720) or 0.720
    home_ops = game_features.get("home_ops", 0.720) or 0.720

    away_vs_sp_ops = game_features.get("away_vs_sp_ops", 0.720) or 0.720
    home_vs_sp_ops = game_features.get("home_vs_sp_ops", 0.720) or 0.720

    away_streak = game_features.get("away_streak", 0) or 0
    home_streak = game_features.get("home_streak", 0) or 0

    away_def_rank = game_features.get("away_def_rank", 15) or 15
    home_def_rank = game_features.get("home_def_rank", 15) or 15

    row["fip_diff"]              = away_fip - home_fip
    row["away_fip_norm"]         = (away_fip - LEAGUE_AVG_ERA) / 1.5
    row["home_fip_norm"]         = (home_fip - LEAGUE_AVG_ERA) / 1.5
    row["xfip_diff"]             = away_xfip - home_xfip
    row["away_xfip_norm"]        = (away_xfip - LEAGUE_AVG_ERA) / 1.5
    row["home_xfip_norm"]        = (home_xfip - LEAGUE_AVG_ERA) / 1.5
    row["ops_diff"]              = away_ops - home_ops
    row["vs_sp_ops_diff"]        = away_vs_sp_ops - home_vs_sp_ops
    row["era_diff"]              = away_era - home_era
    row["away_era_norm"]         = (away_era - LEAGUE_AVG_ERA) / 1.5
    row["home_era_norm"]         = (home_era - LEAGUE_AVG_ERA) / 1.5
    row["bullpen_era_diff"]      = away_bullpen_era - home_bullpen_era
    row["away_bullpen_era_norm"] = (away_bullpen_era - LEAGUE_AVG_ERA) / 1.5
    row["home_bullpen_era_norm"] = (home_bullpen_era - LEAGUE_AVG_ERA) / 1.5
    row["away_qs_rate"]          = away_qs
    row["home_qs_rate"]          = home_qs
    row["qs_diff"]               = away_qs - home_qs
    row["win_pct_diff"]          = away_wp - home_wp
    row["h2h_away_win_pct"]      = game_features.get("h2h_away_win_pct", 0.5)
    row["away_last10_runs"]      = game_features.get("away_last10_runs", 4.5)
    row["home_last10_runs"]      = game_features.get("home_last10_runs", 4.5)
    row["park_factor"]           = park_factor
    row["is_dome"]               = int(game_features.get("is_dome", False))
    row["ump_run_factor"]        = game_features.get("ump_run_factor", 1.0)
    row["rest_diff"]             = away_rest - home_rest
    row["away_short_rest"]       = int(away_rest <= 1)
    row["home_short_rest"]       = int(home_rest <= 1)
    row["streak_diff"]           = away_streak - home_streak
    row["away_streak_norm"]      = away_streak / 10.0
    row["home_streak_norm"]      = home_streak / 10.0
    row["def_rank_diff"]         = home_def_rank - away_def_rank
    row["is_day_game"]           = int(game_features.get("is_day_game", False))

    X = pd.DataFrame([row])[active_features]
    prob = np.array(model.predict_proba(X))[0, 1]
    return float(prob)


# ---------------------------------------------
# MAIN -- run training
# ---------------------------------------------

if __name__ == "__main__":
    print("MLB Model Trainer v3")
    print("=" * 50)

    df = load_dataset_from_db()

    if df.empty:
        print("\nNo data in database yet.")
        print("Run: python mlb_data.py --build --seasons 2021 2022 2023 2024 2025")
        print("Takes ~45-60 minutes due to rate-limiting. Run once, cached in mlb.db.\n")
    else:
        seasons = sorted(df["season"].unique().tolist())
        total   = len(df)
        print(f"\nLoaded {total} games across seasons: {seasons}")

        print("\nTraining XGBoost model (walk-forward validation)...")
        result = train_model(df, model_type="xgboost")

        print("\n--- Results ---")
        for s in result.get("metrics", []):
            print(f"  Season {s.get('test_season','?')}: AUC={s.get('auc',0):.3f}  "
                  f"bets={s.get('bets_placed',0)}  win_rate={s.get('win_rate',0):.1%}  "
                  f"ROI={s.get('roi_5pct_edge',0):+.1%}")
        print(f"\n  Model saved to data/mlb_model.pkl")
        print(f"  Metrics saved to data/mlb_metrics.json")
