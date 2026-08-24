/**
 * Generic tag pill input. Call window.initTagBuilder(el) on any
 * .tag-builder container (must contain one .tag-input) to wire it up.
 * Read its committed tags at any time via el._getTags().
 */
function initTagBuilder(builderEl) {
    if (builderEl._tagBuilderInit) return; // avoid double-init
    builderEl._tagBuilderInit = true;
    builderEl._tags = [];

    const inputEl = builderEl.querySelector('.tag-input');

    function renderPills() {
        builderEl.querySelectorAll('.tag-pill').forEach(p => p.remove());

        builderEl._tags.forEach((tag, idx) => {
            const pill = document.createElement('span');
            pill.className = 'tag-pill';
            pill.dataset.idx = idx;

            const label = document.createElement('span');
            label.textContent = tag;

            const x = document.createElement('span');
            x.className = 'tag-pill-x';
            x.innerHTML = '&#x2715;';
            x.title = 'Remove';
            x.addEventListener('click', (e) => {
                e.stopPropagation();
                builderEl._tags.splice(idx, 1);
                renderPills();
            });

            pill.appendChild(label);
            pill.appendChild(x);
            builderEl.insertBefore(pill, inputEl);
        });
    }

    function commitTag() {
        const val = inputEl.value.trim();
        if (!val) return;
        if (!builderEl._tags.some(t => t.toLowerCase() === val.toLowerCase())) {
            builderEl._tags.push(val);
            renderPills();
        }
        inputEl.value = '';
    }

    inputEl.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' || e.key === ',') {
            e.preventDefault();
            commitTag();
        }
        if (e.key === 'Backspace' && inputEl.value === '' && builderEl._tags.length > 0) {
            builderEl._tags.pop();
            renderPills();
        }
    });

    inputEl.addEventListener('blur', commitTag);
    builderEl.addEventListener('click', () => inputEl.focus());

    builderEl._getTags = () => {
        commitTag();
        return [...builderEl._tags];
    };
}

window.initTagBuilder = initTagBuilder;

// Init any tag builders already present in the static HTML (e.g. none by
// default now — Project Details and measure tabs build theirs dynamically).
document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('.tag-builder').forEach(initTagBuilder);
});