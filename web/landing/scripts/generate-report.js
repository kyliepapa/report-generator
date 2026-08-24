/**
 * Generate Report button: validation, job kickoff, and completion handling.
 *
 * Every configured measure tab is now submitted together as a
 * `measures` array (see buildMeasurePayload below) — the backend
 * (report_routes.py) classifies photos across all of them and sorts
 * each with its own type-specific rules. HTML report rendering still
 * covers only the first measure for now; the backend logs a note
 * about that rather than silently dropping the rest.
 */
function resetGenerateBtn() {
    const btn = document.getElementById('generateBtn');
    btn.disabled = false;
    btn.querySelector('.btn-label').textContent = 'Generate Report';
}

function getTagsFor(id) {
    const el = document.getElementById(id);
    return el && el._getTags ? el._getTags() : [];
}

function activeToggleValue(group) {
    const btn = document.querySelector(`button.toggle.active[data-group="${group}"]`);
    return btn ? btn.dataset.value : null;
}

function buildAquamizerPayload(id) {
    const baths = Array.from(document.querySelectorAll(`#aq-${id} .bath`))
        .map(b => b.value.trim())
        .filter(b => b !== '');
    const specialRooms = getTagsFor(`specialRooms-${id}Builder`);

    return {
        multi_bath: activeToggleValue(`multi-${id}`),
        label_format: activeToggleValue(`format-${id}`),
        bath_names: baths.join(','),
        special_rooms: specialRooms.join(','),
    };
}

function buildLightingPayload(id) {
    const serialTag = document.querySelector(`#lt-${id} .serial-tag`).value.trim();

    return {
        installers: getTagsFor(`installers-${id}Builder`).join(','),
        locations: getTagsFor(`locations-${id}Builder`).join(','),
        sublocations: getTagsFor(`sublocations-${id}Builder`).join(','),
        fixture_types: getTagsFor(`fixtureTypes-${id}Builder`).join(','),
        phases: getTagsFor(`phases-${id}Builder`).join(','),
        serial_tag: serialTag,
        loc_numeric: activeToggleValue(`locNumeric-${id}`),
        subloc_numeric: activeToggleValue(`sublocNumeric-${id}`),
        loc_bigger_num: activeToggleValue(`locBiggerNum-${id}`),
    };
}

function buildHeatPumpPayload(id) {
    const serialTag = document.querySelector(`#hp-${id} .serial-tag`).value.trim();
    return {
        fixtures: getTagsFor(`fixtures-${id}Builder`).join(','),
        serial_tag: serialTag,
        allow_competing_fixture_tags: activeToggleValue(`allowCompetingFixtures-${id}`) === 'Yes',
        auto_assign_lone_serial_to_before: activeToggleValue(`autoAssignLoneSerial-${id}`) === 'Yes',
    };
}

function buildSubcontractedPayload(id) {
    const hashEl = document.querySelector(`#sc-${id} .subcontract-hash`);
    const markEl = document.querySelector(`#sc-${id} .subcontract-mark`);
    const keySource = (activeToggleValue(`subconKey-${id}`) || 'Tags').toLowerCase();
    return {
        hash: hashEl ? hashEl.value.trim() : '',
        measure_mark: markEl ? markEl.value.trim() : '',
        key_source: keySource,
    };
}

