// ============================================================
// PDF DASHBOARD CONTROLLER
// ============================================================
 
// ── State ────────────────────────────────────────────────────
let _pdfLayout            = 'grid';
let _hideEmptyFields      = false;
let _hiddenPhotoUrls      = new Set();
let _photoSelectMode      = false;
let _tempHiddenUrls       = new Set();
let _measureInclusion     = {}; // { [measure_id]: boolean }
let _measureShowTags      = {}; // { [measure_id]: boolean }
let _measureHeadingSize   = {}; // { [measure_id]: 'none'|'normal'|'large'|'full_page' }
let _measureHeadingVisibility = {}; // { [measure_id]: { [heading_key]: boolean } }
let _measureHeadingLabels = {}; // { [measure_id]: { [heading_instance_key]: string } }
let _metadataPosition     = 'outside';
let _linearPhotosPerPage  = 4;
let _gridAvailable        = true;

const GRID_INCOMPATIBLE_SORT_MODES = [
    'location_sublocation_type_fixture_phase',
    'heat_pump_phase_serial_buckets',
];
const GRID_INCOMPATIBLE_DATASETS = ['lighting', 'heat_pump'];

// Cover-field state: array of { key, label, value, visible }
// Populated once on first open, then kept in sync with the UI.
let _coverFields = [];

// ── Open / Close modal ───────────────────────────────────────
function openPdfDashboard() {
    if (window.AutoRecReportAnalytics) window.AutoRecReportAnalytics.markPdfOpened();
    document.getElementById('pdfDashboardOverlay').classList.add('active');
    document.getElementById('hideEmptyCheck').checked = _hideEmptyFields;
    if (_coverFields.length === 0) initCoverFields();
    initPdfMeasureTabs();
    updateGridAvailability();
    refreshHideCount();
    syncCoverPhotoCount();
    if (_photoSelectMode) endPhotoSelectMode(false);
    updateLayoutDependentRows();
}

function closePdfDashboard(e) {
    if (e && e.target !== document.getElementById('pdfDashboardOverlay')) return;
    if (_photoSelectMode) endPhotoSelectMode(false);
    document.getElementById('pdfDashboardOverlay').classList.remove('active');
}

document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape') {
        if (_photoSelectMode) { endPhotoSelectMode(false); return; }
        document.getElementById('pdfDashboardOverlay').classList.remove('active');
    }
});

// ── PDF Dashboard Tab Switching ──────────────────────────────
function switchPdfTab(tabId) {
    document.querySelectorAll('.pdf-modal-tab-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.pdfTab === tabId || (tabId === 'general' && btn.id === 'pdfTabBtnGeneral'));
    });
    document.querySelectorAll('.pdf-modal-tab-pane').forEach(pane => {
        pane.classList.remove('active');
    });
    if (tabId === 'general') {
        const genPane = document.getElementById('pdfTabPaneGeneral');
        if (genPane) genPane.classList.add('active');
    } else {
        const pane = document.getElementById('pdfTabPaneMeasure_' + tabId);
        if (pane) pane.classList.add('active');
    }
}

function _headingTypesForMeasure(tabId, sortMode) {
    const schema = window._measureHeadingSchema || {};
    if (schema[tabId] && schema[tabId].length) return schema[tabId];
    // Fallback when schema not embedded (legacy report.html)
    const shape = sortMode || '';
    if (shape === 'location_sublocation_type_fixture_phase') {
        return [
            { key: 'location_level_1', label: 'Location Level 1' },
            { key: 'fixture_type', label: 'Fixture Type' },
        ];
    }
    if (shape === 'full') {
        return [
            { key: 'building', label: 'Building' },
            { key: 'unit', label: 'Unit' },
            { key: 'bathroom', label: 'Bathroom' },
        ];
    }
    if (shape === 'bldg_unit_phase') {
        return [{ key: 'building', label: 'Building' }, { key: 'unit', label: 'Unit' }];
    }
    if (shape === 'unit_bath_phase') {
        return [{ key: 'unit', label: 'Unit' }, { key: 'bathroom', label: 'Bathroom' }];
    }
    if (shape === 'unit_phase') return [{ key: 'unit', label: 'Unit' }];
    if (shape === 'heat_pump_phase_serial_buckets') {
        return [
            { key: 'location', label: 'Location' },
            { key: 'bucket', label: 'Serial Bucket' },
        ];
    }
    if (shape === 'subcontracted_sequence') {
        return [{ key: 'section', label: 'Section Headings' }];
    }
    if (shape === 'manual_arrange_sequence') {
        return [{ key: 'section', label: 'Section Headings' }];
    }
    return [];
}

function _ensureHeadingVisibility(tabId, headingTypes) {
    if (!_measureHeadingVisibility[tabId]) _measureHeadingVisibility[tabId] = {};
    headingTypes.forEach(ht => {
        if (_measureHeadingVisibility[tabId][ht.key] === undefined) {
            _measureHeadingVisibility[tabId][ht.key] = true;
        }
    });
}

