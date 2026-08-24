// ============================================================
// DRAG-AND-DROP ENGINE
// ============================================================

// Global state
window._editMode   = false;
window._dragActive = false;
let _dragging      = null;   // the card element being dragged
let _sourceZone    = null;   // the photo-grid it came from
let _undoStack     = [];     // [{card, fromZone, fromIndex, toZone, toIndex}] or {type:'sortable', grid, order}
window._editCount  = 0;
let _sortableInstances = new Map();
let _sortableUndoSnapshot = null;

// ── Auto-scroll during drag ────────────────────────────────
let _scrollDir = 0; // -1 = up, 1 = down, 0 = none
const _scrollMargin = 80; // px from edge
const _maxScrollSpeed = 20;

function _updateScrollDirection(clientY) {
    const h = window.innerHeight;

    if (clientY < _scrollMargin) {
        // Closer to top = faster scroll
        const intensity = (_scrollMargin - clientY) / _scrollMargin;
        _scrollDir = -intensity;
    } else if (clientY > h - _scrollMargin) {
        // Closer to bottom = faster scroll
        const intensity = (clientY - (h - _scrollMargin)) / _scrollMargin;
        _scrollDir = intensity;
    } else {
        _scrollDir = 0;
    }
}

function _autoScrollLoop() {
    if (window._dragActive && _scrollDir !== 0) {
        window.scrollBy(0, _scrollDir * _maxScrollSpeed);
    }
    requestAnimationFrame(_autoScrollLoop);
}

// Start the loop once
_autoScrollLoop();

// ── Edit-mode toggle ────────────────────────────────────────
const editBtn  = document.getElementById('edit-mode-btn');
const undoBtn  = document.getElementById('undo-btn');
const resetBtn = document.getElementById('reset-btn');
const badge    = document.getElementById('edit-count-badge');

editBtn.addEventListener('click', toggleEditMode);

function toggleEditMode() {
    window._editMode = !window._editMode;
    document.body.classList.toggle('edit-mode', window._editMode);
    editBtn.classList.toggle('active', window._editMode);
    editBtn.textContent = window._editMode ? '✏️ Editing On' : '✏️ Edit Photos';
    document.getElementById('edit-mode-hint').textContent = window._editMode
        ? 'Drag photos between zones · Reorder subcontract photos/headings · Ctrl+Z to undo'
        : 'Enable to rearrange photos';
    if (window._editMode) {
        initSubcontractSortables();
    } else {
        destroySubcontractSortables();
    }
    refreshZones();
    syncCounters();
    updateInjectHeadingBtn();
}

// Keyboard shortcut: Ctrl/Cmd+Z → undo
document.addEventListener('keydown', function(e) {
    if ((e.ctrlKey || e.metaKey) && e.key === 'z' && window._editMode) {
        e.preventDefault();
        undoLast();
    }
});

// ── Undo ────────────────────────────────────────────────────
undoBtn.addEventListener('click', undoLast);

function undoLast() {
    if (!_undoStack.length) return;
    const op = _undoStack.pop();

    if (op.type === 'sortable') {
        op.order.forEach(el => op.grid.appendChild(el));
        window._editCount = Math.max(0, window._editCount - 1);
        refreshBadge();
        syncPhotoNumbers();
        return;
    }

    // Re-insert the card at its original position
    const children = [...op.fromZone.querySelectorAll('.photo-card')];
    if (op.fromIndex >= children.length) {
        op.fromZone.appendChild(op.card);
    } else {
        op.fromZone.insertBefore(op.card, children[op.fromIndex]);
    }

    op.card.classList.add('just-dropped');
    op.card.addEventListener('animationend', () => op.card.classList.remove('just-dropped'), {once:true});

    window._editCount = Math.max(0, window._editCount - 1);
    refreshBadge();
    refreshZones();
    syncCounters();
}

// ── Reset all edits ─────────────────────────────────────────
resetBtn.addEventListener('click', function() {
    if (!_undoStack.length) return;
    if (!confirm('Reset all photo edits and restore the original layout?')) return;
    while (_undoStack.length) undoLast();
});

// ── Helpers ─────────────────────────────────────────────────
function refreshBadge() {
    undoBtn.disabled  = _undoStack.length === 0;
    resetBtn.disabled = _undoStack.length === 0;
    if (window._editCount > 0) {
        badge.textContent = window._editCount + ' edit' + (window._editCount !== 1 ? 's' : '');
        badge.style.display = 'inline-block';
    } else {
        badge.style.display = 'none';
    }
}

