
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { CSS2DRenderer, CSS2DObject } from 'three/addons/renderers/CSS2DRenderer.js';
import { EffectComposer } from 'three/addons/postprocessing/EffectComposer.js';
import { RenderPass } from 'three/addons/postprocessing/RenderPass.js';
import { UnrealBloomPass } from 'three/addons/postprocessing/UnrealBloomPass.js';

console.log("3D Twin: module starting...");

// Configuration
const CONFIG = {
    POLL_INTERVAL: 2000,
    THRESHOLDS: { WARN: 85, CRITICAL: 95 },
    FALLBACK_POS: {
        TOP: new THREE.Vector3(0, 1.25, 0.2), // Near top bushing
        AMB: new THREE.Vector3(-0.8, 0.5, 0), // Left side
        BOT: new THREE.Vector3(0, 0.2, 0.5)   // Bottom front
    }
};

class DigitalTwinViewer {
    constructor(containerId) {
        this.container = document.getElementById(containerId);
        this.trafoId = window.TRAFO_ID || '1';
        this.startDate = '';
        this.endDate = '';
        this.mode = 'live';
        this.loadFactor = 1.0;
        this.chart = null;

        this.initScene();
        this.initLabels();
        this.createDetailedModel();
        this.initChart();

        this.fetchTransformers();

        this.animate();
        this.startPolling();

        window.addEventListener('resize', () => this.onResize());

        // UI Bindings
        document.getElementById('btn-live').onclick = () => this.setMode('live');
        document.getElementById('btn-demo').onclick = () => this.setMode('demo');

        // Load Factor slider
        const slider = document.getElementById('lf-slider');
        const display = document.getElementById('lf-display');
        if (slider && display) {
            slider.oninput = (e) => {
                this.loadFactor = parseFloat(e.target.value);
                display.innerText = this.loadFactor.toFixed(1);
                if (this.mode === 'demo') {
                    this.fetchLatest();
                    this.fetchHistory();
                }
            };
        }

        // Trafo & Date Filters
        this.trafoSelect = document.getElementById('trafo-select');
        this.startDateInput = document.getElementById('start-date');
        this.endDateInput = document.getElementById('end-date');
        this.btnApplyFilter = document.getElementById('btn-apply-filter');

        if (this.trafoSelect) {
            this.trafoSelect.onchange = (e) => {
                this.trafoId = e.target.value;
                this.updateLocationTag();
                this.fetchLatest();
                this.fetchHistory();
            };
        }

        if (this.btnApplyFilter) {
            this.btnApplyFilter.onclick = () => {
                this.startDate = this.startDateInput ? this.startDateInput.value : '';
                this.endDate = this.endDateInput ? this.endDateInput.value : '';
                this.updateStatusIndicator();
                this.fetchLatest();
                this.fetchHistory();
            };
        }

        const btnReset = document.getElementById('reset-date');
        if (btnReset) {
            btnReset.onclick = () => {
                if (this.startDateInput) this.startDateInput.value = '';
                if (this.endDateInput) this.endDateInput.value = '';
                this.startDate = '';
                this.endDate = '';
                this.updateStatusIndicator();
                this.fetchLatest();
                this.fetchHistory();
            };
        }
    }

    updateStatusIndicator() {
        const indicator = document.getElementById('status-indicator');
        const statusLine = document.getElementById('status-line');

        if (this.startDate || this.endDate) {
            let label = "TARİHSEL BAKIŞ";
            if (this.startDate && this.endDate) label = `ARALIK: ${this.startDate.replace('T', ' ')} - ${this.endDate.replace('T', ' ')}`;
            else if (this.startDate) label = `BASLANGIC: ${this.startDate.replace('T', ' ')}`;
            else label = `BITIS: ${this.endDate.replace('T', ' ')}`;

            const statusHtml = `
                <div style="width:8px; height:8px; background:#eab308; border-radius:50%; box-shadow:0 0 8px #eab308;"></div>
                ${label}
            `;
            if (indicator) {
                indicator.innerHTML = statusHtml;
                indicator.style.color = '#eab308';
            }
            if (statusLine) {
                statusLine.innerHTML = statusHtml;
                statusLine.style.color = '#eab308';
            }
        } else {
            const statusHtml = `
                <div style="width:8px; height:8px; background:var(--accent-green); border-radius:50%; box-shadow:0 0 8px var(--accent-green);"></div>
                CANLI BAĞLANTI
            `;
            if (indicator) {
                indicator.innerHTML = statusHtml;
                indicator.style.color = 'var(--accent-green)';
            }
            if (statusLine) {
                statusLine.innerHTML = statusHtml;
                statusLine.style.color = 'var(--accent-green)';
            }
        }
    }