function _ensureHeadingLabels(tabId, catalogEntries) {
    if (!_measureHeadingLabels[tabId]) _measureHeadingLabels[tabId] = {};
    (catalogEntries || []).forEach(entry => {
        if (_measureHeadingLabels[tabId][entry.key] === undefined) {
            _measureHeadingLabels[tabId][entry.key] = '';
        }
    });
}

function _headingTypeLabel(typeKey, headingTypes) {
    if (typeKey === 'special') return 'Special Area';
    const match = (headingTypes || []).find(ht => ht.key === typeKey);
    if (match) return match.label;
    const levelMatch = /^location_level_(\d+)$/.exec(typeKey || '');
    if (levelMatch) return 'Location Level ' + levelMatch[1];
    return typeKey;
}

function _pruneHeadingLabels(tabId, catalogEntries) {
    const labels = _measureHeadingLabels[tabId] || {};
    const pruned = {};
    (catalogEntries || []).forEach(entry => {
        const val = (labels[entry.key] || '').trim();
        if (val && val !== entry.default_label) {
            pruned[entry.key] = val;
        }
    });
    return pruned;
}

function countHeadingLabelEdits() {
    const catalog = window._automaticHeadingCatalog || {};
    let count = 0;
    Object.keys(catalog).forEach(tabId => {
        count += Object.keys(_pruneHeadingLabels(tabId, catalog[tabId])).length;
    });
    return count;
}

function _buildHeadingLabelEditor(tabId, headingTypes, catalogEntries, container) {
    if (!catalogEntries || catalogEntries.length === 0) return;

    _ensureHeadingLabels(tabId, catalogEntries);

    const renameLabel = document.createElement('div');
    renameLabel.className = 'pdf-measure-option-label pdf-heading-rename-label';
    renameLabel.textContent = 'Rename PDF Headings';
    container.appendChild(renameLabel);

    const renameHint = document.createElement('p');
    renameHint.className = 'pdf-measure-option-hint';
    renameHint.textContent = 'Customize individual heading text in the exported PDF. Leave blank to use the default.';
    container.appendChild(renameHint);

    const grouped = {};
    catalogEntries.forEach(entry => {
        const groupKey = entry.type || 'other';
        if (!grouped[groupKey]) grouped[groupKey] = [];
        grouped[groupKey].push(entry);
    });

    const renameGroup = document.createElement('div');
    renameGroup.className = 'pdf-heading-rename-group';

    Object.keys(grouped).forEach(groupKey => {
        const section = document.createElement('div');
        section.className = 'pdf-heading-rename-section';

        const sectionTitle = document.createElement('div');
        sectionTitle.className = 'pdf-heading-rename-section-title';
        sectionTitle.textContent = _headingTypeLabel(groupKey, headingTypes);
        section.appendChild(sectionTitle);

        grouped[groupKey].forEach(entry => {
            const row = document.createElement('label');
            row.className = 'pdf-heading-rename-row';

            const input = document.createElement('input');
            input.type = 'text';
            input.className = 'pdf-heading-rename-input';
            input.value = _measureHeadingLabels[tabId][entry.key] || '';
            input.placeholder = entry.default_label;
            input.dataset.headingKey = entry.key;
            input.addEventListener('input', function() {
                _measureHeadingLabels[tabId][entry.key] = this.value;
            });

            const meta = document.createElement('span');
            meta.className = 'pdf-heading-rename-default';
            meta.textContent = 'Default: ' + entry.default_label;

            row.appendChild(input);
            row.appendChild(meta);
            section.appendChild(row);
        });

        renameGroup.appendChild(section);
    });

    container.appendChild(renameGroup);
}

