"""
Tendencies of the past runnings of the same race (過去の同レースの傾向), as reasons to keep or cut each horse.

The earlier runnings come from keiba.db: a named race by its name, an ordinary race by the same venue, surface,
distance, class and age condition. Over the horses that ran in them, simple conditions on popularity, body weight,
training center, breeder and the previous run are counted as records (1st-2nd-3rd-other). A condition becomes a reason
only if its top-3 rate differs from the average by more than chance (95% Wilson interval) and the older and the newer
half of the runnings agree. No condition is "never": every reason carries its record.
"""

import math
import re
import unicodedata
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

import numpy as np
import pandas as pd

from keiba.dataset import connect_ro, surface_norm

SURF_JA = {"turf": "芝", "dirt": "ダート", "obstacle": "障害"}
JA_SURF = {v: k for k, v in SURF_JA.items()}
MIN_RUNS_NAMED = 3       # past runnings needed for a named race
MIN_RUNS_SAME = 5        # past races needed for an ordinary race
MAX_SAME = 100           # newest races used for an ordinary race
PROFILE_CAP = 300        # past horses whose breeder / training center are fetched from JRA (newest races first)
MIN_KEEP_N, MIN_CUT_N, MIN_VALUE_N = 8, 12, 8

FACTORS = ("人気", "馬体重", "調教場", "生産牧場", "前走の着順", "前走の距離", "前走のレース", "前走の人気")


class TrendError(Exception):
    pass


# ---------- names, classes ----------

_GRADE_MARK = re.compile(r"\((?:J・?)?G(?:III|II|I|[1-3])\)|\(Jpn(?:III|II|I|[1-3])\)|\(L\)|\(OP\)|\(リステッド\)")
_GENERIC = re.compile(r"(?:サラ系)?(?:\d歳(?:以上)?)?(?:新馬|未出走|未勝利|\d勝クラス|\d+万(?:円)?(?:以)?下|オープン)")


def _nfkc(s) -> str:
    return unicodedata.normalize("NFKC", str(s if s is not None else ""))


def norm_name(s) -> str:
    """Race name for matching: NFKC, no spaces, no '第N回', no grade marks ('天皇賞（秋） (GⅠ)' -> '天皇賞(秋)')."""
    t = re.sub(r"\s+", "", _nfkc(s))
    t = re.sub(r"^第\d+回", "", t)
    return _GRADE_MARK.sub("", t)


def is_generic_name(nn: str) -> bool:
    """An ordinary race name made only of age and class words ('3歳以上1勝クラス', '2歳未勝利')."""
    return bool(_GENERIC.fullmatch(nn or ""))


def class_label(grade, race_class, name="") -> str:
    texts = [_nfkc(x) for x in (grade, race_class, name)]
    for t in texts:
        m = re.search(r"G(III|II|I|[1-3])(?![A-Za-z0-9])", t)
        if m:
            return "G" + {"I": "1", "II": "2", "III": "3"}.get(m.group(1), m.group(1))
    for t in (texts[1], texts[2], texts[0]):
        if "新馬" in t:
            return "新馬"
        if "未勝利" in t or "未出走" in t:
            return "未勝利"
        if re.search(r"1勝|500万", t):
            return "1勝クラス"
        if re.search(r"2勝|1000万", t):
            return "2勝クラス"
        if re.search(r"3勝|1600万", t):
            return "3勝クラス"
        if re.search(r"オープン|OP|リステッド|\(L\)", t) or t == "L":
            return "オープン"
    return ""


def age_key(*texts) -> str:
    for t in texts:
        m = re.search(r"[2-4]歳(?:以上)?", _nfkc(t))
        if m:
            return m.group(0)
    return ""


def race_date_of(race_id: str) -> Optional[str]:
    m = (re.fullmatch(r"10\d{2}\d{4}\d{2}\d{2}\d{2}(\d{4})(\d{2})(\d{2})", race_id or "")
         or re.fullmatch(r"(\d{4})(\d{2})(\d{2})\d{2}\d{2}", race_id or ""))
    return f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else None


# ---------- statistics ----------

def wilson(k: int, n: int, z: float = 1.96) -> Tuple[float, float]:
    if n == 0:
        return 0.0, 1.0
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(0.0, c - h), min(1.0, c + h)


