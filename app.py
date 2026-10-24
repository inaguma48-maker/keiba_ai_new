"""
Flask app: JRA racecard and odds viewer with market-implied probabilities.

Model predictions are intentionally NOT shown: against real win odds the model
showed no improvement (docs/DESIGN.md; keiba/eval_odds.py report of 2026-10-20).
"""

import os
import sys
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from flask import Flask, jsonify, request, render_template
from typing import Any, Dict, List

from src.models import RaceInfo, HorseEntry
from src.version import code_version
from src.data import get_sample_races
from src.jra_importer import parse_jra_text
from src.jra_site import JraClient, JraSiteError, card_to_race_info, cname_from_url, pick_target_date
from src.course_specs import get_course
from src.replay import ReplayError, keiba_db_path, load_replay, resolve_race, typical_times
from keiba.dataset import connect_ro
from keiba.predict import AbilityError, latest_bundle, stage_probs
from keiba.trends import TrendError, profile_ids, race_trends
from src import horse_profiles
from src.db import init_db, save_race, get_race_by_id, list_all_races, get_horse_profiles

app = Flask(__name__)
APP_DIR = os.path.dirname(os.path.abspath(__file__))


VERSION = code_version(APP_DIR)
JRA_RAW_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "raw", "jra")
NOTICE = ("表示の確率は、オッズから計算した市場の見立て（払戻率分を除き、合計を100%にした値）です。"
          "AIの予測ではありません。")

init_db()

# Pre-populate sample races in DB if empty
sample_races_cache = {r.race_id: r for r in get_sample_races()}
for s_race in sample_races_cache.values():
    if not get_race_by_id(s_race.race_id):
        save_race(s_race)


def market_view(race: RaceInfo) -> List[Dict[str, Any]]:
    """Win probability implied by the odds (normalised to sum to 1), lowest odds first."""
    inv = [1.0 / max(h.odds, 1.0) for h in race.horses]
    total = sum(inv)
    rows = [{
        "horse_number": h.horse_number,
        "horse_name": h.horse_name,
        "jockey_name": h.jockey_name,
        "odds": h.odds,
        "market_probability": round(i / total, 4),
    } for h, i in zip(race.horses, inv)]
    return sorted(rows, key=lambda r: (r["odds"], r["horse_number"]))


def _process_cards(cards):
    """Save every race that has odds; report the rest as skipped."""
    results, skipped = [], []
    for card in cards:
        try:
            race = card_to_race_info(card)
        except JraSiteError as e:
            skipped.append({"race": f"{card.venue}{card.race_number}R {card.race_name}", "reason": str(e)})
            continue
        save_race(race)
        results.append({"race": race.to_dict(), "predictions": market_view(race)})
    return results, skipped


@app.route("/")
def index():
    return render_template("index.html", v=VERSION, folder=APP_DIR)


@app.route("/api/version", methods=["GET"])
def version():
    return jsonify({"version": VERSION, "folder": APP_DIR})


@app.route("/api/races", methods=["GET"])
def list_races():
    try:
        return jsonify({"status": "success", "races": list_all_races()})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/races/<race_id>", methods=["GET"])
def get_race_detail(race_id: str):
    race = get_race_by_id(race_id) or sample_races_cache.get(race_id)
    if not race:
        return jsonify({"status": "error", "message": "Race not found"}), 404
    return jsonify({"status": "success", "race": race.to_dict()})


@app.route("/api/course", methods=["GET"])
def course_info():
    """Official course dimensions (JRA) for the race's venue / surface / distance."""
    spec = get_course(request.args.get("venue", ""), request.args.get("surface", ""),
                      int(request.args.get("distance", 0) or 0), request.args.get("variant", ""))
    if spec is None:
        return jsonify({"status": "error", "message": "このコースの寸法データがありません（障害・未対応のコース）。"}), 404
    return jsonify({"status": "success", "course": spec})


@app.route("/api/replay/<race_id>", methods=["GET"])
def replay(race_id: str):
    """Real finish times / last-3F of a past race, from the local keiba.db."""
    try:
        return jsonify({"status": "success", **load_replay(keiba_db_path(), race_id, request.args.get("variant", ""))})
    except ReplayError as e:
        return jsonify({"status": "error", "message": str(e)}), 404
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/ability", methods=["POST"])
def ability():
    """Win probabilities from the ability model: stage 1 (ability only) or stage 2 (ability x popularity rank)."""
    data = request.get_json() or {}
    horses = data.get("horses") or []
    try:
        try:
            stage = int(data.get("stage", 1))
        except (TypeError, ValueError):
            return jsonify({"status": "error", "message": "層は 1 または 2 を指定してください。"}), 400
        if len(horses) < 2:
            return jsonify({"status": "error", "message": "出走馬が2頭以上必要です。"}), 400
        bundle = latest_bundle()
        db = keiba_db_path()
        con = connect_ro(db)
        try:
            race_id, _ = resolve_race(con, str(data.get("race_id", "")))
        finally:
            con.close()
        probs = stage_probs(db, race_id, horses, stage, bundle)
        return jsonify({"status": "success", "stage": stage, "probs": {str(k): v for k, v in probs.items()},
                        "model": {"trained_at": bundle.get("trained_at"), "train_end": bundle.get("train_end"),
                                  "alpha": bundle.get("alpha"), "beta": bundle.get("beta")}})
    except (AbilityError, ReplayError) as e:
        return jsonify({"status": "error", "message": str(e)}), 404
    except FileNotFoundError:
        return jsonify({"status": "error", "message": "過去データ(keiba.db)が見つかりません。"}), 404
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


