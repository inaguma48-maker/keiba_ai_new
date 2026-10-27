"""
Self-Growing Feedback Loop Engine for Horse Racing AI Predictor.

Cycle per finished race:
  1. 予測スナップショット: the prediction made BEFORE the race is stored (frozen once a result exists)
  2. 結果検証: the snapshot is compared with the actual result (src/race_review.py) to find
     what went wrong (miss type, over-trusted / under-valued factors)
  3. フィードバック学習:
     a. second-stage combiner (src/calibration.py) refitted on all verified races and adopted
        only if cross-validated log loss improves
     b. base model retrained with badly-missed races weighted higher, adopted only if it does
        not get worse on the most recent verified races (time-split holdout); held back until
        enough verified races exist to run that check
Performance stats are computed from the pre-race snapshots, never by re-predicting with a
model that has already seen the result.
"""

import math
from typing import List, Dict, Any, Optional

import numpy as np
import pandas as pd

from src.db import (
    save_race_result, get_race_by_id, get_all_completed_races,
    save_prediction_snapshot, get_prediction_snapshot, save_race_review, get_race_review,
    list_reviewed_races, get_learning_state, set_learning_state
)
from src.data import extract_features, generate_synthetic_historical_data
from src.predictor import HorseRacePredictor, FEATURE_COLUMNS
from src.race_review import review_race, aggregate_reviews
from src.calibration import fit_combiner, describe_coef, DEFAULT_COEF

STAKE_PER_RACE = 1000  # 1,000 JPY win bet on the top pick per race
HOLDOUT_MIN_RACES = 8  # verified races needed before the base model retrain is validated
HOLDOUT_SIZE_MIN = 3  # most recent races used to validate a retrained base model
HISTORY_LIMIT = 50
EPS = 1e-6


