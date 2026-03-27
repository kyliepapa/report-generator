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
const terminal = document.getElementById('terminal');
const termStatus = document.getElementById('terminalStatus');

function setStatus(state, label) {
    termStatus.className = 'terminal-status ' + state;
    termStatus.textContent = label;
}

function termLine(text) {
    const line = document.createElement('span');

    if (text.startsWith('❌') || text.toLowerCase().includes('error')) {
        line.className = 'line-error';
    } else if (text.startsWith('✅') || text.startsWith('🏷') && text.includes('complete')) {
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
// GENERATE BUTTON
// ================================
document.getElementById('generateBtn').addEventListener('click', () => {
    const projectId   = document.getElementById('projectId').value.trim();
    const projectName = document.getElementById('projectName').value.trim();
    const baths = Array.from(document.querySelectorAll('.bath'))
        .map(b => b.value.trim())
        .filter(b => b !== "");

    const errorDiv = document.getElementById('error');
    errorDiv.textContent = "";

    if (!projectId) {
        errorDiv.textContent = "Please enter a Project ID.";
        return;
    }
    if (!selected.multi) {
        errorDiv.textContent = "Please select whether units have multiple bathrooms.";
        return;
    }
    if (!selected.format) {
        errorDiv.textContent = "Please select a unit label format.";
        return;
    }

    clearTerminal();
    setStatus('running', 'Running…');

    const generateBtn = document.getElementById('generateBtn');
    generateBtn.disabled = true;
    generateBtn.querySelector('.btn-label').textContent = 'Generating…';

    document.getElementById('reportActions').style.display = 'none';

    const params = new URLSearchParams({
        project_id:   projectId,
        project_name: projectName || projectId,
        multi_bath:   selected.multi,
        label_format: selected.format,
        bath_names:   baths.join(',')
    });

    const eventSource = new EventSource(`/generate_stream?${params}`);

    eventSource.onmessage = function(event) {
        termLine(event.data);
    };

    eventSource.addEventListener("complete", function() {
        eventSource.close();
        setStatus('success', 'Done');

        generateBtn.disabled = false;
        generateBtn.querySelector('.btn-label').textContent = 'Generate Report';

        // Show action bar with link to report
        const actions = document.getElementById('reportActions');
        const openBtn = document.getElementById('openReportBtn');
        openBtn.onclick = () => window.open(`/report?${params}`, '_blank');
        actions.style.display = 'flex';
    });

    eventSource.onerror = function() {
        eventSource.close();
        setStatus('error', 'Error');
        termLine('❌ Connection error. Check the server.');

        generateBtn.disabled = false;
        generateBtn.querySelector('.btn-label').textContent = 'Generate Report';
    };
});
