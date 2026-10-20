document.addEventListener("DOMContentLoaded", () => {
    let currentRace = null;

    const selectRace = document.getElementById("select-race");
    const btnLoadRace = document.getElementById("btn-load-race");
    const btnRecalculate = document.getElementById("btn-recalculate");
    const formAddHorse = document.getElementById("form-add-horse");
    const formImportJra = document.getElementById("form-import-jra");
    const btnAutoDetectJra = document.getElementById("btn-auto-detect-jra");

    const displayRaceName = document.getElementById("display-race-name");
    const displayRaceMeta = document.getElementById("display-race-meta");
    const tbodyPredictions = document.getElementById("tbody-predictions");

    // Load available races (including DB saved races) on start
    loadRaces();

    // The race replay (course map, side view, ranking) lives in static/replay.js
    function updateTrackProfileUI(race) {
        if (window.Replay) window.Replay.setRace(race);
    }

    async function loadRaces(selectedId = null) {
        try {
            const res = await fetch("/api/races");
            const data = await res.json();
            if (data.status === "success") {
                selectRace.innerHTML = '<option value="">-- 保存・サンプルレースを選択 --</option>';
                data.races.forEach(r => {
                    const opt = document.createElement("option");
                    opt.value = r.race_id;
                    opt.textContent = `[DB保存] ${r.race_name} (${r.track_name} ${r.surface_type}${r.distance}m / ${r.horse_count}頭)`;
                    selectRace.appendChild(opt);
                });
                if (selectedId) {
                    selectRace.value = selectedId;
                }
            }
        } catch (err) {
            console.error("Failed to fetch races:", err);
        }
    }

    btnLoadRace.addEventListener("click", async () => {
        const raceId = selectRace.value;
        if (!raceId) {
            alert("レースを選択してください。");
            return;
        }

        try {
            const res = await fetch(`/api/races/${raceId}`);
            const data = await res.json();
            if (data.status === "success") {
                currentRace = data.race;
                await runPrediction(currentRace);
            }
        } catch (err) {
            alert("レース情報の取得に失敗しました。");
        }
    });

    btnRecalculate.addEventListener("click", () => {
        if (currentRace) {
            runPrediction(currentRace);
        }
    });

    // One-Click JRA Auto Detection Event Listener
    if (btnAutoDetectJra) {
        btnAutoDetectJra.addEventListener("click", async () => {
            tbodyPredictions.innerHTML = '<tr><td colspan="4" class="text-center py-4"><div class="spinner-border text-warning" role="status"></div><div class="mt-2 text-dark fw-bold">JRA公式最新レース・オッズを自動検出中...</div></td></tr>';

            try {
                const res = await fetch("/api/auto_fetch_jra", { method: "POST" });
                const result = await res.json();

                if (result.status === "success" && result.results && result.results.length > 0) {
                    const firstResult = result.results[0];
                    currentRace = firstResult.race;
                    displayRaceName.textContent = firstResult.race.race_name;
                    displayRaceMeta.textContent = `${firstResult.race.track_name}競馬場 | ${firstResult.race.surface_type}${firstResult.race.distance}m | 馬場: ${firstResult.race.track_condition} | 天候: ${firstResult.race.weather} (自動検出完了)`;
                    renderPredictions(firstResult.predictions);
                    btnRecalculate.classList.remove("d-none");

                    await loadRaces(firstResult.race.race_id);
                    alert(result.message);
                } else {
                    alert("自動検出エラー: " + (result.message || "レースが見つかりませんでした"));
                }
            } catch (err) {
                console.error(err);
                alert("JRA自動検出通信エラーが発生しました。");
            }
        });
    }

    // JRA Racecard Import Form Submit
    formImportJra.addEventListener("submit", async (e) => {
        e.preventDefault();
        const urlInput = document.getElementById("input-jra-url").value.trim();
        const textInput = document.getElementById("input-jra-text").value.trim();

        if (!urlInput && !textInput) {
            alert("URL または 出馬表テキストを入力してください。");
            return;
        }

        tbodyPredictions.innerHTML = '<tr><td colspan="4" class="text-center py-4"><div class="spinner-border text-primary" role="status"></div><div class="mt-2 text-muted">JRA出馬表取り込み＆DB保存＆分析中...</div></td></tr>';

        try {
            const res = await fetch("/api/import_jra", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    url: urlInput || null,
                    text_content: textInput || null
                })
            });
            const result = await res.json();

            if (result.status === "success" && result.race) {
                currentRace = result.race;
                displayRaceName.textContent = result.race.race_name;
                displayRaceMeta.textContent = `${result.race.track_name}競馬場 | ${result.race.surface_type}${result.race.distance}m | 馬場: ${result.race.track_condition} | 天候: ${result.race.weather} (DB保管完了)`;

                updateTrackProfileUI(result.race);
                renderPredictions(result.predictions);
                btnRecalculate.classList.remove("d-none");

                // Refresh race selection dropdown with newly saved DB race
                await loadRaces(result.race.race_id);
            } else {
                alert("JRA取り込みエラー: " + (result.message || "取り込みに失敗しました"));
            }
        } catch (err) {
            console.error(err);
            alert("取り込み通信に失敗しました。");
        }
    });

    async function runPrediction(raceData) {
        displayRaceName.textContent = raceData.race_name;
        displayRaceMeta.textContent = `${raceData.track_name}競馬場 | ${raceData.surface_type}${raceData.distance}m | 馬場: ${raceData.track_condition} | 天候: ${raceData.weather}`;

        tbodyPredictions.innerHTML = '<tr><td colspan="4" class="text-center py-4"><div class="spinner-border text-primary" role="status"></div><div class="mt-2 text-muted">AI 思考解析中...</div></td></tr>';

        try {
            const res = await fetch("/api/predict", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(raceData)
            });
            const result = await res.json();

            if (result.status === "success") {
                updateTrackProfileUI(raceData);
                renderPredictions(result.predictions);
                btnRecalculate.classList.remove("d-none");

                // Refresh race list dropdown
                await loadRaces(raceData.race_id);
            } else {
                alert("予想の実行に失敗しました: " + result.message);
            }
        } catch (err) {
            console.error(err);
            alert("通信エラーが発生しました。");
        }
    }

    function esc(v) {
        return String(v).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
    }

    function renderPredictions(rows) {
        tbodyPredictions.innerHTML = "";
        rows.forEach((p, index) => {
            const tr = document.createElement("tr");
            if (index === 0) tr.classList.add("rank-1");
            else if (index === 1) tr.classList.add("rank-2");
            else if (index === 2) tr.classList.add("rank-3");

            const pct = (p.market_probability * 100).toFixed(1);
            tr.innerHTML = `
                <td class="text-center fw-bold fs-5">${esc(p.horse_number)}</td>
                <td>
                    <div class="fw-bold">${esc(p.horse_name)}</div>
                    <div class="text-muted small"><i class="fa-solid fa-user-tie me-1"></i>${esc(p.jockey_name)}</div>
                </td>
                <td class="text-center fw-bold text-primary">${esc(p.odds)} 倍</td>
                <td>
                    <div class="d-flex justify-content-between small mb-1">
                        <span>市場確率</span>
                        <span class="fw-bold">${pct}%</span>
                    </div>
                    <div class="progress prob-bar">
                        <div class="progress-bar bg-success" style="width: ${pct}%"></div>
                    </div>
                </td>
            `;
            tbodyPredictions.appendChild(tr);
        });
    }

    // Add Custom Horse
    formAddHorse.addEventListener("submit", (e) => {
        e.preventDefault();
        if (!currentRace) {
            alert("先にレースを選択してください。");
            return;
        }

        const horseNum = parseInt(document.getElementById("input-num").value);
        const horseName = document.getElementById("input-name").value;
        const jockeyName = document.getElementById("input-jockey").value;
        const odds = parseFloat(document.getElementById("input-odds").value);
        const speed = parseFloat(document.getElementById("input-speed").value);
        const jockeyWin = parseFloat(document.getElementById("input-jockey-win").value);

        const newHorse = {
            horse_number: horseNum,
            horse_name: horseName,
            jockey_name: jockeyName,
            trainer_name: "カスタム厩舎",
            age: 4,
            weight: 480.0,
            impost: 57.0,
            past_speed_rating: speed,
            past_win_rate: 0.3,
            jockey_win_rate: jockeyWin,
            trainer_win_rate: 0.2,
            track_aptitude: 0.9,
            odds: odds
        };

        const existingIdx = currentRace.horses.findIndex(h => h.horse_number === horseNum);
        if (existingIdx >= 0) {
            currentRace.horses[existingIdx] = newHorse;
        } else {
            currentRace.horses.push(newHorse);
        }

        runPrediction(currentRace);
    });
});
