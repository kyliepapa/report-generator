/**
 * Dynamic location-level rows for Lighting measures (up to 5 levels).
 */

const MAX_LOCATION_LEVELS = 5;

const LEVEL_HINTS = [
    'Top-level areas (e.g. Exterior, 2nd Floor, Hallway, Parking Garage).',
    'More specific areas within the level above (e.g. North Wing, Suite 200).',
    'Further subdivision within the level above.',
    'Further subdivision within the level above.',
    'Further subdivision within the level above.',
];

function _toggleValue(group) {
    const btn = document.querySelector(`button.toggle.active[data-group="${group}"]`);
    return btn ? btn.dataset.value : null;
}

function _makeLevelSwitchHtml(group, label) {
    return `
        <div class="field-group switch-group">
            <div class="switch-group-text field-heading">
                <label class="field-label" for="switch-${group}">${label}</label>
            </div>
            <label class="switch">
                <input type="checkbox" id="switch-${group}" class="switch-input" data-group="${group}" />
                <span class="switch-slider"></span>
            </label>
            <button type="button" class="toggle active" data-group="${group}" data-value="No" hidden tabindex="-1"></button>
            <button type="button" class="toggle" data-group="${group}" data-value="Yes" hidden tabindex="-1"></button>
        </div>`;
}

function _levelLabel(n) {
    const optional = n > 1 ? ' <span class="optional">(optional)</span>' : '';
    return `Location Level ${n}${optional}`;
}

function _createLevelRow(measureId, levelNum) {
    const row = document.createElement('div');
    row.className = 'location-level-row';
    row.dataset.level = String(levelNum);
    const prefix = `locLevel-${measureId}-${levelNum}`;
    const numericGroup = `locLevelNumeric-${measureId}-${levelNum}`;
    row.innerHTML = `
        <div class="field-group location-level-tags">
            <div class="field-heading">
                <label class="field-label">${_levelLabel(levelNum)}</label>
                <div class="field-hint">${LEVEL_HINTS[levelNum - 1]}</div>
            </div>
            <div class="tag-builder" id="${prefix}Builder">
                <input class="tag-input" id="${prefix}Input" placeholder="Type a name, press Enter" autocomplete="off" spellcheck="false" />
            </div>
        </div>
        ${_makeLevelSwitchHtml(numericGroup, 'Includes numbered locations at this level')}`;

    const builder = row.querySelector('.tag-builder');
    if (builder && typeof window.initTagBuilder === 'function') {
        window.initTagBuilder(builder);
    }

    const switchInput = row.querySelector('.switch-input');
    if (switchInput) {
        switchInput.addEventListener('change', () => {
            updateLocationLevelsNumericUI(measureId);
        });
    }

    return row;
}

function _rowsContainer(measureId) {
    return document.getElementById(`locationLevelRows-${measureId}`);
}

function _addBtn(measureId) {
    return document.getElementById(`addLocationLevelBtn-${measureId}`);
}

function _visibleLevelCount(measureId) {
    const container = _rowsContainer(measureId);
    return container ? container.querySelectorAll('.location-level-row').length : 0;
}

function initLocationLevels(measureId) {
    const container = _rowsContainer(measureId);
    const addBtn = _addBtn(measureId);
    if (!container) return;

    if (container.children.length === 0) {
        container.appendChild(_createLevelRow(measureId, 1));
    }

    if (addBtn && !addBtn._locationLevelsWired) {
        addBtn._locationLevelsWired = true;
        addBtn.addEventListener('click', () => addLocationLevel(measureId));
    }

    _updateAddButton(measureId);
    updateLocationLevelsNumericUI(measureId);
}

function addLocationLevel(measureId) {
    const container = _rowsContainer(measureId);
    if (!container) return;
    const count = _visibleLevelCount(measureId);
    if (count >= MAX_LOCATION_LEVELS) return;
    container.appendChild(_createLevelRow(measureId, count + 1));
    _updateAddButton(measureId);
    updateLocationLevelsNumericUI(measureId);
}

function _updateAddButton(measureId) {
    const addBtn = _addBtn(measureId);
    if (!addBtn) return;
    addBtn.style.display = _visibleLevelCount(measureId) >= MAX_LOCATION_LEVELS ? 'none' : '';
}

function getLocationLevels(measureId) {
    const container = _rowsContainer(measureId);
    if (!container) return [];

    return Array.from(container.querySelectorAll('.location-level-row')).map((row, idx) => {
        const levelNum = idx + 1;
        const prefix = `locLevel-${measureId}-${levelNum}`;
        const builder = document.getElementById(`${prefix}Builder`);
        const tags = builder && builder._getTags ? builder._getTags() : [];
        const numeric = _toggleValue(`locLevelNumeric-${measureId}-${levelNum}`) || 'No';
        return { tags, numeric };
    });
}

function updateLocationLevelsNumericUI(measureId) {
    const levels = getLocationLevels(measureId);
    const numericCount = levels.filter(l => l.numeric === 'Yes').length;

    const biggerGroup = document.getElementById(`locBiggerNumGroup-${measureId}`);
    if (biggerGroup) {
        biggerGroup.style.display = numericCount >= 2 ? '' : 'none';
    }

    levels.forEach((level, idx) => {
        const row = _rowsContainer(measureId)?.querySelectorAll('.location-level-row')[idx];
        if (!row) return;
        const label = row.querySelector('.location-level-tags .field-label');
        if (!label) return;
        const n = idx + 1;
        const optional = n > 1 ? ' <span class="optional">(optional)</span>' : '';
        if (n === 1 && level.numeric === 'Yes') {
            label.innerHTML = 'Location Level 1 <span class="optional">(optional)</span>';
        } else {
            label.innerHTML = _levelLabel(n);
        }
    });
}

window.initLocationLevels = initLocationLevels;
window.addLocationLevel = addLocationLevel;
window.getLocationLevels = getLocationLevels;
window.updateLocationLevelsNumericUI = updateLocationLevelsNumericUI;