    async authorizedFetch(url, options = {}) {
        if (!options.headers) options.headers = {};
        if (options.method && options.method !== 'GET') {
            const token = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content');
            if (token) options.headers['X-CSRFToken'] = token;
        }
        const res = await fetch(url, options);
        if (res.status === 401 || res.status === 403) {
            window.location.href = '/login';
            throw new Error("Unauthorized");
        }
        return res;
    }

    async fetchTransformers() {
        try {
            const res = await this.authorizedFetch('/api/transformers');
            const data = await res.json();
            if (this.trafoSelect) {
                this.trafoSelect.innerHTML = '';
                data.forEach(t => {
                    const opt = document.createElement('option');
                    opt.value = t.id;
                    opt.text = t.name.toUpperCase();
                    if (t.id == this.trafoId) opt.selected = true;
                    this.trafoSelect.appendChild(opt);
                });
                this.transformers = data;
                this.updateLocationTag();
            }
        } catch (e) { console.error("Fetch Transformers Error:", e); }
    }

    updateLocationTag() {
        const tag = document.getElementById('trafo-location-tag');
        if (tag && this.transformers) {
            const current = this.transformers.find(t => t.id == this.trafoId);
            if (current) tag.innerText = `• ${current.city_name || 'KONUM BELİRTİLMEDİ'}`.toUpperCase();
        }
    }

    setMode(mode) {
        this.mode = mode;
        document.getElementById('btn-live').classList.toggle('active', mode === 'live');
        document.getElementById('btn-demo').classList.toggle('active', mode === 'demo');

        // Toggle Sim Params UI
        const simParams = document.getElementById('sim-params');
        if (simParams) simParams.style.display = (mode === 'demo') ? 'block' : 'none';

        // Immediate refresh on mode switch
        this.fetchLatest();
        this.fetchHistory();
    }

    initScene() {
        this.scene = new THREE.Scene();
        this.scene.background = null;

        // Camera: Isometric-like high angle
        this.camera = new THREE.PerspectiveCamera(35, this.container.clientWidth / this.container.clientHeight, 0.1, 100);
        this.camera.position.set(3.5, 2.8, 3.5);
        this.camera.lookAt(0, 1.2, 0);

        this.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
        this.renderer.setSize(this.container.clientWidth, this.container.clientHeight);
        this.renderer.shadowMap.enabled = true;
        this.renderer.shadowMap.type = THREE.PCFSoftShadowMap;
        this.renderer.toneMapping = THREE.ACESFilmicToneMapping;
        this.renderer.toneMappingExposure = 1.1;
        this.container.appendChild(this.renderer.domElement);

        // Post Processing (Bloom)
        const renderScene = new RenderPass(this.scene, this.camera);
        const bloomPass = new UnrealBloomPass(new THREE.Vector2(this.container.clientWidth, this.container.clientHeight), 1.5, 0.4, 0.85);
        bloomPass.threshold = 0.3;
        bloomPass.strength = 0.6;
        bloomPass.radius = 0.5;

        this.composer = new EffectComposer(this.renderer);
        this.composer.addPass(renderScene);
        this.composer.addPass(bloomPass);

        // CSS2D Renderer for labels
        this.labelRenderer = new CSS2DRenderer();
        this.labelRenderer.setSize(this.container.clientWidth, this.container.clientHeight);
        this.labelRenderer.domElement.style.position = 'absolute';
        this.labelRenderer.domElement.style.top = '0px';
        this.labelRenderer.domElement.style.pointerEvents = 'none';
        this.container.appendChild(this.labelRenderer.domElement);

        // Lighting
        const amb = new THREE.AmbientLight(0xffffff, 0.8);
        this.scene.add(amb);

        // Main warm light (Sun)
        const dirLight = new THREE.DirectionalLight(0xffaa00, 3.0);
        dirLight.position.set(5, 8, 3);
        dirLight.castShadow = true;
        this.scene.add(dirLight);

        // Cool rim light (Cyberpunk feel)
        const spotRim = new THREE.SpotLight(0x0088ff, 100);
        spotRim.position.set(-3, 2, -3);
        this.scene.add(spotRim);

        // Base glow
        const pLight = new THREE.PointLight(0xff4d4d, 5, 10);
        pLight.position.set(0, 0.2, 0);
        this.scene.add(pLight);

        this.controls = new OrbitControls(this.camera, this.renderer.domElement);
        this.controls.enableDamping = true;
        this.controls.target.set(0, 1.2, 0);
        this.controls.autoRotate = true;
        this.controls.autoRotateSpeed = 0.8;
    }

