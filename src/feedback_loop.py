"""
Self-Growing Feedback Loop Engine for Horse Racing AI Predictor.
Collects actual race outcomes, evaluates hit rates and recovery rates (回収率 ROI %),
applies importance-weighted feedback retraining to achieve and sustain >100% recovery rates.
"""

import pandas as pd
import numpy as np
from typing import List, Dict, Any, Tuple
from src.db import (
    save_race_result, get_race_result, get_race_by_id,
    get_all_completed_races, list_all_races, save_prediction_log
)
from src.data import extract_features, generate_synthetic_historical_data
from src.predictor import HorseRacePredictor, FEATURE_COLUMNS

class SelfLearningEngine:
    def __init__(self, predictor: HorseRacePredictor):
        self.predictor = predictor
        self.generation = 1

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
        Record actual race finish numbers and payouts into DB and trigger self-learning update.
        """
        save_race_result(
            race_id=race_id,
            first=first_horse_number,
            second=second_horse_number,
            third=third_horse_number,
            win_payout=win_payout,
            place_payout=place_payout
        )

        # Trigger model retraining with updated feedback data
        retrain_summary = self.retrain_from_feedback()
        stats = self.calculate_performance_stats()

        return {
            "status": "success",
            "message": f"レース結果を蓄積し、AI自己成長ループ（世代 {self.generation}）を適用しました。",
            "retrain_summary": retrain_summary,
            "performance_stats": stats
        }

    def calculate_performance_stats(self) -> Dict[str, Any]:
        """
        Calculate model accuracy, hit rate %, and return on investment (回収率 ROI %)
        across all recorded completed races.
        """
        completed = get_all_completed_races()
        if not completed:
            return {
                "total_races": 0,
                "win_hit_rate": 0.0,
                "place_hit_rate": 0.0,
                "total_stake": 0,
                "total_payout": 0,
                "recovery_rate": 100.0,  # Baseline
                "roi_status": "初期化状態 (データ蓄積中)",
                "generation": self.generation
            }

        total_races = len(completed)
        win_hits = 0
        place_hits = 0
        total_stake = total_races * 1000  # Assume 1,000 JPY standard wager unit per race
        total_payout = 0.0

        for r in completed:
            race_obj = get_race_by_id(r["race_id"])
            if not race_obj or not race_obj.horses:
                continue

            predictions = self.predictor.predict_race(race_obj)
            if not predictions:
                continue

            top_pick = predictions[0]
            top_horse_num = top_pick["horse_number"]

            first_num = r["first_horse_number"]
            second_num = r["second_horse_number"]
            third_num = r["third_horse_number"]

            # Win Hit check
            if top_horse_num == first_num:
                win_hits += 1
                total_payout += (r["win_payout"] / 100.0) * 1000.0

            # Place Hit check
            if top_horse_num in [first_num, second_num, third_num]:
                place_hits += 1

        win_hit_rate = round((win_hits / total_races) * 100, 1) if total_races > 0 else 0.0
        place_hit_rate = round((place_hits / total_races) * 100, 1) if total_races > 0 else 0.0

        recovery_rate = round((total_payout / total_stake) * 100, 1) if total_stake > 0 else 100.0

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
            "generation": self.generation
        }

    def retrain_from_feedback(self) -> Dict[str, Any]:
        """
        Construct a training dataset combining historical baseline data and actual race feedback.
        Feedback data is heavily weighted to steer the model towards high-ROI predictions.
        """
        completed = get_all_completed_races()

        # Start with base historical dataset
        base_df = generate_synthetic_historical_data(num_races=250)

        feedback_rows = []
        for r in completed:
            race_obj = get_race_by_id(r["race_id"])
            if not race_obj:
                continue

            first_num = r["first_horse_number"]
            second_num = r["second_horse_number"]
            third_num = r["third_horse_number"]

            df_feats = extract_features(race_obj)
            for i, h in enumerate(race_obj.horses):
                row = df_feats.iloc[i].to_dict()
                row["is_win"] = 1 if h.horse_number == first_num else 0
                row["is_place"] = 1 if h.horse_number in [first_num, second_num, third_num] else 0

                # Multiply feedback samples to give higher importance to actual real-world results
                for _ in range(5):
                    feedback_rows.append(row)

        if feedback_rows:
            feedback_df = pd.DataFrame(feedback_rows)
            combined_df = pd.concat([base_df, feedback_df], ignore_index=True)
        else:
            combined_df = base_df

        # Re-train models with reinforced feedback
        self.predictor.train(combined_df)
        self.generation += 1

        return {
            "training_samples": len(combined_df),
            "real_feedback_samples": len(feedback_rows),
            "new_generation": self.generation
        }
