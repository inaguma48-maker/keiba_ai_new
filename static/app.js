document.addEventListener("DOMContentLoaded", () => {
    let currentRace = null;
    let simPredictions = [];
    let simAnimationFrame = null;
    let simIsRunning = false;
    let simProgress = 0; // 0 to 100%
    let simRunners = [];

    const selectRace = document.getElementById("select-race");
    const canvas = document.getElementById("race-canvas");
    const ctx = canvas ? canvas.getContext("2d") : null;
    const btnStartSim = document.getElementById("btn-start-sim");
    const btnResetSim = document.getElementById("btn-reset-sim");
    const simTimer = document.getElementById("sim-timer");
    const simLeaderName = document.getElementById("sim-leader-name");
    const simCommentary = document.getElementById("sim-commentary");
    const simTimeBadge = document.getElementById("sim-time-badge");
    const simRaceTitle = document.getElementById("sim-race-title");

    // Standard JRA Helmet / Cap Colors by Waku / Horse Number
    const CAP_COLORS = [
        { bg: "#ffffff", text: "#000000" }, // 1: White
        { bg: "#222222", text: "#ffffff" }, // 2: Black
        { bg: "#e63946", text: "#ffffff" }, // 3: Red
        { bg: "#1d3557", text: "#ffffff" }, // 4: Blue
        { bg: "#ffb703", text: "#000000" }, // 5: Yellow
        { bg: "#2a9d8f", text: "#ffffff" }, // 6: Green
        { bg: "#f4a261", text: "#000000" }, // 7: Orange
        { bg: "#ffb3c6", text: "#000000" }  // 8: Pink
    ];

    function getCapColor(num) {
        const idx = (Math.max(1, num) - 1) % CAP_COLORS.length;
        return CAP_COLORS[idx];
    }

    // Initialize TV Race Simulation State
    function initRaceSimulation(race, predictions) {
        if (!canvas || !ctx) return;
        currentRace = race;
        simPredictions = predictions || [];

        if (simRaceTitle && race) {
            simRaceTitle.innerHTML = `<i class="fa-solid fa-tv me-2 text-warning"></i>${race.race_name} (${race.track_name} ${race.surface_type}${race.distance}m)`;
        }

        simProgress = 0;
        simIsRunning = false;
        if (simAnimationFrame) {
            cancelAnimationFrame(simAnimationFrame);
            simAnimationFrame = null;
        }

        if (btnStartSim) {
            btnStartSim.innerHTML = '<i class="fa-solid fa-play me-1"></i> 実況中継スタート';
            btnStartSim.classList.replace("btn-danger", "btn-warning");
            btnStartSim.classList.replace("text-white", "text-dark");
        }

        // Build Runners from predictions or horses
        simRunners = simPredictions.map((p, idx) => {
            const baseProb = p.win_probability || (0.15 - idx * 0.01);
            const odds = p.odds || 5.0;
            const speedRating = (1 / odds) * 50 + (baseProb * 80);

            return {
                horse_number: p.horse_number,
                horse_name: p.horse_name,
                jockey_name: p.jockey_name,
                win_probability: baseProb,
                speedRating: speedRating,
                currentDist: 0,
                laneOffset: (idx % 4) * 6 - 9, // staggered track lanes
                color: getCapColor(p.horse_number),
                rank: idx + 1
            };
        });

        updateSimulationUI();
        drawRaceTrack();
        if (simCommentary) {
            simCommentary.textContent = `出走準備完了！「実況中継スタート」を押すとAIライブ熱血実況が始まります！`;
        }
    }

    // Convert 0..1 distance progress along oval track to Canvas (x, y) coordinates
    function getTrackPos(progress, laneOffset) {
        // Oval Dimensions
        const cx = 380, cy = 160;
        const rx = 240 + laneOffset; // horizontal radius
        const ry = 90 + laneOffset;  // vertical radius

        // Counter-clockwise race oval movement starting from bottom right (Start Gate)
        // startAngle = 0 (bottom right home stretch) -> theta from 0 to 2*PI
        const angle = progress * Math.PI * 2;

        const x = cx + rx * Math.cos(angle - Math.PI / 2);
        const y = cy + ry * Math.sin(angle - Math.PI / 2);

        return { x, y, angle };
    }

    // Draw Realistic 2D Race Track
    function drawRaceTrack() {
        if (!ctx) return;

        // Background
        ctx.fillStyle = "#121824";
        ctx.fillRect(0, 0, canvas.width, canvas.height);

        // Turf Track Outer Oval
        ctx.fillStyle = "#1e4d2b";
        ctx.beginPath();
        ctx.ellipse(380, 160, 275, 125, 0, 0, Math.PI * 2);
        ctx.fill();

        // Dirt Track Inner Oval Surface
        ctx.fillStyle = "#705335";
        ctx.beginPath();
        ctx.ellipse(380, 160, 255, 105, 0, 0, Math.PI * 2);
        ctx.fill();

        // Inner Turf Field Center
        ctx.fillStyle = "#0e2e17";
        ctx.beginPath();
        ctx.ellipse(380, 160, 185, 55, 0, 0, Math.PI * 2);
        ctx.fill();

        // Rails (Inner & Outer White Lines)
        ctx.strokeStyle = "#ffffff";
        ctx.lineWidth = 3;
        ctx.beginPath();
        ctx.ellipse(380, 160, 260, 110, 0, 0, Math.PI * 2);
        ctx.stroke();

        ctx.strokeStyle = "#405d47";
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.ellipse(380, 160, 190, 60, 0, 0, Math.PI * 2);
        ctx.stroke();

        // Finish Line Checkered Strip (Top Straight / Finishing Stretch)
        ctx.save();
        ctx.strokeStyle = "#ff4d4d";
        ctx.lineWidth = 4;
        ctx.beginPath();
        ctx.moveTo(380, 50);
        ctx.lineTo(380, 100);
        ctx.stroke();

        ctx.fillStyle = "#ffffff";
        ctx.font = "bold 11px sans-serif";
        ctx.fillText("🏁 FINISH", 350, 42);
        ctx.restore();

        // Start Gate Marker
        const startPos = getTrackPos(0, 0);
        ctx.save();
        ctx.strokeStyle = "#ffc107";
        ctx.lineWidth = 4;
        ctx.strokeRect(startPos.x - 12, startPos.y - 18, 24, 36);
        ctx.fillStyle = "#ffc107";
        ctx.font = "bold 10px sans-serif";
        ctx.fillText("START ゲート", startPos.x - 28, startPos.y + 32);
        ctx.restore();

        // Draw Slope / Feature Callout
        ctx.fillStyle = "rgba(255, 255, 255, 0.15)";
        ctx.fillRect(250, 270, 260, 18);
        ctx.fillStyle = "#e0e0e0";
        ctx.font = "10px sans-serif";
        ctx.fillText("▲ 直線急坂 (勾配 2.0m)", 310, 283);

        // Draw Horses
        if (simRunners.length > 0) {
            // Sort by current distance so trailing horses are drawn first, leaders drawn on top
            const sorted = [...simRunners].sort((a, b) => a.currentDist - b.currentDist);

            sorted.forEach(runner => {
                const pos = getTrackPos(runner.currentDist, runner.laneOffset);

                // Draw Horse Badge / Helmet Circle
                ctx.save();

                // Shadow
                ctx.fillStyle = "rgba(0, 0, 0, 0.4)";
                ctx.beginPath();
                ctx.arc(pos.x + 2, pos.y + 3, 11, 0, Math.PI * 2);
                ctx.fill();

                // Helmet Circle
                ctx.fillStyle = runner.color.bg;
                ctx.beginPath();
                ctx.arc(pos.x, pos.y, 11, 0, Math.PI * 2);
                ctx.fill();
                ctx.lineWidth = 2;
                ctx.strokeStyle = "#ffffff";
                ctx.stroke();

                // Horse Number Text
                ctx.fillStyle = runner.color.text;
                ctx.font = "bold 11px sans-serif";
                ctx.textAlign = "center";
                ctx.textBaseline = "middle";
                ctx.fillText(runner.horse_number, pos.x, pos.y + 0.5);

                // Lead Horse Banner Overlay
                if (runner.rank === 1) {
                    ctx.fillStyle = "#ffc107";
                    ctx.fillRect(pos.x - 28, pos.y - 28, 56, 14);
                    ctx.fillStyle = "#000000";
                    ctx.font = "bold 9px sans-serif";
                    ctx.fillText(runner.horse_name.substring(0, 5), pos.x, pos.y - 21);
                }

                ctx.restore();
            });
        }
    }

    // Play-by-Play TV Broadcast Commentary Logic
    function updateCommentary(leader, progress, elapsedSec) {
        if (!simCommentary || !leader) return;

        let line = "";
        if (progress < 0.05) {
            line = `【スタート！】全馬一斉にゲートが開きました！綺麗にスタートを切りました！`;
        } else if (progress < 0.25) {
            line = `【第1〜2コーナー】先頭に立ったのは${leader.horse_number}番 ${leader.horse_name}！好スタートからレースを引っぱります！`;
        } else if (progress < 0.55) {
            line = `【向正面】ペースは順調！${leader.horse_number}番 ${leader.horse_name}が1馬身リード！後続もじわじわと位置を上げてくる！`;
        } else if (progress < 0.80) {
            line = `【第3〜4コーナー】さあ各馬スパート開始！${leader.horse_number}番 ${leader.horse_name}が先頭をキープして最後の直線へ向かいます！`;
        } else if (progress < 0.95) {
            const second = simRunners.find(r => r.rank === 2);
            const secondText = second ? `外から${second.horse_number}番 ${second.horse_name}が猛追！` : "";
            line = `【最後の直線！】激しい叩き合い！${leader.horse_name}が粘る！${secondText}残り200m！`;
        } else {
            line = `【ゴールイン！】勝ったのは${leader.horse_number}番 ${leader.horse_name}！AIの緻密な予想通りの圧倒的な走りで見事に勝利を収めました！`;
        }

        if (simCommentary.textContent !== line) {
            simCommentary.textContent = line;
            speakText(line);
        }
    }

    // Optional Web Speech API TTS for TV Broadcast feel
    let lastSpokenText = "";
    function speakText(text) {
        if (!('speechSynthesis' in window) || text === lastSpokenText) return;
        try {
            window.speechSynthesis.cancel(); // stop ongoing speech
            const cleanText = text.replace(/【.*?】/g, "");
            const utterance = new SpeechSynthesisUtterance(cleanText);
            utterance.lang = "ja-JP";
            utterance.rate = 1.2; // lively Japanese commentary pace
            utterance.pitch = 1.1;
            lastSpokenText = text;
            window.speechSynthesis.speak(utterance);
        } catch (e) {
            // ignore speech errors gracefully
        }
    }

    // Update Simulation Time & Leaderboard Overlay
    function updateSimulationUI() {
        if (simRunners.length === 0) return;

        // Sort runners by current progress
        simRunners.sort((a, b) => b.currentDist - a.currentDist);
        simRunners.forEach((r, idx) => r.rank = idx + 1);

        const leader = simRunners[0];
        const elapsedSec = (simProgress * 100 * 0.95).toFixed(1);

        if (simTimer) {
            const min = Math.floor(elapsedSec / 60).toString().padStart(2, "0");
            const sec = (elapsedSec % 60).toFixed(1).padStart(4, "0");
            simTimer.textContent = `${min}:${sec}`;
        }

        if (simLeaderName && leader) {
            simLeaderName.textContent = `先頭: ${leader.horse_number}番 ${leader.horse_name}`;
        }

        if (simTimeBadge) {
            simTimeBadge.textContent = `${elapsedSec}秒`;
        }

        updateCommentary(leader, simProgress, elapsedSec);
    }

    // Main Animation Loop
    function animateRace() {
        if (!simIsRunning) return;

        simProgress += 0.0025; // Speed factor (~12-15 seconds full race)

        // Update each runner according to their speed & small random variance
        simRunners.forEach((runner, idx) => {
            const staminaFactor = 1.0 + (runner.speedRating / 100.0) * 0.15;
            const variance = (Math.random() - 0.48) * 0.0008;
            runner.currentDist = Math.min(1.0, runner.currentDist + 0.0025 * staminaFactor + variance);
        });

        updateSimulationUI();
        drawRaceTrack();

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

    // Start / Pause Simulation Toggle
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

    // Reset Simulation
    if (btnResetSim) {
        btnResetSim.addEventListener("click", () => {
            if (currentRace) {
                initRaceSimulation(currentRace, simPredictions);
            }
        });
    }

    // Handle one-click weekly JRA data fetch
    const btnLoadRace = document.getElementById("btn-load-race");
    const btnRecalculate = document.getElementById("btn-recalculate");
    const btnRetrain = document.getElementById("btn-retrain");
    const formAddHorse = document.getElementById("form-add-horse");
    const formImportJra = document.getElementById("form-import-jra");
    const btnFetchWeekly = document.getElementById("btn-fetch-weekly");
    const btnFetchWeeklySide = document.getElementById("btn-fetch-weekly-side");

    const displayRaceName = document.getElementById("display-race-name");
    const displayRaceMeta = document.getElementById("display-race-meta");
    const confidenceContainer = document.getElementById("confidence-container");
    const displayConfidence = document.getElementById("display-confidence");
    const tbodyPredictions = document.getElementById("tbody-predictions");

    // Handle one-click weekly JRA data fetch
    async function handleFetchWeeklyJra() {
        const originalBtnText = btnFetchWeekly ? btnFetchWeekly.innerHTML : "";
        if (btnFetchWeekly) {
            btnFetchWeekly.disabled = true;
            btnFetchWeekly.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span> JRA公式から今週の出馬表を一括取得・AI予想中...';
        }
        if (btnFetchWeeklySide) {
            btnFetchWeeklySide.disabled = true;
            btnFetchWeeklySide.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span> 取得中...';
        }

        tbodyPredictions.innerHTML = '<tr><td colspan="6" class="text-center py-4"><div class="spinner-border text-primary" role="status"></div><div class="mt-2 text-muted fw-bold">JRAホームページから今週のレース出馬表を取得・データベース保存・AI全予想計算中...</div></td></tr>';

        try {
            const res = await fetch("/api/import_weekly_jra", { method: "POST" });
            const data = await res.json();

            if (data.status === "success" && data.results && data.results.length > 0) {
                // Refresh race dropdown and select the first race
                await loadRaces(data.results[0].race.race_id);

                // Render the first imported race's predictions
                const firstResult = data.results[0];
                currentRace = firstResult.race;
                displayRaceName.textContent = firstResult.race.race_name;
                displayRaceMeta.textContent = `${firstResult.race.track_name}競馬場 | ${firstResult.race.surface_type}${firstResult.race.distance}m | 馬場: ${firstResult.race.track_condition} | 天候: ${firstResult.race.weather} (今週のJRA出馬表一括取得完了: ${data.count}レース)`;

                renderPredictions(firstResult.predictions);
                renderRecommendations(firstResult.recommendations);

                confidenceContainer.classList.remove("d-none");
                displayConfidence.textContent = `${firstResult.recommendations.confidence_score}%`;
                btnRecalculate.classList.remove("d-none");

                // Initialize race simulation engine
                initRaceSimulation(firstResult.race, firstResult.predictions);

                alert(`【成功】${data.message}\nドロップダウンから今週の全レース (${data.count}レース) を切替可能です。`);
            } else {
                alert("今週のJRAデータ取得エラー: " + (data.message || "データが見つかりませんでした。"));
            }
        } catch (err) {
            console.error("Failed to fetch weekly JRA races:", err);
            alert("通信エラーにより今週のJRAデータ取得に失敗しました。");
        } finally {
            if (btnFetchWeekly) {
                btnFetchWeekly.disabled = false;
                btnFetchWeekly.innerHTML = originalBtnText;
            }
            if (btnFetchWeeklySide) {
                btnFetchWeeklySide.disabled = false;
                btnFetchWeeklySide.innerHTML = '<i class="fa-solid fa-calendar-check me-1"></i> 今週分のJRAデータ取得 & 予想';
            }
        }
    }

    if (btnFetchWeekly) btnFetchWeekly.addEventListener("click", handleFetchWeeklyJra);
    if (btnFetchWeeklySide) btnFetchWeeklySide.addEventListener("click", handleFetchWeeklyJra);

    // Load available races (including DB saved races) on start
    loadRaces();

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

            if (result.status === "success") {
                currentRace = result.race;
                displayRaceName.textContent = result.race.race_name;
                displayRaceMeta.textContent = `${result.race.track_name}競馬場 | ${result.race.surface_type}${result.race.distance}m | 馬場: ${result.race.track_condition} | 天候: ${result.race.weather} (DB保管完了)`;
                renderPredictions(result.predictions);
                renderRecommendations(result.recommendations);

                confidenceContainer.classList.remove("d-none");
                displayConfidence.textContent = `${result.recommendations.confidence_score}%`;
                btnRecalculate.classList.remove("d-none");

                // Initialize race simulation engine
                initRaceSimulation(result.race, result.predictions);

                // Refresh race selection dropdown with newly saved DB race
                await loadRaces(result.race.race_id);
            } else {
                alert("JRA取り込みエラー: " + result.message);
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
