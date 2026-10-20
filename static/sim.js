/*
 * Race simulation from win probabilities (default: probabilities implied by the odds).
 * A finishing order is drawn from the Plackett-Luce model with the Gumbel trick, so each horse wins with
 * exactly its probability. Times are built around a baseline winning time and last-3F time.
 * This is a random draw, not a forecast of one particular result.
 */
(function (root) {
    "use strict";

    function marketProbs(horses) {
        const inv = horses.map(h => 1 / Math.max(h.odds, 1));
        const sum = inv.reduce((a, b) => a + b, 0);
        return inv.map(v => v / sum);
    }

    function gumbel(rnd) { return -Math.log(-Math.log(Math.min(1 - 1e-12, Math.max(1e-12, rnd())))); }
    function gauss(rnd) { return Math.sqrt(-2 * Math.log(Math.max(1e-12, rnd()))) * Math.cos(2 * Math.PI * rnd()); }

    // rough typical winning time / last 3F when no past data is available (general approximation, flagged as such)
    function fallbackBase(distance, surface) {
        const dirt = surface === "dirt" || surface === "ダート";
        const v = (17.2 - 0.0006 * (distance - 1000)) * (dirt ? 0.98 : 1);
        return { winner_time_s: distance / v, last3f_s: dirt ? 37.0 : 35.0, source: "概算（過去データなし）" };
    }

    /**
     * horses: [{horse_number, horse_name, odds}], base: {winner_time_s, last3f_s}, opts: {probs, rnd}
     * returns runners sorted by finish: {horse_number, horse_name, frame, finish, time_s, last3f_s, dnf, p}
     */
    function simulate(horses, base, opts) {
        opts = opts || {};
        const rnd = opts.rnd || Math.random;
        const p = opts.probs || marketProbs(horses);
        const jitter = 1 + (rnd() - 0.5) * 0.03;
        const scored = horses.map((h, i) => ({ h, p: p[i], s: Math.log(p[i]) + gumbel(rnd) })).sort((a, b) => b.s - a.s);
        const top = scored[0].s, tw = base.winner_time_s * jitter;
        return scored.map((e, i) => {
            const time = tw + 0.28 * (top - e.s);
            const l3 = Math.min(base.last3f_s + 2.5, Math.max(base.last3f_s - 1.5,
                base.last3f_s - 0.35 * gauss(rnd) + 0.05 * i + 0.25 * gauss(rnd)));
            return { horse_number: e.h.horse_number, horse_name: e.h.horse_name, frame: null, finish: i + 1,
                time_s: time, last3f_s: Math.min(l3, time - 30), dnf: false, p: e.p };
        });
    }

    const api = { simulate, marketProbs, fallbackBase };
    if (typeof module !== "undefined" && module.exports) module.exports = api; else root.RaceSim = api;
})(typeof window !== "undefined" ? window : globalThis);