def mask(df: pd.DataFrame, col: str, op: str, value) -> np.ndarray:
    s = df[col]
    m = {"eq": lambda: s == value, "le": lambda: s <= value, "ge": lambda: s >= value, "lt": lambda: s < value}[op]()
    return m.fillna(False).to_numpy(bool)


def record(finish: pd.Series, m: np.ndarray) -> str:
    f = finish[m]
    w = [int((f == i).sum()) for i in (1, 2, 3)]
    return f"{w[0]}-{w[1]}-{w[2]}-{int(m.sum()) - sum(w)}"


# ---------- reading keiba.db ----------

def _chunks(seq: List, n: int = 500):
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


RACES_SQL = ("select race_id, race_date, venue, race_number, race_name, grade, category, race_class, surface, distance_m "
             "from races where race_date < ?")


def target(con, race, keiba_race_id: Optional[str]) -> Dict[str, Any]:
    """The race to explain: from keiba.db when it is there (same naming as the past races), else from the app."""
    name_app = re.sub(r"^\S*?\d{1,2}R\s*", "", race.race_name or "")
    row = None
    if keiba_race_id:
        row = con.execute("select race_date, venue, race_name, grade, category, race_class, surface, distance_m "
                          "from races where race_id=?", (keiba_race_id,)).fetchone()
    if row:
        date, venue, name, grade, category, rclass, surface, dist = row
        return {"date": str(date)[:10], "venue": venue, "surface": surface_norm(surface, category), "distance": int(dist),
                "name": name or name_app, "cls": class_label(grade, rclass, name), "age": age_key(category, name)}
    date = race_date_of(race.race_id)
    if not date:
        raise TrendError("レースの日付が分かりません（JRAから取り込んだレースで使えます）。")
    return {"date": date, "venue": race.track_name, "surface": JA_SURF.get(race.surface_type, "other"),
            "distance": int(race.distance), "name": name_app, "cls": class_label("", "", name_app), "age": age_key(name_app)}


def find_history(con, t: Dict[str, Any]) -> Tuple[pd.DataFrame, str, str, str]:
    """(past races, 'named' | 'same', label, note)."""
    races = pd.read_sql_query(RACES_SQL, con, params=(t["date"],))
    races["surf"] = [surface_norm(s, c) for s, c in zip(races["surface"], races["category"])]
    races = races[races["surf"] == t["surface"]].copy()
    races["nn"] = races["race_name"].map(norm_name)
    name, note = norm_name(t["name"]), ""
    if name and not is_generic_name(name):
        same = races[races["nn"] == name]
        if same.empty and len(name) >= 4:
            same = races[races["nn"].str.contains(name, regex=False)]
        if len(same) and same.groupby(same["race_date"].astype(str).str[:4]).size().max() <= 2:
            if len(same) >= MIN_RUNS_NAMED:
                return same.sort_values("race_date"), "named", name, note
            note = f"同名のレースが過去{len(same)}回しかないため、同じ条件の過去レースで集計しました。"
    if not t["cls"]:
        raise TrendError(note or "このレースのクラス（未勝利・1勝クラスなど）が分からないため、同じ条件の過去レースを選べません。")
    races = races[(races["venue"] == t["venue"]) & (pd.to_numeric(races["distance_m"], errors="coerce") == t["distance"])].copy()
    races["cls"] = [class_label(g, c, n) for g, c, n in zip(races["grade"], races["race_class"], races["race_name"])]
    races["age"] = [age_key(c, n) for c, n in zip(races["category"], races["race_name"])]
    m = (races["cls"] == t["cls"]) & (races["age"] == t["age"])
    label = f"{t['venue']} {SURF_JA.get(t['surface'], '')}{t['distance']}m・{t['age']}{t['cls']}"
    return races[m].sort_values("race_date").tail(MAX_SAME), "same", label, note