function validateMultiProject(configured, errors) {
    if (!window.isMultiProject || !window.isMultiProject()) return;

    const packageName = document.getElementById('projectName').value.trim();
    if (!packageName) errors.push('Please enter a Package Name.');

    const complete = window.getCompleteProjectPairs ? window.getCompleteProjectPairs() : [];
    if (complete.length === 0) {
        errors.push('Add at least one complete project pair (ID and nickname).');
        return;
    }

    const ids = {};
    const nicks = {};
    complete.forEach(p => {
        if (ids[p.id]) {
            errors.push(`Duplicate project ID "${p.id}".`);
        } else {
            ids[p.id] = p.nickname;
        }
        if (nicks[p.nickname]) {
            errors.push(`Duplicate project nickname "${p.nickname}".`);
        } else {
            nicks[p.nickname] = p.id;
        }
    });

    const claimed = new Set();
    configured.forEach(tab => {
        const checked = window.getCheckedProjectIds
            ? window.getCheckedProjectIds(tab.id)
            : [];
        if (checked.length === 0) {
            const label = tab.panelEl.querySelector('.measure-name')?.value.trim()
                || tab.type || tab.id;
            errors.push(`Select at least one project for measure "${label}".`);
        }
        checked.forEach(pid => claimed.add(pid));
    });

    complete.forEach(p => {
        if (!claimed.has(p.id)) {
            errors.push(`Project "${p.nickname}" is not assigned to any measure.`);
        }
    });
}

function buildMeasurePayload(tab) {
    const measureName = tab.panelEl.querySelector('.measure-name').value.trim();
    let typePayload = {};
    if (tab.type === 'aquamizer') {
        typePayload = buildAquamizerPayload(tab.id);
    } else if (tab.type === 'lighting') {
        typePayload = buildLightingPayload(tab.id);
    } else if (tab.type === 'heat_pump') {
        typePayload = buildHeatPumpPayload(tab.id);
    } else if (tab.type === 'subcontracted') {
        typePayload = buildSubcontractedPayload(tab.id);
    }

    const payload = {
        id: tab.id,
        type: tab.type,
        name: measureName,
        ...typePayload,
    };

    if (tab.type !== 'subcontracted') {
        payload.measure_keywords = getTagsFor(`measureKeywords-${tab.id}Builder`);
    }

    if (window.isMultiProject && window.isMultiProject()) {
        payload.applicable_projects = window.getCheckedProjectIds
            ? window.getCheckedProjectIds(tab.id)
            : [];
    }

    return payload;
}

function validateSubcontractedCrossTab(configured, errors) {
    const marks = {};
    const hashOnly = {};

    configured.filter(t => t.type === 'subcontracted').forEach(tab => {
        const { hash, measure_mark: mark } = buildSubcontractedPayload(tab.id);
        if (mark) {
            const mk = mark.toUpperCase();
            if (marks[mk]) {
                errors.push(`Duplicate subcontracted measure mark "${mark}" across measure tabs.`);
            } else {
                marks[mk] = tab.id;
            }
        } else if (hash) {
            if (hashOnly[hash]) {
                errors.push(`Only one subcontracted measure without a measure mark is allowed per hash "${hash}".`);
            } else {
                hashOnly[hash] = tab.id;
            }
        }
    });
}

function validateMeasure(type, id, errors) {
    if (type === 'aquamizer') {
        if (!activeToggleValue(`multi-${id}`)) errors.push('Select whether units have multiple bathrooms.');
        if (!activeToggleValue(`format-${id}`)) errors.push('Select a unit label format.');
    } else if (type === 'lighting') {
        const locNumeric = activeToggleValue(`locNumeric-${id}`);
        const sublocNumeric = activeToggleValue(`sublocNumeric-${id}`);
        if (locNumeric !== 'Yes' && getTagsFor(`locations-${id}Builder`).length === 0) {
            errors.push('Add at least one Lighting location.');
        }
        if (getTagsFor(`fixtureTypes-${id}Builder`).length === 0) errors.push('Add at least one Lighting fixture type.');
        if (getTagsFor(`phases-${id}Builder`).length === 0) errors.push('Add at least one Lighting phase.');
        if (!document.querySelector(`#lt-${id} .serial-tag`).value.trim()) errors.push('Enter a serial tag for Lighting.');
        if (!locNumeric) errors.push('Select whether Lighting locations are numbered.');
        if (!sublocNumeric) errors.push('Select whether Lighting sublocations are numbered.');
        if (locNumeric === 'Yes' && sublocNumeric === 'Yes' && !activeToggleValue(`locBiggerNum-${id}`)) {
            errors.push('Select the Lighting location/sublocation sort answer.');
        }
    } else if (type === 'heat_pump') {
        if (!document.querySelector(`#hp-${id} .serial-tag`).value.trim()) errors.push('Enter a serial tag for Single-Unit Heat Pump.');
    } else if (type === 'water_meter') {
        errors.push('Water Meter is not supported yet — pick a different measure type.');
    } else if (type === 'subcontracted') {
        const hash = document.querySelector(`#sc-${id} .subcontract-hash`).value.trim();
        const mark = document.querySelector(`#sc-${id} .subcontract-mark`).value.trim();
        const keySource = (activeToggleValue(`subconKey-${id}`) || 'Tags').toLowerCase();
        if (!activeToggleValue(`subconKey-${id}`)) errors.push('Select whether subcon keys are in photo tags or descriptions.');
        if (hash.length !== 1) errors.push('Subcontracted measure requires a single-character hash.');
        if (mark && mark.length !== 1) errors.push('Subcontracted measure mark must be a single character.');
        if (keySource !== 'tags' && keySource !== 'description') {
            errors.push('Photo identification must be Tags or Description.');
        }
    }
}

