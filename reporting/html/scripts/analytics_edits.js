/**
 * Report-page edit analytics (drag/drop, headings, transforms).
 */
(function () {
    const params = new URLSearchParams(window.location.search);
    const runId = params.get('run_id');

    const edits = {
        edit_mode_entered: false,
        photo_moves_count: 0,
        photo_reorders_count: 0,
        undo_count: 0,
        reset_clicked: false,
        heading_edits_count: 0,
        heading_injections_count: 0,
        heading_label_edits_count: 0,
        photo_tag_edits_count: 0,
        photo_transforms_count: 0,
        zones_touched: [],
    };

    const zonesSet = new Set();

    function touchZone(zoneId) {
        if (!zoneId) return;
        zonesSet.add(zoneId);
        edits.zones_touched = Array.from(zonesSet);
    }

    function snapshot() {
        if (typeof collectPhotoTransforms === 'function') {
            const t = collectPhotoTransforms();
            edits.photo_transforms_count = Object.keys(t || {}).length;
        }
        if (typeof collectPhotoTagEdits === 'function') {
            const tags = collectPhotoTagEdits();
            edits.photo_tag_edits_count = Object.keys(tags || {}).length;
        }
        return { ...edits, zones_touched: Array.from(zonesSet) };
    }

    window.AutoRecReportAnalytics = {
        runId,
        getEdits: snapshot,
        recordEditMode: () => { edits.edit_mode_entered = true; },
        recordMove: (fromZone, toZone) => {
            edits.photo_moves_count += 1;
            touchZone(fromZone);
            touchZone(toZone);
        },
        recordReorder: (zoneId) => {
            edits.photo_reorders_count += 1;
            touchZone(zoneId);
        },
        recordUndo: () => { edits.undo_count += 1; },
        recordReset: () => { edits.reset_clicked = true; },
        recordHeadingEdit: () => { edits.heading_edits_count += 1; },
        recordHeadingInjection: () => { edits.heading_injections_count += 1; },
        flush: () => {
            if (!runId) return;
            const body = JSON.stringify({ run_id: runId, edits: snapshot() });
            if (navigator.sendBeacon) {
                navigator.sendBeacon('/analytics/patch_report_edits', new Blob([body], { type: 'application/json' }));
            } else {
                fetch('/analytics/patch_report_edits', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body,
                    keepalive: true,
                }).catch(() => {});
            }
        },
        getAnalyticsPayload: () => {
            const ctx = window.AutoRecReportContext || {};
            return {
                parent_run_id: runId,
                user_id: ctx.user_id,
                display_name: ctx.display_name,
                session_id: ctx.session_id,
                edits: snapshot(),
                ux: {},
            };
        },
        markPdfOpened: () => {
            window._pdfAnalyticsOpened = true;
        },
    };

    window.addEventListener('beforeunload', () => {
        window.AutoRecReportAnalytics.flush();
    });
})();
