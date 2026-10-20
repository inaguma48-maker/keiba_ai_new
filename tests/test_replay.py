"""Course dimensions, replay data and the replay API (no network, synthetic keiba.db)."""

import json
import math
import sqlite3

import pytest

from src import course_specs as cs
from src.db import get_race_by_id, init_db, save_race
from src.models import HorseEntry, RaceInfo
from src.replay import ReplayError, load_replay
from tests.make_keiba_fixture import build


def test_every_course_is_geometrically_possible():
    """A loop needs lap > 2 x straight, otherwise the stadium shape has no turns."""
    for venue, kinds in cs.COURSES.items():
        for kind, layouts in kinds.items():
            for variant, spec in layouts.items():
                if spec.get("kind") == "straight":
                    continue
                r = (spec["loop_m"] - 2 * spec["straight_m"]) / (2 * math.pi)
                assert 100 < r < 220, (venue, kind, variant, r)
                assert spec["width_min_m"] <= spec["width_max_m"]


def test_variant_resolution():
    assert cs.get_course("東京", "芝", 2400)["loop_m"] == 2083.1
    assert cs.get_course("京都", "芝", 2000, "外")["straight_m"] == 403.7
    assert cs.get_course("京都", "turf", 1800)["variant"] == "外"          # only on the outer loop
    assert cs.get_course("京都", "turf", 1200)["variant"] == "内"          # only on the inner loop
    ambiguous = cs.get_course("京都", "turf", 1600)
    assert ambiguous["variant"] == "内" and "不明" in ambiguous["note"]      # said out loud, not hidden
    assert cs.get_course("新潟", "turf", 1000)["kind"] == "straight"
    assert cs.get_course("東京", "ダート", 1600)["straight_m"] == 501.6
    assert cs.get_course("東京", "障害", 3000) is None
    assert cs.get_course("存在しない", "芝", 1200) is None
    assert cs.direction_of("東京") == "左" and cs.direction_of("中山") == "右"
    for venue in cs.ONLY_INNER:
        assert not (cs.ONLY_INNER[venue] & cs.ONLY_OUTER[venue])


@pytest.fixture()
def keiba_db(tmp_path, monkeypatch):
    p = tmp_path / "keiba.db"
    build(str(p))
    monkeypatch.setenv("KEIBA_DB", str(p))
    return p


def _flat_race(db):
    con = sqlite3.connect(db)
    row = con.execute("select race_id from races where surface in ('turf','dirt') and category not like '%障害%' limit 1").fetchone()
    obstacle = con.execute("select race_id from races where category like '%障害%' limit 1").fetchone()
    con.close()
    return row[0], obstacle[0]


def test_load_replay_returns_real_times(keiba_db):
    rid, _ = _flat_race(keiba_db)
    rp = load_replay(str(keiba_db), rid)
    runners = rp["runners"]
    assert len(runners) >= 8 and runners[0]["finish"] == 1
    assert rp["course"]["distance_m"] == rp["race"]["distance_m"]
    winners = [r for r in runners if r["finish"] == 1]
    assert all(r["time_s"] and r["last3f_s"] for r in winners)
    assert min(r["time_s"] for r in runners if r["time_s"]) == winners[0]["time_s"]   # winner is the fastest
    assert all(r["horse_name"].startswith("テストホース") for r in runners)


def test_replay_errors_are_explicit(keiba_db, tmp_path):
    rid, obstacle = _flat_race(keiba_db)
    with pytest.raises(ReplayError, match="障害"):
        load_replay(str(keiba_db), obstacle)
    with pytest.raises(ReplayError, match="ありません"):
        load_replay(str(keiba_db), "no-such-race")
    with pytest.raises(ReplayError, match="見つかりません"):
        load_replay(str(tmp_path / "missing.db"), rid)


def test_replay_marks_untrusted_times_instead_of_using_them(keiba_db):
    rid, _ = _flat_race(keiba_db)
    con = sqlite3.connect(keiba_db)
    con.execute("update race_results set time_seconds = 3.0 where race_entry_id = (select e.id from race_entries e "
                "where e.race_id=? and e.horse_number=3)", (rid,))
    con.commit(); con.close()
    r3 = [r for r in load_replay(str(keiba_db), rid)["runners"] if r["horse_number"] == 3][0]
    assert r3["time_s"] is None and r3["dnf"] is True


