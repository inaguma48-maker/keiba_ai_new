"""
Second-stage combiner (Benter-style conditional logit) learned from real race results.

utility_i = b_model * log(p_model_i) + b_market * log(p_market_i) + sum_k b_k * z_k,i
p_i       = softmax(utility) within the race

The coefficients are fitted on prediction snapshots that were taken BEFORE each race
(so the evaluation is honest) using a Plackett-Luce likelihood over the 1st-3rd finishers.
Default coefficients (b_model=1, others 0) reproduce the raw model probabilities exactly.
"""

import math
from typing import List, Dict, Any, Optional

import numpy as np
from scipy.optimize import minimize

COEF_NAMES = [
    "log_model", "log_market",
    "z_past_speed_rating", "z_past_win_rate", "z_jockey_win_rate",
    "z_trainer_win_rate", "z_track_aptitude", "z_impost",
]

COEF_LABELS = {
    "log_model": "AIモデル確率",
    "log_market": "市場オッズ確率",
    "z_past_speed_rating": "スピード指数補正",
    "z_past_win_rate": "過去勝率補正",
    "z_jockey_win_rate": "騎手勝率補正",
    "z_trainer_win_rate": "調教師勝率補正",
    "z_track_aptitude": "馬場適性補正",
    "z_impost": "斤量補正",
}

DEFAULT_COEF = {name: (1.0 if name == "log_model" else 0.0) for name in COEF_NAMES}

# L2 pull towards the default; keeps the combiner stable with few races
REGULARIZATION = 2.0
MIN_RACES_TO_FIT = 3
EPS = 1e-6


def _zscore(arr: np.ndarray) -> np.ndarray:
    std = arr.std()
    if std < EPS:
        return np.zeros_like(arr)
    return (arr - arr.mean()) / std


def build_design_matrix(model_probs, market_probs, features: List[Dict[str, float]]) -> np.ndarray:
    """Rows = horses, columns = COEF_NAMES."""
    model_probs = np.clip(np.asarray(model_probs, dtype=float), EPS, 1.0)
    market_probs = np.clip(np.asarray(market_probs, dtype=float), EPS, 1.0)
    cols = [np.log(model_probs), np.log(market_probs)]
    for name in COEF_NAMES[2:]:
        key = name[2:]
        cols.append(_zscore(np.array([f.get(key, 0.0) for f in features], dtype=float)))
    return np.column_stack(cols)


def apply_combiner(coef: Optional[Dict[str, float]], model_probs, market_probs,
                   features: List[Dict[str, float]]) -> np.ndarray:
    coef = coef or DEFAULT_COEF
    X = build_design_matrix(model_probs, market_probs, features)
    beta = np.array([coef.get(name, DEFAULT_COEF[name]) for name in COEF_NAMES])
    u = X @ beta
    u = u - u.max()
    e = np.exp(u)
    return e / e.sum()


