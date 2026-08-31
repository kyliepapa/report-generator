// Session-only photo edits (rotate, crop, tags, hide-flag). Cleared on page reload / HTML regenerate.
window._photoSession = window._photoSession || {};

function normalizePhotoUrl(url) {
    if (!url) return '';
    try {
        return decodeURI(String(url).trim()).replace(/\/$/, '');
    } catch (e) {
        return String(url).trim().replace(/\/$/, '');
    }
}

function _defaultSession() {
    return { rotation: 0, crop: null, tags: null, hideFlagged: false };
}

function getPhotoSession(url) {
    const key = normalizePhotoUrl(url);
    const s = window._photoSession[key];
    return Object.assign(_defaultSession(), s || {});
}

function setPhotoSession(url, patch) {
    const key = normalizePhotoUrl(url);
    if (!key) return;
    const cur = getPhotoSession(key);
    window._photoSession[key] = Object.assign({}, cur, patch);
}

function parseCardTags(card) {
    if (!card || !card.dataset.tags) return [];
    try {
        const t = JSON.parse(card.dataset.tags);
        return Array.isArray(t) ? t : [];
    } catch (e) {
        return [];
    }
}

function cardDefaultTags(card) {
    if (!card) return [];
    if (card.dataset.tagsDefault) {
        try {
            const t = JSON.parse(card.dataset.tagsDefault);
            return Array.isArray(t) ? t : [];
        } catch (e) { /* fall through */ }
    }
    return parseCardTags(card);
}

function getEffectiveTags(url, card) {
    const s = getPhotoSession(url);
    if (s.tags !== null) return s.tags.slice();
    return card ? cardDefaultTags(card) : [];
}

function cropInsetStyle(crop) {
    if (!crop) return '';
    const x = crop.x, y = crop.y, w = crop.w, h = crop.h;
    const top = (y * 100).toFixed(3) + '%';
    const right = ((1 - x - w) * 100).toFixed(3) + '%';
    const bottom = ((1 - y - h) * 100).toFixed(3) + '%';
    const left = (x * 100).toFixed(3) + '%';
    return 'inset(' + top + ' ' + right + ' ' + bottom + ' ' + left + ')';
}

function applyTransformStyles(img, session) {
    if (!img) return;
    const rot = session.rotation || 0;
    const crop = session.crop;
    let transform = '';
    if (rot) transform += 'rotate(' + rot + 'deg)';
    img.style.transform = transform || '';
    img.style.transformOrigin = 'center center';
    if (crop) {
        img.style.clipPath = cropInsetStyle(crop);
        img.style.webkitClipPath = cropInsetStyle(crop);
    } else {
        img.style.clipPath = '';
        img.style.webkitClipPath = '';
    }
}

function applyPhotoCardVisuals(card) {
    if (!card) return;
    const url = photoCardUrl(card);
    if (!url) return;
    const session = getPhotoSession(url);
    const wrap = card.querySelector('.photo-img-wrap');
    const img = wrap ? wrap.querySelector('img') : card.querySelector('img');
    if (img) applyTransformStyles(img, session);
}

function syncPhotoCardBadge(card) {
    if (!card) return;
    const url = photoCardUrl(card);
    const flagged = url && getPhotoSession(url).hideFlagged;
    card.classList.toggle('photo-hide-flagged', !!flagged);
    let badge = card.querySelector('.photo-hide-flag-badge');
    if (flagged) {
        if (!badge) {
            badge = document.createElement('span');
            badge.className = 'photo-hide-flag-badge';
            badge.textContent = 'Flagged to hide';
            card.appendChild(badge);
        }
    } else if (badge) {
        badge.remove();
    }
}

function syncPhotoCardFromSession(card) {
    applyPhotoCardVisuals(card);
    syncPhotoCardBadge(card);
    const url = photoCardUrl(card);
    if (!url) return;
    const s = getPhotoSession(url);
    if (s.tags !== null) {
        card.dataset.tags = JSON.stringify(s.tags);
    }
}

function photoCardUrl(card) {
    const canonical = card.dataset.photoUrl;
    if (canonical) return normalizePhotoUrl(canonical);
    const img = card.querySelector('img');
    return img ? normalizePhotoUrl(img.src) : null;
}

function tagsEqual(a, b) {
    if (!a || !b) return false;
    if (a.length !== b.length) return false;
    const sa = a.map(function(t) { return String(t).toLowerCase(); }).sort();
    const sb = b.map(function(t) { return String(t).toLowerCase(); }).sort();
    return sa.every(function(t, i) { return t === sb[i]; });
}

function collectPhotoTransforms() {
    const out = {};
    Object.keys(window._photoSession).forEach(function(key) {
        const s = window._photoSession[key];
        const rot = s.rotation || 0;
        const crop = s.crop;
        if (rot || crop) {
            const entry = {};
            if (rot) entry.rotation = rot;
            if (crop) entry.crop = crop;
            out[key] = entry;
        }
    });
    return Object.keys(out).length ? out : {};
}

function collectPhotoTagEdits() {
    const out = {};
    document.querySelectorAll('.photo-card[data-photo-url]').forEach(function(card) {
        const url = photoCardUrl(card);
        if (!url) return;
        const s = getPhotoSession(url);
        if (s.tags === null) return;
        const defaults = cardDefaultTags(card);
        if (!tagsEqual(s.tags, defaults)) {
            out[url] = s.tags.slice();
        }
    });
    return Object.keys(out).length ? out : {};
}

function collectHideFlags() {
    return Object.keys(window._photoSession).filter(function(key) {
        return window._photoSession[key].hideFlagged;
    });
}

// Apply session visuals to all cards on load (e.g. after tab switch)
function initPhotoSessionCards() {
    document.querySelectorAll('.photo-card[data-photo-url]').forEach(syncPhotoCardFromSession);
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initPhotoSessionCards);
} else {
    initPhotoSessionCards();
}
