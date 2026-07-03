/**
 * Chart.js construction helpers shared by the dashboard pages.
 */

// Shared line/bar color palette, cycled through by index.
const CHART_COLORS = [
    { border: '#667eea', bg: 'rgba(102,126,234,0.1)' },
    { border: '#f59e0b', bg: 'rgba(245,158,11,0.1)' },
    { border: '#10b981', bg: 'rgba(16,185,129,0.1)' },
    { border: '#ec4899', bg: 'rgba(236,72,153,0.1)' },
    { border: '#f97316', bg: 'rgba(249,115,22,0.1)' },
    { border: '#6366f1', bg: 'rgba(99,102,241,0.1)' },
];

/**
 * Render a frequency histogram of `values` into a Chart.js bar chart.
 *
 * Generic enough to back the overfitting-tab logit-score histogram today,
 * and CPCV / bootstrap distribution plots in later phases.
 *
 * @param {string} canvasId - id of the <canvas> element to render into.
 * @param {number[]} values - raw sample values to bin.
 * @param {object} [options]
 * @param {number} [options.nBinsMin=10] - minimum bin count.
 * @param {number} [options.nBinsMax=30] - maximum bin count.
 * @param {string} [options.label='Frequency'] - dataset label.
 * @param {string} [options.xTitle=''] - x-axis title (hidden if empty).
 * @param {string} [options.yTitle='Frequency'] - y-axis title.
 * @param {(binLabel: string) => string} [options.colorFn] - maps a bin's
 *   center label (string) to a CSS color for that bar.
 * @param {Chart|null} [options.existingChart] - a previous Chart instance
 *   to destroy before rendering (avoids leaking canvases on re-render).
 * @param {(binLabel: string) => string} [options.tooltipTitle] - optional
 *   tooltip title callback, given the hovered bin's label.
 * @returns {Chart|null} the new Chart.js instance, or null if the canvas
 *   is missing.
 */
function renderHistogram(canvasId, values, options = {}) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return null;

    const {
        nBinsMin = 10,
        nBinsMax = 30,
        label = 'Frequency',
        xTitle = '',
        yTitle = 'Frequency',
        colorFn = () => 'rgba(102,126,234,0.6)',
        existingChart = null,
        tooltipTitle = null,
    } = options;

    if (existingChart) existingChart.destroy();

    const min = Math.min(...values);
    const max = Math.max(...values);
    const nBins = Math.min(nBinsMax, Math.max(nBinsMin, Math.round(Math.sqrt(values.length))));
    const binWidth = (max - min) / nBins || 1;
    const bins = Array(nBins).fill(0);
    values.forEach(v => {
        const idx = Math.min(Math.floor((v - min) / binWidth), nBins - 1);
        bins[idx]++;
    });
    const labels = bins.map((_, i) => (min + (i + 0.5) * binWidth).toFixed(2));
    const colors = labels.map(colorFn);

    return new Chart(canvas.getContext('2d'), {
        type: 'bar',
        data: {
            labels,
            datasets: [{
                label,
                data: bins,
                backgroundColor: colors,
                borderColor: colors.map(c => c.replace('0.6', '1')),
                borderWidth: 1,
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false },
                tooltip: tooltipTitle
                    ? { callbacks: { title: items => tooltipTitle(items[0].label) } }
                    : {},
            },
            scales: {
                x: { title: { display: !!xTitle, text: xTitle } },
                y: { title: { display: true, text: yTitle }, beginAtZero: true }
            }
        }
    });
}