    // --- Detailed Procedural Model ---
    createDetailedModel() {
        const group = new THREE.Group();

        // Materials
        const metalMat = new THREE.MeshStandardMaterial({ color: 0x8899a6, roughness: 0.3, metalness: 0.7 }); // Silver tank
        const finMat = new THREE.MeshStandardMaterial({ color: 0x6e7f8a, roughness: 0.5, metalness: 0.5 }); // Darker fins
        const porcelainMat = new THREE.MeshStandardMaterial({ color: 0x5c2e0e, roughness: 0.1, metalness: 0.1 }); // Brown glossy
        const brassMat = new THREE.MeshStandardMaterial({ color: 0xffd700, roughness: 0.3, metalness: 0.9 }); // Terminals
        const gaugeMat = new THREE.MeshBasicMaterial({ color: 0x111111 }); // Digital Screen Base

        // 1. Main Tank Body
        const tankGeo = new THREE.BoxGeometry(1.2, 0.9, 0.8);
        const tank = new THREE.Mesh(tankGeo, metalMat);
        tank.position.y = 0.55;
        tank.castShadow = true; tank.receiveShadow = true;
        group.add(tank);

        // 2. Cover Plate
        const coverGeo = new THREE.BoxGeometry(1.3, 0.05, 0.9);
        const cover = new THREE.Mesh(coverGeo, metalMat);
        cover.position.y = 1.0;
        cover.castShadow = true;
        group.add(cover);

        // 3. Corrugated Fins (Radiators) - Sides
        const finGeo = new THREE.BoxGeometry(0.02, 0.7, 0.2);
        for (let i = 0; i < 6; i++) {
            // Right Side
            let f1 = new THREE.Mesh(finGeo, finMat);
            f1.position.set(0.65, 0.55, -0.25 + i * 0.1);
            f1.rotation.y = Math.PI / 2;
            f1.castShadow = true;
            group.add(f1);

            // Left Side
            let f2 = new THREE.Mesh(finGeo, finMat);
            f2.position.set(-0.65, 0.55, -0.25 + i * 0.1);
            f2.rotation.y = Math.PI / 2;
            f2.castShadow = true;
            group.add(f2);

            // Front Side
            let f3 = new THREE.Mesh(finGeo, finMat);
            f3.position.set(-0.4 + i * 0.16, 0.5, 0.45);
            f3.scale.set(1, 0.8, 1); // Shorter
            f3.castShadow = true;
            group.add(f3);
        }

        // 4. HV Bushings (High Voltage - Brown)
        // Array of 3 large bushings
        const bushPositions = [[-0.3, 1.05, 0], [0, 1.05, 0.1], [0.3, 1.05, 0]];
        bushPositions.forEach((pos, idx) => {
            const bGroup = new THREE.Group();

            // Base pipe
            const pipe = new THREE.Mesh(new THREE.CylinderGeometry(0.06, 0.06, 0.6, 16), porcelainMat);
            pipe.position.y = 0.3;
            bGroup.add(pipe);

            // Skirts (Discs)
            for (let j = 0; j < 5; j++) {
                const skirt = new THREE.Mesh(new THREE.CylinderGeometry(0.14, 0.14, 0.03, 16), porcelainMat);
                skirt.position.y = 0.1 + j * 0.1;
                skirt.castShadow = true;
                bGroup.add(skirt);
            }

            // Terminal (Brass)
            const term = new THREE.Mesh(new THREE.CylinderGeometry(0.02, 0.02, 0.1, 16), brassMat);
            term.position.y = 0.65;
            bGroup.add(term);

            bGroup.position.set(...pos);
            // Slight tilt pattern for realism (optional)
            if (idx === 0) bGroup.rotation.z = 0.1;
            if (idx === 2) bGroup.rotation.z = -0.1;

            group.add(bGroup);
        });

        // 5. LV Bushings (Low Voltage - Smaller)
        // Array of 4 small bushings at the front
        for (let k = 0; k < 4; k++) {
            const sk = new THREE.Mesh(new THREE.CylinderGeometry(0.04, 0.04, 0.2, 16), porcelainMat);
            sk.position.set(-0.3 + k * 0.2, 1.1, 0.3);
            sk.castShadow = true;
            group.add(sk);
        }

        // 6. Control Box (Digital Unit)
        const boxGeo = new THREE.BoxGeometry(0.3, 0.2, 0.1);
        const box = new THREE.Mesh(boxGeo, metalMat);
        box.position.set(0.5, 0.3, 0.45);
        group.add(box);

        // Screen (Glowing)
        const screen = new THREE.Mesh(new THREE.PlaneGeometry(0.2, 0.1), new THREE.MeshBasicMaterial({ color: 0xff0000 }));
        screen.position.set(0.5, 0.3, 0.501);
        group.add(screen);

        // Add lifting lugs
        const lugGeo = new THREE.TorusGeometry(0.05, 0.01, 8, 16);
        const lug1 = new THREE.Mesh(lugGeo, metalMat); lug1.position.set(0, 1.05, 0.4); group.add(lug1);

        this.scene.add(group);
        this.tankMesh = tank; // For reference if we want heat shader later
    }

