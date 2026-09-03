/**
 * Tab system for the landing page.
 *
 * Tab 0 = "Project Details" (fixed, always present, not closable).
 * Tab 1..N = "measure" tabs (Aquamizer / Lighting / Water Meter),
 * addable via the "+" button and closable (except the last remaining one).
 *
 * Each measure tab starts as just a Measure Type dropdown. Picking a
 * type reveals a Measure Name field + that type's inputs. Switching
 * the dropdown swaps the fields shown; values in hidden sections are
 * not read on submit (see generate-report.js).
 */

let tabCounter = 0;
const measureTabs = []; // [{ id, type, nameEl, panelEl, tabEl }]

const tabStrip = document.getElementById('tabStrip');
const tabPanels = document.getElementById('tabPanels');

/* ── helpers ───────────────────────────────────────────── */

function makeFieldHeadingHtml(label, hint) {
    return `
            <div class="field-heading">
                <label class="field-label">${label}</label>
                ${hint ? `<div class="field-hint">${hint}</div>` : ''}
            </div>`;
}

function makeTagBuilderHtml(idPrefix, label, hint, placeholder) {
    return `
        <div class="field-group">
            ${makeFieldHeadingHtml(label, hint)}
            <div class="tag-builder" id="${idPrefix}Builder">
                <input class="tag-input" id="${idPrefix}Input" placeholder="${placeholder}" autocomplete="off" spellcheck="false" />
            </div>
        </div>`;
}

function makeToggleHtml(group, label, options) {
    const btns = options.map(o => `<button class="toggle" data-group="${group}" data-value="${o}">${o}</button>`).join('');
    return `
        <div class="field-group">
            ${makeFieldHeadingHtml(label, '')}
            <div class="toggle-row">${btns}</div>
        </div>`;
}

/* Minimalist settings-style toggle switch, defaults to off (false).
   Keeps two hidden .toggle buttons in sync so existing code that reads
   state via activeToggleValue()/document click-delegation (form-state.js,
   generate-report.js, updateLightingNumericUI) keeps working unchanged. */
function makeSwitchHtml(group, label, hint, defaultOn = false) {
    const checkedAttr = defaultOn ? ' checked' : '';
    const noActive = defaultOn ? '' : ' active';
    const yesActive = defaultOn ? ' active' : '';
    return `
        <div class="field-group switch-group">
            <div class="switch-group-text field-heading">
                <label class="field-label" for="switch-${group}">${label}</label>
                ${hint ? `<div class="field-hint">${hint}</div>` : ''}
            </div>
            <label class="switch">
                <input type="checkbox" id="switch-${group}" class="switch-input" data-group="${group}"${checkedAttr} />
                <span class="switch-slider"></span>
            </label>
            <button type="button" class="toggle${noActive}" data-group="${group}" data-value="No" hidden tabindex="-1"></button>
            <button type="button" class="toggle${yesActive}" data-group="${group}" data-value="Yes" hidden tabindex="-1"></button>
        </div>`;
}

/* ── measure sub-sections ─────────────────────────────── */

function aquamizerFieldsHtml(id) {
    return `
        <div class="measure-fields" data-type="aquamizer" id="aq-${id}" style="display:none;">
            ${makeSwitchHtml(`multi-${id}`, 'Multiple bathrooms per unit?')}
            <div class="field-group" id="bathNamesGroup-${id}">
                ${makeFieldHeadingHtml('Bathroom names <span class="optional">(optional)</span>', '')}
                <div class="bath-grid">
                    <input class="bath field-input" placeholder="e.g. Master" />
                    <input class="bath field-input" placeholder="e.g. Guest" />
                    <input class="bath field-input" placeholder="e.g. Hall" />
                    <input class="bath field-input" placeholder="e.g. En Suite" />
                </div>
            </div>
            ${makeTagBuilderHtml(`specialRooms-${id}`, 'Special rooms <span class="optional">(optional)</span>',
                'e.g. Lobby, Office, Clubhouse — photos tagged with these names will be sorted into their own sections.',
                'Type a room name, press Enter')}
            ${makeToggleHtml(`format-${id}`, 'Unit label format', ['123', '123 A', 'A 123'])}
        </div>`;
}

