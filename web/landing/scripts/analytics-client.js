/**
 * Landing-page UX analytics helpers.
 */
(function () {
    const ux = {
        time_on_landing_ms: 0,
        validation_errors_before_submit: 0,
        help_overlay_opened: false,
        changelog_viewed: false,
    };

    const landingStart = Date.now();

    window.AutoRecAnalytics = window.AutoRecAnalytics || {};

    window.AutoRecAnalytics.getUx = function () {
        ux.time_on_landing_ms = Date.now() - landingStart;
        return { ...ux };
    };

    window.AutoRecAnalytics.recordValidationError = function () {
        ux.validation_errors_before_submit += 1;
    };

    window.AutoRecAnalytics.markHelpOpened = function () {
        ux.help_overlay_opened = true;
    };

    window.AutoRecAnalytics.markChangelogViewed = function () {
        ux.changelog_viewed = true;
    };

    window.AutoRecAnalytics.buildPayload = function () {
        const ctx = window.AutoRecAnalytics.getContext ? window.AutoRecAnalytics.getContext() : {};
        return {
            user_id: ctx.user_id,
            display_name: ctx.display_name,
            session_id: ctx.session_id,
            ux: window.AutoRecAnalytics.getUx(),
        };
    };
})();
