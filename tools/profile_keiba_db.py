"""
Read-only profile of the keiba.db schema: value formats, coverage and null rates.
Prints aggregates only (no horse/jockey/trainer names). Never modifies the DB.

usage: python tools/profile_keiba_db.py <path-to-keiba.db>
"""

import sqlite3
import sys
from pathlib import Path


def q(con, sql, params=()):
    try:
        return con.execute(sql, params).fetchall()
    except sqlite3.Error as e:
        return [(f"(エラー: {e})",)]


def show(title, rows, limit=40):
    print(f"\n### {title}")
    for r in rows[:limit]:
        print("  " + " | ".join("NULL" if v is None else str(v)[:120] for v in r))
    if len(rows) > limit:
        print(f"  … 他 {len(rows) - limit} 件")


def dist(con, table, col, limit=30):
    show(f"{table}.{col} の値と件数", q(con, f'select {col}, count(*) c from {table} group by {col} order by c desc limit {limit}'))


def nulls(con, table, cols):
    parts = ", ".join(f"round(100.0*sum({c} is null)/count(*),1)" for c in cols)
    row = q(con, f"select count(*), {parts} from {table}")[0]
    print(f"\n### {table} の欠損率(%)  行数={row[0]}")
    for c, v in zip(cols, row[1:]):
        print(f"  {c}: {v}")


def main() -> int:
    if len(sys.argv) != 2 or not Path(sys.argv[1]).is_file():
        print("usage: python tools/profile_keiba_db.py <path-to-keiba.db>", file=sys.stderr)
        return 1
    con = sqlite3.connect(f"file:{Path(sys.argv[1]).resolve().as_posix()}?mode=ro", uri=True)

    print("# keiba.db プロファイル（集計のみ・読み取り専用）")

    show("races: 期間・件数", q(con, "select min(race_date), max(race_date), count(*), count(distinct race_id) from races"))
    show("races: 年ごとの件数", q(con, "select substr(race_date,1,4) y, count(*) from races group by y order by y"))
    show("races: race_id の例と長さの分布", q(con, "select length(race_id) l, count(*), min(race_id), max(race_id) from races group by l"))
    for col in ("venue", "surface", "track_condition", "weather", "grade", "category", "rule", "weight_type"):
        dist(con, "races", col)
    dist(con, "races", "race_class", 20)
    show("races: 距離の最小・最大", q(con, "select min(distance_m), max(distance_m) from races"))
    nulls(con, "races", ["race_date", "venue", "surface", "distance_m", "track_condition", "post_time"])

    show("race_entries: 1レースあたりの頭数の分布", q(con, "select n, count(*) from (select race_id, count(*) n from race_entries group by race_id) group by n order by n"), 25)
    nulls(con, "race_entries", ["horse_id", "horse_number", "weight_carried", "jockey_id", "trainer_id", "body_weight", "body_weight_diff", "odds", "popularity"])
    show("race_entries: races にない race_id の件数", q(con, "select count(*) from race_entries e left join races r on r.race_id=e.race_id where r.race_id is null"))
    show("race_entries: horse_id の長さの分布と例", q(con, "select length(horse_id) l, count(*), min(horse_id) from race_entries group by l"))
    show("race_entries: odds の最小・中央付近・最大", q(con, "select min(odds), max(odds), round(avg(odds),1) from race_entries"))

    dist(con, "race_results", "finish_position", 30)
    nulls(con, "race_results", ["finish_position", "time_seconds", "last_3f", "passing_positions"])
    show("race_results: race_entries と結びつかない件数", q(con, "select count(*) from race_results x left join race_entries e on e.id=x.race_entry_id where e.id is null"))
    show("races のうち結果が無いレース数", q(con, "select count(*) from races r where not exists (select 1 from race_entries e join race_results x on x.race_entry_id=e.id where e.race_id=r.race_id)"))

    show("payouts: 券種ごとの件数と組合せの例", q(con, "select bet_type, count(*), min(combination), max(combination), min(amount_yen), max(amount_yen) from payouts group by bet_type order by 2 desc"))
    show("payouts: 払戻のあるレース数", q(con, "select count(distinct race_id) from payouts"))

    dist(con, "odds_history", "snapshot_label", 20)
    show("odds_history: 記録の期間とレース数", q(con, "select min(recorded_at), max(recorded_at), count(distinct race_id) from odds_history"))
    nulls(con, "odds_history", ["win_odds", "place_odds_low", "place_odds_high", "popularity"])
    show("odds_history: 1レース1馬あたりのスナップショット数の分布", q(con, "select n, count(*) from (select race_id, horse_number, count(*) n from odds_history group by race_id, horse_number) group by n order by n"), 15)

    show("feature_versions", q(con, "select id, label, substr(description,1,200), created_at from feature_versions"))
    show("horse_features: feature_version ごとの行数・レース数・期間", q(con, "select f.feature_version_id, count(*), count(distinct f.race_id), min(r.race_date), max(r.race_date) from horse_features f left join races r on r.race_id=f.race_id group by f.feature_version_id"))
    nulls(con, "horse_features", ["career_starts_before", "avg_finish_last5", "avg_last3f_last5", "days_since_last_race", "implied_prob_from_odds", "market_rank", "jockey_win_rate_before", "trainer_win_rate_before", "race_class_level"])
    show("horse_features: race_entries と結びつく割合", q(con, "select count(*), sum(exists(select 1 from race_entries e where e.race_id=f.race_id and e.horse_id=f.horse_id)) from horse_features f where f.id % 50 = 0"))

    show("model_runs（新しい順 5件）", q(con, "select id, model_name, feature_version_id, train_start_date, train_end_date, test_start_date, test_end_date, substr(metrics,1,300) from model_runs order by id desc limit 5"))
    show("horses: id の長さの分布と例", q(con, "select length(horse_id) l, count(*), min(horse_id) from horses group by l"))
    show("track_condition_history: 期間", q(con, "select min(race_date), max(race_date), count(*) from track_condition_history"))

    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
