/** Report & Request overlay: user submission form. */
document.getElementById('rnrBtn').addEventListener('click', () => {
    showScreen('rnrForm');
    document.getElementById('rnrError').textContent = '';
    openOverlay('rnrOverlay');
});

document.getElementById('rnrCloseBtn').addEventListener('click', () => closeOverlay('rnrOverlay'));

document.getElementById('rnrSubmitBtn').addEventListener('click', async () => {
    const message = document.getElementById('rnrMessage').value.trim();
    const submitter = document.getElementById('rnrSubmitter').value.trim();
    const errorEl = document.getElementById('rnrError');

    if (!message && !submitter) {
        errorEl.textContent = 'Please fill in both fields before submitting.';
        return;
    }
    if (!message) {
        errorEl.textContent = 'Please describe your report or request.';
        return;
    }
    if (!submitter) {
        errorEl.textContent = 'Please enter your name in the "Submitted by" field.';
        return;
    }

    errorEl.textContent = '';

    try {
        const res = await fetch('/submit_rnr', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message, submitter }),
        });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);

        document.getElementById('rnrMessage').value = '';
        document.getElementById('rnrSubmitter').value = '';

        showScreen('rnrSuccess');
        setTimeout(() => closeOverlay('rnrOverlay'), 2400);
    } catch (err) {
        errorEl.textContent = `Submission failed: ${err.message}`;
    }
});