// Update the "(N photos)" counters in each phase-section header
function syncCounters() {
    document.querySelectorAll('.phase-section').forEach(section => {
        const grid    = section.querySelector('.photo-grid');
        const counter = section.querySelector('.phase-count');
        if (grid && counter) {
            const n = grid.querySelectorAll('.photo-card').length;
            counter.textContent = n + ' photo' + (n !== 1 ? 's' : '');
        }
    });
    syncPhotoNumbers();
}

function syncPhotoNumbers() {
    document.querySelectorAll('.subcontract-grid').forEach(grid => {
        let n = 0;
        grid.querySelectorAll('.photo-card').forEach(card => {
            n += 1;
            let label = card.querySelector('.photo-index');
            if (!label) {
                label = document.createElement('span');
                label.className = 'photo-index';
                card.insertBefore(label, card.firstChild);
            }
            label.textContent = String(n);
        });
    });
}

function initSubcontractSortables() {
    if (typeof Sortable === 'undefined') return;
    destroySubcontractSortables();
    document.querySelectorAll('.subcontract-grid').forEach(grid => {
        const instance = Sortable.create(grid, {
            animation: 150,
            draggable: '.photo-card, .subcontract-heading',
            ghostClass: 'sortable-ghost',
            chosenClass: 'sortable-chosen',
            disabled: !window._editMode,
            onStart() {
                _sortableUndoSnapshot = { type: 'sortable', grid, order: [...grid.children] };
            },
            onEnd() {
                const changed = _sortableUndoSnapshot
                    && _sortableUndoSnapshot.order.some((el, i) => grid.children[i] !== el);
                if (changed) {
                    _undoStack.push(_sortableUndoSnapshot);
                    window._editCount++;
                    refreshBadge();
                }
                _sortableUndoSnapshot = null;
                syncPhotoNumbers();
            },
        });
        _sortableInstances.set(grid, instance);
    });
}

function destroySubcontractSortables() {
    _sortableInstances.forEach(instance => instance.destroy());
    _sortableInstances.clear();
    _sortableUndoSnapshot = null;
}

// Ensure every photo-grid has a drop-empty-hint sibling
function refreshZones() {
    document.querySelectorAll('.photo-grid').forEach(grid => {
        let hint = grid.nextElementSibling;
        if (!hint || !hint.classList.contains('drop-empty-hint')) {
            hint = document.createElement('div');
            hint.className = 'drop-empty-hint';
            hint.textContent = 'Drop photos here';
            grid.parentNode.insertBefore(hint, grid.nextSibling);
        }
        // Toggle visibility
        const empty = grid.querySelectorAll('.photo-card').length === 0;
        hint.classList.toggle('visible', empty && window._editMode);
    });
}

// ── Drag event wiring ────────────────────────────────────────
// We use event delegation on document so dynamically-moved cards
// keep working without re-binding.

document.addEventListener('dragstart', function(e) {
    if (!window._editMode) return;
    const card = e.target.closest('.photo-card');
    if (!card || card.closest('.subcontract-grid')) return;

    _dragging       = card;
    _sourceZone     = card.closest('.photo-grid');
    window._dragActive = true;

    // Semi-transparent ghost (browser default is fine, but we fade the source)
    setTimeout(() => card.classList.add('dragging'), 0);
    e.dataTransfer.effectAllowed = 'move';
    // Store card URL as transfer data (used for cross-zone logic)
    const img = card.querySelector('img');
    if (img) e.dataTransfer.setData('text/plain', img.src);
});

document.addEventListener('dragend', function(e) {
    if (_dragging) {
        _dragging.classList.remove('dragging');
        _dragging = null;
    }
    window._dragActive = false;
    _scrollDir = 0; // Reset scroll direction

    // Clean up all drop indicators and highlights
    document.querySelectorAll('.drop-indicator').forEach(el => el.remove());
    document.querySelectorAll('.photo-grid.drag-over').forEach(el => el.classList.remove('drag-over'));
    refreshZones();
    syncCounters();
});

