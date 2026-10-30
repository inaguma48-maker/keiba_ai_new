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
    const btnRecordSim = document.getElementById("btn-record-sim");
    const simSpeedText = document.getElementById("sim-speed-text");
    const simRaceTitle = document.getElementById("sim-race-title");
    const simTimer = document.getElementById("sim-timer");
    const simDistanceLeft = document.getElementById("sim-distance-left");
    const simLeaderName = document.getElementById("sim-leader-name");
    const simBottomPositionBar = document.getElementById("sim-bottom-position-bar");
    const tvCornerBanner = document.getElementById("tv-corner-banner");
    const simCommentaryHeadline = document.getElementById("sim-commentary-headline");
    const simCommentarySub = document.getElementById("sim-commentary-sub");
    const simSkillPopup = document.getElementById("sim-skill-popup");
    const simSkillTitle = document.getElementById("sim-skill-title");
    const simSkillText = document.getElementById("sim-skill-text");

    // Stage Badges
    const stageBadges = {
        start: document.getElementById("stage-start"),
        backstretch: document.getElementById("stage-backstretch"),
        corner3: document.getElementById("stage-corner3"),
        corner4: document.getElementById("stage-corner4"),
        straight: document.getElementById("stage-straight"),
        finish: document.getElementById("stage-finish")
    };

    function updateStageHUD(stageKey) {
        Object.entries(stageBadges).forEach(([k, el]) => {
            if (!el) return;
            if (k === stageKey) {
                el.className = "badge bg-warning text-dark border fw-bold shadow-sm";
            } else {
                el.className = "badge bg-dark border text-white-50";
            }
        });
    }

    // MediaRecorder Video Generation Engine
    let mediaRecorder = null;
    let recordedChunks = [];
    let isRecording = false;

    if (btnRecordSim) {
        btnRecordSim.addEventListener("click", () => {
            if (isRecording) {
                stopRecording();
            } else {
                startRecording();
            }
        });
    }

    function startRecording() {
        if (!canvas) return;
        try {
            const stream = canvas.captureStream(30); // 30 FPS
            recordedChunks = [];
            let options = { mimeType: "video/webm;codecs=vp9" };
            if (!MediaRecorder.isTypeSupported(options.mimeType)) {
                options = { mimeType: "video/webm" };
            }

            mediaRecorder = new MediaRecorder(stream, options);
            mediaRecorder.ondataavailable = (e) => {
                if (e.data.size > 0) recordedChunks.push(e.data);
            };
            mediaRecorder.onstop = exportRecordedVideo;

            mediaRecorder.start();
            isRecording = true;
            btnRecordSim.innerHTML = '<span class="spinner-grow spinner-grow-sm me-1"></span> 録画中(停止＆保存)';
            btnRecordSim.className = "btn btn-danger btn-sm fw-bold";

            // If race not running, start it
            if (!simIsRunning) {
                btnStartSim.click();
            }
        } catch (err) {
            console.error("Recording error:", err);
            alert("動画録画を開始できませんでした: " + err.message);
        }
    }

    function stopRecording() {
        if (mediaRecorder && isRecording) {
            mediaRecorder.stop();
            isRecording = false;
            btnRecordSim.innerHTML = '<i class="fa-solid fa-circle-dot text-danger me-1"></i> AI中継動画を作成';
            btnRecordSim.className = "btn btn-outline-danger btn-sm fw-bold";
        }
    }

    function exportRecordedVideo() {
        const blob = new Blob(recordedChunks, { type: "video/webm" });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        const raceName = currentRace ? currentRace.race_name : "JRA_Race";
        a.href = url;
        a.download = `${raceName}_AI競馬中継動画.webm`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        alert(`【AI中継動画完成】\n「${raceName}_AI競馬中継動画.webm」を生成・ダウンロードしました！`);
    }

    // Speed Multiplier Switcher
    if (btnSpeedSim) {
        btnSpeedSim.addEventListener("click", () => {
            if (simSpeedMultiplier === 1.0) simSpeedMultiplier = 2.0;
            else if (simSpeedMultiplier === 2.0) simSpeedMultiplier = 3.0;
            else simSpeedMultiplier = 1.0;
            if (simSpeedText) simSpeedText.textContent = `${simSpeedMultiplier.toFixed(1)}x`;
        });
    }

    // --- Three.js WebGL 3D Simulation Setup ---
    let threeScene, threeCamera, threeRenderer;
    let threeHorsesGroup = [];
    let threeTrackLength = 400; // 3D units representing race track
    let cameraMode = "broadcast"; // broadcast, corner, chase, top

    // Camera Switcher UI Events
    const btnCamBroadcast = document.getElementById("btn-cam-broadcast");
    const btnCamCorner = document.getElementById("btn-cam-corner");
    const btnCamChase = document.getElementById("btn-cam-chase");
    const btnCamTop = document.getElementById("btn-cam-top");

    function setCameraMode(mode) {
        cameraMode = mode;
        if (btnCamBroadcast) btnCamBroadcast.className = `btn btn-sm fw-bold fs-8 ${mode === 'broadcast' ? 'btn-warning active' : 'btn-outline-warning'}`;
        if (btnCamCorner) btnCamCorner.className = `btn btn-sm fw-bold fs-8 ${mode === 'corner' ? 'btn-warning active' : 'btn-outline-warning'}`;
        if (btnCamChase) btnCamChase.className = `btn btn-sm fw-bold fs-8 ${mode === 'chase' ? 'btn-warning active' : 'btn-outline-warning'}`;
        if (btnCamTop) btnCamTop.className = `btn btn-sm fw-bold fs-8 ${mode === 'top' ? 'btn-warning active' : 'btn-outline-warning'}`;
    }

    if (btnCamBroadcast) btnCamBroadcast.addEventListener("click", () => setCameraMode("broadcast"));
    if (btnCamCorner) btnCamCorner.addEventListener("click", () => setCameraMode("corner"));
    if (btnCamChase) btnCamChase.addEventListener("click", () => setCameraMode("chase"));
    if (btnCamTop) btnCamTop.addEventListener("click", () => setCameraMode("top"));

    function init3DScene() {
        if (typeof THREE === "undefined" || !canvas) return;

        // Create WebGL Renderer attached to canvas
        threeScene = new THREE.Scene();
        threeScene.background = new THREE.Color(0x1a2536); // Night stadium ambiance
        threeScene.fog = new THREE.FogExp2(0x1a2536, 0.0035);

        const width = canvas.clientWidth || 800;
        const height = canvas.clientHeight || 400;

        threeCamera = new THREE.PerspectiveCamera(50, width / height, 0.1, 1000);
        threeCamera.position.set(-30, 25, 40);

        try {
            threeRenderer = new THREE.WebGLRenderer({ canvas: canvas, antialias: true, alpha: true });
            threeRenderer.setSize(width, height, false);
            threeRenderer.shadowMap.enabled = true;
            threeRenderer.shadowMap.type = THREE.PCFSoftShadowMap;
        } catch (e) {
            console.warn("WebGL not supported, falling back to 2D canvas simulation mode:", e);
            threeRenderer = null;
        }

        // Lighting
        const ambientLight = new THREE.AmbientLight(0xffffff, 0.65);
        threeScene.add(ambientLight);

        const dirLight = new THREE.DirectionalLight(0xfffaed, 1.2);

        // Speed Line Dust Particles
        const particleCount = 150;
        const particleGeo = new THREE.BufferGeometry();
        const particlePositions = new Float32Array(particleCount * 3);

        for (let i = 0; i < particleCount * 3; i += 3) {
            particlePositions[i] = (Math.random() - 0.5) * 500;
            particlePositions[i + 1] = Math.random() * 5 + 0.2;
            particlePositions[i + 2] = (Math.random() - 0.5) * 40;
        }

        particleGeo.setAttribute('position', new THREE.BufferAttribute(particlePositions, 3));
        const particleMat = new THREE.PointsMaterial({
            color: 0xffffff,
            size: 0.4,
            transparent: true,
            opacity: 0.5
        });
        const particleSystem = new THREE.Points(particleGeo, particleMat);
        threeScene.add(particleSystem);
        threeScene.dustParticles = particleSystem;

        const dirLightRef = dirLight;
        dirLight.position.set(-50, 100, 50);
        dirLight.castShadow = true;
        dirLight.shadow.mapSize.width = 1024;
        dirLight.shadow.mapSize.height = 1024;
        dirLight.shadow.camera.near = 0.5;
        dirLight.shadow.camera.far = 500;
        dirLight.shadow.camera.left = -200;
        dirLight.shadow.camera.right = 200;
        dirLight.shadow.camera.top = 100;
        dirLight.shadow.camera.bottom = -100;
        threeScene.add(dirLight);

        // Turf Track Plane
        const trackWidth = 35;
        const trackGeo = new THREE.PlaneGeometry(threeTrackLength + 100, trackWidth);
        const trackMat = new THREE.MeshStandardMaterial({
            color: 0x38761d,
            roughness: 0.8,
            metalness: 0.1
        });
        const trackMesh = new THREE.Mesh(trackGeo, trackMat);
        trackMesh.rotation.x = -Math.PI / 2;
        trackMesh.position.x = threeTrackLength / 2;
        trackMesh.receiveShadow = true;
        threeScene.add(trackMesh);

        // Track Rails (Fence)
        const railGeo = new THREE.BoxGeometry(threeTrackLength + 100, 1.2, 0.4);
        const railMat = new THREE.MeshStandardMaterial({ color: 0xffffff, roughness: 0.3 });

        const innerRail = new THREE.Mesh(railGeo, railMat);
        innerRail.position.set(threeTrackLength / 2, 1.2, -trackWidth / 2);
        threeScene.add(innerRail);

        const outerRail = new THREE.Mesh(railGeo, railMat);
        outerRail.position.set(threeTrackLength / 2, 1.2, trackWidth / 2);
        threeScene.add(outerRail);

        // Goal Gate Banner
        const goalGroup = new THREE.Group();
        goalGroup.position.set(threeTrackLength * 0.9, 0, 0);

        const pillarGeo = new THREE.CylinderGeometry(0.5, 0.5, 16);
        const pillarMat = new THREE.MeshStandardMaterial({ color: 0xe63946, metalness: 0.5 });

        const p1 = new THREE.Mesh(pillarGeo, pillarMat);
        p1.position.set(0, 8, -trackWidth / 2);
        goalGroup.add(p1);

        const p2 = new THREE.Mesh(pillarGeo, pillarMat);
        p2.position.set(0, 8, trackWidth / 2);
        goalGroup.add(p2);

        const archGeo = new THREE.BoxGeometry(1, 2, trackWidth + 2);
        const archMat = new THREE.MeshStandardMaterial({ color: 0xffd166, metalness: 0.8 });
        const arch = new THREE.Mesh(archGeo, archMat);
        arch.position.set(0, 15, 0);
        goalGroup.add(arch);

        threeScene.add(goalGroup);
    }

    // Create 3D Horse & Jockey Mesh Group
    function create3DHorseMesh(runner) {
        const group = new THREE.Group();

        // Body (Horse)
        const bodyGeo = new THREE.BoxGeometry(3.2, 1.8, 1.2);
        const bodyMat = new THREE.MeshStandardMaterial({ color: 0x5c3d1e, roughness: 0.6 });
        const body = new THREE.Mesh(bodyGeo, bodyMat);
        body.position.y = 2.2;
        body.castShadow = true;
        group.add(body);

        // Head
        const headGeo = new THREE.BoxGeometry(1.2, 1.0, 0.8);
        const head = new THREE.Mesh(headGeo, bodyMat);
        head.position.set(1.6, 3.2, 0);
        head.rotation.z = -0.2;
        head.castShadow = true;
        group.add(head);

        // Legs (4 Cylinder Legs)
        const legGeo = new THREE.CylinderGeometry(0.2, 0.15, 2.0);
        const legMat = new THREE.MeshStandardMaterial({ color: 0x3d2813 });
        const legPositions = [
            [1.0, 1.0, 0.4], [1.0, 1.0, -0.4],
            [-1.0, 1.0, 0.4], [-1.0, 1.0, -0.4]
        ];
        runner.legs = [];
        legPositions.forEach((pos, idx) => {
            const leg = new THREE.Mesh(legGeo, legMat);
            leg.position.set(pos[0], pos[1], pos[2]);
            leg.castShadow = true;
            group.add(leg);
            runner.legs.push(leg);
        });

        // Jockey (Umamusume Style Helmet / Cap & Shirt)
        const jockeyGeo = new THREE.SphereGeometry(0.7, 16, 16);
        const capHex = parseInt(runner.color.bg.replace("#", "0x"), 16);
        const jockeyMat = new THREE.MeshStandardMaterial({ color: capHex, roughness: 0.3 });
        const jockeyHead = new THREE.Mesh(jockeyGeo, jockeyMat);
        jockeyHead.position.set(0.2, 3.8, 0);
        jockeyHead.castShadow = true;
        group.add(jockeyHead);

        // Number Plate Marker
        const numGeo = new THREE.BoxGeometry(0.8, 0.8, 1.25);
        const numMat = new THREE.MeshStandardMaterial({ color: 0xffffff });
        const numMesh = new THREE.Mesh(numGeo, numMat);
        numMesh.position.set(-0.5, 2.4, 0);
        group.add(numMesh);

        // Aura Light Effect Mesh (Initially hidden)
        const auraGeo = new THREE.SphereGeometry(2.5, 16, 16);
        const auraMat = new THREE.MeshBasicMaterial({ color: 0xffd700, transparent: true, opacity: 0, wireframe: true });
        const auraMesh = new THREE.Mesh(auraGeo, auraMat);
        auraMesh.position.set(0, 2.5, 0);
        group.add(auraMesh);
        runner.auraMesh = auraMesh;

        return group;
    }

    // Initialize Simulation Engine
    function initSimulation(race, predictions) {
        if (!canvas) return;
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

        // Initialize 3D Scene
        if (!threeScene) {
            init3DScene();
        }

        // Clear existing 3D runners
        threeHorsesGroup.forEach(mesh => threeScene.remove(mesh));
        threeHorsesGroup = [];

        simRunners = simPredictions.map((p, idx) => {
            const baseProb = p.win_probability || (0.15 - idx * 0.01);
            const odds = p.odds || 5.0;
            const speedRating = (1 / odds) * 50 + (baseProb * 80);
            const laneOffset = (idx - simPredictions.length / 2) * 1.8;

            const runnerObj = {
                horse_number: p.horse_number,
                horse_name: p.horse_name,
                jockey_name: p.jockey_name,
                running_style: STYLES[idx % STYLES.length],
                win_probability: baseProb,
                speedRating: speedRating,
                currentDist: 0,
                laneOffset: laneOffset,
                color: getCapColor(p.horse_number),
                rank: idx + 1,
                hasTriggeredSkill: false
            };

            const mesh = create3DHorseMesh(runnerObj);
            mesh.position.set(0, 0, laneOffset);
            threeScene.add(mesh);
            runnerObj.mesh = mesh;
            threeHorsesGroup.push(mesh);

            return runnerObj;
        });

        updateStageHUD("start");
        updateSimulationUI();
        render3DScene();
    }

    // Render 3D Scene Frame & Animate Camera/Legs (with 2D Canvas Fallback if WebGL unavailable)
    function render3DScene() {
        if (!threeRenderer || !threeScene || !threeCamera) {
            // 2D Canvas Fallback renderer
            if (ctx && canvas) {
                ctx.clearRect(0, 0, canvas.width, canvas.height);
                ctx.fillStyle = "#38761d";
                ctx.fillRect(0, 0, canvas.width, canvas.height);

                // Rail lines
                ctx.strokeStyle = "#ffffff";
                ctx.lineWidth = 2;
                ctx.beginPath();
                ctx.moveTo(0, 60); ctx.lineTo(canvas.width, 60);
                ctx.moveTo(0, canvas.height - 60); ctx.lineTo(canvas.width, canvas.height - 60);
                ctx.stroke();

                // Goal line
                ctx.strokeStyle = "#ffd700";
                ctx.lineWidth = 4;
                ctx.beginPath();
                ctx.moveTo(canvas.width * 0.9, 50);
                ctx.lineTo(canvas.width * 0.9, canvas.height - 50);
                ctx.stroke();

                // Draw Horses
                simRunners.forEach((runner, idx) => {
                    const y = 80 + idx * ((canvas.height - 160) / Math.max(1, simRunners.length));
                    const x = 50 + runner.currentDist * (canvas.width * 0.85);

                    // Horse Body
                    ctx.fillStyle = "#654321";
                    ctx.beginPath();
                    ctx.ellipse(x, y, 16, 9, 0, 0, Math.PI * 2);
                    ctx.fill();

                    // Jockey Cap
                    ctx.fillStyle = runner.color.bg;
                    ctx.beginPath();
                    ctx.arc(x + 4, y - 6, 6, 0, Math.PI * 2);
                    ctx.fill();

                    // Horse Number
                    ctx.fillStyle = "#ffffff";
                    ctx.font = "bold 9px sans-serif";
                    ctx.fillText(runner.horse_number, x - 4, y + 3);
                });
            }
            return;
        }

        // Position runners in 3D world based on currentDist
        simRunners.forEach((runner, idx) => {
            if (runner.mesh) {
                const targetX = runner.currentDist * threeTrackLength;
                runner.mesh.position.x = targetX;

                // Running leg animation
                if (simIsRunning && runner.legs) {
                    const time = Date.now() * 0.012;
                    runner.legs[0].rotation.z = Math.sin(time + idx) * 0.6;
                    runner.legs[1].rotation.z = -Math.sin(time + idx) * 0.6;
                    runner.legs[2].rotation.z = -Math.sin(time + idx) * 0.6;
                    runner.legs[3].rotation.z = Math.sin(time + idx) * 0.6;
                }

                // Skill Aura animation
                if (runner.hasTriggeredSkill && runner.auraMesh) {
                    runner.auraMesh.material.opacity = 0.6 + Math.sin(Date.now() * 0.01) * 0.3;
                    runner.auraMesh.rotation.y += 0.05;
                }
            }
        });

        // Particle motion effect during simulation
        if (simIsRunning && threeScene.dustParticles) {
            const positions = threeScene.dustParticles.geometry.attributes.position.array;
            for (let i = 0; i < positions.length; i += 3) {
                positions[i] -= 1.5 * simSpeedMultiplier;
                if (positions[i] < -50) positions[i] += 500;
            }
            threeScene.dustParticles.geometry.attributes.position.needsUpdate = true;
        }

        // Dynamic 3D Camera Controls (Corner by Corner Live Broadcast Directed Cameras)
        if (simRunners.length > 0) {
            const sorted = [...simRunners].sort((a, b) => b.currentDist - a.currentDist);
            const leader = sorted[0];
            const leaderX = leader ? leader.currentDist * threeTrackLength : 0;

            if (cameraMode === "broadcast") {
                // Automatic TV Broadcast Director transitioning across corners
                if (simProgress < 0.15) {
                    // スタート台正面 〜 正面スタンド前パン
                    threeCamera.position.set(leaderX + 35, 14, 25);
                    threeCamera.lookAt(leaderX, 2.5, 0);
                } else if (simProgress < 0.40) {
                    // 向正面: 遠景パノラマ・ハイアングル追従中継
                    threeCamera.position.set(leaderX + 45, 22, 38);
                    threeCamera.lookAt(leaderX + 5, 2.5, 0);
                } else if (simProgress < 0.65) {
                    // 第3コーナー: コーナー入り口からカーブを捉える望遠中継
                    threeCamera.position.set(leaderX + 30, 16, 28);
                    threeCamera.lookAt(leaderX, 2.5, -2);
                } else if (simProgress < 0.80) {
                    // 第4コーナー: 直線入り口のローアングル迫力中継
                    threeCamera.position.set(leaderX + 25, 11, 20);
                    threeCamera.lookAt(leaderX, 2.8, 0);
                } else if (simProgress < 0.96) {
                    // 最後の直線: 叩き合い！正面スタンド正面ズーム
                    threeCamera.position.set(leaderX + 22, 10, 16);
                    threeCamera.lookAt(leaderX, 2.5, 0);
                } else {
                    // ゴール板スロー中継
                    const goalX = threeTrackLength * 0.9;
                    threeCamera.position.set(goalX + 15, 12, 22);
                    threeCamera.lookAt(goalX, 3.0, 0);
                }
            } else if (cameraMode === "corner") {
                // コーナー固定アングル (望遠視点)
                const cornerStationX = Math.floor(leaderX / 80) * 80 + 40;
                threeCamera.position.set(cornerStationX + 25, 18, 30);
                threeCamera.lookAt(leaderX, 3, 0);
            } else if (cameraMode === "chase") {
                // Close Chase Camera behind leader
                threeCamera.position.set(leaderX - 18, 10, leader.laneOffset + 8);
                threeCamera.lookAt(leaderX + 10, 3, leader.laneOffset);
            } else if (cameraMode === "top") {
                // Top-down overhead camera
                threeCamera.position.set(leaderX, 60, 0);
                threeCamera.lookAt(leaderX, 0, 0);
            }
        }

        threeRenderer.render(threeScene, threeCamera);
    }

    // Update Simulation UI
    function updateSimulationUI() {
        if (simRunners.length === 0) return;

        simRunners.sort((a, b) => b.currentDist - a.currentDist);
        simRunners.forEach((r, idx) => r.rank = idx + 1);

        const leader = simRunners[0];
        const second = simRunners[1];

        // 映像の中の下に番号をリアルタイムに表示した位置取りバー
        if (simBottomPositionBar) {
            simBottomPositionBar.innerHTML = simRunners.map((r, idx) => {
                const isLeader = idx === 0;
                const prevRunner = idx > 0 ? simRunners[idx - 1] : null;
                const gap = prevRunner ? (prevRunner.currentDist - r.currentDist) * 100 : 0;
                const showGap = gap > 2.0;

                return `
                    ${showGap ? '<span class="text-secondary fw-bold fs-9">··</span>' : ''}
                    <div class="d-inline-flex flex-column align-items-center" style="min-width: 28px;">
                        <span class="badge rounded-1 fw-bold fs-7 shadow-sm text-center"
                              style="background:${r.color.bg}; color:${r.color.text}; border: 1.5px solid ${isLeader ? '#ffd700' : '#444'}; width: 28px; height: 24px; line-height: 20px;">
                            ${r.horse_number}
                        </span>
                        <span class="text-white-50 fs-9 text-truncate text-center" style="max-width: 32px; font-size: 8px;">
                            ${r.horse_name.slice(0, 2)}
                        </span>
                    </div>
                `;
            }).join("");
        }

        // Remaining distance calculation
        const totalDist = (currentRace && currentRace.distance) ? currentRace.distance : 1600;
        const remainingDist = Math.max(0, Math.round(totalDist * (1.0 - simProgress)));
        if (simDistanceLeft) {
            simDistanceLeft.textContent = `${remainingDist}m`;
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

        // Corner stages tracking and TV banner
        if (simProgress < 0.15) {
            updateStageHUD("start");
            if (tvCornerBanner) tvCornerBanner.textContent = "ゲートオープン / スタート";
            if (simCommentaryHeadline) simCommentaryHeadline.textContent = `全馬一斉に綺麗にスタート！各馬ポジションを探り合います！`;
            if (simCommentarySub) simCommentarySub.textContent = `好スタートを切って先頭に躍り出たのは${leader.horse_number}番 ${leader.horse_name}！`;
        } else if (simProgress < 0.40) {
            updateStageHUD("backstretch");
            if (tvCornerBanner) tvCornerBanner.textContent = "向正面 (バックストレッチ)";
            if (simCommentaryHeadline) simCommentaryHeadline.textContent = `向正面を通過中！隊列が落ち着き、レースのペースを刻みます。`;
            if (simCommentarySub) simCommentarySub.textContent = `2番手には${second ? second.horse_name : "後続"}が追走！一団となって進みます！`;
        } else if (simProgress < 0.65) {
            updateStageHUD("corner3");
            if (tvCornerBanner) tvCornerBanner.textContent = "第3コーナー通過";
            if (simCommentaryHeadline) simCommentaryHeadline.textContent = `第3コーナーへ！各馬鞍上の手が動き始め、ペースアップ！`;
            if (simCommentarySub) simCommentarySub.textContent = `外から差し馬が進出を開始！勝負どころを迎えます！`;
        } else if (simProgress < 0.80) {
            updateStageHUD("corner4");
            if (tvCornerBanner) tvCornerBanner.textContent = "第4コーナー (最終カーブ)";
            if (simCommentaryHeadline) simCommentaryHeadline.textContent = `第4コーナーをカーブして直線の攻防へ！`;
            if (simCommentarySub) simCommentarySub.textContent = `先頭は依然として${leader.horse_name}！後続も外へ持ち出して追撃態勢！`;

            if (!leader.hasTriggeredSkill && simSkillPopup) {
                leader.hasTriggeredSkill = true;
                if (simSkillTitle) simSkillTitle.textContent = `【AI加速判定】${leader.horse_name}`;
                if (simSkillText) simSkillText.textContent = `【脚質: ${leader.running_style}】ラストスパート発動！`;
                simSkillPopup.classList.remove("d-none");
                setTimeout(() => simSkillPopup.classList.add("d-none"), 2500);
            }
        } else if (simProgress < 0.96) {
            updateStageHUD("straight");
            if (tvCornerBanner) tvCornerBanner.textContent = "最後の直線 (叩き合い)";
            if (simCommentaryHeadline) simCommentaryHeadline.textContent = `【最後の直線！】残り200m！激しい叩き合い！`;
            if (simCommentarySub) simCommentarySub.textContent = `${leader.horse_name}が粘るか！後続が怒涛の追い込み！`;
        } else {
            updateStageHUD("finish");
            if (tvCornerBanner) tvCornerBanner.textContent = "ゴールイン！";
            if (simCommentaryHeadline) simCommentaryHeadline.textContent = `【ゴールイン！】大歓声の中、激戦を制しました！`;
            if (simCommentarySub) simCommentarySub.textContent = `栄光の先頭ゴールは${leader.horse_number}番 ${leader.horse_name}！`;
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
        render3DScene();

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
