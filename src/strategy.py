"""
Betting Strategy and Expected Value Calculation Module.
Calculates optimal ticket recommendations for Win (単勝), Place (複勝), Exacta (馬単), and Trio (3連複).
"""

from typing import List, Dict, Any

def calculate_betting_recommendations(predictions: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Generate betting recommendations based on predicted probabilities and EV.
    predictions: sorted list of dicts from HorseRacePredictor.predict_race
    """
    if not predictions:
        return {"win_tickets": [], "place_tickets": [], "exacta_tickets": [], "trio_tickets": [], "summary": "No data"}

    # Sort predictions by win_probability descending for ranking
    sorted_by_prob = sorted(predictions, key=lambda x: x["win_probability"], reverse=True)
    sorted_by_ev = sorted(predictions, key=lambda x: x["win_ev"], reverse=True)

    # 1. Win Tickets (単勝) - Filter by EV > 0.85 or Top 1 prob
    win_tickets = []
    for p in sorted_by_prob:
        ev = p["win_ev"]
        prob = p["win_probability"]
        if ev >= 1.0 or (prob >= 0.25 and ev >= 0.85):
            recommendation_level = "S (大本命・高期待値)" if (prob > 0.3 and ev >= 1.0) else "A (高確率・期待値優良)" if ev >= 0.9 else "B (穴馬・高利回り狙い)"
            win_tickets.append({
                "horse_number": p["horse_number"],
                "horse_name": p["horse_name"],
                "odds": p["odds"],
                "probability": round(prob * 100, 1),
                "ev": p["win_ev"],
                "level": recommendation_level,
                "recommended_stake_percent": round(min(15.0, prob * 30), 1)
            })

    if not win_tickets:
        top_h = sorted_by_prob[0]
        win_tickets.append({
            "horse_number": top_h["horse_number"],
            "horse_name": top_h["horse_name"],
            "odds": top_h["odds"],
            "probability": round(top_h["win_probability"] * 100, 1),
            "ev": top_h["win_ev"],
            "level": "A (軸馬推奨)",
            "recommended_stake_percent": 10.0
        })

    # 2. Place Tickets (複勝) - High place probability
    place_tickets = []
    for p in sorted_by_prob[:4]:
        p_prob = p["place_probability"]
        if p_prob >= 0.35:
            place_tickets.append({
                "horse_number": p["horse_number"],
                "horse_name": p["horse_name"],
                "odds": p["odds"],
                "place_probability": round(p_prob * 100, 1),
                "recommendation": "複勝軸候補" if p_prob >= 0.5 else "ヒモ荒れ注意"
            })

    # 3. Exacta Tickets (馬単: 1着 - 2着)
    exacta_tickets = []
    top_1st = sorted_by_prob[0]
    for second in sorted_by_prob[1:4]:
        comb_prob = top_1st["win_probability"] * (second["win_probability"] * 1.5)  # approximate joint prob
        est_odds = round((top_1st["odds"] * second["odds"] * 0.7), 1)
        est_ev = round(comb_prob * est_odds, 2)
        exacta_tickets.append({
            "first_number": top_1st["horse_number"],
            "first_name": top_1st["horse_name"],
            "second_number": second["horse_number"],
            "second_name": second["horse_name"],
            "combination": f"{top_1st['horse_number']} → {second['horse_number']}",
            "estimated_odds": est_odds,
            "joint_probability": round(comb_prob * 100, 1),
            "ev": est_ev
        })

    # 4. Trio Tickets (3連複: 1軸流し)
    trio_tickets = []
    axis = sorted_by_prob[0]
    partners = sorted_by_prob[1:5]
    for i in range(len(partners)):
        for j in range(i + 1, len(partners)):
            p1, p2 = partners[i], partners[j]
            approx_prob = axis["win_probability"] * p1["place_probability"] * p2["place_probability"]
            est_trio_odds = round((axis["odds"] + p1["odds"] + p2["odds"]) * 2.2, 1)
            trio_tickets.append({
                "axis_number": axis["horse_number"],
                "axis_name": axis["horse_name"],
                "partner1_number": p1["horse_number"],
                "partner1_name": p1["horse_name"],
                "partner2_number": p2["horse_number"],
                "partner2_name": p2["horse_name"],
                "combination": f"{axis['horse_number']} - {p1['horse_number']} - {p2['horse_number']}",
                "estimated_odds": est_trio_odds,
                "joint_probability": round(approx_prob * 100, 1)
            })

    confidence_score = round(min(100.0, sorted_by_prob[0]["win_probability"] * 250), 1)

    return {
        "confidence_score": confidence_score,
        "win_tickets": win_tickets[:3],
        "place_tickets": place_tickets[:3],
        "exacta_tickets": exacta_tickets[:3],
        "trio_tickets": trio_tickets[:3],
        "top_pick": {
            "horse_number": sorted_by_prob[0]["horse_number"],
            "horse_name": sorted_by_prob[0]["horse_name"],
            "win_probability": round(sorted_by_prob[0]["win_probability"] * 100, 1)
        }
    }