function lightingFieldsHtml(id) {
    return `
        <div class="measure-fields" data-type="lighting" id="lt-${id}" style="display:none;">
            ${makeTagBuilderHtml(`installers-${id}`, 'Installers', 'Names of techs tagged in the project.', 'Type a name, press Enter')}
            <div class="location-levels-wrap" id="locationLevelsWrap-${id}">
                <div id="locationLevelRows-${id}"></div>
                <button type="button" class="add-project-btn" id="addLocationLevelBtn-${id}">+ Add Level</button>
            </div>
            <div class="field-divider"></div>
            ${makeTagBuilderHtml(`fixtureTypes-${id}`, 'Fixture types', 'e.g. Wallpack, Vapor Tight, Sconce.', 'Type a fixture type, press Enter')}
            ${makeTagBuilderHtml(`phases-${id}`, 'Phases', 'Usually BEFORE, AFTER, SETTINGS. Type them in the order you\'d like them to appear in the report.', 'Type a phase, press Enter')}
            <div class="field-divider"></div>
            ${makeTagBuilderHtml(`lightingSerialTags-${id}`, 'Serial tags <span class="optional">(optional)</span>', 'Lets the program know what the tag for model number photos looks like (usually SERIAL/PART NUMBER)', 'Type a tag, press Enter')}
            <div id="locBiggerNumGroup-${id}" style="display:none;">
                ${makeSwitchHtml(`locBiggerNum-${id}`, 'Higher location levels have larger numbers')}
            </div>
        </div>`;
}

function heatPumpFieldsHtml(id) {
    return `
        <div class="measure-fields" data-type="heat_pump" id="hp-${id}" style="display:none;">
            ${makeToggleHtml(`hpMultiUnit-${id}`, 'Does this measure include a single unit/location or multiple?', ['Single', 'Multiple'])}
            <div id="hpMultiUnitGroup-${id}" style="display:none;">
                ${makeToggleHtml(`hpLoneNumber-${id}`, 'How many of the location/unit tags are just lone numbers?', ['None', 'Some', 'All'])}
                <div id="hpLocationsGroup-${id}" style="display:none;">
                    ${makeTagBuilderHtml(`hpLocations-${id}`, 'Locations/Units', 'e.g. Basement, Garage, Unit A. Type them in the order you\'d like them to appear in the report.', 'Type a location, press Enter')}
                </div>
            </div>
            ${makeSwitchHtml(`intuitiveFixtureSort-${id}`, 'Intuitive Fixture Sort', 'Automatically sorts photos by fixture type within the BEFORE and AFTER buckets.', true)}
            <div id="hpManualFixtureGroup-${id}" style="display:none;">
                ${makeTagBuilderHtml(`fixtures-${id}`, 'Fixtures <span class="optional">(optional)</span>', 'e.g. Gas Meter, Descaler, Expansion Tank. Photos without a fixture tag stay in their phase bucket.', 'Type a fixture, press Enter')}
                ${makeSwitchHtml(`allowCompetingFixtures-${id}`, 'Allow Competing Fixture Tags', 'When enabled, photos tagged with multiple fixtures are assigned to the first matching fixture instead of Untagged.')}
            </div>
            ${makeTagBuilderHtml(`heatPumpSerialTags-${id}`, 'Serial tags <span class="optional">(optional)</span>', 'Lets the program know what the tag for model number photos looks like (usually SERIAL/PART NUMBER)', 'Type a tag, press Enter')}
            ${makeSwitchHtml(`autoAssignLoneSerial-${id}`, 'Auto-assign Lone S/PN Photos to Before', 'When enabled, photos tagged with the serial tag but no BEFORE or AFTER tag are placed in BEFORE — SERIAL NUMBERS.')}
            <div class="basic-mode-drawer-anchor"></div>
        </div>`;
}

function waterMeterFieldsHtml(id) {
    return `
        <div class="measure-fields" data-type="water_meter" id="wm-${id}" style="display:none;">
            <div class="coming-soon">Water Meter support is coming soon — check back later.</div>
        </div>`;
}

function subcontractedFieldsHtml(id) {
    return `
        <div class="measure-fields" data-type="subcontracted" id="sc-${id}" style="display:none;">
            <div class="field-group">
                ${makeFieldHeadingHtml('Photo identification', 'Where to look for the subcon key on each photo.')}
                <div class="toggle-row">
                    <button type="button" class="toggle active" data-group="subconKey-${id}" data-value="Tags">Tags</button>
                    <button type="button" class="toggle" data-group="subconKey-${id}" data-value="Description">Description</button>
                </div>
            </div>
            <div class="field-group">
                ${makeFieldHeadingHtml('Hash', 'Single special character that prefixes every photo tag or description (e.g. #, !, $).')}
                <input class="field-input subcontract-hash" maxlength="1" placeholder="e.g. #" autocomplete="off" />
            </div>
            <div class="field-group">
                ${makeFieldHeadingHtml('Measure Mark <span class="optional">(optional)</span>', 'Single letter after the hash when multiple subcontracted measures share the same hash.')}
                <input class="field-input subcontract-mark" maxlength="1" placeholder="e.g. S" autocomplete="off" />
            </div>
            <div class="basic-mode-drawer-anchor"></div>
        </div>`;
}

