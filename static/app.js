document.addEventListener("DOMContentLoaded", () => {
    // Original anime/uma character pool generator
    const ORIGINAL_NAMES = [
        "アグネスクラウン", "トウカイビクトリー", "シンボリスピリッツ", "サイレンスホープ",
        "メジロファンタジー", "スペシャルダッシュ", "ゴールドシップス", "ダイワロマンス",
        "ウオッカシャイン", "グラスウィナー", "エルコンドルパス", "テイエムスター",
        "マヤノトップガン", "ミホノブルボン", "ライスシャワー", "ビワハヤヒデ",
        "ナリタブライアン", "サクラローレル"
    ];

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

    let runners = [];
    let currentRace = {
        title: "第11回 オリジン記念 (GI / 芝2000m)",
        distance: 2000
    };

    let simAnimationFrame = null;
    let simIsRunning = false;
    let simProgress = 0; // 0.0 to 1.0
    let simSpeedMultiplier = 1.0;

    // DOM Elements
    const screenRacecard = document.getElementById("screen-racecard");
    const screenRace = document.getElementById("screen-race");
    const screenResult = document.getElementById("screen-result");

    const tbodyRacecardRunners = document.getElementById("tbody-racecard-runners");
    const tbodyResults = document.getElementById("tbody-results");

    const btnShuffleRunners = document.getElementById("btn-shuffle-runners");
    const btnGotoRace = document.getElementById("btn-goto-race");
    const btnBackRacecard = document.getElementById("btn-back-racecard");
    const btnBackToRacecard = document.getElementById("btn-back-to-racecard");
    const btnRestartSim = document.getElementById("btn-restart-sim");

    const btnSpeed1x = document.getElementById("btn-speed-1x");
    const btnSpeed2x = document.getElementById("btn-speed-2x");
    const btnSpeedSkip = document.getElementById("btn-speed-skip");
    const btnTogglePlay = document.getElementById("btn-toggle-play");

    const canvas = document.getElementById("race-canvas");
    const ctx = canvas ? canvas.getContext("2d") : null;

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

    const resultWinnerTitle = document.getElementById("result-winner-title");
    const resultWinnerSub = document.getElementById("result-winner-sub");

    // Get Waku / Cap Color
    function getCapColor(num) {
        return CAP_COLORS[(Math.max(1, num) - 1) % CAP_COLORS.length];
    }

    // Generate Original Anime Uma-Musume Runners
    function generateRunners(count = 18) {
        const shuffledNames = [...ORIGINAL_NAMES].sort(() => Math.random() - 0.5);
        runners = [];

        for (let i = 1; i <= count; i++) {
            const name = shuffledNames[i - 1] || `オリジナルウマ娘${i}号`;
            const style = STYLES[(i - 1) % STYLES.length];
            const speed = Math.floor(Math.random() * 25) + 75; // 75-100
            const stamina = Math.floor(Math.random() * 25) + 75;
            const power = Math.floor(Math.random() * 25) + 75;
            const guts = Math.floor(Math.random() * 25) + 75;

            // Calculate popularity & odds
            const totalScore = speed * 1.2 + stamina * 1.0 + power * 0.9 + guts * 0.8;

            runners.push({
                horse_number: i,
                horse_name: name,
                running_style: style,
                speed: speed,
                stamina: stamina,
                power: power,
                guts: guts,
                totalScore: totalScore,
                color: getCapColor(i),
                currentDist: 0,
                xPos: 50,
                yPos: 120 + (i % 6) * 35,
                laneOffset: (i % 5) * 16 - 32,
                rank: i,
                hasTriggeredSkill: false
            });
        }

        // Sort score to set odds & popularity
        const sorted = [...runners].sort((a, b) => b.totalScore - a.totalScore);
        sorted.forEach((r, idx) => {
            r.popularity = idx + 1;
            r.odds = (1.8 + idx * 2.1 + Math.random() * 0.5).toFixed(1);
        });

        // Re-sort by horse_number
        runners.sort((a, b) => a.horse_number - b.horse_number);
        renderRacecard();
    }

    // Render Racecard Table
    function renderRacecard() {
        if (!tbodyRacecardRunners) return;
        tbodyRacecardRunners.innerHTML = runners.map(r => {
            const styleBadgeClass = r.running_style === "逃げ" ? "badge-style-nige" :
                                    r.running_style === "先行" ? "badge-style-senko" :
                                    r.running_style === "差し" ? "badge-style-sashi" : "badge-style-goi";

            return `
                <tr>
                    <td class="text-center">
                        <span class="badge rounded-circle p-2 shadow-sm" style="background:${r.color.bg}; color:${r.color.text}; border: 1px solid ${r.color.border}; font-size: 14px; width:28px; height:28px; display:inline-block; line-height:12px;">
                            ${r.horse_number}
                        </span>
                    </td>
                    <td>
                        <div class="d-flex align-items-center gap-2">
                            <div class="runner-avatar-box" style="background:${r.color.bg}; color:${r.color.text}; border-color:${r.color.border}">
                                🏇
                            </div>
                            <div>
                                <div class="fw-bold fs-6 text-white">${r.horse_name}</div>
                                <div class="text-white-50 fs-8">オリジナル馬娘</div>
                            </div>
                        </div>
                    </td>
                    <td class="text-center">
                        <span class="badge ${styleBadgeClass} px-2 py-1">${r.running_style}</span>
                    </td>
                    <td>
                        <div class="d-flex flex-wrap gap-1 font-monospace">
                            <span class="stat-badge text-warning"><i class="fa-solid fa-gauge-high me-1"></i>スピ ${r.speed}</span>
                            <span class="stat-badge text-info"><i class="fa-solid fa-heart me-1"></i>スタ ${r.stamina}</span>
                            <span class="stat-badge text-danger"><i class="fa-solid fa-dumbbell me-1"></i>パワ ${r.power}</span>
                            <span class="stat-badge text-success"><i class="fa-solid fa-fire me-1"></i>根性 ${r.guts}</span>
                        </div>
                    </td>
                    <td class="text-center">
                        <div class="fw-bold text-warning">${r.popularity}番人気</div>
                        <div class="text-white-50 small">${r.odds}倍</div>
                    </td>
                </tr>
            `;
        }).join("");
    }

    // Switch Screen
    function switchScreen(targetScreen) {
        [screenRacecard, screenRace, screenResult].forEach(s => s && s.classList.remove("active"));
        if (targetScreen) targetScreen.classList.add("active");
    }

    // Initialize Race Simulation State
    function initSimulation() {
        simProgress = 0;
        simIsRunning = false;
        simSpeedMultiplier = 1.0;

        runners.forEach(r => {
            r.currentDist = 0;
            r.hasTriggeredSkill = false;
        });

        if (btnTogglePlay) btnTogglePlay.innerHTML = '<i class="fa-solid fa-play me-1"></i> スタート';
        if (btnSpeed1x) {
            btnSpeed1x.classList.add("active");
            btnSpeed2x.classList.remove("active");
            btnSpeedSkip.classList.remove("active");
        }

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
        if (runners.length > 0) {
            const sorted = [...runners].sort((a, b) => a.yPos - b.yPos);

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
        if (runners.length === 0) return;

        // Sort by current progress
        runners.sort((a, b) => b.currentDist - a.currentDist);
        runners.forEach((r, idx) => r.rank = idx + 1);

        const leader = runners[0];
        const second = runners[1];

        // Top 5 Leaderboard
        if (simTop5Leaderboard) {
            const top5 = runners.slice(0, 5);
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
            topHorsesTrack.innerHTML = runners.map(r => `
                <span class="position-absolute translate-middle" style="left: ${(r.currentDist * 100).toFixed(1)}%; top: -5px;">
                    <span class="badge rounded-circle p-1 text-center" style="background:${r.color.bg}; color:${r.color.text}; font-size: 7px; width:14px; height:14px; border:1px solid #fff; line-height:8px;">
                        ${r.horse_number}
                    </span>
                </span>
            `).join("");
        }

        // Commentary & Phase
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

        const delta = 0.003 * simSpeedMultiplier;
        simProgress += delta;

        runners.forEach(r => {
            const staminaFactor = 1.0 + (r.speed / 100.0) * 0.12;
            const variance = (Math.random() - 0.48) * 0.0008;
            r.currentDist = Math.min(1.0, r.currentDist + delta * staminaFactor + variance);
        });

        updateSimulationUI();
        drawCanvasTrack();

        if (simProgress >= 1.0) {
            simIsRunning = false;
            simProgress = 1.0;
            setTimeout(showResultsScreen, 1200);
            return;
        }

        simAnimationFrame = requestAnimationFrame(animateRace);
    }

    // Show Results Screen
    function showResultsScreen() {
        switchScreen(screenResult);

        runners.sort((a, b) => b.currentDist - a.currentDist);
        const winner = runners[0];

        if (resultWinnerTitle) resultWinnerTitle.textContent = `1着: ${winner.horse_number}番 ${winner.horse_name}`;
        if (resultWinnerSub) resultWinnerSub.textContent = `脚質: ${winner.running_style} | 人気: ${winner.popularity}番人気 (${winner.odds}倍) | 圧巻の1着！`;

        if (tbodyResults) {
            tbodyResults.innerHTML = runners.map((r, idx) => {
                const rankBadgeClass = idx === 0 ? "bg-warning text-dark fw-bold" :
                                       idx === 1 ? "bg-light text-dark fw-bold" :
                                       idx === 2 ? "bg-secondary text-white" : "bg-dark text-white-50";

                const timeSec = (118.4 + idx * 0.3 + Math.random() * 0.1).toFixed(1);
                const min = Math.floor(timeSec / 60);
                const sec = (timeSec % 60).toFixed(1).padStart(4, "0");
                const marginText = idx === 0 ? "-" : `${(idx * 1.5).toFixed(1)}馬身`;

                return `
                    <tr>
                        <td class="text-center">
                            <span class="badge ${rankBadgeClass} px-2 py-1 fs-6">${idx + 1}着</span>
                        </td>
                        <td class="text-center">
                            <span class="badge rounded-circle p-1" style="background:${r.color.bg}; color:${r.color.text}; border:1px solid #fff;">${r.horse_number}</span>
                        </td>
                        <td>
                            <div class="fw-bold text-white">${r.horse_name}</div>
                            <div class="text-white-50 fs-8">${r.popularity}番人気 (${r.odds}倍)</div>
                        </td>
                        <td class="text-center">
                            <span class="badge bg-dark border border-secondary">${r.running_style}</span>
                        </td>
                        <td class="text-center font-monospace">${min}:${sec}</td>
                        <td class="text-center text-white-50 fs-8">${marginText}</td>
                    </tr>
                `;
            }).join("");
        }
    }

    // Event Listeners
    if (btnShuffleRunners) {
        btnShuffleRunners.addEventListener("click", () => generateRunners(18));
    }

    if (btnGotoRace) {
        btnGotoRace.addEventListener("click", () => {
            switchScreen(screenRace);
            initSimulation();
            simIsRunning = true;
            if (btnTogglePlay) btnTogglePlay.innerHTML = '<i class="fa-solid fa-pause me-1"></i> 一時停止';
            animateRace();
        });
    }

    if (btnBackRacecard) {
        btnBackRacecard.addEventListener("click", () => {
            simIsRunning = false;
            if (simAnimationFrame) cancelAnimationFrame(simAnimationFrame);
            switchScreen(screenRacecard);
        });
    }

    if (btnBackToRacecard) {
        btnBackToRacecard.addEventListener("click", () => switchScreen(screenRacecard));
    }

    if (btnRestartSim) {
        btnRestartSim.addEventListener("click", () => {
            switchScreen(screenRace);
            initSimulation();
            simIsRunning = true;
            if (btnTogglePlay) btnTogglePlay.innerHTML = '<i class="fa-solid fa-pause me-1"></i> 一時停止';
            animateRace();
        });
    }

    if (btnTogglePlay) {
        btnTogglePlay.addEventListener("click", () => {
            simIsRunning = !simIsRunning;
            if (simIsRunning) {
                btnTogglePlay.innerHTML = '<i class="fa-solid fa-pause me-1"></i> 一時停止';
                animateRace();
            } else {
                btnTogglePlay.innerHTML = '<i class="fa-solid fa-play me-1"></i> 再開';
                if (simAnimationFrame) cancelAnimationFrame(simAnimationFrame);
            }
        });
    }

    if (btnSpeed1x) {
        btnSpeed1x.addEventListener("click", () => {
            simSpeedMultiplier = 1.0;
            [btnSpeed1x, btnSpeed2x, btnSpeedSkip].forEach(b => b.classList.remove("active"));
            btnSpeed1x.classList.add("active");
        });
    }

    if (btnSpeed2x) {
        btnSpeed2x.addEventListener("click", () => {
            simSpeedMultiplier = 2.5;
            [btnSpeed1x, btnSpeed2x, btnSpeedSkip].forEach(b => b.classList.remove("active"));
            btnSpeed2x.classList.add("active");
        });
    }

    if (btnSpeedSkip) {
        btnSpeedSkip.addEventListener("click", () => {
            simProgress = 1.0;
            simIsRunning = false;
            showResultsScreen();
        });
    }

    // JRA Fetch Integration (Optional Flask Backend API support)
    const btnFetchWeekly = document.getElementById("btn-fetch-weekly");
    const btnFetchWeeklyCard = document.getElementById("btn-fetch-weekly-card");

    async function handleFetchWeeklyJra() {
        alert("JRA公式HPから今週の出馬表データを取得して対戦用データを読み込みます。");
        try {
            const res = await fetch("/api/import_weekly_jra", { method: "POST" });
            const data = await res.json();
            if (data.status === "success" && data.results && data.results.length > 0) {
                const race = data.results[0].race;
                currentRace.title = `${race.race_name} (${race.track_name} ${race.surface_type}${race.distance}m)`;
                document.getElementById("racecard-title").textContent = currentRace.title;

                runners = race.horses.map((h, idx) => ({
                    horse_number: h.horse_number,
                    horse_name: h.horse_name,
                    running_style: STYLES[idx % STYLES.length],
                    speed: Math.floor(h.past_speed_rating || 85),
                    stamina: 80,
                    power: 80,
                    guts: 80,
                    odds: h.odds || 5.0,
                    popularity: idx + 1,
                    color: getCapColor(h.horse_number),
                    currentDist: 0,
                    xPos: 50,
                    yPos: 120 + (idx % 6) * 35,
                    laneOffset: (idx % 5) * 16 - 32,
                    rank: idx + 1,
                    hasTriggeredSkill: false
                }));

                renderRacecard();
                alert(`JRA今週のデータ一括読込完了 (${data.count}レース)！`);
            }
        } catch (e) {
            console.log("Standalone mode running without backend server.");
        }
    }

    if (btnFetchWeekly) btnFetchWeekly.addEventListener("click", handleFetchWeeklyJra);
    if (btnFetchWeeklyCard) btnFetchWeeklyCard.addEventListener("click", handleFetchWeeklyJra);

    // Initial Load
    generateRunners(18);
});
