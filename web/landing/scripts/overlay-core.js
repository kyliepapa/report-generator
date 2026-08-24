/** Shared open/close/screen-switch helpers for modal overlays. */
const OVERLAY_IDS = ['helpOverlay', 'rnrOverlay', 'changelogOverlay', 'devOverlay'];

function openOverlay(id) {
    document.getElementById(id).classList.add('open');
}

function closeOverlay(id) {
    document.getElementById(id).classList.remove('open');
}

function showScreen(screenId) {
    const panel = document.getElementById(screenId).closest('.overlay-panel');
    panel.querySelectorAll('.overlay-screen').forEach(s => s.classList.remove('active'));
    document.getElementById(screenId).classList.add('active');
}

OVERLAY_IDS.forEach(id => {
    document.getElementById(id).addEventListener('click', function (e) {
        if (e.target === this) closeOverlay(id);
    });
});

document.addEventListener('keydown', e => {
    if (e.key === 'Escape') {
        OVERLAY_IDS.forEach(closeOverlay);
    }
});
