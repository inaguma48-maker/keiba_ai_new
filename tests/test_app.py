"""
Unit and Integration Tests for Horse Racing AI System.
"""

import os
import pytest
import json
import pandas as pd
from src.models import RaceInfo, HorseEntry, JRA_TRACK_PROFILES
from src.data import extract_features, generate_synthetic_historical_data, get_sample_races
from src.predictor import HorseRacePredictor
from src.strategy import calculate_betting_recommendations
from src.jra_importer import parse_jra_text, clean_horse_name
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
    assert "track_profile" in rd
    assert rd["track_profile"]["home_stretch_m"] == 525.9

def test_jra_track_profiles():
    assert len(JRA_TRACK_PROFILES) == 10
    assert "東京" in JRA_TRACK_PROFILES
    assert "中山" in JRA_TRACK_PROFILES
    assert JRA_TRACK_PROFILES["中山"]["max_slope_m"] == 5.3
    assert JRA_TRACK_PROFILES["新潟"]["home_stretch_m"] == 659.0

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
    assert clean_horse_name(raw_name_2) == "サンデーヒルズ"

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

def test_jra_dense_text_parser():
    pasted_text = """
    東京11R 芝2000m
    2 モンシュマン45.1 5,858万円480kg社台レースホース社台ファーム辻 哲英 武豊 55.0kg 45.1倍
    3 ホウオウシェリー10.4 6,010小笹 芳央岡田スタッド池上 昌和 ルメール 54.0kg 10.4倍
    1 グーテンベルク9.1 4,032近藤 英子坂東牧場金成 貴史 川田 57.0kg 9.1倍
    """
    race = parse_jra_text(pasted_text)
    assert len(race.horses) == 3
    horse_names = [h.horse_name for h in race.horses]
    assert "モンシュマン" in horse_names
    assert "ホウオウシェリー" in horse_names
    assert "グーテンベルク" in horse_names

    # Verify no appended owner/earnings metadata
    for h in race.horses:
        assert "万円" not in h.horse_name
        assert "社台" not in h.horse_name
        assert "岡田" not in h.horse_name

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


def test_parse_text_never_guesses_odds_or_falls_back():
    # 斤量 then オッズ: the odds must not be read from the 斤量 column
    race = parse_jra_text("1 アルファホース 武豊 57.0 3.1\n2 ブラボーホース 川田 55.0 5.4")
    assert [(h.impost, h.odds) for h in race.horses] == [(57.0, 3.1), (55.0, 5.4)]
    # a line without odds is skipped, not given an invented value
    race = parse_jra_text("1 アルファホース 武豊 57.0 3.1\n2 ブラボーホース 川田 55.0")
    assert [h.horse_number for h in race.horses] == [1]
    # nothing readable -> error, never a fixed sample race
    with pytest.raises(ValueError):
        parse_jra_text("シリウスステークス 中京 ダート1900m")


def test_flask_api_endpoints(monkeypatch):
    import app as app_module
    from src.jra_site import parse_meetings, parse_racecards
    fx = os.path.join(os.path.dirname(__file__), "fixtures")
    read = lambda n: open(os.path.join(fx, n), encoding="utf-8").read()

    class StubClient:
        def __init__(self, *a, **k): pass
        def fetch_meetings(self): return parse_meetings(read("jra_meetings.html"))
        def fetch_meeting_racecards(self, meeting): return parse_racecards(read("jra_racecards.html"))
        def fetch_by_cname(self, page, cname): return parse_racecards(read("jra_racecards.html"))

    monkeypatch.setattr(app_module, "JraClient", StubClient)
    client = app.test_client()

    res = client.get("/api/races")
    assert res.status_code == 200 and len(res.get_json()["races"]) >= 2

    detail = client.get("/api/races/R2026_01").get_json()
    assert detail["race"]["race_id"] == "R2026_01"

    # market view: probabilities come from the odds only
    sample = get_sample_races()[0]
    pred = client.post("/api/predict", data=json.dumps(sample.to_dict()), content_type="application/json").get_json()
    assert pred["status"] == "success" and len(pred["predictions"]) == len(sample.horses)
    assert abs(sum(p["market_probability"] for p in pred["predictions"]) - 1.0) < 0.01
    assert [p["odds"] for p in pred["predictions"]] == sorted(p["odds"] for p in pred["predictions"])
    for banned in ("recommendations", "confidence_score"):
        assert banned not in pred
    assert "AIの予測ではありません" in pred["notice"]

    # JRA auto fetch (stubbed; no network)
    auto = client.post("/api/auto_fetch_jra").get_json()
    assert auto["status"] == "success" and len(auto["results"]) == 1
    r = auto["results"][0]
    assert r["race"]["race_id"] == "1005202604061120261017" and len(r["predictions"]) == 2   # scratched horse excluded
    assert "recommendations" not in r

    # URL import and text import
    url = client.post("/api/import_jra", data=json.dumps(
        {"url": "https://www.jra.go.jp/JRADB/accessD.html?CNAME=pw01drl10052026040620261017/16"}), content_type="application/json")
    assert url.status_code == 200 and url.get_json()["status"] == "success"
    bad = client.post("/api/import_jra", data=json.dumps({"url": "https://example.com/x"}), content_type="application/json")
    assert bad.status_code == 502
    txt = client.post("/api/import_jra", data=json.dumps({"text_content": "1 アルファホース 武豊 57.0 3.1\n2 ブラボーホース 川田 55.0 5.4"}),
                      content_type="application/json").get_json()
    assert txt["status"] == "success" and len(txt["predictions"]) == 2
    empty = client.post("/api/import_jra", data=json.dumps({"text_content": "読めない文字列"}), content_type="application/json")
    assert empty.status_code == 400


def test_version_and_cache_busting():
    import app as app_module
    c = app_module.app.test_client()
    v = c.get("/api/version").get_json()
    assert len(v["version"]) == 8 and v["folder"]
    html = c.get("/").get_data(as_text=True)
    assert f"replay.js?v={v['version']}" in html and f"app.js?v={v['version']}" in html
    assert v["version"] in html and "起動しているフォルダ" in html
