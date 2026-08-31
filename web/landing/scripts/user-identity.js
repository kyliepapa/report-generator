/**
 * User identity modal + session context for analytics.
 * Blocks the app until a name is entered or a quick-pick is chosen.
 */
(function () {
    const STORAGE_KEY = 'autorec_user';

    function slugify(name) {
        return String(name || '')
            .trim()
            .toLowerCase()
            .replace(/[^a-z0-9]+/g, '_')
            .replace(/^_+|_+$/g, '') || 'anonymous';
    }

    function newSessionId() {
        if (window.crypto && crypto.randomUUID) return crypto.randomUUID();
        return 'sess_' + Date.now() + '_' + Math.random().toString(36).slice(2);
    }

    function loadStoredUser() {
        try {
            const raw = localStorage.getItem(STORAGE_KEY);
            if (!raw) return null;
            return JSON.parse(raw);
        } catch (e) {
            return null;
        }
    }

    function saveUser(displayName) {
        const user = {
            user_id: slugify(displayName),
            display_name: displayName.trim(),
        };
        localStorage.setItem(STORAGE_KEY, JSON.stringify(user));
        return user;
    }

    const state = {
        session_id: newSessionId(),
        session_started_at: Date.now(),
        user_id: null,
        display_name: null,
        ready: false,
    };

    window.AutoRecAnalytics = window.AutoRecAnalytics || {};

    window.AutoRecAnalytics.getContext = function () {
        return {
            user_id: state.user_id,
            display_name: state.display_name,
            session_id: state.session_id,
        };
    };

    window.AutoRecAnalytics.isReady = function () {
        return state.ready;
    };

    window.AutoRecAnalytics.slugify = slugify;

    function dismissModal() {
        const modal = document.getElementById('userIdentityModal');
        if (modal) modal.classList.remove('active');
        document.body.classList.remove('identity-locked');
        state.ready = true;
        window.dispatchEvent(new CustomEvent('autorec:user-ready', {
            detail: window.AutoRecAnalytics.getContext(),
        }));
    }

    function confirmName(raw) {
        const name = String(raw || '').trim();
        if (!name) return false;
        const user = saveUser(name);
        state.user_id = user.user_id;
        state.display_name = user.display_name;
        dismissModal();
        return true;
    }

    function initModal() {
        const modal = document.getElementById('userIdentityModal');
        const input = document.getElementById('userIdentityInput');
        const continueBtn = document.getElementById('userIdentityContinue');
        const quickBtns = document.querySelectorAll('[data-user-quick]');

        if (!modal || !input) return;

        const stored = loadStoredUser();
        if (stored && stored.display_name) {
            state.user_id = stored.user_id || slugify(stored.display_name);
            state.display_name = stored.display_name;
            dismissModal();
            return;
        }

        document.body.classList.add('identity-locked');
        modal.classList.add('active');
        input.focus();

        continueBtn.addEventListener('click', () => {
            if (!confirmName(input.value)) {
                input.focus();
            }
        });

        input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                if (!confirmName(input.value)) input.focus();
            }
        });

        quickBtns.forEach(btn => {
            btn.addEventListener('click', () => {
                const name = btn.getAttribute('data-user-quick');
                input.value = name;
                confirmName(name);
            });
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initModal);
    } else {
        initModal();
    }
})();
