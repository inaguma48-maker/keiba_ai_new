"""Stage1 / Stage2 probabilities for one race (synthetic keiba.db, model trained in a temp dir)."""

import shutil
import sqlite3

import numpy as np
import pytest

from keiba import train
from keiba.predict import AbilityError, latest_bundle, stage_probs, stage1_probs
from tests.make_keiba_fixture import build


@pytest.fixture(scope="module")
def env(tmp_path_factory):
    d = tmp_path_factory.mktemp("ability")
    db = d / "keiba.db"
    build(str(db))
    train.run(str(db), "2021-06-30", "2022-03-31", out_dir=str(d / "rep"), model_dir=str(d / "models"))
    return {"db": str(db), "models": str(d / "models"), "dir": d}


def _flat_race(db):
    con = sqlite3.connect(db)
    rid = con.execute("select race_id from races where surface in ('turf','dirt') and category not like '%障害%' "
                      "and race_date > '2022-04-01' limit 1").fetchone()[0]
    nums = [r[0] for r in con.execute("select horse_number from race_entries where race_id=? and popularity is not null order by horse_number", (rid,))]
    con.close()
    return rid, nums


def test_stage1_sums_to_one_and_ignores_odds_and_popularity(env, tmp_path):
    bundle = latest_bundle(env["models"])
    rid, nums = _flat_race(env["db"])
    p = stage1_probs(env["db"], rid, nums, bundle)
    assert abs(sum(p.values()) - 1) < 1e-9 and set(p) == set(nums)
    other = tmp_path / "scrambled.db"
    shutil.copy(env["db"], other)
    con = sqlite3.connect(other)
    con.execute("update race_entries set popularity = 19 - popularity where race_id = ? and popularity is not null", (rid,))
    con.execute("update horse_features set market_rank = 99, market_rank_ratio = 9.9, implied_prob_from_odds = 0.5 where race_id = ?", (rid,))
    con.commit(); con.close()
    assert stage1_probs(str(other), rid, nums, bundle) == p          # market columns cannot move Stage1


def test_stage1_works_for_a_race_not_yet_run(env, tmp_path):
    bundle = latest_bundle(env["models"])
    rid, nums = _flat_race(env["db"])
    up = tmp_path / "upcoming.db"
    shutil.copy(env["db"], up)
    con = sqlite3.connect(up)
    con.execute("insert into races select 'UP1', '2026-11-01', venue, kai, nichime, race_number, race_name, grade, category, race_class, rule, "
                "weight_type, surface, distance_m, track_condition, weather, post_time from races where race_id = ?", (rid,))
    con.execute("insert into race_entries (race_id, horse_id, horse_number, frame_number, sex, age, weight_carried, jockey_id, trainer_id, "
                "body_weight, body_weight_diff, odds, popularity) select 'UP1', horse_id, horse_number, frame_number, sex, age, weight_carried, "
                "jockey_id, trainer_id, body_weight, body_weight_diff, null, null from race_entries where race_id = ?", (rid,))
    con.execute("insert into horse_features (race_id, horse_id, feature_version_id, career_starts_before, career_win_rate_before, "
                "career_top3_rate_before, avg_finish_last5, avg_last3f_last5, days_since_last_race, jockey_win_rate_before, "
                "trainer_win_rate_before) select 'UP1', horse_id, feature_version_id, career_starts_before, career_win_rate_before, "
                "career_top3_rate_before, avg_finish_last5, avg_last3f_last5, days_since_last_race, jockey_win_rate_before, "
                "trainer_win_rate_before from horse_features where race_id = ?", (rid,))
    con.commit(); con.close()
    p = stage1_probs(str(up), "UP1", nums, bundle)
    assert abs(sum(p.values()) - 1) < 1e-9 and len(p) == len(nums)
    with pytest.raises(AbilityError, match="特徴量"):
        con = sqlite3.connect(up); con.execute("delete from horse_features where race_id = 'UP1'"); con.commit(); con.close()
        stage1_probs(str(up), "UP1", nums, bundle)


def test_stage2_follows_the_popularity_rank(env):
    bundle = latest_bundle(env["models"])
    rid, nums = _flat_race(env["db"])
    fav_first = [{"horse_number": n, "odds": 2.0 + i} for i, n in enumerate(nums)]      # horse nums[0] is the favourite
    fav_last = [{"horse_number": n, "odds": 2.0 + (len(nums) - i)} for i, n in enumerate(nums)]
    a, b = stage_probs(env["db"], rid, fav_first, 2, bundle), stage_probs(env["db"], rid, fav_last, 2, bundle)
    assert abs(sum(a.values()) - 1) < 1e-9 and abs(sum(b.values()) - 1) < 1e-9
    assert a[nums[0]] > b[nums[0]] and a[nums[-1]] < b[nums[-1]]                          # being the favourite raises it
    s1 = stage_probs(env["db"], rid, fav_first, 1, bundle)
    assert s1 == stage_probs(env["db"], rid, fav_last, 1, bundle)                        # Stage1 does not look at the odds
    with pytest.raises(AbilityError, match="オッズ"):
        stage_probs(env["db"], rid, [{"horse_number": n, "odds": None} for n in nums], 2, bundle)
    with pytest.raises(AbilityError):
        stage_probs(env["db"], rid, fav_first, 3, bundle)


def test_missing_model_is_explained(tmp_path):
    with pytest.raises(AbilityError, match="未作成"):
        latest_bundle(str(tmp_path / "nothing"))


def test_ability_api(env, monkeypatch):
    import app as app_module
    monkeypatch.setenv("KEIBA_DB", env["db"]); monkeypatch.setenv("KEIBA_MODEL_DIR", env["models"])
    rid, nums = _flat_race(env["db"])
    c = app_module.app.test_client()
    horses = [{"horse_number": n, "odds": 3.0 + i} for i, n in enumerate(nums)]
    for stage in (1, 2):
        r = c.post("/api/ability", json={"race_id": rid, "stage": stage, "horses": horses}).get_json()
        assert r["status"] == "success" and abs(sum(r["probs"].values()) - 1) < 1e-6
    bad = c.post("/api/ability", json={"race_id": "nope", "stage": 1, "horses": horses})
    assert bad.status_code == 404
    monkeypatch.setenv("KEIBA_MODEL_DIR", str(env["dir"] / "empty"))
    assert "未作成" in c.post("/api/ability", json={"race_id": rid, "stage": 1, "horses": horses}).get_json()["message"]
