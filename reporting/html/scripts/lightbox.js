(function() {
    let _activeCard = null;
    let _activeUrl = '';
    let _cropMode = false;
    let _draftCrop = null;
    let _cropDrag = null;

    const MIN_CROP = 0.08;

    function el(id) { return document.getElementById(id); }

    function getImgRect() {
        const img = el('lightbox-img');
        const wrap = el('lightbox-img-wrap');
        if (!img || !wrap) return null;
        const ir = img.getBoundingClientRect();
        const wr = wrap.getBoundingClientRect();
        return {
            img, wrap,
            left: ir.left - wr.left,
            top: ir.top - wr.top,
            width: ir.width,
            height: ir.height,
        };
    }

    function defaultCropRect() {
        return { x: 0.05, y: 0.05, w: 0.9, h: 0.9 };
    }

    function clampCrop(c) {
        let x = Math.max(0, Math.min(1, c.x));
        let y = Math.max(0, Math.min(1, c.y));
        let w = Math.max(MIN_CROP, Math.min(1 - x, c.w));
        let h = Math.max(MIN_CROP, Math.min(1 - y, c.h));
        return { x: x, y: y, w: w, h: h };
    }

    function renderCropOverlay() {
        const overlay = el('lightbox-crop-overlay');
        const box = el('lightbox-crop-box');
        const rect = getImgRect();
        if (!overlay || !box || !rect || !_draftCrop) return;

        const c = _draftCrop;
        const bx = rect.left + c.x * rect.width;
        const by = rect.top + c.y * rect.height;
        const bw = c.w * rect.width;
        const bh = c.h * rect.height;

        box.style.left = bx + 'px';
        box.style.top = by + 'px';
        box.style.width = bw + 'px';
        box.style.height = bh + 'px';

        const shades = overlay.querySelectorAll('.lightbox-crop-shade');
        if (shades.length >= 4) {
            shades[0].style.cssText = 'top:0;left:0;right:0;height:' + by + 'px;';
            shades[1].style.cssText = 'top:' + by + 'px;right:0;width:' + (rect.wrap.clientWidth - bx - bw) + 'px;height:' + bh + 'px;';
            shades[2].style.cssText = 'bottom:0;left:0;right:0;height:' + (rect.wrap.clientHeight - by - bh) + 'px;';
            shades[3].style.cssText = 'top:' + by + 'px;left:0;width:' + bx + 'px;height:' + bh + 'px;';
        }
    }

    function applyLightboxVisuals() {
        const img = el('lightbox-img');
        if (!img || !_activeUrl) return;
        const session = getPhotoSession(_activeUrl);
        applyTransformStyles(img, session);
    }

    function renderTags(tags) {
        const tagsEl = el('lightbox-tags');
        if (!tagsEl) return;
        tagsEl.innerHTML = '';
        if (!tags || !tags.length) {
            const span = document.createElement('span');
            span.className = 'lightbox-info-value';
            span.style.fontSize = '12px';
            span.textContent = 'None';
            tagsEl.appendChild(span);
            return;
        }
        tags.forEach(function(t) {
            const pill = document.createElement('span');
            pill.className = 'lightbox-tag';
            pill.textContent = t;
            const btn = document.createElement('button');
            btn.type = 'button';
            btn.className = 'lightbox-tag-remove';
            btn.innerHTML = '&times;';
            btn.setAttribute('aria-label', 'Remove tag');
            btn.addEventListener('click', function() {
                removeTag(t);
            });
            pill.appendChild(btn);
            tagsEl.appendChild(pill);
        });
    }

    function saveTags(tags) {
        setPhotoSession(_activeUrl, { tags: tags.slice() });
        renderTags(tags);
        if (_activeCard) {
            _activeCard.dataset.tags = JSON.stringify(tags);
            if (typeof window.refreshPhotoTagDisplay === 'function') {
                window.refreshPhotoTagDisplay(_activeCard);
            }
        }
    }

    function removeTag(tag) {
        const tags = getEffectiveTags(_activeUrl, _activeCard).filter(function(t) {
            return t.toLowerCase() !== String(tag).toLowerCase();
        });
        saveTags(tags);
    }

    function addTag(raw) {
        const val = String(raw || '').trim();
        if (!val) return;
        const tags = getEffectiveTags(_activeUrl, _activeCard);
        if (tags.some(function(t) { return t.toLowerCase() === val.toLowerCase(); })) return;
        tags.push(val);
        saveTags(tags);
    }

    function syncFlagButton() {
        const btn = el('lightbox-flag-btn');
        if (!btn || !_activeUrl) return;
        const flagged = getPhotoSession(_activeUrl).hideFlagged;
        btn.classList.toggle('active', flagged);
        btn.textContent = flagged ? '\u{1F6A9} Flagged for PDF Hide' : '\u{1F6A9} Flag for PDF Hide';
    }

    function exitCropMode(apply) {
        _cropMode = false;
        const overlay = el('lightbox-crop-overlay');
        const bar = el('lightbox-crop-bar');
        if (overlay) {
            overlay.classList.remove('active');
            overlay.hidden = true;
        }
        if (bar) bar.hidden = true;
        if (apply && _draftCrop) {
            setPhotoSession(_activeUrl, { crop: clampCrop(_draftCrop) });
            applyLightboxVisuals();
        }
        _draftCrop = null;
    }

    function enterCropMode() {
        const session = getPhotoSession(_activeUrl);
        _draftCrop = session.crop ? Object.assign({}, session.crop) : defaultCropRect();
        _cropMode = true;
        const overlay = el('lightbox-crop-overlay');
        const bar = el('lightbox-crop-bar');
        if (overlay) {
            overlay.hidden = false;
            overlay.classList.add('active');
        }
        if (bar) bar.hidden = false;
        requestAnimationFrame(renderCropOverlay);
    }

    function pointerToNorm(clientX, clientY) {
        const rect = getImgRect();
        if (!rect || !rect.width || !rect.height) return null;
        const x = (clientX - rect.wrap.getBoundingClientRect().left - rect.left) / rect.width;
        const y = (clientY - rect.wrap.getBoundingClientRect().top - rect.top) / rect.height;
        return { x: x, y: y };
    }

    function onCropPointerDown(e) {
        if (!_cropMode || !_draftCrop) return;
        const handle = e.target.closest('.lightbox-crop-handle');
        const box = el('lightbox-crop-box');
        const rect = getImgRect();
        if (!rect) return;
        e.preventDefault();
        const mode = handle
            ? handle.className.split(' ').pop()
            : (e.target === box ? 'move' : null);
        if (!mode) return;
        _cropDrag = {
            mode: mode,
            startX: e.clientX,
            startY: e.clientY,
            start: Object.assign({}, _draftCrop),
        };
        document.addEventListener('pointermove', onCropPointerMove);
        document.addEventListener('pointerup', onCropPointerUp);
    }

    function onCropPointerMove(e) {
        if (!_cropDrag || !_draftCrop) return;
        const rect = getImgRect();
        if (!rect) return;
        const dx = (e.clientX - _cropDrag.startX) / rect.width;
        const dy = (e.clientY - _cropDrag.startY) / rect.height;
        const s = _cropDrag.start;
        let c = Object.assign({}, s);
        const m = _cropDrag.mode;

        if (m === 'move') {
            c.x = s.x + dx;
            c.y = s.y + dy;
        } else {
            if (m.indexOf('e') >= 0 || m === 'e') c.w = s.w + dx;
            if (m.indexOf('w') >= 0 || m === 'w') { c.x = s.x + dx; c.w = s.w - dx; }
            if (m.indexOf('s') >= 0 || m === 's') c.h = s.h + dy;
            if (m.indexOf('n') >= 0 || m === 'n') { c.y = s.y + dy; c.h = s.h - dy; }
        }
        _draftCrop = clampCrop(c);
        renderCropOverlay();
    }

    function onCropPointerUp() {
        _cropDrag = null;
        document.removeEventListener('pointermove', onCropPointerMove);
        document.removeEventListener('pointerup', onCropPointerUp);
    }

    window.openLightboxFromCard = function(card) {
        if (window._dragActive) return;
        if (!card) return;

        _activeCard = card;
        _activeUrl = photoCardUrl(card);
        if (!_activeUrl) return;

        const session = getPhotoSession(_activeUrl);
        const tags = getEffectiveTags(_activeUrl, card);
        const timestamp = card.dataset.timestamp || '—';
        const geoLabel = card.dataset.geoLabel || '';
        const geoUrl = card.dataset.geoUrl || '';
        const originalUrl = card.dataset.originalUrl || _activeUrl;

        el('lightbox-img').src = _activeUrl;
        el('lightbox-dl').href = originalUrl;

        const openLink = el('lightbox-open-link');
        if (openLink) openLink.href = originalUrl;

        el('lightbox-ts').textContent = timestamp;

        const geoEl = el('lightbox-geo');
        if (geoLabel && geoUrl) {
            geoEl.innerHTML = '<a class="lightbox-geo-link" href="' + geoUrl + '" target="_blank" rel="noopener">\u{1F4CD} ' + geoLabel + '</a>';
        } else {
            geoEl.textContent = 'No location data';
        }

        renderTags(tags);
        applyLightboxVisuals();
        syncFlagButton();

        const tagInput = el('lightbox-tag-input');
        if (tagInput) tagInput.value = '';

        exitCropMode(false);
        el('lightbox').classList.add('active');
        requestAnimationFrame(applyLightboxVisuals);
    };

    // Legacy entry point for cached reports
    window.openLightbox = function(url, tags, timestamp, geoLabel, geoUrl) {
        const norm = normalizePhotoUrl(url);
        let card = null;
        document.querySelectorAll('.photo-card[data-photo-url]').forEach(function(c) {
            if (!card && photoCardUrl(c) === norm) card = c;
        });
        if (card) {
            openLightboxFromCard(card);
            return;
        }
        _activeCard = null;
        _activeUrl = norm;
        el('lightbox-img').src = url;
        el('lightbox-dl').href = url;
        const openLink = el('lightbox-open-link');
        if (openLink) openLink.href = url;
        el('lightbox-ts').textContent = timestamp || '—';
        const geoEl = el('lightbox-geo');
        if (geoLabel && geoUrl) {
            geoEl.innerHTML = '<a class="lightbox-geo-link" href="' + geoUrl + '" target="_blank" rel="noopener">\u{1F4CD} ' + geoLabel + '</a>';
        } else {
            geoEl.textContent = 'No location data';
        }
        if (tags && tags.length) {
            setPhotoSession(_activeUrl, { tags: tags.slice() });
        }
        renderTags(getEffectiveTags(_activeUrl, null));
        applyLightboxVisuals();
        syncFlagButton();
        el('lightbox').classList.add('active');
    };

    function closeLightboxNow() {
        if (_cropMode) exitCropMode(true);
        if (_activeCard && _activeUrl) {
            syncPhotoCardFromSession(_activeCard);
        }
        _activeCard = null;
        _activeUrl = '';
        el('lightbox').classList.remove('active');
    }

    window.closeLightbox = function(e) {
        if (e && e.target !== el('lightbox')) return;
        closeLightboxNow();
    };

    document.addEventListener('keydown', function(e) {
        if (!el('lightbox').classList.contains('active')) return;
        if (e.key === 'Escape') {
            if (_cropMode) {
                exitCropMode(false);
                e.preventDefault();
                return;
            }
            closeLightboxNow();
        }
        if (e.key === 'r' || e.key === 'R') {
            if (document.activeElement && document.activeElement.tagName === 'INPUT') return;
            rotateLightbox();
        }
    });

    function rotateLightbox() {
        if (!_activeUrl) return;
        const s = getPhotoSession(_activeUrl);
        const next = ((s.rotation || 0) + 90) % 360;
        setPhotoSession(_activeUrl, { rotation: next });
        applyLightboxVisuals();
        if (_cropMode) requestAnimationFrame(renderCropOverlay);
    }

    el('lightbox-close-btn').addEventListener('click', closeLightboxNow);
    el('lightbox-rotate-btn').addEventListener('click', rotateLightbox);
    el('lightbox-crop-btn').addEventListener('click', function() {
        if (_cropMode) exitCropMode(true);
        else enterCropMode();
    });
    el('lightbox-crop-apply').addEventListener('click', function() { exitCropMode(true); });
    el('lightbox-crop-cancel').addEventListener('click', function() { exitCropMode(false); });
    el('lightbox-crop-reset').addEventListener('click', function() {
        _draftCrop = defaultCropRect();
        renderCropOverlay();
    });
    el('lightbox-flag-btn').addEventListener('click', function() {
        if (!_activeUrl) return;
        const s = getPhotoSession(_activeUrl);
        setPhotoSession(_activeUrl, { hideFlagged: !s.hideFlagged });
        syncFlagButton();
    });

    const tagInput = el('lightbox-tag-input');
    if (tagInput) {
        tagInput.addEventListener('keydown', function(e) {
            if (e.key === 'Enter') {
                e.preventDefault();
                addTag(tagInput.value);
                tagInput.value = '';
            }
        });
    }

    const cropOverlay = el('lightbox-crop-overlay');
    if (cropOverlay) {
        cropOverlay.addEventListener('pointerdown', onCropPointerDown);
    }

    window.addEventListener('resize', function() {
        if (_cropMode) renderCropOverlay();
    });
})();