function initPdfMeasureTabs() {
    const measureTabsContainer = document.getElementById('pdfModalMeasureTabs');
    const measurePanesContainer = document.getElementById('pdfTabPanesMeasures');
    if (!measureTabsContainer || !measurePanesContainer) return;

    // Discover measures from the HTML report tab navigation
    const reportTabBtns = document.querySelectorAll('.tab-nav .tab-btn');
    if (reportTabBtns.length === 0) {
        measureTabsContainer.innerHTML = '';
        measurePanesContainer.innerHTML = '';
        return;
    }

    // Only build once, or update if not yet rendered
    if (measureTabsContainer.children.length > 0) return;

    measureTabsContainer.innerHTML = '';
    measurePanesContainer.innerHTML = '';

    reportTabBtns.forEach(btn => {
        const tabId = btn.getAttribute('data-tab');
        const tabLabel = btn.textContent.trim();
        const isUnknown = (tabId === '__unknown__');

        // Set default inclusion: true for standard measures, false for Unknown Measure
        if (_measureInclusion[tabId] === undefined) {
            _measureInclusion[tabId] = !isUnknown;
        }
        if (_measureShowTags[tabId] === undefined) {
            _measureShowTags[tabId] = true;
        }
        if (_measureHeadingSize[tabId] === undefined) {
            _measureHeadingSize[tabId] = 'normal';
        }

        // Tab button in modal nav
        const tabBtn = document.createElement('button');
        tabBtn.className = 'pdf-modal-tab-btn';
        tabBtn.dataset.pdfTab = tabId;
        //tabBtn.textContent = (isUnknown ? '❓ ' : '📊 ') + tabLabel;
        tabBtn.textContent = tabLabel;
        tabBtn.onclick = () => switchPdfTab(tabId);
        measureTabsContainer.appendChild(tabBtn);

        // Tab pane
        const pane = document.createElement('div');
        pane.className = 'pdf-modal-tab-pane';
        pane.id = 'pdfTabPaneMeasure_' + tabId;

        // Card with Include Checkbox
        const headerCard = document.createElement('div');
        headerCard.className = 'pdf-measure-header-card';

        const infoDiv = document.createElement('div');
        infoDiv.className = 'pdf-measure-info';
        const titleSpan = document.createElement('span');
        titleSpan.className = 'pdf-measure-title';
        titleSpan.textContent = tabLabel;
        const subSpan = document.createElement('span');
        subSpan.className = 'pdf-measure-subtitle';
        subSpan.textContent = isUnknown
            ? 'Photos that did not match any configured measure'
            : 'Measure configuration & export options';
        infoDiv.appendChild(titleSpan);
        infoDiv.appendChild(subSpan);

        const toggleLabel = document.createElement('label');
        toggleLabel.className = 'pdf-measure-include-toggle';
        const cb = document.createElement('input');
        cb.type = 'checkbox';
        cb.checked = _measureInclusion[tabId];
        cb.addEventListener('change', function() {
            _measureInclusion[tabId] = this.checked;
            updateGridAvailability();
        });
        const toggleText = document.createElement('span');
        toggleText.textContent = 'Include in PDF';
        toggleLabel.appendChild(cb);
        toggleLabel.appendChild(toggleText);

        headerCard.appendChild(infoDiv);
        headerCard.appendChild(toggleLabel);
        pane.appendChild(headerCard);

        const customDiv = document.createElement('div');
        customDiv.className = 'pdf-measure-custom-options';

        const tagsLabel = document.createElement('label');
        tagsLabel.className = 'pdf-option-row pdf-measure-option-row';
        const tagsCb = document.createElement('input');
        tagsCb.type = 'checkbox';
        tagsCb.checked = _measureShowTags[tabId];
        tagsCb.addEventListener('change', function() {
            _measureShowTags[tabId] = this.checked;
        });
        const tagsText = document.createElement('div');
        tagsText.className = 'pdf-option-row-text';
        tagsText.innerHTML = '<span class="pdf-option-row-title">Show Photo Tags</span>'
            + '<span class="pdf-option-row-hint">Display CompanyCam tags alongside each photo in the PDF caption area.</span>';
        tagsLabel.appendChild(tagsCb);
        tagsLabel.appendChild(tagsText);
        customDiv.appendChild(tagsLabel);

        const headingLabel = document.createElement('div');
        headingLabel.className = 'pdf-measure-option-label';
        headingLabel.textContent = 'Measure Heading Size';
        customDiv.appendChild(headingLabel);

        const headingToggle = document.createElement('div');
        headingToggle.className = 'segmented-toggle pdf-measure-heading-toggle';
        [
            { value: 'none', label: 'None' },
            { value: 'normal', label: 'Normal' },
            { value: 'large', label: 'Large' },
            { value: 'full_page', label: 'Full-Page' },
        ].forEach(opt => {
            const btn = document.createElement('button');
            btn.type = 'button';
            btn.className = 'segment-btn' + (_measureHeadingSize[tabId] === opt.value ? ' selected' : '');
            btn.dataset.value = opt.value;
            btn.textContent = opt.label;
            btn.onclick = () => selectMeasureHeadingSize(tabId, opt.value, headingToggle);
            headingToggle.appendChild(btn);
        });
        customDiv.appendChild(headingToggle);

        const sortMode = btn.getAttribute('data-sort-mode') || '';
        const headingTypes = _headingTypesForMeasure(tabId, sortMode);
        if (!isUnknown && headingTypes.length > 0) {
            _ensureHeadingVisibility(tabId, headingTypes);

            const pdfHeadingsLabel = document.createElement('div');
            pdfHeadingsLabel.className = 'pdf-measure-option-label';
            pdfHeadingsLabel.textContent = 'PDF Headings';
            customDiv.appendChild(pdfHeadingsLabel);

            const headingsGroup = document.createElement('div');
            headingsGroup.className = 'pdf-heading-visibility-group';

            headingTypes.forEach(ht => {
                const row = document.createElement('label');
                row.className = 'pdf-option-row pdf-measure-option-row pdf-heading-visibility-row';
                const hCb = document.createElement('input');
                hCb.type = 'checkbox';
                hCb.checked = _measureHeadingVisibility[tabId][ht.key];
                hCb.addEventListener('change', function() {
                    _measureHeadingVisibility[tabId][ht.key] = this.checked;
                });
                const hText = document.createElement('div');
                hText.className = 'pdf-option-row-text';
                hText.innerHTML = '<span class="pdf-option-row-title">' + ht.label + '</span>'
                    + '<span class="pdf-option-row-hint">Show this heading type in the PDF for this measure.</span>';
                row.appendChild(hCb);
                row.appendChild(hText);
                headingsGroup.appendChild(row);
            });
            customDiv.appendChild(headingsGroup);
        }

        const catalogEntries = (window._automaticHeadingCatalog || {})[tabId] || [];
        if (!isUnknown && catalogEntries.length > 0) {
            _buildHeadingLabelEditor(tabId, headingTypes, catalogEntries, customDiv);
        }

        if (isUnknown) {
            const hint = document.createElement('p');
            hint.className = 'pdf-measure-option-hint';
            hint.textContent = 'When included, unmatched photos will appear in an Untagged section in the PDF report.';
            customDiv.appendChild(hint);
        }

        pane.appendChild(customDiv);

        measurePanesContainer.appendChild(pane);
    });
}
 
