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

# Comprehensive JRA 10 Racetracks Profile Dataset (Course shape, direction, straight length, slope, surface types)
JRA_TRACK_PROFILES: Dict[str, Dict[str, Any]] = {
    "東京": {
        "direction": "左回り (カウンタークロック)",
        "shape": "大回り・緩やかな4コーナー",
        "home_stretch_m": 525.9,
        "max_slope_m": 2.1,
        "slope_desc": "ゴール手前526mの直線に高低差2.1mの激坂（つくし坂）",
        "turf_color": "#2e7d32",
        "dirt_color": "#a1887f",
        "obstacle_color": "#1565c0",
        "has_slope": True,
        "has_obstacle_course": True
    },
    "中山": {
        "direction": "右回り (クロックワイズ)",
        "shape": "小回り・急カーブ・急坂",
        "home_stretch_m": 310.0,
        "max_slope_m": 5.3,
        "slope_desc": "ゴール前310mの直線に最大高低差5.3m（急坂2.2m）",
        "turf_color": "#388e3c",
        "dirt_color": "#8d6e63",
        "obstacle_color": "#0d47a1",
        "has_slope": True,
        "has_obstacle_course": True
    },
    "京都": {
        "direction": "右回り (クロックワイズ)",
        "shape": "平坦・3コーナー淀の坂",
        "home_stretch_m": 404.0,
        "max_slope_m": 4.3,
        "slope_desc": "3コーナー手前に高低差4.3mの『淀の坂』。直線は完全平坦",
        "turf_color": "#43a047",
        "dirt_color": "#795548",
        "obstacle_color": "#1976d2",
        "has_slope": True,
        "has_obstacle_course": True
    },
    "阪神": {
        "direction": "右回り (クロックワイズ)",
        "shape": "外回り(大回り)/内回り(急カーブ)",
        "home_stretch_m": 473.6,
        "max_slope_m": 1.8,
        "slope_desc": "ゴール直前200mに高低差1.8mの急坂",
        "turf_color": "#2e7d32",
        "dirt_color": "#8d6e63",
        "obstacle_color": "#1e88e5",
        "has_slope": True,
        "has_obstacle_course": True
    },
    "中京": {
        "direction": "左回り (カウンタークロック)",
        "shape": "起伏に富む高低差・急坂",
        "home_stretch_m": 412.5,
        "max_slope_m": 3.5,
        "slope_desc": "直線412mの途中に勾配2.0%（高低差2.0m）の急坂",
        "turf_color": "#388e3c",
        "dirt_color": "#9e9e9e",
        "obstacle_color": "#1565c0",
        "has_slope": True,
        "has_obstacle_course": False
    },
    "新潟": {
        "direction": "左回り (直線1000mあり)",
        "shape": "日本一長い直線 (659m)",
        "home_stretch_m": 659.0,
        "max_slope_m": 2.2,
        "slope_desc": "日本唯一の直線1000mコースを併設。外回り直線659mは日本最大",
        "turf_color": "#43a047",
        "dirt_color": "#a1887f",
        "obstacle_color": "#1e88e5",
        "has_slope": False,
        "has_obstacle_course": True
    },
    "福島": {
        "direction": "右回り (クロックワイズ)",
        "shape": "スパイラルカーブ・小回り",
        "home_stretch_m": 292.0,
        "max_slope_m": 2.1,
        "slope_desc": "高低差2.1m。起伏の激しい小回りローカルコース",
        "turf_color": "#4caf50",
        "dirt_color": "#8d6e63",
        "obstacle_color": "#2196f3",
        "has_slope": True,
        "has_obstacle_course": True
    },
    "小倉": {
        "direction": "右回り (クロックワイズ)",
        "shape": "完全平坦・小回り",
        "home_stretch_m": 293.0,
        "max_slope_m": 2.9,
        "slope_desc": "小回りで平坦。スピードと先行力が極めて重要なコース",
        "turf_color": "#4caf50",
        "dirt_color": "#795548",
        "obstacle_color": "#1976d2",
        "has_slope": False,
        "has_obstacle_course": True
    },
    "札幌": {
        "direction": "右回り (クロックワイズ)",
        "shape": "洋芝オール・丸みを帯びた大回り",
        "home_stretch_m": 266.1,
        "max_slope_m": 0.7,
        "slope_desc": "高低差わずか0.7mの平坦洋芝コース。重厚な洋芝適性がカギ",
        "turf_color": "#1b5e20",
        "dirt_color": "#6d4c41",
        "obstacle_color": "#0d47a1",
        "has_slope": False,
        "has_obstacle_course": False
    },
    "函館": {
        "direction": "右回り (クロックワイズ)",
        "shape": "起伏に富む洋芝コース",
        "home_stretch_m": 262.1,
        "max_slope_m": 3.5,
        "slope_desc": "洋芝で高低差3.5m。4コーナーにかけて下る起伏コース",
        "turf_color": "#2e7d32",
        "dirt_color": "#5d4037",
        "obstacle_color": "#1565c0",
        "has_slope": True,
        "has_obstacle_course": False
    }
}

@dataclass
class RaceInfo:
    race_id: str
    race_name: str
    track_name: str  # 例: 東京, 中山, 阪神, 京都
    surface_type: str  # 芝, ダート, 障害
    distance: int      # 距離 (m)
    track_condition: str  # 良, 稍重, 重, 不良
    weather: str          # 晴, 曇, 雨
    horses: List[HorseEntry]

    def get_track_profile(self) -> Dict[str, Any]:
        return JRA_TRACK_PROFILES.get(self.track_name, JRA_TRACK_PROFILES["東京"])

    def to_dict(self) -> Dict[str, Any]:
        profile = self.get_track_profile()
        return {
            "race_id": self.race_id,
            "race_name": self.race_name,
            "track_name": self.track_name,
            "surface_type": self.surface_type,
            "distance": self.distance,
            "track_condition": self.track_condition,
            "weather": self.weather,
            "track_profile": profile,
            "horses": [h.to_dict() for h in self.horses]
        }
