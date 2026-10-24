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


def test_check_setup_reports_each_item(env, monkeypatch):
    import importlib.util, os
    monkeypatch.setenv("KEIBA_DB", env["db"]); monkeypatch.setenv("KEIBA_MODEL_DIR", env["models"])
    spec = importlib.util.spec_from_file_location("check_setup", os.path.join(os.path.dirname(__file__), "..", "tools", "check_setup.py"))
    cs = importlib.util.module_from_spec(spec); spec.loader.exec_module(cs)
    lines = cs.run_checks(app_url="http://127.0.0.1:9")                 # nothing listens there
    text = "\n".join(f"[{s}] {m}" for s, m in lines)
    assert "[OK] keiba.db" in text and "[OK] 能力モデル" in text
    assert "結果の再生ができます" in text and "層1の予測ができます" in text and "層2の予測ができます" in text
    trend = [f"[{s}] {m}" for s, m in lines if "過去の同レースの傾向" in m]
    assert len(trend) == 1 and trend[0].startswith("[OK]"), trend
    assert "[NG] アプリが応答しません" in text                              # reported, not raised


def test_scratched_horse_does_not_change_the_others_inputs(env, tmp_path):
    """Stage1 for the starters must equal Stage1 computed on a DB that never had the scratched horse."""
    bundle = latest_bundle(env["models"])
    rid, nums = _flat_race(env["db"])
    scratched, starters = nums[-1], nums[:-1]
    with_scratch = stage1_probs(env["db"], rid, starters, bundle)
    other = tmp_path / "without.db"
    shutil.copy(env["db"], other)
    con = sqlite3.connect(other)
    hid = con.execute("select horse_id from race_entries where race_id=? and horse_number=?", (rid, scratched)).fetchone()[0]
    con.execute("delete from race_entries where race_id=? and horse_number=?", (rid, scratched))
    con.execute("delete from horse_features where race_id=? and horse_id=?", (rid, hid))
    con.commit(); con.close()
    without = stage1_probs(str(other), rid, starters, bundle)
    assert with_scratch.keys() == without.keys()
    assert all(abs(with_scratch[k] - without[k]) < 1e-12 for k in with_scratch)