def load_entries(con, race_ids: Iterable[str]) -> pd.DataFrame:
    """Starters (with a finishing position) of the given races."""
    rows = []
    for c in _chunks(list(race_ids)):
        rows += con.execute("select e.race_id, e.horse_id, e.horse_number, e.body_weight, e.body_weight_diff, e.popularity, "
                            "x.finish_position from race_entries e left join race_results x on x.race_entry_id = e.id "
                            f"where e.race_id in ({','.join('?' * len(c))})", c).fetchall()
    df = pd.DataFrame(rows, columns=["race_id", "horse_id", "horse_number", "bw", "bwd", "pop", "finish"])
    for col in ("bw", "bwd", "pop", "finish"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["horse_id"] = df["horse_id"].astype(object).where(df["horse_id"].notna(), None)
    return df[df["finish"].notna()].reset_index(drop=True)


PREV_COLS = ["prev_date", "prev_name", "prev_grade", "prev_class", "prev_category", "prev_surface", "prev_dist", "prev_pop",
             "prev_finish"]


def previous_runs(con, horse_ids: List[Optional[str]], dates: List[str]) -> pd.DataFrame:
    """Row i: the last run in keiba.db of horse_ids[i] before dates[i] (a scratched entry is not a run)."""
    # one pass over race_entries (it has no index on horse_id): the wanted ids go into a temporary table
    con.execute("create temp table if not exists trend_ids (horse_id text primary key)")
    con.execute("delete from trend_ids")
    con.executemany("insert or ignore into trend_ids values (?)", [(str(x),) for x in horse_ids if x])
    rows = con.execute("select e.horse_id, r.race_date, r.race_name, r.grade, r.race_class, r.category, r.surface, "
                       "r.distance_m, e.popularity, x.finish_position from race_entries e join trend_ids t on t.horse_id = e.horse_id "
                       "join races r on r.race_id = e.race_id left join race_results x on x.race_entry_id = e.id").fetchall()
    runs = pd.DataFrame(rows, columns=["horse_id"] + PREV_COLS)
    for col in ("prev_dist", "prev_pop", "prev_finish"):
        runs[col] = pd.to_numeric(runs[col], errors="coerce")
    runs = runs[runs["prev_finish"].notna() | runs["prev_pop"].notna()]
    runs["t"] = pd.to_datetime(runs["prev_date"].astype(str).str[:10], errors="coerce")
    runs = runs.dropna(subset=["t"]).sort_values("t")

    keys = pd.DataFrame({"horse_id": pd.Series(horse_ids, dtype=object), "_i": np.arange(len(horse_ids)),
                         "t": pd.to_datetime(pd.Series(dates, dtype=object).astype(str).str[:10], errors="coerce")})
    ok = keys["horse_id"].notna() & keys["t"].notna()
    out = pd.DataFrame(index=range(len(horse_ids)), columns=PREV_COLS, dtype=object)
    if ok.any() and len(runs):
        left = keys[ok].copy()
        left["horse_id"] = left["horse_id"].astype(str)        # same dtype on both sides (pandas 2 and 3)
        runs["horse_id"] = runs["horse_id"].astype(str)
        merged = pd.merge_asof(left.sort_values("t"), runs, on="t", by="horse_id", allow_exact_matches=False,
                               direction="backward")
        out.loc[merged["_i"].to_numpy(), PREV_COLS] = merged[PREV_COLS].to_numpy()
    for col in ("prev_dist", "prev_pop", "prev_finish"):
        out[col] = pd.to_numeric(out[col], errors="coerce")
    known = keys["horse_id"].notna().to_numpy()
    out["has_prev"] = pd.Series(np.where(known, out["prev_date"].notna(), None), dtype=object)
    out["prev_nn"] = [norm_name(n) if d is not None and d == d else None for n, d in zip(out["prev_name"], out["prev_date"])]
    out["prev_cls"] = [class_label(g, c, n) or None if d is not None and d == d else None
                       for g, c, n, d in zip(out["prev_grade"], out["prev_class"], out["prev_name"], out["prev_date"])]
    return out


def current_horses(con, race, keiba_race_id: Optional[str], date: str) -> Tuple[pd.DataFrame, str]:
    """Starters of the race to explain, with keiba.db ids / weights when it has them; popularity source text."""
    cur = pd.DataFrame([{"horse_number": int(h.horse_number), "horse_name": h.horse_name, "odds": h.odds,
                         "horse_id": h.horse_id, "bw": h.body_weight, "bwd": h.body_weight_diff} for h in race.horses])
    for col in ("odds", "bw", "bwd"):
        cur[col] = pd.to_numeric(cur[col], errors="coerce")
    finished, db_pop = False, None
    if keiba_race_id:
        rows = con.execute("select e.horse_number, e.horse_id, e.body_weight, e.body_weight_diff, e.popularity, x.finish_position "
                           "from race_entries e left join race_results x on x.race_entry_id = e.id where e.race_id=?",
                           (keiba_race_id,)).fetchall()
        if rows:
            d = pd.DataFrame(rows, columns=["horse_number", "d_id", "d_bw", "d_bwd", "d_pop", "d_fin"])
            for col in ("horse_number", "d_bw", "d_bwd", "d_pop", "d_fin"):
                d[col] = pd.to_numeric(d[col], errors="coerce")
            cur = cur.merge(d, on="horse_number", how="left")
            cur["horse_id"] = cur["d_id"].where(cur["d_id"].notna(), cur["horse_id"])
            cur["bw"] = cur["d_bw"].where(cur["d_bw"].notna(), cur["bw"])
            cur["bwd"] = cur["d_bwd"].where(cur["d_bwd"].notna(), cur["bwd"])
            finished, db_pop = bool(cur["d_fin"].notna().any()), cur["d_pop"]
    cur["horse_id"] = cur["horse_id"].astype(object).where(cur["horse_id"].notna(), None)

    missing = [n for n, i in zip(cur["horse_name"], cur["horse_id"]) if i is None and n]
    if missing:
        found = _ids_by_name(con, missing, date)
        cur["horse_id"] = [i if i is not None else found.get(n) for n, i in zip(cur["horse_name"], cur["horse_id"])]

    if finished and db_pop is not None and db_pop.notna().all():
        cur["pop"], src = db_pop, "確定人気"
    elif cur["odds"].notna().all() and (cur["odds"] > 0).all():
        cur["pop"], src = cur["odds"].rank(method="min"), "現在のオッズ順"
    else:
        cur["pop"], src = np.nan, ""
    return cur, src


def _ids_by_name(con, names: List[str], date: str) -> Dict[str, str]:
    """keiba.db horse ids by exact name; with several horses of one name, the one that ran most recently before `date`."""
    rows = []
    for c in _chunks(list(dict.fromkeys(names))):
        rows += con.execute(f"select horse_id, horse_name from horses where horse_name in ({','.join('?' * len(c))})", c).fetchall()
    by_name: Dict[str, List[str]] = {}
    for hid, name in rows:
        by_name.setdefault(name, []).append(str(hid))
    out = {n: ids[0] for n, ids in by_name.items() if len(ids) == 1}
    for name, ids in by_name.items():
        if len(ids) > 1:
            last = con.execute(f"select e.horse_id, max(r.race_date) from race_entries e join races r on r.race_id = e.race_id "
                               f"where e.horse_id in ({','.join('?' * len(ids))}) and r.race_date < ? group by e.horse_id",
                               ids + [date]).fetchall()
            if last:
                out[name] = str(max(last, key=lambda x: str(x[1]))[0])
    return out


def factor_frame(base: pd.DataFrame, prev: pd.DataFrame, distance: np.ndarray, profiles: Dict[str, dict]) -> pd.DataFrame:
    """Factor columns; `profiles` are the cached JRA horse pages ({horse_id: row}, status 'ok' or 'notfound')."""
    f = base.reset_index(drop=True).copy()
    for col in prev.columns:
        f[col] = prev[col].to_numpy()
    pd_ = f["prev_dist"].to_numpy(float)
    dist = np.asarray(distance, float)
    f["dchg"] = pd.Series(np.where(np.isnan(pd_), None, np.where(dist > pd_, "延長", np.where(dist < pd_, "短縮", "同距離"))),
                          dtype=object)
    prof = [profiles.get(str(h)) or {} if h else {} for h in f["horse_id"]]
    ok = [p.get("status") == "ok" for p in prof]
    f["center"] = pd.Series([p.get("center") or None if o else None for p, o in zip(prof, ok)], dtype=object)
    f["breeder"] = pd.Series([p.get("breeder") or None if o else None for p, o in zip(prof, ok)], dtype=object)
    f["profile_status"] = [p.get("status") for p in prof]
    return f


# ---------- conditions ----------

def candidates(h: pd.DataFrame) -> List[Tuple[str, str, str, str, Any]]:
    """(factor, text, column, op, value). Category values need MIN_VALUE_N past horses."""
    def values(col):
        vc = h[col].dropna().value_counts()
        return [v for v, n in vc.items() if n >= MIN_VALUE_N]

    c = [("人気", "1番人気", "pop", "eq", 1)]
    c += [("人気", f"1〜{k}番人気", "pop", "le", k) for k in (2, 3, 5)]
    c += [("人気", f"{k}番人気以下", "pop", "ge", k) for k in (4, 6, 8, 10, 13)]
    c += [("馬体重", f"馬体重{k}kg未満", "bw", "lt", k) for k in (440, 460, 480)]
    c += [("馬体重", f"馬体重{k}kg以上", "bw", "ge", k) for k in (480, 500, 520)]
    c += [("馬体重", f"馬体重が前走から{k}kg以上減", "bwd", "le", -k) for k in (6, 10)]
    c += [("馬体重", f"馬体重が前走から{k}kg以上増", "bwd", "ge", k) for k in (6, 10)]
    c += [("調教場", f"{v}所属", "center", "eq", v) for v in values("center")]
    c += [("生産牧場", f"生産牧場が{v}", "breeder", "eq", v) for v in values("breeder")]
    c += [("前走の着順", "前走1着", "prev_finish", "eq", 1)]
    c += [("前走の着順", f"前走{k}着以内", "prev_finish", "le", k) for k in (3, 5)]
    c += [("前走の着順", f"前走{k}着以下", "prev_finish", "ge", k) for k in (4, 6, 10)]
    c += [("前走の距離", "今回が距離延長（前走より長い）", "dchg", "eq", "延長"),
          ("前走の距離", "今回が距離短縮（前走より短い）", "dchg", "eq", "短縮"),
          ("前走の距離", "前走と同じ距離", "dchg", "eq", "同距離")]
    c += [("前走の距離", f"前走{int(v)}m", "prev_dist", "eq", v) for v in values("prev_dist")]
    c += [("前走のレース", f"前走{v}", "prev_cls", "eq", v) for v in values("prev_cls")]
    c += [("前走のレース", f"前走{v}", "prev_nn", "eq", v) for v in values("prev_nn") if not is_generic_name(v)]
    c += [("前走のレース", "JRAでの前走なし（デビュー戦・地方/海外から）", "has_prev", "eq", False)]
    c += [("前走の人気", "前走1番人気", "prev_pop", "eq", 1)]
    c += [("前走の人気", f"前走1〜{k}番人気", "prev_pop", "le", k) for k in (3, 5)]
    c += [("前走の人気", f"前走{k}番人気以下", "prev_pop", "ge", k) for k in (4, 6, 10)]
    return c


def select_rules(h: pd.DataFrame, older: np.ndarray) -> Tuple[List[Dict[str, Any]], float]:
    """Conditions whose top-3 rate differs from the average beyond chance, in both the older and the newer half."""
    top3 = (h["finish"] <= 3).to_numpy(bool)
    rate0 = float(top3.mean())
    rules = []
    for factor, text, col, op, value in candidates(h):
        m = mask(h, col, op, value)
        n = int(m.sum())
        if n < MIN_KEEP_N:
            continue
        k = int(top3[m].sum())
        lo, hi = wilson(k, n)
        halves = [(int((m & part).sum()), int((m & part & top3).sum())) for part in (older, ~older)]
        if (k >= 3 and k / n >= 1.8 * rate0 and lo >= rate0
                and all(nh >= 3 and kh / nh >= 1.2 * rate0 for nh, kh in halves)):
            kind = "keep"
        elif (n >= MIN_CUT_N and k / n <= 0.35 * rate0 and hi <= rate0
              and all(nh >= 4 and kh / nh <= 0.6 * rate0 for nh, kh in halves)):
            kind = "cut"
        else:
            continue
        rules.append({"kind": kind, "factor": factor, "text": text, "col": col, "op": op,
                      "value": value.item() if hasattr(value, "item") else value,
                      "n": n, "k": k, "rate": k / n, "record": record(h["finish"], m),
                      "halves": [{"n": nh, "k": kh} for nh, kh in halves]})
    return rules, rate0


def sentence(r: Dict[str, Any], scope: str) -> str:
    pct = f"{r['rate'] * 100:.0f}%"
    if r["kind"] == "keep":
        s = f"「{r['text']}」の馬は、{scope}で{r['n']}頭中{r['k']}頭が3着以内（{r['record']}、{pct}）。"
    elif r["k"] == 0:
        s = f"「{r['text']}」の馬は、{scope}で{r['n']}頭すべて4着以下（{r['record']}）。"
    else:
        s = f"「{r['text']}」の馬は、{scope}で{r['n']}頭中{r['k']}頭しか3着以内に来ていない（{r['record']}、{pct}）。"
    return s + ("※頭数が少ないので参考程度。" if r["n"] < 20 else "")


def _num(v) -> Optional[float]:
    return None if v is None or (isinstance(v, float) and math.isnan(v)) else float(v)


def facts(row: pd.Series, pop_src: str) -> List[str]:
    out = []
    pop = _num(row["pop"])
    out.append(f"人気 {pop:.0f}番（{pop_src}）" if pop is not None else "人気 不明（オッズ未発表）")
    bw, bwd = _num(row["bw"]), _num(row["bwd"])
    out.append(f"馬体重 {bw:.0f}kg" + (f"（{bwd:+.0f}）" if bwd is not None else "") if bw is not None else "馬体重 未発表")
    missing = {"ok": "記載なし", "notfound": "JRAにページなし"}.get(row["profile_status"], "未取得")
    out.append(f"調教場 {row['center']}" if row["center"] else f"調教場 {missing}")
    out.append(f"生産牧場 {row['breeder']}" if row["breeder"] else f"生産牧場 {missing}")
    if row["has_prev"] is None:
        out.append("前走 不明（過去データに見つからない馬）")
    elif not row["has_prev"]:
        out.append("前走 JRAでの出走なし")
    else:
        parts = [row["prev_nn"] or "", f"（{row['prev_cls'] or '?'}・{SURF_JA.get(surface_norm(row['prev_surface'], row['prev_category']), '')}"
                 f"{_num(row['prev_dist']) or 0:.0f}m）"]
        fin, pp = _num(row["prev_finish"]), _num(row["prev_pop"])
        parts.append(f"{fin:.0f}着" if fin is not None else "着順なし")
        if pp is not None:
            parts.append(f"・{pp:.0f}番人気")
        out.append("前走 " + "".join(parts))
    return out


def explain(cur: pd.DataFrame, rules: List[Dict[str, Any]], scope: str, pop_src: str) -> List[Dict[str, Any]]:
    """Per horse: the strongest firing keep / cut condition of each factor, as sentences."""
    fired = [(r, mask(cur, r["col"], r["op"], r["value"])) for r in rules]
    out = []
    for i in range(len(cur)):
        best: Dict[Tuple[str, str], Dict[str, Any]] = {}
        for r, m in fired:
            if not m[i]:
                continue
            key, b = (r["kind"], r["factor"]), best.get((r["kind"], r["factor"]))
            better = (r["rate"] > b["rate"] if r["kind"] == "keep" else r["rate"] < b["rate"]) if b else True
            if better or (b and r["rate"] == b["rate"] and r["n"] > b["n"]):
                best[key] = r
        keep = sorted((r for (kind, _), r in best.items() if kind == "keep"), key=lambda r: -r["rate"])
        cut = sorted((r for (kind, _), r in best.items() if kind == "cut"), key=lambda r: r["rate"])
        verdict = "mixed" if keep and cut else "keep" if keep else "cut" if cut else "none"
        row = cur.iloc[i]
        out.append({"horse_number": int(row["horse_number"]), "horse_name": row["horse_name"], "verdict": verdict,
                    "keep": [sentence(r, scope) for r in keep], "cut": [sentence(r, scope) for r in cut],
                    "facts": facts(row, pop_src)})
    return out


# ---------- one race ----------

def _collect(con, race, keiba_race_id):
    t = target(con, race, keiba_race_id)
    races, mode, label, note = find_history(con, t)
    need = MIN_RUNS_NAMED if mode == "named" else MIN_RUNS_SAME
    if len(races) < need:
        raise TrendError(f"比べられる過去のレースが{len(races)}回しかないため、傾向は出せません"
                         f"（{'同名のレース' if mode == 'named' else '同じ条件のレース'}・{label}）。")
    ent = load_entries(con, races["race_id"].tolist())
    ent = ent.merge(races[["race_id", "race_date", "distance_m"]], on="race_id", how="left")
    cur, pop_src = current_horses(con, race, keiba_race_id, t["date"])
    return t, races, mode, label, note, ent, cur, pop_src


_JRA_ID = re.compile(r"\d{11}")


def _wanted_profiles(races: pd.DataFrame, ent: pd.DataFrame, cur: pd.DataFrame) -> List[str]:
    """This race's horses, then past horses (newest races first, at most PROFILE_CAP) - ids JRA has pages for."""
    order = {rid: i for i, rid in enumerate(races["race_id"].iloc[::-1])}
    past = ent.assign(o=ent["race_id"].map(order)).sort_values("o", kind="stable")["horse_id"].dropna().astype(str).tolist()
    past = [h for h in dict.fromkeys(past) if _JRA_ID.fullmatch(h)][:PROFILE_CAP]
    return list(dict.fromkeys([str(h) for h in cur["horse_id"] if h and _JRA_ID.fullmatch(str(h))] + past))


def profile_ids(db_path: str, race, keiba_race_id: Optional[str]) -> List[str]:
    """Horses whose breeder / training center are fetched for this race (see _wanted_profiles)."""
    con = connect_ro(db_path)
    try:
        _t, races, _m, _l, _n, ent, cur, _p = _collect(con, race, keiba_race_id)
    finally:
        con.close()
    return _wanted_profiles(races, ent, cur)


def race_trends(db_path: str, race, keiba_race_id: Optional[str],
                get_profiles: Optional[Callable[[List[str]], Dict[str, dict]]] = None) -> Dict[str, Any]:
    con = connect_ro(db_path)
    try:
        t, races, mode, label, note, ent, cur, pop_src = _collect(con, race, keiba_race_id)
        if ent.empty:
            raise TrendError("過去のレースの結果（着順）が過去データにありません。")
        prev = previous_runs(con, ent["horse_id"].tolist() + cur["horse_id"].tolist(),
                             ent["race_date"].astype(str).tolist() + [t["date"]] * len(cur))
    finally:
        con.close()
    hp, cp = prev.iloc[:len(ent)].reset_index(drop=True), prev.iloc[len(ent):].reset_index(drop=True)
    ids = list(dict.fromkeys(str(h) for h in ent["horse_id"].tolist() + cur["horse_id"].tolist() if h))
    cached = get_profiles(ids) if get_profiles else {}
    wanted = _wanted_profiles(races, ent, cur)
    done = sum(1 for i in wanted if i in cached)                    # a horse JRA has no page for counts as done
    nopage = sum(1 for i in wanted if cached.get(i, {}).get("status") == "notfound")
    h = factor_frame(ent, hp, ent["distance_m"].to_numpy(float), cached)
    c = factor_frame(cur, cp, np.full(len(cur), float(t["distance"])), cached)

    order = races["race_id"].tolist()
    older = h["race_id"].isin(order[:len(order) // 2]).to_numpy(bool)
    rules, rate0 = select_rules(h, older)
    scope = "過去の同レース" if mode == "named" else "同じ条件の過去レース"
    years = races["race_date"].astype(str).str[:4]

    notes = []
    if not pop_src:
        notes.append("人気: オッズが未発表のため、人気の条件では判定していません。")
    elif pop_src == "現在のオッズ順":
        notes.append("人気: 過去は確定人気、今回は現在のオッズ順の人気で判定しています（締切までに変わります）。")
    if c["bw"].isna().all():
        notes.append("馬体重: まだ発表されていないため、馬体重の条件では判定していません（当日、発表後に読み込み直してください）。")
    if done < len(wanted):
        notes.append(f"調教場・生産牧場: JRAから取得済み {done}/{len(wanted)}頭。未取得の馬は、この2つの条件で判定していません。")
    if nopage:
        notes.append(f"調教場・生産牧場: JRAに競走馬のページが無かった馬が{nopage}頭います（この2つの条件では判定していません）。")
    n_hp = int((h["profile_status"] == "ok").sum())
    if 0 < n_hp < len(h):
        notes.append(f"調教場・生産牧場の条件は、JRAから取得できた過去の{n_hp}頭（全{len(h)}頭中）で集計しています。")
    if c["has_prev"].isna().any():
        notes.append("前走: 過去データ(keiba.db)で見つからない馬は、前走の条件で判定していません。")
    if note:
        notes.append(note)

    return {
        "history": {"mode": mode, "label": label, "scope": scope, "n_races": len(races),
                    "years": f"{years.min()}〜{years.max()}年" if len(years) else "",
                    "n_horses": len(h), "n_top3": int((h["finish"] <= 3).sum()), "rate": rate0},
        "profiles": {"have": done, "need": len(wanted), "notfound": nopage},
        "rules": [{**{k: r[k] for k in ("kind", "factor", "text", "n", "k", "rate", "record")}, "sentence": sentence(r, scope)}
                  for r in sorted(rules, key=lambda r: (r["kind"], -r["rate"] if r["kind"] == "keep" else r["rate"]))],
        "horses": explain(c, rules, scope, pop_src),
        "notes": notes,
    }
