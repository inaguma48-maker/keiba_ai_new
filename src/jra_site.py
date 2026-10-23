"""
JRA official site (www.jra.go.jp) racecard client and parser.

The site serves its pages through form POSTs (doAction(page, CNAME)); a plain GET
is redirected to an error page. Pages are Shift_JIS (cp932).

Failures raise JraSiteError. Nothing is ever substituted for data that could not
be fetched or parsed.
"""

import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional

from bs4 import BeautifulSoup

from src.course_specs import COURSES
from src.models import HorseEntry, RaceInfo

BASE_URL = "https://www.jra.go.jp"
DB_PATH_PREFIX = "/JRADB/"
USER_AGENT = "keiba_ai_new/0.1 (personal research)"
MEETING_LIST = ("accessD.html", "pw01dli00/F3")  # 出馬表 開催選択

VENUE_CODES = {
    "01": "札幌", "02": "函館", "03": "福島", "04": "新潟", "05": "東京",
    "06": "中山", "07": "中京", "08": "京都", "09": "阪神", "10": "小倉",
}

# JRA racecards carry no past-performance data. These constants fill the
# HorseEntry fields the current model requires; they are NOT observed values.
PLACEHOLDER_FEATURES = {
    "age": 4,
    "weight": 480.0,
    "past_speed_rating": 80.0,
    "past_win_rate": 0.2,
    "jockey_win_rate": 0.15,
    "trainer_win_rate": 0.15,
    "track_aptitude": 0.8,
}


class JraSiteError(Exception):
    pass


@dataclass
class Meeting:
    date: str            # YYYYMMDD
    venue_code: str
    venue: str
    kai: int
    nichi: int
    list_cname: str      # pw01drl10... (race list page)


@dataclass
class RunnerRow:
    waku: Optional[int]
    horse_number: int
    horse_name: str
    horse_id: Optional[str]
    sex_age: str
    horse_weight: Optional[float]
    weight_change: Optional[str]
    impost: Optional[float]
    jockey_name: str
    jockey_id: Optional[str]
    trainer_name: str
    trainer_id: Optional[str]
    odds: Optional[float]
    scratched: bool


@dataclass
class RaceCard:
    race_key: str        # YYYYMMDD + venue(2) + race(2)
    db_race_id: str      # '10' + venue(2) + year(4) + kai(2) + nichi(2) + race(2) + YYYYMMDD (JRA CNAME form, as in keiba.db)
    date: str
    venue: str
    venue_code: str
    race_number: int
    race_name: str
    grade: Optional[str]
    category: str
    race_class: str
    distance: int
    surface: str         # 芝 / ダート / 障害
    direction: str       # 左 / 右 / ""
    variant: str         # 外 / 直 / "" (JRA marks only outer and straight; no mark = inner or the only loop)
    post_time: Optional[str]
    runners: List[RunnerRow] = field(default_factory=list)

    @property
    def active_runners(self) -> List[RunnerRow]:
        return [r for r in self.runners if not r.scratched]

    @property
    def odds_ready(self) -> bool:
        active = self.active_runners
        return bool(active) and all(r.odds is not None for r in active)


def _text(el) -> str:
    return re.sub(r"\s+", " ", el.get_text(" ", strip=True)) if el else ""


