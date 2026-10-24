"""Tests for the JRA official-site client/parser. No network access."""

import os
import pytest
from src.jra_site import (
    JraNotFound, JraSiteError, parse_meetings, parse_racecards, card_to_race_info,
    cname_from_url, pick_target_date, find_all_races_cname, cname_check, horse_cname, parse_horse_profile,
)

FIX = os.path.join(os.path.dirname(__file__), "fixtures")

def _read(name):
    with open(os.path.join(FIX, name), encoding="utf-8") as f:
        return f.read()

def test_parse_meetings():
    ms = parse_meetings(_read("jra_meetings.html"))
    assert [(m.date, m.venue) for m in ms] == [("20261017", "東京"), ("20261017", "京都"), ("20261018", "東京"),
                                               ("20261024", "東京"), ("20261024", "京都")]   # incl. the 'pw01drl00' (before final) form
    assert ms[0].list_cname.startswith("pw01drl10")

def test_pick_target_date():
    ms = parse_meetings(_read("jra_meetings.html"))
    assert pick_target_date(ms, "20261017") == "20261017"
    assert pick_target_date(ms, "20261018") == "20261018"
    assert pick_target_date(ms, "20261019") == "20261024"  # nearest upcoming date
    assert pick_target_date(ms, "20261030") == "20261024"  # nothing upcoming: latest listed

def test_parse_racecards():
    cards = parse_racecards(_read("jra_racecards.html"))
    assert len(cards) == 1
    c = cards[0]
    assert (c.race_key, c.venue, c.race_number, c.grade) == ("202610170511", "東京", 11, "GⅡ")
    assert c.db_race_id == "1005202604061120261017"  # '10'+東京05+2026+4回+6日+11R+date
    assert (c.surface, c.direction, c.distance, c.post_time) == ("芝", "左", 1600, "15:45")
    assert len(c.runners) == 3 and len(c.active_runners) == 2
    r = c.runners[0]
    assert (r.horse_number, r.horse_name, r.horse_id, r.jockey_id, r.trainer_id) == (1, "アルファテスト", "02024100001", "1001", "1002")
    assert (r.horse_weight, r.weight_change, r.impost, r.odds) == (464.0, "+10", 57.0, 2.5)
    assert c.runners[2].scratched and c.runners[2].odds is None

def test_card_to_race_info_excludes_scratched():
    race = card_to_race_info(parse_racecards(_read("jra_racecards.html"))[0])
    assert race.race_id == "1005202604061120261017"
    assert [h.horse_number for h in race.horses] == [1, 2]
    assert race.track_name == "東京" and race.distance == 1600
    h = race.horses[0]
    assert (h.horse_id, h.body_weight, h.body_weight_diff) == ("02024100001", 464.0, 10)   # kept for the past-race lookup

def test_missing_odds_is_an_error_not_a_guess():
    card = parse_racecards(_read("jra_racecards.html"))[0]
    card.runners[0].odds = None
    with pytest.raises(JraSiteError):
        card_to_race_info(card)

def test_changed_page_structure_is_an_error():
    with pytest.raises(JraSiteError):
        parse_racecards("<html><body>maintenance</body></html>")
    with pytest.raises(JraSiteError):
        find_all_races_cname("<html></html>")

def test_cname_from_url():
    page, cname = cname_from_url("https://www.jra.go.jp/JRADB/accessD.html?CNAME=pw01drl10052026040620261017/16")
    assert (page, cname) == ("accessD.html", "pw01drl10052026040620261017/16")
    for bad in ("https://example.com/JRADB/accessD.html?CNAME=x", "https://www.jra.go.jp/JRADB/accessD.html"):
        with pytest.raises(JraSiteError):
            cname_from_url(bad)


def test_course_variant_is_read_from_the_racecard():
    html = _read("jra_racecards.html")
    assert parse_racecards(html)[0].variant == ""
    assert parse_racecards(html.replace("（芝・左）", "（芝・右 外）"))[0].variant == "外"
    assert parse_racecards(html.replace("（芝・左）", "（芝・直）"))[0].variant == "直"
    kyoto = html.replace("4回東京6日", "4回京都6日").replace("（芝・左）", "（芝・右）")
    assert card_to_race_info(parse_racecards(kyoto)[0]).course_variant == "内"      # unmarked = inner loop
    kyoto_outer = html.replace("4回東京6日", "4回京都6日").replace("（芝・左）", "（芝・右 外）")
    assert card_to_race_info(parse_racecards(kyoto_outer)[0]).course_variant == "外"
    assert card_to_race_info(parse_racecards(html)[0]).course_variant == ""          # Tokyo has a single loop


def test_no_meetings_error_says_what_was_found():
    from src.jra_site import JraClient
    c = JraClient(min_interval=0)
    c.post = lambda page, cname: "<html><a onclick=\"doAction('/JRADB/accessD.html','pw01drl99xx/00')\">x</a></html>"
    with pytest.raises(JraSiteError, match="解釈できません"):
        c.fetch_meetings()
    c.post = lambda page, cname: "<html></html>"
    with pytest.raises(JraSiteError, match="開催のない週"):
        c.fetch_meetings()


# (CNAME, check value) pairs as linked on real JRA pages (horses, races, results, jockeys, trainers)
REAL_LINKS = [
    ("pw01dde0104202604030120261024", "50"), ("pw01dde0105202604081020261024", "76"), ("pw01dde1004202604020620261018", "DF"),
    ("pw01dde1008202604060220261017", "42"), ("pw01dud002017104238", "0D"), ("pw01dud002022103702", "E0"),
    ("pw01dud002023105578", "0A"), ("pw01dud002024103168", "E4"), ("pw01dud102016104583", "0C"),
    ("pw01sde1004202604020120261018", "12"), ("pw01sde1005202604070120261018", "9B"), ("pw01sde1008202604060120261017", "49"),
    ("pw04kmk000422", "1B"), ("pw04kmk001102", "90"), ("pw04krc015490", "CE"), ("pw05cmk000423", "EA"),
    ("pw05cmk001082", "E1"), ("pw05cmk001177", "7C"),
]


def test_cname_check_matches_real_links():
    assert [cname_check(base) for base, _ in REAL_LINKS] == [c for _, c in REAL_LINKS]
    assert horse_cname("02017104238") == "pw01dud002017104238/0D"
    with pytest.raises(JraSiteError):
        horse_cname("H1_0")
    with pytest.raises(ValueError):
        cname_check("pw01dli00")             # a length whose check value was never verified


def test_parse_horse_profile():
    p = parse_horse_profile(_read("jra_horse.html"), "02024100001")
    assert (p.horse_name, p.trainer, p.center, p.breeder) == ("アルファテスト", "試験 太郎", "栗東", "テスト牧場")
    with pytest.raises(JraNotFound):
        parse_horse_profile("<html><head><title>ＤＢ検索エラー　JRA</title></head><body></body></html>", "02012102000")
    with pytest.raises(JraSiteError):
        parse_horse_profile("<html><head><title>パラメータエラー　JRA</title></head></html>", "02012102000")
    with pytest.raises(JraSiteError):
        parse_horse_profile("<html><head><title>競走馬情報　JRA</title></head><body>改装中</body></html>", "02012102000")