document.addEventListener('dragover', function(e) {
    if (!window._editMode || !_dragging) return;
    _updateScrollDirection(e.clientY);
    const grid = e.target.closest('.photo-grid');
    if (!grid || grid.classList.contains('subcontract-grid')) return;
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';

    grid.classList.add('drag-over');

    // Remove any existing indicator
    grid.querySelectorAll('.drop-indicator').forEach(el => el.remove());

    // Find the card we're hovering over and insert an indicator before it
    const cards = [...grid.querySelectorAll('.photo-card:not(.dragging)')];
    let insertBefore = null;

    for (const c of cards) {
        const rect = c.getBoundingClientRect();
        const midX = rect.left + rect.width / 2;
        if (e.clientX < midX) {
            insertBefore = c;
            break;
        }
    }

    const indicator = document.createElement('div');
    indicator.className = 'drop-indicator';
    if (insertBefore) {
        grid.insertBefore(indicator, insertBefore);
    } else {
        grid.appendChild(indicator);
    }
});

document.addEventListener('dragleave', function(e) {
    const grid = e.target.closest('.photo-grid');
    if (!grid || grid.classList.contains('subcontract-grid')) return;
    // Only clear if we truly left the grid (not entered a child)
    if (!grid.contains(e.relatedTarget)) {
        grid.classList.remove('drag-over');
        grid.querySelectorAll('.drop-indicator').forEach(el => el.remove());
    }
});

document.addEventListener('drop', function(e) {
    if (!window._editMode || !_dragging) return;
    const grid = e.target.closest('.photo-grid');
    if (!grid || grid === _dragging || grid.classList.contains('subcontract-grid')) return;
    e.preventDefault();

    grid.classList.remove('drag-over');

    // Find insert position (before whichever card the cursor is left of)
    const cards = [...grid.querySelectorAll('.photo-card:not(.dragging)')];
    let insertBefore = null;
    for (const c of cards) {
        const rect = c.getBoundingClientRect();
        if (e.clientX < rect.left + rect.width / 2) {
            insertBefore = c;
            break;
        }
    }

    // Record undo state BEFORE the move
    const fromZone  = _sourceZone;
    const fromIndex = [...fromZone.querySelectorAll('.photo-card')].indexOf(_dragging);
    const toZone    = grid;
    const toIndex   = insertBefore
        ? [...toZone.querySelectorAll('.photo-card')].indexOf(insertBefore)
        : toZone.querySelectorAll('.photo-card').length;

    _undoStack.push({ card: _dragging, fromZone, fromIndex, toZone, toIndex });

    // Perform the move
    if (insertBefore) {
        grid.insertBefore(_dragging, insertBefore);
    } else {
        grid.appendChild(_dragging);
    }

    // Visual feedback
    const droppedCard = _dragging;
    droppedCard.classList.add('just-dropped');
    droppedCard.addEventListener('animationend', () => droppedCard.classList.remove('just-dropped'), {once:true});

    window._editCount++;
    refreshBadge();
    refreshZones();
    syncCounters();
});

// ── Make all cards draggable in edit mode ───────────────────
// We set draggable=true on all .photo-card elements at init,
// but only the dragstart handler actually fires when editMode is off.
document.querySelectorAll('.photo-card').forEach(card => {
    if (!card.closest('.subcontract-grid')) {
        card.setAttribute('draggable', 'true');
    }
});

// ── Subcontracted: heading injection + photo selection ───────
let _selectedPhoto = null;
let _selectedHeading = null;
const injectHeadingBtn = document.getElementById('inject-heading-btn');

function activeTabPane() {
    return document.querySelector('.tab-pane.active');
}

function _headingText(el) {
    const span = el.querySelector('.heading-text');
    if (span) return span.textContent;
    return el.textContent.replace(/×/g, '').trim();
}

function _setHeadingText(el, text) {
    const span = el.querySelector('.heading-text');
    if (span) span.textContent = text;
    else el.textContent = text;
}

function clearHeadingSelection() {
    document.querySelectorAll('.subcontract-heading.selected').forEach(h => h.classList.remove('selected'));
    _selectedHeading = null;
}

function clearPhotoSelection() {
    document.querySelectorAll('.photo-card.selected').forEach(c => c.classList.remove('selected'));
    _selectedPhoto = null;
}

function removeHeading(heading) {
    if (!heading || !window._editMode) return;
    heading.remove();
    if (_selectedHeading === heading) _selectedHeading = null;
    window._editCount++;
    refreshBadge();
    syncPhotoNumbers();
}

function updateInjectHeadingBtn() {
    if (!injectHeadingBtn) return;
    const pane = activeTabPane();
    const hasSub = pane && pane.querySelector('.subcontract-grid');
    injectHeadingBtn.style.display = (window._editMode && hasSub) ? 'inline-block' : 'none';
}

function _newHeadingId() {
    return 'h_' + Date.now() + '_' + Math.random().toString(36).slice(2, 7);
}