document.getElementById('generateBtn').addEventListener('click', () => {
    const errorDiv = document.getElementById('error');
    errorDiv.textContent = '';
    const errors = [];

    const projectId = document.getElementById('projectId').value.trim();
    const projectName = document.getElementById('projectName').value.trim();
    const projectAddress = document.getElementById('projectAddress').value.trim();
    const multi = window.isMultiProject && window.isMultiProject();

    if (!multi && !projectId) errors.push('Please enter a Project ID.');

    const measureTabs = window.getMeasureTabs();
    const configured = measureTabs.filter(t => t.type);
    if (configured.length === 0) errors.push('Select a Measure Type for at least one measure tab.');

    configured.forEach(t => validateMeasure(t.type, t.id, errors));
    validateSubcontractedCrossTab(configured, errors);
    validateMultiProject(configured, errors);

    if (errors.length) {
        errorDiv.textContent = errors[0];
        return;
    }

    clearTerminal();
    setStatus('running', 'Running…');

    const generateBtn = document.getElementById('generateBtn');
    generateBtn.disabled = true;
    generateBtn.querySelector('.btn-label').textContent = 'Generating…';
    document.getElementById('reportActions').style.display = 'none';

    const payload = {
        project_address: projectAddress,
        measures: configured.map(buildMeasurePayload),
    };

    if (multi) {
        payload.is_multi_project = true;
        payload.package_name = projectName || 'Package';
        payload.projects = window.getAllProjectPairs ? window.getAllProjectPairs() : [];
    } else {
        payload.project_id = projectId;
        payload.project_name = projectName || projectId;
    }

    fetch('/start_job', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
    })
        .then(r => {
            if (r.status === 429) throw new Error('busy');
            if (!r.ok) throw new Error(`HTTP ${r.status}`);
            return r.json();
        })
        .then(({ job_id, package_id }) => {
            termLine('Job started, processing...');

            pollJob(
                job_id,
                () => {
                    setStatus('success', 'Done');
                    resetGenerateBtn();

                    const actions = document.getElementById('reportActions');
                    const openBtn = document.getElementById('openReportBtn');
                    const urlParams = new URLSearchParams();
                    if (multi && package_id) {
                        urlParams.set('package_id', package_id);
                        urlParams.set('project_name', projectName || 'Package');
                    } else {
                        urlParams.set('project_id', projectId);
                        urlParams.set('project_name', projectName || projectId);
                    }
                    openBtn.onclick = () => window.open(`/report?${urlParams}`, '_blank');
                    actions.style.display = 'flex';
                },
                () => {
                    setStatus('error', 'Error');
                    resetGenerateBtn();
                }
            );
        })
        .catch(err => {
            if (err.message === 'busy') {
                termLine('⏳ Another report is already running. Please wait and try again.');
            } else {
                termLine(`❌ Failed to start job: ${err}`);
            }
            setStatus('error', 'Error');
            resetGenerateBtn();
        });
});