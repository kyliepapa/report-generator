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

function getTagsFor(id, panelEl) {
    const root = panelEl || document;
    const el = root.querySelector ? root.querySelector(`#${id}`) : document.getElementById(id);
    return el && el._getTags ? el._getTags() : [];
}

function activeToggleValue(group, panelEl) {
    const root = panelEl || document;
    const btn = root.querySelector
        ? root.querySelector(`button.toggle.active[data-group="${group}"]`)
        : document.querySelector(`button.toggle.active[data-group="${group}"]`);
    return btn ? btn.dataset.value : null;
}

function buildAquamizerPayload(id, panelEl) {
    const baths = Array.from(panelEl.querySelectorAll(`#aq-${id} .bath`))
        .map(b => b.value.trim())
        .filter(b => b !== '');
    const specialRooms = getTagsFor(`specialRooms-${id}Builder`, panelEl);

    return {
        multi_bath: activeToggleValue(`multi-${id}`, panelEl),
        label_format: activeToggleValue(`format-${id}`, panelEl),
        bath_names: baths.join(','),
        special_rooms: specialRooms.join(','),
    };
}

function buildLightingPayload(id, panelEl) {
    const serialTags = window.getSerialTags
        ? window.getSerialTags('lighting', id, panelEl)
        : getTagsFor(`lightingSerialTags-${id}Builder`, panelEl);
    const locationLevels = window.getLocationLevels
        ? window.getLocationLevels(id).map(level => ({
            tags: level.tags.join(','),
            numeric: level.numeric,
        }))
        : [];

    const phases = window.getLightingPhases
        ? window.getLightingPhases(id, panelEl)
        : getTagsFor(`phases-${id}Builder`, panelEl);

    return {
        installers: getTagsFor(`installers-${id}Builder`, panelEl).join(','),
        location_levels: locationLevels,
        fixture_types: getTagsFor(`fixtureTypes-${id}Builder`, panelEl).join(','),
        phases: phases.join(','),
        serial_tag: serialTags.join(','),
        loc_bigger_num: activeToggleValue(`locBiggerNum-${id}`, panelEl),
    };
}

function buildHeatPumpPayload(id, panelEl) {
    const serialTags = window.getSerialTags
        ? window.getSerialTags('heat_pump', id, panelEl)
        : getTagsFor(`heatPumpSerialTags-${id}Builder`, panelEl);
    const intuitiveSort = activeToggleValue(`intuitiveFixtureSort-${id}`, panelEl) === 'Yes';
    const multiUnit = activeToggleValue(`hpMultiUnit-${id}`, panelEl) === 'Multiple';
    const loneRaw = activeToggleValue(`hpLoneNumber-${id}`, panelEl);
    const loneNumberMode = multiUnit && loneRaw ? loneRaw.toLowerCase() : 'none';
    const locationTags = getTagsFor(`hpLocations-${id}Builder`, panelEl);
    return {
        multi_unit: multiUnit,
        lone_number_mode: loneNumberMode,
        locations: multiUnit ? locationTags : [],
        intuitive_fixture_sort: intuitiveSort,
        fixtures: intuitiveSort ? '' : getTagsFor(`fixtures-${id}Builder`, panelEl).join(','),
        serial_tag: serialTags.join(','),
        allow_competing_fixture_tags: intuitiveSort
            ? false
            : activeToggleValue(`allowCompetingFixtures-${id}`, panelEl) === 'Yes',
        auto_assign_lone_serial_to_before: activeToggleValue(`autoAssignLoneSerial-${id}`, panelEl) === 'Yes',
    };
}

function buildSubcontractedPayload(id, panelEl) {
    const markEl = panelEl.querySelector(`#sc-${id} .subcontract-mark`);
    const keySource = window.getSubcontractedKeySource
        ? window.getSubcontractedKeySource(id, panelEl)
        : (activeToggleValue(`subconKey-${id}`, panelEl) || 'Tags').toLowerCase();
    const hash = window.getSubcontractedHash
        ? window.getSubcontractedHash(id, panelEl)
        : (panelEl.querySelector(`#sc-${id} .subcontract-hash`)?.value.trim() || '');
    return {
        hash,
        measure_mark: markEl ? markEl.value.trim() : '',
        key_source: keySource,
    };
}

function buildManualArrangePayload(id, panelEl) {
    return {
        pre_sort_buckets: getTagsFor(`preSortBuckets-${id}Builder`, panelEl),
        allow_conflicting_tags: activeToggleValue(`allowConflictingTags-${id}`, panelEl) !== 'No',
    };
}

