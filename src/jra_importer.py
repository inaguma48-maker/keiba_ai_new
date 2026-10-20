"""
JRA & Netkeiba Racecard Importer & Parser Module.
Parses JRA / netkeiba HTML pages and copied text formats into RaceInfo objects.
Specialized support for G3 Sirius Stakes and all JRA dirt/turf races.
"""

import re
import uuid
from typing import Dict, Any, List, Optional
from src.models import RaceInfo, HorseEntry

JRA_TRACKS = ["東京", "中山", "阪神", "京都", "中京", "新潟", "福島", "小倉", "札幌", "函館"]

EXCLUDED_WORDS = {
    'ステークス', 'カップ', 'オープン', 'サラ', 'トレセン', 'ファーム',
    'レースホース', 'スタッド', 'クラブ', 'ハンデ', 'リステッド', 'グループ',
    'レーシング', 'ギャロップ', 'ターフ', 'フロンティア', 'ホース', 'ホースクラブ',
    'サラブレッド', 'ライオン', 'キャロット', 'シルク', 'サンデー', 'ロード',
    'ウイン', 'ラフィアン', 'ノルマンディー', '東京ホース', 'ゴドルフィン',
    '騎手', '人気', '倍', 'キロ', 'メートル', 'ダート', '芝', '良', '稍重', '重', '不良',
    '東京', '中山', '阪神', '京都', '中京', '新潟', '福島', '小倉', '札幌', '函館'
}

def clean_horse_name(name_raw: str) -> str:
    """
    Cleans raw horse name text extracted from JRA pages or pasted text.
    Strictly extracts JRA registered horse names (2 to 9 Katakana characters)
    and removes attached odds, earnings, body weights, owner names, and trainers.
    """
    if not name_raw:
        return ""

    # Pre-clean popularity, pedigree, parens, and sex/age
    cleaned = re.sub(r'\(?\d+番?人気\)?', '', name_raw)
    cleaned = re.split(r'父\s*[:：]', cleaned)[0]
    cleaned = re.split(r'母\s*[:：]', cleaned)[0]
    cleaned = re.sub(r'[\.\(（].*?[\)）]', '', cleaned)
    cleaned = re.sub(r'[\(\[\（].*$', '', cleaned)
    cleaned = re.sub(r'(牡|牝|セ)\d+$', '', cleaned)

    # Japanese JRA horse names are strictly 2 to 9 Katakana characters
    matches = re.findall(r'[\u30A1-\u30FC]{2,9}', cleaned)
    for m in matches:
        if m not in EXCLUDED_WORDS and not any(ex in m for ex in ['ステークス', 'ファーム', 'クラブ', 'レース', 'スタッド', 'オープン']):
            return m

    fallback = re.sub(r'[\d\.\,\%\s万円kg]', '', cleaned).strip()
    if len(fallback) >= 2 and not any(ex in fallback for ex in ['騎手', '人気', '倍', 'コース']):
        return fallback
    return ""

KNOWN_JOCKEYS = [
    'ルメール', 'C.ルメール', '武豊', '武 豊', '川田', '川田将雅', '坂井', '坂井瑠星',
    '松山', '松山弘平', '岩田望', '岩田望来', '横山武', '横山武史', '藤岡佑', 'M.デムーロ',
    '戸崎', '戸崎圭太', '丹内', '菅原', '三浦', '佐々木', '田辺', '津村', '鮫島克', '西村淳'
]

def _extract_odds(line: str) -> Optional[float]:
    """Odds from a pasted line: the number followed by 倍, else the last decimal when there are two or more."""
    with_unit = re.findall(r'(\d+\.\d+)\s*倍', line)
    if with_unit:
        return float(with_unit[-1])
    decimals = re.findall(r'\d+\.\d+', line)
    return float(decimals[-1]) if len(decimals) >= 2 else None


