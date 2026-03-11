// qBit Manager Web — Dashboard Charts & Data

const COLORS = {
    blue: 'rgba(13, 110, 253, 0.8)',
    green: 'rgba(25, 135, 84, 0.8)',
    red: 'rgba(220, 53, 69, 0.8)',
    yellow: 'rgba(255, 193, 7, 0.8)',
    cyan: 'rgba(13, 202, 240, 0.8)',
    purple: 'rgba(111, 66, 193, 0.8)',
    orange: 'rgba(253, 126, 20, 0.8)',
    teal: 'rgba(32, 201, 151, 0.8)',
};

const CHART_DEFAULTS = {
    responsive: true,
    maintainAspectRatio: true,
    plugins: {
        legend: { labels: { color: '#8b8fa3', font: { size: 11 } } },
    },
    scales: {
        x: { ticks: { color: '#8b8fa3', font: { size: 10 } }, grid: { color: '#1e2129' } },
        y: { ticks: { color: '#8b8fa3', font: { size: 10 } }, grid: { color: '#1e2129' } },
    },
};

let diskChart, statesChart, runsChart, trackerChart;

// ── Stats Cards ──────────────────────────────────────────────────────────

function loadStats() {
    fetch('/api/stats')
        .then(r => r.json())
        .then(data => {
            const lr = data.last_run;
            if (lr) {
                const el = document.getElementById('stat-status');
                el.textContent = lr.status.toUpperCase();
                el.className = 'fs-4 fw-bold ' + (lr.status === 'active' ? 'text-success' : 'text-danger');
            }
            document.getElementById('stat-runs-24h').textContent = data.runs_24h;
            document.getElementById('stat-pauses').textContent = data.total_pauses;
            document.getElementById('stat-deletions').textContent = data.total_deletions;
            document.getElementById('last-update').textContent =
                'Atualizado: ' + new Date().toLocaleTimeString('pt-BR');
        })
        .catch(() => {});
}

// ── Disk Space Chart ─────────────────────────────────────────────────────

function loadDiskChart() {
    const limit = document.getElementById('disk-limit').value;
    fetch(`/api/disk-history?limit=${limit}`)
        .then(r => r.json())
        .then(data => {
            const labels = data.history.map(h =>
                new Date(h.timestamp).toLocaleString('pt-BR', {
                    day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit'
                })
            );

            const colorList = [COLORS.blue, COLORS.green, COLORS.cyan, COLORS.purple, COLORS.orange];
            const datasets = data.disk_names.map((name, i) => ({
                label: name,
                data: data.history.map(h => h[name]?.toFixed(1) || 0),
                borderColor: colorList[i % colorList.length],
                backgroundColor: colorList[i % colorList.length].replace('0.8', '0.1'),
                fill: true,
                tension: 0.3,
                pointRadius: 1,
            }));

            if (diskChart) diskChart.destroy();
            diskChart = new Chart(document.getElementById('diskChart'), {
                type: 'line',
                data: { labels, datasets },
                options: {
                    ...CHART_DEFAULTS,
                    plugins: {
                        ...CHART_DEFAULTS.plugins,
                        tooltip: {
                            callbacks: {
                                label: ctx => `${ctx.dataset.label}: ${ctx.parsed.y} GB`
                            }
                        }
                    },
                    scales: {
                        ...CHART_DEFAULTS.scales,
                        y: { ...CHART_DEFAULTS.scales.y, title: { display: true, text: 'GB', color: '#8b8fa3' } }
                    }
                }
            });
        });
}

// ── Torrent States Chart ─────────────────────────────────────────────────

function loadStatesChart() {
    fetch('/api/torrent-states')
        .then(r => r.json())
        .then(data => {
            const STATE_LABELS = {
                'uploading': 'Uploading', 'stalledUP': 'Stalled UP', 'downloading': 'Downloading',
                'stalledDL': 'Stalled DL', 'pausedUP': 'Paused UP', 'pausedDL': 'Paused DL',
                'queuedUP': 'Queued UP', 'queuedDL': 'Queued DL', 'checkingUP': 'Checking UP',
                'checkingDL': 'Checking DL', 'forcedDL': 'Forced DL', 'forcedUP': 'Forced UP',
                'moving': 'Moving', 'missingFiles': 'Missing', 'error': 'Error',
            };

            const labels = Object.keys(data).map(k => STATE_LABELS[k] || k);
            const values = Object.values(data);
            const colors = [
                COLORS.green, COLORS.blue, COLORS.cyan, COLORS.yellow,
                COLORS.red, COLORS.orange, COLORS.purple, COLORS.teal,
                '#6c757d', '#adb5bd', '#495057', '#343a40',
            ];

            if (statesChart) statesChart.destroy();
            statesChart = new Chart(document.getElementById('statesChart'), {
                type: 'doughnut',
                data: {
                    labels,
                    datasets: [{ data: values, backgroundColor: colors.slice(0, values.length) }]
                },
                options: {
                    responsive: true,
                    plugins: {
                        legend: { position: 'right', labels: { color: '#8b8fa3', font: { size: 10 }, boxWidth: 12 } },
                    },
                },
            });
        });
}

// ── Runs History Chart ───────────────────────────────────────────────────

