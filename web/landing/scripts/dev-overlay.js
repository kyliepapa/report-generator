/** Developer Access overlay: password gate and file editors. */
let devUnlocked = false;

document.getElementById('devBtn').addEventListener('click', () => {
    if (devUnlocked) {
        showScreen('devHub');
    } else {
        showScreen('devPwScreen');
        document.getElementById('devPwInput').value = '';
        document.getElementById('devPwError').textContent = '';
    }
    document.getElementById('devBackBtn').style.display = 'none';
    document.getElementById('devTitle').textContent = 'Developer Access';
    openOverlay('devOverlay');
});

document.getElementById('devCloseBtn').addEventListener('click', () => {
    autoSaveDevEditors();
    closeOverlay('devOverlay');
});

document.getElementById('devOverlay').addEventListener('click', function (e) {
    if (e.target === this) {
        autoSaveDevEditors();
        closeOverlay('devOverlay');
    }
});

document.getElementById('devPwSubmit').addEventListener('click', checkDevPassword);
document.getElementById('devPwInput').addEventListener('keydown', e => {
    if (e.key === 'Enter') checkDevPassword();
});

function checkDevPassword() {
    const val = document.getElementById('devPwInput').value;
    if (val === DEV_PASSWORD) {
        devUnlocked = true;
        document.getElementById('devPwError').textContent = '';
        showScreen('devHub');
        document.getElementById('devBackBtn').style.display = 'none';
        document.getElementById('devTitle').textContent = 'Developer Access';
    } else {
        document.getElementById('devPwError').textContent = 'Incorrect password.';
        document.getElementById('devPwInput').value = '';
        document.getElementById('devPwInput').focus();
    }
}

document.getElementById('devBackBtn').addEventListener('click', () => {
    autoSaveDevEditors();
    showScreen('devHub');
    document.getElementById('devBackBtn').style.display = 'none';
    document.getElementById('devTitle').textContent = 'Developer Access';
});

document.getElementById('goUsageLogsBtn').addEventListener('click', async () => {
    showScreen('devUsageLogs');
    document.getElementById('devBackBtn').style.display = '';
    document.getElementById('devTitle').textContent = 'Usage Logs';

    const area = document.getElementById('devUsageLogsArea');
    area.value = 'Loading…';
    try {
        const res = await fetch('/dev_get_file?file=usage_logs');
        const data = await res.json();
        area.value = data.content || '';
    } catch (err) {
        area.value = `Error loading file: ${err.message}`;
    }
});

document.getElementById('goDevRnrBtn').addEventListener('click', async () => {
    showScreen('devRnrEditor');
    document.getElementById('devBackBtn').style.display = '';
    document.getElementById('devTitle').textContent = 'Reports & Requests';

    const area = document.getElementById('devRnrArea');
    area.value = 'Loading…';
    try {
        const res = await fetch('/dev_get_file?file=repnreq');
        const data = await res.json();
        area.value = data.content || '';
    } catch (err) {
        area.value = `Error loading file: ${err.message}`;
    }
});

document.getElementById('devSaveUsage').addEventListener('click', () => saveDevFile('usage_logs', 'devUsageLogsArea', 'devSaveUsageFlash'));
document.getElementById('devSaveRnr').addEventListener('click', () => saveDevFile('repnreq', 'devRnrArea', 'devSaveRnrFlash'));

async function saveDevFile(file, areaId, flashId) {
    const content = document.getElementById(areaId).value;
    try {
        await fetch('/dev_save_file', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ file, content }),
        });
        const flash = document.getElementById(flashId);
        flash.classList.add('show');
        setTimeout(() => flash.classList.remove('show'), 2000);
    } catch (err) {
        console.error('Save failed:', err);
    }
}

function autoSaveDevEditors() {
    const usageScreen = document.getElementById('devUsageLogs');
    const rnrScreen = document.getElementById('devRnrEditor');
    if (usageScreen.classList.contains('active')) {
        saveDevFile('usage_logs', 'devUsageLogsArea', 'devSaveUsageFlash');
    }
    if (rnrScreen.classList.contains('active')) {
        saveDevFile('repnreq', 'devRnrArea', 'devSaveRnrFlash');
    }
}
