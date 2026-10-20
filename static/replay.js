/*
 * Race replay: real finish times / last-3F (keiba.db) on the real course dimensions (JRA).
 * Main view = side-scrolling TV camera, mini map = top-down course drawn to scale.
 * The distance each horse has run follows its real time and last-3F; the spacing between horses
 * and the lanes they use are computed from that (the data has no positions).
 */
(function () {
    "use strict";

    const FRAME_COLORS = [["#ffffff", "#222222"], ["#222222", "#ffffff"], ["#e53935", "#ffffff"], ["#1e88e5", "#ffffff"],
        ["#fdd835", "#222222"], ["#43a047", "#ffffff"], ["#fb8c00", "#ffffff"], ["#f48fb1", "#222222"]];
    const COATS = ["#6b3f2a", "#3a2a22", "#a8561f", "#9a9a9a", "#1d1d1d", "#7b4a2e"];
    const LANE_M = 2.0, GAP_M = 4.2, GATE_S = 3.0, TA = 2.5;

    const $ = id => document.getElementById(id);
    const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
    const esc = v => String(v).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
    const fmtTime = s => { const m = Math.floor(s / 60); return `${m}:${(s - m * 60).toFixed(1).padStart(4, "0")}`; };

    let main, mapc, mctx, cctx;
    let S = null;          // current replay state
    const DIM = { W: 960, H: 420, mW: 960, mH: 300, dpr: 1, k: 1 };

    function fit() {
        const dpr = Math.min(2, window.devicePixelRatio || 1), W = Math.round(clamp(main.clientWidth || 960, 300, 1100));
        DIM.dpr = dpr; DIM.W = W; DIM.H = Math.round(W * 0.44); DIM.mW = W; DIM.mH = Math.round(W * 0.31); DIM.k = clamp(W / 960, 0.62, 1);
        main.width = W * dpr; main.height = DIM.H * dpr; main.style.height = DIM.H + "px";
        mapc.width = W * dpr; mapc.height = DIM.mH * dpr; mapc.style.height = DIM.mH + "px";
    }
    let raf = null, lastTs = null;
    let CUR = null;        // { race, course } of the race on screen (for the simulation button)

    // ---------- distance curves (real time + real last 3F) ----------
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

    // ---------- course geometry (simplified stadium scaled to the official lap / straight length) ----------
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

    function uOf(S_, d) { return d - S_.D; } // distance run -> metres from the finish line (negative = before it)

    // ---------- setup ----------
    function silk(r) { return FRAME_COLORS[((r.frame || r.horse_number) - 1 + 8) % 8]; }

    function buildState(course, runners, race, hasReplay) {
        const D = course.distance_m;
        const fin = runners.filter(r => r.time_s);
        const Tw = hasReplay ? Math.min.apply(null, fin.map(r => r.time_s)) : 0;
        const n = runners.length;
        const wmin = course.width_min_m || 20;
        const spacing = Math.min(LANE_M, (wmin - 1) / (n + 1));
        runners.forEach((r, i) => {
            r.curve = hasReplay ? makeCurve(r, D, Tw) : (() => 0);
            r.gate = Math.max(0, (r.horse_number - 1)) * spacing + 0.8;
            r.lat = r.gate; r.latT = r.gate; r.d = 0;
            r.coat = COATS[(r.horse_number * 7) % COATS.length];
        });
        const Tend = hasReplay ? Math.max.apply(null, fin.map(r => r.time_s)) + 7 : 0;
        return { course, g: geometry(course), runners, race, D, Tw, Tend, hasReplay, t: -GATE_S, playing: false, speed: 2,
            camD: 0, camW: 90, said: {}, finished: false, wmin, lanes: Math.max(1, Math.floor((wmin - 1) / LANE_M)) };
    }

    // ---------- simulation step ----------
    function step(dt, snap) {
        const s = S, rs = s.runners;
        rs.forEach(r => { r.d = s.t <= 0 ? 0 : r.curve(s.t); });
        // lane assignment: leaders pick the inside lane first; followers move outward when blocked
        const order = rs.slice().sort((a, b) => b.d - a.d);
        const taken = [];
        order.forEach(r => {
            if (s.t <= 0) { r.latT = r.gate; return; }
            let k = 0;
            while (k < s.lanes - 1 && taken.some(o => o.k === k && Math.abs(o.d - r.d) < GAP_M)) k++;
            taken.push({ k, d: r.d });
            r.latT = 0.9 + k * LANE_M;
        });
        const a = snap ? 1 : 1 - Math.exp(-dt * 1.6);
        rs.forEach(r => { r.lat += (r.latT - r.lat) * a; });
        // camera: the pack (leader .. about the 80th percentile)
        const ds = order.map(r => r.d), lead = ds[0], tail = ds[Math.min(ds.length - 1, Math.floor(ds.length * 0.8))];
        const wide = $("select-cam-mode") && $("select-cam-mode").value === "wide";
        const wT = clamp((lead - tail) * 1.35 + 40, wide ? 140 : 80, wide ? 420 : 260);
        const cT = (lead + tail) / 2 + wT * 0.12;
        const b = snap ? 1 : 1 - Math.exp(-dt * 3);
        s.camD += (cT - s.camD) * b; s.camW += (wT - s.camW) * b;
        s.order = order;
    }

    // ---------- drawing: main side view ----------
    function drawHorse(c, x, y, len, phase, r, isLead) {
        const [silkC, silkT] = silk(r);
        c.save(); c.translate(x, y); c.scale(len, len);
        c.lineCap = "round"; c.lineJoin = "round";
        const coat = r.coat, dark = "rgba(0,0,0,0.55)";
        const leg = (hx, hy, ph, front) => {
            const a1 = Math.sin(ph) * (front ? 0.85 : 0.75), k = Math.max(0, Math.sin(ph + (front ? 1.2 : -0.9))) * 1.15;
            const l1 = 0.2, l2 = 0.2;
            const kx = hx + Math.sin(a1) * l1, ky = hy + Math.cos(a1) * l1;
            const fx = kx + Math.sin(a1 - (front ? -k : k)) * l2, fy = ky + Math.cos(a1 - (front ? -k : k)) * l2;
            c.strokeStyle = coat; c.lineWidth = 0.05; c.beginPath(); c.moveTo(hx, hy); c.lineTo(kx, ky); c.lineTo(fx, fy); c.stroke();
            c.strokeStyle = dark; c.lineWidth = 0.052; c.beginPath(); c.moveTo(fx, fy - 0.03); c.lineTo(fx, fy); c.stroke();
        };
        const bob = Math.sin(phase * 2) * 0.012;
        c.translate(0, bob);
        // far legs, tail, body, near legs, neck/head, jockey
        leg(-0.24, 0.08, phase + 2.6, false); leg(0.22, 0.08, phase + 3.4, true);
        c.strokeStyle = coat; c.lineWidth = 0.05; c.beginPath(); c.moveTo(-0.3, -0.06);
        c.quadraticCurveTo(-0.5, -0.02 + Math.sin(phase) * 0.04, -0.58, 0.1 + Math.sin(phase + 1) * 0.05); c.stroke();
        c.fillStyle = coat; c.beginPath(); c.ellipse(0, 0, 0.34, 0.16, 0, 0, Math.PI * 2); c.fill();
        c.beginPath(); c.ellipse(0.22, -0.02, 0.15, 0.16, 0, 0, Math.PI * 2); c.fill();
        leg(-0.24, 0.08, phase, false); leg(0.22, 0.08, phase + 0.8, true);
        const ny = Math.sin(phase) * 0.012;
        c.beginPath(); c.moveTo(0.26, -0.1); c.lineTo(0.5, -0.27 + ny); c.lineTo(0.56, -0.2 + ny); c.lineTo(0.34, 0.03); c.closePath(); c.fill();
        c.beginPath(); c.ellipse(0.58, -0.24 + ny, 0.095, 0.05, 0.5, 0, Math.PI * 2); c.fill();
        c.fillStyle = dark; c.beginPath(); c.moveTo(0.5, -0.3 + ny); c.lineTo(0.52, -0.36 + ny); c.lineTo(0.55, -0.3 + ny); c.fill();
        c.strokeStyle = dark; c.lineWidth = 0.025; c.beginPath(); c.moveTo(0.3, -0.12); c.lineTo(0.48, -0.27 + ny); c.stroke();
        // saddle cloth with number
        c.fillStyle = silkC; c.fillRect(-0.1, -0.15, 0.17, 0.15);
        c.strokeStyle = "rgba(0,0,0,0.5)"; c.lineWidth = 0.012; c.strokeRect(-0.1, -0.15, 0.17, 0.15);
        c.fillStyle = silkT; c.font = "bold 0.12px sans-serif"; c.textAlign = "center"; c.textBaseline = "middle";
        c.fillText(String(r.horse_number), -0.015, -0.075);
        // jockey (crouched)
        c.fillStyle = silkC; c.beginPath(); c.ellipse(0.04, -0.23, 0.1, 0.06, -0.5, 0, Math.PI * 2); c.fill();
        c.strokeStyle = "rgba(0,0,0,0.4)"; c.lineWidth = 0.01; c.stroke();
        c.fillStyle = "#f3d3b5"; c.beginPath(); c.arc(0.15, -0.28, 0.034, 0, Math.PI * 2); c.fill();
        c.fillStyle = silkC; c.beginPath(); c.arc(0.15, -0.295, 0.04, Math.PI, 0); c.fill();
        c.restore();
        if (isLead) { c.fillStyle = "#ffeb3b"; c.beginPath(); c.moveTo(x - 5, y - len * 0.55 - 12); c.lineTo(x + 5, y - len * 0.55 - 12); c.lineTo(x, y - len * 0.55 - 4); c.fill(); }
    }

    function drawMain() {
        const c = cctx, W = DIM.W, H = DIM.H, s = S;
        c.setTransform(DIM.dpr, 0, 0, DIM.dpr, 0, 0);
        const pxm = W / s.camW, camL = s.camD - s.camW / 2;
        const yNear = H * 0.80, yFar = H * 0.50, wT = s.wmin;
        const yOf = lat => yNear + (yFar - yNear) * clamp(lat / wT, 0, 1);
        const sc = lat => 1 - 0.38 * clamp(lat / wT, 0, 1);
        const X = d => (d - camL) * pxm;

        // sky, far scenery
        const sky = c.createLinearGradient(0, 0, 0, H * 0.5); sky.addColorStop(0, "#7ec0ee"); sky.addColorStop(1, "#dff1fb");
        c.fillStyle = sky; c.fillRect(0, 0, W, H);
        c.fillStyle = "#6d8f78";
        for (let i = -2; i < 40; i++) { const wx = (i * 90 - camL * 0.12) % (W + 180); const px = ((wx % (W + 180)) + W + 180) % (W + 180) - 90; c.beginPath(); c.arc(px, H * 0.46, 34 + (i * 13 % 17), Math.PI, 0); c.fill(); }
        // grandstand along the last ~350 m
        const gx0 = X(s.D - 380), gx1 = X(s.D + 80);
        if (gx1 > 0 && gx0 < W) {
            const gy = H * 0.20, gh = H * 0.26;
            c.fillStyle = "#c9ced6"; c.fillRect(gx0, gy, gx1 - gx0, gh);
            c.fillStyle = "#98a1ad"; c.fillRect(gx0, gy, gx1 - gx0, 7);
            for (let x = Math.max(gx0, 0); x < Math.min(gx1, W); x += 11) for (let y = gy + 16; y < gy + gh - 6; y += 11) {
                c.fillStyle = ["#e57373", "#ffd54f", "#64b5f6", "#a5d6a7", "#f5f5f5", "#ba68c8"][((x * 7 + y * 3) | 0) % 6]; c.fillRect(x + 2, y, 5, 5);
            }
        }
        // turf, stripes scrolling with distance
        const turf = s.course.surface === "dirt" ? ["#8d6e5a", "#a07e68"] : ["#2e8b3d", "#37a047"];
        c.fillStyle = turf[0]; c.fillRect(0, H * 0.46, W, H * 0.54);
        for (let d = Math.floor(camL / 20) * 20; d < camL + s.camW + 20; d += 20) {
            if (((d / 20) | 0) % 2) { c.fillStyle = turf[1]; c.fillRect(X(d), H * 0.5, 20 * pxm, H * 0.5); }
        }
        // far rail
        c.fillStyle = "#ffffff"; c.fillRect(0, H * 0.485, W, 3);
        // furlong markers and the finish line
        c.textAlign = "center"; c.font = "bold 12px sans-serif";
        for (let rem = 200; rem <= s.D; rem += 200) {
            const d = s.D - rem, x = X(d); if (x < -30 || x > W + 30) continue;
            c.fillStyle = rem === 600 ? "#ff9800" : "#ffffff"; c.fillRect(x - 1.5, H * 0.5, 3, H * 0.30 - 4);
            c.fillStyle = "rgba(0,0,0,0.55)"; c.fillRect(x - 24, H * 0.5 - 18, 48, 16);
            c.fillStyle = rem === 600 ? "#ffcc80" : "#ffffff"; c.fillText(rem === 600 ? "600m▶" : rem + "m", x, H * 0.5 - 6);
        }
        const fx = X(s.D);
        if (fx > -20 && fx < W + 20) {
            c.fillStyle = "#ffffff"; c.fillRect(fx - 3, H * 0.34, 6, H * 0.50);
            for (let i = 0; i < 9; i++) { c.fillStyle = i % 2 ? "#d32f2f" : "#ffffff"; c.fillRect(fx - 3, H * 0.34 + i * (H * 0.50 / 9), 6, H * 0.50 / 9); }
            c.fillStyle = "#d32f2f"; c.fillRect(fx - 30, H * 0.30, 60, 20); c.fillStyle = "#fff"; c.font = "bold 13px sans-serif"; c.fillText("GOAL", fx, H * 0.30 + 15);
        }
        // start gate
        const sx = X(0);
        if (sx > -60 && sx < W + 60) { c.fillStyle = "rgba(60,70,85,0.9)"; c.fillRect(sx - 52, H * 0.45, 52, H * 0.38); c.fillStyle = "#ffb300"; c.fillRect(sx - 52, H * 0.45, 52, 5); }

        // horses: far lanes first
        const list = s.runners.slice().sort((a, b) => b.lat - a.lat);
        const lead = s.order[0];
        let offL = 0, offR = 0;
        const rankOf = new Map(s.order.map((r, i) => [r, i]));
        list.forEach(r => {
            const x = X(r.d), scl = sc(r.lat), len = clamp(2.5 * pxm * 1.9, 30, 120) * scl, y = yOf(r.lat);
            if (x < -len) { offL++; return; } if (x > W + len) { offR++; return; }
            const ph = s.t * Math.PI * 2 * 2.6 + r.horse_number * 0.9;
            c.fillStyle = "rgba(0,0,0,0.25)"; c.beginPath(); c.ellipse(x - len * 0.05, y + len * 0.3, len * 0.4, len * 0.06, 0, 0, Math.PI * 2); c.fill();
            drawHorse(c, x, y, len, s.t > 0 ? ph : 0.4, r, false);
            const rk = rankOf.get(r);
            if (s.hasReplay && s.t > 0 && rk < 3) {
                const col = ["#ffd54f", "#cfd8dc", "#d7a371"][rk], by2 = y - len * 0.62;
                c.fillStyle = col; c.strokeStyle = "#000"; c.lineWidth = 1.5; c.beginPath(); c.arc(x + len * 0.1, by2, 9, 0, Math.PI * 2); c.fill(); c.stroke();
                c.fillStyle = "#000"; c.font = "bold 12px sans-serif"; c.textAlign = "center"; c.textBaseline = "middle"; c.fillText(String(rk + 1), x + len * 0.1, by2 + 0.5); c.textBaseline = "alphabetic";
            }
        });
        // near rail + posts
        c.fillStyle = "#ffffff"; c.fillRect(0, H * 0.865, W, 4);
        for (let d = Math.floor(camL / 10) * 10; d < camL + s.camW + 10; d += 10) { c.fillRect(X(d) - 1, H * 0.865, 2.5, 18); }
        if (offL) { c.fillStyle = "rgba(0,0,0,0.6)"; c.fillRect(6, H * 0.88, 74, 20); c.fillStyle = "#fff"; c.textAlign = "left"; c.font = "bold 12px sans-serif"; c.fillText(`◀ ${offL}頭`, 12, H * 0.88 + 14); }
        if (offR) { c.fillStyle = "rgba(0,0,0,0.6)"; c.fillRect(W - 80, H * 0.88, 74, 20); c.fillStyle = "#fff"; c.textAlign = "right"; c.font = "bold 12px sans-serif"; c.fillText(`${offR}頭 ▶`, W - 12, H * 0.88 + 14); }

        if (s.sim) {
            c.fillStyle = "rgba(230,81,0,0.92)"; const tw = 168 * DIM.k; c.fillRect((W - tw) / 2, 8, tw, 26 * DIM.k);
            c.fillStyle = "#fff"; c.font = `bold ${Math.round(13 * DIM.k)}px sans-serif`; c.textAlign = "center"; c.fillText("SIMULATION（架空）", W / 2, 8 + 18 * DIM.k);
        }
        if (!s.hasReplay && s.msg) {
            const k2 = DIM.k, lines = [], text = "実際の結果の再生はできません: " + s.msg + (CUR && CUR.race.horses && CUR.race.horses.length >= 2 ? " ※「シミュレーション」は使えます。" : "");
            for (let i = 0; i < text.length; i += 26) lines.push(text.slice(i, i + 26));
            const bh = lines.length * 20 * k2 + 14, bw = Math.min(W - 24, 26 * 15 * k2 + 24);
            c.fillStyle = "rgba(120,20,20,0.88)"; c.fillRect((W - bw) / 2, H * 0.12, bw, bh);
            c.fillStyle = "#fff"; c.font = `bold ${Math.round(14 * k2)}px sans-serif`; c.textAlign = "center";
            lines.forEach((ln, i) => c.fillText(ln, W / 2, H * 0.12 + 22 * k2 + i * 20 * k2));
        }
        // progress bar (all horses)
        const by = H - 16;
        c.fillStyle = "rgba(0,0,0,0.55)"; c.fillRect(0, by - 8, W, 24);
        c.fillStyle = "#cfd8dc"; c.fillRect(14, by + 2, W - 28, 3);
        s.runners.forEach(r => { const p = clamp(r.d / s.D, 0, 1.0); c.fillStyle = silk(r)[0]; c.strokeStyle = "#000"; c.lineWidth = 1;
            c.beginPath(); c.arc(14 + p * (W - 28), by + 3.5, 5, 0, Math.PI * 2); c.fill(); c.stroke(); });
        // HUD
        const k = DIM.k, rem = Math.max(0, s.D - (lead ? lead.d : 0));
        c.font = `bold ${Math.round(14 * k)}px sans-serif`; c.textAlign = "left";
        c.fillStyle = "rgba(0,0,0,0.6)"; c.fillRect(8, 8, 230 * k, 30 * k); c.fillStyle = "#ffeb3b";
        c.fillText(s.t < 0 ? "ゲートイン" : (s.hasReplay ? `先頭 ${lead.horse_number}番 ${lead.horse_name.slice(0, 7)}` : "出走表"), 14, 8 + 20 * k);
        c.fillStyle = "rgba(0,0,0,0.6)"; c.fillRect(W - 8 - 190 * k, 8, 190 * k, 30 * k); c.fillStyle = "#fff"; c.textAlign = "right";
        c.fillText(`残り${Math.round(rem)}m  ${s.t < 0 ? "0:00.0" : fmtTime(Math.min(s.t, s.Tend))}`, W - 14, 8 + 20 * k);
    }

    // ---------- drawing: top-down course map to scale ----------
    function drawMap() {
        const c = mctx, W = DIM.mW, H = DIM.mH, s = S, g = s.g;
        c.setTransform(DIM.dpr, 0, 0, DIM.dpr, 0, 0);
        c.clearRect(0, 0, W, H);
        c.fillStyle = "#1e2b27"; c.fillRect(0, 0, W, H);
        const w = s.wmin, halfW = g.kind === "straight" ? g.S / 2 : g.S / 2 + g.r + w;
        const halfH = g.kind === "straight" ? w : g.r + w;
        const sc = Math.min((W - 60) / (2 * halfW), (H - 50) / (2 * halfH));
        const P = (u, lat) => { const p = mapPos(g, u, lat); return { x: W / 2 + p.x * sc, y: H / 2 + 6 - p.y * sc }; };
        const trace = (lat) => { c.beginPath(); const n = 240; for (let i = 0; i <= n; i++) { const p = P(g.kind === "straight" ? (i / n) * g.L - g.L : (i / n) * g.L, lat); i ? c.lineTo(p.x, p.y) : c.moveTo(p.x, p.y); } if (g.kind === "loop") c.closePath(); };
        const turf = s.course.surface === "dirt" ? "#8d6e5a" : "#2e8b3d";
        c.lineJoin = "round"; c.strokeStyle = turf; c.lineWidth = w * sc; trace(w / 2); c.stroke();
        c.strokeStyle = "#ffffff"; c.lineWidth = 1.5; trace(0); c.stroke(); trace(w); c.stroke();
        // finish and start
        const f0 = P(0, -2), f1 = P(0, w + 2); c.strokeStyle = "#ffffff"; c.lineWidth = 3; c.beginPath(); c.moveTo(f0.x, f0.y); c.lineTo(f1.x, f1.y); c.stroke();
        c.setLineDash([4, 4]); c.strokeStyle = "#d32f2f"; c.beginPath(); c.moveTo(f0.x, f0.y); c.lineTo(f1.x, f1.y); c.stroke(); c.setLineDash([]);
        const s0 = P(-s.D, -2), s1 = P(-s.D, w + 2), side = s0.x >= f0.x ? 1 : -1, close = Math.abs(s0.x - f0.x) < 70;
        c.font = "bold 12px sans-serif"; c.fillStyle = "#ffeb3b"; c.textAlign = close ? (side > 0 ? "right" : "left") : "center";
        c.fillText("GOAL", f0.x + (close ? -side * 3 : 0), f0.y + (f0.y > H / 2 ? 16 : -8)); c.strokeStyle = "#ffb300"; c.lineWidth = 3; c.beginPath(); c.moveTo(s0.x, s0.y); c.lineTo(s1.x, s1.y); c.stroke();
        c.fillStyle = "#ffb300"; c.textAlign = close ? (side > 0 ? "left" : "right") : "center"; c.fillText("START", s0.x + (close ? side * 3 : 0), s0.y + (s0.y > H / 2 ? 16 : -8));
        // 600 m to go (last 3F)
        const m0 = P(-600, -2), m1 = P(-600, w + 2); c.strokeStyle = "#ff9800"; c.lineWidth = 1.5; c.beginPath(); c.moveTo(m0.x, m0.y); c.lineTo(m1.x, m1.y); c.stroke();
        // title
        const cs = s.course;
        c.fillStyle = "#ffffff"; c.textAlign = "left"; c.font = "bold 13px sans-serif";
        c.fillText(cs.kind === "straight" ? `${cs.venue} 芝 直線コース ${cs.straight_m}m  幅員${cs.width_min_m}m`
            : `${cs.venue} ${cs.surface === "dirt" ? "ダート" : "芝"}${cs.variant ? "・" + cs.variant + "回り" : ""} ${cs.direction}回り  1周${cs.loop_m}m  直線${cs.straight_m}m  幅員${cs.width_min_m}m〜`, 10, 18);
        // horses
        const lead = s.order && s.order[0];
        (s.order ? s.order.slice().reverse() : s.runners).forEach(r => {
            const lat = clamp(r.lat, 0.5, w - 0.5), p = P(uOf(s, r.d), lat);
            c.fillStyle = silk(r)[0]; c.strokeStyle = r === lead && s.t > 0 ? "#ffeb3b" : "#000"; c.lineWidth = r === lead && s.t > 0 ? 2.5 : 1;
            c.beginPath(); c.arc(p.x, p.y, 5, 0, Math.PI * 2); c.fill(); c.stroke();
            c.fillStyle = silk(r)[1]; c.font = "bold 7px sans-serif"; c.textAlign = "center"; c.textBaseline = "middle"; c.fillText(String(r.horse_number), p.x, p.y + 0.5); c.textBaseline = "alphabetic";
        });
    }

    // ---------- HUD: ranking, commentary, result ----------
    function updateHud() {
        const s = S;
        if ($("sim-live-time")) $("sim-live-time").textContent = s.t < 0 ? "0:00.0" : fmtTime(Math.min(s.t, s.Tend));
        if ($("replay-seek")) $("replay-seek").value = s.Tend ? String(Math.round(((s.t + GATE_S) / (s.Tend + GATE_S)) * 1000)) : "0";
        const rk = $("replay-rank");
        if (rk && s.order) {
            const top = s.order.slice(0, 8), lead = top[0];
            rk.innerHTML = top.map((r, i) => {
                const gap = i === 0 ? "" : `+${Math.max(0, lead.d - r.d).toFixed(1)}m`;
                return `<li><span class="badge" style="background:${silk(r)[0]};color:${silk(r)[1]};border:1px solid #888">${r.horse_number}</span> ${esc(r.horse_name)} <span class="text-muted small">${gap}</span></li>`;
            }).join("");
        }
        const say = $("broadcast-commentary-text"); if (!say || !s.hasReplay) return;
        const lead = s.order[0], second = s.order[1], rem = s.D - lead.d, nm = r => `${r.horse_number}番${r.horse_name}`;
        let msg = null;
        if (s.t < 0) msg = `${s.runners.length}頭、ゲートイン。${s.course.venue}${s.course.surface === "dirt" ? "ダート" : "芝"}${s.D}m。`;
        else if (s.t < 4) msg = "スタートしました！";
        else if (rem <= 0 && s.order.some(r => r.d >= s.D)) msg = null;
        const marks = [[600, `残り600m、ここから上がり3F。先頭は${nm(lead)}。`], [Math.min(s.course.straight_m, 500), `最後の直線に入ります。先頭は${nm(lead)}、${second ? nm(second) + "が続く" : ""}。`], [200, `残り200m！先頭は${nm(lead)}、${second ? "2番手に" + nm(second) : ""}。`]];
        marks.forEach(([m, text]) => { if (rem <= m && rem > 0 && !s.said[m]) { s.said[m] = true; msg = text; } });
        if (!s.finished && s.t >= s.Tw && s.t > 0) {
            s.finished = true;
            msg = finishText();
            showResult();
        }
        if (msg) say.textContent = msg;
    }

    function finishText() {
        const w = S.runners.find(r => r.finish === 1) || S.order[0];
        return `ゴール！ ${w.horse_number}番${w.horse_name} が1着${S.sim ? "（シミュレーション）" : ""}。タイム ${fmtTime(w.time_s)}${w.last3f_s ? "、上がり3F " + w.last3f_s.toFixed(1) : ""}。`;
    }

    function showResult() {
        const el = $("replay-result"); if (!el) return;
        const rows = S.runners.slice().sort((a, b) => (a.finish || 99) - (b.finish || 99));
        el.innerHTML = (S.sim ? `<div class="fw-bold text-danger mb-1">シミュレーション結果（実際の結果ではありません）</div>` : "") + `<table class="table table-sm mb-0"><thead><tr><th>着</th><th>馬番</th><th>馬名</th><th>タイム</th><th>上がり3F</th></tr></thead><tbody>` +
            rows.map(r => `<tr><td>${r.finish || "—"}</td><td>${r.horse_number}</td><td>${esc(r.horse_name)}</td><td>${r.time_s ? fmtTime(r.time_s) : "—"}</td><td>${r.last3f_s ? r.last3f_s.toFixed(1) : "—"}</td></tr>`).join("") + "</tbody></table>";
    }

    // ---------- loop / controls ----------
    function frame(ts) {
        if (!S) return;
        const dt = lastTs ? Math.min(0.1, (ts - lastTs) / 1000) : 0; lastTs = ts;
        if (S.playing && S.hasReplay) {
            S.t += dt * S.speed;
            if (S.t >= S.Tend) { S.t = S.Tend; S.playing = false; setButton(); }
        }
        step(dt, false); draw();
        raf = requestAnimationFrame(frame);
    }
    function draw() { drawMain(); drawMap(); updateHud(); }
    function setButton() { const b = $("btn-start-sim"); if (b) b.innerHTML = S && S.playing ? '<i class="fa-solid fa-pause me-1"></i> 一時停止' : '<i class="fa-solid fa-play me-1"></i> ' + (S && S.t > -GATE_S + 0.01 && S.t < S.Tend ? "再開" : "再生"); }

    function seek(t) {
        S.t = clamp(t, -GATE_S, S.Tend); S.said = {}; S.finished = S.t >= S.Tw && S.Tw > 0;
        const res = $("replay-result"); if (res && !S.finished) res.innerHTML = "";
        step(0, true); draw();
        if (S.finished && S.hasReplay) { showResult(); const say = $("broadcast-commentary-text"); if (say) say.textContent = finishText(); }
    }

    function setNote(text, warn) { const n = $("replay-note"); if (n) { n.textContent = text; n.className = "small mb-2 " + (warn ? "text-danger" : "text-muted"); } }
    function setBadges(c) {
        const set = (id, t) => { const e = $(id); if (e) e.textContent = t; };
        set("badge-track-dir", `回り: ${c.direction}回り${c.variant ? "（" + c.variant + "）" : ""}`);
        set("badge-track-shape", c.loop_m ? `1周: ${c.loop_m}m（Aコース）` : "直線コース");
        set("badge-track-stretch", `直線: ${c.straight_m}m`);
        set("badge-track-slope", c.drop_m != null ? `高低差: ${c.drop_m}m` : "高低差: —");
    }

    async function setRace(race) {
        if (raf) cancelAnimationFrame(raf), raf = null;
        S = null; lastTs = null;
        const res = $("replay-result"); if (res) res.innerHTML = ""; const rk = $("replay-rank"); if (rk) rk.innerHTML = "";
        const q = new URLSearchParams({ venue: race.track_name, surface: race.surface_type, distance: race.distance, variant: race.course_variant || "" });
        let replay = null, course = null, msg = "";
        try {
            const r = await fetch(`/api/replay/${encodeURIComponent(race.race_id)}?variant=${encodeURIComponent(race.course_variant || "")}`);
            const j = await r.json();
            if (j.status === "success") { replay = j; course = j.course; } else { msg = j.message; }
        } catch (e) { msg = "リプレイデータの取得に失敗しました。"; }
        if (!course) {
            try { const r = await fetch(`/api/course?${q}`); const j = await r.json(); if (j.status === "success") course = j.course; else msg = msg || j.message; } catch (e) { /* ignore */ }
        }
        const simBtn = $("btn-simulate"), realBtn = $("btn-real");
        if (realBtn) realBtn.classList.add("d-none");
        if (simBtn) simBtn.innerHTML = '<i class="fa-solid fa-dice me-1"></i> シミュレーション';
        if (!course) { CUR = null; if (simBtn) simBtn.disabled = true; setNote(msg || "このコースは表示できません。", true); clear(); return; }
        CUR = { race, course };
        if (simBtn) simBtn.disabled = !(race.horses && race.horses.length >= 2);
        fit(); setBadges(course);
        let runners, has = !!replay;
        if (has) runners = replay.runners; else runners = race.horses.map(h => ({ horse_number: h.horse_number, horse_name: h.horse_name, frame: null, finish: null, time_s: null, last3f_s: null }));
        S = buildState(course, runners, race, has);
        S.msg = msg;
        S.speed = parseFloat(($("select-replay-speed") || { value: "2" }).value);
        setNote(has ? `${replay.notes[0]}${course.note ? " " + course.note : ""}` : `${msg} （コースの形と出走馬のみ表示します）${course.note ? " " + course.note : ""}`, !has);
        const b = $("btn-start-sim"), r2 = $("btn-reset-sim"); if (b) b.disabled = !has; if (r2) r2.disabled = !has;
        const say = $("broadcast-commentary-text"); if (say) say.textContent = has ? "再生ボタンでレースが始まります。" : `実際の結果の再生はできません: ${msg}（シミュレーションは使えます）`;
        step(0, true); S.camD = (S.order[0].d); draw(); setButton();
        raf = requestAnimationFrame(frame);
    }

    async function startSimulation() {
        if (!CUR) return;
        const { race, course } = CUR;
        const horses = race.horses;
        const stage = parseInt(($("select-ability-stage") || { value: "1" }).value, 10);
        const say0 = $("broadcast-commentary-text");
        let ab = null;
        try {
            const r = await fetch("/api/ability", { method: "POST", headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ race_id: race.race_id, stage, horses: horses.map(h => ({ horse_number: h.horse_number, odds: h.odds })) }) });
            ab = await r.json();
        } catch (e) { ab = { status: "error", message: "通信に失敗しました。" }; }
        if (ab.status !== "success") {
            setNote(`シミュレーションできません: ${ab.message}`, true);
            if (say0) say0.textContent = `シミュレーションできません: ${ab.message}`;
            return;
        }
        let base = null;
        try {
            const q = new URLSearchParams({ venue: race.track_name, surface: race.surface_type, distance: race.distance });
            const j = await (await fetch(`/api/baseline?${q}`)).json();
            if (j.status === "success" && j.baseline) base = j.baseline;
        } catch (e) { /* use the rough approximation */ }
        if (!base) base = RaceSim.fallbackBase(race.distance, course.surface);
        const runners = RaceSim.simulate(horses, base, { probs: horses.map(h => ab.probs[String(h.horse_number)]) });
        runners.forEach(r => { const h = horses.find(x => x.horse_number === r.horse_number); r.jockey = h ? h.jockey_name : ""; });
        if (raf) cancelAnimationFrame(raf), raf = null;
        lastTs = null;
        const speed = parseFloat(($("select-replay-speed") || { value: "2" }).value);
        S = buildState(course, runners, race, true);
        S.sim = true; S.speed = speed; S.msg = ""; S.playing = true;
        const res = $("replay-result"); if (res) res.innerHTML = "";
        const how = stage === 1
            ? "層1（能力のみ。オッズも人気順位も使いません）。過去の検証では、この層で1番手に選んだ馬の1着率は27.0%で、人気1位(33.3%)を下回りました。"
            : "層2（能力×人気順位。人気順位は画面のオッズの低い順）。過去の検証では、人気順位だけより確率の質が少し良い(0.0085)程度で、実際のオッズとの比較では改善を確認できていません。";
        setNote(`シミュレーション: ${how} 勝率でサイコロを振って作った架空のレースで、押すたびに変わります。実際の結果の予想ではありません。勝ち時計・上がり3Fは ${base.source}。`, false);
        const say = $("broadcast-commentary-text"); if (say) say.textContent = "シミュレーション開始。各馬ゲートイン。";
        const b = $("btn-start-sim"), r2 = $("btn-reset-sim"), real = $("btn-real"), sim = $("btn-simulate");
        if (b) b.disabled = false; if (r2) r2.disabled = false; if (real) real.classList.remove("d-none");
        if (sim) sim.innerHTML = '<i class="fa-solid fa-dice me-1"></i> もう一度';
        step(0, true); S.camD = S.order[0].d; draw(); setButton();
        raf = requestAnimationFrame(frame);
    }

    function clear() { [main, mapc].forEach(cv => { if (cv) { const x = cv.getContext("2d"); x.setTransform(1, 0, 0, 1, 0, 0); x.clearRect(0, 0, cv.width, cv.height); } }); }

    function init() {
        main = $("replay-canvas"); mapc = $("replay-map");
        if (!main || !mapc) return;
        cctx = main.getContext("2d"); mctx = mapc.getContext("2d");
        fit(); window.addEventListener("resize", () => { fit(); if (S) draw(); });
        $("btn-start-sim") && $("btn-start-sim").addEventListener("click", () => {
            if (!S || !S.hasReplay) return;
            if (S.t >= S.Tend) { seek(-GATE_S); }
            S.playing = !S.playing; setButton();
        });
        $("btn-reset-sim") && $("btn-reset-sim").addEventListener("click", () => { if (!S) return; S.playing = false; seek(-GATE_S); const res = $("replay-result"); if (res) res.innerHTML = ""; setButton(); });
        $("btn-simulate") && $("btn-simulate").addEventListener("click", startSimulation);
        $("btn-real") && $("btn-real").addEventListener("click", () => { if (CUR) setRace(CUR.race); const sim = $("btn-simulate"); if (sim) sim.innerHTML = '<i class="fa-solid fa-dice me-1"></i> シミュレーション'; });
        $("select-replay-speed") && $("select-replay-speed").addEventListener("change", e => { if (S) S.speed = parseFloat(e.target.value); });
        $("replay-seek") && $("replay-seek").addEventListener("input", e => { if (S && S.hasReplay) { S.playing = false; setButton(); seek(-GATE_S + (parseFloat(e.target.value) / 1000) * (S.Tend + GATE_S)); } });
    }

    window.Replay = { init, setRace, seekTo: t => { if (S) { S.playing = false; seek(t); } }, state: () => S };
    document.addEventListener("DOMContentLoaded", init);
})();
