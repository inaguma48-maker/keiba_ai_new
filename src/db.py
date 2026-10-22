"""
Database module using SQLite for storing and loading race information, imported racecards,
race results feedback, and prediction accuracy tracking.
"""

import sqlite3
import json
import os
from typing import List, Optional, Dict, Any
from src.models import RaceInfo, HorseEntry

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "racing_app.db")

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS races (
            race_id TEXT PRIMARY KEY,
            race_name TEXT NOT NULL,
            track_name TEXT NOT NULL,
            surface_type TEXT NOT NULL,
            distance INTEGER NOT NULL,
            track_condition TEXT NOT NULL,
            weather TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS horses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            race_id TEXT NOT NULL,
            horse_number INTEGER NOT NULL,
            horse_name TEXT NOT NULL,
            jockey_name TEXT NOT NULL,
            trainer_name TEXT NOT NULL,
            age INTEGER NOT NULL,
            weight REAL NOT NULL,
            impost REAL NOT NULL,
            past_speed_rating REAL NOT NULL,
            past_win_rate REAL NOT NULL,
            jockey_win_rate REAL NOT NULL,
            trainer_win_rate REAL NOT NULL,
            track_aptitude REAL NOT NULL,
            odds REAL NOT NULL,
            FOREIGN KEY (race_id) REFERENCES races (race_id) ON DELETE CASCADE
        );
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS race_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            race_id TEXT UNIQUE NOT NULL,
            first_horse_number INTEGER NOT NULL,
            second_horse_number INTEGER NOT NULL,
            third_horse_number INTEGER NOT NULL,
            win_payout REAL NOT NULL,
            place_payout REAL DEFAULT 0.0,
            recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (race_id) REFERENCES races (race_id) ON DELETE CASCADE
        );
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS prediction_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            race_id TEXT NOT NULL,
            predicted_top_horse INTEGER NOT NULL,
            predicted_confidence REAL NOT NULL,
            top_pick_odds REAL NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)

    conn.commit()
    conn.close()

import re

def save_race(race: RaceInfo) -> None:
    init_db()
    conn = get_db_connection()
    cursor = conn.cursor()

    # Clean race_name prefix (e.g. "自動検出: ") for duplicate matching
    clean_title = re.sub(r'^(自動検出:\s*|JRA出馬表レース:\s*|JRA取り込みレース:\s*)', '', race.race_name).strip()

    # Delete existing race entries with matching race_id OR same track_name and clean race_name to prevent duplicate entries
    cursor.execute("""
        SELECT race_id FROM races
        WHERE race_id = ?
           OR (track_name = ? AND REPLACE(REPLACE(REPLACE(race_name, '自動検出: ', ''), 'JRA出馬表レース: ', ''), 'JRA取り込みレース: ', '') = ?)
    """, (race.race_id, race.track_name, clean_title))

    existing_ids = [row["race_id"] for row in cursor.fetchall()]
    for old_id in existing_ids:
        cursor.execute("DELETE FROM horses WHERE race_id = ?", (old_id,))
        cursor.execute("DELETE FROM races WHERE race_id = ?", (old_id,))

    # Also delete existing race entry if overwriting directly
    cursor.execute("DELETE FROM horses WHERE race_id = ?", (race.race_id,))
    cursor.execute("DELETE FROM races WHERE race_id = ?", (race.race_id,))

    cursor.execute("""
        INSERT INTO races (race_id, race_name, track_name, surface_type, distance, track_condition, weather)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (race.race_id, race.race_name, race.track_name, race.surface_type, race.distance, race.track_condition, race.weather))

    for h in race.horses:
        cursor.execute("""
            INSERT INTO horses (
                race_id, horse_number, horse_name, jockey_name, trainer_name, age, weight,
                impost, past_speed_rating, past_win_rate, jockey_win_rate, trainer_win_rate, track_aptitude, odds
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            race.race_id, h.horse_number, h.horse_name, h.jockey_name, h.trainer_name, h.age, h.weight,
            h.impost, h.past_speed_rating, h.past_win_rate, h.jockey_win_rate, h.trainer_win_rate, h.track_aptitude, h.odds
        ))

    conn.commit()
    conn.close()

