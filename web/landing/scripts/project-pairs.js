/**
 * Multi-project package UI: toggle, dynamic project ID/nickname pairs.
 */

const MULTI_PROJECT_ONLY = true;

const _pairChangeCallbacks = [];

function onProjectPairsChange(fn) {
    _pairChangeCallbacks.push(fn);
}

function _notifyChange() {
    _pairChangeCallbacks.forEach(fn => {
        try { fn(); } catch (e) { console.error('project-pairs callback error', e); }
    });
}

function isMultiProject() {
    if (MULTI_PROJECT_ONLY) return true;
    const btn = document.querySelector('button.toggle.active[data-group="multiProject"]');
    return btn && btn.dataset.value === 'Yes';
}

function _createPairRow() {
    const row = document.createElement('div');
    row.className = 'project-pair-row';
    row.innerHTML = `
        <input class="field-input project-id-input" placeholder="e.g. 99615753" autocomplete="off" />
        <input class="field-input project-nick-input" placeholder="e.g. Building A" autocomplete="off" />
    `;
    row.querySelectorAll('input').forEach(inp => {
        inp.addEventListener('input', _notifyChange);
        inp.addEventListener('blur', _notifyChange);
    });
    return row;
}

function getAllProjectPairs() {
    const rows = document.querySelectorAll('#projectPairRows .project-pair-row');
    return Array.from(rows).map(row => ({
        id: row.querySelector('.project-id-input').value.trim(),
        nickname: row.querySelector('.project-nick-input').value.trim(),
    }));
}

function getCompleteProjectPairs() {
    return getAllProjectPairs().filter(p => p.id && p.nickname);
}

function _updateMultiProjectUI() {
    const multi = isMultiProject();
    const wrap = document.getElementById('projectPairsWrap');
    const idGroup = document.getElementById('projectIdGroup');
    const nameLabel = document.getElementById('projectNameLabel');

    if (wrap) wrap.style.display = multi ? 'block' : 'none';
    if (idGroup) idGroup.style.display = multi ? 'none' : 'block';
    if (nameLabel) {
        nameLabel.innerHTML = multi
            ? 'Package Name'
            : 'Project Name <span class="optional">(optional)</span>';
    }

    const nameInput = document.getElementById('projectName');
    if (nameInput) {
        nameInput.placeholder = multi ? 'e.g. Belovida Phase 2' : 'e.g. Belovida';
    }

    _notifyChange();
}

function initProjectPairs() {
    const rowsContainer = document.getElementById('projectPairRows');
    const addBtn = document.getElementById('addProjectBtn');

    if (rowsContainer && rowsContainer.children.length === 0) {
        rowsContainer.appendChild(_createPairRow());
    }

    if (addBtn) {
        addBtn.addEventListener('click', () => {
            rowsContainer.appendChild(_createPairRow());
            _notifyChange();
        });
    }

    document.querySelectorAll('button.toggle[data-group="multiProject"]').forEach(btn => {
        btn.addEventListener('click', () => {
            setTimeout(_updateMultiProjectUI, 0);
        });
    });

    _updateMultiProjectUI();
}

document.addEventListener('DOMContentLoaded', initProjectPairs);

window.isMultiProject = isMultiProject;
window.getAllProjectPairs = getAllProjectPairs;
window.getCompleteProjectPairs = getCompleteProjectPairs;
window.onProjectPairsChange = onProjectPairsChange;
