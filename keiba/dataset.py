"""
Training data from the existing keiba.db (opened read-only).

Scope (docs/DESIGN.md D2): flat races only; obstacle races are dropped.
Final popularity is the only market information available for the whole history
(race_entries.odds is empty), so it is kept out of the Stage1 feature set.
"""

import sqlite3
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np
import pandas as pd

MARKET_COLS = ("implied_prob_from_odds", "market_rank", "market_rank_ratio")
NON_FEATURE_COLS = ("id", "race_id", "horse_id", "feature_version_id", "created_at")
CATEGORICAL = ["sex", "venue", "surface_norm", "track_condition", "race_class", "weight_type"]
MAX_NULL_RATE = 0.98
REL_COLS = (
    "avg_finish_last5", "career_top3_rate_before", "career_win_rate_before", "jockey_top3_rate_before",
    "trainer_top3_rate_before", "avg_last3f_last5", "best_last3f_rank_ratio_last5",
    "avg_position_ratio_last5", "body_weight", "weight_carried",
)
ENTRY_NUMERIC = ["age", "weight_carried", "body_weight", "body_weight_diff", "frame_number", "horse_number"]


def connect_ro(path) -> sqlite3.Connection:
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"DBファイルが見つかりません: {p}")
    return sqlite3.connect(f"file:{p.resolve().as_posix()}?mode=ro", uri=True)


def pick_feature_version(con: sqlite3.Connection) -> int:
    row = con.execute(
        "select feature_version_id from horse_features group by feature_version_id "
        "order by count(*) desc, feature_version_id desc limit 1").fetchone()
    if not row:
        raise ValueError("horse_features が空です。")
    return int(row[0])


def surface_norm(surface, category) -> str:
    if isinstance(category, str) and "障害" in category:
        return "obstacle"
    s = str(surface or "")
    if s in ("dirt", "ダート") or s.startswith("ダ"):
        return "dirt"
    if s == "turf" or s.startswith("芝"):
        return "turf"
    return "other"


def load_raw(db_path, feature_version: Optional[int] = None) -> Tuple[pd.DataFrame, int]:
    con = connect_ro(db_path)
    try:
        fv = feature_version if feature_version is not None else pick_feature_version(con)
        races = pd.read_sql_query(
            "select race_id, race_date, venue, surface, distance_m, track_condition, race_class, category, "
            "weight_type from races", con)
        entries = pd.read_sql_query(
            "select id as entry_id, race_id, horse_id, horse_number, frame_number, sex, age, weight_carried, "
            "body_weight, body_weight_diff, popularity from race_entries", con)
        results = pd.read_sql_query("select race_entry_id as entry_id, finish_position from race_results", con)
        feats = pd.read_sql_query("select * from horse_features where feature_version_id = ?", con, params=(fv,))
    finally:
        con.close()

    results = results.drop_duplicates("entry_id", keep="last")
    feats = feats.drop_duplicates(["race_id", "horse_id"], keep="last")
    df = entries.merge(races, on="race_id", how="inner").merge(results, on="entry_id", how="left")
    df = df.merge(feats.drop(columns=[c for c in ("id", "feature_version_id", "created_at") if c in feats]),
                  on=["race_id", "horse_id"], how="left")
    return df, fv


def load_race(db_path, race_id: str, feature_version: int) -> pd.DataFrame:
    """Entries of one race with the stored pre-race features (results, if any, are ignored by Stage1)."""
    con = connect_ro(db_path)
    try:
        races = pd.read_sql_query(
            "select race_id, race_date, venue, surface, distance_m, track_condition, race_class, category, weight_type "
            "from races where race_id = ?", con, params=(race_id,))
        entries = pd.read_sql_query(
            "select id as entry_id, race_id, horse_id, horse_number, frame_number, sex, age, weight_carried, body_weight, "
            "body_weight_diff, popularity from race_entries where race_id = ?", con, params=(race_id,))
        feats = pd.read_sql_query("select * from horse_features where race_id = ? and feature_version_id = ?", con,
                                  params=(race_id, feature_version))
    finally:
        con.close()
    feats = feats.drop_duplicates(["race_id", "horse_id"], keep="last")
    df = entries.merge(races, on="race_id", how="inner")
    df = df.merge(feats.drop(columns=[c for c in ("id", "feature_version_id", "created_at") if c in feats]),
                  on=["race_id", "horse_id"], how="left")
    df["finish_position"] = np.nan
    return df


def prepare(df: pd.DataFrame, upcoming: bool = False) -> Tuple[pd.DataFrame, List[str], List[str]]:
    """Clean, scope and add features. Returns (frame, feature_cols, categorical_cols).

    upcoming=True keeps every entry (a race that has not been run has no popularity / result to tell scratches apart)."""
    df = df.copy()
    df["race_date"] = pd.to_datetime(df["race_date"])
    df["surface_norm"] = [surface_norm(s, c) for s, c in zip(df["surface"], df["category"])]
    df = df[df["surface_norm"].isin(["turf", "dirt"])]

    # Non-starters (scratched/excluded) have neither a popularity nor a result.
    if not upcoming:
        df = df[~(df["popularity"].isna() & df["finish_position"].isna())]
    df = df.copy()

    for c in set(df.columns) - set(CATEGORICAL) - {"race_date", "race_id", "horse_id", "category", "surface"}:
        if df[c].dtype == object:
            df[c] = pd.to_numeric(df[c], errors="coerce")

    df["field_size"] = df.groupby("race_id")["horse_number"].transform("count")
    df["month"] = df["race_date"].dt.month
    df["is_win"] = (df["finish_position"] == 1).astype(int)
    df["is_top3"] = (df["finish_position"] <= 3).astype(int)
    df["popularity"] = df["popularity"].fillna(df["field_size"])

    grp = df.groupby("race_id")
    rel_names = []
    for c in REL_COLS:
        if c in df:
            df[f"{c}_rel"] = df[c] - grp[c].transform("mean")
            df[f"{c}_rk"] = grp[c].rank(pct=True)
            rel_names += [f"{c}_rel", f"{c}_rk"]

    excluded = (set(NON_FEATURE_COLS) | set(MARKET_COLS) | set(ENTRY_NUMERIC) | set(CATEGORICAL) | set(rel_names)
                | {"entry_id", "finish_position", "popularity", "is_win", "is_top3", "field_size", "month",
                   "distance_m", "race_date", "surface", "category"})
    hf_cols = [c for c in df.columns if c not in excluded and pd.api.types.is_numeric_dtype(df[c])]
    hf_cols = [c for c in hf_cols if df[c].isna().mean() <= MAX_NULL_RATE]

    cat_cols = [c for c in CATEGORICAL if c in df]
    for c in cat_cols:
        df[c] = df[c].astype("category")

    feature_cols = ENTRY_NUMERIC + ["field_size", "distance_m", "month"] + hf_cols + rel_names + cat_cols
    feature_cols = [c for c in dict.fromkeys(feature_cols) if c in df]
    return df.reset_index(drop=True), feature_cols, cat_cols


def split_by_date(df: pd.DataFrame, train_end: str, valid_end: str):
    d = df["race_date"]
    te, ve = pd.Timestamp(train_end), pd.Timestamp(valid_end)
    return df[d <= te], df[(d > te) & (d <= ve)], df[d > ve]
