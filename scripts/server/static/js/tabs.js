/**
 * Tab switching + lazy-load dispatch, shared by pages that use the
 * .tab-button / .tab-panel markup convention (currently strategy.html).
 *
 * Pages register their per-tab lazy loaders once (typically after their
 * loader functions are defined), then wire up onclick="showTab('id', event)"
 * on each tab button as before — showTab looks up the registered loader
 * for that tab name and calls it once per page load.
 */

let TAB_LAZY_LOADERS = {};

function registerTabLoaders(loaders) {
    TAB_LAZY_LOADERS = loaders || {};
}

function showTab(tabName, event) {
    document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
    document.querySelectorAll('.tab-button').forEach(b => b.classList.remove('active'));
    document.getElementById(tabName).classList.add('active');
    if (event) event.target.classList.add('active');

    const loader = TAB_LAZY_LOADERS[tabName];
    if (loader) loader();
}
