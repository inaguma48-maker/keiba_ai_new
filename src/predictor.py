"""
Machine Learning Prediction Engine for Horse Racing Prediction.
Trains LightGBM / RandomForest models and calculates win/place probabilities with High-Volatility (荒れ度) analysis.
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

        # Win Model: LightGBM tuned for high discrimination power
        self.win_model = LGBMClassifier(
            n_estimators=150,
            learning_rate=0.04,
            num_leaves=20,
            subsample=0.8,
            colsample_bytree=0.8,
            random_state=42,
            verbosity=-1
        )
        self.win_model.fit(X, y_win)

        # Place Model: RandomForest for smooth place probability
        self.place_model = RandomForestClassifier(
            n_estimators=120,
            max_depth=7,
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
        synth_df = generate_synthetic_historical_data(num_races=300)
        self.train(synth_df)

    def analyze_3rd_place_trends(self, race: RaceInfo) -> Dict[str, Any]:
        """
        Analyzes historical trends using the 7 conditions:
        1. 前走人気 (prev_popularity)
        2. 馬体重 (weight)
        3. 調教場 (training_center)
        4. 生産牧場 (breeding_farm)
        5. 前走着順 (prev_rank)
        6. 前走距離 (prev_distance)
        7. 前走レース (prev_race_name)

        Generates bulleted Japanese explanations for:
        - 絶対に3着に来ない馬の理由 (Reasons for cutting/disqualifying from top 3)
        - 3着に来る(残す)馬の理由 (Reasons for keeping in top 3)
        """
        cut_horses = []
        keep_horses = []

        for h in race.horses:
            cut_reasons = []
            keep_reasons = []

            # 1. 前走人気 (prev_popularity)
            if h.prev_popularity >= 10:
                cut_reasons.append(f"前走{h.prev_popularity}番人気と支持率が低く好走再現性に疑問")
            elif h.prev_popularity <= 3:
                keep_reasons.append(f"前走{h.prev_popularity}番人気と上位人気で実力を立証済み")

            # 2. 馬体重 (weight)
            if h.weight < 450.0:
                cut_reasons.append(f"馬体重{int(h.weight)}kgと軽量で長距離・坂のあるタフな展開での体力不足懸念")
            elif h.weight >= 480.0:
                keep_reasons.append(f"馬体重{int(h.weight)}kgと恵まれた馬体でタフな競り合い・軸安定感あり")

            # 3. 調教場 (training_center)
            if h.training_center == "地方・美浦坂路難あり":
                cut_reasons.append(f"調教場が{h.training_center}で直前仕上げに疑問")
            else:
                keep_reasons.append(f"調教場({h.training_center})で順調な最終追い切りとタイムを消化")

            # 4. 生産牧場 (breeding_farm)
            if h.breeding_farm in ["ノーザンファーム", "社台ファーム", "社台コーポレーション"]:
                keep_reasons.append(f"生産牧場が最高峰の[{h.breeding_farm}]で外厩仕上げ・素質血統重視")

            # 5. 前走着順 (prev_rank)
            if h.prev_rank >= 8:
                cut_reasons.append(f"前走{h.prev_rank}着と大敗しており一変の期待値が低い")
            elif h.prev_rank <= 3:
                keep_reasons.append(f"前走{h.prev_rank}着と好走トレンドを維持")

            # 6. 前走距離 (prev_distance)
            dist_diff = abs(h.prev_distance - race.distance)
            if dist_diff >= 600:
                cut_reasons.append(f"前走距離({h.prev_distance}m)から今走({race.distance}m)への距離差{dist_diff}mと展開適応に難あり")
            elif dist_diff <= 200:
                keep_reasons.append(f"前走距離({h.prev_distance}m)から同等距離({race.distance}m)で展開・ペース追従性が抜群")

            # 7. 前走レース (prev_race_name)
            if "G1" in h.prev_race_name or "G2" in h.prev_race_name or "重賞" in h.prev_race_name or "ステップ" in h.prev_race_name:
                keep_reasons.append(f"前走格上の[{h.prev_race_name}]を経由しておりレースレベルの経験値が勝る")

            # Categorize into cut vs keep
            if len(cut_reasons) >= 2 or h.odds >= 30.0 or h.prev_rank >= 10:
                cut_horses.append({
                    "horse_number": h.horse_number,
                    "horse_name": h.horse_name,
                    "odds": h.odds,
                    "reasons": cut_reasons if cut_reasons else ["前走データおよび馬体重・調教での好走データ条件を満たさず3着内率は極めて低い"]
                })
            else:
                keep_horses.append({
                    "horse_number": h.horse_number,
                    "horse_name": h.horse_name,
                    "odds": h.odds,
                    "reasons": keep_reasons if keep_reasons else ["前走人気・馬体重・牧場データの複合条件をクリアし3着内軸として有力"]
                })

        return {
            "cut_horses": cut_horses,
            "keep_horses": keep_horses
        }

    def calculate_race_volatility(self, race: RaceInfo) -> Dict[str, Any]:
        """
        Analyze race volatility / upset potential (荒れ度 index).
        High volatility = favorite is vulnerable, dark horses offer high EV for >100% ROI.
        """
        if not race.horses:
            return {"volatility_level": "中平穏", "volatility_score": 50, "is_high_volatility": False, "description": "馬情報なし"}

        odds_list = sorted([h.odds for h in race.horses if h.odds > 0])
        if not odds_list:
            return {"volatility_level": "中平穏", "volatility_score": 50, "is_high_volatility": False, "description": "オッズ未確定"}

        top1_odds = odds_list[0]
        top3_odds = odds_list[:3]
        total_horses = len(race.horses)

        # Variance/std dev of top odds
        std_odds = float(np.std(odds_list[:min(8, len(odds_list))]))

        # Volatility Score (0 - 100)
        # Higher score = more competitive/unpredictable/high-payout race
        score = 50.0

        if top1_odds >= 4.0:
            score += 25  # No solid favorite (混戦・大荒れ気配)
        elif top1_odds >= 3.0:
            score += 15
        elif top1_odds <= 1.8:
            score -= 25  # Super strong favorite (堅い本命)

        if total_horses >= 14:
            score += 15
        elif total_horses <= 9:
            score -= 10

        if std_odds < 3.0:
            score += 10  # Very tight odds distribution (接戦)

        score = max(5.0, min(95.0, score))

        if score >= 70:
            level = "超大荒れ警戒 (HIGH ROI TARGET)"
            desc = "本命馬が脆く、中穴・大穴の頭・ヒモ荒れで高配当が狙える超高回収率ターゲットレース"
            is_high = True
        elif score >= 55:
            level = "波乱含み (UPSET POTENTIAL)"
            desc = "1番人気と後続の能力差が小さく、期待値(EV)重視の買い目構築で100%超を狙えるレース"
            is_high = True
        elif score >= 35:
            level = "標準・中平穏"
            desc = "本命と対抗が堅実。軸馬から相手を適度にひねる標準的レース"
            is_high = False
        else:
            level = "本命堅固 (LOW VOLATILITY)"
            desc = "上位人気の信頼度が高くトリガミ注意。買目を絞って回収率を確保すべきレース"
            is_high = False

        return {
            "volatility_level": level,
            "volatility_score": round(score, 1),
            "is_high_volatility": is_high,
            "top1_odds": top1_odds,
            "description": desc
        }

    def predict_race(self, race: RaceInfo) -> List[Dict[str, Any]]:
        """
        Predict win and place probabilities for each horse in the given race.
        Includes high-volatility adjustments for ROI optimization.
        """
        if not self.is_trained:
            synth_df = generate_synthetic_historical_data(num_races=300)
            self.train(synth_df)

        df_feats = extract_features(race)
        X = df_feats[FEATURE_COLUMNS]

        # Raw predicted win probabilities
        raw_win_probs = self.win_model.predict_proba(X)[:, 1]
        # Raw predicted place probabilities
        raw_place_probs = self.place_model.predict_proba(X)[:, 1]

        # Normalize win probabilities to sum to 1.0
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

        volatility_info = self.calculate_race_volatility(race)

        results = []
        for i, h in enumerate(race.horses):
            win_prob = float(norm_win_probs[i])
            place_prob = float(norm_place_probs[i])

            # Implied market probability (1 / odds)
            implied_prob = 1.0 / h.odds if h.odds > 0 else 0.05

            # Expected Value (EV = Win Prob * Odds)
            win_ev = win_prob * h.odds

            # Value edge: Model Prob - Implied Prob
            value_edge = round(win_prob - implied_prob, 4)

            # Dark Horse / Value Tag determination
            if win_ev >= 1.15 and h.odds >= 5.0:
                value_tag = "超高期待値・穴馬 (HIGH ROI)"
            elif win_ev >= 1.0:
                value_tag = "高期待値 (POSITIVE EV)"
            elif win_prob >= 0.25:
                value_tag = "本命軸 (SOLID FAVORITE)"
            else:
                value_tag = "過小評価警戒" if value_edge > 0.02 else "通常"

            results.append({
                "horse_number": h.horse_number,
                "horse_name": h.horse_name,
                "jockey_name": h.jockey_name,
                "odds": h.odds,
                "win_probability": round(win_prob, 4),
                "place_probability": round(place_prob, 4),
                "win_ev": round(win_ev, 3),
                "value_edge": value_edge,
                "value_tag": value_tag,
                "composite_score": round(df_feats.iloc[i]["composite_score"], 1),
                "past_speed_rating": h.past_speed_rating,
            })

        # Sort by predicted win probability descending
        results.sort(key=lambda x: x["win_probability"], reverse=True)
        return results
