"""
Race replay data from the existing keiba.db (opened read-only): real finish times and last-3F times.

Nothing is invented: a horse whose time cannot be trusted is flagged `estimated` (constant speed) or `dnf`.
"""

import os
from pathlib import Path
from typing import Any, Dict, Optional

from keiba.dataset import connect_ro, surface_norm
from src.course_specs import get_course


class ReplayError(Exception):
    pass


def keiba_db_path() -> str:
    return os.environ.get("KEIBA_DB") or str(Path.home() / ".keiba" / "db" / "keiba.db")


def _f(v) -> Optional[float]:
    try:
        return None if v is None else float(v)
    except (TypeError, ValueError):
        return None


def load_replay(db_path: str, race_id: str, variant: str = "") -> Dict[str, Any]:
    if not Path(db_path).is_file():
        raise ReplayError("過去データ(keiba.db)が見つかりません。環境変数 KEIBA_DB でファイルの場所を指定してください。")
    con = connect_ro(db_path)
    try:
        race = con.execute(
            "select race_date, venue, surface, distance_m, track_condition, race_name, category from races where race_id=?",
            (race_id,)).fetchone()
        if not race:
            raise ReplayError("このレースは過去データ(keiba.db)にありません。")
        rows = con.execute(
            "select e.horse_number, e.frame_number, h.horse_name, x.finish_position, x.time_seconds, x.last_3f, e.popularity "
            "from race_entries e left join race_results x on x.race_entry_id = e.id "
            "left join horses h on h.horse_id = e.horse_id where e.race_id=? order by e.horse_number", (race_id,)).fetchall()
    finally:
        con.close()

    date, venue, surface, distance, going, name, category = race
    surf = surface_norm(surface, category)
    if surf == "obstacle":
        raise ReplayError("障害レースのリプレイには対応していません。")
    hint = variant or ("外" if "外" in str(surface) and "内" not in str(surface) else "")
    spec = get_course(venue, surf, int(distance), hint)
    if spec is None:
        raise ReplayError(f"{venue}の{surface}コースは未対応です。")

    runners = []
    for num, frame, hname, fin, t, l3, pop in rows:
        if fin is None and pop is None:
            continue  # scratched / excluded
        t, l3 = _f(t), _f(l3)
        speed_ok = t is not None and 12.0 <= distance / t <= 20.0
        l3_ok = speed_ok and l3 is not None and 600.0 / 21.0 <= l3 <= 600.0 / 12.0 and (t - l3) > 0
        runners.append({
            "horse_number": int(num), "frame": int(frame) if frame is not None else None,
            "horse_name": hname or f"{num}番", "finish": int(fin) if fin is not None else None,
            "time_s": t if speed_ok else None, "last3f_s": l3 if l3_ok else None,
            "dnf": not speed_ok,
        })
    finishers = [r for r in runners if r["time_s"] is not None]
    if len(finishers) < 2:
        raise ReplayError("このレースには、リプレイに必要なタイムの記録がありません。")
    runners.sort(key=lambda r: (r["finish"] is None, r["finish"] or 99, r["horse_number"]))
    return {
        "race": {"race_id": race_id, "race_date": str(date), "venue": venue, "surface": surf, "distance_m": int(distance),
                 "track_condition": going, "race_name": name},
        "course": spec,
        "runners": runners,
        "source": "keiba.db",
        "notes": ["走行距離は、実際の競走タイムと上がり3Fに合わせています。馬どうしの間隔と走るコースは、タイムから計算した表示です。"],
    }