// ── Layout selection ─────────────────────────────────────────
function selectLayout(layout) {
    if (layout === 'grid' && !_gridAvailable) return;
    _pdfLayout = layout;
    document.getElementById('layoutBtnGrid').classList.toggle('selected',   layout === 'grid');
    document.getElementById('layoutBtnLinear').classList.toggle('selected', layout === 'linear');
    updateLayoutDependentRows();
}

function updateLayoutDependentRows() {
    const isGrid = _pdfLayout === 'grid';
    const metaRow = document.getElementById('metadataPositionRow');
    const linearRow = document.getElementById('linearPhotosRow');
    if (metaRow) metaRow.style.display = isGrid ? '' : 'none';
    if (linearRow) linearRow.style.display = isGrid ? 'none' : '';
}

function selectMetadataPosition(value) {
    _metadataPosition = value;
    document.querySelectorAll('#metadataPositionToggle .segment-btn').forEach(btn => {
        btn.classList.toggle('selected', btn.dataset.value === value);
    });
}

function selectLinearPhotosPerPage(value) {
    _linearPhotosPerPage = value;
    document.querySelectorAll('#linearPhotosToggle .segment-btn').forEach(btn => {
        btn.classList.toggle('selected', parseInt(btn.dataset.value, 10) === value);
    });
}

function selectMeasureHeadingSize(tabId, value, container) {
    _measureHeadingSize[tabId] = value;
    if (container) {
        container.querySelectorAll('.segment-btn').forEach(btn => {
            btn.classList.toggle('selected', btn.dataset.value === value);
        });
    }
}

function _reportUsesGridIncompatibleMeasure() {
    const reportTabBtns = document.querySelectorAll('.tab-nav .tab-btn');
    if (reportTabBtns.length === 0) {
        const params = new URLSearchParams(window.location.search);
        const dk = (params.get('dataset_key') || params.get('dataset') || 'plumbing').toLowerCase();
        return GRID_INCOMPATIBLE_DATASETS.includes(dk);
    }
    const includedIds = Object.keys(_measureInclusion).filter(id => _measureInclusion[id]);
    const idsToCheck = includedIds.length > 0 ? includedIds : [...reportTabBtns].map(b => b.getAttribute('data-tab'));
    for (const tabId of idsToCheck) {
        const btn = document.querySelector(`.tab-nav .tab-btn[data-tab="${tabId}"]`);
        const sortMode = btn ? btn.getAttribute('data-sort-mode') : '';
        if (GRID_INCOMPATIBLE_SORT_MODES.includes(sortMode)) return true;
    }
    return false;
}

function updateGridAvailability() {
    _gridAvailable = !_reportUsesGridIncompatibleMeasure();
    const gridBtn = document.getElementById('layoutBtnGrid');
    if (gridBtn) gridBtn.classList.toggle('disabled', !_gridAvailable);
    if (!_gridAvailable && _pdfLayout === 'grid') selectLayout('linear');
}
 
// ── Hide-empty checkbox ──────────────────────────────────────
document.getElementById('hideEmptyCheck').addEventListener('change', function() {
    _hideEmptyFields = this.checked;
});
 
// ── Cover page fields ─────────────────────────────────────────────────────────
// Derive sensible defaults from the URL params baked into the report page.
function getOriginalProjectName(params) {
    return params.get('project_name') || params.get('package_id') || params.get('project_id') || '';
}

