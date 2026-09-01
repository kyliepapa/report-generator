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
let _manualArrangeUndoSnapshot = null;

const MANUAL_ARRANGE_SORT_MODE = 'manual_arrange_sequence';

const SORTABLE_SCROLL_OPTS = {
    scroll: true,
    scrollSensitivity: 90,
    scrollSpeed: 30,
    bubbleScroll: true,
};

// ── Auto-scroll during drag ────────────────────────────────
let _scrollDir = 0; // -1 = up, 1 = down, 0 = none
let _sortableDragActive = false;
const _topScrollZone = 170;
const _bottomScrollZone = 85;
const _minScrollIntensity = 0.10;
const _maxScrollSpeed = 38;
let _sortablePointerHandler = null;

function _toolbarScrollOffset() {
    const toolbar = document.getElementById('dnd-toolbar');
    return toolbar ? toolbar.offsetHeight : 0;
}

function _scrollIntensityUp(clientY, isElementEdge) {
    const toolbarH = _toolbarScrollOffset();
    const topEnd = toolbarH + _topScrollZone;

    if (clientY >= topEnd) return 0;

    if (!isElementEdge && clientY < toolbarH) {
        return 0;
    }

    if (isElementEdge && clientY < toolbarH) {
        const depth = 1 + (toolbarH - clientY) / _topScrollZone;
        return Math.max(_minScrollIntensity, Math.min(depth * depth, 1.5));
    }

    const depth = (topEnd - clientY) / _topScrollZone;
    return Math.max(_minScrollIntensity, depth * depth);
}

function _scrollIntensityDown(clientY) {
    const h = window.innerHeight;
    const bottomStart = h - _bottomScrollZone;
    if (clientY <= bottomStart) return 0;
    const depth = (clientY - bottomStart) / _bottomScrollZone;
    return Math.max(_minScrollIntensity, depth * depth);
}

function _applyScrollIntensities(upIntensity, downIntensity) {
    if (upIntensity > downIntensity && upIntensity > 0) {
        _scrollDir = -upIntensity;
    } else if (downIntensity > 0) {
        _scrollDir = downIntensity;
    } else {
        _scrollDir = 0;
    }
}

function _updateScrollDirection(clientY) {
    _applyScrollIntensities(
        _scrollIntensityUp(clientY, false),
        _scrollIntensityDown(clientY),
    );
}

function _updateScrollFromDrag(evt) {
    const oe = evt.originalEvent;
    const pointerY = oe
        ? (oe.clientY != null ? oe.clientY : (oe.touches && oe.touches[0] ? oe.touches[0].clientY : null))
        : null;
    const rect = evt.dragged ? evt.dragged.getBoundingClientRect() : null;
    const toolbarH = _toolbarScrollOffset();
    const pointerInToolbar = pointerY != null && pointerY < toolbarH;

    const upFromPointer = (pointerY != null && !pointerInToolbar)
        ? _scrollIntensityUp(pointerY, false) : 0;
    const downFromPointer = (pointerY != null && !pointerInToolbar)
        ? _scrollIntensityDown(pointerY) : 0;
    const upFromRect = rect ? _scrollIntensityUp(rect.top, true) : 0;
    const downFromRect = rect ? _scrollIntensityDown(rect.bottom) : 0;

    _applyScrollIntensities(
        Math.max(upFromPointer, upFromRect),
        Math.max(downFromPointer, downFromRect),
    );
}

function _sortableOnMove(evt) {
    _updateScrollFromDrag(evt);
    return true;
}

function _autoScrollLoop() {
    if ((window._dragActive || _sortableDragActive) && _scrollDir !== 0) {
        window.scrollBy(0, _scrollDir * _maxScrollSpeed);
    }
    requestAnimationFrame(_autoScrollLoop);
}

