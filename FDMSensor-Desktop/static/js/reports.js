document.addEventListener('DOMContentLoaded', () => {
    let compChart = null;

    // Elements
    const trafoSelect = document.getElementById('trafo-select');
    const peakTop = document.getElementById('peak-top');
    const peakAmb = document.getElementById('peak-amb');
    const peakBot = document.getElementById('peak-bot');
    const ctx = document.getElementById('compChart').getContext('2d');

    // Init Chart
    try {
        compChart = new Chart(ctx, {
            type: 'line',
            data: {
                labels: [],
                datasets: [
                    { label: 'FDM Üst Yağ (Ölçülen)', borderColor: '#ef4444', data: [], fill: false, borderWidth: 2 },
                    { label: 'Hermetik Üst Yağ (Simüle)', borderColor: '#ef4444', data: [], fill: false, borderDash: [5, 5], borderWidth: 1 },
                    { label: 'FDM Alt Yağ (Ölçülen)', borderColor: '#f59e0b', data: [], fill: false, borderWidth: 2 },
                    { label: 'Hermetik Alt Yağ (Simüle)', borderColor: '#f59e0b', data: [], fill: false, borderDash: [5, 5], borderWidth: 1 },
                    { label: 'Ortam Sıcaklığı', borderColor: '#3b82f6', data: [], fill: false, pointRadius: 0, borderWidth: 1 }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: { mode: 'index', intersect: false },
                scales: {
                    x: { ticks: { color: '#94a3b8', maxTicksLimit: 10 } },
                    y: { ticks: { color: '#94a3b8' }, grid: { color: 'rgba(255,255,255,0.05)' } }
                },
                plugins: {
                    legend: { position: 'top', labels: { color: '#f8fafc', boxWidth: 15 } }
                },
                onClick: (e, activeEls) => {
                    if (activeEls.length > 0) {
                        const idx = activeEls[0].index;
                        const timestamp = currentReportData.comparison[idx].sensor_timestamp;
                        showDetailAtTimestamp(timestamp);
                    }
                }
            }
        });
    } catch (e) {
        console.error("Chart.js could not be initialized:", e);
    }

    let currentReportData = null;

    // API Calls
    async function authorizedFetch(url, options = {}) {
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

    async function fetchTransformers() {
        try {
            const res = await authorizedFetch('/api/transformers');
            const data = await res.json();
            trafoSelect.innerHTML = '<option value="" disabled selected>Trafo Seçiniz...</option>';
            data.forEach(t => {
                const opt = document.createElement('option');
                opt.value = t.id;
                opt.text = t.name;
                trafoSelect.appendChild(opt);
            });

            if (data.length > 0) {
                trafoSelect.value = data[0].id;
                loadReport();
            }
        } catch (e) {
            console.error("Fetch Transformers Error:", e);
        }
    }

    window.loadReport = async function () {
        const id = trafoSelect.value;
        if (!id) return;

        const startDate = document.getElementById('start-date').value;
        const endDate = document.getElementById('end-date').value;

        try {
            let url = `/api/reports/summary?trafo_id=${id}`;
            if (startDate) url += `&start_date=${startDate}`;
            if (endDate) url += `&end_date=${endDate}`;

            const res = await authorizedFetch(url);
            const data = await res.json();
            console.log("REPORT DATA:", data); // DEBUG LOG

            if (data.status === 'error') {
                alert("Hata: " + data.message);
                return;
            }

            currentReportData = data; // Store globally for drill-down

            // Helper to format date: 2024/05/15 12:00:00 -> 15/05/2024 12:00
            const formatDate = (raw) => {
                if (!raw) return "--";
                try {
                    const [d, t] = raw.split(' ');
                    const [y, m, day] = d.split('/');
                    return `${day}/${m}/${y} ${t.substring(0, 5)}`;
                } catch (e) { return raw; }
            };

            // Update FDM Peaks
            if (data.peaks) {
                peakTop.innerText = (data.peaks.top?.val || 0).toFixed(1);
                document.getElementById('date-top').innerText = formatDate(data.peaks.top?.ts);

                peakAmb.innerText = (data.peaks.amb?.val || 0).toFixed(1);
                document.getElementById('date-amb').innerText = formatDate(data.peaks.amb?.ts);

                peakBot.innerText = (data.peaks.bot?.val || 0).toFixed(1);
                document.getElementById('date-bot').innerText = formatDate(data.peaks.bot?.ts);
            }

            // Render Top 5
            const renderTop5 = (list, tbodyId) => {
                const tbody = document.getElementById(tbodyId);
                tbody.innerHTML = '';
                if (!list || list.length === 0) {
                    tbody.innerHTML = '<tr><td colspan="2" style="text-align:center; color:var(--text-muted)">Veri Yok</td></tr>';
                    return;
                }
                list.forEach(item => {
                    const tr = document.createElement('tr');
                    tr.innerHTML = `<td>${formatDate(item.ts)}</td><td>${(item.val || 0).toFixed(1)}</td>`;
                    tbody.appendChild(tr);
                });
            };

            if (data.top_5_top) renderTop5(data.top_5_top, 'top5-top-body');
            if (data.top_5_bot) renderTop5(data.top_5_bot, 'top5-bot-body');

            // Update Simulated Peaks (Synchronized)
            if (data.sim_peaks) {
                const fmtVal = (v) => (v !== null && v !== undefined) ? v.toFixed(1) : "--";

                document.getElementById('sim-peak-top').innerText = fmtVal(data.sim_peaks.top?.val);
                document.getElementById('sim-date-top').innerText = formatDate(data.sim_peaks.top?.ts);

                // Ambient Removed

                document.getElementById('sim-peak-bot').innerText = fmtVal(data.sim_peaks.bot?.val);
                document.getElementById('sim-date-bot').innerText = formatDate(data.sim_peaks.bot?.ts);
            }

            // Update Chart
            const comp = data.comparison || [];
            const labels = comp.map(r => {
                const parts = (r.sensor_timestamp || "").split(' ');
                return parts.length > 1 ? parts[1].substring(0, 5) : "";
            });

            compChart.data.labels = labels;
            compChart.data.datasets[0].data = comp.map(r => r.sensor1);
            compChart.data.datasets[1].data = comp.map(r => r.hermetic_top_oil_C);
            compChart.data.datasets[2].data = comp.map(r => r.sensor3);
            compChart.data.datasets[3].data = comp.map(r => r.hermetic_bottom_oil_C);
            compChart.data.datasets[4].data = comp.map(r => r.sensor2);
            compChart.update();

        } catch (e) {
            console.error("Load Report Error:", e);
        }
    };

    // Drill-down Logic
    window.showPeakDetail = function (type) {
        if (!currentReportData) return;

        const modal = document.getElementById('detail-modal');
        const title = document.getElementById('modal-title');
        const tbody = document.getElementById('detail-body');

        let peakInfo = null;
        let label = "";

        if (type === 'fdm_top') { peakInfo = currentReportData.peaks.top; label = "FDM Üst Yağ Zirvesi"; }
        else if (type === 'fdm_amb') { peakInfo = currentReportData.peaks.amb; label = "FDM Ortam Zirvesi"; }
        else if (type === 'fdm_bot') { peakInfo = currentReportData.peaks.bot; label = "FDM Alt Yağ Zirvesi"; }
        else if (type === 'sim_top') { peakInfo = currentReportData.sim_peaks.top; label = "Simüle Üst Yağ (Zirve Anı)"; }
        // sim_amb removed
        else if (type === 'sim_bot') { peakInfo = currentReportData.sim_peaks.bot; label = "Simüle Alt Yağ (Zirve Anı)"; }

        if (!peakInfo || peakInfo.val === null) {
            alert("Bu veri için henüz detay mevcut değil (Simülasyon eşleşmesi yok).");
            return;
        }

        title.innerText = `${label} Detayı (${peakInfo.val.toFixed(1)}°C)`;

        // Find index of peak in comparison data
        const comp = currentReportData.comparison || [];
        let peakIdx = comp.findIndex(r => r.sensor_timestamp === peakInfo.ts);

        let start = 0;
        let end = comp.length;

        if (peakIdx !== -1) {
            // Show ONLY that specific row
            start = peakIdx;
            end = peakIdx + 1;
        } else {
            // If peak not in current window (older), but we have the timestamp, we might not be able to show it from 'comparison' array if it's limited.
            // But comparison usually has the data range.
            // If not found, show empty or handle gracefully.
            tbody.innerHTML = '<tr><td colspan="6" style="text-align:center">Veri bu aralıkta bulunamadı.</td></tr>';
            modal.style.display = 'flex';
            return;
        }

        const rows = comp.slice(start, end);
        tbody.innerHTML = '';

        rows.forEach(r => {
            const isPeak = r.sensor_timestamp === peakInfo.ts;
            const tr = document.createElement('tr');
            if (isPeak) tr.style.backgroundColor = 'rgba(59, 130, 246, 0.2)';

            tr.innerHTML = `
                <td>${r.sensor_timestamp}</td>
                <td>${(r.sensor1 || 0).toFixed(1)}</td>
                <td>${(r.sensor3 || 0).toFixed(1)}</td>
                <td>${(r.sensor2 || 20).toFixed(1)}</td>
                <td>${(r.hermetic_top_oil_C || 0).toFixed(1)}</td>
                <td>${(r.hermetic_bottom_oil_C || 0).toFixed(1)}</td>
            `;
            tbody.appendChild(tr);
        });

        modal.style.display = 'flex';
    };

    window.showDetailAtTimestamp = function (ts) {
        if (!currentReportData) return;

        const modal = document.getElementById('detail-modal');
        const title = document.getElementById('modal-title');
        const tbody = document.getElementById('detail-body');

        title.innerText = `Veri Detayı (${ts})`;

        const comp = currentReportData.comparison || [];
        const peakIdx = comp.findIndex(r => r.sensor_timestamp === ts);

        let start = 0;
        let end = comp.length;

        if (peakIdx !== -1) {
            start = Math.max(0, peakIdx - 10);
            end = Math.min(comp.length, peakIdx + 11);
        }

        const rows = comp.slice(start, end);
        tbody.innerHTML = '';

        rows.forEach(r => {
            const isTarget = r.sensor_timestamp === ts;
            const tr = document.createElement('tr');
            if (isTarget) tr.style.backgroundColor = 'rgba(59, 130, 246, 0.2)';

            tr.innerHTML = `
                <td>${r.sensor_timestamp}</td>
                <td>${(r.sensor1 || 0).toFixed(1)}</td>
                <td>${(r.sensor3 || 0).toFixed(1)}</td>
                <td>${(r.sensor2 || 20).toFixed(1)}</td>
                <td>${(r.hermetic_top_oil_C || 0).toFixed(1)}</td>
                <td>${(r.hermetic_bottom_oil_C || 0).toFixed(1)}</td>
            `;
            tbody.appendChild(tr);
        });

        modal.style.display = 'flex';
    };

    window.closeModal = function () {
        document.getElementById('detail-modal').style.display = 'none';
    };

    trafoSelect.onchange = loadReport;

    // Initial Load
    fetchTransformers();
});