function getEffectiveProjectName(params) {
    const field = _coverFields.find(f => f.key === 'project_name');
    if (field && field.visible && field.value.trim()) {
        return field.value.trim();
    }
    return getOriginalProjectName(params);
}

function getCoverDefaults() {
    const p = new URLSearchParams(window.location.search);
    const projectName = getOriginalProjectName(p);
    // Date formatted the same way Python does it in context['date_generated']
    const today = new Date();
    const months = ['January','February','March','April','May','June',
                    'July','August','September','October','November','December'];
    const dateStr = `${months[today.getMonth()]} ${String(today.getDate()).padStart(2,'0')}, ${today.getFullYear()}`;
 
    return [
        { key: 'subtitle',         label: 'Subtitle',       value: 'INSTALLATION PHOTOS' },
        { key: 'project_name',     label: 'Project Name',   value: projectName.toUpperCase() },
        { key: 'address',          label: 'Address',        value: p.get('project_address') || '' },
        { key: 'date',             label: 'Date Line',      value: `Date: ${dateStr}` },
        { key: 'total_buildings',  label: 'Buildings',      value: '' },
        { key: 'total_units',      label: 'Units',          value: '' },
        { key: 'total_bathrooms',  label: 'Bathrooms',      value: '' },
        { key: 'total_photos',     label: 'Total Photos',   value: '' },
        { key: 'layout',           label: 'Layout Badge',   value: '' },
    ];
}
 
function initCoverFields() {
    _coverFields = getCoverDefaults().map(f => ({ ...f, visible: true }));
    renderCoverEditor();
    syncCoverPhotoCount();
}
 
function renderCoverEditor() {
    const container = document.getElementById('coverFieldsContainer');
    if (!container) return;
    container.innerHTML = '';
 
    _coverFields.forEach((field, idx) => {
        const row = document.createElement('div');
        row.className = 'cover-field-row' + (field.visible ? '' : ' cover-field-hidden');
        row.dataset.idx = idx;
 
        // Visibility toggle
        const toggle = document.createElement('input');
        toggle.type = 'checkbox';
        toggle.className = 'cover-field-toggle';
        toggle.checked = field.visible;
        toggle.title = 'Include this line on the cover page';
        toggle.addEventListener('change', function() {
            _coverFields[idx].visible = this.checked;
            row.classList.toggle('cover-field-hidden', !this.checked);
            inp.disabled = !this.checked;
        });
 
        // Label
        const lbl = document.createElement('span');
        lbl.className = 'cover-field-label';
        lbl.textContent = field.label;
 
        // Text input
        const inp = document.createElement('input');
        inp.type = 'text';
        inp.className = 'cover-field-input';
        inp.placeholder = field.value || '(auto)';
        inp.value = field.value;
        inp.disabled = !field.visible;
        inp.addEventListener('input', function() {
            _coverFields[idx].value = this.value;
        });
 
        row.appendChild(toggle);
        row.appendChild(lbl);
        row.appendChild(inp);
        container.appendChild(row);
    });
}
 
// ── Photo selection mode ─────────────────────────────────────
function _cardsInElement(el) {
    return el ? [...el.querySelectorAll('.photo-card')] : [];
}

function _cardsUnderSubcontractHeading(heading) {
    const grid = heading.closest('.subcontract-grid');
    if (!grid) return [];
    const cards = [];
    let sibling = heading.nextElementSibling;
    while (sibling) {
        if (sibling.classList.contains('subcontract-heading')) break;
        if (sibling.classList.contains('photo-card')) cards.push(sibling);
        sibling = sibling.nextElementSibling;
    }
    return cards;
}

function _setCardsHidden(cards, hidden) {
    cards.forEach(card => {
        const url = photoCardUrl(card);
        if (!url) return;
        const cb = card.querySelector('.pdf-hide-checkbox');
        if (hidden) {
            _tempHiddenUrls.add(url);
            card.classList.add('pdf-hidden-selected');
        } else {
            _tempHiddenUrls.delete(url);
            card.classList.remove('pdf-hidden-selected');
        }
        if (cb) cb.checked = hidden;
    });
    refreshSelectModeCount();
}

function _syncGroupCheckbox(groupCb, cards) {
    if (!groupCb || !cards.length) {
        if (groupCb) {
            groupCb.checked = false;
            groupCb.indeterminate = false;
        }
        return;
    }
    const hiddenCount = cards.filter(card => {
        const url = photoCardUrl(card);
        return url && _tempHiddenUrls.has(url);
    }).length;
    groupCb.checked = hiddenCount === cards.length;
    groupCb.indeterminate = hiddenCount > 0 && hiddenCount < cards.length;
}

