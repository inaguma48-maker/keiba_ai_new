"""
keiba.db-shaped file for the same-race trend tests, with patterns planted on purpose.

Named race 'テスト記念' (G2, 東京 芝1800m), run every October 2016-2025 with 16 horses, plus one upcoming running in 2026:
  - the favourite always finishes in the top 3; horses at 10th favourite or lower never do;
  - every horse ran a prep race 4 weeks before, with the same 16 horses; the prep finish follows the popularity,
    so 'previous run 10th or worse' never finishes in the top 3 either;
  - training center alternates by horse number (no pattern); breeders are set in the app DB by the tests.
Ordinary races '3歳以上1勝クラス' (中山 ダート1200m), 60 runnings 2020-2025 with 14 horses: 9th favourite or lower never
finishes in the top 3.
"""

import sqlite3
from datetime import date, timedelta

import numpy as np

from tests.make_keiba_fixture import SCHEMA

NAMED_TARGET = "10052026040811" + "20261024"   # 22 digits, as in keiba.db
SAME_TARGET = "10062026040805" + "20261024"


def _rid(venue_code: str, d: date, race_no: int, kai: int = 4, nichi: int = 8) -> str:
    return f"10{venue_code}{d.year}{kai:02d}{nichi:02d}{race_no:02d}{d:%Y%m%d}"


class _Writer:
    def __init__(self, con):
        self.con, self.eid = con, 0

    def race(self, rid, d, venue, no, name, grade, category, rclass, surface, dist):
        self.con.execute("insert into races values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                         (rid, d.isoformat(), venue, 4, 8, no, name, grade, category, rclass, None, "別定", surface, dist,
                          "良", "晴", "15:40"))

    def entry(self, rid, hid, num, pop, finish, bw=480, bwd=0):
        self.eid += 1
        self.con.execute("insert into race_entries values (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                         (self.eid, rid, hid, num, 1 + (num - 1) // 2, "牡", 4, 57.0, "J1", "T1", bw, bwd, None, pop))
        self.con.execute("insert into race_results values (?,?,?,?,?,?,?,?)",
                         (self.eid, self.eid, finish, "", None if finish is None else 100.0 + finish, "", "", None))


def build(path, seed=3):
    rng = np.random.default_rng(seed)
    con = sqlite3.connect(path)
    con.executescript(SCHEMA)
    w = _Writer(con)
    meta = {"named_top3_pop1": 0}

    for y in range(2016, 2027):
        d = date(y, 10, 24) if y == 2026 else date(y, 10, 20)
        prep = d - timedelta(days=28)
        rid = NAMED_TARGET if y == 2026 else _rid("05", d, 11)
        prid = _rid("06", prep, 11, kai=3)
        w.race(rid, d, "東京", 11, "テスト記念(G2)", "G2", "3歳以上", "オープン", "芝", 1800)
        w.race(prid, prep, "中山", 11, "ステップ賞" if y % 2 else "オータムS", "G3" if y % 2 else None, "3歳以上",
               "オープン", "芝", 2000 if y % 2 else 1600)
        pops = rng.permutation(16) + 1                      # popularity of horse numbers 1..16
        others = [p for p in range(2, 10)]
        rng.shuffle(others)
        top = [1] + others[:2]                              # favourite + two of the 2nd..9th favourites
        rest = [p for p in range(2, 17) if p not in top]
        rng.shuffle(rest)
        rest.sort(key=lambda p: p >= 10)                    # 10th favourite or lower: always behind the others
        order = top + rest                                  # finishing order by popularity
        for i in range(16):
            num, pop = i + 1, int(pops[i])
            hid = f"0{y:04d}{num:06d}"
            fin = order.index(pop) + 1
            w.entry(prid, hid, num, pop, pop)               # prep: finish == popularity
            w.entry(rid, hid, num, None if y == 2026 else pop, None if y == 2026 else fin,
                    bw=int(rng.integers(440, 530)), bwd=int(rng.integers(-8, 9)))
            con.execute("insert into horses values (?,?,?)", (hid, f"テスト{y}_{num}", "2026-01-01"))
        meta["named_top3_pop1"] += y < 2026

    k = 0
    for y in range(2020, 2027):
        for j in range(10 if y < 2026 else 1):
            d = date(y, 1 + j, 10) if y < 2026 else date(2026, 10, 24)
            rid = SAME_TARGET if y == 2026 else _rid("06", d, 5, kai=1)
            w.race(rid, d, "中山", 5, "3歳以上1勝クラス", None, "3歳以上", "1勝クラス", "ダート", 1200)
            pops = rng.permutation(14) + 1
            fav = list(range(1, 9))
            rng.shuffle(fav)
            order = fav[:3] + sorted(set(range(1, 15)) - set(fav[:3]), key=lambda p: (p >= 9, rng.random()))
            for i in range(14):
                k += 1
                hid = f"1{y:04d}{k:06d}"
                pop = int(pops[i])
                prid = _rid("08", d - timedelta(days=21), 3, kai=2)
                if i == 0:
                    w.race(prid, d - timedelta(days=21), "京都", 3, "3歳以上1勝クラス", None, "3歳以上", "1勝クラス",
                           "ダート", 1400)
                w.entry(prid, hid, i + 1, int(rng.integers(1, 15)), int(rng.integers(1, 15)))
                w.entry(rid, hid, i + 1, None if y == 2026 else pop, None if y == 2026 else order.index(pop) + 1)
                con.execute("insert into horses values (?,?,?)", (hid, f"ジョウケン{k}", "2026-01-01"))
    con.commit()
    con.close()
    return meta
