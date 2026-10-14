document.addEventListener("DOMContentLoaded", () => {
    let currentRace = null;

    const selectRace = document.getElementById("select-race");
    const btnLoadRace = document.getElementById("btn-load-race");
    const btnRecalculate = document.getElementById("btn-recalculate");
    const btnRetrain = document.getElementById("btn-retrain");
    const formAddHorse = document.getElementById("form-add-horse");
    const formImportJra = document.getElementById("form-import-jra");
    const btnAutoDetectJra = document.getElementById("btn-auto-detect-jra");

    const displayRaceName = document.getElementById("display-race-name");
    const displayRaceMeta = document.getElementById("display-race-meta");
    const confidenceContainer = document.getElementById("confidence-container");
    const displayConfidence = document.getElementById("display-confidence");
    const tbodyPredictions = document.getElementById("tbody-predictions");

    // Canvas Simulation Elements
    const canvas = document.getElementById("raceCanvas");
    const ctx = canvas ? canvas.getContext("2d") : null;
    const btnStartSim = document.getElementById("btn-start-sim");
    const btnResetSim = document.getElementById("btn-reset-sim");
    const simLiveTime = document.getElementById("sim-live-time");

    const badgeTrackDir = document.getElementById("badge-track-dir");
    const badgeTrackShape = document.getElementById("badge-track-shape");
    const badgeTrackStretch = document.getElementById("badge-track-stretch");
    const badgeTrackSlope = document.getElementById("badge-track-slope");

    let simAnimId = null;
    let simProgress = 0; // 0.0 to 1.0
    let simRunning = false;
    let simPredictions = [];

    // Load available races (including DB saved races) on start
    loadRaces();

    function updateTrackProfileUI(race) {
        const profile = race.track_profile || {
            direction: "右回り (クロックワイズ)",
            shape: "標準オーバル",
            home_stretch_m: 350.0,
            slope_desc: "一般的な坂"
        };

        if (badgeTrackDir) badgeTrackDir.textContent = `回り: ${profile.direction}`;
        if (badgeTrackShape) badgeTrackShape.textContent = `コース: ${profile.shape}`;
        if (badgeTrackStretch) badgeTrackStretch.textContent = `直線: ${profile.home_stretch_m}m`;
        if (badgeTrackSlope) badgeTrackSlope.textContent = `勾配/坂: ${profile.slope_desc}`;

        if (btnStartSim) btnStartSim.disabled = false;
        if (btnResetSim) btnResetSim.disabled = false;

        drawTrackCanvas(race, 0);
    }

    function drawTrackCanvas(race, progress = 0) {
        if (!ctx || !canvas) return;
        const width = canvas.width;
        const height = canvas.height;

        ctx.clearRect(0, 0, width, height);

        const surface = race ? race.surface_type : "芝";
        const trackName = race ? race.track_name : "東京";
        const isObstacle = surface === "障害";
        const isDirt = surface === "ダート";

        // Environment Background
        ctx.fillStyle = isObstacle ? "#e3f2fd" : (isDirt ? "#efebe9" : "#f1f8e9");
        ctx.fillRect(0, 0, width, height);

        // Course Colors
        let outerColor = "#2e7d32";
        let innerColor = "#1b5e20";
        let dirtColor = "#8d6e63";

        if (isDirt) {
            outerColor = "#a1887f";
            innerColor = "#6d4c41";
        } else if (isObstacle) {
            outerColor = "#1565c0";
            innerColor = "#0d47a1";
        }

        // Outer Oval Track Geometry
        ctx.lineWidth = isObstacle ? 36 : 28;
        ctx.strokeStyle = outerColor;
        ctx.beginPath();
        ctx.roundRect(50, 40, width - 100, height - 90, [80]);
        ctx.stroke();

        // Inner Dirt / Sub Track Surface
        ctx.lineWidth = 14;
        ctx.strokeStyle = dirtColor;
        ctx.beginPath();
        ctx.roundRect(65, 55, width - 130, height - 120, [65]);
        ctx.stroke();

        // Finish Line
        const finishX = 220;
        const finishYTop = height - 85;

        ctx.lineWidth = 4;
        ctx.strokeStyle = "#d32f2f";
        ctx.beginPath();
        ctx.moveTo(finishX, finishYTop);
        ctx.lineTo(finishX, height - 20);
        ctx.stroke();

        ctx.fillStyle = "#d32f2f";
        ctx.font = "bold 12px sans-serif";
        ctx.fillText("FINISH", finishX - 20, finishYTop - 6);

        // Slope / Rise Indicator
        const profile = race ? race.track_profile : null;
        if (profile && profile.has_slope) {
            ctx.fillStyle = "#ff6f00";
            ctx.fillRect(280, height - 42, 120, 6);
            ctx.fillStyle = "#e65100";
            ctx.font = "bold 10px sans-serif";
            ctx.fillText("▲ 坂 (高低差 " + profile.max_slope_m + "m)", 285, height - 28);
        }

        // Steeplechase Jump Fences for Obstacle Races
        if (isObstacle) {
            const jumpPositions = [
                { x: 180, y: 40 },
                { x: 500, y: 40 },
                { x: 650, y: 170 },
                { x: 400, y: height - 50 }
            ];
            jumpPositions.forEach(j => {
                ctx.fillStyle = "#ff9800";
                ctx.fillRect(j.x - 12, j.y - 12, 24, 24);
                ctx.strokeStyle = "#bf360c";
                ctx.lineWidth = 2;
                ctx.strokeRect(j.x - 12, j.y - 12, 24, 24);
                ctx.fillStyle = "#ffffff";
                ctx.font = "bold 10px sans-serif";
                ctx.fillText("生垣", j.x - 10, j.y + 4);
            });
        }

        // Draw Horses moving along course oval path
        const horses = (simPredictions && simPredictions.length > 0)
            ? simPredictions
            : (race ? race.horses : []);

        const hCount = horses.length;
        if (hCount === 0) return;

        horses.forEach((h, idx) => {
            const speedFactor = h.win_probability ? (0.85 + h.win_probability * 0.5) : 1.0;
            const horseProgress = Math.min(1.0, progress * speedFactor);

            const pos = getOvalPathCoords(horseProgress, width, height, idx, hCount);

            const colors = ["#d32f2f", "#1976d2", "#388e3c", "#fbc02d", "#7b1fa2", "#e65100", "#00838f", "#4e342e"];
            const hColor = colors[idx % colors.length];

            ctx.fillStyle = hColor;
            ctx.beginPath();
            ctx.arc(pos.x, pos.y, 9, 0, Math.PI * 2);
            ctx.fill();
            ctx.lineWidth = 2;
            ctx.strokeStyle = "#ffffff";
            ctx.stroke();

            ctx.fillStyle = "#ffffff";
            ctx.font = "bold 10px sans-serif";
            ctx.textAlign = "center";
            ctx.textBaseline = "middle";
            ctx.fillText(h.horse_number, pos.x, pos.y);

            ctx.fillStyle = "#212121";
            ctx.font = "9px sans-serif";
            ctx.fillText(h.horse_name.substring(0, 5), pos.x, pos.y - 14);
        });
    }

    function getOvalPathCoords(t, width, height, laneIdx, totalLanes) {
        const rx = (width - 120) / 2;
        const ry = (height - 110) / 2;
        const cx = width / 2;
        const cy = height / 2;

        const laneOffset = (laneIdx - totalLanes / 2) * 3;
        const angle = Math.PI * 2 * (1.0 - t) + Math.PI / 2;

        const x = cx + (rx + laneOffset) * Math.cos(angle);
        const y = cy + (ry + laneOffset) * Math.sin(angle);

        return { x, y };
    }

    if (btnStartSim) {
        btnStartSim.addEventListener("click", () => {
            if (simRunning) return;
            simRunning = true;
            simProgress = 0;
            const startTime = Date.now();

            function animate() {
                if (!simRunning) return;
                simProgress += 0.0035;
                const elapsedSec = ((Date.now() - startTime) / 1000).toFixed(1);
                if (simLiveTime) simLiveTime.textContent = `${elapsedSec}秒`;

                drawTrackCanvas(currentRace, simProgress);

                if (simProgress >= 1.0) {
                    simRunning = false;
                    if (simLiveTime) simLiveTime.textContent = `${elapsedSec}秒 (GOAL!)`;
                } else {
                    simAnimId = requestAnimationFrame(animate);
                }
            }
            animate();
        });
    }

    if (btnResetSim) {
        btnResetSim.addEventListener("click", () => {
            simRunning = false;
            if (simAnimId) cancelAnimationFrame(simAnimId);
            simProgress = 0;
            if (simLiveTime) simLiveTime.textContent = "0.0秒";
            drawTrackCanvas(currentRace, 0);
        });
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
            tbodyPredictions.innerHTML = '<tr><td colspan="6" class="text-center py-4"><div class="spinner-border text-warning" role="status"></div><div class="mt-2 text-dark fw-bold">JRA公式最新レース・オッズを自動検出中...</div></td></tr>';

            try {
                const res = await fetch("/api/auto_fetch_jra", { method: "POST" });
                const result = await res.json();

                if (result.status === "success" && result.results && result.results.length > 0) {
                    const firstResult = result.results[0];
                    currentRace = firstResult.race;
                    displayRaceName.textContent = firstResult.race.race_name;
                    displayRaceMeta.textContent = `${firstResult.race.track_name}競馬場 | ${firstResult.race.surface_type}${firstResult.race.distance}m | 馬場: ${firstResult.race.track_condition} | 天候: ${firstResult.race.weather} (自動検出完了)`;
                    renderPredictions(firstResult.predictions);
                    renderRecommendations(firstResult.recommendations);

                    confidenceContainer.classList.remove("d-none");
                    displayConfidence.textContent = `${firstResult.recommendations.confidence_score}%`;
                    btnRecalculate.classList.remove("d-none");

                    await loadRaces(firstResult.race.race_id);
                    alert(`JRA最新レース・オッズの自動検出に成功しました！ (${result.results.length}件取り込み済み)`);
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

        tbodyPredictions.innerHTML = '<tr><td colspan="6" class="text-center py-4"><div class="spinner-border text-primary" role="status"></div><div class="mt-2 text-muted">JRA出馬表取り込み＆DB保存＆分析中...</div></td></tr>';

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
                renderRecommendations(result.recommendations);

                confidenceContainer.classList.remove("d-none");
                displayConfidence.textContent = `${result.recommendations.confidence_score}%`;
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

        tbodyPredictions.innerHTML = '<tr><td colspan="6" class="text-center py-4"><div class="spinner-border text-primary" role="status"></div><div class="mt-2 text-muted">AI 思考解析中...</div></td></tr>';

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
                renderRecommendations(result.recommendations);

                confidenceContainer.classList.remove("d-none");
                displayConfidence.textContent = `${result.recommendations.confidence_score}%`;
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

    function renderPredictions(predictions) {
        tbodyPredictions.innerHTML = "";
        predictions.forEach((p, index) => {
            const tr = document.createElement("tr");
            if (index === 0) tr.classList.add("rank-1");
            else if (index === 1) tr.classList.add("rank-2");
            else if (index === 2) tr.classList.add("rank-3");

            const winPercent = (p.win_probability * 100).toFixed(1);
            const placePercent = (p.place_probability * 100).toFixed(1);
            const evColor = p.win_ev >= 1.0 ? "bg-danger" : p.win_ev >= 0.85 ? "bg-warning text-dark" : "bg-secondary";

            tr.innerHTML = `
                <td class="text-center fw-bold fs-5">${p.horse_number}</td>
                <td>
                    <div class="fw-bold">${p.horse_name}</div>
                    <div class="text-muted small"><i class="fa-solid fa-user-tie me-1"></i>${p.jockey_name}</div>
                </td>
                <td class="text-center fw-bold text-primary">${p.odds} 倍</td>
                <td>
                    <div class="d-flex justify-content-between small mb-1">
                        <span>勝率</span>
                        <span class="fw-bold">${winPercent}%</span>
                    </div>
                    <div class="progress prob-bar">
                        <div class="progress-bar bg-success" style="width: ${winPercent}%"></div>
                    </div>
                </td>
                <td>
                    <div class="d-flex justify-content-between small mb-1">
                        <span>複勝率</span>
                        <span class="fw-bold">${placePercent}%</span>
                    </div>
                    <div class="progress prob-bar">
                        <div class="progress-bar bg-info" style="width: ${placePercent}%"></div>
                    </div>
                </td>
                <td class="text-center">
                    <span class="badge ${evColor} ev-badge fs-6">${p.win_ev}</span>
                </td>
            `;
            tbodyPredictions.appendChild(tr);
        });
    }

    function renderRecommendations(recs) {
        // Render Win Tickets
        const winContainer = document.getElementById("container-win-tickets");
        if (recs.win_tickets.length === 0) {
            winContainer.innerHTML = '<div class="text-muted small p-2">推奨単勝カードなし</div>';
        } else {
            winContainer.innerHTML = recs.win_tickets.map(t => `
                <div class="col-md-6">
                    <div class="card ticket-card p-3">
                        <div class="d-flex justify-content-between align-items-center mb-1">
                            <span class="badge bg-danger">${t.level}</span>
                            <span class="fw-bold text-success">期待値 ${t.ev}</span>
                        </div>
                        <h5 class="fw-bold mb-1">${t.horse_number}番 ${t.horse_name}</h5>
                        <div class="small text-muted">勝率: ${t.probability}% | オッズ: ${t.odds}倍</div>
                        <div class="mt-2 text-end text-primary fw-bold small">推奨資金配分: ${t.recommended_stake_percent}%</div>
                    </div>
                </div>
            `).join("");
        }

        // Render Place Tickets
        const placeContainer = document.getElementById("container-place-tickets");
        placeContainer.innerHTML = recs.place_tickets.map(t => `
            <div class="col-md-6">
                <div class="card ticket-card p-3">
                    <div class="d-flex justify-content-between align-items-center mb-1">
                        <span class="badge bg-info text-dark">${t.recommendation}</span>
                        <span class="fw-bold text-dark">複勝率 ${t.place_probability}%</span>
                    </div>
                    <h5 class="fw-bold mb-1">${t.horse_number}番 ${t.horse_name}</h5>
                    <div class="small text-muted">単勝オッズ: ${t.odds}倍</div>
                </div>
            </div>
        `).join("");

        // Render Exacta Tickets
        const exactaContainer = document.getElementById("container-exacta-tickets");
        exactaContainer.innerHTML = recs.exacta_tickets.map(t => `
            <div class="col-md-6">
                <div class="card ticket-card p-3">
                    <div class="d-flex justify-content-between align-items-center mb-1">
                        <span class="badge bg-dark">馬単 (1着-2着)</span>
                        <span class="fw-bold text-primary">想定オッズ ${t.estimated_odds}倍</span>
                    </div>
                    <h5 class="fw-bold mb-1">${t.combination} (${t.first_name} → ${t.second_name})</h5>
                    <div class="small text-muted">合成確率: ${t.joint_probability}% | 期待値: ${t.ev}</div>
                </div>
            </div>
        `).join("");

        // Render Trio Tickets
        const trioContainer = document.getElementById("container-trio-tickets");
        trioContainer.innerHTML = recs.trio_tickets.map(t => `
            <div class="col-md-6">
                <div class="card ticket-card p-3">
                    <div class="d-flex justify-content-between align-items-center mb-1">
                        <span class="badge bg-warning text-dark">3連複 (1軸流し)</span>
                        <span class="fw-bold text-success">想定オッズ ${t.estimated_odds}倍</span>
                    </div>
                    <h5 class="fw-bold mb-1">${t.combination}</h5>
                    <div class="small text-muted">軸: ${t.axis_name} / 相手: ${t.partner1_name}, ${t.partner2_name}</div>
                    <div class="small text-muted">合成確率: ${t.joint_probability}%</div>
                </div>
            </div>
        `).join("");
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

    // Retrain Model
    btnRetrain.addEventListener("click", async () => {
        btnRetrain.disabled = true;
        btnRetrain.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span> 学習中...';
        try {
            const res = await fetch("/api/train", { method: "POST" });
            const data = await res.json();
            alert(data.message);
            if (currentRace) runPrediction(currentRace);
        } catch (err) {
            alert("モデル再学習に失敗しました。");
        } finally {
            btnRetrain.disabled = false;
            btnRetrain.innerHTML = '<i class="fa-solid fa-arrows-rotate me-1"></i> AIモデル再学習';
        }
    });
});