function _syncGroupCheckboxForCard(card) {
    const phaseSection = card.closest('.phase-section');
    if (phaseSection) {
        const groupCb = phaseSection.querySelector('.pdf-hide-group-checkbox');
        _syncGroupCheckbox(groupCb, _cardsInElement(phaseSection));
    }
    const grid = card.closest('.subcontract-grid');
    if (grid) {
        let heading = card.previousElementSibling;
        while (heading && !heading.classList.contains('subcontract-heading')) {
            heading = heading.previousElementSibling;
        }
        if (heading) {
            const groupCb = heading.querySelector('.pdf-hide-group-checkbox');
            _syncGroupCheckbox(groupCb, _cardsUnderSubcontractHeading(heading));
        }
    }
}

function _injectGroupHideCheckboxes() {
    document.querySelectorAll('.phase-section').forEach(section => {
        const header = section.querySelector('.phase-header');
        if (!header || header.querySelector('.pdf-hide-group-checkbox')) return;
        const cards = _cardsInElement(section);
        if (!cards.length) return;

        const groupCb = document.createElement('input');
        groupCb.type = 'checkbox';
        groupCb.className = 'pdf-hide-group-checkbox';
        groupCb.title = 'Select all photos in this section';
        groupCb.addEventListener('change', function(e) {
            e.stopPropagation();
            _setCardsHidden(cards, this.checked);
            _syncGroupCheckbox(groupCb, cards);
        });
        header.insertBefore(groupCb, header.firstChild);
        _syncGroupCheckbox(groupCb, cards);
    });

    document.querySelectorAll('.subcontract-heading').forEach(heading => {
        if (heading.querySelector('.pdf-hide-group-checkbox')) return;
        const cards = _cardsUnderSubcontractHeading(heading);
        if (!cards.length) return;

        const groupCb = document.createElement('input');
        groupCb.type = 'checkbox';
        groupCb.className = 'pdf-hide-group-checkbox';
        groupCb.title = 'Select all photos under this heading';
        groupCb.addEventListener('change', function(e) {
            e.stopPropagation();
            _setCardsHidden(cards, this.checked);
            _syncGroupCheckbox(groupCb, cards);
        });
        heading.insertBefore(groupCb, heading.firstChild);
        _syncGroupCheckbox(groupCb, cards);
    });
}

function _removeGroupHideCheckboxes() {
    document.querySelectorAll('.pdf-hide-group-checkbox').forEach(cb => cb.remove());
}

function togglePhotoSelectMode() {
    if (!_photoSelectMode) {
        startPhotoSelectMode();
    } else {
        endPhotoSelectMode(true);
    }
}
 
function startPhotoSelectMode() {
    _photoSelectMode = true;
    _tempHiddenUrls  = new Set(_hiddenPhotoUrls);
    document.getElementById('pdfDashboardOverlay').classList.remove('active');
 
    document.querySelectorAll('.photo-card').forEach(card => {
        const img = card.querySelector('img');
        if (!img) return;
 
        let cb = card.querySelector('.pdf-hide-checkbox');
        if (!cb) {
            cb = document.createElement('input');
            cb.type = 'checkbox';
            cb.className = 'pdf-hide-checkbox';
            cb.addEventListener('change', function(e) {
                e.stopPropagation();
                const url = photoCardUrl(card);
                if (!url) return;
                if (this.checked) {
                    _tempHiddenUrls.add(url);
                    card.classList.add('pdf-hidden-selected');
                } else {
                    _tempHiddenUrls.delete(url);
                    card.classList.remove('pdf-hidden-selected');
                }
                _syncGroupCheckboxForCard(card);
                refreshSelectModeCount();
            });
            card.appendChild(cb);
        }
 
        const url = photoCardUrl(card);
        if (!url) return;
        cb.checked = _hiddenPhotoUrls.has(url);
        card.classList.toggle('pdf-hidden-selected', cb.checked);
 
        card._pdfClickHandler = function(e) {
            if (e.target === cb) return;
            cb.checked = !cb.checked;
            cb.dispatchEvent(new Event('change'));
        };
        card.addEventListener('click', card._pdfClickHandler);
    });

    _injectGroupHideCheckboxes();

    document.body.classList.add('pdf-select-mode');
    document.getElementById('pdfHidePhotosBtn').textContent = '💾 Save Selections';
    document.getElementById('pdfHidePhotosBtn').classList.add('selecting');
    showSelectModeBanner();
    refreshSelectModeCount();
}
 
function endPhotoSelectMode(save) {
    _photoSelectMode = false;
    if (save) _hiddenPhotoUrls = new Set(_tempHiddenUrls);
 
    document.querySelectorAll('.photo-card').forEach(card => {
        card.classList.remove('pdf-hidden-selected');
        if (card._pdfClickHandler) {
            card.removeEventListener('click', card._pdfClickHandler);
            delete card._pdfClickHandler;
        }
    });

    _removeGroupHideCheckboxes();

    document.body.classList.remove('pdf-select-mode');
    document.getElementById('pdfHidePhotosBtn').textContent = '🙈 Select Photos to Hide';
    document.getElementById('pdfHidePhotosBtn').classList.remove('selecting');
    removeSelectModeBanner();
    refreshHideCount();
    document.getElementById('pdfDashboardOverlay').classList.add('active');
}
 
