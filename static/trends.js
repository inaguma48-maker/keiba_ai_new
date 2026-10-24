/*
 * Reasons to keep / cut each horse, from the past runnings of the same race (POST /api/trends).
 * Breeder and training center come from the JRA horse pages; the button fetches them a batch at a time.
 */
(function () {
    let token = 0;

    const box = () => document.getElementById("trend-body");
    const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
    const pct = r => `${Math.round(r * 100)}%`;

    async function post(url, body) {
        try {
            const res = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
            try {
                return await res.json();
            } catch (e) {
                return { status: "error", message: `サーバーの応答を読めません（${res.status}）。` };
            }
        } catch (e) {
            return { status: "error", message: "アプリに接続できません。アプリが起動しているか確認してください。" };
        }
    }

    function horseCard(h) {
        const items = h.keep.map(s => `<li class="text-success"><strong>残す:</strong> ${esc(s)}</li>`)
            .concat(h.cut.map(s => `<li class="text-danger"><strong>切る:</strong> ${esc(s)}</li>`));
        return `<div class="border rounded p-2 mb-2 bg-white">
            <div class="fw-bold">${h.horse_number} ${esc(h.horse_name)}</div>
            <ul class="small mb-1 ps-3">${items.join("")}</ul>
            <div class="text-muted" style="font-size: .75rem;">この馬: ${h.facts.map(esc).join(" ／ ")}</div>
        </div>`;
    }

    function render(d, race, my) {
        const hst = d.history;
        const what = hst.mode === "named" ? `「${esc(hst.label)}」` : `同じ条件のレース（${esc(hst.label)}）`;
        let html = `<p class="small mb-2"><strong>比べたレース:</strong> ${what} ${esc(hst.years)}の${hst.n_races}回
            （出走${hst.n_horses}頭・3着以内${hst.n_top3}頭＝${pct(hst.rate)}）</p>`;
        if (d.profiles.have < d.profiles.need) {
            const rest = d.profiles.need - d.profiles.have;
            html += `<div class="d-flex flex-wrap align-items-center gap-2 small mb-2">
                <span>調教場・生産牧場: 取得済み ${d.profiles.have}/${d.profiles.need}頭</span>
                <button id="btn-trend-profiles" class="btn btn-sm btn-outline-primary">JRAから取得（残り${rest}頭・約${Math.max(1, Math.ceil(rest * 1.3 / 60))}分）</button>
                <span id="trend-profile-progress" class="text-muted"></span></div>`;
        }
        const groups = [["keep", "残す馬（3着に来る傾向）", "success"], ["cut", "切る馬（3着に来ない傾向）", "danger"],
                        ["mixed", "判断が分かれる馬", "warning"], ["none", "当てはまる条件がない馬", "secondary"]];
        for (const [verdict, title, color] of groups) {
            const hs = d.horses.filter(h => h.verdict === verdict);
            if (!hs.length) continue;
            html += `<h6 class="mt-3 mb-2 fw-bold text-${color === "warning" ? "dark" : color}">
                <span class="badge bg-${color} me-1">${hs.length}頭</span>${title}</h6>`;
            html += verdict === "none"
                ? `<p class="small mb-1">${hs.map(h => `${h.horse_number} ${esc(h.horse_name)}`).join("、")}</p>`
                : hs.map(horseCard).join("");
        }
        if (d.rules.length) {
            html += `<details class="small mt-2"><summary>見つかった条件の一覧（${d.rules.length}件）</summary><ul class="mb-0 ps-3 mt-1">
                ${d.rules.map(r => `<li class="text-${r.kind === "keep" ? "success" : "danger"}">${r.kind === "keep" ? "残す" : "切る"}・${esc(r.factor)}: ${esc(r.sentence)}</li>`).join("")}
                </ul></details>`;
        } else {
            html += `<p class="small mb-1">偶然とは言えない差のある条件は、見つかりませんでした。</p>`;
        }
        if (d.notes.length) html += `<ul class="small text-muted mt-2 mb-1 ps-3">${d.notes.map(n => `<li>${esc(n)}</li>`).join("")}</ul>`;
        html += `<p class="small text-muted mb-0">※ 過去の傾向です。「絶対に来ない／来る」条件はありません。
            過去の3着以内の割合が平均と偶然では説明しにくいほど違い（95%信頼区間）、しかも前半・後半どちらの年でも同じ傾向だった条件だけを表示しています。
            成績は「1着-2着-3着-4着以下」の頭数です。</p>`;
        box().innerHTML = html;
        const btn = document.getElementById("btn-trend-profiles");
        if (btn) btn.addEventListener("click", () => fetchProfiles(race, my));
    }

    async function fetchProfiles(race, my) {
        const btn = document.getElementById("btn-trend-profiles");
        const prog = document.getElementById("trend-profile-progress");
        btn.disabled = true;
        prog.textContent = "JRAの競走馬ページから取得しています…";
        while (my === token) {
            const d = await post("/api/profiles/fetch", { race_id: race.race_id });
            if (my !== token) return;
            if (d.status !== "success") {
                prog.textContent = d.message || "取得できませんでした。";
                btn.disabled = false;
                return;
            }
            if (d.remaining === 0) break;
            prog.textContent = `取得中… 残り${d.remaining}頭`;
        }
        if (my === token) load(race);
    }

    async function load(race) {
        const my = ++token;
        if (!box()) return;
        if (!race || !race.race_id) {
            box().innerHTML = '<p class="text-muted small mb-0">レースを読み込むと表示します。</p>';
            return;
        }
        box().innerHTML = '<p class="text-muted small mb-0"><span class="spinner-border spinner-border-sm me-1"></span>過去の同レースを集計しています…</p>';
        const d = await post("/api/trends", { race_id: race.race_id });
        if (my !== token) return;
        if (d.status !== "success") {
            box().innerHTML = `<div class="alert alert-secondary small mb-0">${esc(d.message || "表示できません。")}</div>`;
            return;
        }
        render(d, race, my);
    }

    window.Trends = { load };
})();
