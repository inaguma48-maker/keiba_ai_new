"""
Check every number in src/course_specs.py against the JRA course pages (needs network access to www.jra.go.jp).

usage: python tools/verify_course_specs.py
"""

import os
import re
import sys
import time
import urllib.request

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from src.course_specs import COURSES, SLUGS, SOURCE_URL  # noqa: E402


def fmt(n) -> str:
    s = f"{n:,}"
    return s[:-2] if s.endswith(".0") else s


def page_text(slug: str) -> str:
    req = urllib.request.Request(SOURCE_URL.format(slug=slug), headers={"User-Agent": "keiba_ai_new/0.1 (personal research)"})
    raw = urllib.request.urlopen(req, timeout=25).read()
    html = raw.decode("cp932", errors="replace")
    return re.sub(r"\s+", "", re.sub(r"<[^>]+>", " ", html))


def main() -> int:
    bad = 0
    for venue, kinds in COURSES.items():
        text = page_text(SLUGS[venue])
        time.sleep(1)
        for kind, layouts in kinds.items():
            for variant, s in layouts.items():
                wanted = [("1周", s.get("loop_m"), "m"), ("直線", s.get("straight_m"), "m")]
                wanted.append(("高低差", s.get("drop_m"), "m"))
                for label, v, unit in wanted:
                    if v is None:
                        continue
                    if (fmt(v) + unit) not in text and (f"{v:,.1f}" + unit) not in text:
                        bad += 1
                        print(f"NOT FOUND  {venue} {kind} {variant or '-'} {label}: {fmt(v)}{unit}")
                lo, hi = s["width_min_m"], s["width_max_m"]
                if f"{fmt(lo)}～{fmt(hi)}m" not in text and f"{fmt(lo)}m" not in text:
                    bad += 1
                    print(f"NOT FOUND  {venue} {kind} {variant or '-'} 幅員: {lo}-{hi}")
    print("OK: all numbers found on the JRA pages." if not bad else f"{bad} value(s) not found.")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
