"""
Tests for post-race verification and the feedback loop that improves prediction accuracy.
"""

import json
import math

import numpy as np
import pytest

from src.models import RaceInfo, HorseEntry
from src.race_review import review_race, aggregate_reviews
from src.calibration import fit_combiner, apply_combiner, DEFAULT_COEF
from src.predictor import HorseRacePredictor
from src.feedback_loop import SelfLearningEngine
from src import db


def _snapshot(probs, market, speeds, odds):
    horses = []
    for i, (p, m, sp, o) in enumerate(zip(probs, market, speeds, odds)):
        horses.append({
            "horse_number": i + 1, "horse_name": f"馬{i + 1}", "odds": o,
            "win_probability": p, "model_probability": p, "market_probability": m,
            "place_probability": min(0.95, p * 2.5),
            "features": {"past_speed_rating": sp, "past_win_rate": 0.2, "jockey_win_rate": 0.15,
                         "trainer_win_rate": 0.15, "track_aptitude": 0.8, "impost": 57.0, "odds": o},
        })
    return {"race_id": "T1", "generation": 1, "horses": horses}


def test_review_detects_overrated_pick_and_overtrusted_factor():
    # Model loved #1 (fast speed rating, 8.0 odds) but the 1.5 favourite #2 won
    snap = _snapshot(
        probs=[0.50, 0.20, 0.15, 0.10, 0.05],
        market=[0.10, 0.55, 0.15, 0.12, 0.08],
        speeds=[100, 80, 82, 78, 75],
        odds=[8.0, 1.5, 5.5, 7.0, 10.0],
    )
    rv = review_race(snap, {"first_horse_number": 2, "second_horse_number": 3,
                            "third_horse_number": 4, "win_payout": 150})
    codes = [m["code"] for m in rv["miss_types"]]
    assert rv["win_hit"] is False and rv["place_hit"] is False
    assert "OVERRATED_PICK" in codes
    assert rv["winner"]["market_rank"] == 1
    assert rv["feature_signals"]["past_speed_rating"] == -1   # speed over-trusted
    assert rv["feature_signals"]["odds"] == 1                 # popularity under-valued
    assert rv["metrics"]["model_log_loss"] > rv["metrics"]["market_log_loss"]
    assert "市場" in rv["vs_market"]

    agg = aggregate_reviews([rv, rv])
    assert agg["total_races"] == 2
    assert any("スピード指数を過信" in t["verdict"] for t in agg["feature_tendencies"])


def test_review_hit():
    snap = _snapshot([0.6, 0.2, 0.2], [0.5, 0.3, 0.2], [90, 80, 70], [1.8, 3.0, 5.0])
    rv = review_race(snap, {"first_horse_number": 1, "second_horse_number": 2,
                            "third_horse_number": 3, "win_payout": 180})
    assert rv["win_hit"] and rv["miss_types"][0]["code"] == "HIT"
    assert rv["top3_overlap"] == 3


def _simulated_race(rng, idx):
    """Race whose outcome follows the market odds (so a model that ignores odds is miscalibrated)."""
    n = int(rng.integers(8, 13))
    strength = rng.normal(0, 1, n)
    market = np.exp(strength * 1.2)
    market /= market.sum()
    odds = np.maximum(1.1, np.round(0.8 / market, 1))
    horses = []
    for i in range(n):
        horses.append(HorseEntry(
            i + 1, f"SIM{idx}_{i + 1}", "騎手", "厩舎", 4, float(rng.uniform(440, 520)), 57.0,
            float(rng.normal(80, 8)), float(rng.uniform(0.05, 0.5)), float(rng.uniform(0.05, 0.3)),
            float(rng.uniform(0.05, 0.3)), float(rng.uniform(0.5, 1.0)), float(odds[i])))
    # Plackett-Luce draw of the first three finishers from the true probabilities
    remaining = list(range(n))
    order = []
    for _ in range(3):
        p = market[remaining] / market[remaining].sum()
        pick = remaining[int(rng.choice(len(remaining), p=p))]
        order.append(pick + 1)
        remaining.remove(pick)
    race = RaceInfo(f"SIM_{idx:03d}", f"検証シミュレーション{idx}", "東京", "芝", 2000, "良", "晴", horses)
    return race, order