def _trend_race(data):
    """(race, keiba.db path, the race's id in keiba.db or None) for the trend endpoints."""
    race = get_race_by_id(str(data.get("race_id", "")))
    if race is None:
        raise TrendError("レースが見つかりません。")
    db = keiba_db_path()
    if not os.path.isfile(db):
        raise TrendError("過去データ(keiba.db)が見つかりません。環境変数 KEIBA_DB でファイルの場所を指定してください。")
    con = connect_ro(db)
    try:
        keiba_id = resolve_race(con, race.race_id)[0]
    except ReplayError:
        keiba_id = None                       # not in keiba.db yet: the app's own data is used for this race
    finally:
        con.close()
    return race, db, keiba_id


@app.route("/api/trends", methods=["POST"])
def trends():
    """Reasons to keep / cut each horse, from the past runnings of the same race (keiba/trends.py)."""
    try:
        race, db, keiba_id = _trend_race(request.get_json(silent=True) or {})
        return jsonify({"status": "success", **race_trends(db, race, keiba_id, get_horse_profiles)})
    except TrendError as e:
        return jsonify({"status": "error", "message": str(e)}), 404
    except Exception as e:
        app.logger.exception("trends failed")
        return jsonify({"status": "error", "message": f"傾向の集計に失敗しました: {e}"}), 500


@app.route("/api/profiles/fetch", methods=["POST"])
def fetch_profiles():
    """Fetch (a batch of) breeders / training centers from the JRA horse pages for the trend of one race."""
    try:
        race, db, keiba_id = _trend_race(request.get_json(silent=True) or {})
        return jsonify({"status": "success", **horse_profiles.fetch_missing(profile_ids(db, race, keiba_id))})
    except TrendError as e:
        return jsonify({"status": "error", "message": str(e)}), 404
    except JraSiteError as e:
        return jsonify({"status": "error", "message": str(e)}), 502
    except Exception as e:
        app.logger.exception("profile fetch failed")
        return jsonify({"status": "error", "message": f"取得に失敗しました: {e}"}), 500


@app.route("/api/baseline", methods=["GET"])
def baseline():
    """Typical winning time / last 3F for the venue, surface and distance (past winners in keiba.db), or null."""
    b = typical_times(keiba_db_path(), request.args.get("venue", ""), request.args.get("surface", ""),
                      int(request.args.get("distance", 0) or 0))
    return jsonify({"status": "success", "baseline": b})


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
            return jsonify({"status": "error", "message": "表示できるレースがありません（オッズ未発表の可能性）。", "skipped": skipped}), 404
        return jsonify({
            "status": "success",
            "message": f"JRA公式サイトから{target[:4]}年{target[4:6]}月{target[6:]}日の{len(results)}レースを取り込みました。",
            "source": "www.jra.go.jp",
            "notice": NOTICE,
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

    try:
        if url:
            page, cname = cname_from_url(url)
            results, skipped = _process_cards(JraClient(raw_dir=JRA_RAW_DIR).fetch_by_cname(page, cname))
            if not results:
                return jsonify({"status": "error", "message": "表示できるレースがありません。", "skipped": skipped}), 404
            first = results[0]
            return jsonify({
                "status": "success",
                "message": f"JRA公式サイトから{len(results)}レースを取り込み、データベースに保存しました。",
                "notice": NOTICE,
                "skipped": skipped,
                "race": first["race"],
                "predictions": first["predictions"],
            })
        if text_content:
            race = parse_jra_text(text_content, race_name_override=data.get("race_name"))
            save_race(race)
            return jsonify({
                "status": "success",
                "message": "出馬表を取り込み、データベースに保存しました。",
                "notice": NOTICE,
                "race": race.to_dict(),
                "predictions": market_view(race),
            })
        return jsonify({"status": "error", "message": "url または text_content が必要です。"}), 400
    except JraSiteError as e:
        return jsonify({"status": "error", "message": str(e)}), 502
    except ValueError as e:
        return jsonify({"status": "error", "message": str(e)}), 400
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/predict", methods=["POST"])
def predict_race():
    """Kept for the UI's reload/recalculate path; returns market-implied probabilities only."""
    data = request.get_json()
    if not data or "horses" not in data:
        return jsonify({"status": "error", "message": "Invalid payload: horses list required"}), 400

    try:
        horses = [HorseEntry(
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
            odds=float(h["odds"]),
        ) for h in data["horses"]]
        if not horses:
            return jsonify({"status": "error", "message": "horses が空です。"}), 400

        race = RaceInfo(
            race_id=data.get("race_id", "CUSTOM_01"),
            race_name=data.get("race_name", "カスタムレース"),
            track_name=data.get("track_name", "東京"),
            surface_type=data.get("surface_type", "芝"),
            distance=int(data.get("distance", 2000)),
            track_condition=data.get("track_condition", "良"),
            weather=data.get("weather", "晴"),
            horses=horses,
            course_variant=str(data.get("course_variant", "")),
        )
        save_race(race)
        return jsonify({"status": "success", "notice": NOTICE, "race": race.to_dict(), "predictions": market_view(race)})
    except KeyError as e:
        return jsonify({"status": "error", "message": f"必須項目がありません: {e}"}), 400
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


if __name__ == "__main__":
    # Under pythonw (background start) there is no console: write output to a log file instead.
    if sys.stdout is None or sys.stderr is None:
        log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
        os.makedirs(log_dir, exist_ok=True)
        sys.stdout = sys.stderr = open(os.path.join(log_dir, "viewer.log"), "a", encoding="utf-8", buffering=1)
    # Local only by default. KEIBA_HOST=0.0.0.0 allows other devices on the same network (e.g. a phone).
    app.run(host=os.environ.get("KEIBA_HOST", "127.0.0.1"), port=int(os.environ.get("KEIBA_PORT", "5000")),
            debug=os.environ.get("KEIBA_DEBUG") == "1")
