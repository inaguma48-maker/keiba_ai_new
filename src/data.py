"""
Data generation and feature engineering for Japanese Horse Racing prediction.
"""

import numpy as np
import pandas as pd
from typing import List, Dict, Any, Tuple
from src.models import HorseEntry, RaceInfo

TRACK_CONDITIONS = {"良": 1.0, "稍重": 0.9, "重": 0.8, "不良": 0.7}
WEATHER_TYPES = ["晴", "曇", "雨"]
TRACK_NAMES = ["東京", "中山", "阪神", "京都", "中京", "新潟"]
SURFACE_TYPES = ["芝", "ダート"]

SAMPLE_HORSE_NAMES = [
    "ディープスター", "コントレイルネクスト", "アーモンドゴールド", "オルフェインパクト", "エフフォーリアワン",
    "イクイノックスビジョン", "タイトルホルダーキング", "ソダシホワイト", "グランアレグリアスター", "クロノジェネシスクイーン",
    "ドゥラメンテロード", "キタサンブラックパワー", "モーリスサンシャイン", "ゴールドシップウェイ", "ウオッカスペシャリティ",
    "ダノンプレミアムエース", "ヴェラアズールフラッシュ", "シャフリヤールクラウン", "ジャックドールスピード", "レイパパレウィナー"
]

JOCKEY_NAMES = ["ルメール", "川田", "武豊", "福永", "横山武", "松山", "戸崎", "デムーロ", "岩田望", "坂井"]
TRAINER_NAMES = ["矢作", "木村", "国枝", "友道", "中内田", "手塚", "池江", "杉山晴", "須貝", "安田翔"]


def extract_features(race: RaceInfo) -> pd.DataFrame:
    """
    Extract feature DataFrame from a RaceInfo object for machine learning models.
    """
    rows = []
    condition_val = TRACK_CONDITIONS.get(race.track_condition, 1.0)
    total_horses = len(race.horses)

    for h in race.horses:
        implied_prob = 1.0 / max(h.odds, 1.01)
        impost_ratio = h.impost / max(h.weight, 400.0)

        # Composite performance score
        composite_score = (
            h.past_speed_rating * 0.4 +
            h.past_win_rate * 100 * 0.2 +
            h.jockey_win_rate * 100 * 0.2 +
            h.trainer_win_rate * 100 * 0.1 +
            h.track_aptitude * 100 * 0.1
        )

        row = {
            "horse_number": h.horse_number,
            "age": h.age,
            "weight": h.weight,
            "impost": h.impost,
            "impost_ratio": impost_ratio,
            "past_speed_rating": h.past_speed_rating,
            "past_win_rate": h.past_win_rate,
            "jockey_win_rate": h.jockey_win_rate,
            "trainer_win_rate": h.trainer_win_rate,
            "track_aptitude": h.track_aptitude,
            "odds": h.odds,
            "implied_prob": implied_prob,
            "composite_score": composite_score,
            "track_condition_val": condition_val,
            "distance": race.distance,
            "total_horses": total_horses,
        }
        rows.append(row)

    df = pd.DataFrame(rows)
    # Relative features normalized within the race
    df["speed_rank"] = df["past_speed_rating"].rank(ascending=False)
    df["composite_rank"] = df["composite_score"].rank(ascending=False)
    df["relative_speed"] = df["past_speed_rating"] - df["past_speed_rating"].mean()
    df["relative_composite"] = df["composite_score"] - df["composite_score"].mean()

    return df


