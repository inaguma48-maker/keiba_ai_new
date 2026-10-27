"""
Post-race verification (予測検証) module.

Compares the prediction snapshot taken BEFORE the race with the actual result,
classifies what went wrong (miss type), and diagnoses which factors the model
over-trusted or under-valued. The output is used both for display and as the
input of the feedback learning loop (src/feedback_loop.py).
"""

import math
from typing import List, Dict, Any, Optional

import numpy as np

# Factors examined in the post-race diagnosis (key -> 表示名)
DIAGNOSIS_FEATURES = {
    "past_speed_rating": "スピード指数",
    "past_win_rate": "過去勝率",
    "jockey_win_rate": "騎手勝率",
    "trainer_win_rate": "調教師勝率",
    "track_aptitude": "馬場適性",
    "impost": "斤量",
    "odds": "単勝オッズ(人気)",
}

# z-score gap between two horses that counts as a meaningful difference
DIAGNOSIS_Z_GAP = 0.5

EPS = 1e-6


def _zscores(values: List[float]) -> List[float]:
    arr = np.array(values, dtype=float)
    std = arr.std()
    if std < EPS:
        return [0.0] * len(values)
    return list((arr - arr.mean()) / std)


def _rank_of(horses: List[Dict[str, Any]], key: str, horse_number: int) -> Optional[int]:
    ordered = sorted(horses, key=lambda h: h[key], reverse=True)
    for i, h in enumerate(ordered):
        if h["horse_number"] == horse_number:
            return i + 1
    return None


def review_race(snapshot: Dict[str, Any], result: Dict[str, Any]) -> Dict[str, Any]:
    """
    Build a verification report for one race.

    snapshot: {"race_id", "generation", "horses": [{horse_number, horse_name, odds,
               win_probability, model_probability, market_probability, place_probability,
               features: {...}}]}
    result:   {"first_horse_number", "second_horse_number", "third_horse_number", "win_payout"}
    """
    horses = snapshot["horses"]
    n = len(horses)
    first = result["first_horse_number"]
    top3 = [result["first_horse_number"], result["second_horse_number"], result["third_horse_number"]]
    top3 = [x for x in top3 if x]
    by_num = {h["horse_number"]: h for h in horses}

    predicted_order = sorted(horses, key=lambda h: h["win_probability"], reverse=True)
    top_pick = predicted_order[0]
    predicted_top3 = [h["horse_number"] for h in predicted_order[:3]]

    if top_pick["horse_number"] in top3:
        top_pick_finish = top3.index(top_pick["horse_number"]) + 1
    else:
        top_pick_finish = None  # 4着以下

    winner = by_num.get(first)
    winner_model_rank = _rank_of(horses, "win_probability", first)
    winner_market_rank = _rank_of(horses, "market_probability", first)

    # Probability-based accuracy metrics (lower is better)
    p_model_winner = winner["win_probability"] if winner else EPS
    p_market_winner = winner["market_probability"] if winner else EPS
    model_log_loss = -math.log(max(p_model_winner, EPS))
    market_log_loss = -math.log(max(p_market_winner, EPS))
    brier = sum((h["win_probability"] - (1.0 if h["horse_number"] == first else 0.0)) ** 2 for h in horses)
    place_overlap = len(set(predicted_top3) & set(top3))

    # ---- Miss classification ----
    miss_types = []
    if top_pick_finish == 1:
        miss_types.append({"code": "HIT", "label": "◎的中", "detail": "本命が1着。予測通り。"})
    else:
        if top_pick_finish in (2, 3):
            miss_types.append({"code": "NEAR_MISS", "label": "僅差の取りこぼし",
                               "detail": f"◎{top_pick['horse_name']}は{top_pick_finish}着。勝ち切れず。"})
        elif top_pick["win_probability"] >= top_pick["market_probability"] * 1.2:
            miss_types.append({"code": "OVERRATED_PICK", "label": "本命の過大評価",
                               "detail": f"◎{top_pick['horse_name']}を市場評価より高く見積もったが4着以下。"})
        else:
            miss_types.append({"code": "PICK_FAILED", "label": "本命凡走",
                               "detail": f"◎{top_pick['horse_name']}が4着以下。"})

        if winner is not None:
            if winner_market_rank == 1 and winner_model_rank and winner_model_rank >= 3:
                miss_types.append({"code": "FAVORITE_UNDERRATED", "label": "1番人気の軽視",
                                   "detail": f"勝ち馬は1番人気だがAIは{winner_model_rank}番手評価。"})
            if winner_market_rank and winner_market_rank >= 5 and winner_model_rank and winner_model_rank >= 4:
                if winner_market_rank >= 6 and winner_model_rank >= 6:
                    miss_types.append({"code": "UPSET", "label": "波乱(市場も外れ)",
                                       "detail": f"勝ち馬は{winner_market_rank}番人気。市場・AIとも上位評価なし。"})
                else:
                    miss_types.append({"code": "DARK_HORSE_MISSED", "label": "穴馬の見逃し",
                                       "detail": f"勝ち馬は{winner_market_rank}番人気、AIは{winner_model_rank}番手評価。"})

    # ---- Factor diagnosis: what did the model trust that turned out wrong? ----
    factor_findings = []
    feature_signals = {}  # feature -> +1 (under-valued) / -1 (over-trusted)
    if winner is not None and top_pick["horse_number"] != first and "features" in top_pick:
        for key, label in DIAGNOSIS_FEATURES.items():
            values = [h["features"].get(key, 0.0) for h in horses]
            zs = dict(zip([h["horse_number"] for h in horses], _zscores(values)))
            # Higher odds / impost is worse, so flip their sign to "goodness"
            sign = -1.0 if key in ("odds", "impost") else 1.0
            gap = sign * (zs[first] - zs[top_pick["horse_number"]])
            if gap >= DIAGNOSIS_Z_GAP:
                feature_signals[key] = 1
                factor_findings.append({
                    "feature": key, "label": label, "direction": "under_valued",
                    "text": f"勝ち馬は「{label}」で◎を上回っていた → {label}の軽視"
                })
            elif gap <= -DIAGNOSIS_Z_GAP:
                feature_signals[key] = -1
                factor_findings.append({
                    "feature": key, "label": label, "direction": "over_trusted",
                    "text": f"◎は「{label}」で勝ち馬を上回っていたが敗戦 → {label}の過信"
                })

    # Model vs market: did our model add value over the public odds?
    if model_log_loss < market_log_loss - 0.05:
        vs_market = "AIが市場(オッズ)より勝ち馬を高く評価できていた"
    elif model_log_loss > market_log_loss + 0.05:
        vs_market = "市場(オッズ)の方が勝ち馬を正しく評価していた → 市場情報の比重を上げる余地"
    else:
        vs_market = "AIと市場の評価は同程度"

    # Surprise score 0..1.5: how badly the model missed the winner (used as sample weight)
    surprise = min(1.5, model_log_loss / max(math.log(max(n, 2)), EPS))

    summary_parts = [m["label"] for m in miss_types]
    summary = " / ".join(summary_parts)

    return {
        "race_id": snapshot["race_id"],
        "generation": snapshot.get("generation"),
        "num_horses": n,
        "top_pick": {"horse_number": top_pick["horse_number"], "horse_name": top_pick["horse_name"],
                     "win_probability": round(top_pick["win_probability"] * 100, 1),
                     "odds": top_pick["odds"], "finish": top_pick_finish},
        "winner": {"horse_number": first,
                   "horse_name": winner["horse_name"] if winner else "不明",
                   "odds": winner["odds"] if winner else None,
                   "model_rank": winner_model_rank, "market_rank": winner_market_rank,
                   "win_probability": round(p_model_winner * 100, 1)},
        "actual_top3": top3,
        "predicted_top3": predicted_top3,
        "win_hit": top_pick_finish == 1,
        "place_hit": top_pick_finish is not None,
        "top3_overlap": place_overlap,
        "metrics": {
            "model_log_loss": round(model_log_loss, 4),
            "market_log_loss": round(market_log_loss, 4),
            "brier": round(brier, 4),
        },
        "vs_market": vs_market,
        "miss_types": miss_types,
        "factor_findings": factor_findings,
        "feature_signals": feature_signals,
        "surprise": round(surprise, 4),
        "summary": summary,
    }