    initLabels() {
        this.labels = {};

        ['TOP', 'AMB', 'BOT'].forEach(key => {
            const div = document.createElement('div');
            // CSS Structure for Label from twin.html css
            div.className = 'sensor-label-container';
            div.innerHTML = `
                <div class="sensor-ring" id="ring-${key}">--</div>
                <div class="sensor-value-tag" id="tag-${key}">-- °C</div>
            `;

            // Style locally for 3D overlay context (override absolute 2D)
            div.style.display = 'flex';
            div.style.alignItems = 'center';
            div.style.pointerEvents = 'none';
            // Inner styles handled by CSS class in twin.html (we restored them? Need to check css)
            // If removed, we need to inject styles.

            const labelObj = new CSS2DObject(div);
            labelObj.position.copy(CONFIG.FALLBACK_POS[key]);
            this.scene.add(labelObj);

            this.labels[key] = {
                obj: labelObj,
                ring: div.querySelector('.sensor-ring'),
                tag: div.querySelector('.sensor-value-tag')
            };
        });
    }

    initChart() {
        const ctx = document.getElementById('trendChart').getContext('2d');
        Chart.defaults.color = '#94a3b8';
        Chart.defaults.borderColor = 'rgba(255,255,255,0.1)';

        try {
            this.chart = new Chart(ctx, {
                type: 'line',
                data: {
                    labels: [],
                    datasets: [
                        { label: 'Top Oil', data: [], borderColor: '#ff4d4d', tension: 0.4 },
                        { label: 'Ambient', data: [], borderColor: '#2ecc71', tension: 0.4 }
                    ]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: { legend: { display: false } },
                    scales: { x: { ticks: { maxTicksLimit: 5 } }, y: {} },
                    animation: false
                }
            });
        } catch (e) {
            console.error("Chart.js could not be initialized:", e);
        }
    }

    onResize() {
        this.camera.aspect = this.container.clientWidth / this.container.clientHeight;
        this.camera.updateProjectionMatrix();
        this.renderer.setSize(this.container.clientWidth, this.container.clientHeight);
        this.composer.setSize(this.container.clientWidth, this.container.clientHeight);
        this.labelRenderer.setSize(this.container.clientWidth, this.container.clientHeight);
    }

    animate() {
        requestAnimationFrame(() => this.animate());
        this.controls.update();
        this.composer.render();
        this.labelRenderer.render(this.scene, this.camera);
    }

    startPolling() {
        setInterval(() => {
            if (this.mode === 'live') {
                this.fetchLatest();
                this.fetchHistory();
            }
        }, CONFIG.POLL_INTERVAL);

        if (this.mode === 'live') { this.fetchLatest(); this.fetchHistory(); }
    }