def _decode(raw: bytes) -> str:
    for enc in ("cp932", "utf-8"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("cp932", errors="replace")


def extract_actions(html: str) -> List[tuple]:
    """All (page, cname) pairs from doAction('page', 'cname') calls, in order."""
    return re.findall(r"doAction\(\s*'([^']+)'\s*,\s*'([^']+)'\s*\)", html)


def parse_meetings(html: str) -> List[Meeting]:
    """Meetings (date x venue) from the 出馬表 開催選択 page."""
    found: Dict[str, Meeting] = {}
    for _page, cname in extract_actions(html):
        # 'pw01drl' + 2 digits (00 = before the racecard is final, 10 = final; both carry numbers and odds) + venue ...
        m = re.match(r"^pw01drl\d{2}(\d{2})(\d{4})(\d{2})(\d{2})(\d{8})/", cname)
        if not m:
            continue
        code, _year, kai, nichi, date = m.groups()
        if code not in VENUE_CODES:
            raise JraSiteError(f"未知の競馬場コード: {code}")
        found[cname] = Meeting(date, code, VENUE_CODES[code], int(kai), int(nichi), cname)
    return sorted(found.values(), key=lambda x: (x.date, x.venue_code))


def find_all_races_cname(html: str) -> str:
    """CNAME of the 'all races of this meeting' page (pw01des...) from a race list page."""
    for _page, cname in extract_actions(html):
        if cname.startswith("pw01des"):
            return cname
    raise JraSiteError("レース選択ページに出馬表(pw01des)へのリンクが見つかりません。")


def _int_or_none(s: str) -> Optional[int]:
    m = re.search(r"\d+", s or "")
    return int(m.group(0)) if m else None


def _float_or_none(s: str) -> Optional[float]:
    m = re.search(r"\d+(?:\.\d+)?", (s or "").replace(",", ""))
    return float(m.group(0)) if m else None


def _id_from_link(a, prefix: str) -> Optional[str]:
    """Extract the id embedded in a CNAME like 'pw01dud00' + '2024102446' + '/82'."""
    if a is None:
        return None
    src = a.get("href", "") + " " + a.get("onclick", "")
    m = re.search(re.escape(prefix) + r"(\d+)", src)
    return m.group(1) if m else None


def _parse_runner(tr) -> Optional[RunnerRow]:
    num_td = tr.select_one("td.num")
    horse_td = tr.select_one("td.horse")
    if not (num_td and horse_td):
        return None
    odds_text = _text(tr.select_one("td.odds"))
    scratched = any(w in odds_text or w in _text(num_td) for w in ("取消", "除外"))
    num = _int_or_none(_text(num_td))
    name = _text(horse_td)
    if not name or (num is None and not scratched):
        raise JraSiteError(f"出走馬の行を解釈できません: {_text(tr)[:60]}")
    if num is None:
        num = 0  # 取消・除外馬は馬番が付かない
    waku_img = tr.select_one("td.waku img")

    hw_td = tr.select_one("td.h_weight")
    change = hw_td.select_one(".change") if hw_td else None
    return RunnerRow(
        waku=_int_or_none(waku_img.get("alt", "")) if waku_img else None,
        horse_number=num,
        horse_name=name,
        horse_id=_id_from_link(horse_td.find("a"), "pw01dud0"),
        sex_age=_text(tr.select_one("td.age")),
        horse_weight=_float_or_none(_text(hw_td).split("(")[0]) if hw_td else None,
        weight_change=_text(change).strip("()") if change else None,
        impost=_float_or_none(_text(tr.select_one("td.weight"))),
        jockey_name=_text(tr.select_one("td.jockey")),
        jockey_id=_id_from_link(tr.select_one("td.jockey a"), "pw04kmk00"),
        trainer_name=_text(tr.select_one("td.trainer")),
        trainer_id=_id_from_link(tr.select_one("td.trainer a"), "pw05cmk00"),
        odds=None if scratched else _float_or_none(odds_text) if re.fullmatch(r"\d+(?:\.\d+)?", odds_text) else None,
        scratched=scratched,
    )


def parse_racecards(html: str) -> List[RaceCard]:
    """All races (with runners) from a 出走馬一覧 page (pw01des...)."""
    soup = BeautifulSoup(html, "html.parser")
    headers = soup.select("div.race_header")
    tables = soup.select("table")
    if not headers:
        raise JraSiteError("出走馬一覧のレース見出しが見つかりません（ページ構造が変わった可能性があります）。")
    if len(headers) != len(tables):
        raise JraSiteError(f"レース見出し({len(headers)})と出走表({len(tables)})の数が一致しません。")

    cards: List[RaceCard] = []
    for header, table in zip(headers, tables):
        date_cell = _text(header.select_one(".cell.date"))
        dm = re.search(r"(\d{4})年(\d{1,2})月(\d{1,2})日", date_cell)
        vm = re.search(r"(\d+)回(\S+?)(\d+)日", date_cell)
        if not (dm and vm):
            raise JraSiteError(f"開催日・競馬場を解釈できません: {date_cell}")
        date = f"{int(dm.group(1)):04d}{int(dm.group(2)):02d}{int(dm.group(3)):02d}"
        kai, venue, nichi = int(vm.group(1)), vm.group(2), int(vm.group(3))
        venue_code = next((c for c, v in VENUE_CODES.items() if v == venue), None)
        if venue_code is None:
            raise JraSiteError(f"未知の競馬場: {venue}")

        rn_img = header.select_one(".race_number img")
        race_number = _int_or_none(rn_img.get("alt", "")) if rn_img else None
        course = header.select_one(".cell.course")
        dist = _int_or_none(_text(course).replace(",", "").split("メートル")[0].split("：")[-1]) if course else None
        detail = _text(course.select_one(".detail")) if course else ""
        if race_number is None or dist is None:
            raise JraSiteError(f"レース番号・距離を解釈できません: {_text(header)[:60]}")

        surface = "障害" if "障害" in _text(header.select_one(".cell.category")) + _text(header.select_one(".cell.class")) else (
            "ダート" if "ダート" in detail else "芝" if "芝" in detail else "")
        if not surface:
            raise JraSiteError(f"コース種別を解釈できません: {detail}")
        dir_m = re.search(r"[・、]\s*(左|右)", detail)
        tokens = re.split(r"[・\s]+", detail.strip("（） "))
        variant = "直" if "直" in tokens else "外" if "外" in tokens else ""

        name_el = header.select_one(".race_name")
        grade_img = name_el.select_one(".grade_icon img") if name_el else None
        time_m = re.search(r"(\d{1,2})時(\d{2})分", _text(header.select_one(".cell.time")))

        runners = [r for r in (_parse_runner(tr) for tr in table.select("tr")) if r]
        if not runners:
            raise JraSiteError(f"{venue}{race_number}R の出走馬が空です。")

        cards.append(RaceCard(
            race_key=f"{date}{venue_code}{race_number:02d}",
            db_race_id=f"10{venue_code}{date[:4]}{kai:02d}{nichi:02d}{race_number:02d}{date}",
            date=date,
            venue=venue,
            venue_code=venue_code,
            race_number=race_number,
            race_name=_text(name_el.find(string=True, recursive=False)) if name_el and name_el.find(string=True, recursive=False) else _text(name_el),
            grade=grade_img.get("alt") if grade_img else None,
            category=_text(header.select_one(".cell.category")),
            race_class=_text(header.select_one(".cell.class")),
            distance=dist,
            surface=surface,
            direction=dir_m.group(1) if dir_m else "",
            variant=variant,
            post_time=f"{int(time_m.group(1)):02d}:{time_m.group(2)}" if time_m else None,
            runners=runners,
        ))
    return cards


def card_to_race_info(card: RaceCard) -> RaceInfo:
    """
    Convert a RaceCard to the model's RaceInfo. Requires odds for every runner.
    Past-performance features are placeholders (see PLACEHOLDER_FEATURES).
    """
    if not card.odds_ready:
        raise JraSiteError(f"{card.venue}{card.race_number}R はオッズが未発表のため予測できません。")

    name = card.race_name + (f" ({card.grade})" if card.grade else "")
    horses = []
    for r in card.active_runners:
        horses.append(HorseEntry(
            horse_number=r.horse_number,
            horse_name=r.horse_name,
            jockey_name=r.jockey_name or "未定",
            trainer_name=r.trainer_name or "未定",
            age=_int_or_none(r.sex_age) or PLACEHOLDER_FEATURES["age"],
            weight=r.horse_weight if r.horse_weight else PLACEHOLDER_FEATURES["weight"],
            impost=r.impost if r.impost else 57.0,
            past_speed_rating=PLACEHOLDER_FEATURES["past_speed_rating"],
            past_win_rate=PLACEHOLDER_FEATURES["past_win_rate"],
            jockey_win_rate=PLACEHOLDER_FEATURES["jockey_win_rate"],
            trainer_win_rate=PLACEHOLDER_FEATURES["trainer_win_rate"],
            track_aptitude=PLACEHOLDER_FEATURES["track_aptitude"],
            odds=r.odds,
        ))
    inner_outer = "内" in COURSES.get(card.venue, {}).get("turf", {})
    variant = card.variant or ("内" if inner_outer and card.surface == "芝" else "")
    return RaceInfo(
        race_id=card.db_race_id,
        race_name=f"{card.venue}{card.race_number}R {name}",
        track_name=card.venue,
        surface_type=card.surface,
        distance=card.distance,
        track_condition="不明",
        weather="不明",
        horses=horses,
        course_variant=variant,
    )


class JraClient:
    """Polite client: identifies itself, waits between requests, keeps raw HTML."""

    def __init__(self, raw_dir: Optional[str] = None, min_interval: float = 1.0, timeout: float = 20.0):
        self.raw_dir = raw_dir
        self.min_interval = min_interval
        self.timeout = timeout
        self._last = 0.0

    def post(self, page: str, cname: str) -> str:
        wait = self.min_interval - (time.monotonic() - self._last)
        if wait > 0:
            time.sleep(wait)
        url = f"{BASE_URL}{DB_PATH_PREFIX}{page}"
        req = urllib.request.Request(
            url,
            data=urllib.parse.urlencode({"cname": cname}).encode("ascii"),
            headers={"User-Agent": USER_AGENT, "Referer": BASE_URL + "/"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                final_url = resp.geturl()
                raw = resp.read()
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise JraSiteError(f"JRAサイトへの接続に失敗しました: {e}") from e
        finally:
            self._last = time.monotonic()

        if "/error/" in final_url:
            raise JraSiteError(f"JRAサイトがエラーページを返しました: {final_url}")
        html = _decode(raw)
        self._save_raw(page, cname, raw)
        return html

    def _save_raw(self, page: str, cname: str, raw: bytes) -> None:
        if not self.raw_dir:
            return
        try:
            os.makedirs(self.raw_dir, exist_ok=True)
            stamp = datetime.now().strftime("%Y%m%dT%H%M%S")
            safe = re.sub(r"[^0-9A-Za-z]+", "_", f"{page}_{cname}")
            with open(os.path.join(self.raw_dir, f"{stamp}_{safe}.html"), "wb") as f:
                f.write(raw)
        except OSError:
            pass  # raw retention is best-effort; never break a fetch for it

    def fetch_meetings(self) -> List[Meeting]:
        html = self.post(*MEETING_LIST)
        meetings = parse_meetings(html)
        if not meetings:
            found = sum(1 for _p, c in extract_actions(html) if c.startswith("pw01drl"))
            raise JraSiteError("開催情報が見つかりませんでした。" + (
                f"（リンクは{found}件ありましたが、形式を解釈できません。JRAサイトの形式が変わった可能性があります）" if found
                else "（開催のない週か、JRAサイトの形式が変わった可能性があります）"))
        return meetings

    def fetch_meeting_racecards(self, meeting: Meeting) -> List[RaceCard]:
        list_html = self.post("accessD.html", meeting.list_cname)
        all_html = self.post("accessD.html", find_all_races_cname(list_html))
        return parse_racecards(all_html)

    def fetch_by_cname(self, page: str, cname: str) -> List[RaceCard]:
        """Fetch racecards from a JRA racecard page reference (race list or all-races page)."""
        html = self.post(page, cname)
        if cname.startswith("pw01drl"):
            html = self.post("accessD.html", find_all_races_cname(html))
        elif not cname.startswith("pw01des"):
            raise JraSiteError("未対応のJRAページです（出馬表の開催/レース選択ページのURLを指定してください）。")
        return parse_racecards(html)


def cname_from_url(url: str) -> tuple:
    """(page, cname) from a https://www.jra.go.jp/JRADB/accessX.html?CNAME=... URL."""
    u = urllib.parse.urlparse(url)
    if u.hostname != "www.jra.go.jp" or not u.path.startswith(DB_PATH_PREFIX):
        raise JraSiteError("www.jra.go.jp の出馬表URLのみ指定できます。")
    q = urllib.parse.parse_qs(u.query)
    cname = (q.get("CNAME") or q.get("cname") or [""])[0]
    if not cname:
        raise JraSiteError("URLにCNAMEパラメータがありません。")
    return u.path[len(DB_PATH_PREFIX):], cname


def pick_target_date(meetings: List[Meeting], today: Optional[str] = None) -> str:
    """Nearest date on/after today (YYYYMMDD); if none, the latest listed date."""
    today = today or datetime.now().strftime("%Y%m%d")
    dates = sorted({m.date for m in meetings})
    upcoming = [d for d in dates if d >= today]
    return upcoming[0] if upcoming else dates[-1]