class SelfLearningEngine:
    def __init__(self, predictor: HorseRacePredictor):
        self.predictor = predictor
        self.generation = int(get_learning_state("generation", 1))
        self.predictor.combiner_coef = get_learning_state("combiner_coef", None)

    # ------------------------------------------------------------------ snapshot
    def snapshot_prediction(self, race, predictions: List[Dict[str, Any]], source: str = "pre_race") -> bool:
        """Store the pre-race prediction. Ignored once the race already has a result."""
        snapshot = self.predictor.build_snapshot(race, predictions, self.generation)
        return save_prediction_snapshot(race.race_id, self.generation, snapshot, source)

    def _ensure_snapshot(self, race_id: str) -> Optional[Dict[str, Any]]:
        snapshot = get_prediction_snapshot(race_id)
        if snapshot:
            return snapshot
        race = get_race_by_id(race_id)
        if not race or not race.horses:
            return None
        # No prediction was viewed before the race: predict now, before any learning from this result
        self.snapshot_prediction(race, self.predictor.predict_race(race), source="at_result_entry")
        return get_prediction_snapshot(race_id)

    # ------------------------------------------------------------------ main entry
    def record_result_and_learn(
        self,
        race_id: str,
        first_horse_number: int,
        second_horse_number: int,
        third_horse_number: int,
        win_payout: float,
        place_payout: float = 0.0
    ) -> Dict[str, Any]:
        """
        Record actual race finish numbers, verify the pre-race prediction against them,
        and feed the findings back into the models.
        """
        snapshot = self._ensure_snapshot(race_id)

        save_race_result(
            race_id=race_id,
            first=first_horse_number,
            second=second_horse_number,
            third=third_horse_number,
            win_payout=win_payout,
            place_payout=place_payout
        )

        review = None
        if snapshot:
            review = review_race(snapshot, {
                "first_horse_number": first_horse_number,
                "second_horse_number": second_horse_number,
                "third_horse_number": third_horse_number,
                "win_payout": win_payout,
            })
            review["snapshot_source"] = snapshot.get("source", "pre_race")
            save_race_review(race_id, review)

        learning = self.learn_from_feedback()

        if review is not None:
            review["applied_feedback"] = learning["feedback_notes"]
            save_race_review(race_id, review)

        stats = self.calculate_performance_stats()
        return {
            "status": "success",
            "message": f"レース結果を検証し、AI自己成長ループ（世代 {self.generation}）を適用しました。",
            "review": review,
            "learning": learning,
            "retrain_summary": learning["base_model"],
            "performance_stats": stats
        }

    def learn_from_feedback(self) -> Dict[str, Any]:
        combiner = self.update_combiner()
        base = self.retrain_from_feedback()
        notes = [combiner["reason"], base["reason"]]
        if combiner["adopt"]:
            changed = [d for d in describe_coef(combiner["coef"]) if d["effect"] != "変更なし"]
            notes += [f"{d['label']}: {d['effect']} (係数 {d['value']})" for d in changed]
        self._append_history({
            "generation": self.generation,
            "verified_races": combiner["races_used"],
            "combiner_adopted": combiner["adopt"],
            "combiner_cv_log_loss": combiner.get("cv_log_loss_new"),
            "combiner_current_log_loss": combiner.get("log_loss_current"),
            "base_model_adopted": base["adopted"],
            "base_holdout_log_loss_candidate": base.get("holdout_log_loss_candidate"),
            "base_holdout_log_loss_current": base.get("holdout_log_loss_current"),
        })
        return {"combiner": combiner, "base_model": base, "feedback_notes": notes}

    # ------------------------------------------------------------------ feedback a: combiner
    def update_combiner(self) -> Dict[str, Any]:
        pairs = [{"snapshot": r["snapshot"], "result": r["result"]} for r in list_reviewed_races()]
        res = fit_combiner(pairs, self.predictor.combiner_coef)
        if res["adopt"]:
            self.predictor.combiner_coef = res["coef"]
            set_learning_state("combiner_coef", res["coef"])
        return res

    # ------------------------------------------------------------------ feedback b: base model
    def _feedback_frame(self, races: List[Dict[str, Any]]) -> pd.DataFrame:
        rows = []
        for r in races:
            race_obj = get_race_by_id(r["race_id"])
            if not race_obj or not race_obj.horses:
                continue
            review = get_race_review(r["race_id"])
            # Badly-missed races teach the model more: weight by how surprised it was
            weight = 3.0 + 4.0 * (review["surprise"] if review else 0.5)
            top3 = [r["first_horse_number"], r["second_horse_number"], r["third_horse_number"]]
            df_feats = extract_features(race_obj)
            for i, h in enumerate(race_obj.horses):
                row = df_feats.iloc[i].to_dict()
                row["is_win"] = 1 if h.horse_number == r["first_horse_number"] else 0
                row["is_place"] = 1 if h.horse_number in top3 else 0
                row["sample_weight"] = weight
                row["race_id"] = r["race_id"]
                rows.append(row)
        return pd.DataFrame(rows)

    def _winner_log_loss(self, predictor: HorseRacePredictor, races: List[Dict[str, Any]]) -> float:
        """Average -log P(winner) of the raw base model (no combiner) on the given races."""
        losses = []
        for r in races:
            race_obj = get_race_by_id(r["race_id"])
            if not race_obj or not race_obj.horses:
                continue
            X = extract_features(race_obj)[FEATURE_COLUMNS]
            probs = predictor.win_model.predict_proba(X)[:, 1]
            probs = probs / probs.sum() if probs.sum() > 0 else np.ones(len(probs)) / len(probs)
            nums = [h.horse_number for h in race_obj.horses]
            if r["first_horse_number"] in nums:
                losses.append(-math.log(max(probs[nums.index(r["first_horse_number"])], EPS)))
        return float(np.mean(losses)) if losses else float("nan")

    def _train(self, base_df: pd.DataFrame, feedback_df: pd.DataFrame, target: HorseRacePredictor, save: bool):
        base = base_df.copy()
        base["sample_weight"] = 1.0
        combined = pd.concat([base, feedback_df], ignore_index=True) if len(feedback_df) else base
        target.train(combined, sample_weight=combined["sample_weight"].values, save=save)
        return len(combined)

    def retrain_from_feedback(self) -> Dict[str, Any]:
        """
        Retrain the base model with real results (hard-example weighted).
        With enough verified races, the candidate is validated on the most recent races first
        and only adopted when it is not worse than the current model.
        """
        completed = get_all_completed_races()
        verified_ids = [r["race_id"] for r in list_reviewed_races()]
        base_df = generate_synthetic_historical_data(num_races=250)

        summary = {"adopted": False, "holdout_races": 0}
        if len(verified_ids) >= HOLDOUT_MIN_RACES:
            holdout_ids = set(verified_ids[-max(HOLDOUT_SIZE_MIN, len(verified_ids) // 4):])
            train_races = [r for r in completed if r["race_id"] not in holdout_ids]
            holdout_races = [r for r in completed if r["race_id"] in holdout_ids]

            candidate = HorseRacePredictor.__new__(HorseRacePredictor)
            candidate.combiner_coef = None
            self._train(base_df, self._feedback_frame(train_races), candidate, save=False)

            cand_loss = self._winner_log_loss(candidate, holdout_races)
            cur_loss = self._winner_log_loss(self.predictor, holdout_races)
            summary.update({
                "holdout_races": len(holdout_races),
                "holdout_log_loss_candidate": round(cand_loss, 4),
                "holdout_log_loss_current": round(cur_loss, 4),
            })
            summary["adopted"] = bool(cand_loss <= cur_loss)

        feedback_df = self._feedback_frame(completed)
        if summary["adopted"]:
            total = self._train(base_df, feedback_df, self.predictor, save=True)
            summary["reason"] = "直近レースでの検証で悪化しないことを確認し、再学習モデルを採用"
        else:
            total = len(base_df) + len(feedback_df)
            if summary["holdout_races"]:
                summary["reason"] = "再学習モデルが直近レースで悪化したため不採用（現行モデルを維持）"
            else:
                summary["reason"] = f"検証済みレースが{HOLDOUT_MIN_RACES}件未満のため、ベースモデルの再学習は保留"

        self.generation += 1
        set_learning_state("generation", self.generation)
        summary.update({
            "training_samples": total,
            "real_feedback_samples": len(feedback_df),
            "new_generation": self.generation,
        })
        return summary

    # ------------------------------------------------------------------ reporting
    def _append_history(self, entry: Dict[str, Any]) -> None:
        history = get_learning_state("history", [])
        history.append(entry)
        set_learning_state("history", history[-HISTORY_LIMIT:])

    def calculate_performance_stats(self) -> Dict[str, Any]:
        """
        Hit rate %, recovery rate (回収率 ROI %) and probability accuracy, computed from the
        predictions that were made BEFORE each race.
        """
        reviewed = list_reviewed_races()
        if not reviewed:
            return {
                "total_races": 0,
                "win_hits": 0,
                "win_hit_rate": 0.0,
                "place_hits": 0,
                "place_hit_rate": 0.0,
                "total_stake": 0,
                "total_payout": 0,
                "recovery_rate": 100.0,  # Baseline
                "roi_status": "初期化状態 (データ蓄積中)",
                "avg_model_log_loss": None,
                "avg_market_log_loss": None,
                "generation": self.generation
            }

        total_races = len(reviewed)
        win_hits = sum(1 for r in reviewed if r["review"]["win_hit"])
        place_hits = sum(1 for r in reviewed if r["review"]["place_hit"])
        total_stake = total_races * STAKE_PER_RACE
        total_payout = sum((r["result"]["win_payout"] / 100.0) * STAKE_PER_RACE
                           for r in reviewed if r["review"]["win_hit"])

        win_hit_rate = round((win_hits / total_races) * 100, 1)
        place_hit_rate = round((place_hits / total_races) * 100, 1)
        recovery_rate = round((total_payout / total_stake) * 100, 1)

        if recovery_rate >= 120.0:
            roi_status = "超高収益 (黒字拡大中)"
        elif recovery_rate >= 100.0:
            roi_status = "目標達成 (回収率100%超)"
        elif recovery_rate >= 80.0:
            roi_status = "堅調 (微増調整中)"
        else:
            roi_status = "学習フィードバック強化中"

        return {
            "total_races": total_races,
            "win_hits": win_hits,
            "win_hit_rate": win_hit_rate,
            "place_hits": place_hits,
            "place_hit_rate": place_hit_rate,
            "total_stake": total_stake,
            "total_payout": round(total_payout, 0),
            "recovery_rate": recovery_rate,
            "roi_status": roi_status,
            "avg_model_log_loss": round(float(np.mean([r["review"]["metrics"]["model_log_loss"] for r in reviewed])), 4),
            "avg_market_log_loss": round(float(np.mean([r["review"]["metrics"]["market_log_loss"] for r in reviewed])), 4),
            "generation": self.generation
        }

    def get_learning_report(self) -> Dict[str, Any]:
        reviewed = list_reviewed_races()
        aggregate = aggregate_reviews([r["review"] for r in reviewed])
        coef = self.predictor.combiner_coef or DEFAULT_COEF
        return {
            "stats": self.calculate_performance_stats(),
            "aggregate": aggregate,
            "combiner": describe_coef(coef),
            "history": get_learning_state("history", []),
            "recent_reviews": [r["review"] for r in reviewed[-5:]][::-1],
        }