function manualArrangeFieldsHtml(id) {
    return `
        <div class="measure-fields" data-type="manual_arrange" id="ma-${id}" style="display:none;">
            ${makeTagBuilderHtml(`preSortBuckets-${id}`, 'Pre-sort Buckets <span class="optional">(optional)</span>',
                'Optionally pre-sorts your photos by only these tags for faster access while sorting. Leave blank to have everything dumped into the staging area',
                'Type a tag, press Enter')}
            ${makeSwitchHtml(`allowConflictingTags-${id}`, 'Allow Conflicting Tags to Self-Determine',
                'When enabled, photos tagged with multiple bucket tags are assigned to the first matching bucket. When off, they go to the staging area.',
                true)}
            <div class="basic-mode-drawer-anchor"></div>
        </div>`;
}

/* ── measure tab creation ─────────────────────────────── */

const measureTypeLabels = {
    aquamizer: 'Aquamizer',
    lighting: 'Lighting',
    heat_pump: 'Water Heaters / Heat Pumps',
    subcontracted: 'Subcontracted',
    manual_arrange: 'Manual Arrange',
    water_meter: 'Water Meter',
};

function updateMeasureTabLabel(entry) {
    const lbl = entry.tabEl && entry.tabEl.querySelector('.tab-label');
    if (!lbl) return;
    const nameInput = entry.panelEl.querySelector('.measure-name');
    const customName = nameInput && nameInput.value.trim();
    lbl.textContent = customName || measureTypeLabels[entry.type] || 'New Measure';
}

function createMeasureTab() {
    const id = `m${++tabCounter}`;

    const tabEl = document.createElement('button');
    tabEl.className = 'tab';
    tabEl.dataset.tabId = id;
    tabEl.innerHTML = `<span class="tab-label">New Measure</span><span class="tab-close" title="Remove tab">&#x2715;</span>`;
    tabStrip.insertBefore(tabEl, document.getElementById('tabAddBtn'));

    const panelEl = document.createElement('div');
    panelEl.className = 'tab-panel';
    panelEl.id = `panel-${id}`;
    panelEl.innerHTML = `
        <div class="field-group">
            ${makeFieldHeadingHtml('Measure Type', '')}
            <select class="field-input measure-select" id="measureType-${id}">
                <option value="">Select a measure type…</option>
                <option value="aquamizer">Aquamizer</option>
                <option value="lighting">Lighting</option>
                <option value="heat_pump">Water Heaters / Heat Pumps</option>
                <option value="subcontracted">Subcontracted</option>
                <option value="manual_arrange">Manual Arrange</option>
                <option value="water_meter">Water Meter</option>
            </select>
        </div>
        <div class="measure-body" id="measureBody-${id}" style="display:none;">
            <div class="field-group">
                ${makeFieldHeadingHtml('Measure Name <span class="optional">(optional)</span>', '')}
                <input class="field-input measure-name" placeholder="e.g. Knolls 15, HVAC, Lighting" autocomplete="off" />
            </div>
            ${makeTagBuilderHtml(`measureKeywords-${id}`, 'Measure Keywords <span class="optional">(optional)</span>',
                '', 'Type a keyword, press Enter')}
            ${aquamizerFieldsHtml(id)}
            ${lightingFieldsHtml(id)}
            ${heatPumpFieldsHtml(id)}
            ${subcontractedFieldsHtml(id)}
            ${manualArrangeFieldsHtml(id)}
            ${waterMeterFieldsHtml(id)}
            <div class="applicable-projects-section field-group" id="applicableProjects-${id}" style="display:none;">
                ${makeFieldHeadingHtml('Which projects contain photos for this measure?', 'Select at least one project. Each complete project must be assigned to at least one measure.')}
                <div class="project-checklist" id="projectChecklist-${id}"></div>
            </div>
        </div>`;
    tabPanels.appendChild(panelEl);

    // Init tag builders inside this panel (they're hidden but still fine to init).
    panelEl.querySelectorAll('.tag-builder').forEach(b => window.initTagBuilder(b));
    if (typeof window.initLocationLevels === 'function') {
        window.initLocationLevels(id);
    }

    const select = panelEl.querySelector('.measure-select');
    select.addEventListener('change', () => onMeasureTypeChange(id, select.value));

    const entry = { id, type: null, tabEl, panelEl };
    measureTabs.push(entry);

    const nameInput = panelEl.querySelector('.measure-name');
    if (nameInput) {
        nameInput.addEventListener('input', () => updateMeasureTabLabel(entry));
    }

    tabEl.addEventListener('click', (e) => {
        if (e.target.closest('.tab-close')) {
            removeMeasureTab(id);
        } else {
            activateTab(id);
        }
    });

    activateTab(id);
    if (typeof window.applyBasicModeUI === 'function') window.applyBasicModeUI(panelEl);
    return entry;
}

