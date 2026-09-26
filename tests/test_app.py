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
from src.jra_importer import parse_jra_text, fetch_and_parse_jra_url, clean_horse_name
from src.db import init_db, save_race, get_race_by_id, list_all_races
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

def test_db_persistence():
    init_db()
    horse = HorseEntry(1, "アイサンサン", "万代岡", "調教師", 4, 480, 57.0, 92.0, 0.35, 0.2, 0.18, 0.85, 5.0)
    test_race = RaceInfo("TEST_DB_RACE_01", "テスト保管レース", "阪神", "芝", 1600, "良", "晴", [horse])

    save_race(test_race)
    loaded = get_race_by_id("TEST_DB_RACE_01")
    assert loaded is not None
    assert loaded.race_name == "テスト保管レース"
    assert loaded.horses[0].horse_name == "アイサンサン"

    races = list_all_races()
    assert any(r["race_id"] == "TEST_DB_RACE_01" for r in races)

def test_clean_horse_name():
    raw_name_1 = "アイサンサン.(1番人気)"
    assert clean_horse_name(raw_name_1) == "アイサンサン"

    raw_name_2 = "サンデーヒルズ橋田宜長(栗東)父：キズナ"
    assert clean_horse_name(raw_name_2) == "サンデーヒルズ橋田宜長"

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

def test_jra_parser():
    text = "1 ディープスター ルメール 57.0 2.5\n2 コントレイル 川田 57.0 4.0"
    race = parse_jra_text(text, race_name_override="JRAテスト")
    assert race.race_name == "JRAテスト"
    assert len(race.horses) == 2
    assert race.horses[0].horse_name == "ディープスター"

def test_sirius_stakes_parser():
    sirius_text = """
    第28回 シリウスステークス (G3) 中京 ダート1900m 良
    1 ヤマニンウルス 牡4 武豊 57.0 1.8
    2 ハギノピリナ 牝5 藤岡佑 54.0 12.5
    3 オメガギネス 牡4 岩田望 57.5 3.5
    4 カンピオーネ 牡5 横山武 56.0 15.0
    5 ヴァンヤール 牡6 荻野極 57.0 8.2
    6 サンライズウルス 牡6 松山 57.0 22.0
    7 サンマルパトロール 牡4 デムーロ 55.0 6.8
    8 フタイテンロック 牡5 秋山稔 54.0 45.0
    """
    race = parse_jra_text(sirius_text)
    assert "シリウス" in race.race_name
    assert race.surface_type == "ダート"
    assert race.distance == 1900
    assert len(race.horses) == 8
    assert race.horses[0].horse_name == "ヤマニンウルス"
    assert race.horses[0].jockey_name == "武豊"

def test_sirius_stakes_url_import():
    url = "https://race.netkeiba.com/race/shutuba.html?race_id=202407040811"
    race = fetch_and_parse_jra_url(url)
    assert race is not None
    assert len(race.horses) >= 3

def test_jra_cp932_encoding_url_import():
    jra_official_url = "https://www.jra.go.jp/JRADB/accessD.html?CNAME=pw01dde0109202604081120260926/08"
    race = fetch_and_parse_jra_url(jra_official_url)
    assert race is not None
    assert race.race_name is not None
    assert len(race.horses) >= 1

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

    # Test POST /api/import_jra for Sirius Stakes
    res_import = client.post(
        "/api/import_jra",
        data=json.dumps({
            "text_content": "第28回 シリウスステークス (G3) 中京 ダ1900m\n1 ヤマニンウルス 武豊 57.0 1.8\n2 オメガギネス 岩田望 57.5 3.5"
        }),
        content_type="application/json"
    )
    assert res_import.status_code == 200
    import_data = res_import.get_json()
    assert import_data["status"] == "success"
    assert "predictions" in import_data
    assert "シリウス" in import_data["race"]["race_name"]
