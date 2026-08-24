/** Terminal output UI and background-job polling. */
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

function pollJob(jobId, onComplete, onError) {
    let seenLines = 0;

    const interval = setInterval(() => {
        fetch(`/job_status/${jobId}`)
            .then(r => {
                if (!r.ok) throw new Error(`HTTP ${r.status}`);
                return r.json();
            })
            .then(data => {
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
                console.warn('Poll blip:', err);
            });
    }, 2000);
}
