/**
 * Number / percent formatting and verdict-badge helpers shared by the
 * dashboard pages.
 */

// --- strategy.html formatters ----------------------------------------

function formatCurrency(value) {
    if (value === null || value === undefined) return '—';
    const num = parseFloat(value);
    if (isNaN(num)) return '—';
    return '£' + num.toLocaleString('en-GB', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function formatMetric(key, value) {
    if (value === null || value === undefined) return '—';

    if (key.toLowerCase().includes('value') || key.toLowerCase().includes('cost') ||
        key.toLowerCase().includes('capital') || key.toLowerCase() === 'final_value') {
        return formatCurrency(value);
    }

    const k = key.toLowerCase();
    const num = parseFloat(value);
    if (isNaN(num)) return String(value);

    // Always treat these as decimal fractions → multiply by 100
    if (k.includes('return') || k.includes('volatility') || k.includes('drawdown') || k === 'cagr') {
        return (num * 100).toFixed(2) + '%';
    }

    if (k.includes('sharpe') || k.includes('sortino') || k.includes('calmar') || k.includes('omega')) {
        return num.toFixed(3);
    }

    if (k.includes('transaction') || k.includes('rebalance') || k.includes('count')) {
        return Math.round(num);
    }

    return num.toFixed(2);
}

// --- overview.html formatter -------------------------------------------

function fmt(val, isPercent) {
    if (val === null || val === undefined) return '—';
    const n = parseFloat(val);
    if (isNaN(n)) return '—';
    if (isPercent) return (n * 100).toFixed(2) + '%';
    return n.toFixed(3);
}

// --- HTML escaping for innerHTML interpolation ---------------------------

function escHtml(s) {
    if (s === null || s === undefined) return '';
    return String(s)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

// --- verdict badge (PASS / WARN / FAIL -> CSS class) --------------------

function verdictBadge(verdict) {
    return `<span class="verdict-badge verdict-${verdict}">${verdict}</span>`;
}
