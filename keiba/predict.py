"""
Stage1 (ability only) win probabilities for one race, from the stored pre-race features in keiba.db.

Odds and popularity are never used here: they are not Stage1 features.
"""

import glob
import os
from pathlib import Path
from typing import Dict, List, Optional

import joblib
import numpy as np
import pandas as pd

from keiba import dataset as ds
from keiba import model as md


class AbilityError(Exception):
    pass


def default_model_dir() -> str:
    return os.environ.get("KEIBA_MODEL_DIR") or str(Path.home() / ".keiba" / "models")


def latest_bundle(model_dir: Optional[str] = None) -> dict:
    files = sorted(glob.glob(os.path.join(model_dir or default_model_dir(), "keiba_stage12_*.joblib")))
    if not files:
        raise AbilityError("能力モデルが未作成です。keiba\\train.py を一度実行してください（数分かかります）。")
    return joblib.load(files[-1])


def stage1_probs(db_path: str, race_id: str, horse_numbers: List[int], bundle: dict) -> Dict[int, float]:
    """{horse_number: win probability} over `horse_numbers` (the starters), summing to 1."""
    df = ds.load_race(db_path, race_id, bundle["feature_version"])
    if df.empty:
        raise AbilityError("このレースの出走馬が過去データ(keiba.db)にありません。")
    wanted = {int(n) for n in horse_numbers}
    missing = sorted(wanted - set(df["horse_number"].astype(int)))
    if missing:
        raise AbilityError(f"出走馬の一部（{missing}番）が過去データにありません。")
    # scratched horses must not count in field size / relative features: keep only the real starters first
    df = df[df["horse_number"].isin(wanted)].copy()
    df, _, _ = ds.prepare(df, upcoming=True)
    if df.empty:
        raise AbilityError("このコース（障害など）は、能力モデルの対象外です。")
    feats = bundle["feature_cols"]
    absent = [c for c in feats if c not in df.columns]
    if absent:
        raise AbilityError(f"特徴量が足りません: {absent[:3]}")
    if len(df) < 2:
        raise AbilityError("出走馬が少なすぎます。")
    if df[[c for c in feats if c.startswith("career_starts")]].isna().all(axis=None):
        raise AbilityError("このレースの特徴量が、まだ過去データ(keiba.db)に作られていません。")
    raw = bundle["model"].predict_proba(df[feats])[:, 1]
    p = raw / raw.sum()
    return {int(n): float(v) for n, v in zip(df["horse_number"], p)}


def stage_probs(db_path: str, race_id: str, horses: List[dict], stage: int, bundle: dict) -> Dict[int, float]:
    """
    stage 1: ability only (no odds, no popularity).
    stage 2: ability x popularity rank, where the rank is the order of the given odds (lowest odds = 1).
    horses: [{"horse_number": int, "odds": float|None}]
    """
    nums = [int(h["horse_number"]) for h in horses]
    p1 = stage1_probs(db_path, race_id, nums, bundle)
    if stage == 1:
        return p1
    if stage != 2:
        raise AbilityError("層は 1 または 2 を指定してください。")
    odds = {int(h["horse_number"]): h.get("odds") for h in horses}
    if any(o is None or float(o) <= 0 for o in odds.values()):
        raise AbilityError("層2には、全馬のオッズ（人気順位の計算用）が必要です。")
    order = sorted(nums, key=lambda n: (float(odds[n]), n))
    pop = {n: i + 1 for i, n in enumerate(order)}
    frame = pd.DataFrame({"race_id": "r", "field_size": len(nums), "popularity": [pop[n] for n in nums]})
    pr = md.predict_rank(bundle["rank_table"], frame)
    base = np.array([p1[n] for n in nums])
    blended = md.blend(frame["race_id"].to_numpy(), base, pr, bundle["alpha"], bundle["beta"])
    return {n: float(v) for n, v in zip(nums, blended)}
