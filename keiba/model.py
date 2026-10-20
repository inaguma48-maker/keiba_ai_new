"""
Stage1: ability model (no market information).
Stage2: blend with the market proxy (final popularity) by a conditional logit.
Metrics are computed per race on probabilities normalised to sum to 1.
"""

from typing import Dict, List, Tuple

import numpy as np
import pandas as pd
from lightgbm import LGBMClassifier, early_stopping, log_evaluation

EPS = 1e-9


def normalize(race_ids: np.ndarray, raw: np.ndarray) -> np.ndarray:
    s = pd.Series(raw).groupby(race_ids).transform("sum").to_numpy()
    return raw / s


def fit_stage1(train: pd.DataFrame, valid: pd.DataFrame, feature_cols: List[str]) -> LGBMClassifier:
    model = LGBMClassifier(
        n_estimators=3000, learning_rate=0.03, num_leaves=31, min_child_samples=100,
        subsample=0.8, subsample_freq=1, colsample_bytree=0.8, reg_lambda=1.0,
        random_state=42, verbosity=-1)
    model.fit(train[feature_cols], train["is_win"],
              eval_set=[(valid[feature_cols], valid["is_win"])], eval_metric="binary_logloss",
              callbacks=[early_stopping(100, verbose=False), log_evaluation(0)])
    return model


def predict_stage1(model, df: pd.DataFrame, feature_cols: List[str]) -> np.ndarray:
    return normalize(df["race_id"].to_numpy(), model.predict_proba(df[feature_cols])[:, 1])


def fit_rank_table(train: pd.DataFrame, min_count: int = 50) -> Dict:
    by_size = train.groupby(["field_size", "popularity"])["is_win"].agg(["sum", "count"])
    by_rank = train.groupby("popularity")["is_win"].agg(["sum", "count"])
    return {
        "by_size": {k: (v["sum"] / v["count"]) for k, v in by_size.iterrows() if v["count"] >= min_count},
        "by_rank": {k: (v["sum"] / v["count"]) for k, v in by_rank.iterrows() if v["count"] > 0},
        "floor": 1e-3,
    }


def predict_rank(table: Dict, df: pd.DataFrame) -> np.ndarray:
    raw = np.array([
        table["by_size"].get((fs, pop), table["by_rank"].get(pop, table["floor"]))
        for fs, pop in zip(df["field_size"], df["popularity"])], dtype=float)
    return normalize(df["race_id"].to_numpy(), np.maximum(raw, table["floor"]))


def blend(race_ids: np.ndarray, p1: np.ndarray, pr: np.ndarray, alpha: float, beta: float) -> np.ndarray:
    z = pd.Series(alpha * np.log(np.clip(p1, EPS, 1)) + beta * np.log(np.clip(pr, EPS, 1)))
    z = z - z.groupby(race_ids).transform("max")
    return normalize(race_ids, np.exp(z.to_numpy()))


def race_logloss(df: pd.DataFrame, p: np.ndarray) -> pd.Series:
    """Per-race -log(probability given to the winner); dead heats are averaged."""
    w = df["is_win"].to_numpy() == 1
    d = pd.DataFrame({"race_id": df["race_id"].to_numpy()[w], "ll": -np.log(np.clip(p[w], EPS, 1))})
    return d.groupby("race_id")["ll"].mean()


def fit_blend(valid: pd.DataFrame, p1: np.ndarray, pr: np.ndarray) -> Tuple[float, float, float]:
    ids = valid["race_id"].to_numpy()
    best = (None, None, np.inf)
    grid = np.round(np.arange(0.0, 1.55, 0.1), 2)
    for a in grid:
        for b in grid:
            if a == 0 and b == 0:
                continue
            ll = race_logloss(valid, blend(ids, p1, pr, a, b)).mean()
            if ll < best[2]:
                best = (float(a), float(b), float(ll))
    return best


def top1_hit_rate(df: pd.DataFrame, p: np.ndarray) -> float:
    d = df[["race_id", "is_win"]].copy()
    d["p"] = p
    top = d.sort_values("p", ascending=False).drop_duplicates("race_id")
    return float(top["is_win"].mean())
