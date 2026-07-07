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
