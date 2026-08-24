function openLightbox(url, tags, timestamp, geoLabel, geoUrl) {
    // Don't open lightbox while dragging
    if (window._dragActive) return;

    document.getElementById('lightbox-img').src = url;
    document.getElementById('lightbox-dl').href = url;
    document.getElementById('lightbox-ts').textContent = timestamp || '—';

    const geoEl = document.getElementById('lightbox-geo');
    if (geoLabel && geoUrl) {
        geoEl.innerHTML = '<a class="lightbox-geo-link" href="' + geoUrl + '" target="_blank">📍 ' + geoLabel + '</a>';
    } else {
        geoEl.textContent = 'No location data';
    }

    const tagsEl = document.getElementById('lightbox-tags');
    tagsEl.innerHTML = '';
    if (tags && tags.length) {
        tags.forEach(function(t) {
            const span = document.createElement('span');
            span.className = 'lightbox-tag';
            span.textContent = t;
            tagsEl.appendChild(span);
        });
    } else {
        tagsEl.textContent = 'None';
    }

    document.getElementById('lightbox').classList.add('active');
}
function closeLightbox(e) {
    if (e.target === document.getElementById('lightbox')) {
        document.getElementById('lightbox').classList.remove('active');
    }
}
document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape') document.getElementById('lightbox').classList.remove('active');
});