"""Tests for the JRA official-site client/parser. No network access."""

import os
import pytest
from src.jra_site import (
    JraSiteError, parse_meetings, parse_racecards, card_to_race_info,
    cname_from_url, pick_target_date, find_all_races_cname,
)

FIX = os.path.join(os.path.dirname(__file__), "fixtures")

def _read(name):
    with open(os.path.join(FIX, name), encoding="utf-8") as f:
        return f.read()

def test_parse_meetings():
    ms = parse_meetings(_read("jra_meetings.html"))
    assert [(m.date, m.venue) for m in ms] == [("20261017", "東京"), ("20261017", "京都"), ("20261018", "東京")]
    assert ms[0].list_cname.startswith("pw01drl10")

def test_pick_target_date():
    ms = parse_meetings(_read("jra_meetings.html"))
    assert pick_target_date(ms, "20261017") == "20261017"
    assert pick_target_date(ms, "20261018") == "20261018"
    assert pick_target_date(ms, "20261019") == "20261018"  # nothing upcoming: latest listed

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
