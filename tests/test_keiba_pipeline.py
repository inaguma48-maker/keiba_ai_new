"""End-to-end test of keiba/train.py on a keiba.db-shaped synthetic file (no real data)."""

import glob
import os
import sqlite3

import numpy as np

from keiba import dataset as ds
from keiba import model as md
from keiba import train
from tests.make_keiba_fixture import build

ARGS = ["--train-end", "2021-06-30", "--valid-end", "2022-03-31"]


def _db(tmp_path):
    p = tmp_path / "keiba.db"
    build(str(p))
    return p


def test_prepare_scopes_and_excludes_market_and_target(tmp_path):
    raw, fv = ds.load_raw(_db(tmp_path))
    df, feats, cats = ds.prepare(raw)
    assert fv == 3
    assert set(df["surface_norm"].astype(str)) <= {"turf", "dirt"}          # obstacle & odd surfaces handled
    assert df["popularity"].notna().all()                                    # non-starters dropped
    for banned in ("finish_position", "is_win", "is_top3", "popularity", "market_rank", "market_rank_ratio",
                   "implied_prob_from_odds", "entry_id", "race_id", "horse_id"):
        assert banned not in feats, banned
    assert "race_class_level" not in feats                                   # >98% null columns dropped
    assert "avg_finish_last5_rel" in feats


def test_probabilities_sum_to_one_and_stage1_beats_uniform(tmp_path):
    raw, _ = ds.load_raw(_db(tmp_path))
    df, feats, _ = ds.prepare(raw)
    tr, va, te = ds.split_by_date(df, "2021-06-30", "2022-03-31")
    m1 = md.fit_stage1(tr, va, feats)
    p1 = md.predict_stage1(m1, te, feats)
    sums = te.assign(p=p1).groupby("race_id")["p"].sum()
    assert np.allclose(sums, 1.0)
    uni = md.normalize(te["race_id"].to_numpy(), np.ones(len(te)))
    assert md.race_logloss(te, p1).mean() < md.race_logloss(te, uni).mean()


def test_train_writes_report_and_model_and_never_modifies_db(tmp_path):
    db = _db(tmp_path)
    before = db.read_bytes()
    out, mdir = tmp_path / "reports", tmp_path / "models"
    rc = train.main([str(db), *ARGS, "--out-dir", str(out), "--model-dir", str(mdir)])
    assert rc == 0
    report = open(glob.glob(str(out / "train_report_*.txt"))[0], encoding="utf-8").read()
    for heading in ("勝ち馬に付けた確率の質", "Stage2の重み", "単勝を各レース100円", "校正", "情報漏れ(リーク)の点検"):
        assert heading in report
    assert glob.glob(str(mdir / "keiba_stage12_*.joblib"))
    assert db.read_bytes() == before


def test_missing_db_is_a_clear_error(tmp_path, capsys):
    assert train.main([str(tmp_path / "nope.db")]) == 1
    assert "見つかりません" in capsys.readouterr().err


def test_eval_with_real_odds_runs_and_is_read_only(tmp_path):
    from keiba import eval_odds
    db = _db(tmp_path)
    before = db.read_bytes()
    rc = eval_odds.main([str(db), *ARGS, "--out-dir", str(tmp_path / "rep")])
    assert rc == 0
    report = open(glob.glob(str(tmp_path / "rep" / "eval_odds_*.txt"))[0], encoding="utf-8").read()
    assert "確定に近いオッズ" in report and "発走30分前のオッズ" in report
    assert "能力×実オッズ" in report and "全頭に100円ずつ買った回収率" in report
    assert "評価できません" not in report       # fixture has enough races with odds
    assert db.read_bytes() == before


def test_snapshot_before_post_never_uses_later_snapshots():
    import pandas as pd
    from keiba.eval_odds import snapshot_before_post
    odds = pd.DataFrame({
        "race_id": ["R"] * 3, "horse_number": [1] * 3, "win_odds": [5.0, 4.0, 3.0],
        "label_dt": pd.to_datetime(["2026-01-01 13:00", "2026-01-01 14:30", "2026-01-01 15:10"])})
    posts = pd.DataFrame({"race_id": ["R"], "post_dt": pd.to_datetime(["2026-01-01 15:00"])})
    got = snapshot_before_post(odds, posts, 30)
    assert list(got["win_odds"]) == [4.0]       # 14:30 is the latest at least 30 min before 15:00