def generate_synthetic_historical_data(num_races: int = 300) -> pd.DataFrame:
    """
    Generate synthetic historical race data for model training.
    Realistic simulation where higher speed rating and lower odds correlate with better finish positions.
    """
    np.random.seed(42)
    records = []

    for race_idx in range(1, num_races + 1):
        num_horses = np.random.randint(8, 17)
        track_name = np.random.choice(TRACK_NAMES)
        surface_type = np.random.choice(SURFACE_TYPES)
        distance = np.random.choice([1200, 1600, 1800, 2000, 2400])
        condition = np.random.choice(["良", "稍重", "重", "不良"], p=[0.6, 0.2, 0.1, 0.1])
        condition_val = TRACK_CONDITIONS[condition]

        race_horses = []
        raw_scores = []

        for h_idx in range(1, num_horses + 1):
            base_speed = np.random.normal(75, 10)
            past_win_rate = np.clip(np.random.beta(2, 5), 0.05, 0.6)
            jockey_win_rate = np.clip(np.random.beta(2, 6), 0.05, 0.35)
            trainer_win_rate = np.clip(np.random.beta(2, 6), 0.05, 0.35)
            track_aptitude = np.clip(np.random.beta(5, 2), 0.2, 1.0)
            weight = np.random.uniform(440, 520)
            impost = np.random.choice([54.0, 55.0, 56.0, 57.0, 58.0])

            # Latent performance strength
            latent_ability = (
                base_speed * 0.45 +
                past_win_rate * 40 +
                jockey_win_rate * 30 +
                trainer_win_rate * 20 +
                track_aptitude * 15 -
                (impost - 55.0) * 1.5
            )
            raw_scores.append(latent_ability)

            # Odds simulation based on latent ability with noise
            perceived_strength = latent_ability + np.random.normal(0, 5)
            raw_scores_arr = np.array(raw_scores)

            race_horses.append({
                "horse_number": h_idx,
                "horse_name": f"馬_{race_idx}_{h_idx}",
                "jockey_name": np.random.choice(JOCKEY_NAMES),
                "trainer_name": np.random.choice(TRAINER_NAMES),
                "age": np.random.choice([3, 4, 5, 6]),
                "weight": weight,
                "impost": impost,
                "past_speed_rating": base_speed,
                "past_win_rate": past_win_rate,
                "jockey_win_rate": jockey_win_rate,
                "trainer_win_rate": trainer_win_rate,
                "track_aptitude": track_aptitude,
                "latent_ability": latent_ability,
            })

        # Calculate realistic odds using softmax of perceived strength
        strengths = np.array([h["latent_ability"] + np.random.normal(0, 4) for h in race_horses])
        exp_strengths = np.exp((strengths - np.max(strengths)) / 10.0)
        probs = exp_strengths / np.sum(exp_strengths)

        # Calculate finishing order with randomness
        race_day_performances = strengths + np.random.normal(0, 6, size=len(race_horses))
        finish_ranks = np.argsort(-race_day_performances) + 1  # 1st, 2nd, ...

        for h_idx, h in enumerate(race_horses):
            odds = max(1.1, float(np.round(1.0 / (probs[h_idx] * 0.8), 1)))
            h["odds"] = odds
            finish_pos = int(finish_ranks[h_idx])
            h["finish_position"] = finish_pos
            h["is_win"] = 1 if finish_pos == 1 else 0
            h["is_place"] = 1 if finish_pos <= 3 else 0

            # Construct feature row
            race_obj = RaceInfo(
                race_id=f"R{race_idx:04d}",
                race_name=f"模擬レース_{race_idx}",
                track_name=track_name,
                surface_type=surface_type,
                distance=distance,
                track_condition=condition,
                weather="晴",
                horses=[HorseEntry(
                    horse_number=h["horse_number"],
                    horse_name=h["horse_name"],
                    jockey_name=h["jockey_name"],
                    trainer_name=h["trainer_name"],
                    age=h["age"],
                    weight=h["weight"],
                    impost=h["impost"],
                    past_speed_rating=h["past_speed_rating"],
                    past_win_rate=h["past_win_rate"],
                    jockey_win_rate=h["jockey_win_rate"],
                    trainer_win_rate=h["trainer_win_rate"],
                    track_aptitude=h["track_aptitude"],
                    odds=h["odds"]
                )]
            )
            df_feats = extract_features(race_obj)
            row = df_feats.iloc[0].to_dict()
            row["race_id"] = f"R{race_idx:04d}"
            row["finish_position"] = finish_pos
            row["is_win"] = h["is_win"]
            row["is_place"] = h["is_place"]
            records.append(row)

    return pd.DataFrame(records)


