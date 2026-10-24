"""Same-race trends (keep / cut reasons) on a keiba.db-shaped file with planted patterns. No network access."""

import sqlite3

import numpy as np
import pandas as pd
import pytest

from keiba import trends
from keiba.trends import (TrendError, age_key, class_label, factor_frame, facts, is_generic_name, norm_name, previous_runs,
                          profile_ids, race_date_of, race_trends)
from src.models import HorseEntry, RaceInfo
from tests.make_keiba_fixture import SCHEMA
from tests.make_trend_fixture import NAMED_TARGET, SAME_TARGET, build


@pytest.fixture(scope="module")
def kdb(tmp_path_factory):
    path = str(tmp_path_factory.mktemp("trend") / "keiba.db")
    build(path)
    return path


def app_race(rid, name, venue, surface, dist, names, odds=None, horse_ids=None):
    hs = [HorseEntry(i + 1, n, "J", "T", 4, 480, 57, 80, .2, .1, .1, .8, odds[i] if odds else 2.0 + i,
                     horse_id=horse_ids[i] if horse_ids else None) for i, n in enumerate(names)]
    return RaceInfo(rid, name, venue, surface, dist, "良", "晴", hs)


def named_race(names=None, odds=None):
    return app_race(NAMED_TARGET, "東京11R テスト記念 (GⅡ)", "東京", "芝", 1800,
                    names or [f"テスト2026_{i}" for i in range(1, 17)], odds)


def planted_profiles(kdb):
    """Breeder 'ノーザンファーム' for 2 of the 3 top-3 horses and 2 of the others every year; center by horse number."""
    con = sqlite3.connect(kdb)
    rows = con.execute("select e.horse_id, e.horse_number, x.finish_position, r.race_date from race_entries e "
                       "join races r on r.race_id = e.race_id left join race_results x on x.race_entry_id = e.id "
                       "where r.race_name like 'テスト記念%' order by r.race_date, x.finish_position").fetchall()
    con.close()
    prof, seen = {}, {}
    for hid, num, fin, d in rows:
        year = d[:4]
        i = seen[year] = seen.get(year, -1) + 1
        nf = (fin is not None and fin <= 2) or i in (5, 6) or (fin is None and num % 4 == 0)
        prof[hid] = {"status": "ok", "center": "美浦" if num % 2 else "栗東", "breeder": "ノーザンファーム" if nf else "テスト牧場"}
    return prof


def test_name_helpers():
    assert norm_name("第174回 天皇賞（秋）(GⅠ)") == "天皇賞(秋)"
    assert norm_name("テスト記念 (GⅡ)") == norm_name("テスト記念(G2)") == "テスト記念"
    assert is_generic_name("3歳以上1勝クラス") and is_generic_name("2歳未勝利") and is_generic_name("4歳以上1000万下")
    assert not is_generic_name("テスト記念") and not is_generic_name("天皇賞(秋)")
    assert class_label("GⅢ", "オープン") == "G3" and class_label(None, "1600万下") == "3勝クラス"
    assert class_label("", "", "2歳未勝利") == "未勝利" and class_label("L", "") == "オープン" and class_label("", "") == ""
    assert age_key("サラ系3歳以上") == "3歳以上" and age_key("", "2歳新馬") == "2歳"
    assert race_date_of(NAMED_TARGET) == "2026-10-24" and race_date_of("202610170511") == "2026-10-17"
    assert race_date_of("sample_1") is None


def test_named_race_finds_the_planted_patterns(kdb):
    prof = planted_profiles(kdb)
    odds = [2.0 + i for i in range(16)]                          # horse 1 is the favourite, horse 16 the 16th
    res = race_trends(kdb, named_race(odds=odds), NAMED_TARGET, lambda ids: {i: prof[i] for i in ids if i in prof})
    h = res["history"]
    assert (h["mode"], h["label"], h["n_races"], h["years"], h["n_horses"], h["n_top3"]) == \
        ("named", "テスト記念", 10, "2016〜2025年", 160, 30)
    rules = {(r["kind"], r["text"]): r for r in res["rules"]}
    assert rules[("keep", "1番人気")]["record"] == "10-0-0-0"
    assert rules[("cut", "10番人気以下")]["record"] == "0-0-0-70"
    assert rules[("cut", "前走10着以下")]["record"] == "0-0-0-70"
    assert ("keep", "生産牧場がノーザンファーム") in rules
    assert not any(r["factor"] == "調教場" for r in res["rules"])        # center has no pattern
    assert all(r["kind"] in ("keep", "cut") and r["sentence"].startswith("「") for r in res["rules"])

    horses = {x["horse_number"]: x for x in res["horses"]}
    fav, outsider = horses[1], horses[16]
    assert fav["verdict"] in ("keep", "mixed") and any("「1番人気」" in s and "10頭中10頭が3着以内" in s for s in fav["keep"])
    assert outsider["verdict"] in ("cut", "mixed") and any("「10番人気以下」" in s and "70頭すべて4着以下" in s for s in outsider["cut"])
    assert "人気 16番（現在のオッズ順）" in outsider["facts"]
    assert any(f.startswith("前走 ") and "着" in f for f in outsider["facts"])
    assert res["profiles"] == {"have": 176, "need": 176, "notfound": 0}
    assert any("現在のオッズ順" in n for n in res["notes"])


