"""
Flask API Web Application for Horse Racing AI Prediction System.
"""

from flask import Flask, jsonify, request, render_template
from typing import Dict, Any

from src.models import RaceInfo, HorseEntry
from src.data import get_sample_races, generate_synthetic_historical_data
from src.predictor import HorseRacePredictor
from src.strategy import calculate_betting_recommendations

app = Flask(__name__)
predictor = HorseRacePredictor()
sample_races_cache = {r.race_id: r for r in get_sample_races()}

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/races", methods=["GET"])
def list_races():
    races_summary = []
    for r_id, r in sample_races_cache.items():
        races_summary.append({
            "race_id": r.race_id,
            "race_name": r.race_name,
            "track_name": r.track_name,
            "surface_type": r.surface_type,
            "distance": r.distance,
            "track_condition": r.track_condition,
            "weather": r.weather,
            "horse_count": len(r.horses)
        })
    return jsonify({"status": "success", "races": races_summary})

@app.route("/api/races/<race_id>", methods=["GET"])
def get_race_detail(race_id: str):
    race = sample_races_cache.get(race_id)
    if not race:
        return jsonify({"status": "error", "message": "Race not found"}), 404
    return jsonify({"status": "success", "race": race.to_dict()})

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
