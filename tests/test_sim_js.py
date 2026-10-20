"""Statistical checks of static/sim.js (needs node; skipped when node is not installed)."""

import json
import os
import shutil
import subprocess

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")

SCRIPT = r"""
const S = require(process.argv[1]);
let seed = 12345; const rnd = () => { seed = (seed * 1664525 + 1013904223) % 4294967296; return seed / 4294967296; };
const horses = [2.0, 4.0, 8.0, 16.0, 32.0, 50.0].map((o, i) => ({ horse_number: i + 1, horse_name: "h" + (i + 1), odds: o }));
const p = S.marketProbs(horses), N = 20000, wins = horses.map(() => 0);
let monotone = true, l3ok = true;
for (let k = 0; k < N; k++) {
  const r = S.simulate(horses, { winner_time_s: 120, last3f_s: 35 }, { rnd });
  wins[r[0].horse_number - 1]++;
  for (let i = 1; i < r.length; i++) if (!(r[i].time_s >= r[i - 1].time_s)) monotone = false;
  r.forEach(x => { if (!(x.time_s - x.last3f_s > 30) || x.last3f_s < 30 || x.last3f_s > 45) l3ok = false; });
}
const fb = S.fallbackBase(2000, "turf");
console.log(JSON.stringify({ p, freq: wins.map(w => w / N), monotone, l3ok, sum: p.reduce((a, b) => a + b, 0), fb }));
"""


def test_simulation_wins_follow_the_probabilities():
    out = subprocess.run(["node", "-e", SCRIPT, os.path.join(ROOT, "static", "sim.js")], capture_output=True, text=True, check=True)
    r = json.loads(out.stdout)
    assert abs(r["sum"] - 1.0) < 1e-9
    for p, f in zip(r["p"], r["freq"]):
        assert abs(p - f) < 0.012, (p, f)          # each horse wins about as often as its probability says
    assert r["monotone"] and r["l3ok"]               # finish order matches times; last 3F stays plausible
    assert 115 < r["fb"]["winner_time_s"] < 128       # rough 2000 m turf time
