"""Property tests of static/curves.js (distance curves and course geometry). Needs node; skipped without it."""

import json
import os
import shutil
import subprocess

import pytest

from src import course_specs as cs

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")

SCRIPT = r"""
const C = require(process.argv[1]);
const specs = JSON.parse(process.argv[2]);
let seed = 424242; const rnd = () => { seed = (seed * 1664525 + 1013904223) % 4294967296; return seed / 4294967296; };
const bad = [];
const note = (what, info) => { if (bad.length < 12) bad.push(what + " " + JSON.stringify(info)); };

// ---- distance curves from (time, last 3F)
const dists = [1000, 1200, 1400, 1600, 1800, 2000, 2400, 3000, 3600];
for (let n = 0; n < 1500; n++) {
  const D = dists[Math.floor(rnd() * dists.length)], T = D / (15.6 + rnd() * 1.8), L3 = 33 + rnd() * 4.5;
  const useL3 = rnd() < 0.8, c = C.makeCurve({ time_s: T, last3f_s: useL3 ? L3 : null }, D, T);
  if (c(0) !== 0) note("c(0)", { D, T });
  if (Math.abs(c(T) - D) > 1e-6) note("c(T)!=D", { D, T, got: c(T) });
  if (useL3 && D > 650 && T - L3 > 3.5 && Math.abs(c(T - L3) - (D - 600)) > 1e-6) note("last3f knot", { D, T, L3, got: c(T - L3) });
  let prev = 0, maxV = 0;
  for (let t = 0; t <= T + 12; t += 0.05) {
    const d = c(t);
    if (d < prev - 1e-9) { note("not monotone", { D, T, L3, t }); break; }
    maxV = Math.max(maxV, (d - prev) / 0.05); prev = d;
  }
  if (maxV > 25) note("too fast", { D, T, L3, maxV });
  if (c(T + 12) > D + 60) note("runs on too far", { D, got: c(T + 12) });
}
// a horse that did not finish stops before the line and never runs backwards
for (const D of dists) {
  const c = C.makeCurve({ time_s: null }, D, D / 16.5); let prev = 0;
  for (let t = 0; t <= 400; t += 0.1) { const d = c(t); if (d < prev - 1e-9) note("dnf backwards", { D, t }); prev = d; }
  if (c(400) > 0.75 * D + 45) note("dnf too far", { D, got: c(400) });
}

// ---- course geometry, every official course
for (const s of specs) {
  const g = C.geometry(s), name = s.venue + s.surface + s.variant;
  const P = (u, lat) => C.mapPos(g, u, lat || 0);
  if (g.kind === "straight") { if (Math.abs(P(-1000).x - (-g.S / 2)) > 1e-9 || Math.abs(P(0).x - g.S / 2) > 1e-9) note("straight ends", name); continue; }
  if (!(g.r > 90 && g.r < 230)) note("radius", { name, r: g.r });
  let per = 0, a = P(0);
  for (let u = 0.25; u <= g.L + 1e-9; u += 0.25) { const b = P(u); per += Math.hypot(b.x - a.x, b.y - a.y); a = b; }
  if (Math.abs(per - g.L) / g.L > 0.002) note("perimeter", { name, per, L: g.L });
  const p0 = P(0), pL = P(g.L);
  if (Math.hypot(p0.x - pL.x, p0.y - pL.y) > 1e-6) note("not closed", name);
  const finishX = g.left ? g.S / 2 : -g.S / 2;
  if (Math.abs(p0.x - finishX) > 1e-9) note("finish at the wrong end", { name, x: p0.x });
  for (let k = 0; k < 40; k++) {
    const u = rnd() * g.L, lat = rnd() * 30, q0 = P(u), q1 = P(u, lat), q2 = P(u + 0.5);
    if (Math.abs(Math.hypot(q1.x - q0.x, q1.y - q0.y) - lat) > 1e-6) note("lateral offset", { name, u, lat });
    const step = Math.hypot(q2.x - q0.x, q2.y - q0.y);
    if (step > 0.5 + 1e-9 || step < 0.4999) note("not arc-length", { name, u, step });
  }
  // direction: left-handed courses run counter-clockwise (signed area > 0 for the inner rail path)
  let area = 0, pa = P(0);
  for (let u = 1; u <= g.L; u += 1) { const b = P(u); area += pa.x * b.y - b.x * pa.y; pa = b; }
  if ((area > 0) !== g.left) note("direction", { name, left: g.left, area });
}
console.log(JSON.stringify({ bad }));
"""


def _all_specs():
    out = []
    for venue, kinds in cs.COURSES.items():
        for kind, layouts in kinds.items():
            for variant in layouts:
                dist = 1000 if variant == "直" else 1600
                out.append(cs.get_course(venue, "turf" if kind == "turf" else "dirt", dist, variant))
    return out


def test_curves_and_course_geometry_properties():
    specs = _all_specs()
    assert len(specs) == 25                               # turf 15 (inner/outer at 4 venues, Niigata straight) + dirt 10
    out = subprocess.run(["node", "-e", SCRIPT, os.path.join(ROOT, "static", "curves.js"), json.dumps(specs)],
                         capture_output=True, text=True, check=True)
    assert json.loads(out.stdout)["bad"] == []
