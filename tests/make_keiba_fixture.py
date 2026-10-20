"""Build a small keiba.db-shaped SQLite file (real column layout, synthetic values) for tests."""

import sqlite3
from datetime import date, timedelta

import numpy as np

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
create table horses (horse_id text primary key, horse_name text, created_at datetime);
create table odds_history (id integer primary key, race_id text, horse_number int, recorded_at datetime,
  snapshot_label text, win_odds numeric, place_odds_low numeric, place_odds_high numeric, popularity int);
create table horse_features (id integer primary key, race_id text, horse_id text, feature_version_id int,
  career_starts_before float, career_win_rate_before float, career_top3_rate_before float, avg_finish_last5 float,
  avg_last3f_last5 float, days_since_last_race float, jockey_win_rate_before float, trainer_win_rate_before float,
  implied_prob_from_odds float, market_rank real, market_rank_ratio real, race_class_level float, created_at datetime);
"""


def build(path, n_races=900, seed=7):
    rng = np.random.default_rng(seed)
    con = sqlite3.connect(path)
    con.executescript(SCHEMA)
    start = date(2020, 1, 4)
    eid = 0
    fid = 0
    pid = 0
    for r in range(n_races):
        d = start + timedelta(days=int(r * 1000 / n_races))
        venue = ["東京", "阪神", "中山", "京都"][r % 4]
        obstacle = r % 25 == 0
        surface = "芝→ダート" if obstacle else rng.choice(["turf", "dirt", "芝 外"])
        category = "障害3歳以上" if obstacle else "3歳以上"
        rid = f"10{(r % 4) + 5:02d}{d.year}{1 + r % 4:02d}{1 + r % 9:02d}{1 + r % 12:02d}{d:%Y%m%d}{r:03d}"
        dist = int(rng.choice([1200, 1600, 2000, 2400]))
        con.execute("insert into races values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (rid, d.isoformat(), venue, 1, 1, 1 + r % 12, "t", None, category, "1勝クラス", None, "馬齢",
                     str(surface), dist, "良", "晴", "15:00"))
        n = int(rng.integers(8, 17))
        ability = rng.normal(0, 1, n)
        perf = ability + rng.normal(0, 1.3, n)
        order = np.argsort(-perf)
        finish = np.empty(n, int)
        finish[order] = np.arange(1, n + 1)
        pop = np.empty(n, int)
        pop[np.argsort(-(ability + rng.normal(0, 0.8, n)))] = np.arange(1, n + 1)
        q = np.exp(ability + rng.normal(0, 0.8, n))
        q = q / q.sum()
        odds = np.maximum(1.1, np.round(0.8 / q, 1))
        oid = 0
        for label_t in ("13:00", "14:30", "15:10"):
            for i in range(n):
                oid += 1
                con.execute("insert into odds_history (race_id, horse_number, recorded_at, snapshot_label, win_odds, "
                            "place_odds_low, place_odds_high, popularity) values (?,?,?,?,?,?,?,?)",
                            (rid, i + 1, f"{d.isoformat()} {label_t}:05.123456", f"{d.isoformat()}T{label_t}",
                             float(odds[i]), 1.1, 1.5, int(pop[i])))
        for i in range(n):
            eid += 1
            fid += 1
            hn = i + 1
            nonstarter = (r % 5 == 0) and i == n - 1
            con.execute("insert into race_entries values (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (eid, rid, f"H{r}_{i}", hn, 1 + i // 2, "牡", 4, 56.0, "J1", "T1",
                         int(rng.normal(480, 20)), int(rng.integers(-8, 9)), None,
                         None if nonstarter else int(pop[i])))
            tm = dist / 16.4 + 0.14 * (finish[i] - 1) + float(rng.uniform(0, 0.05))   # times never invert the finish order
            l3 = 34.0 + 0.12 * (finish[i] - 1) + float(rng.normal(0, 0.5))
            con.execute("insert into race_results values (?,?,?,?,?,?,?,?)",
                        (eid, eid, None if nonstarter else int(finish[i]), "", None if nonstarter else round(tm, 1), "", "",
                         None if nonstarter else round(l3, 1)))
            con.execute("insert into horses values (?,?,?)", (f"H{r}_{i}", f"テストホース{r}-{hn}", "2026-01-01"))
            con.execute("insert into horse_features values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (fid, rid, f"H{r}_{i}", 3, float(rng.integers(0, 30)),
                         float(np.clip(0.1 + 0.08 * ability[i] + rng.normal(0, 0.05), 0, 1)),
                         float(np.clip(0.3 + 0.12 * ability[i] + rng.normal(0, 0.08), 0, 1)),
                         None if rng.random() < 0.1 else float(9 - 2.0 * ability[i] + rng.normal(0, 2)),
                         float(35 + rng.normal(0, 1)), float(rng.integers(7, 90)),
                         float(rng.uniform(0.02, 0.2)), float(rng.uniform(0.02, 0.2)),
                         None, float(pop[i]), float(pop[i]) / n, None, "2026-01-01"))
        w = int(np.argmin(finish))
        pid += 1
        con.execute("insert into payouts values (?,?,?,?,?,?)", (pid, rid, "win", str(w + 1), int(round(100 * odds[w])), int(pop[w])))
    con.commit()
    con.close()
