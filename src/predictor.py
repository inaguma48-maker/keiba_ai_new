"""
Machine Learning Prediction Engine for Horse Racing Prediction.
Trains LightGBM / RandomForest models and calculates win/place probabilities.
"""

import os
import joblib
import numpy as np
import pandas as pd
from typing import List, Dict, Any, Tuple
from lightgbm import LGBMClassifier
from sklearn.ensemble import RandomForestClassifier

from src.models import RaceInfo, HorseEntry
from src.data import generate_synthetic_historical_data, extract_features

FEATURE_COLUMNS = [
    "age", "weight", "impost", "impost_ratio", "past_speed_rating",
    "past_win_rate", "jockey_win_rate", "trainer_win_rate", "track_aptitude",
    "odds", "implied_prob", "composite_score", "track_condition_val",
    "distance", "total_horses", "speed_rank", "composite_rank",
    "relative_speed", "relative_composite"
]

MODEL_FILE_PATH = "model_cache.pkl"

class HorseRacePredictor:
    def __init__(self):
        self.win_model = None
        self.place_model = None
        self.is_trained = False
        self._load_or_train_default()

    def train(self, df: pd.DataFrame):
        """
        Train LightGBM / RandomForest ensemble models for Win and Place prediction.
        """
        X = df[FEATURE_COLUMNS]
        y_win = df["is_win"]
        y_place = df["is_place"]

        # Win Model: LightGBM
        self.win_model = LGBMClassifier(
            n_estimators=100,
            learning_rate=0.05,
            num_leaves=15,
            random_state=42,
            verbosity=-1
        )
        self.win_model.fit(X, y_win)

        # Place Model: RandomForest for smooth place probability
        self.place_model = RandomForestClassifier(
            n_estimators=100,
            max_depth=6,
            random_state=42
        )
        self.place_model.fit(X, y_place)

        self.is_trained = True
        self._save_model()

    def _save_model(self):
        try:
            joblib.dump({
                "win_model": self.win_model,
                "place_model": self.place_model,
                "is_trained": self.is_trained
            }, MODEL_FILE_PATH)
        except Exception as e:
            print(f"Warning: Could not save model cache: {e}")

    def _load_or_train_default(self):
        if os.path.exists(MODEL_FILE_PATH):
            try:
                data = joblib.load(MODEL_FILE_PATH)
                self.win_model = data["win_model"]
                self.place_model = data["place_model"]
                self.is_trained = data["is_trained"]
                return
            except Exception:
                pass

        # If model file does not exist, train on synthetic dataset
        synth_df = generate_synthetic_historical_data(num_races=250)
        self.train(synth_df)

    def predict_race(self, race: RaceInfo) -> List[Dict[str, Any]]:
        """
        Predict win and place probabilities for each horse in the given race.
        Returns a list of dicts with horse info, win prob, place prob, and expected score.
        """
        if not self.is_trained:
            synth_df = generate_synthetic_historical_data(num_races=250)
            self.train(synth_df)

        df_feats = extract_features(race)
        X = df_feats[FEATURE_COLUMNS]

        # Raw predicted win probabilities
        raw_win_probs = self.win_model.predict_proba(X)[:, 1]
        # Raw predicted place probabilities
        raw_place_probs = self.place_model.predict_proba(X)[:, 1]

        # Normalize win probabilities to sum to 1.0 (since exactly 1 horse wins)
        sum_win = np.sum(raw_win_probs)
        if sum_win > 0:
            norm_win_probs = raw_win_probs / sum_win
        else:
            norm_win_probs = np.ones(len(race.horses)) / len(race.horses)

        # Normalize place probabilities to sum to min(3, total_horses)
        target_place_sum = min(3.0, float(len(race.horses)))
        sum_place = np.sum(raw_place_probs)
        if sum_place > 0:
            norm_place_probs = np.clip(raw_place_probs * (target_place_sum / sum_place), 0.05, 0.95)
        else:
            norm_place_probs = np.ones(len(race.horses)) * (target_place_sum / len(race.horses))

        results = []
        for i, h in enumerate(race.horses):
            win_prob = float(norm_win_probs[i])
            place_prob = float(norm_place_probs[i])

            # Expected value multiplier for Win: EV = Prob * Odds
            win_ev = win_prob * h.odds

            results.append({
                "horse_number": h.horse_number,
                "horse_name": h.horse_name,
                "jockey_name": h.jockey_name,
                "odds": h.odds,
                "win_probability": round(win_prob, 4),
                "place_probability": round(place_prob, 4),
                "win_ev": round(win_ev, 3),
                "composite_score": round(df_feats.iloc[i]["composite_score"], 1),
                "past_speed_rating": h.past_speed_rating,
            })

        # Sort by predicted win probability descending
        results.sort(key=lambda x: x["win_probability"], reverse=True)
        return results
