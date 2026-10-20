"""Smoke test: tools/profile_keiba_db.py runs to the end on a keiba.db-shaped file."""

import os
import sqlite3
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SCHEMA = """
create table races (race_id text primary key, race_date date, venue text, kai int, nichime int, race_number int,
  race_name text, grade text, category text, race_class text, rule text, weight_type text, surface text,
  distance_m int, track_condition text, weather text, post_time time);
create table race_entries (id integer primary key, race_id text, horse_id text, horse_number int, frame_number int,
  sex text, age int, weight_carried numeric, jockey_id text, trainer_id text, body_weight int, body_weight_diff int,
  odds numeric, popularity int);
create table race_results (id integer primary key, race_entry_id int, finish_position int, time_raw text,
  time_seconds numeric, margin text, passing_positions text, last_3f numeric);
create table payouts (id integer primary key, race_id text, bet_type text, combination text, amount_yen int, popularity int);
create table odds_history (id integer primary key, race_id text, horse_number int, recorded_at datetime,
  snapshot_label text, win_odds numeric, place_odds_low numeric, place_odds_high numeric, popularity int);
create table feature_versions (id integer primary key, label text, description text, created_at datetime);
create table horse_features (id integer primary key, race_id text, horse_id text, feature_version_id int,
  career_starts_before float, avg_finish_last5 float, avg_last3f_last5 float, days_since_last_race float,
  implied_prob_from_odds float, market_rank real, jockey_win_rate_before float, trainer_win_rate_before float,
  race_class_level float);
create table model_runs (id integer primary key, model_name text, feature_version_id int, train_start_date date,
  train_end_date date, test_start_date date, test_end_date date, metrics json);
create table horses (horse_id text primary key, horse_name text, created_at datetime);
create table track_condition_history (id integer primary key, venue text, race_date date);
insert into races values ('202601010101','2026-01-05','東京',1,1,1,'テスト','','3歳以上','1勝','','馬齢','芝',1600,'良','晴','10:00');
insert into race_entries values (1,'202601010101','H1',1,1,'牡',4,57,'J1','T1',480,2,3.5,1);
insert into race_results values (1,1,1,'1:34.5',94.5,'','1-1',34.0);
insert into payouts values (1,'202601010101','単勝','1',350,1);
insert into odds_history values (1,'202601010101',1,'2026-01-05 09:00','final',3.5,1.5,2.0,1);
insert into feature_versions values (1,'v1','d','2026-01-01');
insert into horse_features values (1,'202601010101','H1',1,5,3.2,34.5,28,0.28,1,0.12,0.1,3);
insert into horses values ('H1','n','2026-01-01');
"""


def test_profile_tool_runs_without_errors(tmp_path):
    db = tmp_path / "keiba.db"
    con = sqlite3.connect(db)
    con.executescript(SCHEMA)
    con.commit()
    con.close()
    before = db.read_bytes()

    out = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "profile_keiba_db.py"), str(db)],
                         capture_output=True, text=True, encoding="utf-8")
    assert out.returncode == 0, out.stderr
    assert "(エラー" not in out.stdout, out.stdout
    assert "races: 期間・件数" in out.stdout and "payouts: 券種ごと" in out.stdout
    assert db.read_bytes() == before  # read-only
