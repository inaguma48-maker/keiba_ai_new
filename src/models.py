"""
Data models and schemas for the Horse Racing Prediction Application.
"""

from typing import List, Dict, Optional, Any
from dataclasses import dataclass, asdict

@dataclass
class HorseEntry:
    horse_number: int
    horse_name: str
    jockey_name: str
    trainer_name: str
    age: int
    weight: float
    impost: float  # 斤量
    past_speed_rating: float  # 過去走スピード指数 (例: 50~110)
    past_win_rate: float      # 過去勝率 (0.0~1.0)
    jockey_win_rate: float    # 騎手勝率 (0.0~1.0)
    trainer_win_rate: float   # 調教師勝率 (0.0~1.0)
    track_aptitude: float     # 馬場適性 (0.0~1.0)
    odds: float               # 単勝オッズ

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

@dataclass
class RaceInfo:
    race_id: str
    race_name: str
    track_name: str  # 例: 東京, 中山, 阪神, 京都
    surface_type: str  # 芝, ダート
    distance: int      # 距離 (m)
    track_condition: str  # 良, 稍重, 重, 不良
    weather: str          # 晴, 曇, 雨
    horses: List[HorseEntry]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "race_id": self.race_id,
            "race_name": self.race_name,
            "track_name": self.track_name,
            "surface_type": self.surface_type,
            "distance": self.distance,
            "track_condition": self.track_condition,
            "weather": self.weather,
            "horses": [h.to_dict() for h in self.horses]
        }