def test_replay_and_course_api(keiba_db):
    import app as app_module
    rid, obstacle = _flat_race(keiba_db)
    client = app_module.app.test_client()
    ok = client.get(f"/api/replay/{rid}").get_json()
    assert ok["status"] == "success" and ok["source"] == "keiba.db" and len(ok["runners"]) >= 8
    assert client.get(f"/api/replay/{obstacle}").status_code == 404
    assert client.get("/api/replay/no-such-race").status_code == 404
    c = client.get("/api/course", query_string={"venue": "中山", "surface": "芝", "distance": 2500, "variant": ""}).get_json()
    assert c["course"]["variant"] == "内" and c["course"]["direction"] == "右"
    assert client.get("/api/course", query_string={"venue": "東京", "surface": "障害", "distance": 3110}).status_code == 404


def test_db_migrates_old_schema_and_keeps_course_variant(tmp_path, monkeypatch):
    import importlib
    import src.db as db
    old = tmp_path / "old.db"
    con = sqlite3.connect(old)
    con.executescript("""
        create table races (race_id text primary key, race_name text not null, track_name text not null, surface_type text not null,
          distance integer not null, track_condition text not null, weather text not null, created_at timestamp default current_timestamp);
        create table horses (id integer primary key autoincrement, race_id text not null, horse_number integer not null, horse_name text not null,
          jockey_name text not null, trainer_name text not null, age integer not null, weight real not null, impost real not null,
          past_speed_rating real not null, past_win_rate real not null, jockey_win_rate real not null, trainer_win_rate real not null,
          track_aptitude real not null, odds real not null);""")
    con.close()
    monkeypatch.setattr(db, "DB_PATH", str(old))
    db.init_db()
    h = HorseEntry(1, "ア", "騎", "厩", 4, 480, 57.0, 80, 0.2, 0.1, 0.1, 0.8, 3.0)
    db.save_race(RaceInfo("R1", "n", "京都", "芝", 2000, "良", "晴", [h], course_variant="外"))
    assert db.get_race_by_id("R1").course_variant == "外"


def test_replay_finds_the_race_by_date_venue_and_number_when_ids_differ(keiba_db):
    con = sqlite3.connect(keiba_db)
    rid, date, venue, number = con.execute(
        "select race_id, race_date, venue, race_number from races where surface in ('turf','dirt') and category not like '%障害%' limit 1").fetchone()
    con.close()
    code = {v: k for k, v in __import__("src.jra_site", fromlist=["VENUE_CODES"]).VENUE_CODES.items()}[venue]
    other_id = f"10{code}{date[:4]}0909{number:02d}{date.replace('-', '')}"      # same race, different kai/nichi digits
    assert other_id != rid
    assert load_replay(str(keiba_db), other_id)["race"]["race_id"] == rid
    with pytest.raises(ReplayError, match="まだありません"):
        load_replay(str(keiba_db), f"10{code}20990101010199{number:02d}20990101"[:22].replace("99", "01", 1))


def test_typical_times_use_past_winners(keiba_db):
    from src.replay import typical_times
    con = sqlite3.connect(keiba_db)
    venue, dist, surf = con.execute("select venue, distance_m, surface from races where surface in ('turf','dirt') and category not like '%障害%' "
                                    "group by venue, distance_m, surface having count(*) >= 8 limit 1").fetchone()
    con.close()
    b = typical_times(str(keiba_db), venue, "芝" if surf == "turf" else "ダート", dist, going="良")
    assert b and b["n"] >= 5 and 12 <= dist / b["winner_time_s"] <= 20 and 28 <= b["last3f_s"] <= 48
    assert typical_times(str(keiba_db), "東京", "障害", 3000) is None
    import app as app_module
    r = app_module.app.test_client().get("/api/baseline", query_string={"venue": venue, "surface": surf, "distance": dist}).get_json()
    assert r["status"] == "success" and r["baseline"]["n"] >= 5
