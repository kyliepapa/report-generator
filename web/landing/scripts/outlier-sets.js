/**
 * Dynamic outlier-set rows for Outliers measures.
 * Patterned after project-pairs.js (not location-levels.js).
 */

function _getOutlierProjectPairs() {
    const multi = typeof window.isMultiProject === 'function' && window.isMultiProject();
    if (multi && typeof window.getCompleteProjectPairs === 'function') {
        return window.getCompleteProjectPairs();
    }
    const projectId = document.getElementById('projectId')?.value.trim();
    const projectName = document.getElementById('projectName')?.value.trim();
    if (projectId && projectName) {
        return [{ id: projectId, nickname: projectName }];
    }
    if (projectId) {
        return [{ id: projectId, nickname: projectId }];
    }
    return [];
}

function _populateProjectSelect(select) {
    const pairs = _getOutlierProjectPairs();
    const prev = select.value;
    select.innerHTML = '';
    if (pairs.length === 0) {
        const opt = document.createElement('option');
        opt.value = '';
        opt.textContent = 'Add project details first';
        select.appendChild(opt);
        return;
    }
    pairs.forEach((pair, idx) => {
        const opt = document.createElement('option');
        opt.value = pair.id;
        opt.textContent = pair.nickname;
        if (prev === pair.id || (!prev && idx === 0)) {
            opt.selected = true;
        }
        select.appendChild(opt);
    });
}

function _createOutlierSetRow(measureId) {
    const row = document.createElement('div');
    row.className = 'outlier-set-block';
    row.innerHTML = `
        <input class="field-input outlier-section-name" placeholder="e.g. Site Issues" autocomplete="off" />
        <select class="field-input outlier-project-select" aria-label="Project"></select>
        <div class="tag-builder outlier-tag-builder">
            <input class="tag-input outlier-tag-input" placeholder="e.g. OUTLIER, REJECT — press Enter per tag" autocomplete="off" spellcheck="false" />
        </div>
        <label class="outlier-match-switch" title="OR: match any tag. AND: match all tags.">
            <input type="checkbox" class="outlier-match-input" />
            <span class="outlier-match-track" aria-hidden="true">
                <span class="outlier-match-opt outlier-match-or">OR</span>
                <span class="outlier-match-opt outlier-match-and">AND</span>
                <span class="outlier-match-thumb"></span>
            </span>
        </label>`;

    const select = row.querySelector('.outlier-project-select');
    _populateProjectSelect(select);

    const builder = row.querySelector('.tag-builder');
    if (builder && typeof window.initTagBuilder === 'function') {
        window.initTagBuilder(builder);
    }

    return row;
}

function _rowsContainer(measureId) {
    return document.getElementById(`outlierSetRows-${measureId}`);
}

function _addBtn(measureId) {
    return document.getElementById(`addOutlierSetBtn-${measureId}`);
}

function initOutlierSets(measureId) {
    const container = _rowsContainer(measureId);
    const addBtn = _addBtn(measureId);
    if (!container) return;

    if (container.children.length === 0) {
        container.appendChild(_createOutlierSetRow(measureId));
    } else {
        container.querySelectorAll('.outlier-project-select').forEach(_populateProjectSelect);
    }

    if (addBtn && !addBtn._outlierSetsWired) {
        addBtn._outlierSetsWired = true;
        addBtn.addEventListener('click', () => addOutlierSet(measureId));
    }
}

function addOutlierSet(measureId) {
    const container = _rowsContainer(measureId);
    if (!container) return;
    container.appendChild(_createOutlierSetRow(measureId));
}

function refreshOutlierProjectSelects(measureId) {
    const container = _rowsContainer(measureId);
    if (!container) return;
    container.querySelectorAll('.outlier-project-select').forEach(_populateProjectSelect);
}

function refreshAllOutlierProjectSelects() {
    document.querySelectorAll('[id^="outlierSetRows-"]').forEach(el => {
        refreshOutlierProjectSelects(el.id.replace('outlierSetRows-', ''));
    });
}

function getOutlierSets(measureId) {
    const container = _rowsContainer(measureId);
    if (!container) return [];

    return Array.from(container.querySelectorAll('.outlier-set-block')).map(row => {
        const builder = row.querySelector('.tag-builder');
        const tags = builder && builder._getTags ? builder._getTags() : [];
        const sectionName = row.querySelector('.outlier-section-name')?.value.trim() || '';
        const projectId = row.querySelector('.outlier-project-select')?.value.trim() || '';
        const matchInput = row.querySelector('.outlier-match-input');
        const tagMatchMode = matchInput && matchInput.checked ? 'all' : 'any';
        return { section_name: sectionName, project_id: projectId, tags, tag_match_mode: tagMatchMode };
    });
}

window.initOutlierSets = initOutlierSets;
window.addOutlierSet = addOutlierSet;
window.getOutlierSets = getOutlierSets;
window.refreshOutlierProjectSelects = refreshOutlierProjectSelects;
window.refreshAllOutlierProjectSelects = refreshAllOutlierProjectSelects;
