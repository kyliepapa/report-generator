/** Changelog overlay: fetches and displays server-side changelog text. */
document.getElementById('changelogBtn').addEventListener('click', async () => {
    const content = document.getElementById('changelogContent');
    content.textContent = 'Loading…';
    openOverlay('changelogOverlay');

    try {
        const res = await fetch('/get_changelog');
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        if (data.content && data.content.trim()) {
            content.textContent = data.content;
        } else {
            content.innerHTML = '<div class="changelog-empty">No changelog entries yet.</div>';
        }
    } catch (err) {
        content.innerHTML = `<div class="changelog-empty">Could not load changelog: ${err.message}</div>`;
    }
});

document.getElementById('changelogCloseBtn').addEventListener('click', () => closeOverlay('changelogOverlay'));