function _normalizeWeight(input) {
    const v = (input || '').trim().toLowerCase();
    if (v === 'light' || v === 'l') return 'light';
    if (v === 'heavy' || v === 'h') return 'heavy';
    return 'medium';
}

function _createHeadingElement(text, weight, id) {
    const el = document.createElement('div');
    el.className = 'subcontract-heading weight-' + weight;
    el.dataset.headingId = id;
    el.dataset.weight = weight;

    const textSpan = document.createElement('span');
    textSpan.className = 'heading-text';
    textSpan.textContent = text;

    const deleteBtn = document.createElement('button');
    deleteBtn.type = 'button';
    deleteBtn.className = 'heading-delete-btn';
    deleteBtn.title = 'Remove heading';
    deleteBtn.setAttribute('aria-label', 'Remove heading');
    deleteBtn.textContent = '×';
    deleteBtn.addEventListener('click', function(e) {
        e.preventDefault();
        e.stopPropagation();
        removeHeading(el);
    });

    el.appendChild(textSpan);
    el.appendChild(deleteBtn);
    return el;
}

function injectHeadingAfter(anchor) {
    const text = prompt('Heading text:');
    if (text === null) return;
    const weightInput = prompt('Heading weight (Light / Medium / Heavy):', 'Medium');
    if (weightInput === null) return;
    const weight = _normalizeWeight(weightInput);
    const id = _newHeadingId();
    const heading = _createHeadingElement(text.trim() || 'Heading', weight, id);

    const grid = (anchor && anchor.closest('.subcontract-grid')) || activeTabPane()?.querySelector('.subcontract-grid');
    if (!grid) return;

    if (anchor && anchor.classList.contains('photo-card')) {
        anchor.insertAdjacentElement('afterend', heading);
    } else {
        grid.appendChild(heading);
    }

    window._editCount++;
    refreshBadge();
    syncPhotoNumbers();
}

if (injectHeadingBtn) {
    injectHeadingBtn.addEventListener('click', function() {
        if (!window._editMode) return;
        injectHeadingAfter(_selectedPhoto);
    });
}

document.addEventListener('click', function(e) {
    const deleteBtn = e.target.closest('.heading-delete-btn');
    if (deleteBtn && window._editMode) {
        e.preventDefault();
        e.stopPropagation();
        removeHeading(deleteBtn.closest('.subcontract-heading'));
        return;
    }

    const card = e.target.closest('.photo-card');
    const grid = e.target.closest('.subcontract-grid');
    if (card && grid && window._editMode) {
        clearHeadingSelection();
        clearPhotoSelection();
        card.classList.add('selected');
        _selectedPhoto = card;
        return;
    }

    const heading = e.target.closest('.subcontract-heading');
    if (heading && grid && window._editMode) {
        clearPhotoSelection();
        clearHeadingSelection();
        heading.classList.add('selected');
        _selectedHeading = heading;
        return;
    }

    if (!e.target.closest('.subcontract-heading')) {
        clearPhotoSelection();
        clearHeadingSelection();
    }
});

document.addEventListener('keydown', function(e) {
    if (!window._editMode || !_selectedHeading) return;
    if (e.key === 'Delete' || e.key === 'Backspace') {
        const active = document.activeElement;
        if (active && (active.tagName === 'INPUT' || active.tagName === 'TEXTAREA' || active.isContentEditable)) return;
        e.preventDefault();
        removeHeading(_selectedHeading);
    }
});

document.addEventListener('dblclick', function(e) {
    if (e.target.closest('.heading-delete-btn')) return;
    const heading = e.target.closest('.subcontract-heading');
    if (!heading || !window._editMode) return;
    e.preventDefault();
    const text = prompt('Edit heading text:', _headingText(heading));
    if (text === null) return;
    const weightInput = prompt('Edit heading weight (Light / Medium / Heavy):', heading.dataset.weight || 'medium');
    if (weightInput === null) return;
    const weight = _normalizeWeight(weightInput);
    _setHeadingText(heading, text.trim() || 'Heading');
    heading.dataset.weight = weight;
    heading.className = 'subcontract-heading weight-' + weight;
    window._editCount++;
    refreshBadge();
});

document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', updateInjectHeadingBtn);
});

window.updateInjectHeadingBtn = updateInjectHeadingBtn;

// ── Initial state ────────────────────────────────────────────
refreshBadge();
refreshZones();