def test_only_earlier_runnings_are_used(kdb):
    """Explaining the 2025 running: its own result and later runnings must not be counted."""
    con = sqlite3.connect(kdb)
    rid = con.execute("select race_id from races where race_name like 'テスト記念%' and race_date like '2025%'").fetchone()[0]
    names = [r[0] for r in con.execute("select h.horse_name from race_entries e join horses h on h.horse_id = e.horse_id "
                                       "where e.race_id=? order by e.horse_number", (rid,))]
    con.close()
    res = race_trends(kdb, app_race(rid, "東京11R テスト記念", "東京", "芝", 1800, names), rid)
    assert res["history"]["n_races"] == 9 and res["history"]["years"] == "2016〜2024年"
    assert any("確定人気" in f for f in res["horses"][0]["facts"])        # a finished race uses its final popularity


def test_same_conditions_for_an_ordinary_race(kdb):
    race = app_race(SAME_TARGET, "中山5R 3歳以上1勝クラス", "中山", "ダート", 1200, [f"x{i}" for i in range(14)])
    res = race_trends(kdb, race, SAME_TARGET)
    h = res["history"]
    assert (h["mode"], h["n_races"], h["label"]) == ("same", 60, "中山 ダート1200m・3歳以上1勝クラス")
    assert any(r["kind"] == "cut" and r["text"] == "10番人気以下" and r["k"] == 0 for r in res["rules"])
    assert res["horses"][0]["keep"] == [] or "同じ条件の過去レース" in res["horses"][0]["keep"][0]
    assert res["profiles"] == {"have": 0, "need": 14 + 300, "notfound": 0}      # past horses: newest 300 only
    assert any("調教場・生産牧場: JRAから取得済み 0/314頭" in n for n in res["notes"])


def test_race_not_in_keiba_db_uses_the_app_data(kdb):
    """No keiba.db id: horses are matched by name, unknown horses and unannounced weights are not judged."""
    names = [f"テスト2026_{i}" for i in range(1, 16)] + ["ミチノウマ"]
    res = race_trends(kdb, named_race(names=names), None)
    assert res["history"]["n_races"] == 10
    unknown = res["horses"][-1]
    assert "前走 不明（過去データに見つからない馬）" in unknown["facts"]
    assert not any("前走" in s for s in unknown["cut"] + unknown["keep"])
    assert any(f.startswith("前走 ") and "着" in f for f in res["horses"][0]["facts"])          # found by name
    assert any(n.startswith("馬体重: まだ発表されていない") for n in res["notes"])
    assert all("馬体重 未発表" in x["facts"] for x in res["horses"])


def test_errors_are_explained(kdb):
    new = app_race("1005202604080120261024", "東京1R 新設ステークス", "東京", "芝", 1400, ["a", "b"])
    with pytest.raises(TrendError, match="クラス"):
        race_trends(kdb, new, None)
    lonely = app_race("1005202604080120261024", "東京1R 2歳未勝利", "東京", "芝", 1400, ["a", "b"])
    with pytest.raises(TrendError, match="0回しかない"):
        race_trends(kdb, lonely, None)
    with pytest.raises(TrendError, match="日付"):
        race_trends(kdb, app_race("sample_1", "サンプル", "東京", "芝", 1600, ["a", "b"]), None)


def test_previous_run_skips_scratched_entries(tmp_path):
    path = str(tmp_path / "k.db")
    con = sqlite3.connect(path)
    con.executescript(SCHEMA)
    for i, (d, name, fin, pop) in enumerate([("2026-01-05", "一月S", 3, 2), ("2026-02-05", "二月S", None, None),
                                             ("2026-03-05", "三月S", 7, 9)], start=1):
        rid = f"r{i}"
        con.execute("insert into races (race_id, race_date, venue, race_name, grade, category, race_class, surface, distance_m) "
                    "values (?,?,?,?,?,?,?,?,?)", (rid, d, "東京", name, None, "3歳以上", "オープン", "芝", 1600 + 200 * i))
        con.execute("insert into race_entries (id, race_id, horse_id, horse_number, popularity) values (?,?,?,?,?)", (i, rid, "H", 1, pop))
        con.execute("insert into race_results (id, race_entry_id, finish_position) values (?,?,?)", (i, i, fin))
    con.commit()
    out = previous_runs(con, ["H", "H", "H", None, "X"], ["2026-03-01", "2026-03-05", "2026-01-05", "2026-03-01", "2026-03-01"])
    con.close()
    assert out["prev_name"].tolist()[:2] == ["一月S", "一月S"]          # the scratched 二月S is not a run; same day excluded
    assert out["prev_finish"].tolist()[:2] == [3, 3] and out["prev_dist"].tolist()[0] == 1800
    assert out["has_prev"].tolist() == [True, True, False, None, False]  # None: horse unknown, False: no earlier run


