"""
Unit tests for Self-Growing Feedback Loop and Race Volatility Analysis.
"""

import pytest
import json
from src.models import RaceInfo, HorseEntry
from src.data import get_sample_races
from src.predictor import HorseRacePredictor
from src.strategy import calculate_betting_recommendations
from src.feedback_loop import SelfLearningEngine
from src.db import init_db, save_race, get_race_result
from app import app

def test_race_volatility_calculation():
    predictor = HorseRacePredictor()

    # 1. High Volatility Race (no strong favorite, wide odds)
    h1 = [
        HorseEntry(1, "穴馬ワン", "武豊", "友道", 4, 480, 57.0, 85.0, 0.2, 0.2, 0.2, 0.8, 4.5),
        HorseEntry(2, "穴馬ツー", "川田", "矢作", 4, 480, 57.0, 84.0, 0.2, 0.2, 0.2, 0.8, 5.0),
        HorseEntry(3, "穴馬スリー", "ルメール", "木村", 4, 480, 57.0, 83.0, 0.2, 0.2, 0.2, 0.8, 6.0),
        HorseEntry(4, "穴馬フォー", "横山武", "手塚", 4, 480, 57.0, 82.0, 0.2, 0.2, 0.2, 0.8, 7.5),
        HorseEntry(5, "穴馬ファイブ", "坂井", "矢作", 4, 480, 57.0, 81.0, 0.2, 0.2, 0.2, 0.8, 8.0),
        HorseEntry(6, "穴馬シックス", "岩田望", "友道", 4, 480, 57.0, 80.0, 0.2, 0.2, 0.2, 0.8, 9.5),
        HorseEntry(7, "穴馬セブン", "デムーロ", "吉岡", 4, 480, 57.0, 80.0, 0.2, 0.2, 0.2, 0.8, 12.0),
        HorseEntry(8, "穴馬エイト", "松山", "池江", 4, 480, 57.0, 80.0, 0.2, 0.2, 0.2, 0.8, 15.0),
        HorseEntry(9, "穴馬ナイン", "戸崎", "国枝", 4, 480, 57.0, 80.0, 0.2, 0.2, 0.2, 0.8, 18.0),
        HorseEntry(10, "穴馬テン", "菅原明", "斎藤", 4, 480, 57.0, 80.0, 0.2, 0.2, 0.2, 0.8, 22.0),
        HorseEntry(11, "穴馬イレブン", "田辺", "田中", 4, 480, 57.0, 80.0, 0.2, 0.2, 0.2, 0.8, 28.0),
        HorseEntry(12, "穴馬トゥエルブ", "三浦", "鹿戸", 4, 480, 57.0, 80.0, 0.2, 0.2, 0.2, 0.8, 35.0),
        HorseEntry(13, "穴馬サーティーン", "津村", "林", 4, 480, 57.0, 80.0, 0.2, 0.2, 0.2, 0.8, 45.0),
        HorseEntry(14, "穴馬フォーティーン", "西村淳", "安田", 4, 480, 57.0, 80.0, 0.2, 0.2, 0.2, 0.8, 50.0),
    ]
    vol_race = RaceInfo("VOL_01", "波乱必至ハンデ戦", "中山", "芝", 1600, "良", "晴", h1)
    vol_res = predictor.calculate_race_volatility(vol_race)
    assert vol_res["is_high_volatility"] is True
    assert vol_res["volatility_score"] >= 60

    # 2. Low Volatility Race (overwhelming 1.5 odds favorite)
    h2 = [
        HorseEntry(1, "超圧倒的大本命", "ルメール", "木村", 4, 480, 57.0, 105.0, 0.8, 0.3, 0.25, 0.95, 1.4),
        HorseEntry(2, "対抗馬", "川田", "中内田", 4, 480, 57.0, 88.0, 0.3, 0.2, 0.2, 0.85, 6.0),
        HorseEntry(3, "単穴馬", "武豊", "友道", 4, 480, 57.0, 82.0, 0.2, 0.18, 0.18, 0.8, 12.0)
    ]
    solid_race = RaceInfo("SOLID_01", "堅実本命戦", "東京", "芝", 2000, "良", "晴", h2)
    solid_res = predictor.calculate_race_volatility(solid_race)
    assert solid_res["is_high_volatility"] is False
    assert solid_res["volatility_score"] < 50

def test_self_learning_feedback_loop():
    init_db()
    predictor = HorseRacePredictor()
    engine = SelfLearningEngine(predictor)

    sample_race = get_sample_races()[0]
    save_race(sample_race)

    # Record result where 1st place is horse #1, win payout = 480 JPY
    res = engine.record_result_and_learn(
        race_id=sample_race.race_id,
        first_horse_number=sample_race.horses[0].horse_number,
        second_horse_number=sample_race.horses[1].horse_number,
        third_horse_number=sample_race.horses[2].horse_number,
        win_payout=480.0,
        place_payout=160.0
    )

    assert res["status"] == "success"
    assert res["retrain_summary"]["new_generation"] >= 2

    recorded_db = get_race_result(sample_race.race_id)
    assert recorded_db is not None
    assert recorded_db["win_payout"] == 480.0

    # Verification compares against the PRE-race prediction (no leakage from retraining)
    assert res["review"] is not None
    assert res["review"]["winner"]["horse_number"] == sample_race.horses[0].horse_number
    assert res["review"]["miss_types"]

    stats = engine.calculate_performance_stats()
    assert stats["total_races"] >= 1
    assert stats["recovery_rate"] >= 0

def test_feedback_api_endpoints():
    client = app.test_client()

    # Test POST /api/feedback/record_result
    res_rec = client.post(
        "/api/feedback/record_result",
        data=json.dumps({
            "race_id": "R2026_01",
            "first_horse_number": 1,
            "second_horse_number": 2,
            "third_horse_number": 3,
            "win_payout": 520.0,
            "place_payout": 180.0
        }),
        content_type="application/json"
    )
    assert res_rec.status_code == 200
    rec_data = res_rec.get_json()
    assert rec_data["status"] == "success"
    assert "performance_stats" in rec_data

    # Test GET /api/feedback/stats
    res_stats = client.get("/api/feedback/stats")
    assert res_stats.status_code == 200
    stats_data = res_stats.get_json()
    assert stats_data["status"] == "success"
    assert stats_data["stats"]["total_races"] >= 1

    # Test POST /api/feedback/retrain
    res_retrain = client.post("/api/feedback/retrain")
    assert res_retrain.status_code == 200
    retrain_data = res_retrain.get_json()
    assert retrain_data["status"] == "success"
    assert retrain_data["retrain_summary"]["new_generation"] >= 2
