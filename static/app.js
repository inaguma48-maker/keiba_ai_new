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

    // Canvas Simulation & Broadcast TV Elements
    const canvas = document.getElementById("raceCanvas");
    const ctx = canvas ? canvas.getContext("2d") : null;
    const btnStartSim = document.getElementById("btn-start-sim");
    const btnResetSim = document.getElementById("btn-reset-sim");
    const simLiveTime = document.getElementById("sim-live-time");
    const selectCamMode = document.getElementById("select-cam-mode");
    const commentaryText = document.getElementById("broadcast-commentary-text");
    const badgeLiveTv = document.getElementById("badge-live-tv");

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
        const profile = race ? race.track_profile : null;
        const isObstacle = surface === "障害";
        const isDirt = surface === "ダート";

        // Realistic Ground / Infield Environment Textures
        const gradBg = ctx.createRadialGradient(width/2, height/2, 50, width/2, height/2, width/2);
        gradBg.addColorStop(0, "#1b2e2b");
        gradBg.addColorStop(1, "#0d1b1a");
        ctx.fillStyle = gradBg;
        ctx.fillRect(0, 0, width, height);

        // Multi-lane Course Colors
        let turfMain = "#1e532b";
        let turfSub = "#2e7d32";
        let dirtMain = "#6d4c41";
        let obstacleMain = "#0d47a1";

        if (isDirt) {
            turfMain = "#5d4037";
            turfSub = "#8d6e63";
        } else if (isObstacle) {
            turfMain = "#1565c0";
            turfSub = "#1976d2";
        }

        // Outer Main Turf/Dirt Track Polygon / Oval
        ctx.lineWidth = isObstacle ? 42 : 34;
        ctx.strokeStyle = turfMain;
        ctx.lineJoin = "round";
        ctx.beginPath();
        ctx.roundRect(60, 45, width - 120, height - 100, [90]);
        ctx.stroke();

        // Multi-lane Markings (Inner Lane)
        ctx.lineWidth = 16;
        ctx.strokeStyle = isDirt ? "#8d6e63" : "#2a6f3b";
        ctx.beginPath();
        ctx.roundRect(75, 60, width - 150, height - 130, [75]);
        ctx.stroke();

        // White Fence Outer/Inner Barriers
        ctx.lineWidth = 2;
        ctx.strokeStyle = "#ffffff";
        ctx.beginPath();
        ctx.roundRect(42, 27, width - 84, height - 64, [100]);
        ctx.roundRect(92, 77, width - 184, height - 164, [60]);
        ctx.stroke();

        // Checkered Finish Line & Pole
        const finishX = 230;
        const finishYTop = height - 92;
        const finishYBot = height - 26;

        ctx.lineWidth = 6;
        ctx.strokeStyle = "#ffffff";
        ctx.beginPath();
        ctx.moveTo(finishX, finishYTop);
        ctx.lineTo(finishX, finishYBot);
        ctx.stroke();

        ctx.lineWidth = 6;
        ctx.setLineDash([4, 4]);
        ctx.strokeStyle = "#d32f2f";
        ctx.beginPath();
        ctx.moveTo(finishX, finishYTop);
        ctx.lineTo(finishX, finishYBot);
        ctx.stroke();
        ctx.setLineDash([]); // reset

        ctx.fillStyle = "#ffeb3b";
        ctx.font = "bold 12px sans-serif";
        ctx.textAlign = "center";
        ctx.fillText("🏁 FINISH", finishX, finishYTop - 10);

        // Authentic Starting Gate (発走ゲート)
        const gateX = width - 180;
        const gateY = height - 72;
        ctx.fillStyle = "#37474f";
        ctx.fillRect(gateX - 25, gateY - 14, 50, 28);
        ctx.strokeStyle = "#ffb300";
        ctx.lineWidth = 3;
        ctx.strokeRect(gateX - 25, gateY - 14, 50, 28);
        ctx.fillStyle = "#ffffff";
        ctx.font = "bold 10px sans-serif";
        ctx.fillText("START ゲート", gateX, gateY + 4);

        // Elevation / Rise Steep Slope Overlay (つくし坂・急坂)
        if (profile && profile.has_slope) {
            const slopeX = 290;
            const slopeY = height - 60;
            const gradSlope = ctx.createLinearGradient(slopeX, slopeY, slopeX + 130, slopeY);
            gradSlope.addColorStop(0, "rgba(255,111,0,0.85)");
            gradSlope.addColorStop(1, "rgba(229,57,53,0.85)");

            ctx.fillStyle = gradSlope;
            ctx.beginPath();
            ctx.moveTo(slopeX, slopeY + 10);
            ctx.lineTo(slopeX + 130, slopeY - 8);
            ctx.lineTo(slopeX + 130, slopeY + 12);
            ctx.lineTo(slopeX, slopeY + 12);
            ctx.closePath();
            ctx.fill();

            ctx.fillStyle = "#ffffff";
            ctx.font = "bold 11px sans-serif";
            ctx.textAlign = "left";
            ctx.fillText("▲ 直線急坂 (高低差 " + profile.max_slope_m + "m)", slopeX + 10, slopeY + 28);
        }

        // Steeplechase Jump Fences for Obstacle Races (生垣・バンケット・大竹柵)
        if (isObstacle) {
            const jumpPositions = [
                { x: 190, y: 45, label: "大生垣" },
                { x: 520, y: 45, label: "水濠" },
                { x: 690, y: 190, label: "バンケット" },
                { x: 420, y: height - 60, label: "大竹柵" }
            ];
            jumpPositions.forEach(j => {
                ctx.fillStyle = "#e65100";
                ctx.fillRect(j.x - 16, j.y - 14, 32, 28);
                ctx.strokeStyle = "#ffeb3b";
                ctx.lineWidth = 2;
                ctx.strokeRect(j.x - 16, j.y - 14, 32, 28);
                ctx.fillStyle = "#ffffff";
                ctx.font = "bold 10px sans-serif";
                ctx.textAlign = "center";
                ctx.fillText(j.label, j.x, j.y + 4);
            });
        }

        // Draw Realistic Video-Like Galloping Horses with High-Precision Thoroughbred Sprites, Camera Zoom & Broadcast HUD
        const horses = (simPredictions && simPredictions.length > 0)
            ? simPredictions
            : (race ? race.horses : []);

        const hCount = horses.length;
        if (hCount === 0) return;

        const isLeftTurn = profile ? profile.is_left_turn : false;
        const nowSec = Date.now() / 1000.0;

        // Calculate positions of all horses
        const horseStates = horses.map((h, idx) => {
            const speedFactor = h.win_probability ? (0.85 + h.win_probability * 0.5) : 1.0;
            const horseProgress = Math.min(1.0, progress * speedFactor);
            const pos = getOvalPathCoords(horseProgress, width, height, idx, hCount, isLeftTurn);
            const posNext = getOvalPathCoords(Math.min(1.0, horseProgress + 0.002), width, height, idx, hCount, isLeftTurn);
            const moveAngle = Math.atan2(posNext.y - pos.y, posNext.x - pos.x);
            return { h, idx, horseProgress, pos, moveAngle };
        });

        // Find current leader
        horseStates.sort((a, b) => b.horseProgress - a.horseProgress);
        const leader = horseStates[0];

        // Dynamic Broadcast Camera Pan & Zoom Matrix
        const camMode = selectCamMode ? selectCamMode.value : "overview";
        ctx.save();

        if (camMode === "lead" && simRunning && leader) {
            ctx.translate(width / 2, height / 2);
            ctx.scale(1.4, 1.4);
            ctx.translate(-leader.pos.x, -leader.pos.y);
        } else if (camMode === "finish" && simRunning) {
            ctx.translate(width / 2, height / 2);
            ctx.scale(1.35, 1.35);
            ctx.translate(-finishX - 30, -finishYBot + 40);
        }

        // Draw Horses in order from background to foreground
        horseStates.reverse().forEach(({ h, idx, horseProgress, pos, moveAngle }) => {
            // Galloping Gait Kinematics (サラブレッド走法のアニメーション)
            const gallopPhase = (nowSec * 16.0 + idx * 0.8) % (Math.PI * 2);
            const verticalBob = Math.sin(gallopPhase) * 4.0;
            const legExtendFront = Math.cos(gallopPhase) * 14.0;
            const legExtendRear = Math.sin(gallopPhase + 0.4) * 14.0;

            const silksColors = [
                "#d32f2f", "#1976d2", "#388e3c", "#fbc02d",
                "#7b1fa2", "#e65100", "#00838f", "#4e342e"
            ];
            const silkColor = silksColors[idx % silksColors.length];

            // Horse Body Coat Color Varieties (栗毛、鹿毛、青毛、芦毛)
            const coatColors = ["#3e2723", "#4e342e", "#212121", "#757575", "#5d4037"];
            const coatColor = coatColors[idx % coatColors.length];

            ctx.save();
            ctx.translate(pos.x, pos.y + verticalBob);
            ctx.rotate(moveAngle);

            // Turf Kickup Particle Physics
            if (simRunning) {
                ctx.fillStyle = isDirt ? "rgba(141, 110, 99, 0.7)" : "rgba(76, 175, 80, 0.7)";
                for (let p = 0; p < 4; p++) {
                    const px = -22 - Math.random() * 15;
                    const py = (Math.random() - 0.5) * 12;
                    ctx.beginPath();
                    ctx.arc(px, py, 1.5 + Math.random() * 3.0, 0, Math.PI * 2);
                    ctx.fill();
                }
            }

            // High-Detail Muscle Shaded Horse Body & Limbs
            // Rear Hooves & Legs
            ctx.lineWidth = 3.0;
            ctx.strokeStyle = coatColor;
            ctx.beginPath();
            ctx.moveTo(-6, 3);
            ctx.lineTo(-8 - legExtendRear, 13);
            ctx.lineTo(-12 - legExtendRear * 1.1, 18);
            ctx.moveTo(-10, 3);
            ctx.lineTo(-12 + legExtendRear * 0.7, 14);
            ctx.stroke();

            // Front Hooves & Legs
            ctx.beginPath();
            ctx.moveTo(10, 3);
            ctx.lineTo(12 + legExtendFront, 13);
            ctx.lineTo(16 + legExtendFront * 1.1, 18);
            ctx.moveTo(6, 3);
            ctx.lineTo(6 - legExtendFront * 0.7, 14);
            ctx.stroke();

            // Muscular Horse Torso (馬体胴部)
            ctx.fillStyle = coatColor;
            ctx.beginPath();
            ctx.ellipse(0, 0, 18, 9, 0, 0, Math.PI * 2);
            ctx.fill();

            // Saddle Cloth (鞍とゼッケン)
            ctx.fillStyle = silkColor;
            ctx.fillRect(-6, -8, 12, 10);
            ctx.strokeStyle = "#ffffff";
            ctx.lineWidth = 1;
            ctx.strokeRect(-6, -8, 12, 10);

            // Neck & Dynamic Head Movement
            const neckAngle = -0.3 + Math.sin(gallopPhase) * 0.1;
            ctx.save();
            ctx.translate(12, -4);
            ctx.rotate(neckAngle);

            ctx.fillStyle = coatColor;
            ctx.beginPath();
            ctx.moveTo(0, 0);
            ctx.lineTo(10, -10);
            ctx.lineTo(18, -8);
            ctx.lineTo(16, -2);
            ctx.lineTo(4, 5);
            ctx.closePath();
            ctx.fill();

            // Horse Snout & Ears
            ctx.beginPath();
            ctx.arc(17, -7, 3, 0, Math.PI * 2);
            ctx.fill();
            ctx.beginPath();
            ctx.moveTo(8, -12);
            ctx.lineTo(10, -16);
            ctx.lineTo(11, -11);
            ctx.closePath();
            ctx.fill();

            ctx.restore(); // end neck

            // Jockey Silks & Posture
            ctx.fillStyle = silkColor;
            ctx.beginPath();
            ctx.ellipse(-2, -10, 6, 5, -0.4, 0, Math.PI * 2);
            ctx.fill();

            // Jockey Helmet
            ctx.fillStyle = "#ffeb3b";
            ctx.beginPath();
            ctx.arc(-2, -15, 3.5, 0, Math.PI * 2);
            ctx.fill();

            ctx.restore();

            // Overhead Horse Saddle Number Badge & Name Box
            ctx.save();
            ctx.translate(pos.x, pos.y - 28);

            ctx.fillStyle = silkColor;
            ctx.beginPath();
            ctx.arc(0, 0, 10, 0, Math.PI * 2);
            ctx.fill();
            ctx.lineWidth = 1.5;
            ctx.strokeStyle = "#ffffff";
            ctx.stroke();

            ctx.fillStyle = "#ffffff";
            ctx.font = "bold 11px sans-serif";
            ctx.textAlign = "center";
            ctx.textBaseline = "middle";
            ctx.fillText(h.horse_number, 0, 0);

            // Horse Name Tag with Glassmorphic Badge
            ctx.fillStyle = "rgba(0, 0, 0, 0.75)";
            ctx.fillRect(-28, -20, 56, 13);
            ctx.strokeStyle = "rgba(255,255,255,0.4)";
            ctx.strokeRect(-28, -20, 56, 13);

            ctx.fillStyle = "#ffeb3b";
            ctx.font = "bold 9px sans-serif";
            ctx.fillText(h.horse_name.substring(0, 6), 0, -13);

            ctx.restore();
        });

        ctx.restore(); // end camera transformation

        // Live Broadcast TV HUD Leaderboard Bar (画面上部 Live 実況テロップ)
        if (simRunning && leader) {
            ctx.fillStyle = "rgba(10, 10, 10, 0.85)";
            ctx.fillRect(15, 15, 300, 32);
            ctx.strokeStyle = "#fbc02d";
            ctx.lineWidth = 2;
            ctx.strokeRect(15, 15, 300, 32);

            ctx.fillStyle = "#fbc02d";
            ctx.font = "bold 12px sans-serif";
            ctx.textAlign = "left";
            ctx.fillText("LIVE 先頭: " + leader.h.horse_number + "番 " + leader.h.horse_name, 25, 35);
        }
    }

    function getOvalPathCoords(t, width, height, laneIdx, totalLanes, isLeftTurn = false) {
        const rx = (width - 140) / 2;
        const ry = (height - 120) / 2;
        const cx = width / 2;
        const cy = height / 2;

        const laneOffset = (laneIdx - totalLanes / 2) * 3.2;

        // Counter-clockwise vs Clockwise directional angle mapping
        let angle = isLeftTurn
            ? (Math.PI * 2 * t + Math.PI / 2)
            : (Math.PI * 2 * (1.0 - t) + Math.PI / 2);

        const x = cx + (rx + laneOffset) * Math.cos(angle);
        const y = cy + (ry + laneOffset) * Math.sin(angle);

        return { x, y };
    }

    if (btnStartSim) {
        btnStartSim.addEventListener("click", () => {
            if (simRunning) return;
            simRunning = true;
            simProgress = 0;
            if (badgeLiveTv) badgeLiveTv.classList.remove("d-none");
            const startTime = Date.now();

            function animate() {
                if (!simRunning) return;
                simProgress += 0.0035;
                const elapsedSec = ((Date.now() - startTime) / 1000).toFixed(1);
                if (simLiveTime) simLiveTime.textContent = `${elapsedSec}秒`;

                // Real-time Japanese Broadcast Commentary Generator
                if (commentaryText) {
                    if (simProgress < 0.1) {
                        commentaryText.textContent = "ゲートが一斉に開いた！綺麗なスタートを切りました！";
                    } else if (simProgress < 0.35) {
                        commentaryText.textContent = "各馬向正面へと差し掛かります。激しい先行争いが続いています！";
                    } else if (simProgress < 0.65) {
                        commentaryText.textContent = "レースは第3コーナーから第4コーナーへ！先頭馬が手応え良く後続を引き離します！";
                    } else if (simProgress < 0.88) {
                        commentaryText.textContent = "さあ最終直線だ！坂を駆け上がる！外からAI本命馬が猛烈な追い上げ！";
                    } else if (simProgress < 1.0) {
                        commentaryText.textContent = "大歓声の中、ゴール板前接戦！激しい追い比べ！";
                    } else {
                        commentaryText.textContent = "各馬ゴールイン！見事な一戦となりました！";
                    }
                }

                drawTrackCanvas(currentRace, simProgress);

                if (simProgress >= 1.0) {
                    simRunning = false;
                    if (badgeLiveTv) badgeLiveTv.classList.add("d-none");
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
            if (badgeLiveTv) badgeLiveTv.classList.add("d-none");
            if (simLiveTime) simLiveTime.textContent = "0.0秒";
            if (commentaryText) commentaryText.textContent = "出走準備完了。スタートボタンを押すとAIリアル中継シミュレーションが始まります。";
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
                    alert(`${result.message}\n\n【注意】${result.warning || ""}`);
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
