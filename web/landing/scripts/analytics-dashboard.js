/** Dev Access analytics dashboard: overview + filterable run log. */
let _analyticsRuns = [];
let _analyticsOverview = null;

document.getElementById('goAnalyticsBtn').addEventListener('click', async () => {
    showScreen('devAnalytics');
    document.getElementById('devBackBtn').style.display = '';
    document.getElementById('devTitle').textContent = 'Usage Analytics';
    await refreshAnalyticsDashboard();
});

async function refreshAnalyticsDashboard() {
    const userFilter = document.getElementById('analyticsUserFilter').value;
    const typeFilter = document.getElementById('analyticsTypeFilter').value;
    const qs = new URLSearchParams();
    if (userFilter) qs.set('user_id', userFilter);
    if (typeFilter) qs.set('run_type', typeFilter);

    const overviewQs = userFilter ? `?user_id=${encodeURIComponent(userFilter)}` : '';
    try {
        const [runsRes, overviewRes, usersRes] = await Promise.all([
            fetch(`/analytics/runs?${qs}`),
            fetch(`/analytics/overview${overviewQs}`),
            fetch('/analytics/users'),
        ]);
        const runsData = await runsRes.json();
        const overviewData = await overviewRes.json();
        const usersData = await usersRes.json();
        _analyticsRuns = runsData.runs || [];
        _analyticsOverview = overviewData;
        populateUserFilter(usersData.users || [], userFilter);
        renderOverviewCards(overviewData);
        renderRunsTable(_analyticsRuns);
    } catch (err) {
        document.getElementById('analyticsOverview').innerHTML =
            `<div class="analytics-error">Failed to load analytics: ${err.message}</div>`;
    }
}

function populateUserFilter(users, selected) {
    const sel = document.getElementById('analyticsUserFilter');
    const current = selected || sel.value;
    sel.innerHTML = '<option value="">All users</option>';
    users.forEach(u => {
        const opt = document.createElement('option');
        opt.value = u.user_id;
        opt.textContent = `${u.display_name} (${u.run_count || 0})`;
        sel.appendChild(opt);
    });
    sel.value = current;
}

function renderOverviewCards(data) {
    const el = document.getElementById('analyticsOverview');
    const cards = [
        ['Report runs', data.reports_completed, `${data.reports_failed || 0} failed`],
        ['PDF runs', data.pdfs_completed, `of ${data.report_runs || 0} reports`],
        ['Photos processed', data.total_photos_processed, ''],
        ['Avg unknown rate', `${((data.avg_unknown_rate || 0) * 100).toFixed(1)}%`, `${data.total_unknown_photos || 0} unknown`],
        ['Avg edit intensity', (data.avg_edit_intensity || 0).toFixed(3), ''],
        ['PDF conversion', `${((data.pdf_conversion_rate || 0) * 100).toFixed(0)}%`, ''],
    ];
    el.innerHTML = cards.map(([label, value, sub]) => `
        <div class="analytics-card">
            <div class="analytics-card-label">${label}</div>
            <div class="analytics-card-value">${value}</div>
            ${sub ? `<div class="analytics-card-sub">${sub}</div>` : ''}
        </div>
    `).join('');
}

function formatTs(ts) {
    if (!ts) return '—';
    try {
        return new Date(ts).toLocaleString();
    } catch (e) {
        return ts;
    }
}

function projectLabel(run) {
    const p = run.project || {};
    const pdf = run.pdf || {};
    const original = p.is_multi_project
        ? (p.package_name || p.package_id || 'Package')
        : (p.project_name || p.project_id || '—');
    if (run.run_type === 'pdf' && pdf.project_name_edited) {
        return `${original} → ${pdf.project_name}`;
    }
    if (run.run_type === 'pdf' && pdf.project_name) {
        return pdf.project_name;
    }
    return original || '—';
}

function runSummary(run) {
    if (run.run_type === 'pdf') {
        const pdf = run.pdf || {};
        const nameNote = pdf.project_name_edited ? ' · name edited' : '';
        return `PDF · ${pdf.layout || '?'} · ${pdf.hidden_photo_count || 0} hidden${nameNote}`;
    }
    const pipe = run.pipeline || {};
    const measures = (run.measures || []).map(m => m.type).join(', ');
    return `${pipe.photos_fetched_total || 0} photos · ${measures || '—'} · ${((pipe.unknown_rate || 0) * 100).toFixed(1)}% unknown`;
}

function renderRunsTable(runs) {
    const tbody = document.getElementById('analyticsRunsBody');
    if (!runs.length) {
        tbody.innerHTML = '<tr><td colspan="8" class="analytics-empty">No runs yet.</td></tr>';
        return;
    }
    tbody.innerHTML = runs.map((run, idx) => {
        const edits = run.edits || {};
        const statusClass = run.status === 'complete' ? 'ok' : (run.status === 'error' ? 'err' : '');
        return `<tr class="analytics-run-row" data-idx="${idx}">
            <td>${formatTs(run.ts_start)}</td>
            <td>${run.display_name || run.user_id || '—'}</td>
            <td><span class="analytics-pill">${run.run_type}</span></td>
            <td>${projectLabel(run)}</td>
            <td class="analytics-summary">${runSummary(run)}</td>
            <td>${edits.edit_intensity != null ? edits.edit_intensity : '—'}</td>
            <td><span class="analytics-status ${statusClass}">${run.status}</span></td>
            <td>${run.duration_ms != null ? Math.round(run.duration_ms / 1000) + 's' : '—'}</td>
        </tr>`;
    }).join('');

    tbody.querySelectorAll('.analytics-run-row').forEach(row => {
        row.addEventListener('click', () => {
            const run = runs[Number(row.dataset.idx)];
            showRunDetail(run);
        });
    });
}

function showRunDetail(run) {
    const panel = document.getElementById('analyticsRunDetail');
    panel.classList.add('open');
    panel.innerHTML = `
        <div class="analytics-detail-header">
            <strong>${run.run_type === 'pdf' ? 'PDF' : 'Report'} run</strong>
            <button type="button" class="analytics-detail-close" id="analyticsDetailClose">✕</button>
        </div>
        <pre class="analytics-detail-json">${escapeHtml(JSON.stringify(run, null, 2))}</pre>
    `;
    document.getElementById('analyticsDetailClose').addEventListener('click', () => {
        panel.classList.remove('open');
    });
}

function escapeHtml(str) {
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;');
}

document.getElementById('analyticsUserFilter').addEventListener('change', refreshAnalyticsDashboard);
document.getElementById('analyticsTypeFilter').addEventListener('change', refreshAnalyticsDashboard);
document.getElementById('analyticsRefreshBtn').addEventListener('click', refreshAnalyticsDashboard);