// ── Floating banner ──────────────────────────────────────────
let _banner = null;
 
function showSelectModeBanner() {
    if (_banner) return;
    _banner = document.createElement('div');
    _banner.style.cssText = `
        position:fixed; bottom:24px; left:50%; transform:translateX(-50%);
        background:#1a2535; color:white; padding:13px 28px; border-radius:40px;
        font-size:13.5px; font-weight:600; z-index:10001;
        box-shadow:0 8px 32px rgba(0,0,0,0.35);
        display:flex; align-items:center; gap:16px; white-space:nowrap;
    `;
    _banner.innerHTML = `
        <span id="bannerCount">Click photos to hide them from the PDF</span>
        <button onclick="endPhotoSelectMode(true)" style="background:#2e86de;color:white;border:none;
            padding:7px 16px;border-radius:20px;font-size:12px;font-weight:700;cursor:pointer;">
            💾 Save
        </button>
        <button onclick="endPhotoSelectMode(false)" style="background:rgba(255,255,255,0.12);
            color:white;border:none;padding:7px 14px;border-radius:20px;font-size:12px;cursor:pointer;">
            Cancel
        </button>
    `;
    document.body.appendChild(_banner);
}
 
function removeSelectModeBanner() {
    if (_banner) { _banner.remove(); _banner = null; }
}
 
function refreshSelectModeCount() {
    const n  = _tempHiddenUrls.size;
    const el = document.getElementById('bannerCount');
    if (el) el.textContent = n === 0
        ? 'Click photos to hide them from the PDF'
        : `${n} photo${n !== 1 ? 's' : ''} selected to hide`;
}
 
function refreshHideCount() {
    const el = document.getElementById('photoHideCount');
    if (!el) return;
    const n = _hiddenPhotoUrls.size;
    if (n === 0) {
        el.textContent = '';
        el.className = 'photo-hide-count';
    } else {
        el.textContent = `${n} photo${n !== 1 ? 's' : ''} will be hidden`;
        el.className = 'photo-hide-count has-hidden';
    }
    syncCoverPhotoCount();
}

function countVisiblePhotos() {
    let n = 0;
    document.querySelectorAll('.photo-card').forEach(card => {
        const url = photoCardUrl(card);
        if (url && !_hiddenPhotoUrls.has(url)) n++;
    });
    return n;
}

function syncCoverPhotoCount() {
    const field = _coverFields.find(f => f.key === 'total_photos');
    if (!field) return;
    field.value = `Total Photos: ${countVisiblePhotos()}`;
    const idx = _coverFields.indexOf(field);
    const row = document.querySelector(`.cover-field-row[data-idx="${idx}"]`);
    if (row) {
        const inp = row.querySelector('.cover-field-input');
        if (inp) inp.value = field.value;
    }
}
 