def _avg_winner_log_loss(predictor, races):
    losses = []
    for race, order in races:
        preds = {p["horse_number"]: p["win_probability"] for p in predictor.predict_race(race)}
        losses.append(-math.log(max(preds[order[0]], 1e-6)))
    return float(np.mean(losses))


def test_feedback_loop_improves_accuracy_on_unseen_races():
    rng = np.random.default_rng(7)
    predictor = HorseRacePredictor()
    engine = SelfLearningEngine(predictor)
    predictor.combiner_coef = None

    test_races = [_simulated_race(rng, 900 + i) for i in range(25)]
    loss_before = _avg_winner_log_loss(predictor, test_races)

    # Race-by-race: predict before the race -> record result -> verify -> learn
    for i in range(10):
        race, order = _simulated_race(rng, i)
        db.save_race(race)
        engine.snapshot_prediction(race, predictor.predict_race(race))
        res = engine.record_result_and_learn(race.race_id, order[0], order[1], order[2], win_payout=500.0)
        assert res["review"]["snapshot_source"] == "pre_race"
        assert res["learning"]["feedback_notes"]

    report = engine.get_learning_report()
    assert report["aggregate"]["total_races"] >= 10
    assert report["history"]
    # The combiner must have learned that the market odds carry information the model missed
    assert predictor.combiner_coef is not None
    assert predictor.combiner_coef["log_market"] > 0.1

    loss_after = _avg_winner_log_loss(predictor, test_races)
    assert loss_after < loss_before


def test_snapshot_is_frozen_after_result():
    predictor = HorseRacePredictor()
    engine = SelfLearningEngine(predictor)
    rng = np.random.default_rng(11)
    race, order = _simulated_race(rng, 500)
    db.save_race(race)
    assert engine.snapshot_prediction(race, predictor.predict_race(race)) is True
    engine.record_result_and_learn(race.race_id, order[0], order[1], order[2], win_payout=300.0)
    before = db.get_prediction_snapshot(race.race_id)
    # Viewing the race after the result must not overwrite the pre-race prediction
    assert engine.snapshot_prediction(race, predictor.predict_race(race)) is False
    assert db.get_prediction_snapshot(race.race_id)["horses"] == before["horses"]


def test_combiner_not_adopted_without_enough_races():
    res = fit_combiner([], None)
    assert res["adopt"] is False
    probs = apply_combiner(DEFAULT_COEF, [0.5, 0.3, 0.2], [0.2, 0.3, 0.5], [{}, {}, {}])
    assert np.allclose(probs, [0.5, 0.3, 0.2])


def test_review_and_report_api():
    from app import app
    client = app.test_client()
    res = client.post("/api/feedback/record_result", data=json.dumps({
        "race_id": "R2026_02", "first_horse_number": 2, "second_horse_number": 1,
        "third_horse_number": 3, "win_payout": 380.0, "place_payout": 150.0
    }), content_type="application/json")
    data = res.get_json()
    assert data["status"] == "success"
    assert data["review"]["race_id"] == "R2026_02"

    rv = client.get("/api/feedback/review/R2026_02").get_json()
    assert rv["status"] == "success"
    assert "applied_feedback" in rv["review"]

    detail = client.get("/api/races/R2026_02").get_json()
    assert detail["review"]["race_id"] == "R2026_02"

    rep = client.get("/api/feedback/report").get_json()
    assert rep["status"] == "success"
    assert rep["report"]["aggregate"]["total_races"] >= 1
    assert any(c["name"] == "log_market" for c in rep["report"]["combiner"])

    assert client.get("/api/feedback/review/NO_SUCH_RACE").status_code == 404