def _race_from_snapshot(snapshot: Dict[str, Any], result: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    horses = snapshot["horses"]
    nums = [h["horse_number"] for h in horses]
    order = []
    for key in ("first_horse_number", "second_horse_number", "third_horse_number"):
        num = result.get(key)
        if num and num in nums and nums.index(num) not in order:
            order.append(nums.index(num))
    if not order or len(horses) < 2:
        return None
    X = build_design_matrix(
        [h["model_probability"] for h in horses],
        [h["market_probability"] for h in horses],
        [h.get("features", {}) for h in horses],
    )
    return {"X": X, "order": order}


def _pl_nll(beta: np.ndarray, races: List[Dict[str, Any]]) -> float:
    total = 0.0
    for r in races:
        u = r["X"] @ beta
        remaining = list(range(len(u)))
        for idx in r["order"]:
            sub = u[remaining]
            m = sub.max()
            total -= u[idx] - (m + math.log(np.exp(sub - m).sum()))
            remaining.remove(idx)
    return total


def _winner_nll(beta: np.ndarray, races: List[Dict[str, Any]]) -> float:
    total = 0.0
    for r in races:
        u = r["X"] @ beta
        m = u.max()
        total -= u[r["order"][0]] - (m + math.log(np.exp(u - m).sum()))
    return total / max(len(races), 1)


def _fit(races: List[Dict[str, Any]]) -> np.ndarray:
    beta0 = np.array([DEFAULT_COEF[n] for n in COEF_NAMES])

    def objective(beta):
        return _pl_nll(beta, races) + REGULARIZATION * float(np.sum((beta - beta0) ** 2))

    res = minimize(objective, beta0, method="L-BFGS-B")
    return res.x


def fit_combiner(pairs: List[Dict[str, Any]], current_coef: Optional[Dict[str, float]] = None) -> Dict[str, Any]:
    """
    pairs: [{"snapshot": ..., "result": ...}] for reviewed races.
    Returns fitted coefficients plus a cross-validated comparison against the current coefficients.
    The new coefficients should only be adopted when "adopt" is True.
    """
    races = [r for r in (_race_from_snapshot(p["snapshot"], p["result"]) for p in pairs) if r]
    current_coef = current_coef or DEFAULT_COEF
    beta_cur = np.array([current_coef.get(n, DEFAULT_COEF[n]) for n in COEF_NAMES])
    beta_default = np.array([DEFAULT_COEF[n] for n in COEF_NAMES])

    if len(races) < MIN_RACES_TO_FIT:
        return {"adopt": False, "races_used": len(races),
                "reason": f"検証済みレースが{MIN_RACES_TO_FIT}件未満のため補正係数は据え置き",
                "coef": dict(current_coef)}

    # Cross-validated winner log loss (leave-one-out, or 10-fold when many races)
    k = len(races) if len(races) <= 30 else 10
    folds = [list(range(i, len(races), k)) for i in range(k)]
    cv_new = 0.0
    for test_idx in folds:
        train = [races[i] for i in range(len(races)) if i not in test_idx]
        test = [races[i] for i in test_idx]
        beta = _fit(train)
        cv_new += _winner_nll(beta, test) * len(test)
    cv_new /= len(races)
    cv_cur = _winner_nll(beta_cur, races)
    cv_default = _winner_nll(beta_default, races)

    beta_new = _fit(races)
    # The fitting procedure is adopted when it generalizes better than the raw model.
    # (Comparing with the current coefficients would be unfair: they were fitted on these same races.)
    adopt = bool(cv_new < cv_default - 1e-4)
    return {
        "adopt": adopt,
        "races_used": len(races),
        "cv_log_loss_new": round(float(cv_new), 4),
        "log_loss_current": round(float(cv_cur), 4),
        "log_loss_raw_model": round(float(cv_default), 4),
        "coef": {n: round(float(b), 4) for n, b in zip(COEF_NAMES, beta_new)} if adopt else dict(current_coef),
        "candidate_coef": {n: round(float(b), 4) for n, b in zip(COEF_NAMES, beta_new)},
        "reason": ("交差検証で生モデルより予測誤差(対数損失)が小さいため補正係数を更新"
                   if adopt else "交差検証で生モデルより改善しないため補正係数は据え置き"),
    }


def describe_coef(coef: Dict[str, float]) -> List[Dict[str, Any]]:
    """Human-readable explanation of how the combiner adjusts the raw model."""
    rows = []
    for name in COEF_NAMES:
        value = coef.get(name, DEFAULT_COEF[name])
        base = DEFAULT_COEF[name]
        diff = value - base
        if abs(diff) < 0.02:
            effect = "変更なし"
        elif name == "log_model":
            effect = "AI確率の比重を上げる" if diff > 0 else "AI確率の比重を下げる"
        elif name == "log_market":
            effect = "オッズ(市場)の比重を上げる" if diff > 0 else "オッズ(市場)の比重を下げる"
        else:
            effect = "高い馬を上方修正" if diff > 0 else "高い馬を下方修正"
        rows.append({"name": name, "label": COEF_LABELS[name], "value": round(value, 4), "effect": effect})
    return rows