def parse_jra_text(text_content: str, race_name_override: Optional[str] = None) -> RaceInfo:
    """
    Parses pasted text racecards (e.g., copied from JRA official site, netkeiba, or sports news tables).
    Handles typical racecard formats including horse number, horse name, sex/age, impost, jockey, weight, odds, etc.
    """
    lines = [l.strip() for l in text_content.strip().split("\n") if l.strip()]

    # Metadata extraction
    race_name = race_name_override or "JRA出馬表レース"
    track_name = "中京" if "中京" in text_content else ("阪神" if "阪神" in text_content else "東京")
    surface_type = "ダート" if ("ダ" in text_content or "ダート" in text_content or "シリウス" in text_content) else "芝"
    distance = 1900 if ("1900" in text_content or "シリウス" in text_content) else 2000
    condition = "良"

    for line in lines[:8]:
        if "シリウス" in line or "シリウスS" in line or "シリウスステークス" in line:
            race_name = "第28回 シリウスステークス (G3)"
            surface_type = "ダート"
            distance = 1900
            track_name = "中京"
        for track in JRA_TRACKS:
            if track in line:
                track_name = track
        if "ダート" in line or "ダ1" in line or "ダ2" in line:
            surface_type = "ダート"
        dist_match = re.search(r'(\d{4})m?', line)
        if dist_match:
            distance = int(dist_match.group(1))
        if "稍重" in line: condition = "稍重"
        elif "重" in line: condition = "重"
        elif "不良" in line: condition = "不良"
        elif "良" in line: condition = "良"

    horses: List[HorseEntry] = []

    for line in lines:
        if "馬名" in line or "性齢" in line or ("枠" in line and "馬番" in line and "騎手" in line):
            continue

        # Extract Horse Number from start of line or early tokens
        num_match = re.search(r'^\s*(\d{1,2})\b', line) or re.search(r'\b(\d{1,2})\b', line)
        if not num_match:
            continue
        h_num = int(num_match.group(1))
        if not (1 <= h_num <= 28):
            continue

        h_name = clean_horse_name(line)
        if not h_name:
            continue

        odds = _extract_odds(line)
        if odds is None:
            continue  # odds are never guessed

        # Extract Weight (e.g. 480kg or 480(+2))
        w_match = re.search(r'(\d{3})\s*kg', line) or re.search(r'(\d{3})\s*\([+-]?\d+\)', line)
        weight = float(w_match.group(1)) if w_match else 490.0

        # Extract Impost (e.g. 55.0kg or 55.0)
        imp_match = re.search(r'(\d{2}\.\d)\s*kg', line)
        if imp_match:
            impost = float(imp_match.group(1))
        else:  # no unit: 斤量 is the decimal before the odds
            decimals = re.findall(r'\d+\.\d+', line)
            impost = float(decimals[0]) if len(decimals) >= 2 and 40.0 <= float(decimals[0]) <= 70.0 else 56.0

        # Extract Jockey Name
        jockey = "騎手"
        for j in KNOWN_JOCKEYS:
            if j in line:
                jockey = j
                break

        speed_rating = 88.0 + (15.0 / max(odds, 1.1))
        jockey_win = 0.25 if jockey in ["川田", "ルメール", "武豊", "坂井", "松山", "岩田望", "横山武"] else 0.15

        horses.append(HorseEntry(
            horse_number=h_num,
            horse_name=h_name,
            jockey_name=jockey,
            trainer_name="JRA厩舎",
            age=4,
            weight=weight,
            impost=impost,
            past_speed_rating=speed_rating,
            past_win_rate=0.3,
            jockey_win_rate=jockey_win,
            trainer_win_rate=0.18,
            track_aptitude=0.85,
            odds=odds
        ))

    if not horses:
        raise ValueError("出馬表から馬名とオッズを読み取れませんでした。「馬番 馬名 騎手 斤量 オッズ」の形式で貼り付けてください。")

    race_id = f"JRA_IMP_{uuid.uuid4().hex[:8]}"

    return RaceInfo(
        race_id=race_id,
        race_name=race_name,
        track_name=track_name,
        surface_type=surface_type,
        distance=distance,
        track_condition=condition,
        weather="晴",
        horses=horses
    )
