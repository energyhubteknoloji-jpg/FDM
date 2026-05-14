document.addEventListener('DOMContentLoaded', () => {
    console.log("Modern UI v3 Loaded");
    // State
    let isRunning = false;
    let chartInstance = null;
    let currentPage = 1;
    let limit = 100;
    let simChartInstance = null;

    // Multi-Transformer State
    let currentTrafoId = null;
    let transformers = [];

    // Elements
    const btnScrape = document.getElementById('btn-scrape');
    const btnToggleAuto = document.getElementById('btn-toggle-auto');
    const btnSettings = document.getElementById('btn-settings');
    const modalSettings = document.getElementById('settings-modal');
    const btnCloseSettings = document.getElementById('btn-close-settings');

    // Transformer UI Elements
    const trafoSelect = document.getElementById('trafo-select');
    const trafoList = document.getElementById('trafo-list');
    const btnAddNewTrafo = document.getElementById('btn-add-new-trafo');
    const trafoFormContainer = document.getElementById('trafo-form-container');
    const btnSaveTrafo = document.getElementById('btn-save-trafo');
    const btnCancelForm = document.getElementById('btn-cancel-form');

    const tableBody = document.querySelector('#data-table tbody');
    const statusIndicator = document.getElementById('service-status');
    const ctx = document.getElementById('tempChart').getContext('2d');

    // Simulation Elements
    const sliderLoadFactor = document.getElementById('slider-load-factor');
    const lblLoadFactor = document.getElementById('lbl-load-factor');
    const btnRefreshSim = document.getElementById('btn-refresh-sim');
    const btnExportSim = document.getElementById('btn-export-sim');
    const btnExport = document.getElementById('btn-export');
    const ctxSim = document.getElementById('simChart').getContext('2d');
    const simStartDate = document.getElementById('sim-start-date');
    const simEndDate = document.getElementById('sim-end-date');

    // Excel Export Modal Elements
    const modalExport = document.getElementById('export-modal');
    const btnCloseExport = document.getElementById('btn-close-export');
    const btnConfirmExport = document.getElementById('btn-confirm-export');
    const exportYear = document.getElementById('export-year');
    const exportMonth = document.getElementById('export-month');

    // Sync currentTrafoId on load if dropdown has a value (e.g. from browser)
    if (trafoSelect && trafoSelect.value) {
        currentTrafoId = trafoSelect.value;
    }

    // Initialize Dates (Default: Today and Yesterday?)
    // Actually, for better view, maybe last 3 days?
    const today = new Date();
    const yesterday = new Date();
    yesterday.setDate(today.getDate() - 1);

    // Format YYYY-MM-DDTHH:MM (Local Time)
    const pad = n => n.toString().padStart(2, '0');
    const fmt = d => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;

    if (simEndDate) simEndDate.value = fmt(today);
    if (simStartDate) {
        const startOfYesterday = new Date(yesterday);
        startOfYesterday.setHours(0, 0, 0, 0);
        simStartDate.value = fmt(startOfYesterday);
    }

    // Pagination Elements
    const btnPrev = document.getElementById('btn-prev');
    const btnNext = document.getElementById('btn-next');
    const pageInfo = document.getElementById('page-info');

    // Chart Init
    try {
        chartInstance = new Chart(ctx, {
            type: 'line',
            data: {
                labels: [],
                datasets: [
                    { label: 'Üst Yağ Sıcaklığı', borderColor: '#ef4444', data: [], fill: false }, // Red 500
                    { label: 'Ortam Sıcaklığı', borderColor: '#0ea5e9', data: [], fill: false },   // Sky 500
                    { label: 'Alt Yağ Sıcaklığı', borderColor: '#f59e0b', data: [], fill: false }, // Amber 500
                    { label: 'Dış Sıcaklık', borderColor: '#10b981', data: [], fill: false, borderDash: [5, 5] } // Emerald 500
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    x: { display: true },
                    y: { beginAtZero: false }
                }
            }
        });

        // Sub-Chart for Simulation
        simChartInstance = new Chart(ctxSim, {
            type: 'line',
            data: {
                labels: [],
                datasets: [
                    { label: 'FDM Üst Yağ', borderColor: '#ef4444', data: [], fill: false, borderWidth: 1 }, // Red 500
                    { label: 'Hermetik Üst Yağ', borderColor: '#b91c1c', data: [], fill: false, borderDash: [5, 5] }, // Red 700
                    { label: 'FDM Alt Yağ', borderColor: '#f59e0b', data: [], fill: false, borderWidth: 1 }, // Amber 500
                    { label: 'Hermetik Alt Yağ', borderColor: '#c2410c', data: [], fill: false, borderDash: [5, 5] }, // Orange 700
                    { label: 'Ortam', borderColor: '#0ea5e9', data: [], fill: false, borderWidth: 1, pointRadius: 0 } // Sky 500
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: { x: { display: true }, y: { beginAtZero: false } }
            }
        });
    } catch (e) {
        console.error("Chart.js could not be initialized:", e);
    }

    // --- Helper for Auth ---
    async function authorizedFetch(url, options = {}) {
        if (!options.headers) options.headers = {};

        // Add CSRF token for non-GET requests
        if (options.method && options.method !== 'GET') {
            const csrfToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content');
            if (csrfToken) {
                options.headers['X-CSRFToken'] = csrfToken;
            }
        }

        const res = await fetch(url, options);
        if (res.status === 401 || res.status === 403) {
            window.location.href = '/login';
            throw new Error("Unauthorized");
        }
        return res;
    }

    // --- API Calls ---

    async function loadTransformers() {
        try {
            const res = await authorizedFetch('/api/transformers');
            transformers = await res.json();

            // Populate Dropdown
            let selectedValue = trafoSelect.value;
            trafoSelect.innerHTML = '<option value="" disabled selected>Trafo Seçiniz...</option>';

            transformers.forEach(t => {
                const opt = document.createElement('option');
                opt.value = t.id;
                opt.innerText = t.name;
                trafoSelect.appendChild(opt);
            });

            // Restore selection or select first
            if (transformers.length > 0) {
                if (currentTrafoId && transformers.find(t => t.id == currentTrafoId)) {
                    trafoSelect.value = currentTrafoId;
                } else if (!currentTrafoId) {
                    currentTrafoId = transformers[0].id;
                    trafoSelect.value = currentTrafoId;
                    currentPage = 1;
                    loadData(1); // Load data for default
                }
            } else {
                currentTrafoId = null;
                // clear table?
            }

            // Populate Manager List
            window.renderTrafoList();

        } catch (e) {
            console.error("Error loading transformers", e);
        }
    }

    async function loadStatus() {
        try {
            const res = await authorizedFetch('/api/status'); // Status might be public, but let's check
            const data = await res.json();
            isRunning = data.running;

            // Update Running/Stopped UI
            // Check if buttons exist (admin only)
            if (btnToggleAuto) {
                if (isRunning) {
                    btnToggleAuto.innerText = "Otomatik Durdur";
                    btnToggleAuto.classList.remove('secondary');
                    btnToggleAuto.classList.add('danger');
                    btnToggleAuto.style.backgroundColor = '#ef4444';
                } else {
                    btnToggleAuto.innerText = "Otomatik Başlat";
                    btnToggleAuto.style.backgroundColor = '';
                    btnToggleAuto.classList.remove('danger');
                    btnToggleAuto.classList.add('secondary');
                }
            }

            if (statusIndicator) {
                if (isRunning) {
                    statusIndicator.innerText = "Servis Çalışıyor";
                    statusIndicator.classList.remove('stopped');
                    statusIndicator.classList.add('running');
                } else {
                    statusIndicator.innerText = "Servis Durdu";
                    statusIndicator.classList.remove('running');
                    statusIndicator.classList.add('stopped');
                }
            }

            // Update Last Update Display for current transformer (in controls)
            const lastUpdateDisplay = document.getElementById('last-update-display');
            if (lastUpdateDisplay) {
                if (currentTrafoId && data.last_updates && data.last_updates[currentTrafoId]) {
                    lastUpdateDisplay.innerText = `Son Güncelleme: ${data.last_updates[currentTrafoId]}`;
                } else {
                    lastUpdateDisplay.innerText = `Son Güncelleme: -`;
                }
            }

        } catch (e) {
            console.error("Status check failed", e);
        }
    }

    async function loadData(page = 1) {
        if (!currentTrafoId) return;

        const startDate = document.getElementById('filter-start-date').value;
        const endDate = document.getElementById('filter-end-date').value;
        const searchFilter = document.getElementById('filter-search').value;

        let url = `/api/data?page=${page}&limit=${limit}&trafo_id=${currentTrafoId}`;
        if (startDate) url += `&start_date=${startDate}`;
        if (endDate) url += `&end_date=${endDate}`;
        if (searchFilter) url += `&search=${searchFilter}`;

        try {
            const res = await authorizedFetch(url);
            const jsonResponse = await res.json();

            const data = jsonResponse.data || [];
            const pagination = jsonResponse.pagination;

            updateTable(data);
            updateChart(data);

            if (pagination) {
                currentPage = pagination.page;
                updatePaginationControls(pagination);

                // Update info text
                if (pageInfo) {
                    pageInfo.innerText = `Sayfa ${pagination.page} / ${pagination.pages} (Toplam: ${pagination.total})`;
                }
            }

        } catch (e) {
            console.error("Error loading data", e);
        }
    }

    async function toggleAuto() {
        if (!btnToggleAuto) return;
        const newState = !isRunning;
        try {
            const res = await authorizedFetch('/api/toggle-auto', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ state: newState })
            });
            const data = await res.json();
            isRunning = data.running;
            loadStatus(); // refresh UI
        } catch (e) { console.error(e); }
    }

    async function manualScrape() {
        if (!currentTrafoId) {
            alert("Lütfen bir trafo seçiniz.");
            return;
        }
        if (!btnScrape) return;

        btnScrape.disabled = true;
        btnScrape.innerText = "Çekiliyor...";
        try {
            const res = await authorizedFetch('/api/scrape', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ trafo_id: currentTrafoId })
            });
            const data = await res.json();
            if (data.status === 'success') {
                alert("Veri başarıyla çekildi!");
                loadData(1);
                loadStatus(); // update timestamp
            } else {
                alert("Hata: " + data.message);
            }
        } catch (e) {
            alert("İşlem başarısız (Yetki veya Bağlantı).");
        } finally {
            if (btnScrape) {
                btnScrape.disabled = false;
                btnScrape.innerText = "Anlık Veri Çek";
            }
        }
    }

    async function loadSimulationData() {
        if (!currentTrafoId) return;

        const lf = sliderLoadFactor.value;
        const sDate = simStartDate.value;
        const eDate = simEndDate.value;

        btnRefreshSim.innerText = "Hesaplanıyor...";

        try {
            let url = `/api/simulation/hermetic?trafo_id=${currentTrafoId}&load_factor=${lf}`;
            if (sDate) url += `&start_date=${sDate}`;
            if (eDate) url += `&end_date=${eDate}`;

            const res = await authorizedFetch(url);
            const json = await res.json();
            const data = json.data || [];

            updateSimChart(data);
            updateKPIs(data);

        } catch (e) {
            console.error("Simulation error", e);
            if (e.message !== "Unauthorized") alert("Simülasyon hatası: " + e);
        } finally {
            btnRefreshSim.innerText = "Hesapla";
        }
    }

    function updateSimChart(data) {
        // Data is chronological (oldest first) coming from simulation engine
        // Chart expects chronological.

        const labels = [];
        const fdmTop = [];
        const hermeticTop = [];
        const fdmBottom = [];
        const hermeticBottom = [];
        const ambient = [];

        data.forEach(r => {
            const d = new Date(r.sensor_timestamp || r.time);
            labels.push(d.toLocaleTimeString());
            fdmTop.push(parseFloat(r.sensor1));
            hermeticTop.push(parseFloat(r.hermetic_top_oil_C));
            fdmBottom.push(parseFloat(r.sensor3));
            hermeticBottom.push(parseFloat(r.hermetic_bottom_oil_C));
            ambient.push(parseFloat(r.sensor2));
        });

        simChartInstance.data.labels = labels;
        simChartInstance.data.datasets[0].data = fdmTop;
        simChartInstance.data.datasets[1].data = hermeticTop;
        simChartInstance.data.datasets[2].data = fdmBottom;
        simChartInstance.data.datasets[3].data = hermeticBottom;
        simChartInstance.data.datasets[4].data = ambient;
        simChartInstance.update();
    }

    function updateKPIs(data) {
        if (!data || data.length === 0) return;

        // Last point
        const last = data[data.length - 1];

        document.getElementById('kpi-delta-top').innerText = last.delta_top_C || '-';
        document.getElementById('kpi-delta-bottom').innerText = last.delta_bottom_C || '-';
        document.getElementById('kpi-hermetic-top').innerText = last.hermetic_top_oil_C || '-';
        document.getElementById('kpi-hermetic-bottom').innerText = last.hermetic_bottom_oil_C || '-';
    }

    // --- Transformer Management Functions ---

    // --- Map Logic ---
    let map = null;
    let marker = null;

    window.initMap = function () {
        console.log("initMap called. Current map state:", map ? "Initialized" : "Null");

        if (!document.getElementById('map')) {
            console.error("Map container element #map not found in DOM!");
            return;
        }

        if (!map) {
            try {
                console.log("Initializing Leaflet map...");
                // Default center: Turkey
                map = L.map('map').setView([39.9334, 32.8597], 6);
                L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
                    attribution: '&copy; OpenStreetMap contributors'
                }).addTo(map);

                map.on('click', function (e) {
                    setMarker(e.latlng.lat, e.latlng.lng, "Seçilen Konum");
                });
                console.log("Map initialized successfully.");
            } catch (e) {
                console.error("Error creating Leaflet map:", e);
                // If "Map container is already initialized" error, we might need to handle it, 
                // but checking (!map) usually prevents this unless map var was reset.
            }
        }

        // Leaflet needs visible container to size correctly
        setTimeout(() => {
            if (map) {
                map.invalidateSize();
                console.log("Map size invalidated.");
            }
        }, 100);
    };

    function setMarker(lat, lng, name) {
        if (!map) return; // Safety

        if (marker) {
            marker.setLatLng([lat, lng]);
        } else {
            marker = L.marker([lat, lng]).addTo(map);
        }

        document.getElementById('t-lat').value = lat;
        document.getElementById('t-lon').value = lng;

        // Optional: Update display name if not generic
        if (name && name !== "Seçilen Konum") {
            document.getElementById('t-city').value = name;
        } else {
            // Keep existing text or show coords if empty
            const currentVal = document.getElementById('t-city').value;
            if (!currentVal || currentVal.includes("Seçilen")) {
                document.getElementById('t-city').value = `Seçilen (${lat.toFixed(4)}, ${lng.toFixed(4)})`;
            }
        }
    }

    window.searchLocation = async function () {
        // Ensure map is init
        if (!map) {
            console.warn("Map not initialized when searching. Attempting init...");
            window.initMap();
            if (!map) {
                alert("Harita yüklenemedi. Lütfen sayfayı yenileyip tekrar deneyin.");
                return;
            }
        }

        const query = document.getElementById('loc-search').value;
        if (!query) return;

        // Visual feedback
        const btn = document.querySelector('#loc-search').nextElementSibling;
        const originalText = btn.innerText;
        btn.innerText = "Ara...";
        btn.disabled = true;

        try {
            // Added limit and accept-language
            const url = `https://nominatim.openstreetmap.org/search?format=json&q=${encodeURIComponent(query)}&limit=5&accept-language=tr`;

            const res = await fetch(url);

            if (!res.ok) {
                throw new Error(`Sunucu Hatası: ${res.status}`);
            }

            const data = await res.json();

            if (data && data.length > 0) {
                const lat = parseFloat(data[0].lat);
                const lon = parseFloat(data[0].lon);
                // Simplify display name for better UX
                let displayName = data[0].display_name;

                map.setView([lat, lon], 12);
                setMarker(lat, lon, displayName);
                // document.getElementById('t-city').value = displayName; // setMarker already does this
            } else {
                alert("Konum bulunamadı. Lütfen il/ilçe adını kontrol edin.");
            }
        } catch (e) {
            console.error("Geocoding error:", e);
            alert("Arama sırasında hata oluştu: " + e.message);
        } finally {
            btn.innerText = originalText;
            btn.disabled = false;
        }
    };

    // Bind Search Enter Key
    const locInput = document.getElementById('loc-search');
    if (locInput) {
        locInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault(); // Prevent form submit
                window.searchLocation();
            }
        });
    }


    // --- Transformer Management Functions ---

    window.renderTrafoList = function() {
        if (!trafoList) return;
        trafoList.innerHTML = '';
        
        // Use global escapeHTML if available, otherwise define a local fallback
        const esc = window.escapeHTML || function(str) {
            if (!str) return '';
            return String(str).replace(/[&<>'"]/g, t => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[t]));
        };

        transformers.forEach(t => {
            const li = document.createElement('li');
            li.className = 'trafo-item';

            let locInfo = '';
            if (t.city_name) locInfo = `📍 ${esc(t.city_name)}`;
            else if (t.latitude) locInfo = `📍 ${t.latitude.toFixed(2)}, ${t.longitude.toFixed(2)}`;

            li.innerHTML = `
                <div class="trafo-info">
                    <div style="font-weight: bold;">${esc(t.name)}</div>
                    <div class="trafo-detail">${esc(t.url)}</div>
                    <div class="trafo-detail" style="color: #2980b9; font-size: 0.85em;">${locInfo}</div>
                </div>
                <div class="trafo-actions">
                    <button class="btn small outline btn-edit-trafo" data-id="${t.id}">Düzenle</button>
                    <button class="btn small danger btn-delete-trafo" data-id="${t.id}">Sil</button>
                </div>
            `;
            trafoList.appendChild(li);
        });

        // Items bind events delegated or here
        document.querySelectorAll('.btn-edit-trafo').forEach(b => {
            b.addEventListener('click', (e) => editTrafo(e.target.dataset.id));
        });
        document.querySelectorAll('.btn-delete-trafo').forEach(b => {
            b.addEventListener('click', (e) => deleteTrafo(e.target.dataset.id));
        });
    }

    function editTrafo(id) {
        const t = transformers.find(tx => tx.id == id);
        if (!t) return;

        document.getElementById('edit-trafo-id').value = t.id;
        document.getElementById('t-name').value = t.name;
        document.getElementById('t-url').value = t.url;
        document.getElementById('t-username').value = t.username || 'admin';
        document.getElementById('t-city').value = t.city_name || '';
        document.getElementById('t-lat').value = t.latitude || '';
        document.getElementById('t-lon').value = t.longitude || '';
        document.getElementById('t-password').value = ''; // Don't show password
        document.getElementById('form-title').innerText = "Trafo Düzenle";

        trafoFormContainer.classList.remove('hidden');
        document.querySelector('.trafo-list-container').classList.add('hidden'); // Hide list

        // Init Map
        window.initMap();

        // Use timeout to allow map to init before flying
        setTimeout(() => {
            if (t.latitude && t.longitude) {
                map.setView([t.latitude, t.longitude], 12);
                setMarker(t.latitude, t.longitude, t.city_name);
            } else {
                // Default view if no loc
                map.setView([39.9334, 32.8597], 6);
                if (marker) marker.remove();
                marker = null;
            }
        }, 200);
    }

    async function deleteTrafo(id) {
        if (!confirm("Bu trafoyu silmek istediğinize emin misiniz?")) return;

        try {
            const res = await authorizedFetch(`/api/transformers/${id}`, { method: 'DELETE' });
            const data = await res.json();
            if (data.status === 'success') {
                await loadTransformers();
            } else {
                alert("Silme başarısız: " + data.message);
            }
        } catch (e) {
            alert("Hata oluştu: " + e);
        }
    }

    async function saveTransformer() {
        const id = document.getElementById('edit-trafo-id').value;
        const name = document.getElementById('t-name').value;
        const url = document.getElementById('t-url').value;
        const username = document.getElementById('t-username').value;
        const password = document.getElementById('t-password').value;
        const city_name = document.getElementById('t-city').value;
        const latitude = document.getElementById('t-lat').value;
        const longitude = document.getElementById('t-lon').value;

        if (!name || !url || !username) {
            alert("Lütfen tüm alanları doldurunuz.");
            return;
        }

        const payload = {
            name, url, username, password, city_name,
            latitude: latitude ? parseFloat(latitude) : null,
            longitude: longitude ? parseFloat(longitude) : null
        };

        let urlApi = '/api/transformers';
        let method = 'POST';

        if (id) {
            urlApi += `/${id}`;
            method = 'PUT';
        } else {
            if (!password) {
                alert("Yeni trafo için şifre gereklidir.");
                return;
            }
        }

        try {
            const res = await authorizedFetch(urlApi, {
                method: method,
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            const data = await res.json();

            if (data.status === 'success') {
                alert("Kaydedildi.");
                trafoFormContainer.classList.add('hidden');
                document.querySelector('.trafo-list-container').classList.remove('hidden'); // Show list
                await loadTransformers();
            } else {
                alert("Hata: " + data.message);
            }
        } catch (e) {
            alert("Kaydetme hatası: " + e);
        }
    }

    // --- UI Helpers ---

    function updateTable(data) {
        tableBody.innerHTML = '';
        const esc = window.escapeHTML || function(str) {
            if (!str) return '';
            return String(str).replace(/[&<>'"]/g, t => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[t]));
        };
        data.forEach(row => {
            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td>${esc(row.id) || '-'}</td>
                <td>${esc(row.time) || '-'}</td>
                <td>${esc(row.sensor1) || '-'}</td>
                <td>${esc(row.sensor2) || '-'}</td>
                <td>${esc(row.sensor3) || '-'}</td>
                <td>${row.weather_temp ? esc(row.weather_temp) + ' °C' : '-'}</td>
            `;
            tableBody.appendChild(tr);
        });
    }

    function updatePaginationControls(pagination) {
        pageInfo.innerText = `Sayfa ${pagination.page} / ${pagination.pages || 1}`;
        btnPrev.disabled = pagination.page <= 1;
        btnNext.disabled = pagination.page >= pagination.pages;
    }

    function updateChart(data) {
        const chartData = [...data].reverse();
        const labels = [];
        const s1 = [], s2 = [], s3 = [], w = [];

        chartData.forEach(row => {
            const d = new Date(row.time);
            labels.push(d.toLocaleTimeString());
            s1.push(parseFloat(row.sensor1));
            s2.push(parseFloat(row.sensor2));
            s3.push(parseFloat(row.sensor3));
            w.push(row.weather_temp ? parseFloat(row.weather_temp) : null);
        });

        chartInstance.data.labels = labels;
        chartInstance.data.datasets[0].data = s1;
        chartInstance.data.datasets[1].data = s2;
        chartInstance.data.datasets[2].data = s3;
        chartInstance.data.datasets[3].data = w;
        chartInstance.update();
    }

    // --- Events ---
    if (btnScrape) btnScrape.addEventListener('click', manualScrape);
    if (btnToggleAuto) btnToggleAuto.addEventListener('click', toggleAuto);

    // Excel Export (Main Dashboard)
    if (btnExport) {
        btnExport.addEventListener('click', () => {
            if (!currentTrafoId) {
                alert("Lütfen önce bir trafo seçiniz.");
                return;
            }
            modalExport.classList.remove('hidden');
        });

        // Modal Specific Buttons
        if (btnConfirmExport) {
            btnConfirmExport.addEventListener('click', async () => {
                const year = exportYear.value;
                const month = exportMonth.value;

                let url = `/api/export?trafo_id=${currentTrafoId}`;
                if (year) url += `&year=${year}`;
                if (month) url += `&month=${month}`;

                console.log("Triggering Excel Export:", { trafo_id: currentTrafoId, year, month, url });

                try {
                    const res = await fetch('/api/status');
                    if (!res.ok) {
                        window.location.href = '/login';
                        return;
                    }

                    // Hide modal
                    modalExport.classList.add('hidden');

                    // Success!
                    window.location.href = url;
                } catch (err) {
                    console.error("Export Error:", err);
                    alert("Dışa aktarma başlatılamadı.");
                }
            });
        }

        if (btnCloseExport) {
            btnCloseExport.addEventListener('click', () => {
                modalExport.classList.add('hidden');
            });
        }
    }

    // Settings / Trafo Management (Now handled in inline script)

    // Trafo CRUD
    if (btnAddNewTrafo) {
        btnAddNewTrafo.addEventListener('click', () => {
            document.getElementById('edit-trafo-id').value = '';
            document.getElementById('t-name').value = '';
            document.getElementById('t-url').value = '';
            document.getElementById('t-username').value = 'admin';
            document.getElementById('t-city').value = '';
            document.getElementById('t-lat').value = '';
            document.getElementById('t-lon').value = '';
            document.getElementById('t-password').value = '';
            document.getElementById('form-title').innerText = "Yeni Trafo Ekle";

            trafoFormContainer.classList.remove('hidden');
            document.querySelector('.trafo-list-container').classList.add('hidden'); // Hide list

            // Init Map and Reset View
            window.initMap();
            setTimeout(() => {
                map.setView([39.9334, 32.8597], 6);
                if (marker) marker.remove();
                marker = null;
            }, 100);
        });
    }

    if (btnCancelForm) {
        btnCancelForm.addEventListener('click', () => {
            trafoFormContainer.classList.add('hidden');
            document.querySelector('.trafo-list-container').classList.remove('hidden'); // Show list
        });
    }

    if (btnSaveTrafo) btnSaveTrafo.addEventListener('click', saveTransformer);

    // Selection Change
    trafoSelect.addEventListener('change', (e) => {
        currentTrafoId = e.target.value;
        currentPage = 1;
        loadData(1);
        loadStatus();
    });

    // Pagination
    btnPrev.addEventListener('click', () => { if (currentPage > 1) loadData(currentPage - 1); });
    btnNext.addEventListener('click', () => { loadData(currentPage + 1); });

    // --- Filter Logic ---
    const filterStartDate = document.getElementById('filter-start-date');
    const filterEndDate = document.getElementById('filter-end-date');
    const filterSearch = document.getElementById('filter-search');

    function debounce(func, wait) {
        let timeout;
        return function (...args) {
            clearTimeout(timeout);
            timeout = setTimeout(() => func.apply(this, args), wait);
        };
    }

    const triggerFilter = debounce(() => {
        currentPage = 1;
        loadData(1);
    }, 500);

    if (filterStartDate) filterStartDate.addEventListener('change', triggerFilter);
    if (filterEndDate) filterEndDate.addEventListener('change', triggerFilter);
    if (filterSearch) filterSearch.addEventListener('input', triggerFilter);

    // Initial Load
    loadTransformers();
    loadStatus();

    // --- Simulation Events ---
    sliderLoadFactor.addEventListener('input', (e) => {
        lblLoadFactor.innerText = (e.target.value * 100).toFixed(0) + "%";
    });

    btnRefreshSim.addEventListener('click', loadSimulationData);

    if (btnExportSim) {
        btnExportSim.addEventListener('click', async () => {
            if (!currentTrafoId) {
                alert("Lütfen bir trafo seçiniz.");
                return;
            }
            try {
                await authorizedFetch('/api/status');
                const lf = sliderLoadFactor.value;
                const sDate = simStartDate.value;
                const eDate = simEndDate.value;
                let url = `/api/simulation/export?trafo_id=${currentTrafoId}&load_factor=${lf}`;
                if (sDate) url += `&start_date=${sDate}`;
                if (eDate) url += `&end_date=${eDate}`;
                window.location.href = url;
            } catch (e) { }
        });
    }

    // Global tab function (needs to be on window to work with onclick in HTML)
    window.openTab = function (evt, tabName) {
        // Hide all tab content
        const tabContent = document.getElementsByClassName("tab-content");
        for (let i = 0; i < tabContent.length; i++) {
            tabContent[i].style.display = "none";
            tabContent[i].classList.remove("active");
        }

        // Deactivate all tab links
        const tabLinks = document.getElementsByClassName("tab-link");
        for (let i = 0; i < tabLinks.length; i++) {
            tabLinks[i].className = tabLinks[i].className.replace(" active", "");
        }

        // Show current tab
        const target = document.getElementById(tabName);
        if (target) {
            target.style.display = "block";
            // If opening simulation for first time or data is stale, maybe load?
            if (tabName === 'Simulation') {
                loadSimulationData();
            }
        }

        evt.currentTarget.className += " active";
    };

    // --- User Management ---
    // User management logic has been moved to index.html (inline script) 
    // to prevent caching issues and ensure reliable execution.
    // Conflicting event listeners have been removed.


    // Poll status (keep existing interval)
    setInterval(async () => {
        await loadStatus();
    }, 5000);

});
