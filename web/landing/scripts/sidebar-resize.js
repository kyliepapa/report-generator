/**
 * Draggable resize handle for the landing page sidebar.
 * Persists width in localStorage (desktop layout only).
 */
(function () {
    const STORAGE_KEY = 'autorec-sidebar-width';
    const MIN_WIDTH = 360;
    const DEFAULT_WIDTH = 500;

    const sidebar = document.querySelector('.sidebar.wide');
    const handle = document.getElementById('sidebarResizeHandle');
    if (!sidebar || !handle) return;

    function maxWidth() {
        return Math.min(900, Math.floor(window.innerWidth * 0.75));
    }

    function isResizeEnabled() {
        return window.matchMedia('(min-width: 901px)').matches;
    }

    function setWidth(px) {
        const clamped = Math.max(MIN_WIDTH, Math.min(maxWidth(), px));
        sidebar.style.setProperty('--sidebar-width', clamped + 'px');
        return clamped;
    }

    const saved = parseInt(localStorage.getItem(STORAGE_KEY), 10);
    if (saved >= MIN_WIDTH) {
        setWidth(saved);
    } else {
        setWidth(DEFAULT_WIDTH);
    }

    let startX = 0;
    let startWidth = 0;

    function onMove(e) {
        const clientX = e.touches ? e.touches[0].clientX : e.clientX;
        setWidth(startWidth + (clientX - startX));
    }

    function onEnd() {
        document.body.classList.remove('sidebar-resizing');
        document.body.style.cursor = '';
        document.body.style.userSelect = '';
        window.removeEventListener('mousemove', onMove);
        window.removeEventListener('mouseup', onEnd);
        window.removeEventListener('touchmove', onMove);
        window.removeEventListener('touchend', onEnd);
        if (isResizeEnabled()) {
            localStorage.setItem(STORAGE_KEY, sidebar.offsetWidth);
        }
    }

    function onStart(e) {
        if (!isResizeEnabled()) return;
        e.preventDefault();
        startX = e.touches ? e.touches[0].clientX : e.clientX;
        startWidth = sidebar.offsetWidth;
        document.body.classList.add('sidebar-resizing');
        document.body.style.cursor = 'col-resize';
        document.body.style.userSelect = 'none';
        window.addEventListener('mousemove', onMove);
        window.addEventListener('mouseup', onEnd);
        window.addEventListener('touchmove', onMove, { passive: false });
        window.addEventListener('touchend', onEnd);
    }

    handle.addEventListener('mousedown', onStart);
    handle.addEventListener('touchstart', onStart, { passive: false });

    window.addEventListener('resize', function () {
        if (!isResizeEnabled()) {
            sidebar.style.removeProperty('--sidebar-width');
        } else if (sidebar.offsetWidth > maxWidth()) {
            setWidth(maxWidth());
        }
    });
})();
