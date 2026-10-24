"""
Breeder and training center of horses, taken from the JRA horse pages and kept in the app DB (one fetch per horse).

keiba.db has neither, so they are fetched only when asked for, politely (one page a second), a batch at a time.
"""

import re
import threading
import time
from typing import Dict, Iterable, Optional

from src import db
from src.jra_site import JraClient, JraNotFound, JraSiteError, horse_cname, parse_horse_profile

_LOCK = threading.Lock()


def valid_ids(horse_ids: Iterable) -> list:
    return [h for h in dict.fromkeys(str(x) for x in horse_ids if x) if re.fullmatch(r"\d{11}", h)]


def fetch_missing(horse_ids: Iterable, client: Optional[JraClient] = None, max_count: int = 25,
                  time_budget: float = 30.0) -> Dict[str, int]:
    """Fetch the profiles not cached yet, at most `max_count` (and about `time_budget` seconds) per call."""
    ids = valid_ids(horse_ids)
    have = db.get_horse_profiles(ids)
    todo = [h for h in ids if h not in have]
    if not todo:
        return {"fetched": 0, "remaining": 0, "total": len(ids)}
    if not _LOCK.acquire(blocking=False):
        raise JraSiteError("いま別の取得が動いています。終わってから、もう一度押してください。")
    try:
        client = client or JraClient(raw_dir=None)
        start, done = time.monotonic(), 0
        for hid in todo[:max_count]:
            if done and time.monotonic() - start > time_budget:
                break
            try:
                p = parse_horse_profile(client.post("accessU.html", horse_cname(hid)), hid)
                db.save_horse_profile(hid, "ok", p.horse_name, p.trainer, p.center, p.breeder)
            except JraNotFound:
                db.save_horse_profile(hid, "notfound")
            done += 1
        return {"fetched": done, "remaining": len(todo) - done, "total": len(ids)}
    finally:
        _LOCK.release()