def get_sample_races() -> List[RaceInfo]:
    """
    Returns preset sample races representing typical Japan Cup / Arima Kinen / Derby scenarios.
    """
    races = [
        RaceInfo(
            race_id="R2026_01",
            race_name="第45回 ジャパンカップ (G1)",
            track_name="東京",
            surface_type="芝",
            distance=2400,
            track_condition="良",
            weather="晴",
            horses=[
                HorseEntry(1, "イクイノックスビジョン", "ルメール", "木村", 4, 492, 58.0, 98.5, 0.75, 0.28, 0.22, 0.95, 1.8),
                HorseEntry(2, "ドウデュースパワー", "武豊", "友道", 5, 504, 58.0, 95.0, 0.55, 0.22, 0.24, 0.90, 3.2),
                HorseEntry(3, "スターズオンアース", "川田", "高柳", 5, 484, 56.0, 92.0, 0.45, 0.25, 0.18, 0.88, 5.5),
                HorseEntry(4, "ジャスティンパレス", "鮫島駿", "杉山晴", 5, 472, 58.0, 90.0, 0.38, 0.15, 0.20, 0.85, 8.4),
                HorseEntry(5, "タイトルホルダー", "横山和", "栗田", 6, 476, 58.0, 89.5, 0.42, 0.14, 0.16, 0.80, 11.2),
                HorseEntry(6, "ヴェラアズール", "松山", "渡辺", 6, 518, 58.0, 88.0, 0.35, 0.16, 0.15, 0.82, 16.0),
                HorseEntry(7, "ダノンベルーガ", "モレイラ", "堀", 5, 500, 58.0, 91.0, 0.30, 0.26, 0.19, 0.86, 9.8),
                HorseEntry(8, "ディープボンド", "和田竜", "大久保", 7, 506, 58.0, 86.0, 0.28, 0.12, 0.14, 0.78, 24.5),
            ]
        ),
        RaceInfo(
            race_id="R2026_02",
            race_name="第69回 有馬記念 (G1)",
            track_name="中山",
            surface_type="芝",
            distance=2500,
            track_condition="稍重",
            weather="曇",
            horses=[
                HorseEntry(1, "ソールオリエンス", "横山武", "手塚", 4, 468, 58.0, 93.0, 0.50, 0.19, 0.20, 0.92, 2.9),
                HorseEntry(2, "タスティエーラ", "レーン", "堀", 4, 490, 58.0, 92.5, 0.48, 0.27, 0.21, 0.89, 3.8),
                HorseEntry(3, "ジャスティンミラクル", "戸崎", "友道", 3, 482, 56.0, 94.0, 0.60, 0.18, 0.24, 0.87, 4.2),
                HorseEntry(4, "レガレイラ", "ルメール", "木村", 3, 456, 54.0, 91.5, 0.50, 0.28, 0.22, 0.91, 5.0),
                HorseEntry(5, "ベラジオオペラ", "横山和", "上村", 4, 502, 58.0, 89.0, 0.40, 0.14, 0.17, 0.84, 12.0),
                HorseEntry(6, "ローシャムパーク", "戸崎", "田中博", 5, 500, 58.0, 88.5, 0.38, 0.18, 0.18, 0.81, 15.6),
                HorseEntry(7, "プログノーシス", "川田", "中内田", 6, 480, 58.0, 90.5, 0.45, 0.25, 0.23, 0.85, 7.8),
                HorseEntry(8, "ボルドグフーシュ", "吉田隼", "宮本", 5, 496, 58.0, 85.0, 0.25, 0.11, 0.12, 0.75, 33.0),
            ]
        )
    ]
    return races
