/**
 * Shared fetch helpers for the dashboard API.
 *
 * Two helpers cover the two fetch patterns duplicated across
 * overview.html and strategy.html:
 *
 *  - fetchJSON: fire-and-parse, used where callers never checked
 *    response.ok before (network errors still surface via the caller's
 *    try/catch).
 *  - fetchJSONWithStatus: used where the caller renders a distinct UI on
 *    non-2xx responses (e.g. "analysis not yet run" with a hint from the
 *    error body).
 */

async function fetchJSON(url, options) {
    const response = await fetch(url, options);
    if (!response.ok) {
        throw new Error(`HTTP ${response.status} for ${url}`);
    }
    return response.json();
}

async function fetchJSONWithStatus(url, options) {
    const response = await fetch(url, options);
    const data = await response.json().catch(() => ({}));
    return { ok: response.ok, status: response.status, data };
}

/**
 * URL builders for the two endpoints reached with a query string. A static
 * export (window.STATIC_MODE, set by scripts/export_static_site.py) can't
 * round-trip a query string through a static host, so those responses are
 * pre-expanded to flat sub-paths; mirror that mapping here. Against the live
 * Flask server STATIC_MODE is unset and the normal query URLs are used.
 */
function rollingUrl(key, metric, win) {
    return window.STATIC_MODE
        ? `/api/strategy/${key}/rolling/${metric}_${win}`
        : `/api/strategy/${key}/rolling?metric=${metric}&window=${win}`;
}

/**
 * The .metric-info tooltips are CSS-only (::after on hover/focus), so screen
 * readers never see data-tip. Stamp it as aria-label: once on load for static
 * markup, and lazily on focus/hover for tooltips injected by later renders.
 */
function stampTooltipLabel(el) {
    if (el && el.classList && el.classList.contains('metric-info') &&
        el.dataset.tip && !el.getAttribute('aria-label')) {
        el.setAttribute('aria-label', el.dataset.tip);
        el.setAttribute('role', 'note');
    }
}
document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('.metric-info[data-tip]').forEach(stampTooltipLabel);
});
document.addEventListener('focusin', e => stampTooltipLabel(e.target));
document.addEventListener('mouseover', e => stampTooltipLabel(e.target));

function exportUrl(key, type) {
    return window.STATIC_MODE
        ? `/api/strategy/${key}/export/${type}.csv`
        : `/api/strategy/${key}/export?type=${type}`;
}