// ============================================================
// SHOW EMPTY ZONES
// ============================================================
let _zonesVisible = false;
document.getElementById('show-zones-btn').addEventListener('click', toggleEmptyZones);
function toggleEmptyZones() {
    _zonesVisible = !_zonesVisible;
    const btn = document.getElementById('show-zones-btn');
    btn.classList.toggle('zones-visible', _zonesVisible);
    btn.textContent = _zonesVisible ? '− Hide Empty Zones' : '＋ Show Empty Zones';
    if (_zonesVisible) {
        injectEmptyZones();
    } else {
        removeInjectedZones();
    }
}
// When edit mode is turned off, also hide any injected zones
const _origToggleEditMode = toggleEditMode;

// Patch toggleEditMode to also clean up zones when mode turns off
const _editBtn2 = document.getElementById('edit-mode-btn');
_editBtn2.removeEventListener('click', toggleEditMode);
_editBtn2.addEventListener('click', function() {
    toggleEditMode();
    updateInjectHeadingBtn();
    if (!window._editMode && _zonesVisible) {
        _zonesVisible = false;
        document.getElementById('show-zones-btn').classList.remove('zones-visible');
        document.getElementById('show-zones-btn').textContent = '＋ Show Empty Zones';
        removeInjectedZones();
    }
});
function removeInjectedZones() {
    document.querySelectorAll('.injected-zone-wrap').forEach(wrap => {
        const grid = wrap.querySelector('.photo-grid');

        // If something is malformed, just remove it safely
        if (!grid) {
            wrap.remove();
            return;
        }

        const hasPhotos = grid.querySelector('.photo-card') !== null;

        if (!hasPhotos) {
            wrap.remove();
        } else {
            // Keep it, but convert it to a normal section
            wrap.classList.remove('injected-zone-wrap');
            wrap.removeAttribute('data-injected');
        }
    });

    refreshZones();
    syncCounters();
}

function injectEmptyZones() {
    // For every .unit-phases or .bathroom-group block, ensure all three phases exist
    // as droppable zones.  We look for the parent containers that already hold
    // .phase-section children and add any that are missing.
    // Collect all existing zone IDs so we don't double-inject
    const existingZones = new Set(
        [...document.querySelectorAll('.photo-grid[data-zone]')].map(g => g.dataset.zone)
    );

    // Walk every phase container (unit-phases div)
    document.querySelectorAll('.unit-phases').forEach(container => {
        // Derive the "base" zone prefix from the first existing zone in this container
        const firstGrid = container.querySelector('.photo-grid[data-zone]');
        if (!firstGrid) return;

        const firstZone = firstGrid.dataset.zone;
        // Lighting zones use the \x1f delimiter, not plumbing's __PHASE suffixes.
        if (firstZone.includes('\x1f')) return;
        // Strip the trailing __BEFORE / __AFTER / __UNTAGGED to get the base
        const zoneBase = firstZone.replace(/__(?:BEFORE|AFTER|UNTAGGED)$/, '');

        const phasesToCheck = ['BEFORE', 'AFTER', 'UNTAGGED'];
        phasesToCheck.forEach(phase => {
            const zid = zoneBase + '__' + phase;
            if (existingZones.has(zid)) return; // already there

            const wrap = document.createElement('div');
            wrap.className = 'injected-zone-wrap phase-section visible';
            wrap.dataset.injected = '1';

            const badgeClass = phase === 'BEFORE' ? 'before' : (phase === 'AFTER' ? 'after' : 'untagged');
            const label = phase === 'UNTAGGED' ? 'Untagged' : phase.charAt(0) + phase.slice(1).toLowerCase();

            wrap.innerHTML = `
                <div class="injected-zone-label">
                    <span class="iz-badge phase-badge ${badgeClass}">${label}</span>
                    <span style="color:#8899aa;font-size:10px;">Empty — drop photos here</span>
                </div>
                <div class="phase-header" style="display:none">
                    <h3 class="phase-title"></h3>
                    <span class="phase-count">0 photos</span>
                </div>
                <div class="photo-grid" data-zone="${zid}"></div>
            `;

            container.appendChild(wrap);
        });
    });

    // Also handle bathroom-group containers (unit_bath_phase / full modes)
    document.querySelectorAll('.bathroom-group').forEach(group => {
        const container = group.querySelector('.unit-phases');
        if (!container) return;
        // Already handled above by the .unit-phases walker
    });

    // Make all new cards draggable and refresh zones
    document.querySelectorAll('.photo-card').forEach(card => {
        if (!card.closest('.subcontract-grid')) {
            card.setAttribute('draggable', 'true');
        }
    });
    refreshZones();
    syncCounters();
}