def aggregate_reviews(reviews: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Aggregate per-race reviews (oldest first) into an accuracy trend and recurring error patterns.
    """
    if not reviews:
        return {"total_races": 0, "miss_type_counts": {}, "feature_tendencies": [], "trend": [],
                "first_half": None, "second_half": None}

    miss_counts: Dict[str, int] = {}
    feat_over: Dict[str, int] = {}
    feat_under: Dict[str, int] = {}
    trend = []
    for i, rv in enumerate(reviews):
        for m in rv["miss_types"]:
            miss_counts[m["label"]] = miss_counts.get(m["label"], 0) + 1
        for key, sig in rv.get("feature_signals", {}).items():
            if sig < 0:
                feat_over[key] = feat_over.get(key, 0) + 1
            else:
                feat_under[key] = feat_under.get(key, 0) + 1
        trend.append({
            "index": i + 1,
            "race_id": rv["race_id"],
            "generation": rv.get("generation"),
            "model_log_loss": rv["metrics"]["model_log_loss"],
            "market_log_loss": rv["metrics"]["market_log_loss"],
            "win_hit": rv["win_hit"],
            "place_hit": rv["place_hit"],
        })

    tendencies = []
    for key, label in DIAGNOSIS_FEATURES.items():
        over, under = feat_over.get(key, 0), feat_under.get(key, 0)
        if over == 0 and under == 0:
            continue
        if over > under:
            verdict = f"{label}を過信しがち ({over}回)"
        elif under > over:
            verdict = f"{label}を軽視しがち ({under}回)"
        else:
            verdict = f"{label}は過信/軽視が拮抗 ({over}回ずつ)"
        tendencies.append({"feature": key, "label": label, "over_trusted": over,
                           "under_valued": under, "verdict": verdict})
    tendencies.sort(key=lambda t: abs(t["over_trusted"] - t["under_valued"]), reverse=True)

    def _half(items):
        if not items:
            return None
        return {
            "races": len(items),
            "avg_model_log_loss": round(float(np.mean([t["model_log_loss"] for t in items])), 4),
            "avg_market_log_loss": round(float(np.mean([t["market_log_loss"] for t in items])), 4),
            "win_hit_rate": round(100.0 * sum(t["win_hit"] for t in items) / len(items), 1),
            "place_hit_rate": round(100.0 * sum(t["place_hit"] for t in items) / len(items), 1),
        }

    mid = len(trend) // 2
    return {
        "total_races": len(reviews),
        "miss_type_counts": miss_counts,
        "feature_tendencies": tendencies,
        "trend": trend,
        "first_half": _half(trend[:mid]) if mid > 0 else None,
        "second_half": _half(trend[mid:]),
    }