// ── PDF generation ────────────────────────────────────────────
function startPdfGeneration() {
    const params      = new URLSearchParams(window.location.search);
    const generateBtn = document.getElementById('pdfGenerateBtn');
    const progressSec = document.getElementById('pdfProgressSection');
    const fill        = document.getElementById('pdfProgressFill');
    const statusText  = document.getElementById('pdfProgressText');
    const statusPct   = document.getElementById('pdfProgressPct');
    const openLink    = document.getElementById('pdfOpenLink');
 
    const photoEdits = (window._editCount > 0)
        ? collectPhotoEdits() : null;
    const headingEdits = (window._editCount > 0)
        ? collectHeadingEdits() : null;
 
    // Flush any unsaved cover-field input values
    document.querySelectorAll('.cover-field-input').forEach((inp, i) => {
        if (_coverFields[i]) _coverFields[i].value = inp.value;
    });
 
    generateBtn.disabled    = true;
    generateBtn.textContent = '⏳ Generating…';
    progressSec.classList.add('visible');
    fill.style.width        = '0%';
    fill.style.background   = 'linear-gradient(90deg, #2e86de, #10ac84)';
    statusText.textContent  = 'Starting…';
    statusPct.textContent   = '';
    openLink.classList.remove('visible');
 
    const hasMeasureTabs = Object.keys(_measureInclusion).length > 0;
    const measuresIncluded = hasMeasureTabs
        ? Object.keys(_measureInclusion).filter(id => _measureInclusion[id])
        : null;
    const measureOptions = {};
    Object.keys(_measureShowTags).forEach(id => {
        const catalogEntries = (window._automaticHeadingCatalog || {})[id] || [];
        measureOptions[id] = {
            show_tags: _measureShowTags[id],
            heading_size: _measureHeadingSize[id] || 'normal',
            heading_visibility: _measureHeadingVisibility[id] || {},
            heading_labels: _pruneHeadingLabels(id, catalogEntries),
        };
    });

    const analyticsBlock = (window.AutoRecReportAnalytics && window.AutoRecReportAnalytics.getAnalyticsPayload)
        ? window.AutoRecReportAnalytics.getAnalyticsPayload()
        : null;
    if (analyticsBlock) {
        analyticsBlock.edits = analyticsBlock.edits || {};
        analyticsBlock.edits.heading_label_edits_count = countHeadingLabelEdits();
    }

    fetch('/start_pdf_job', {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            project_id:         params.get('project_id'),
            package_id:         params.get('package_id'),
            project_name:       getOriginalProjectName(params),
            pdf_project_name:   getEffectiveProjectName(params),
            project_address:    params.get('project_address'),
            parent_run_id:      params.get('run_id'),
            dataset_key:        params.get('dataset_key') || params.get('dataset') || 'plumbing',
            multi_bath:         params.get('multi_bath'),
            label_format:       params.get('label_format'),
            bath_names:         params.get('bath_names'),
            special_rooms:      params.get('special_rooms'),
            photo_edits:        photoEdits,
            heading_edits:      headingEdits,
            pdf_layout:             _pdfLayout,
            hide_empty_fields:      _hideEmptyFields,
            metadata_position:      _metadataPosition,
            linear_photos_per_page: _linearPhotosPerPage,
            hidden_photos:          Array.from(_hiddenPhotoUrls),
            photo_transforms:   (typeof collectPhotoTransforms === 'function') ? collectPhotoTransforms() : {},
            photo_tag_edits:    (typeof collectPhotoTagEdits === 'function') ? collectPhotoTagEdits() : {},
            cover_fields:       _coverFields,
            measures_included:  measuresIncluded,
            measure_inclusions: _measureInclusion,
            measure_options:    measureOptions,
            analytics:          analyticsBlock,
        }),
    })
    .then(r => r.json())
    .then(({ job_id }) => {
        const interval = setInterval(() => {
            fetch(`/job_status/${job_id}`)
                .then(r => r.json())
                .then(data => {
                    const done  = data.progress_done  || 0;
                    const total = data.progress_total || 0;
 
                    if (total > 0) {
                        const pct = Math.min(Math.round((done / total) * 100), 99);
                        fill.style.width       = pct + '%';
                        statusText.textContent = `Rendering photo ${done} of ${total}…`;
                        statusPct.textContent  = pct + '%';
                    } else {
                        const current = parseFloat(fill.style.width) || 0;
                        if (current < 28) fill.style.width = (current + 1.5) + '%';
                        statusText.textContent = 'Fetching & tagging photos…';
                    }
 
                    if (data.status === 'complete') {
                        clearInterval(interval);
                        fill.style.width        = '100%';
                        statusText.textContent  = '✅ PDF ready!';
                        statusPct.textContent   = '100%';
                        generateBtn.textContent = '⬇ Generate PDF';
                        generateBtn.disabled    = false;
                        openLink.href           = `/reports/${data.pdf_filename}`;
                        openLink.classList.add('visible');
                    }
 
                    if (data.status === 'error') {
                        clearInterval(interval);
                        fill.style.background   = '#e74c3c';
                        fill.style.width        = '100%';
                        statusText.textContent  = '❌ Error generating PDF';
                        statusPct.textContent   = '';
                        generateBtn.textContent = '⬇ Generate PDF';
                        generateBtn.disabled    = false;
                    }
                });
        }, 2000);
    });
}

function collectPhotoEdits() {
    const edits = {};
    document.querySelectorAll('.photo-grid[data-zone]').forEach(grid => {
        const zoneId = grid.dataset.zone;
        if (grid.classList.contains('subcontract-grid')) {
            edits[zoneId] = [...grid.children].map(el => {
                if (el.classList.contains('photo-card')) {
                    return photoCardUrl(el);
                }
                if (el.classList.contains('subcontract-heading')) {
                    return 'heading:' + el.dataset.headingId;
                }
                return null;
            }).filter(Boolean);
        } else {
            const urls = [...grid.querySelectorAll('.photo-card')].map(card => photoCardUrl(card)).filter(Boolean);
            edits[zoneId] = urls;
        }
    });
    return edits;
}

function collectHeadingEdits() {
    const edits = {};
    document.querySelectorAll('.subcontract-heading').forEach(el => {
        const textEl = el.querySelector('.heading-text');
        edits[el.dataset.headingId] = {
            text: textEl ? textEl.textContent : el.textContent.replace(/×/g, '').trim(),
            weight: el.dataset.weight || 'medium',
        };
    });
    return edits;
}