    async fetchLatest() {
        const id = this.trafoId;
        let url = `/api/twin/latest?trafo_id=${id}`;

        if (this.startDate) url += `&start_date=${this.startDate}`;
        if (this.endDate) url += `&end_date=${this.endDate}`;

        if (this.mode === 'demo') {
            url = `/api/simulation/hermetic?trafo_id=${id}&load_factor=${this.loadFactor}`;
        }

        try {
            const res = await this.authorizedFetch(url);
            const raw = await res.json();

            // Map data if from simulation engine
            let data = raw;
            if (this.mode === 'demo' && raw.data && raw.data.length > 0) {
                const latest = raw.data[raw.data.length - 1]; // Last row is latest
                data = {
                    top_oil_c: latest.hermetic_top_oil_C,
                    ambient_c: latest.sensor2,
                    bottom_oil_c: latest.hermetic_bottom_oil_C,
                    ts: Date.now() / 1000
                };
            }

            this.updateView(data);
        } catch (e) {
            console.error("Fetch Latest Error:", e);
        }
    }

    async fetchHistory() {
        const id = this.trafoId;
        let url = `/api/twin/history?trafo_id=${id}`;

        if (this.startDate) url += `&start_date=${this.startDate}`;
        if (this.endDate) url += `&end_date=${this.endDate}`;

        if (this.mode === 'demo') {
            url = `/api/simulation/hermetic?trafo_id=${id}&load_factor=${this.loadFactor}`;
        }

        try {
            const res = await this.authorizedFetch(url);
            const raw = await res.json();

            if (this.mode === 'demo' && raw.data) {
                // Map simulation array to Chart.js format
                const labels = raw.data.map(r => (r.sensor_timestamp || "").split(' ')[1]?.substring(0, 5) || "");
                const topOil = raw.data.map(r => r.hermetic_top_oil_C);
                const amb = raw.data.map(r => r.sensor2);
                const botOil = raw.data.map(r => r.hermetic_bottom_oil_C);

                this.chart.data.labels = labels.slice(-20); // Keep last 20
                this.chart.data.datasets[0].data = topOil.slice(-20);
                this.chart.data.datasets[1].data = amb.slice(-20);
                // Optionally add/manage more datasets if the chart layout allows
                this.chart.update('none');
            } else if (this.chart && raw.labels) {
                this.chart.data.labels = raw.labels;
                this.chart.data.datasets = raw.datasets;
                this.chart.update('none');
            }
        } catch (e) {
            console.error("Fetch History Error:", e);
        }
    }

    updateView(data) {
        const top = data.top_oil_c || 0;
        const amb = data.ambient_c || 0;
        const bot = data.bottom_oil_c || 0;
        const deltaTo = top - amb;
        const deltaVert = top - bot;

        // 1. Update Labels
        this.updateLabel('TOP', top);
        this.updateLabel('AMB', amb);
        this.updateLabel('BOT', bot);

        // 2. Metrics
        const setVal = (id, v) => { const el = document.getElementById(id); if (el) el.innerText = v.toFixed(1); };
        setVal('val-top', top);
        setVal('val-amb', amb);
        setVal('val-amb-2', amb);
        setVal('val-bot', bot);
        setVal('val-delta-to', deltaTo);
        setVal('val-delta-rise', deltaTo);
        setVal('val-delta-vert', deltaVert);
        setVal('val-delta-vert-2', deltaVert);

        const elUpdate = document.getElementById('last-update');
        if (elUpdate) elUpdate.innerText = new Date().toLocaleTimeString();

        // 3. Alerts
        const alertBox = document.getElementById('alert-box');
        const emptyBox = document.getElementById('no-alerts');
        const alertVal = document.getElementById('alert-val');
        if (alertBox && emptyBox) {
            if (top > CONFIG.THRESHOLDS.WARN) {
                alertBox.style.display = 'block';
                emptyBox.style.display = 'none';
                alertVal.innerText = top.toFixed(1);
            } else {
                alertBox.style.display = 'none';
                emptyBox.style.display = 'block';
            }
        }
    }

    updateLabel(key, val) {
        const label = this.labels[key];
        if (!label) return;

        label.ring.innerText = Math.round(val);
        label.tag.innerText = val.toFixed(1) + " °C";

        let color = '#2ecc71';
        if (val >= CONFIG.THRESHOLDS.CRITICAL) color = '#ff4d4d';
        else if (val >= CONFIG.THRESHOLDS.WARN) color = '#eab308';

        label.ring.style.borderColor = color;
        label.ring.style.boxShadow = `0 0 15px ${color}, inset 0 0 10px ${color}`;
        label.tag.style.borderColor = color;
    }
}

document.addEventListener('DOMContentLoaded', () => {
    if (document.getElementById('viewer-area')) {
        new DigitalTwinViewer('viewer-area');
    }
});