def get_race_by_id(race_id: str) -> Optional[RaceInfo]:
    init_db()
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM races WHERE race_id = ?", (race_id,))
    race_row = cursor.fetchone()
    if not race_row:
        conn.close()
        return None

    cursor.execute("SELECT * FROM horses WHERE race_id = ? ORDER BY horse_number ASC", (race_id,))
    horse_rows = cursor.fetchall()
    conn.close()

    horses = []
    for hr in horse_rows:
        horses.append(HorseEntry(
            horse_number=hr["horse_number"],
            horse_name=hr["horse_name"],
            jockey_name=hr["jockey_name"],
            trainer_name=hr["trainer_name"],
            age=hr["age"],
            weight=hr["weight"],
            impost=hr["impost"],
            past_speed_rating=hr["past_speed_rating"],
            past_win_rate=hr["past_win_rate"],
            jockey_win_rate=hr["jockey_win_rate"],
            trainer_win_rate=hr["trainer_win_rate"],
            track_aptitude=hr["track_aptitude"],
            odds=hr["odds"]
        ))

    return RaceInfo(
        race_id=race_row["race_id"],
        race_name=race_row["race_name"],
        track_name=race_row["track_name"],
        surface_type=race_row["surface_type"],
        distance=race_row["distance"],
        track_condition=race_row["track_condition"],
        weather=race_row["weather"],
        horses=horses
    )

def list_all_races() -> List[Dict[str, Any]]:
    init_db()
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT r.race_id, r.race_name, r.track_name, r.surface_type, r.distance, r.track_condition, r.weather, r.created_at,
               COUNT(h.id) as horse_count,
               res.first_horse_number, res.win_payout
        FROM races r
        LEFT JOIN horses h ON r.race_id = h.race_id
        LEFT JOIN race_results res ON r.race_id = res.race_id
        GROUP BY r.race_id
        ORDER BY r.created_at DESC
    """)
    rows = cursor.fetchall()
    conn.close()

    seen_keys = set()
    result = []
    for row in rows:
        clean_title = re.sub(r'^(自動検出:\s*|JRA出馬表レース:\s*|JRA取り込みレース:\s*)', '', row["race_name"]).strip()
        dedup_key = f"{row['track_name']}_{clean_title}"
        if dedup_key in seen_keys:
            continue
        seen_keys.add(dedup_key)

        result.append({
            "race_id": row["race_id"],
            "race_name": row["race_name"],
            "track_name": row["track_name"],
            "surface_type": row["surface_type"],
            "distance": row["distance"],
            "track_condition": row["track_condition"],
            "weather": row["weather"],
            "created_at": str(row["created_at"]),
            "horse_count": row["horse_count"],
            "has_result": row["first_horse_number"] is not None,
            "winner_horse_number": row["first_horse_number"],
            "win_payout": row["win_payout"]
        })
    return result

def save_race_result(race_id: str, first: int, second: int, third: int, win_payout: float, place_payout: float = 0.0) -> None:
    init_db()
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("DELETE FROM race_results WHERE race_id = ?", (race_id,))
    cursor.execute("""
        INSERT INTO race_results (race_id, first_horse_number, second_horse_number, third_horse_number, win_payout, place_payout)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (race_id, first, second, third, win_payout, place_payout))

    conn.commit()
    conn.close()

def get_race_result(race_id: str) -> Optional[Dict[str, Any]]:
    init_db()
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM race_results WHERE race_id = ?", (race_id,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        return None
    return dict(row)

def save_prediction_log(race_id: str, top_horse: int, confidence: float, top_odds: float) -> None:
    init_db()
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO prediction_logs (race_id, predicted_top_horse, predicted_confidence, top_pick_odds)
        VALUES (?, ?, ?, ?)
    """, (race_id, top_horse, confidence, top_odds))

    conn.commit()
    conn.close()

def get_all_completed_races() -> List[Dict[str, Any]]:
    init_db()
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT r.race_id, res.first_horse_number, res.second_horse_number, res.third_horse_number, res.win_payout, res.place_payout
        FROM races r
        INNER JOIN race_results res ON r.race_id = res.race_id
    """)
    rows = cursor.fetchall()
    conn.close()

    return [dict(r) for r in rows]
