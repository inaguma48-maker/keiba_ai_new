document.addEventListener("DOMContentLoaded", () => {
    let currentRace = null;
    let simPredictions = [];
    let simAnimationFrame = null;
    let simIsRunning = false;
    let simProgress = 0; // 0.0 to 1.0
    let simRunners = [];
    let simSpeedMultiplier = 1.0;

    const CAP_COLORS = [
        { bg: "#ffffff", text: "#000000", border: "#cccccc" }, // 1: White
        { bg: "#222222", text: "#ffffff", border: "#000000" }, // 2: Black
        { bg: "#e63946", text: "#ffffff", border: "#b01825" }, // 3: Red
        { bg: "#1d3557", text: "#ffffff", border: "#0d1b2a" }, // 4: Blue
        { bg: "#ffb703", text: "#000000", border: "#d49200" }, // 5: Yellow
        { bg: "#2a9d8f", text: "#ffffff", border: "#186057" }, // 6: Green
        { bg: "#f4a261", text: "#000000", border: "#cc6f28" }, // 7: Orange
        { bg: "#ffb3c6", text: "#000000", border: "#d8708c" }  // 8: Pink
    ];

    const STYLES = ["逃げ", "先行", "差し", "追込"];

    function getCapColor(num) {
        return CAP_COLORS[(Math.max(1, num) - 1) % CAP_COLORS.length];
    }

    // DOM Elements
    const selectRace = document.getElementById("select-race");
    const btnLoadRace = document.getElementById("btn-load-race");
    const btnFetchWeekly = document.getElementById("btn-fetch-weekly");
    const btnFetchWeeklySide = document.getElementById("btn-fetch-weekly-side");
    const formImportJra = document.getElementById("form-import-jra");
    const btnRecalculate = document.getElementById("btn-recalculate");
    const btnRetrain = document.getElementById("btn-retrain");

    const displayRaceName = document.getElementById("display-race-name");
    const displayRaceMeta = document.getElementById("display-race-meta");
    const displayConfidence = document.getElementById("display-confidence");
    const tbodyPredictions = document.getElementById("tbody-predictions");

    const canvas = document.getElementById("race-canvas");
    const ctx = canvas ? canvas.getContext("2d") : null;

    const btnStartSim = document.getElementById("btn-start-sim");
    const btnResetSim = document.getElementById("btn-reset-sim");
    const btnSpeedSim = document.getElementById("btn-speed-sim");
    const simSpeedText = document.getElementById("sim-speed-text");
    const simRaceTitle = document.getElementById("sim-race-title");
    const simTimer = document.getElementById("sim-timer");
    const simLeaderName = document.getElementById("sim-leader-name");
    const simTop5Leaderboard = document.getElementById("sim-top5-leaderboard");
    const simRunningPhase = document.getElementById("sim-running-phase");
    const simCommentaryHeadline = document.getElementById("sim-commentary-headline");
    const simCommentarySub = document.getElementById("sim-commentary-sub");
    const simSkillPopup = document.getElementById("sim-skill-popup");
    const simSkillTitle = document.getElementById("sim-skill-title");
    const simSkillText = document.getElementById("sim-skill-text");
    const topProgressFill = document.getElementById("top-progress-fill");
    const topHorsesTrack = document.getElementById("top-horses-track");

    // Speed Multiplier Switcher
    if (btnSpeedSim) {
        btnSpeedSim.addEventListener("click", () => {
            if (simSpeedMultiplier === 1.0) simSpeedMultiplier = 2.0;
            else if (simSpeedMultiplier === 2.0) simSpeedMultiplier = 3.0;
            else simSpeedMultiplier = 1.0;
            if (simSpeedText) simSpeedText.textContent = `${simSpeedMultiplier.toFixed(1)}x`;
        });
    }

    // Initialize Simulation Engine
    function initSimulation(race, predictions) {
        if (!canvas || !ctx) return;
        currentRace = race;
        simPredictions = predictions || [];

        if (simRaceTitle && race) {
            simRaceTitle.textContent = `${race.race_name} (${race.track_name} ${race.surface_type}${race.distance}m)`;
        }

        simProgress = 0;
        simIsRunning = false;
        if (simAnimationFrame) {
            cancelAnimationFrame(simAnimationFrame);
            simAnimationFrame = null;
        }

        if (btnStartSim) {
            btnStartSim.innerHTML = '<i class="fa-solid fa-play me-1"></i> スタート';
            btnStartSim.classList.replace("btn-danger", "btn-warning");
            btnStartSim.classList.replace("text-white", "text-dark");
        }

        simRunners = simPredictions.map((p, idx) => {
            const baseProb = p.win_probability || (0.15 - idx * 0.01);
            const odds = p.odds || 5.0;
            const speedRating = (1 / odds) * 50 + (baseProb * 80);

            return {
                horse_number: p.horse_number,
                horse_name: p.horse_name,
                jockey_name: p.jockey_name,
                running_style: STYLES[idx % STYLES.length],
                win_probability: baseProb,
                speedRating: speedRating,
                currentDist: 0,
                xPos: 50,
                yPos: 120 + (idx % 6) * 35,
                laneOffset: (idx % 5) * 16 - 32,
                color: getCapColor(p.horse_number),
                rank: idx + 1,
                hasTriggeredSkill: false
            };
        });

        updateSimulationUI();
        drawCanvasTrack();
    }

    // Draw 3D-Perspective Canvas Track and Sprites
    function drawCanvasTrack() {
        if (!ctx || !canvas) return;

        // Background Turf Green
        ctx.fillStyle = "#5b824b";
        ctx.fillRect(0, 0, canvas.width, canvas.height);

        // Rail Posts & Fence
        ctx.save();
        ctx.beginPath();
        ctx.moveTo(0, 100);
        ctx.bezierCurveTo(280, 100, 520, 150, 800, 160);
        ctx.lineWidth = 10;
        ctx.strokeStyle = "#ffffff";
        ctx.stroke();

        for (let x = 20; x <= 800; x += 40) {
            const y = 100 + (x / 800) * 60;
            ctx.fillStyle = "#ffffff";
            ctx.fillRect(x - 2, y - 14, 4, 18);
        }
        ctx.restore();

        // Main Track Path Gradient
        const trackGrad = ctx.createLinearGradient(0, 120, 0, 380);
        trackGrad.addColorStop(0, "#6a9458");
        trackGrad.addColorStop(1, "#4b6e3a");
        ctx.fillStyle = trackGrad;
        ctx.beginPath();
        ctx.moveTo(0, 110);
        ctx.bezierCurveTo(280, 110, 520, 160, 800, 170);
        ctx.lineTo(800, 400);
        ctx.lineTo(0, 400);
        ctx.fill();

        // Finish Goal Line Gate
        if (simProgress > 0.82) {
            ctx.save();
            ctx.fillStyle = "#ff3333";
            ctx.fillRect(680, 140, 6, 240);
            ctx.fillStyle = "#ffffff";
            ctx.font = "bold 14px sans-serif";
            ctx.fillText("🏁 GOAL", 655, 130);
            ctx.restore();
        }

        // Draw Runners
        if (simRunners.length > 0) {
            const sorted = [...simRunners].sort((a, b) => a.yPos - b.yPos);

            sorted.forEach(runner => {
                const relProgress = Math.max(0, Math.min(1.0, (runner.currentDist - simProgress * 0.85) / 0.2 + 0.3));
                const rx = 60 + relProgress * 660;
                const ry = 170 + runner.laneOffset + (relProgress * 55);

                runner.xPos = rx;
                runner.yPos = ry;

                ctx.save();

                // Shadow
                ctx.fillStyle = "rgba(0, 0, 0, 0.3)";
                ctx.beginPath();
                ctx.ellipse(rx, ry + 10, 16, 6, 0, 0, Math.PI * 2);
                ctx.fill();

                // Anime Head / Hair
                ctx.fillStyle = "#4a2c11";
                ctx.beginPath();
                ctx.arc(rx, ry - 12, 10, 0, Math.PI * 2);
                ctx.fill();

                // Cap / Helmet
                ctx.fillStyle = runner.color.bg;
                ctx.beginPath();
                ctx.arc(rx, ry - 18, 8, 0, Math.PI * 2);
                ctx.fill();
                ctx.lineWidth = 1;
                ctx.strokeStyle = "#ffffff";
                ctx.stroke();

                // Horse Number
                ctx.fillStyle = runner.color.text;
                ctx.font = "bold 9px sans-serif";
                ctx.textAlign = "center";
                ctx.textBaseline = "middle";
                ctx.fillText(runner.horse_number, rx, ry - 17.5);

                // Lead Horse Marker
                if (runner.rank === 1) {
                    ctx.fillStyle = "#ffea00";
                    ctx.beginPath();
                    ctx.moveTo(rx, ry - 30);
                    ctx.lineTo(rx - 6, ry - 40);
                    ctx.lineTo(rx + 6, ry - 40);
                    ctx.closePath();
                    ctx.fill();
                }

                ctx.restore();
            });
        }
    }

    // Update Simulation UI
    function updateSimulationUI() {
        if (simRunners.length === 0) return;

        simRunners.sort((a, b) => b.currentDist - a.currentDist);
        simRunners.forEach((r, idx) => r.rank = idx + 1);

        const leader = simRunners[0];
        const second = simRunners[1];

        // Top 5 Leaderboard
        if (simTop5Leaderboard) {
            const top5 = simRunners.slice(0, 5);
            simTop5Leaderboard.innerHTML = top5.map((r, idx) => {
                const gapText = idx === 0 ? "先頭" : `${((leader.currentDist - r.currentDist) * 100).toFixed(1)}m`;
                return `
                    <div class="d-flex align-items-center justify-content-between fs-8">
                        <div class="d-flex align-items-center gap-1">
                            <span class="badge ${idx === 0 ? "bg-warning text-dark" : "bg-dark text-white"}" style="width:16px; height:16px; padding:2px 0; text-center;">${idx + 1}</span>
                            <span class="badge" style="background:${r.color.bg}; color:${r.color.text}; font-size:8px;">${r.horse_number}</span>
                            <span class="text-truncate text-white fw-bold" style="max-width: 70px;">${r.horse_name}</span>
                        </div>
                        <span class="text-warning-emphasis fs-8 opacity-75">${gapText}</span>
                    </div>
                `;
            }).join("");
        }

        const elapsedSec = (simProgress * 100 * 0.95).toFixed(1);
        if (simTimer) {
            const min = Math.floor(elapsedSec / 60).toString().padStart(2, "0");
            const sec = (elapsedSec % 60).toFixed(1).padStart(4, "0");
            simTimer.textContent = `${min}:${sec}`;
        }

        if (simLeaderName && leader) {
            simLeaderName.textContent = `先頭: ${leader.horse_number}番 ${leader.horse_name}`;
        }

        if (topProgressFill) topProgressFill.style.width = `${(simProgress * 100).toFixed(1)}%`;

        if (topHorsesTrack) {
            topHorsesTrack.innerHTML = simRunners.map(r => `
                <span class="position-absolute translate-middle" style="left: ${(r.currentDist * 100).toFixed(1)}%; top: -5px;">
                    <span class="badge rounded-circle p-1 text-center" style="background:${r.color.bg}; color:${r.color.text}; font-size: 7px; width:14px; height:14px; border:1px solid #fff; line-height:8px;">
                        ${r.horse_number}
                    </span>
                </span>
            `).join("");
        }

        // Commentary
        if (simProgress < 0.1) {
            if (simRunningPhase) simRunningPhase.textContent = "スタート";
            if (simCommentaryHeadline) simCommentaryHeadline.textContent = `全馬一斉に綺麗にスタート！`;
            if (simCommentarySub) simCommentarySub.textContent = `好スタートを切ったのは${leader.horse_number}番 ${leader.horse_name}！`;
        } else if (simProgress < 0.4) {
            if (simRunningPhase) simRunningPhase.textContent = "向正面";
            if (simCommentaryHeadline) simCommentaryHeadline.textContent = `先頭集団がレースを引っ張る！`;
            if (simCommentarySub) simCommentarySub.textContent = `2番手に${second ? second.horse_name : "後続"}がピタリとつける！`;
        } else if (simProgress < 0.75) {
            if (simRunningPhase) simRunningPhase.textContent = "第3~4コーナー";
            if (simCommentaryHeadline) simCommentaryHeadline.textContent = `【第3〜4コーナー】各馬位置取りを激しく争う！`;
            if (simCommentarySub) simCommentarySub.textContent = `手応え十分に最終コーナーを回ってくる！`;

            if (!leader.hasTriggeredSkill && simSkillPopup) {
                leader.hasTriggeredSkill = true;
                if (simSkillTitle) simSkillTitle.textContent = `【固有スキル発動】${leader.horse_name}`;
                if (simSkillText) simSkillText.textContent = `【脚質: ${leader.running_style}】スパートスパート！`;
                simSkillPopup.classList.remove("d-none");
                setTimeout(() => simSkillPopup.classList.add("d-none"), 2500);
            }
        } else if (simProgress < 0.99) {
            if (simRunningPhase) simRunningPhase.textContent = "直線たたき合い";
            if (simCommentaryHeadline) simCommentaryHeadline.textContent = `【最後の直線！】叩き合い！ラストスパート！`;
            if (simCommentarySub) simCommentarySub.textContent = `${leader.horse_name}が粘る！残り200m！`;
        } else {
            if (simRunningPhase) simRunningPhase.textContent = "ゴールイン";
            if (simCommentaryHeadline) simCommentaryHeadline.textContent = `【ゴールイン！】圧巻の勝負を見せた！`;
            if (simCommentarySub) simCommentarySub.textContent = `栄光の1着は${leader.horse_number}番 ${leader.horse_name}！`;
        }
    }

    // Animation Loop
    function animateRace() {
        if (!simIsRunning) return;

        const delta = 0.0025 * simSpeedMultiplier;
        simProgress += delta;

        simRunners.forEach(r => {
            const staminaFactor = 1.0 + (r.speedRating / 100.0) * 0.12;
            const variance = (Math.random() - 0.48) * 0.0008;
            r.currentDist = Math.min(1.0, r.currentDist + delta * staminaFactor + variance);
        });

        updateSimulationUI();
        drawCanvasTrack();

        if (simProgress >= 1.0) {
            simIsRunning = false;
            simProgress = 1.0;
            if (btnStartSim) {
                btnStartSim.innerHTML = '<i class="fa-solid fa-rotate-right me-1"></i> もう一度再生';
                btnStartSim.classList.replace("btn-danger", "btn-warning");
            }
            return;
        }

        simAnimationFrame = requestAnimationFrame(animateRace);
    }

    // Toggle Play/Pause Simulation
    if (btnStartSim) {
        btnStartSim.addEventListener("click", () => {
            if (simProgress >= 1.0) {
                simProgress = 0;
                simRunners.forEach(r => r.currentDist = 0);
            }

            simIsRunning = !simIsRunning;

            if (simIsRunning) {
                btnStartSim.innerHTML = '<i class="fa-solid fa-pause me-1"></i> 一時停止';
                btnStartSim.classList.replace("btn-warning", "btn-danger");
                btnStartSim.classList.replace("text-dark", "text-white");
                animateRace();
            } else {
                btnStartSim.innerHTML = '<i class="fa-solid fa-play me-1"></i> 再開';
                btnStartSim.classList.replace("btn-danger", "btn-warning");
                btnStartSim.classList.replace("text-white", "text-dark");
                if (simAnimationFrame) cancelAnimationFrame(simAnimationFrame);
            }
        });
    }

    if (btnResetSim) {
        btnResetSim.addEventListener("click", () => {
            if (currentRace) {
                initSimulation(currentRace, simPredictions);
            }
        });
    }

    // Load available races into select dropdown
    async function loadRaces(selectedId = null) {
        try {
            const res = await fetch("/api/races");
            const data = await res.json();
            if (data.status === "success" && data.races) {
                selectRace.innerHTML = '<option value="">-- 保存・サンプルレースを選択 --</option>';
                data.races.forEach(r => {
                    const opt = document.createElement("option");
                    opt.value = r.race_id;
                    opt.textContent = `[JRA] ${r.race_name} (${r.track_name} ${r.surface_type}${r.distance}m / ${r.horse_count}頭)`;
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

    // Load selected race
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

    // One-Click Weekly JRA Data Auto Import Handler
    async function handleFetchWeeklyJra() {
        const originalText = btnFetchWeekly ? btnFetchWeekly.innerHTML : "";
        if (btnFetchWeekly) {
            btnFetchWeekly.disabled = true;
            btnFetchWeekly.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span> JRA公式から今週の出馬表を一括取得・AI全予想計算中...';
        }
        if (btnFetchWeeklySide) {
            btnFetchWeeklySide.disabled = true;
            btnFetchWeeklySide.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span> 取得中...';
        }

        tbodyPredictions.innerHTML = '<tr><td colspan="6" class="text-center py-4"><div class="spinner-border text-warning" role="status"></div><div class="mt-2 text-warning fw-bold">JRAホームページから今週のレース出馬表を取得・データベース保存・AI全予想計算中...</div></td></tr>';

        try {
            const res = await fetch("/api/import_weekly_jra", { method: "POST" });
            const data = await res.json();

            if (data.status === "success" && data.results && data.results.length > 0) {
                // Refresh dropdown and select the first race
                await loadRaces(data.results[0].race.race_id);

                const firstResult = data.results[0];
                currentRace = firstResult.race;

                displayRaceName.textContent = firstResult.race.race_name;
                displayRaceMeta.textContent = `${firstResult.race.track_name}競馬場 | ${firstResult.race.surface_type}${firstResult.race.distance}m | 馬場: ${firstResult.race.track_condition} | 天候: ${firstResult.race.weather} (JRA一括取得完了: ${data.count}レース)`;

                renderPredictions(firstResult.predictions);
                renderRecommendations(firstResult.recommendations);
                displayConfidence.textContent = `${firstResult.recommendations.confidence_score}%`;

                // Initialize Simulation
                initSimulation(firstResult.race, firstResult.predictions);

                alert(`【成功】今週の全JRA出馬表 (${data.count}レース) を一括取得しました！\nドロップダウンから各レースを自由に切り替え可能です。`);
            } else {
                alert("今週のJRAデータ取得エラー: " + (data.message || "データが見つかりませんでした。"));
            }
        } catch (err) {
            console.error("Failed to fetch weekly JRA races:", err);
            alert("通信エラーにより今週のJRAデータ取得に失敗しました。");
        } finally {
            if (btnFetchWeekly) {
                btnFetchWeekly.disabled = false;
                btnFetchWeekly.innerHTML = originalText;
            }
            if (btnFetchWeeklySide) {
                btnFetchWeeklySide.disabled = false;
                btnFetchWeeklySide.innerHTML = '<i class="fa-solid fa-sync me-1"></i> 今週のJRA全レースを再取得';
            }
        }
    }

    if (btnFetchWeekly) btnFetchWeekly.addEventListener("click", handleFetchWeeklyJra);
    if (btnFetchWeeklySide) btnFetchWeeklySide.addEventListener("click", handleFetchWeeklyJra);

    // Individual JRA Import Form
    formImportJra.addEventListener("submit", async (e) => {
        e.preventDefault();
        const urlInput = document.getElementById("input-jra-url").value.trim();
        const textInput = document.getElementById("input-jra-text").value.trim();

        if (!urlInput && !textInput) {
            alert("URL または 出馬表テキストを入力してください。");
            return;
        }

        tbodyPredictions.innerHTML = '<tr><td colspan="6" class="text-center py-4"><div class="spinner-border text-primary" role="status"></div><div class="mt-2 text-muted">JRA出馬表取り込み＆分析中...</div></td></tr>';

        try {
            const res = await fetch("/api/import_jra", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ url: urlInput || null, text_content: textInput || null })
            });
            const result = await res.json();

            if (result.status === "success") {
                currentRace = result.race;
                displayRaceName.textContent = result.race.race_name;
                displayRaceMeta.textContent = `${result.race.track_name}競馬場 | ${result.race.surface_type}${result.race.distance}m | 馬場: ${result.race.track_condition}`;

                renderPredictions(result.predictions);
                renderRecommendations(result.recommendations);
                displayConfidence.textContent = `${result.recommendations.confidence_score}%`;

                initSimulation(result.race, result.predictions);
                await loadRaces(result.race.race_id);
            } else {
                alert("JRA取り込みエラー: " + result.message);
            }
        } catch (err) {
            alert("取り込み通信に失敗しました。");
        }
    });

    async function runPrediction(raceData) {
        displayRaceName.textContent = raceData.race_name;
        displayRaceMeta.textContent = `${raceData.track_name}競馬場 | ${raceData.surface_type}${raceData.distance}m | 馬場: ${raceData.track_condition} | 天候: ${raceData.weather}`;

        tbodyPredictions.innerHTML = '<tr><td colspan="6" class="text-center py-4"><div class="spinner-border text-warning" role="status"></div><div class="mt-2 text-warning">AI 思考解析中...</div></td></tr>';

        try {
            const res = await fetch("/api/predict", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(raceData)
            });
            const result = await res.json();

            if (result.status === "success") {
                renderPredictions(result.predictions);
                renderRecommendations(result.recommendations);
                displayConfidence.textContent = `${result.recommendations.confidence_score}%`;

                initSimulation(raceData, result.predictions);
                await loadRaces(raceData.race_id);
            } else {
                alert("予想の実行に失敗しました: " + result.message);
            }
        } catch (err) {
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
                <td class="text-center fw-bold fs-6">${p.horse_number}</td>
                <td>
                    <div class="fw-bold text-white">${p.horse_name}</div>
                    <div class="text-white-50 fs-8"><i class="fa-solid fa-user-tie me-1"></i>${p.jockey_name}</div>
                </td>
                <td class="text-center fw-bold text-warning">${p.odds} 倍</td>
                <td>
                    <div class="d-flex justify-content-between small mb-1">
                        <span class="fs-8">勝率</span>
                        <span class="fw-bold fs-8">${winPercent}%</span>
                    </div>
                    <div class="progress prob-bar">
                        <div class="progress-bar bg-success" style="width: ${winPercent}%"></div>
                    </div>
                </td>
                <td>
                    <div class="d-flex justify-content-between small mb-1">
                        <span class="fs-8">複勝率</span>
                        <span class="fw-bold fs-8">${placePercent}%</span>
                    </div>
                    <div class="progress prob-bar">
                        <div class="progress-bar bg-info" style="width: ${placePercent}%"></div>
                    </div>
                </td>
                <td class="text-center">
                    <span class="badge ${evColor} fs-7">${p.win_ev}</span>
                </td>
            `;
            tbodyPredictions.appendChild(tr);
        });
    }

    function renderRecommendations(recs) {
        const winContainer = document.getElementById("container-win-tickets");
        if (!recs.win_tickets || recs.win_tickets.length === 0) {
            winContainer.innerHTML = '<div class="text-white-50 small p-2">推奨単勝カードなし</div>';
        } else {
            winContainer.innerHTML = recs.win_tickets.map(t => `
                <div class="col-md-6">
                    <div class="ticket-card p-3">
                        <div class="d-flex justify-content-between align-items-center mb-1">
                            <span class="badge bg-danger">${t.level}</span>
                            <span class="fw-bold text-warning fs-7">期待値 ${t.ev}</span>
                        </div>
                        <h6 class="fw-bold mb-1 text-white">${t.horse_number}番 ${t.horse_name}</h6>
                        <div class="fs-8 text-white-50">勝率: ${t.probability}% | オッズ: ${t.odds}倍</div>
                        <div class="mt-1 text-end text-info fw-bold fs-8">推奨資金配分: ${t.recommended_stake_percent}%</div>
                    </div>
                </div>
            `).join("");
        }

        const placeContainer = document.getElementById("container-place-tickets");
        if (placeContainer && recs.place_tickets) {
            placeContainer.innerHTML = recs.place_tickets.map(t => `
                <div class="col-md-6">
                    <div class="ticket-card p-3">
                        <div class="d-flex justify-content-between align-items-center mb-1">
                            <span class="badge bg-info text-dark">${t.recommendation}</span>
                            <span class="fw-bold text-white fs-7">複勝率 ${t.place_probability}%</span>
                        </div>
                        <h6 class="fw-bold mb-1 text-white">${t.horse_number}番 ${t.horse_name}</h6>
                        <div class="fs-8 text-white-50">単勝オッズ: ${t.odds}倍</div>
                    </div>
                </div>
            `).join("");
        }

        const exactaContainer = document.getElementById("container-exacta-tickets");
        if (exactaContainer && recs.exacta_tickets) {
            exactaContainer.innerHTML = recs.exacta_tickets.map(t => `
                <div class="col-md-6">
                    <div class="ticket-card p-3">
                        <div class="d-flex justify-content-between align-items-center mb-1">
                            <span class="badge bg-dark border border-secondary">馬単 (1着-2着)</span>
                            <span class="fw-bold text-warning fs-7">想定 ${t.estimated_odds}倍</span>
                        </div>
                        <h6 class="fw-bold mb-1 text-white">${t.combination} (${t.first_name} → ${t.second_name})</h6>
                        <div class="fs-8 text-white-50">合成確率: ${t.joint_probability}% | 期待値: ${t.ev}</div>
                    </div>
                </div>
            `).join("");
        }

        const trioContainer = document.getElementById("container-trio-tickets");
        if (trioContainer && recs.trio_tickets) {
            trioContainer.innerHTML = recs.trio_tickets.map(t => `
                <div class="col-md-6">
                    <div class="ticket-card p-3">
                        <div class="d-flex justify-content-between align-items-center mb-1">
                            <span class="badge bg-warning text-dark">3連複 (1軸流し)</span>
                            <span class="fw-bold text-success fs-7">想定 ${t.estimated_odds}倍</span>
                        </div>
                        <h6 class="fw-bold mb-1 text-white">${t.combination}</h6>
                        <div class="fs-8 text-white-50">軸: ${t.axis_name} / 相手: ${t.partner1_name}, ${t.partner2_name}</div>
                    </div>
                </div>
            `).join("");
        }
    }

    // Retrain Model
    if (btnRetrain) {
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
    }

    // Initial load
    loadRaces();
});