function _startSortableAutoScroll() {
    _sortableDragActive = true;
    if (_sortablePointerHandler) return;
    _sortablePointerHandler = function(e) {
        const y = e.clientY != null ? e.clientY : (e.touches && e.touches[0] ? e.touches[0].clientY : null);
        if (y != null) _updateScrollDirection(y);
    };
    document.addEventListener('pointermove', _sortablePointerHandler, { passive: true });
    document.addEventListener('touchmove', _sortablePointerHandler, { passive: true });
}

function _stopSortableAutoScroll() {
    _sortableDragActive = false;
    _scrollDir = 0;
    if (_sortablePointerHandler) {
        document.removeEventListener('pointermove', _sortablePointerHandler);
        document.removeEventListener('touchmove', _sortablePointerHandler);
        _sortablePointerHandler = null;
    }
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
    if (window._editMode && window.AutoRecReportAnalytics) {
        window.AutoRecReportAnalytics.recordEditMode();
    }
    document.body.classList.toggle('edit-mode', window._editMode);
    editBtn.classList.toggle('active', window._editMode);
    editBtn.textContent = window._editMode ? '✏️ Editing On' : '✏️ Edit Photos';
    document.getElementById('edit-mode-hint').textContent = window._editMode
        ? 'Drag photos between zones · Shift+click to select · Click to preview · Ctrl+Z to undo'
        : 'Enable to rearrange photos';
    if (window._editMode) {
        initAllSortables();
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
    if (window.AutoRecReportAnalytics) window.AutoRecReportAnalytics.recordUndo();
    const op = _undoStack.pop();

    if (op.type === 'sortable') {
        op.order.forEach(el => op.grid.appendChild(el));
        window._editCount = Math.max(0, window._editCount - 1);
        refreshBadge();
        syncPhotoNumbers();
        return;
    }

    if (op.type === 'sortable-cross') {
        op.grids.forEach(({ grid, order }) => order.forEach(el => grid.appendChild(el)));
        window._editCount = Math.max(0, window._editCount - 1);
        refreshBadge();
        syncPhotoNumbers();
        refreshZones();
        syncCounters();
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
    if (window.AutoRecReportAnalytics) window.AutoRecReportAnalytics.recordReset();
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

function _manualArrangeMeasureIdForPane(pane) {
    if (!pane) return null;
    if (pane.dataset.sortMode === MANUAL_ARRANGE_SORT_MODE) {
        return pane.id.startsWith('tab-') ? pane.id.slice(4) : null;
    }
    if (!pane.id.startsWith('tab-')) return null;
    const tabId = pane.id.slice(4);
    const btn = document.querySelector(`.tab-btn[data-tab="${tabId}"]`);
    if (btn && btn.dataset.sortMode === MANUAL_ARRANGE_SORT_MODE) return tabId;
    return null;
}

function _isManualArrangeStagingGrid(grid) {
    if (!grid || !grid.classList.contains('subcontract-grid')) return false;
    return !!_manualArrangeMeasureIdForPane(grid.closest('.tab-pane'));
}

function _manualArrangePaneGrids(pane) {
    const staging = pane.querySelector('.subcontract-grid.photo-grid');
    const buckets = [...pane.querySelectorAll('.manual-arrange-bucket .photo-grid')];
    return { staging, buckets };
}

function _snapshotManualArrangeGrids(pane) {
    const { staging, buckets } = _manualArrangePaneGrids(pane);
    const grids = [staging, ...buckets].filter(Boolean);
    return {
        type: 'sortable-cross',
        grids: grids.map(grid => ({ grid, order: [...grid.children] })),
    };
}

function _manualArrangeGridsChanged(snapshot) {
    return snapshot.grids.some(({ grid, order }) =>
        order.some((el, i) => grid.children[i] !== el)
    );
}

function _sortableEndAnalytics(fromGrid, toGrid) {
    if (!window.AutoRecReportAnalytics) return;
    const fromZ = fromGrid ? fromGrid.dataset.zone || '' : '';
    const toZ = toGrid ? toGrid.dataset.zone || '' : '';
    if (fromZ === toZ) {
        window.AutoRecReportAnalytics.recordReorder(toZ);
    } else {
        window.AutoRecReportAnalytics.recordMove(fromZ, toZ);
    }
}

function _usesSortableDrag(card) {
    if (!card) return false;
    if (card.closest('.manual-arrange-bucket')) return true;
    if (card.closest('.subcontract-grid')) return true;
    return false;
}

function _sortableGridForCard(card) {
    if (!card) return null;
    const bucketGrid = card.closest('.manual-arrange-bucket .photo-grid');
    if (bucketGrid) return bucketGrid;
    return card.closest('.subcontract-grid');
}

function _orderedSelectedCardsInGrid(grid) {
    if (!grid) return [];
    return [...grid.children].filter(el =>
        el.classList.contains('photo-card') && _selectedPhotos.has(el)
    );
}

function _orderedSelectedCardsForMultiDrag(evt) {
    const dragged = evt.item;
    if (!dragged.classList.contains('photo-card')) return null;
    if (!_selectedPhotos.has(dragged) || _selectedPhotos.size < 2) return null;

    const pane = evt.from.closest('.tab-pane');
    if (pane && _manualArrangeMeasureIdForPane(pane)) {
        const cards = [...pane.querySelectorAll('.photo-card')].filter(c => _selectedPhotos.has(c));
        return cards.length > 1 ? cards : null;
    }

    const ordered = _orderedSelectedCardsInGrid(evt.from);
    return ordered.length > 1 ? ordered : null;
}

let _multiDragPending = null;

function _clearMultiDragVisuals() {
    document.querySelectorAll('.photo-card.multi-drag-source').forEach(card => {
        card.classList.remove('multi-drag-source');
    });
}

function _applyMultiDragReposition(evt) {
    if (!_multiDragPending) return;
    const { cards } = _multiDragPending;
    const toGrid = evt.to;
    const dragged = evt.item;

    const preChildren = [...toGrid.children];
    const dropIndex = preChildren.indexOf(dragged);
    let insertAt = 0;
    for (let i = 0; i < dropIndex; i++) {
        if (!cards.includes(preChildren[i])) insertAt++;
    }

    cards.forEach(card => card.remove());

    const ref = toGrid.children[insertAt] || null;
    if (ref) {
        cards.forEach(card => toGrid.insertBefore(card, ref));
    } else {
        cards.forEach(card => toGrid.appendChild(card));
    }
    _multiDragPending = null;
}

function _sortableDragStart(evt) {
    _startSortableAutoScroll();
    if (!evt.item.classList.contains('photo-card')) return;
    const cards = _orderedSelectedCardsForMultiDrag(evt);
    if (!cards) return;
    _multiDragPending = { cards, from: evt.from };
    cards.forEach(card => {
        if (card !== evt.item) card.classList.add('multi-drag-source');
    });
}

function _sortableDragEnd(evt) {
    _applyMultiDragReposition(evt);
    _clearMultiDragVisuals();
    _stopSortableAutoScroll();
}

function _setCardDraggable(card) {
    card.setAttribute('draggable', _usesSortableDrag(card) ? 'false' : 'true');
}

function initAllSortables() {
    if (typeof Sortable === 'undefined') return;
    destroySubcontractSortables();
    initSubcontractSortables();
    initManualArrangeSortables();
}

function initSubcontractSortables() {
    document.querySelectorAll('.subcontract-grid').forEach(grid => {
        if (_isManualArrangeStagingGrid(grid)) return;

        const instance = Sortable.create(grid, {
            ...SORTABLE_SCROLL_OPTS,
            animation: 150,
            draggable: '.photo-card, .subcontract-heading',
            ghostClass: 'sortable-ghost',
            chosenClass: 'sortable-chosen',
            disabled: !window._editMode,
            onMove: _sortableOnMove,
            onStart(evt) {
                _sortableUndoSnapshot = { type: 'sortable', grid, order: [...grid.children] };
                _sortableDragStart(evt);
            },
            onEnd(evt) {
                _sortableDragEnd(evt);
                const changed = _sortableUndoSnapshot
                    && _sortableUndoSnapshot.order.some((el, i) => grid.children[i] !== el);
                if (changed) {
                    _undoStack.push(_sortableUndoSnapshot);
                    window._editCount++;
                    _sortableEndAnalytics(grid, grid);
                    refreshBadge();
                }
                _sortableUndoSnapshot = null;
                syncPhotoNumbers();
            },
        });
        _sortableInstances.set(grid, instance);
    });
}

function initManualArrangeSortables() {
    document.querySelectorAll('.tab-pane').forEach(pane => {
        const measureId = _manualArrangeMeasureIdForPane(pane);
        if (!measureId) return;

        const { staging, buckets } = _manualArrangePaneGrids(pane);
        if (!staging) return;

        const group = {
            name: 'manual-arrange-' + measureId,
            pull: true,
            put(to, from, dragEl) {
                if (dragEl.classList.contains('subcontract-heading')) {
                    return to.el.classList.contains('subcontract-grid');
                }
                return true;
            },
        };

        let dragFromGrid = null;

        const sortableOpts = {
            ...SORTABLE_SCROLL_OPTS,
            animation: 150,
            group,
            ghostClass: 'sortable-ghost',
            chosenClass: 'sortable-chosen',
            disabled: !window._editMode,
            onMove: _sortableOnMove,
            onStart(evt) {
                dragFromGrid = evt.from;
                _manualArrangeUndoSnapshot = _snapshotManualArrangeGrids(pane);
                _sortableDragStart(evt);
            },
            onEnd(evt) {
                _sortableDragEnd(evt);
                const changed = _manualArrangeUndoSnapshot
                    && _manualArrangeGridsChanged(_manualArrangeUndoSnapshot);
                if (changed) {
                    _undoStack.push(_manualArrangeUndoSnapshot);
                    window._editCount++;
                    _sortableEndAnalytics(dragFromGrid, evt.to);
                    refreshBadge();
                }
                _manualArrangeUndoSnapshot = null;
                dragFromGrid = null;
                syncPhotoNumbers();
                refreshZones();
                syncCounters();
            },
        };

        const stagingInstance = Sortable.create(staging, {
            ...sortableOpts,
            draggable: '.photo-card, .subcontract-heading',
        });
        _sortableInstances.set(staging, stagingInstance);

        buckets.forEach(bucketGrid => {
            bucketGrid.querySelectorAll('.photo-card').forEach(card => {
                card.setAttribute('draggable', 'false');
            });
            const instance = Sortable.create(bucketGrid, {
                ...sortableOpts,
                draggable: '.photo-card',
            });
            _sortableInstances.set(bucketGrid, instance);
        });
    });
}

function destroySubcontractSortables() {
    _sortableInstances.forEach(instance => instance.destroy());
    _sortableInstances.clear();
    _sortableUndoSnapshot = null;
    _manualArrangeUndoSnapshot = null;
    _multiDragPending = null;
    _clearMultiDragVisuals();
    _stopSortableAutoScroll();
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
    if (!card || _usesSortableDrag(card)) return;

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

    if (window.AutoRecReportAnalytics) {
        const fromZ = fromZone ? fromZone.dataset.zone : '';
        const toZ = toZone ? toZone.dataset.zone : '';
        if (fromZ === toZ) {
            window.AutoRecReportAnalytics.recordReorder(toZ);
        } else {
            window.AutoRecReportAnalytics.recordMove(fromZ, toZ);
        }
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
document.querySelectorAll('.photo-card').forEach(_setCardDraggable);

// ── Subcontracted: heading injection + photo selection ───────
const _selectedPhotos = new Set();
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
    _selectedPhotos.clear();
    _selectedPhoto = null;
}

function selectPhotoCard(card, additive) {
    if (!card) return;
    if (additive) {
        if (_selectedPhotos.has(card)) {
            _selectedPhotos.delete(card);
            card.classList.remove('selected');
            _selectedPhoto = _selectedPhotos.size ? [..._selectedPhotos].slice(-1)[0] : null;
        } else {
            _selectedPhotos.add(card);
            card.classList.add('selected');
            _selectedPhoto = card;
        }
        return;
    }
    clearPhotoSelection();
    _selectedPhotos.add(card);
    card.classList.add('selected');
    _selectedPhoto = card;
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
    if (window.AutoRecReportAnalytics) window.AutoRecReportAnalytics.recordHeadingInjection();
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
    const sortableGrid = card ? _sortableGridForCard(card) : null;
    if (card && sortableGrid && window._editMode && e.shiftKey) {
        e.preventDefault();
        e.stopPropagation();
        clearHeadingSelection();
        selectPhotoCard(card, true);
        return;
    }

    const grid = e.target.closest('.subcontract-grid');
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
    if (window.AutoRecReportAnalytics) window.AutoRecReportAnalytics.recordHeadingEdit();
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
    document.querySelectorAll('.photo-card').forEach(_setCardDraggable);
    if (window._editMode) {
        initAllSortables();
    }
    refreshZones();
    syncCounters();
}

// ── Collapsible toolbar options + Show Tags ─────────────────
const SHOW_TAGS_STORAGE_KEY = 'autorec_show_photo_tags';

function _parseCardTags(card) {
    const raw = card.dataset.tags || card.dataset.tagsDefault || '[]';
    try {
        const parsed = JSON.parse(raw);
        return Array.isArray(parsed) ? parsed : [];
    } catch (e) {
        return [];
    }
}

function refreshPhotoTagDisplay(card) {
    if (!card) return;
    let row = card.querySelector('.photo-tags-display');
    if (!row) {
        row = document.createElement('div');
        row.className = 'photo-tags-display';
        const meta = card.querySelector('.photo-metadata');
        if (meta) meta.appendChild(row);
        else card.appendChild(row);
    }
    const tags = _parseCardTags(card);
    if (!tags.length) {
        row.innerHTML = '<span class="photo-tag-chip">No tags</span>';
        return;
    }
    row.innerHTML = tags.map(t => (
        `<span class="photo-tag-chip">${String(t).replace(/</g, '&lt;').replace(/>/g, '&gt;')}</span>`
    )).join('');
}

function refreshAllPhotoTagDisplays() {
    document.querySelectorAll('.photo-card[data-photo-url]').forEach(refreshPhotoTagDisplay);
}

function setShowPhotoTags(enabled) {
    document.body.classList.toggle('show-photo-tags', !!enabled);
    try {
        sessionStorage.setItem(SHOW_TAGS_STORAGE_KEY, enabled ? '1' : '0');
    } catch (e) { /* ignore */ }
    if (enabled) refreshAllPhotoTagDisplays();
}

(function initToolbarOptions() {
    const toggleBtn = document.getElementById('toolbar-options-toggle');
    const panel = document.getElementById('toolbar-options-panel');
    const showTagsCb = document.getElementById('show-tags-toggle');

    if (toggleBtn && panel) {
        toggleBtn.addEventListener('click', () => {
            const open = panel.hasAttribute('hidden');
            if (open) {
                panel.removeAttribute('hidden');
                toggleBtn.setAttribute('aria-expanded', 'true');
                toggleBtn.textContent = '▴ Options';
            } else {
                panel.setAttribute('hidden', '');
                toggleBtn.setAttribute('aria-expanded', 'false');
                toggleBtn.textContent = '▾ Options';
            }
        });
    }

    let initialShowTags = false;
    try {
        initialShowTags = sessionStorage.getItem(SHOW_TAGS_STORAGE_KEY) === '1';
    } catch (e) { /* ignore */ }

    if (showTagsCb) {
        showTagsCb.checked = initialShowTags;
        showTagsCb.addEventListener('change', () => setShowPhotoTags(showTagsCb.checked));
    }
    setShowPhotoTags(initialShowTags);

    window.refreshPhotoTagDisplay = refreshPhotoTagDisplay;
    window.refreshAllPhotoTagDisplays = refreshAllPhotoTagDisplays;
})();