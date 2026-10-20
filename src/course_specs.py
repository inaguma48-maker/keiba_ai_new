"""
JRA course dimensions (Aコース = innermost rail position).

Source: https://www.jra.go.jp/facilities/race/<venue>/course/ (fetched 2026-10-20). Every number below is checked
against those pages by tools/verify_course_specs.py. The shape drawn from these is a simplified "stadium"
(two straights + two semicircles) scaled to the official lap length and home-stretch length.
"""

from typing import Any, Dict, Optional

SOURCE_URL = "https://www.jra.go.jp/facilities/race/{slug}/course/"
SLUGS = {"札幌": "sapporo", "函館": "hakodate", "福島": "fukushima", "新潟": "niigata", "東京": "tokyo",
         "中山": "nakayama", "中京": "chukyo", "京都": "kyoto", "阪神": "hanshin", "小倉": "kokura"}
LEFT_HANDED = {"東京", "中京", "新潟"}


def _c(loop, straight, wmin, wmax, drop):
    return {"loop_m": loop, "straight_m": straight, "width_min_m": wmin, "width_max_m": wmax, "drop_m": drop}


# turf: {variant: spec}; variant "" = single layout, "内"/"外" = inner/outer loop, "直" = straight course
COURSES: Dict[str, Dict[str, Dict[str, Dict[str, Any]]]] = {
    "札幌": {"turf": {"": _c(1640.9, 266.1, 25, 27, 0.7)}, "dirt": {"": _c(1487, 264.3, 20, 20, 0.9)}},
    "函館": {"turf": {"": _c(1626.6, 262.1, 29, 29, 3.5)}, "dirt": {"": _c(1475.8, 260.3, 20, 20, 3.5)}},
    "福島": {"turf": {"": _c(1600, 292.0, 25, 27, 1.9)}, "dirt": {"": _c(1444.6, 295.7, 20, 25, 2.1)}},
    "新潟": {"turf": {"内": _c(1623, 358.7, 25, 25, 0.8), "外": _c(2223, 658.7, 25, 25, 2.2),
                      "直": {"kind": "straight", "straight_m": 1000, "width_min_m": 25, "width_max_m": 25, "drop_m": None}},
             "dirt": {"": _c(1472.5, 353.9, 20, 20, 0.6)}},
    "東京": {"turf": {"": _c(2083.1, 525.9, 31, 41, 2.7)}, "dirt": {"": _c(1899, 501.6, 25, 25, 2.5)}},
    "中山": {"turf": {"内": _c(1667.1, 310, 20, 32, 5.3), "外": _c(1839.7, 310, 24, 32, 5.3)},
             "dirt": {"": _c(1493, 308, 20, 25, 4.5)}},
    "中京": {"turf": {"": _c(1705.9, 412.5, 28, 30, 3.5)}, "dirt": {"": _c(1530, 410.7, 25, 25, 3.4)}},
    "京都": {"turf": {"内": _c(1782.8, 328.4, 27, 38, 3.1), "外": _c(1894.3, 403.7, 24, 38, 4.3)},
             "dirt": {"": _c(1607.6, 329.1, 25, 25, 3.0)}},
    "阪神": {"turf": {"内": _c(1689, 356.5, 24, 28, 1.9), "外": _c(2089, 473.6, 24, 29, 2.4)},
             "dirt": {"": _c(1517.6, 352.7, 22, 25, 1.6)}},
    "小倉": {"turf": {"": _c(1615.1, 293, 30, 30, 3.0)}, "dirt": {"": _c(1445.4, 291.3, 24, 24, 2.9)}},
}

# Start distances that exist only on one of the two loops (from the same JRA pages); other distances are ambiguous.
ONLY_INNER = {"中山": {1800, 2000, 2500, 3600}, "京都": {1100, 1200}, "阪神": {1200, 2000, 2200, 3000},
              "新潟": {1200, 2200, 2400}}
ONLY_OUTER = {"中山": {1200, 1600, 2200, 2600, 4000}, "京都": {1800, 2200, 2400, 3000, 3200},
              "阪神": {1600, 1800, 2400, 2600}, "新潟": {1600, 1800, 3000, 3200}}


def direction_of(venue: str) -> str:
    return "左" if venue in LEFT_HANDED else "右"


def get_course(venue: str, surface: str, distance: int, variant: str = "") -> Optional[Dict[str, Any]]:
    """
    Course spec for a flat race, or None when unsupported. `variant` is '内'/'外'/'直' when known
    (the JRA racecard marks outer/straight; no mark means inner). Otherwise it is inferred from the distance.
    """
    kind = {"芝": "turf", "turf": "turf", "ダート": "dirt", "dirt": "dirt"}.get(surface)
    layouts = COURSES.get(venue, {}).get(kind or "")
    if not layouts:
        return None
    note = ""
    if len(layouts) == 1:
        key = next(iter(layouts))
    elif variant in layouts:
        key = variant
    elif venue == "新潟" and distance == 1000 and "直" in layouts:
        key = "直"
    elif distance in ONLY_INNER.get(venue, ()):
        key = "内"
    elif distance in ONLY_OUTER.get(venue, ()):
        key = "外"
    else:
        key, note = "内", "内回り・外回りが不明のため、内回りで表示しています。"
    spec = dict(layouts[key])
    spec.update({
        "venue": venue, "surface": kind, "variant": key, "distance_m": distance, "direction": direction_of(venue),
        "note": note, "source": SOURCE_URL.format(slug=SLUGS[venue]),
    })
    spec.setdefault("kind", "loop")
    return spec