def test_profile_ids_are_this_race_first_then_newest_past(kdb, monkeypatch):
    monkeypatch.setattr(trends, "PROFILE_CAP", 20)
    ids = profile_ids(kdb, named_race(), NAMED_TARGET)
    assert len(ids) == 16 + 20 and ids[0] == "02026000001" and all(i.startswith("02025") for i in ids[16:32])


def test_trend_api_and_profile_fetch(kdb, monkeypatch):
    from app import app
    from src import db as appdb, horse_profiles
    monkeypatch.setenv("KEIBA_DB", kdb)
    appdb.save_race(named_race())
    c = app.test_client()
    res = c.post("/api/trends", json={"race_id": NAMED_TARGET})
    assert res.status_code == 200, res.get_json()
    data = res.get_json()
    assert data["status"] == "success" and len(data["horses"]) == 16 and data["history"]["n_races"] == 10
    assert c.post("/api/trends", json={"race_id": "nope"}).status_code == 404

    html = open("tests/fixtures/jra_horse.html", encoding="utf-8").read()
    calls = []

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        def post(self, page, cname):
            calls.append((page, cname))
            return html if len(calls) % 5 else "<html><head><title>ＤＢ検索エラー　JRA</title></head></html>"

    monkeypatch.setattr(horse_profiles, "JraClient", FakeClient)
    got = c.post("/api/profiles/fetch", json={"race_id": NAMED_TARGET}).get_json()
    assert got == {"status": "success", "fetched": 25, "remaining": 176 - 25, "total": 176}
    assert calls[0] == ("accessU.html", "pw01dud002026000001/" + calls[0][1][-2:]) and len(calls) == 25
    saved = appdb.get_horse_profiles(["02026000001", "02026000005"])
    assert saved["02026000001"]["breeder"] == "テスト牧場" and saved["02026000005"]["status"] == "notfound"
    again = c.post("/api/trends", json={"race_id": NAMED_TARGET}).get_json()
    assert again["profiles"] == {"have": 25, "need": 176, "notfound": 5}    # a horse without a JRA page counts as done
    facts = {x["horse_number"]: x["facts"] for x in again["horses"]}
    assert "生産牧場 テスト牧場" in facts[1] and "生産牧場 JRAにページなし" in facts[5] and "生産牧場 未取得" not in facts[5]

    monkeypatch.setenv("KEIBA_DB", kdb + ".missing")
    assert "見つかりません" in c.post("/api/trends", json={"race_id": NAMED_TARGET}).get_json()["message"]


def test_facts_never_print_nan(tmp_path):
    """A previous race without class information (pandas 3 turned None into NaN, shown as 'nan')."""
    con = sqlite3.connect(str(tmp_path / "k.db"))
    con.executescript(SCHEMA)
    con.execute("insert into races (race_id, race_date, venue, race_name, grade, category, race_class, surface, distance_m) "
                "values ('r1', '2026-01-05', '東京', 'テスト特別', NULL, NULL, NULL, '芝', 1600)")
    con.execute("insert into race_entries (id, race_id, horse_id, horse_number, popularity) values (1, 'r1', 'H', 1, 3)")
    con.execute("insert into race_results (id, race_entry_id, finish_position) values (1, 1, 2)")
    con.execute("insert into races (race_id, race_date, venue, race_name, grade, category, race_class, surface, distance_m) "
                "values ('r2', '2026-01-06', '中山', 'テスト杯', 'G2', '3歳', 'オープン', '芝', 2000)")
    con.execute("insert into race_entries (id, race_id, horse_id, horse_number, popularity) values (2, 'r2', 'K', 1, 1)")
    con.execute("insert into race_results (id, race_entry_id, finish_position) values (2, 2, 1)")
    prev = previous_runs(con, ["H", None, "K"], ["2026-02-01"] * 3)
    con.close()
    base = pd.DataFrame({"horse_id": pd.Series(["H", None, "K"], dtype=object), "pop": [np.nan, 2.0, 1.0],
                         "bw": [np.nan, 480.0, np.nan], "bwd": [np.nan, -4.0, np.nan]})
    f = factor_frame(base, prev, np.array([1800.0] * 3), {})
    lines = facts(f.iloc[0], "") + facts(f.iloc[1], "現在のオッズ順") + facts(f.iloc[2], "現在のオッズ順")
    assert not any("nan" in x.lower() for x in lines), lines
    assert "前走 テスト特別（?・芝1600m）2着・3番人気" in lines and "前走 不明（過去データに見つからない馬）" in lines
    assert "馬体重 480kg（-4）" in lines and "人気 不明（オッズ未発表）" in lines and "調教場 未取得" in lines
    assert "前走 テスト杯（G2・芝2000m）1着・1番人気" in lines