function loadRunsChart() {
    fetch('/api/runs-history?limit=50')
        .then(r => r.json())
        .then(data => {
            const labels = data.map(r =>
                new Date(r.started_at).toLocaleString('pt-BR', {
                    day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit'
                })
            );

            if (runsChart) runsChart.destroy();
            runsChart = new Chart(document.getElementById('runsChart'), {
                type: 'bar',
                data: {
                    labels,
                    datasets: [
                        { label: 'Pausados', data: data.map(r => r.paused_count), backgroundColor: COLORS.red, stack: 'a' },
                        { label: 'Checking', data: data.map(r => r.checking), backgroundColor: COLORS.yellow, stack: 'a' },
                        { label: 'Seed Deletados', data: data.map(r => r.seeding_deletados), backgroundColor: COLORS.orange, stack: 'b' },
                        { label: 'Tracker Forcados', data: data.map(r => r.tracker_forcados), backgroundColor: COLORS.blue, stack: 'b' },
                    ],
                },
                options: {
                    ...CHART_DEFAULTS,
                    plugins: {
                        ...CHART_DEFAULTS.plugins,
                        legend: { labels: { color: '#8b8fa3', font: { size: 10 } } },
                    },
                    scales: {
                        ...CHART_DEFAULTS.scales,
                        x: { ...CHART_DEFAULTS.scales.x, stacked: true },
                        y: { ...CHART_DEFAULTS.scales.y, stacked: true },
                    },
                },
            });
        });
}

// ── Tracker Distribution Chart ───────────────────────────────────────────

function loadTrackerChart() {
    fetch('/api/tracker-distribution')
        .then(r => r.json())
        .then(data => {
            const labels = Object.keys(data);
            const values = Object.values(data);
            const colors = [
                COLORS.blue, COLORS.green, COLORS.red, COLORS.yellow,
                COLORS.cyan, COLORS.purple, COLORS.orange, COLORS.teal,
                '#6c757d', '#adb5bd', '#e83e8c', '#fd7e14',
                '#20c997', '#6610f2', '#d63384',
            ];

            if (trackerChart) trackerChart.destroy();
            trackerChart = new Chart(document.getElementById('trackerChart'), {
                type: 'doughnut',
                data: {
                    labels,
                    datasets: [{ data: values, backgroundColor: colors.slice(0, values.length) }]
                },
                options: {
                    responsive: true,
                    plugins: {
                        legend: { position: 'right', labels: { color: '#8b8fa3', font: { size: 10 }, boxWidth: 12 } },
                    },
                },
            });
        });
}

// ── Tables ────────────────────────────────────────────────────────────────

function loadPauseEvents() {
    fetch('/api/pause-events?limit=10')
        .then(r => r.json())
        .then(data => {
            const tbody = document.getElementById('pause-events-table');
            if (!data.length) {
                tbody.innerHTML = '<tr><td colspan="4" class="text-center text-muted">Nenhum evento</td></tr>';
                return;
            }
            tbody.innerHTML = data.map(e => {
                const date = new Date(e.event_at).toLocaleString('pt-BR', {
                    day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit'
                });
                const typeBadge = {
                    'pause': '<span class="badge bg-danger">Pause</span>',
                    'restore': '<span class="badge bg-success">Restore</span>',
                    'waiting': '<span class="badge bg-warning text-dark">Waiting</span>',
                }[e.event_type] || `<span class="badge bg-secondary">${e.event_type}</span>`;
                return `<tr>
                    <td>${date}</td>
                    <td>${typeBadge}</td>
                    <td>${e.reason || '-'}</td>
                    <td>${e.torrents_count}</td>
                </tr>`;
            }).join('');
        });
}

function loadDeletions() {
    fetch('/api/seed-deletions?limit=10')
        .then(r => r.json())
        .then(data => {
            const tbody = document.getElementById('deletions-table');
            if (!data.length) {
                tbody.innerHTML = '<tr><td colspan="5" class="text-center text-muted">Nenhuma delecao</td></tr>';
                return;
            }
            tbody.innerHTML = data.map(d => {
                const date = new Date(d.deleted_at).toLocaleString('pt-BR', {
                    day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit'
                });
                const sizeGB = (d.size_bytes / (1024 ** 3)).toFixed(1);
                const name = d.name.length > 40 ? d.name.substring(0, 40) + '...' : d.name;
                const dryBadge = d.dry_run ? ' <span class="badge bg-info">DRY</span>' : '';
                return `<tr>
                    <td>${date}</td>
                    <td title="${d.name}">${name}${dryBadge}</td>
                    <td>${d.tracker || '-'}</td>
                    <td>${d.seeding_days.toFixed(1)}d</td>
                    <td>${sizeGB} GB</td>
                </tr>`;
            }).join('');
        });
}

// ── Init ──────────────────────────────────────────────────────────────────

function loadAll() {
    loadStats();
    loadDiskChart();
    loadStatesChart();
    loadRunsChart();
    loadTrackerChart();
    loadPauseEvents();
    loadDeletions();
}

document.getElementById('disk-limit').addEventListener('change', loadDiskChart);

// Load on page ready
loadAll();

// Auto-refresh every 60s
setInterval(loadAll, 60000);
