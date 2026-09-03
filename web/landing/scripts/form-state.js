/**
 * Toggle-button groups (multi-bath, label-format, and the lighting
 * yes/no toggles). Delegated on document so it also covers toggles
 * inside measure tabs added after page load. Active state lives on
 * the buttons themselves (.active class) and is read directly from
 * the DOM at submit time — see generate-report.js.
 */
document.addEventListener('click', (e) => {
    const btn = e.target.closest('.toggle');
    if (!btn) return;
    const group = btn.dataset.group;
    document.querySelectorAll(`button.toggle[data-group="${group}"]`)
        .forEach(b => b.classList.remove('active'));
    btn.classList.add('active');

    const levelNumericMatch = group && group.match(/^locLevelNumeric-(m\d+)-(\d+)$/);
    if (levelNumericMatch && typeof window.updateLocationLevelsNumericUI === 'function') {
        window.updateLocationLevelsNumericUI(levelNumericMatch[1]);
    }

    const hpMultiMatch = group && group.match(/^hpMultiUnit-(m\d+)$/);
    if (hpMultiMatch && typeof window.updateHeatPumpLocationUI === 'function') {
        window.updateHeatPumpLocationUI(hpMultiMatch[1]);
    }
    const hpLoneMatch = group && group.match(/^hpLoneNumber-(m\d+)$/);
    if (hpLoneMatch && typeof window.updateHeatPumpLocationUI === 'function') {
        window.updateHeatPumpLocationUI(hpLoneMatch[1]);
    }
});