function updateLightingNumericUI(id) {
    if (typeof window.updateLocationLevelsNumericUI === 'function') {
        window.updateLocationLevelsNumericUI(id);
    }
}

function updateHeatPumpFixtureUI(id) {
    const group = document.getElementById(`hpManualFixtureGroup-${id}`);
    if (!group) return;
    const intuitiveOn = document.querySelector(
        `button.toggle.active[data-group="intuitiveFixtureSort-${id}"]`
    );
    const isOn = intuitiveOn && intuitiveOn.dataset.value === 'Yes';
    group.style.display = isOn ? 'none' : '';
}

function updateHeatPumpLocationUI(id) {
    const multiGroup = document.getElementById(`hpMultiUnitGroup-${id}`);
    const locGroup = document.getElementById(`hpLocationsGroup-${id}`);
    if (!multiGroup) return;

    const multiVal = document.querySelector(
        `button.toggle.active[data-group="hpMultiUnit-${id}"]`
    );
    const isMultiple = multiVal && multiVal.dataset.value === 'Multiple';
    multiGroup.style.display = isMultiple ? '' : 'none';

    if (!isMultiple || !locGroup) return;

    const loneVal = document.querySelector(
        `button.toggle.active[data-group="hpLoneNumber-${id}"]`
    );
    const mode = loneVal ? loneVal.dataset.value : '';
    locGroup.style.display = (mode === 'None' || mode === 'Some') ? '' : 'none';
}

function onMeasureTypeChange(id, type) {
    const entry = measureTabs.find(t => t.id === id);
    if (!entry) return;
    entry.type = type;

    const body = document.getElementById(`measureBody-${id}`);
    if (body) body.style.display = type ? 'block' : 'none';

    entry.panelEl.querySelectorAll('.measure-fields').forEach(f => {
        f.style.display = (f.dataset.type === type) ? 'block' : 'none';
    });

    const kwBuilder = document.getElementById(`measureKeywords-${id}Builder`);
    if (kwBuilder) {
        const kwGroup = kwBuilder.closest('.field-group');
        if (kwGroup) kwGroup.style.display = (type === 'subcontracted' || type === 'manual_arrange') ? 'none' : '';
    }

    if (type === 'lighting') updateLightingNumericUI(id);
    if (type === 'heat_pump') {
        updateHeatPumpFixtureUI(id);
        updateHeatPumpLocationUI(id);
    }

    updateMeasureTabLabel(entry);
    refreshProjectChecklists();
    if (typeof window.applyBasicModeUI === 'function') window.applyBasicModeUI(panelEl);
}

function removeMeasureTab(id) {
    if (measureTabs.length <= 1) return; // keep at least one measure tab
    const idx = measureTabs.findIndex(t => t.id === id);
    if (idx === -1) return;
    const [entry] = measureTabs.splice(idx, 1);
    entry.tabEl.remove();
    entry.panelEl.remove();

    if (getActiveTabId() === id) {
        const fallback = measureTabs[Math.max(0, idx - 1)] || measureTabs[0];
        activateTab(fallback ? fallback.id : 'project');
    }
}

/* ── tab switching (works for 'project' and measure ids) ─ */

function activateTab(id) {
    document.querySelectorAll('.tab').forEach(t => t.classList.toggle('active', t.dataset.tabId === id));
    document.querySelectorAll('.tab-panel').forEach(p => p.classList.toggle('active', p.id === `panel-${id}`));
}

function getActiveTabId() {
    const active = document.querySelector('.tab.active');
    return active ? active.dataset.tabId : 'project';
}

/* ── wiring ────────────────────────────────────────────── */

document.getElementById('projectTab').addEventListener('click', () => activateTab('project'));
document.getElementById('tabAddBtn').addEventListener('click', () => createMeasureTab());