function buildOutliersPayload(id, panelEl) {
    const sets = window.getOutlierSets ? window.getOutlierSets(id) : [];
    return { outlier_sets: sets };
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
        if (tab.type === 'outliers') {
            const sets = window.getOutlierSets ? window.getOutlierSets(tab.id) : [];
            sets.forEach(s => {
                if (s.project_id) claimed.add(s.project_id);
            });
            return;
        }
        const checked = window.getCheckedProjectIds
            ? window.getCheckedProjectIds(tab.id)
            : [];
        if (checked.length === 0) {
            const label = tab.type === 'outliers'
                ? 'Outliers'
                : (tab.panelEl.querySelector('.measure-name')?.value.trim()
                    || tab.type || tab.id);
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
    const panelEl = tab.panelEl;
    const measureName = panelEl.querySelector('.measure-name').value.trim();
    let typePayload = {};
    if (tab.type === 'aquamizer') {
        typePayload = buildAquamizerPayload(tab.id, panelEl);
    } else if (tab.type === 'lighting') {
        typePayload = buildLightingPayload(tab.id, panelEl);
    } else if (tab.type === 'heat_pump') {
        typePayload = buildHeatPumpPayload(tab.id, panelEl);
    } else if (tab.type === 'subcontracted') {
        typePayload = buildSubcontractedPayload(tab.id, panelEl);
    } else if (tab.type === 'manual_arrange') {
        typePayload = buildManualArrangePayload(tab.id, panelEl);
    } else if (tab.type === 'outliers') {
        typePayload = buildOutliersPayload(tab.id, panelEl);
    }

    const payload = {
        id: tab.id,
        type: tab.type,
        name: tab.type === 'outliers' ? 'Outliers' : measureName,
        ...typePayload,
    };

    if (tab.type !== 'subcontracted' && tab.type !== 'manual_arrange' && tab.type !== 'outliers') {
        payload.measure_keywords = window.getMeasureKeywords
            ? window.getMeasureKeywords(tab.id, panelEl)
            : getTagsFor(`measureKeywords-${tab.id}Builder`, panelEl);
    }

    if (window.isMultiProject && window.isMultiProject() && tab.type !== 'outliers') {
        payload.applicable_projects = window.getCheckedProjectIds
            ? window.getCheckedProjectIds(tab.id)
            : [];
    }

    return payload;
}

function validateManualArrangeProjects(configured, errors) {
    const maProjects = new Map();
    const otherProjects = new Map();

    configured.forEach(tab => {
        const checked = window.getCheckedProjectIds
            ? window.getCheckedProjectIds(tab.id)
            : [];
        checked.forEach(pid => {
            if (tab.type === 'manual_arrange') {
                if (otherProjects.has(pid)) {
                    errors.push(
                        `Project cannot be assigned to both Manual Arrange and another measure type.`
                    );
                }
                maProjects.set(pid, tab.id);
            } else {
                if (maProjects.has(pid)) {
                    errors.push(
                        `Project cannot be assigned to both Manual Arrange and another measure type.`
                    );
                }
                otherProjects.set(pid, tab.id);
            }
        });
    });

    if (!window.isMultiProject || !window.isMultiProject()) {
        const maTabs = configured.filter(t => t.type === 'manual_arrange');
        if (maTabs.length && configured.length > 1) {
            errors.push(
                'Manual Arrange cannot be combined with other measures in a single-project run.'
            );
        }
    }
}

function validateSubcontractedCrossTab(configured, errors) {
    const marks = {};
    const hashOnly = {};

    configured.filter(t => t.type === 'subcontracted').forEach(tab => {
        const { hash, measure_mark: mark } = buildSubcontractedPayload(tab.id, tab.panelEl);
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

function validateMeasure(type, id, panelEl, errors) {
    if (type === 'aquamizer') {
        if (!activeToggleValue(`multi-${id}`, panelEl)) errors.push('Select whether units have multiple bathrooms.');
        if (!activeToggleValue(`format-${id}`, panelEl)) errors.push('Select a unit label format.');
    } else if (type === 'lighting') {
        const levels = window.getLocationLevels ? window.getLocationLevels(id) : [];
        if (levels.length === 0) {
            errors.push('Add at least one Lighting location level.');
        }
        levels.forEach((level, idx) => {
            const n = idx + 1;
            if (!level.numeric) {
                errors.push(`Select whether Location Level ${n} uses numbered locations.`);
            }
            if (level.numeric !== 'Yes' && level.tags.length === 0) {
                errors.push(`Add at least one tag for Location Level ${n}, or enable numbered locations.`);
            }
        });
        const numericCount = levels.filter(l => l.numeric === 'Yes').length;
        if (numericCount >= 2 && !activeToggleValue(`locBiggerNum-${id}`, panelEl)) {
            errors.push('Select whether higher location levels have larger numbers.');
        }
        if (getTagsFor(`fixtureTypes-${id}Builder`, panelEl).length === 0) errors.push('Add at least one Lighting fixture type.');
        const phases = window.getLightingPhases
            ? window.getLightingPhases(id, panelEl)
            : getTagsFor(`phases-${id}Builder`, panelEl);
        if (phases.length === 0) errors.push('Add at least one Lighting phase.');
    } else if (type === 'heat_pump') {
        if (!activeToggleValue(`hpMultiUnit-${id}`, panelEl)) {
            errors.push('Select whether the measure includes a single or multiple units/locations.');
        }
        if (activeToggleValue(`hpMultiUnit-${id}`, panelEl) === 'Multiple') {
            const loneMode = activeToggleValue(`hpLoneNumber-${id}`, panelEl);
            if (!loneMode) {
                errors.push('Select how many location/unit tags are lone numbers (None, Some, or All).');
            } else if ((loneMode === 'None' || loneMode === 'Some')
                && getTagsFor(`hpLocations-${id}Builder`, panelEl).length === 0) {
                errors.push('Add at least one Locations/Units tag, or select All for lone-number tags.');
            }
        }
    } else if (type === 'water_meter') {
        errors.push('Water Meter is not supported yet — pick a different measure type.');
    } else if (type === 'subcontracted') {
        const hash = window.getSubcontractedHash
            ? window.getSubcontractedHash(id, panelEl)
            : panelEl.querySelector(`#sc-${id} .subcontract-hash`).value.trim();
        const mark = panelEl.querySelector(`#sc-${id} .subcontract-mark`).value.trim();
        const keySource = window.getSubcontractedKeySource
            ? window.getSubcontractedKeySource(id, panelEl)
            : (activeToggleValue(`subconKey-${id}`, panelEl) || 'Tags').toLowerCase();
        if (!window.getSubcontractedKeySource && !activeToggleValue(`subconKey-${id}`, panelEl)) {
            errors.push('Select whether subcon keys are in photo tags or descriptions.');
        }
        if (hash.length !== 1) errors.push('Subcontracted measure requires a single-character hash.');
        if (mark && mark.length !== 1) errors.push('Subcontracted measure mark must be a single character.');
        if (keySource !== 'tags' && keySource !== 'description') {
            errors.push('Photo identification must be Tags or Description.');
        }
    } else if (type === 'manual_arrange') {
        // Pre-sort buckets optional; no extra required fields.
    } else if (type === 'outliers') {
        const sets = window.getOutlierSets ? window.getOutlierSets(id) : [];
        if (sets.length === 0) {
            errors.push('Add at least one Outliers set.');
        }
        const sectionNames = new Set();
        sets.forEach((set, idx) => {
            const n = idx + 1;
            if (!set.section_name) {
                errors.push(`Outliers set ${n}: enter a section name.`);
            } else if (sectionNames.has(set.section_name.toLowerCase())) {
                errors.push(`Outliers set ${n}: section name "${set.section_name}" is duplicated.`);
            } else {
                sectionNames.add(set.section_name.toLowerCase());
            }
            if (!set.project_id) {
                errors.push(`Outliers set ${n}: select a project.`);
            }
            if (!set.tags || set.tags.length === 0) {
                errors.push(`Outliers set ${n}: add at least one identifier tag.`);
            }
        });
    }
}

document.getElementById('generateBtn').addEventListener('click', () => {
    const errorDiv = document.getElementById('error');
    errorDiv.textContent = '';
    const errors = [];

    if (window.AutoRecAnalytics && !window.AutoRecAnalytics.isReady()) {
        errors.push('Please enter your name to continue.');
    }

    const projectId = document.getElementById('projectId').value.trim();
    const projectName = document.getElementById('projectName').value.trim();
    const projectAddress = document.getElementById('projectAddress').value.trim();
    const multi = window.isMultiProject && window.isMultiProject();

    if (!multi && !projectId) errors.push('Please enter a Project ID.');

    const measureTabs = window.getMeasureTabs();
    const configured = measureTabs.filter(t => t.type);
    if (configured.length === 0) errors.push('Select a Measure Type for at least one measure tab.');

    configured.forEach(t => validateMeasure(t.type, t.id, t.panelEl, errors));
    validateSubcontractedCrossTab(configured, errors);
    validateManualArrangeProjects(configured, errors);
    validateMultiProject(configured, errors);

    if (errors.length) {
        if (window.AutoRecAnalytics && window.AutoRecAnalytics.recordValidationError) {
            window.AutoRecAnalytics.recordValidationError();
        }
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
        analytics: window.AutoRecAnalytics ? window.AutoRecAnalytics.buildPayload() : {},
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
        .then(({ job_id, package_id, run_id }) => {
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
                    if (projectAddress) {
                        urlParams.set('project_address', projectAddress);
                    }
                    if (run_id) urlParams.set('run_id', run_id);
                    const ctx = window.AutoRecAnalytics ? window.AutoRecAnalytics.getContext() : {};
                    if (ctx.user_id) urlParams.set('user_id', ctx.user_id);
                    if (ctx.display_name) urlParams.set('display_name', ctx.display_name);
                    if (ctx.session_id) urlParams.set('session_id', ctx.session_id);
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