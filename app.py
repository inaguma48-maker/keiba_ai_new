"""
Flask API Web Application for Horse Racing AI Prediction System.
"""

import os
import sys
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from flask import Flask, jsonify, request, render_template
from typing import Dict, Any, List

from src.models import RaceInfo, HorseEntry
from src.data import get_sample_races, generate_synthetic_historical_data
from src.predictor import HorseRacePredictor
from src.strategy import calculate_betting_recommendations
from src.jra_importer import parse_jra_text
from src.jra_site import (
    JraClient, JraSiteError, card_to_race_info, cname_from_url, pick_target_date,
)
from src.db import init_db, save_race, get_race_by_id, list_all_races

app = Flask(__name__)
predictor = HorseRacePredictor()
JRA_RAW_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "raw", "jra")
PLACEHOLDER_WARNING = (
    "JRAの出馬表には過去成績が含まれないため、スピード指数・過去勝率・騎手/調教師勝率・馬場適性は"
    "仮の固定値です。予測値は参考になりません（docs/DESIGN.md §2 A2）。"
)

def _process_cards(cards):
    """Save and predict every race that has odds; report the rest as skipped."""
    results, skipped = [], []
    for card in cards:
        label = f"{card.venue}{card.race_number}R {card.race_name}"
        try:
            race = card_to_race_info(card)
        except JraSiteError as e:
            skipped.append({"race": label, "reason": str(e)})
            continue
        save_race(race)
        preds = predictor.predict_race(race)
        results.append({
            "race": race.to_dict(),
            "predictions": preds,
            "recommendations": calculate_betting_recommendations(preds),
        })
    return results, skipped

# Initialize Database
init_db()

# Pre-populate sample races in DB if empty
sample_races_cache = {r.race_id: r for r in get_sample_races()}
for s_race in sample_races_cache.values():
    if not get_race_by_id(s_race.race_id):
        save_race(s_race)

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/races", methods=["GET"])
def list_races():
    try:
        db_races = list_all_races()
        return jsonify({"status": "success", "races": db_races})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/api/races/<race_id>", methods=["GET"])
def get_race_detail(race_id: str):
    race = get_race_by_id(race_id)
    if not race:
        race = sample_races_cache.get(race_id)
    if not race:
        return jsonify({"status": "error", "message": "Race not found"}), 404
    return jsonify({"status": "success", "race": race.to_dict()})

@app.route("/api/auto_fetch_jra", methods=["POST"])
def auto_fetch_jra():
    try:
        client = JraClient(raw_dir=JRA_RAW_DIR)
        meetings = client.fetch_meetings()
        target = pick_target_date(meetings)
        cards = []
        for m in (m for m in meetings if m.date == target):
            cards.extend(client.fetch_meeting_racecards(m))
        results, skipped = _process_cards(cards)
        if not results:
            return jsonify({"status": "error", "message": "予測できるレースがありません（オッズ未発表の可能性）。", "skipped": skipped}), 404
        return jsonify({
            "status": "success",
            "message": f"JRA公式サイトから{target[:4]}年{target[4:6]}月{target[6:]}日の{len(results)}レースを取り込みました。",
            "source": "www.jra.go.jp",
            "warning": PLACEHOLDER_WARNING,
            "skipped": skipped,
            "results": results,
        })
    except JraSiteError as e:
        return jsonify({"status": "error", "message": str(e)}), 502
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/api/import_jra", methods=["POST"])
def import_jra():
    data = request.get_json() or {}
    url = data.get("url")
    text_content = data.get("text_content")
    race_name = data.get("race_name")

    try:
        if url:
            page, cname = cname_from_url(url)
            cards = JraClient(raw_dir=JRA_RAW_DIR).fetch_by_cname(page, cname)
            results, skipped = _process_cards(cards)
            if not results:
                return jsonify({"status": "error", "message": "予測できるレースがありません。", "skipped": skipped}), 404
            first = results[0]
            return jsonify({
                "status": "success",
                "message": f"JRA公式サイトから{len(results)}レースを取り込み、データベースに保存しました。",
                "warning": PLACEHOLDER_WARNING,
                "skipped": skipped,
                "race": first["race"],
                "predictions": first["predictions"],
                "recommendations": first["recommendations"],
            })
        elif text_content:
            race = parse_jra_text(text_content, race_name_override=race_name)
        else:
            return jsonify({"status": "error", "message": "url または text_content が必要です。"}), 400

        # Save to SQLite Database for persistent storage
        save_race(race)

        predictions = predictor.predict_race(race)
        recommendations = calculate_betting_recommendations(predictions)

        return jsonify({
            "status": "success",
            "message": "JRA出馬表を取り込み、データベースに保存しました。",
            "race": race.to_dict(),
            "predictions": predictions,
            "recommendations": recommendations
        })
    except JraSiteError as e:
        return jsonify({"status": "error", "message": str(e)}), 502
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/api/predict", methods=["POST"])
def predict_race():
    data = request.get_json()
    if not data or "horses" not in data:
        return jsonify({"status": "error", "message": "Invalid payload: horses list required"}), 400

    try:
        horses = []
        for h in data["horses"]:
            horses.append(HorseEntry(
                horse_number=int(h["horse_number"]),
                horse_name=str(h["horse_name"]),
                jockey_name=str(h.get("jockey_name", "未定")),
                trainer_name=str(h.get("trainer_name", "未定")),
                age=int(h.get("age", 4)),
                weight=float(h.get("weight", 480)),
                impost=float(h.get("impost", 57.0)),
                past_speed_rating=float(h.get("past_speed_rating", 75.0)),
                past_win_rate=float(h.get("past_win_rate", 0.2)),
                jockey_win_rate=float(h.get("jockey_win_rate", 0.15)),
                trainer_win_rate=float(h.get("trainer_win_rate", 0.15)),
                track_aptitude=float(h.get("track_aptitude", 0.8)),
                odds=float(h.get("odds", 5.0))
            ))

        race = RaceInfo(
            race_id=data.get("race_id", "CUSTOM_01"),
            race_name=data.get("race_name", "カスタム予想レース"),
            track_name=data.get("track_name", "東京"),
            surface_type=data.get("surface_type", "芝"),
            distance=int(data.get("distance", 2000)),
            track_condition=data.get("track_condition", "良"),
            weather=data.get("weather", "晴"),
            horses=horses
        )

        # Save to SQLite DB
        save_race(race)

        predictions = predictor.predict_race(race)
        recommendations = calculate_betting_recommendations(predictions)

        return jsonify({
            "status": "success",
            "race": race.to_dict(),
            "predictions": predictions,
            "recommendations": recommendations
        })

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/api/train", methods=["POST"])
def retrain_model():
    try:
        synth_df = generate_synthetic_historical_data(num_races=300)
        predictor.train(synth_df)
        return jsonify({"status": "success", "message": f"AI Precision Model retrained successfully on {len(synth_df)} data points."})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
