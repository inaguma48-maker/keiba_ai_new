"""
Unit and Integration Tests for Horse Racing AI System.
"""

import pytest
import json
import pandas as pd
from src.models import RaceInfo, HorseEntry
from src.data import extract_features, generate_synthetic_historical_data, get_sample_races
from src.predictor import HorseRacePredictor
from src.strategy import calculate_betting_recommendations
from app import app

def test_data_models():
    horse = HorseEntry(1, "テストホース", "武豊", "友道", 4, 480, 57.0, 90.0, 0.4, 0.2, 0.2, 0.8, 3.5)
    d = horse.to_dict()
    assert d["horse_name"] == "テストホース"
    assert d["odds"] == 3.5

    race = RaceInfo("R01", "テストレース", "東京", "芝", 2000, "良", "晴", [horse])
    rd = race.to_dict()
    assert rd["race_id"] == "R01"
    assert len(rd["horses"]) == 1

def test_feature_extraction():
    sample_race = get_sample_races()[0]
    df = extract_features(sample_race)
    assert not df.empty
    assert "composite_score" in df.columns
    assert "implied_prob" in df.columns
    assert len(df) == len(sample_race.horses)

def test_synthetic_data_generation():
    df = generate_synthetic_historical_data(num_races=10)
    assert len(df) > 0
    assert "is_win" in df.columns
    assert "is_place" in df.columns

def test_predictor_train_and_predict():
    predictor = HorseRacePredictor()
    sample_race = get_sample_races()[0]
    preds = predictor.predict_race(sample_race)

    assert len(preds) == len(sample_race.horses)
    total_win_prob = sum(p["win_probability"] for p in preds)
    assert abs(total_win_prob - 1.0) < 0.01

    for p in preds:
        assert "win_probability" in p
        assert "place_probability" in p
        assert "win_ev" in p

def test_strategy_recommendations():
    predictor = HorseRacePredictor()
    sample_race = get_sample_races()[0]
    preds = predictor.predict_race(sample_race)
    recs = calculate_betting_recommendations(preds)

    assert "win_tickets" in recs
    assert "place_tickets" in recs
    assert "exacta_tickets" in recs
    assert "trio_tickets" in recs
    assert "confidence_score" in recs

def test_flask_api_endpoints():
    client = app.test_client()

    # Test GET /api/races
    res = client.get("/api/races")
    assert res.status_code == 200
    data = res.get_json()
    assert data["status"] == "success"
    assert len(data["races"]) >= 2

    # Test GET /api/races/<race_id>
    res_detail = client.get("/api/races/R2026_01")
    assert res_detail.status_code == 200
    detail_data = res_detail.get_json()
    assert detail_data["status"] == "success"
    assert detail_data["race"]["race_id"] == "R2026_01"

    # Test POST /api/predict
    sample_race = get_sample_races()[0]
    res_pred = client.post(
        "/api/predict",
        data=json.dumps(sample_race.to_dict()),
        content_type="application/json"
    )
    assert res_pred.status_code == 200
    pred_data = res_pred.get_json()
    assert pred_data["status"] == "success"
    assert len(pred_data["predictions"]) == len(sample_race.horses)
