"""
Flask API Web Application for Horse Racing AI Prediction System with Self-Growing Feedback Loop.
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
from src.jra_importer import parse_jra_text, fetch_and_parse_jra_url, auto_detect_jra_races
from src.db import init_db, save_race, get_race_by_id, list_all_races, get_race_result
from src.feedback_loop import SelfLearningEngine

app = Flask(__name__)
predictor = HorseRacePredictor()
learning_engine = SelfLearningEngine(predictor)

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

    predictions = predictor.predict_race(race)
    volatility = predictor.calculate_race_volatility(race)
    trend_analysis = predictor.analyze_3rd_place_trends(race)
    recommendations = calculate_betting_recommendations(predictions, volatility)
    result = get_race_result(race.race_id)

    return jsonify({
        "status": "success",
        "race": race.to_dict(),
        "predictions": predictions,
        "volatility": volatility,
        "trend_analysis": trend_analysis,
        "recommendations": recommendations,
        "result": result
    })

@app.route("/api/auto_fetch_jra", methods=["POST"])
def auto_fetch_jra():
    try:
        races = auto_detect_jra_races()
        if not races:
            return jsonify({"status": "error", "message": "JRA最新レースが自動検出できませんでした。"}), 404

        processed_results = []
        for race in races:
            save_race(race)
            preds = predictor.predict_race(race)
            vol = predictor.calculate_race_volatility(race)
            trends = predictor.analyze_3rd_place_trends(race)
            recs = calculate_betting_recommendations(preds, vol)
            processed_results.append({
                "race": race.to_dict(),
                "predictions": preds,
                "volatility": vol,
                "trend_analysis": trends,
                "recommendations": recs
            })

        return jsonify({
            "status": "success",
            "message": f"JRA最新出馬表・オッズを自動検出し{len(races)}件取り込みました。",
            "results": processed_results
        })
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
            race = fetch_and_parse_jra_url(url)
        elif text_content:
            race = parse_jra_text(text_content, race_name_override=race_name)
        else:
            return jsonify({"status": "error", "message": "url または text_content が必要です。"}), 400

        # Save to SQLite Database for persistent storage
        save_race(race)

        predictions = predictor.predict_race(race)
        volatility = predictor.calculate_race_volatility(race)
        trend_analysis = predictor.analyze_3rd_place_trends(race)
        recommendations = calculate_betting_recommendations(predictions, volatility)

        return jsonify({
            "status": "success",
            "message": "JRA出馬表を取り込み、データベースに保存しました。",
            "race": race.to_dict(),
            "predictions": predictions,
            "volatility": volatility,
            "trend_analysis": trend_analysis,
            "recommendations": recommendations
        })
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
        volatility = predictor.calculate_race_volatility(race)
        trend_analysis = predictor.analyze_3rd_place_trends(race)
        recommendations = calculate_betting_recommendations(predictions, volatility)

        return jsonify({
            "status": "success",
            "race": race.to_dict(),
            "predictions": predictions,
            "volatility": volatility,
            "trend_analysis": trend_analysis,
            "recommendations": recommendations
        })

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# API Feedback & Self-Learning Endpoints

@app.route("/api/feedback/record_result", methods=["POST"])
def record_race_result():
    """
    Record actual race results (1st, 2nd, 3rd place, payout) and feed into self-learning loop.
    """
    data = request.get_json() or {}
    race_id = data.get("race_id")
    first = data.get("first_horse_number")
    second = data.get("second_horse_number")
    third = data.get("third_horse_number")
    win_payout = data.get("win_payout")
    place_payout = data.get("place_payout", 0.0)

    if not race_id or first is None or win_payout is None:
        return jsonify({"status": "error", "message": "race_id, first_horse_number, and win_payout are required"}), 400

    try:
        res = learning_engine.record_result_and_learn(
            race_id=str(race_id),
            first_horse_number=int(first),
            second_horse_number=int(second) if second is not None else 0,
            third_horse_number=int(third) if third is not None else 0,
            win_payout=float(win_payout),
            place_payout=float(place_payout)
        )
        return jsonify(res)
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/api/feedback/stats", methods=["GET"])
def get_feedback_stats():
    """
    Get ROI %, hit rate %, and self-learning feedback loop generation.
    """
    try:
        stats = learning_engine.calculate_performance_stats()
        return jsonify({"status": "success", "stats": stats})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/api/feedback/retrain", methods=["POST"])
def force_retrain():
    """
    Trigger manual self-learning retrain cycle with historical and feedback data.
    """
    try:
        res = learning_engine.retrain_from_feedback()
        stats = learning_engine.calculate_performance_stats()
        return jsonify({
            "status": "success",
            "message": "AI自己学習モデルを再トレーニングし、モデルパラメータを更新しました。",
            "retrain_summary": res,
            "performance_stats": stats
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
