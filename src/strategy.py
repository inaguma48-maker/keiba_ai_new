"""
Betting Strategy and Expected Value Calculation Module.
Calculates optimal ticket recommendations for Win (単勝), Place (複勝), Exacta (馬単), and Trio (3連複)
with Kelly Criterion capital allocation and dark-horse EV maximization to achieve >100% ROI.
"""

from typing import List, Dict, Any

def calculate_betting_recommendations(predictions: List[Dict[str, Any]], volatility_info: Dict[str, Any] = None) -> Dict[str, Any]:
    """
    Generate betting recommendations based on predicted probabilities, EV, and Kelly Criterion.
    predictions: sorted list of dicts from HorseRacePredictor.predict_race
    volatility_info: output from HorseRacePredictor.calculate_race_volatility
    """
    if not predictions:
        return {
            "win_tickets": [], "place_tickets": [], "exacta_tickets": [], "trio_tickets": [],
            "summary": "No data", "volatility_info": volatility_info or {}
        }

    is_high_vol = volatility_info.get("is_high_volatility", False) if volatility_info else False
    vol_score = volatility_info.get("volatility_score", 50) if volatility_info else 50

    # Sort predictions by win_probability and win_ev
    sorted_by_prob = sorted(predictions, key=lambda x: x["win_probability"], reverse=True)
    sorted_by_ev = sorted(predictions, key=lambda x: x["win_ev"], reverse=True)

    # Kelly Criterion calculation helper
    # Fractional Kelly (b*p - q) / b * 0.25 for conservative high-ROI betting
    def compute_kelly_stake(prob: float, odds: float) -> float:
        if odds <= 1.0 or prob <= 0:
            return 0.0
        b = odds - 1.0
        q = 1.0 - prob
        f_star = (b * prob - q) / b
        if f_star <= 0:
            return 0.0
        # Scale to recommended percentage (max 20% per race)
        return round(min(20.0, max(2.0, f_star * 25.0)), 1)

    # 1. Win Tickets (単勝) - Filter by Positive EV (>1.0) or High Kelly Edge
    win_tickets = []
    for p in sorted_by_prob:
        ev = p["win_ev"]
        prob = p["win_probability"]
        odds = p["odds"]
        kelly_stake = compute_kelly_stake(prob, odds)

        if ev >= 1.0 or (prob >= 0.22 and ev >= 0.85):
            if ev >= 1.25 and odds >= 5.0:
                level = "S (高回収率大穴本命・EV " + str(ev) + ")"
            elif ev >= 1.0:
                level = "A (期待値100%超・推奨)"
            else:
                level = "B (軸馬候補・安定勝率)"

            win_tickets.append({
                "horse_number": p["horse_number"],
                "horse_name": p["horse_name"],
                "odds": odds,
                "probability": round(prob * 100, 1),
                "ev": ev,
                "value_tag": p.get("value_tag", "通常"),
                "level": level,
                "recommended_stake_percent": kelly_stake if kelly_stake > 0 else 5.0
            })

    if not win_tickets:
        top_h = sorted_by_prob[0]
        win_tickets.append({
            "horse_number": top_h["horse_number"],
            "horse_name": top_h["horse_name"],
            "odds": top_h["odds"],
            "probability": round(top_h["win_probability"] * 100, 1),
            "ev": top_h["win_ev"],
            "value_tag": top_h.get("value_tag", "軸推奨"),
            "level": "A (安定軸馬推奨)",
            "recommended_stake_percent": 10.0
        })

    # 2. Place Tickets (複勝) - High place probability & dark horse place EV
    place_tickets = []
    for p in sorted_by_prob[:5]:
        p_prob = p["place_probability"]
        # Approximate place odds (roughly odds * 0.3 + 1.1)
        est_place_odds = max(1.1, round(p["odds"] * 0.28 + 1.0, 1))
        place_ev = round(p_prob * est_place_odds, 2)

        if p_prob >= 0.30 or place_ev >= 1.1:
            place_tickets.append({
                "horse_number": p["horse_number"],
                "horse_name": p["horse_name"],
                "odds": p["odds"],
                "est_place_odds": est_place_odds,
                "place_probability": round(p_prob * 100, 1),
                "place_ev": place_ev,
                "recommendation": "高確率軸" if p_prob >= 0.5 else ("高期待値穴複勝" if place_ev >= 1.1 else "ヒモ荒れ注意")
            })

    # 3. Exacta Tickets (馬単: 1着 - 2着)
    # Target high EV pairs when high volatility is detected
    exacta_tickets = []
    top_candidates = sorted_by_prob[:4]
    dark_horses = [p for p in sorted_by_ev if p["odds"] >= 6.0][:3]

    # Combine top candidate with dark horses for high payout
    for first in top_candidates[:2]:
        for second in (dark_horses if is_high_vol else sorted_by_prob[1:5]):
            if first["horse_number"] == second["horse_number"]:
                continue
            comb_prob = first["win_probability"] * (second["place_probability"] * 0.6)
            est_odds = round(first["odds"] * second["odds"] * 0.65, 1)
            est_ev = round(comb_prob * est_odds, 2)

            if est_ev >= 0.85 or len(exacta_tickets) < 3:
                exacta_tickets.append({
                    "first_number": first["horse_number"],
                    "first_name": first["horse_name"],
                    "second_number": second["horse_number"],
                    "second_name": second["horse_name"],
                    "combination": f"{first['horse_number']} → {second['horse_number']}",
                    "estimated_odds": est_odds,
                    "joint_probability": round(comb_prob * 100, 1),
                    "ev": est_ev,
                    "is_high_roi_target": est_ev >= 1.1
                })

    # Sort exacta by EV
    exacta_tickets.sort(key=lambda x: x["ev"], reverse=True)

    # 4. Trio Tickets (3連複: 軸1頭・穴目流し)
    trio_tickets = []
    axis = sorted_by_prob[0]
    partners = sorted_by_prob[1:6]

    for i in range(len(partners)):
        for j in range(i + 1, len(partners)):
            p1, p2 = partners[i], partners[j]
            approx_prob = axis["win_probability"] * p1["place_probability"] * p2["place_probability"] * 0.7
            est_trio_odds = round((axis["odds"] + p1["odds"] + p2["odds"]) * 2.5, 1)
            trio_ev = round(approx_prob * est_trio_odds, 2)

            trio_tickets.append({
                "axis_number": axis["horse_number"],
                "axis_name": axis["horse_name"],
                "partner1_number": p1["horse_number"],
                "partner1_name": p1["horse_name"],
                "partner2_number": p2["horse_number"],
                "partner2_name": p2["horse_name"],
                "combination": f"{axis['horse_number']} - {p1['horse_number']} - {p2['horse_number']}",
                "estimated_odds": est_trio_odds,
                "joint_probability": round(approx_prob * 100, 1),
                "ev": trio_ev,
                "is_high_roi_target": trio_ev >= 1.0 or (p1["odds"] >= 8.0 or p2["odds"] >= 8.0)
            })

    trio_tickets.sort(key=lambda x: x["ev"], reverse=True)

    confidence_score = round(min(100.0, sorted_by_prob[0]["win_probability"] * 250), 1)

    return {
        "confidence_score": confidence_score,
        "volatility_info": volatility_info or {},
        "win_tickets": win_tickets[:4],
        "place_tickets": place_tickets[:4],
        "exacta_tickets": exacta_tickets[:4],
        "trio_tickets": trio_tickets[:4],
        "top_pick": {
            "horse_number": sorted_by_prob[0]["horse_number"],
            "horse_name": sorted_by_prob[0]["horse_name"],
            "win_probability": round(sorted_by_prob[0]["win_probability"] * 100, 1),
            "ev": sorted_by_prob[0]["win_ev"]
        }
    }
