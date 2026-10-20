"""
Race replay data from the existing keiba.db (opened read-only): real finish times and last-3F times.

Nothing is invented: a horse whose time cannot be trusted is flagged `estimated` (constant speed) or `dnf`.
"""

import os
import re
from pathlib import Path
from typing import Any, Dict, Optional

from keiba.dataset import connect_ro, surface_norm
from src.course_specs import get_course
from src.jra_site import VENUE_CODES


class ReplayError(Exception):
    pass


def keiba_db_path() -> str:
    return os.environ.get("KEIBA_DB") or str(Path.home() / ".keiba" / "db" / "keiba.db")


def _f(v) -> Optional[float]:
    try:
        return None if v is None else float(v)
    except (TypeError, ValueError):
        return None


RACE_COLS = "race_date, venue, surface, distance_m, track_condition, race_name, category"


def resolve_race(con, race_id: str):
    """(race_id in keiba.db, race row). The id format may differ between sources, so fall back to date + venue + race number."""
    race = con.execute(f"select {RACE_COLS} from races where race_id=?", (race_id,)).fetchone()
    if race:
        return race_id, race
    where = None
    m = re.fullmatch(r"10(\d{2})\d{4}\d{2}\d{2}(\d{2})(\d{4})(\d{2})(\d{2})", race_id)          # keiba.db style (22 digits)
    if m and m.group(1) in VENUE_CODES:
        where = (f"{m.group(3)}-{m.group(4)}-{m.group(5)}", VENUE_CODES[m.group(1)], int(m.group(2)))
    m = re.fullmatch(r"(\d{4})(\d{2})(\d{2})(\d{2})(\d{2})", race_id)                          # older saved ids: YYYYMMDD + venue + race
    if where is None and m and m.group(4) in VENUE_CODES:
        where = (f"{m.group(1)}-{m.group(2)}-{m.group(3)}", VENUE_CODES[m.group(4)], int(m.group(5)))
    if where:
        found = con.execute(f"select race_id, {RACE_COLS} from races where race_date=? and venue=? and race_number=?", where).fetchone()
        if found:
            return found[0], found[1:]
        raise ReplayError(f"このレース（{where[0]} {where[1]}{where[2]}R）は、過去データ(keiba.db)に、まだありません。"
                          "結果が取り込まれるのを待つ必要があります。")
    raise ReplayError("このレースは過去データ(keiba.db)にありません。")


def load_replay(db_path: str, race_id: str, variant: str = "") -> Dict[str, Any]:
    if not Path(db_path).is_file():
        raise ReplayError("過去データ(keiba.db)が見つかりません。環境変数 KEIBA_DB でファイルの場所を指定してください。")
    con = connect_ro(db_path)
    try:
        race_id, race = resolve_race(con, race_id)
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


def typical_times(db_path: str, venue: str, surface: str, distance: int, going: str = "良", min_n: int = 5) -> Optional[Dict[str, Any]]:
    """Median winning time and last-3F of the winners at this venue / surface / distance (flat races)."""
    if not Path(db_path).is_file():
        return None
    kind = {"芝": "turf", "turf": "turf", "ダート": "dirt", "dirt": "dirt"}.get(surface)
    if kind is None:
        return None
    surf_sql = "(r.surface = 'turf' or r.surface like '芝%')" if kind == "turf" else "(r.surface = 'dirt' or r.surface like 'ダ%')"
    con = connect_ro(db_path)
    try:
        base = ("select x.time_seconds, x.last_3f from races r join race_entries e on e.race_id = r.race_id "
                "join race_results x on x.race_entry_id = e.id where r.venue = ? and r.distance_m = ? and x.finish_position = 1 "
                f"and r.category not like '%障害%' and {surf_sql} and x.time_seconds is not null and x.last_3f is not null")
        rows = con.execute(base + " and r.track_condition = ?", (venue, int(distance), going)).fetchall()
        used = going
        if len(rows) < min_n:
            rows, used = con.execute(base, (venue, int(distance))).fetchall(), "全馬場"
    finally:
        con.close()
    pairs = [(float(t), float(l)) for t, l in rows if 12.0 <= distance / float(t) <= 20.0 and 28.0 <= float(l) <= 48.0]
    if len(pairs) < min_n:
        return None
    ts, ls = sorted(p[0] for p in pairs), sorted(p[1] for p in pairs)
    mid = len(pairs) // 2
    med = lambda v: v[mid] if len(v) % 2 else (v[mid - 1] + v[mid]) / 2
    return {"winner_time_s": round(med(ts), 2), "last3f_s": round(med(ls), 2), "n": len(pairs), "going": used,
            "source": f"過去{len(pairs)}レースの1着馬の中央値（{used}）"}