// Switch inputs stay in sync with the hidden .toggle buttons they're paired
// with, so all existing state-reading/UI-reaction code keeps working as-is.
document.addEventListener('change', (e) => {
    const input = e.target.closest('input.switch-input');
    if (!input) return;
    const group = input.dataset.group;
    const value = input.checked ? 'Yes' : 'No';
    const btn = document.querySelector(`button.toggle[data-group="${group}"][data-value="${value}"]`);
    if (btn) btn.click();
    if (group && group.startsWith('intuitiveFixtureSort-')) {
        updateHeatPumpFixtureUI(group.replace('intuitiveFixtureSort-', ''));
    }
});

window.updateHeatPumpLocationUI = updateHeatPumpLocationUI;
window.updateHeatPumpFixtureUI = updateHeatPumpFixtureUI;

// Start with one measure tab already present.
createMeasureTab();
activateTab('project');

function _getCheckedProjectIds(measureId) {
    const checklist = document.getElementById(`projectChecklist-${measureId}`);
    if (!checklist) return [];
    return Array.from(checklist.querySelectorAll('input[type="checkbox"]:checked'))
        .map(cb => cb.value);
}

function _collectProjectClaims() {
    const manualArrange = new Map();
    const other = new Map();
    measureTabs.forEach(entry => {
        if (!entry.type) return;
        const checked = _getCheckedProjectIds(entry.id);
        checked.forEach(pid => {
            if (entry.type === 'manual_arrange') {
                manualArrange.set(pid, entry.id);
            } else {
                other.set(pid, entry.id);
            }
        });
    });
    return { manualArrange, other };
}

function _onProjectCheckboxChange(changedMeasureId, projectId, isManualArrange, isChecked) {
    if (!isChecked) return;
    measureTabs.forEach(entry => {
        if (entry.id === changedMeasureId || !entry.type) return;
        const incompatible = isManualArrange
            ? entry.type !== 'manual_arrange'
            : entry.type === 'manual_arrange';
        if (!incompatible) return;
        const checklist = document.getElementById(`projectChecklist-${entry.id}`);
        if (!checklist) return;
        checklist.querySelectorAll('input[type="checkbox"]').forEach(cb => {
            if (cb.value === projectId) cb.checked = false;
        });
    });
}

function refreshProjectChecklists() {
    const multi = typeof window.isMultiProject === 'function' && window.isMultiProject();
    const pairs = multi && typeof window.getCompleteProjectPairs === 'function'
        ? window.getCompleteProjectPairs()
        : [];

    const { manualArrange: maClaims, other: otherClaims } = _collectProjectClaims();

    measureTabs.forEach(entry => {
        const section = document.getElementById(`applicableProjects-${entry.id}`);
        const checklist = document.getElementById(`projectChecklist-${entry.id}`);
        if (!section || !checklist) return;

        const show = multi && entry.type;
        section.style.display = show ? 'block' : 'none';
        if (!show) return;

        const previouslyChecked = new Set(_getCheckedProjectIds(entry.id));
        const isManualArrange = entry.type === 'manual_arrange';
        checklist.innerHTML = '';

        pairs.forEach(pair => {
            const label = document.createElement('label');
            const cb = document.createElement('input');
            cb.type = 'checkbox';
            cb.value = pair.id;
            cb.dataset.nickname = pair.nickname;
            cb.checked = previouslyChecked.size > 0
                ? previouslyChecked.has(pair.id)
                : pairs.length === 1;

            const blockedByOther = isManualArrange && otherClaims.has(pair.id)
                && otherClaims.get(pair.id) !== entry.id;
            const blockedByMa = !isManualArrange && maClaims.has(pair.id)
                && maClaims.get(pair.id) !== entry.id;
            if (blockedByOther || blockedByMa) {
                cb.disabled = true;
                cb.checked = false;
                label.classList.add('project-check-disabled');
                label.title = isManualArrange
                    ? 'This project is assigned to another measure type.'
                    : 'This project is assigned to a Manual Arrange measure.';
            }

            cb.addEventListener('change', () => {
                _onProjectCheckboxChange(entry.id, pair.id, isManualArrange, cb.checked);
                refreshProjectChecklists();
            });

            label.appendChild(cb);
            label.appendChild(document.createTextNode(pair.nickname));
            checklist.appendChild(label);
        });
    });
}

if (typeof window.onProjectPairsChange === 'function') {
    window.onProjectPairsChange(refreshProjectChecklists);
}

// Exposed for generate-report.js
window.getMeasureTabs = () => measureTabs;
window.getCheckedProjectIds = _getCheckedProjectIds;
window.refreshProjectChecklists = refreshProjectChecklists;
window.updateLightingNumericUI = updateLightingNumericUI;