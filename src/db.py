"""
Database module using SQLite for storing and loading race information and imported racecards.
"""

import sqlite3
import json
import os
from typing import List, Optional, Dict, Any
from src.models import RaceInfo, HorseEntry

DB_PATH = os.environ.get("KEIBA_APP_DB") or os.path.join(os.path.dirname(os.path.dirname(__file__)), "racing_app.db")

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

    cols = [r["name"] for r in cursor.execute("PRAGMA table_info(races)")]
    if "course_variant" not in cols:
        cursor.execute("ALTER TABLE races ADD COLUMN course_variant TEXT NOT NULL DEFAULT ''")
    cols = [r["name"] for r in cursor.execute("PRAGMA table_info(horses)")]
    for name, kind in (("horse_id", "TEXT"), ("body_weight", "REAL"), ("body_weight_diff", "INTEGER")):
        if name not in cols:
            cursor.execute(f"ALTER TABLE horses ADD COLUMN {name} {kind}")

    # breeder and training center from the JRA horse pages (keiba.db does not have them)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS horse_profiles (
            horse_id TEXT PRIMARY KEY,
            horse_name TEXT,
            trainer TEXT,
            center TEXT,
            breeder TEXT,
            status TEXT NOT NULL,
            fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)

    conn.commit()
    conn.close()

def save_race(race: RaceInfo) -> None:
    init_db()
    conn = get_db_connection()
    cursor = conn.cursor()

    # Delete existing race entry if overwriting
    cursor.execute("DELETE FROM horses WHERE race_id = ?", (race.race_id,))
    cursor.execute("DELETE FROM races WHERE race_id = ?", (race.race_id,))

    cursor.execute("""
        INSERT INTO races (race_id, race_name, track_name, surface_type, distance, track_condition, weather, course_variant)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (race.race_id, race.race_name, race.track_name, race.surface_type, race.distance, race.track_condition, race.weather,
          race.course_variant))

    for h in race.horses:
        cursor.execute("""
            INSERT INTO horses (
                race_id, horse_number, horse_name, jockey_name, trainer_name, age, weight,
                impost, past_speed_rating, past_win_rate, jockey_win_rate, trainer_win_rate, track_aptitude, odds,
                horse_id, body_weight, body_weight_diff
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            race.race_id, h.horse_number, h.horse_name, h.jockey_name, h.trainer_name, h.age, h.weight,
            h.impost, h.past_speed_rating, h.past_win_rate, h.jockey_win_rate, h.trainer_win_rate, h.track_aptitude, h.odds,
            h.horse_id, h.body_weight, h.body_weight_diff
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
            odds=hr["odds"],
            horse_id=hr["horse_id"],
            body_weight=hr["body_weight"],
            body_weight_diff=hr["body_weight_diff"]
        ))

    return RaceInfo(
        race_id=race_row["race_id"],
        race_name=race_row["race_name"],
        track_name=race_row["track_name"],
        surface_type=race_row["surface_type"],
        distance=race_row["distance"],
        track_condition=race_row["track_condition"],
        weather=race_row["weather"],
        horses=horses,
        course_variant=race_row["course_variant"]
    )

def list_all_races() -> List[Dict[str, Any]]:
    init_db()
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT r.race_id, r.race_name, r.track_name, r.surface_type, r.distance, r.track_condition, r.weather, r.created_at,
               COUNT(h.id) as horse_count
        FROM races r
        LEFT JOIN horses h ON r.race_id = h.race_id
        GROUP BY r.race_id
        ORDER BY r.created_at DESC
    """)
    rows = cursor.fetchall()
    conn.close()

    result = []
    for row in rows:
        result.append({
            "race_id": row["race_id"],
            "race_name": row["race_name"],
            "track_name": row["track_name"],
            "surface_type": row["surface_type"],
            "distance": row["distance"],
            "track_condition": row["track_condition"],
            "weather": row["weather"],
            "created_at": str(row["created_at"]),
            "horse_count": row["horse_count"]
        })
    return result


def get_horse_profiles(horse_ids) -> Dict[str, Dict[str, Any]]:
    """{horse_id: profile row} for the ids already fetched from JRA (also the ones JRA did not have: status 'notfound')."""
    ids = [str(h) for h in dict.fromkeys(horse_ids) if h]
    if not ids:
        return {}
    init_db()
    conn = get_db_connection()
    out = {}
    try:
        for i in range(0, len(ids), 500):
            chunk = ids[i:i + 500]
            for r in conn.execute(f"SELECT * FROM horse_profiles WHERE horse_id IN ({','.join('?' * len(chunk))})", chunk):
                out[r["horse_id"]] = dict(r)
    finally:
        conn.close()
    return out


def save_horse_profile(horse_id: str, status: str, horse_name: str = "", trainer: str = "", center: str = "", breeder: str = "") -> None:
    init_db()
    conn = get_db_connection()
    try:
        conn.execute("INSERT OR REPLACE INTO horse_profiles (horse_id, horse_name, trainer, center, breeder, status) VALUES (?, ?, ?, ?, ?, ?)",
                     (horse_id, horse_name, trainer, center, breeder, status))
        conn.commit()
    finally:
        conn.close()
