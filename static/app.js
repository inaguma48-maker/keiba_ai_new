document.addEventListener("DOMContentLoaded", () => {
    let currentRace = null;
    let simPredictions = [];
    let simAnimationFrame = null;
    let simIsRunning = false;
    let simProgress = 0; // 0 to 100%
    let simRunners = [];
    let simSpeedMultiplier = 1.0;

    const selectRace = document.getElementById("select-race");
    const canvas = document.getElementById("race-canvas");
    const ctx = canvas ? canvas.getContext("2d") : null;
    const btnStartSim = document.getElementById("btn-start-sim");
    const btnResetSim = document.getElementById("btn-reset-sim");
    const btnSpeedSim = document.getElementById("btn-speed-sim");
    const simSpeedText = document.getElementById("sim-speed-text");
    const simTimer = document.getElementById("sim-timer");
    const simLeaderName = document.getElementById("sim-leader-name");
    const simRaceTitle = document.getElementById("sim-race-title");
    const simBigRank = document.getElementById("sim-big-rank");
    const simTotalCount = document.getElementById("sim-total-count");
    const simSkillPopup = document.getElementById("sim-skill-popup");
    const simSkillText = document.getElementById("sim-skill-text");
    const simCommentaryHeadline = document.getElementById("sim-commentary-headline");
    const simCommentarySub = document.getElementById("sim-commentary-sub");
    const topProgressFill = document.getElementById("top-progress-fill");
    const topHorsesTrack = document.getElementById("top-horses-track");

    // Standard JRA Cap Colors (8 Waku colors)
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

    function getCapColor(num) {
        const idx = (Math.max(1, num) - 1) % CAP_COLORS.length;
        return CAP_COLORS[idx];
    }

    // Toggle Speed Multiplier (1x -> 2x -> 3x -> 1x)
    if (btnSpeedSim) {
        btnSpeedSim.addEventListener("click", () => {
            if (simSpeedMultiplier === 1.0) simSpeedMultiplier = 2.0;
            else if (simSpeedMultiplier === 2.0) simSpeedMultiplier = 3.0;
            else simSpeedMultiplier = 1.0;
            if (simSpeedText) simSpeedText.textContent = `${simSpeedMultiplier.toFixed(1)}x`;
        });
    }

    // Initialize Game-style Race Simulation State
    function initRaceSimulation(race, predictions) {
        if (!canvas || !ctx) return;
        currentRace = race;
        simPredictions = predictions || [];

        if (simRaceTitle && race) {
            simRaceTitle.innerHTML = `<i class="fa-solid fa-horse me-2 text-warning"></i>${race.race_name} (${race.track_name} ${race.surface_type}${race.distance}m)`;
        }

        simProgress = 0;
        simIsRunning = false;
        if (simAnimationFrame) {
            cancelAnimationFrame(simAnimationFrame);
            simAnimationFrame = null;
        }

        if (btnStartSim) {
            btnStartSim.innerHTML = '<i class="fa-solid fa-play me-1"></i> レーススタート';
            btnStartSim.classList.replace("btn-danger", "btn-warning");
            btnStartSim.classList.replace("text-white", "text-dark");
        }

        const totalRunners = simPredictions.length || 18;
        if (simTotalCount) simTotalCount.textContent = totalRunners;

        // Build Runners
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
                xPos: 100,
                yPos: 150 + (idx % 6) * 35,
                laneOffset: (idx % 5) * 18 - 36,
                color: getCapColor(p.horse_number),
                rank: idx + 1,
                hasTriggeredSkill: false
            };
        });

        updateSimulationUI();
        drawUmamusumeTrack();
        if (simCommentaryHeadline) simCommentaryHeadline.textContent = `さあ、誰が最初に仕掛けるのか！？`;
        if (simCommentarySub) simCommentarySub.textContent = `各馬一斉に出走準備完了！絶好の馬場コンディションです！`;
    }

    // Draw Umamusume Game-style 3D-Perspective Track and Horse Sprites
    function drawUmamusumeTrack() {
        if (!ctx) return;

        // Clear Background (Lush Turf Green)
        ctx.fillStyle = "#7ca16d";
        ctx.fillRect(0, 0, canvas.width, canvas.height);

        // Track Fence Rail (Top Inner Fence Curve)
        ctx.save();
        ctx.beginPath();
        ctx.moveTo(0, 110);
        ctx.bezierCurveTo(280, 110, 520, 170, 800, 180);
        ctx.lineWidth = 12;
        ctx.strokeStyle = "#4d6b41";
        ctx.stroke();

        ctx.lineWidth = 6;
        ctx.strokeStyle = "#ffffff";
        ctx.stroke();

        // White Fence Posts along Rail
        for (let x = 30; x <= 800; x += 45) {
            const progressRatio = x / 800;
            const y = 110 + Math.pow(progressRatio, 1.8) * 70;
            ctx.fillStyle = "#ffffff";
            ctx.fillRect(x - 3, y - 18, 6, 22);
            ctx.fillStyle = "#dddddd";
            ctx.fillRect(x - 1, y - 18, 2, 22);
        }
        ctx.restore();

        // Dirt/Turf Main Running Track Surface (Perspective Slopes)
        const trackGradient = ctx.createLinearGradient(0, 150, 0, 420);
        trackGradient.addColorStop(0, "#83a974");
        trackGradient.addColorStop(0.4, "#8dae7e");
        trackGradient.addColorStop(1, "#668c57");
        ctx.fillStyle = trackGradient;
        ctx.beginPath();
        ctx.moveTo(0, 120);
        ctx.bezierCurveTo(300, 120, 550, 180, 800, 190);
        ctx.lineTo(800, 420);
        ctx.lineTo(0, 420);
        ctx.closePath();
        ctx.fill();

        // White Lane Divider Stripes
        ctx.save();
        ctx.strokeStyle = "rgba(255, 255, 255, 0.35)";
        ctx.lineWidth = 3;
        ctx.setLineDash([15, 12]);
        ctx.beginPath();
        ctx.moveTo(0, 240);
        ctx.bezierCurveTo(300, 250, 550, 270, 800, 280);
        ctx.stroke();
        ctx.restore();

        // Outer Fence Rails (Bottom Right Curve)
        ctx.save();
        ctx.beginPath();
        ctx.moveTo(400, 420);
        ctx.bezierCurveTo(600, 400, 750, 360, 800, 330);
        ctx.lineWidth = 14;
        ctx.strokeStyle = "#a37035"; // Wood fence rail
        ctx.stroke();
        ctx.lineWidth = 8;
        ctx.strokeStyle = "#c88a44";
        ctx.stroke();
        ctx.restore();

        // Finish Line Gate Indicator (near end of track)
        if (simProgress > 0.85) {
            ctx.save();
            ctx.fillStyle = "#ff3333";
            ctx.fillRect(680, 160, 8, 240);
            ctx.fillStyle = "#ffffff";
            ctx.font = "bold 14px sans-serif";
            ctx.fillText("🏁 GOAL", 655, 150);
            ctx.restore();
        }

        // Draw Umamusume Horse Runners
        if (simRunners.length > 0) {
            // Sort runners by Y-position & progress so trailing/further horses are drawn behind
            const sorted = [...simRunners].sort((a, b) => (a.yPos - b.yPos));

            sorted.forEach(runner => {
                // Map runner's progress (0..1) relative to screen camera window
                const relProgress = Math.max(0, Math.min(1.0, (runner.currentDist - simProgress * 0.85) / 0.2 + 0.3));
                const rx = 80 + relProgress * 620;
                const ry = 190 + runner.laneOffset + (relProgress * 60);

                runner.xPos = rx;
                runner.yPos = ry;

                ctx.save();

                // 1. Motion Shadow
                ctx.fillStyle = "rgba(0, 0, 0, 0.3)";
                ctx.beginPath();
                ctx.ellipse(rx, ry + 12, 18, 7, 0, 0, Math.PI * 2);
                ctx.fill();

                // 2. Chibi / Umamusume Runner Character Body
                // Hair / Head
                ctx.fillStyle = "#4a2c11"; // Anime Hair
                ctx.beginPath();
                ctx.arc(rx, ry - 14, 11, 0, Math.PI * 2);
                ctx.fill();

                // Outfit Body
                ctx.fillStyle = runner.color.bg;
                ctx.beginPath();
                ctx.roundRect(rx - 8, ry - 7, 16, 18, 4);
                ctx.fill();
                ctx.lineWidth = 1.5;
                ctx.strokeStyle = runner.color.border;
                ctx.stroke();

                // Helmet / Number Cap Circle
                ctx.fillStyle = runner.color.bg;
                ctx.beginPath();
                ctx.arc(rx, ry - 22, 9, 0, Math.PI * 2);
                ctx.fill();
                ctx.lineWidth = 1.5;
                ctx.strokeStyle = "#ffffff";
                ctx.stroke();

                // Horse Number Text
                ctx.fillStyle = runner.color.text;
                ctx.font = "bold 10px sans-serif";
                ctx.textAlign = "center";
                ctx.textBaseline = "middle";
                ctx.fillText(runner.horse_number, rx, ry - 21.5);

                // 3. Yellow Inverted Triangle (▼) for Lead Horse (Matching Umamusume Target Marker in user image)
                if (runner.rank === 1) {
                    ctx.fillStyle = "#ffea00";
                    ctx.strokeStyle = "#000000";
                    ctx.lineWidth = 1;
                    ctx.beginPath();
                    ctx.moveTo(rx, ry - 35);
                    ctx.lineTo(rx - 7, ry - 46);
                    ctx.lineTo(rx + 7, ry - 46);
                    ctx.closePath();
                    ctx.fill();
                    ctx.stroke();

                    // Horse Name Bubble
                    ctx.fillStyle = "rgba(0,0,0,0.75)";
                    ctx.roundRect(rx - 32, ry - 65, 64, 16, 4);
                    ctx.fill();
                    ctx.fillStyle = "#ffffff";
                    ctx.font = "bold 10px sans-serif";
                    ctx.fillText(runner.horse_name.substring(0, 5), rx, ry - 54);
                }

                ctx.restore();
            });
        }
    }

    // Play-by-Play Commentary & Skill Popup Triggers
    function updateUmamusumeCommentary(leader, second, progress) {
        if (!leader) return;

        if (progress < 0.08) {
            if (simCommentaryHeadline) simCommentaryHeadline.textContent = `さあ、全馬一斉に綺麗にスタートを切りました！`;
            if (simCommentarySub) simCommentarySub.textContent = `好スタートを切ったのは${leader.horse_number}番 ${leader.horse_name}！`;
        } else if (progress < 0.35) {
            if (simCommentaryHeadline) simCommentaryHeadline.textContent = `さあ、誰が最初に仕掛けるのか！？`;
            const secName = second ? `${second.horse_number}番 ${second.horse_name}` : "後続集団";
            if (simCommentarySub) simCommentarySub.textContent = `${secName} 2番手につけ、様子を見守る！`;
        } else if (progress < 0.70) {
            if (simCommentaryHeadline) simCommentaryHeadline.textContent = `【第3〜4コーナー】各馬位置取りを激しく争う！`;
            if (simCommentarySub) simCommentarySub.textContent = `先頭${leader.horse_name}がしっかり手応えを残して直線を迎える！`;

            // Skill trigger demo at mid race
            if (!leader.hasTriggeredSkill && simSkillPopup && simSkillText) {
                leader.hasTriggeredSkill = true;
                simSkillText.textContent = `【脚質: 逃げ】${leader.horse_name} 先頭キープ発動！`;
                simSkillPopup.classList.remove("d-none");
                setTimeout(() => simSkillPopup.classList.add("d-none"), 2500);
            }
        } else if (progress < 0.95) {
            if (simCommentaryHeadline) simCommentaryHeadline.textContent = `【最後の直線！】叩き合い！ラストスパート！`;
            const secName = second ? `外から${second.horse_name}が追撃！` : "";
            if (simCommentarySub) simCommentarySub.textContent = `${leader.horse_name}が粘る！${secName} 残り200m！`;
        } else {
            if (simCommentaryHeadline) simCommentaryHeadline.textContent = `【ゴールイン！】圧巻の勝負を見せた！`;
            if (simCommentarySub) simCommentarySub.textContent = `栄光の1着は${leader.horse_number}番 ${leader.horse_name}！AI予想通りの見事な勝利！`;
        }
    }

    // Update Simulation Time, Leaderboard & Progress Track
    function updateSimulationUI() {
        if (simRunners.length === 0) return;

        // Sort runners by current progress
        simRunners.sort((a, b) => b.currentDist - a.currentDist);
        simRunners.forEach((r, idx) => r.rank = idx + 1);

        const leader = simRunners[0];
        const second = simRunners[1];

        // Update Big Rank display for the predicted winner (#1 selection or user focus)
        if (simBigRank) {
            simBigRank.textContent = leader ? leader.rank : "1";
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

        // Update Top Goal <--- Start Progress Tracker
        if (topProgressFill) {
            topProgressFill.style.width = `${(simProgress * 100).toFixed(1)}%`;
        }

        if (topHorsesTrack) {
            topHorsesTrack.innerHTML = simRunners.map(r => {
                const posPercent = (r.currentDist * 100).toFixed(1);
                return `
                    <span class="position-absolute translate-middle" style="left: ${posPercent}%; top: -6px;">
                        <span class="badge rounded-circle p-1 text-center shadow-sm" style="background:${r.color.bg}; color:${r.color.text}; font-size: 8px; width:16px; height:16px; display:inline-block; border:1px solid #fff; line-height:10px;">
                            ${r.horse_number}
                        </span>
                    </span>
                `;
            }).join("");
        }

        updateUmamusumeCommentary(leader, second, simProgress);
    }

    // Main Animation Loop
    function animateRace() {
        if (!simIsRunning) return;

        const delta = 0.0025 * simSpeedMultiplier;
        simProgress += delta;

        // Update each runner according to speedRating
        simRunners.forEach((runner) => {
            const staminaFactor = 1.0 + (runner.speedRating / 100.0) * 0.15;
            const variance = (Math.random() - 0.48) * 0.0008;
            runner.currentDist = Math.min(1.0, runner.currentDist + delta * staminaFactor + variance);
        });

        updateSimulationUI();
        drawUmamusumeTrack();

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
