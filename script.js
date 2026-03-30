// This is script.js

// ================================
// STATE
// ================================
let selected = { multi: null, format: null };

// ================================
// TOGGLE BUTTONS
// ================================
document.querySelectorAll('.toggle').forEach(btn => {
    btn.addEventListener('click', () => {
        const group = btn.dataset.group;
        document.querySelectorAll(`button[data-group="${group}"]`)
            .forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        selected[group] = btn.dataset.value;
    });
});

// ================================
// TERMINAL HELPERS
// ================================
const terminal   = document.getElementById('terminal');
const termStatus = document.getElementById('terminalStatus');

function setStatus(state, label) {
    termStatus.className = 'terminal-status ' + state;
    termStatus.textContent = label;
}

function termLine(text) {
    const line = document.createElement('span');

    if (text.startsWith('❌') || text.toLowerCase().includes('error')) {
        line.className = 'line-error';
    } else if (text.startsWith('✅') || (text.startsWith('🏷') && text.includes('complete'))) {
        line.className = 'line-success';
    } else if (text.startsWith('📊') || text.startsWith('🔴') || text.startsWith('🟡')) {
        line.className = 'line-section';
    } else if (text.startsWith('──') || text.startsWith('   •')) {
        line.className = 'line-warning';
    }

    line.textContent = text + '\n';
    terminal.appendChild(line);
    terminal.scrollTop = terminal.scrollHeight;
}

function clearTerminal() {
    terminal.innerHTML = '';
}

// ================================
// POLLING HELPER
// Calls /job_status/:id every 2s, prints new log lines,
// resolves when status is 'complete' or 'error'.
// ================================
function pollJob(jobId, onComplete, onError) {
    let seenLines = 0;

    const interval = setInterval(() => {
        fetch(`/job_status/${jobId}`)
            .then(r => {
                if (!r.ok) throw new Error(`HTTP ${r.status}`);
                return r.json();
            })
            .then(data => {
                // Print any new log lines since last poll
                const newLines = data.log.slice(seenLines);
                newLines.forEach(termLine);
                seenLines = data.log.length;

                if (data.status === 'complete') {
                    clearInterval(interval);
                    onComplete(data);
                } else if (data.status === 'error') {
                    clearInterval(interval);
                    onError(data);
                }
            })
            .catch(err => {
                // A single failed poll is just a network blip — keep trying
                console.warn('Poll blip:', err);
            });
    }, 2000);
}

// ================================
// RESET UI HELPERS
// ================================
function resetBtn() {
    const btn = document.getElementById('generateBtn');
    btn.disabled = false;
    btn.querySelector('.btn-label').textContent = 'Generate Report';
}

// ================================
// GENERATE BUTTON
// ================================
document.getElementById('generateBtn').addEventListener('click', () => {
    const projectId   = document.getElementById('projectId').value.trim();
    const projectName = document.getElementById('projectName').value.trim();
    const baths = Array.from(document.querySelectorAll('.bath'))
        .map(b => b.value.trim())
        .filter(b => b !== '');

    const errorDiv = document.getElementById('error');
    errorDiv.textContent = '';

    if (!projectId) {
        errorDiv.textContent = 'Please enter a Project ID.';
        return;
    }
    if (!selected.multi) {
        errorDiv.textContent = 'Please select whether units have multiple bathrooms.';
        return;
    }
    if (!selected.format) {
        errorDiv.textContent = 'Please select a unit label format.';
        return;
    }

    clearTerminal();
    setStatus('running', 'Running…');

    const generateBtn = document.getElementById('generateBtn');
    generateBtn.disabled = true;
    generateBtn.querySelector('.btn-label').textContent = 'Generating…';
    document.getElementById('reportActions').style.display = 'none';

    const payload = {
        project_id:   projectId,
        project_name: projectName || projectId,
        multi_bath:   selected.multi,
        label_format: selected.format,
        bath_names:   baths.join(','),
    };

    // POST to kick off the background job
    fetch('/start_job', {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify(payload),
    })
    .then(r => {
        if (r.status === 429) throw new Error('busy');
        if (!r.ok)            throw new Error(`HTTP ${r.status}`);
        return r.json();
    })
    .then(({ job_id }) => {
        termLine('🔌 Job started, processing...');

        pollJob(
            job_id,
            // onComplete
            () => {
                setStatus('success', 'Done');
                resetBtn();

                const actions = document.getElementById('reportActions');
                const openBtn = document.getElementById('openReportBtn');
                const urlParams = new URLSearchParams(payload);
                openBtn.onclick = () => window.open(`/report?${urlParams}`, '_blank');
                actions.style.display = 'flex';
            },
            // onError
            () => {
                setStatus('error', 'Error');
                resetBtn();
            }
        );
    })
    .catch(err => {
        if (err.message === 'busy') {
            termLine('⏳ Another report is already running. Please wait and try again.');
        } else {
            termLine(`❌ Failed to start job: ${err}`);
        }
        setStatus('error', 'Error');
        resetBtn();
    });
});