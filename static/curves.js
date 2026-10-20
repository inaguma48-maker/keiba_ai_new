/*
 * Pure maths of the replay: distance-vs-time curves from a real finish time / last 3F, and the course geometry
 * (a stadium shape scaled to the official lap and home-stretch length). No DOM access, so it can be tested with node.
 */
(function (root) {
    "use strict";
    const TA = 2.5;   // seconds of the start acceleration

    function hermite(a, b, t) {
        const h = b.t - a.t, u = (t - a.t) / h, u2 = u * u, u3 = u2 * u;
        return (2 * u3 - 3 * u2 + 1) * a.d + (u3 - 2 * u2 + u) * h * a.v + (-2 * u3 + 3 * u2) * b.d + (u3 - u2) * h * b.v;
    }

    function makeCurve(r, D, Tw) {
        if (r.time_s) {
            const T = r.time_s;
            let k;
            if (r.last3f_s && D > 650 && T - r.last3f_s > TA + 1) {
                const t1 = T - r.last3f_s, d1 = D - 600, v2 = 600 / r.last3f_s, v1 = d1 / (t1 - TA / 2);
                k = [{ t: 0, d: 0, v: 0 }, { t: TA, d: v1 * TA / 2, v: v1 }, { t: t1, d: d1, v: (v1 + v2) / 2 }, { t: T, d: D, v: v2 }];
            } else {
                const v = D / (T - TA / 2);
                k = [{ t: 0, d: 0, v: 0 }, { t: TA, d: v * TA / 2, v: v }, { t: T, d: D, v: v }];
            }
            const vEnd = k[k.length - 1].v;
            return t => {
                if (t <= 0) return 0;
                if (t >= T) return D + vEnd * 3 * (1 - Math.exp(-(t - T) / 3));
                for (let i = 0; i < k.length - 1; i++) if (t <= k[i + 1].t) return hermite(k[i], k[i + 1], t);
                return D;
            };
        }
        // did not finish: pulls up at 75% of the distance
        const v = D / (Tw * 1.12), stopAt = D * 0.75;
        return t => {
            if (t <= 0) return 0;
            const tr = Math.min(t, TA), d = v * (tr * tr / (2 * TA)) + (t > TA ? v * (t - TA) : 0);
            if (d < stopAt) return d;
            const tail = (t - (stopAt / v + TA / 2)) ;
            return stopAt + 35 * (1 - Math.exp(-Math.max(0, tail) / 4));
        };
    }

    function geometry(c) {
        if (c.kind === "straight") return { kind: "straight", L: c.straight_m, S: c.straight_m, r: 0, left: true, w: c.width_min_m };
        const r = (c.loop_m - 2 * c.straight_m) / (2 * Math.PI);
        return { kind: "loop", L: c.loop_m, S: c.straight_m, r: r, left: c.direction === "左", w: c.width_min_m };
    }

    // u: metres from the finish line along the running direction; lat: metres outward from the inner rail
    function mapPos(g, u, lat) {
        if (g.kind === "straight") return { x: g.S / 2 + u, y: lat - g.w / 2 };
        const L = g.L, S = g.S, r = g.r, R = r + lat;
        u = ((u % L) + L) % L;
        let x, y;
        if (u < Math.PI * r) { const th = -Math.PI / 2 + u / r; x = S / 2 + R * Math.cos(th); y = R * Math.sin(th); }
        else if (u < Math.PI * r + S) { x = S / 2 - (u - Math.PI * r); y = R; }
        else if (u < 2 * Math.PI * r + S) { const th = Math.PI / 2 + (u - Math.PI * r - S) / r; x = -S / 2 + R * Math.cos(th); y = R * Math.sin(th); }
        else { x = -S / 2 + (u - 2 * Math.PI * r - S); y = -R; }
        return { x: g.left ? x : -x, y: y };
    }


    const api = { hermite, makeCurve, geometry, mapPos, TA };
    if (typeof module !== "undefined" && module.exports) module.exports = api; else root.RaceCurves = api;
})(typeof window !== "undefined" ? window : globalThis);
