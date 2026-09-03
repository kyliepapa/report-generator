/**
 * Basic / Advanced mode overlay for the landing page.
 * Hides preset fields, wraps advanced options in drawers, and supplies
 * preset values at validation/submit time without mutating Advanced behavior.
 */
(function () {
    const STORAGE_KEY = 'autorec-ui-mode';

    function presets() {
        return window.BASIC_MODE_PRESETS || {};
    }

    function getMode() {
        return localStorage.getItem(STORAGE_KEY) === 'advanced' ? 'advanced' : 'basic';
    }

    function setMode(mode) {
        localStorage.setItem(STORAGE_KEY, mode);
        document.body.classList.toggle('basic-mode', mode === 'basic');
        document.body.classList.toggle('advanced-mode', mode === 'advanced');
    }

    function getTagsFor(id, panelEl) {
        const el = panelEl.querySelector(`#${id}`);
        return el && el._getTags ? el._getTags() : [];
    }

    window.isBasicMode = function () {
        return getMode() === 'basic';
    };

    window.getMeasureKeywords = function (id, panelEl) {
        if (!window.isBasicMode()) {
            return getTagsFor(`measureKeywords-${id}Builder`, panelEl);
        }
        return [...(presets().measure_keywords || [])];
    };

    window.getSerialTags = function (measureType, id, panelEl) {
        if (!window.isBasicMode()) {
            const prefix = measureType === 'lighting' ? 'lightingSerialTags' : 'heatPumpSerialTags';
            return getTagsFor(`${prefix}-${id}Builder`, panelEl);
        }
        return [...(presets().serial_tag || [])];
    };

    window.getLightingPhases = function (id, panelEl) {
        if (!window.isBasicMode()) {
            return getTagsFor(`phases-${id}Builder`, panelEl);
        }
        return [...(presets().lighting_phases || [])];
    };

    window.getSubcontractedHash = function (id, panelEl) {
        if (!window.isBasicMode()) {
            const hashEl = panelEl.querySelector(`#sc-${id} .subcontract-hash`);
            return hashEl ? hashEl.value.trim() : '';
        }
        return presets().subcontracted_hash || '#';
    };

    function activeToggleValue(group, panelEl) {
        const btn = panelEl.querySelector(`button.toggle.active[data-group="${group}"]`);
        return btn ? btn.dataset.value : null;
    }

    window.getSubcontractedKeySource = function (id, panelEl) {
        const selected = activeToggleValue(`subconKey-${id}`, panelEl);
        if (selected) return selected.toLowerCase();
        if (window.isBasicMode()) {
            return presets().subcontracted_key_source || 'description';
        }
        return 'tags';
    };

    function setSubcontractedKeySourceDefault(panelEl, id) {
        const descBtn = panelEl.querySelector(
            `button.toggle[data-group="subconKey-${id}"][data-value="Description"]`
        );
        if (descBtn && !descBtn.classList.contains('active')) {
            descBtn.click();
        }
    }

    function markHiddenField(panelEl, selector) {
        const el = panelEl.querySelector(selector);
        if (!el) return;
        const group = el.closest('.field-group');
        if (group) group.classList.add('basic-mode-field');
    }

    function applyHiddenFields(panelEl, id) {
        [
            `#measureKeywords-${id}Builder`,
            `#phases-${id}Builder`,
            `#lightingSerialTags-${id}Builder`,
            `#heatPumpSerialTags-${id}Builder`,
            `#sc-${id} .subcontract-hash`,
        ].forEach(sel => markHiddenField(panelEl, sel));

        panelEl.querySelectorAll('.basic-mode-field').forEach(group => {
            group.classList.toggle('basic-mode-hidden-field', window.isBasicMode());
        });
    }

    function createDrawer(drawerId) {
        const drawer = document.createElement('div');
        drawer.className = 'see-more-drawer';
        drawer.dataset.drawerId = drawerId;

        const summary = document.createElement('button');
        summary.type = 'button';
        summary.className = 'see-more-drawer-summary';
        summary.setAttribute('aria-expanded', 'false');
        summary.textContent = 'See More Options';

        const content = document.createElement('div');
        content.className = 'see-more-drawer-content';
        content.hidden = true;

        summary.addEventListener('click', () => {
            const expanded = summary.getAttribute('aria-expanded') === 'true';
            summary.setAttribute('aria-expanded', expanded ? 'false' : 'true');
            content.hidden = expanded;
            drawer.classList.toggle('expanded', !expanded);
        });

        drawer.appendChild(summary);
        drawer.appendChild(content);
        return drawer;
    }

    function unwrapDrawer(drawer) {
        const content = drawer.querySelector('.see-more-drawer-content');
        if (!content) {
            drawer.remove();
            return;
        }

        const restore = drawer._restoreInfo;
        if (restore && restore.length) {
            restore.forEach(({ el, parent, nextSibling }) => {
                if (!el || !parent) return;
                if (nextSibling && nextSibling.parentNode === parent) {
                    parent.insertBefore(el, nextSibling);
                } else {
                    parent.appendChild(el);
                }
            });
        } else {
            const parent = drawer.parentNode;
            while (content.firstChild) {
                parent.insertBefore(content.firstChild, drawer);
            }
        }
        drawer.remove();
    }

    function syncDrawerElements(container, drawerId, elementFinders, onCreate) {
        if (!container) return false;

        const anchor = container.querySelector('.basic-mode-drawer-anchor');
        const existing = container.querySelector(`.see-more-drawer[data-drawer-id="${drawerId}"]`);

        if (!window.isBasicMode()) {
            if (existing) unwrapDrawer(existing);
            return false;
        }

        let movable;
        if (existing) {
            movable = Array.from(existing.querySelector('.see-more-drawer-content').children);
            if (anchor && !anchor.contains(existing)) {
                anchor.appendChild(existing);
            }
            return false;
        }

        movable = elementFinders.map(fn => fn()).filter(Boolean);
        if (movable.length === 0) return false;

        const drawer = createDrawer(drawerId);
        drawer._restoreInfo = movable.map(el => ({
            el,
            parent: el.parentNode,
            nextSibling: el.nextSibling,
        }));

        const host = anchor || container;
        host.appendChild(drawer);

        const content = drawer.querySelector('.see-more-drawer-content');
        movable.forEach(el => content.appendChild(el));
        if (onCreate) onCreate();
        return true;
    }

    function applyBasicModeToPanel(panelEl) {
        const match = panelEl.id && panelEl.id.match(/^panel-(m\d+)$/);
        if (!match) return;
        const id = match[1];

        applyHiddenFields(panelEl, id);

        const hpContainer = panelEl.querySelector(`#hp-${id}`);
        syncDrawerElements(hpContainer, `hp-${id}`, [
            () => panelEl.querySelector(`#switch-intuitiveFixtureSort-${id}`)?.closest('.switch-group'),
            () => panelEl.querySelector(`#hpManualFixtureGroup-${id}`),
        ]);

        const maContainer = panelEl.querySelector(`#ma-${id}`);
        syncDrawerElements(maContainer, `ma-${id}`, [
            () => panelEl.querySelector(`#preSortBuckets-${id}Builder`)?.closest('.field-group'),
            () => panelEl.querySelector(`#switch-allowConflictingTags-${id}`)?.closest('.switch-group'),
        ]);

        const scContainer = panelEl.querySelector(`#sc-${id}`);
        syncDrawerElements(scContainer, `sc-${id}`, [
            () => panelEl.querySelector(`button.toggle[data-group="subconKey-${id}"]`)?.closest('.field-group'),
        ], () => setSubcontractedKeySourceDefault(panelEl, id));
    }

    window.applyBasicModeUI = function (panelEl) {
        if (panelEl) {
            applyBasicModeToPanel(panelEl);
            return;
        }
        document.querySelectorAll('.tab-panel[id^="panel-m"]').forEach(applyBasicModeToPanel);
    };

    function initModeToggle() {
        const toggle = document.getElementById('basicModeToggle');
        if (!toggle) return;

        const mode = getMode();
        toggle.checked = mode === 'basic';
        setMode(mode);

        toggle.addEventListener('change', () => {
            setMode(toggle.checked ? 'basic' : 'advanced');
            window.applyBasicModeUI();
        });
    }

    function init() {
        initModeToggle();
        window.applyBasicModeUI();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
