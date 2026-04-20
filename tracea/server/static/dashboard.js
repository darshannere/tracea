/* dashboard.js — tracea dashboard entry point */

(function () {
    'use strict';

    // ============================================================
    // Config (injected by server via window.TRACEA_RCA_BACKEND)
    // ============================================================
    var RCA_BACKEND = window.TRACEA_RCA_BACKEND || 'disabled';

    // ============================================================
    // Auth check (placeholder — auth is handled server-side)
    // ============================================================
    async function checkAuth() {
        // TODO: Implement auth check when auth is wired
        return true;
    }

    // ============================================================
    // Warning banner: renders when RCA backend is a cloud LLM
    // ============================================================
    function renderRCAWarningBannerIfNeeded() {
        if (RCA_BACKEND !== 'openai' && RCA_BACKEND !== 'anthropic') {
            return;  // No banner for disabled or ollama
        }

        var banner = document.createElement('div');
        banner.id = 'rca-warning-banner';
        banner.style.cssText = [
            'position: fixed',
            'top: 0',
            'left: 0',
            'right: 0',
            'z-index: 9999',
            'background: "#F59E0B"',
            'color: "#0F172A"',
            'padding: "12px 16px"',
            'display: "flex"',
            'align-items: "center"',
            'gap: 8px',
            'font-family: system-ui, sans-serif',
            'font-size: 14px',
            'font-weight: 400',
            'line-height: 1.4',
            'box-sizing: border-box',
        ].join('; ');

        var icon = document.createElement('span');
        icon.innerHTML = '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>';
        icon.style.display = 'flex';
        icon.style.flexShrink = '0';

        var text = document.createElement('span');
        text.textContent = 'Cloud RCA Active — Using ' + RCA_BACKEND + ' for root-cause analysis. Prompt content may be sent to a third-party LLM. Set TRACEA_RCA_BACKEND=disabled to disable.';

        banner.appendChild(icon);
        banner.appendChild(text);
        document.body.insertBefore(banner, document.body.firstChild);
    }

    // ============================================================
    // Init on DOM ready
    // ============================================================
    document.addEventListener('DOMContentLoaded', async function () {
        await checkAuth();
        renderRCAWarningBannerIfNeeded();
        // TODO: Load dashboard data and render charts (Phase 5)
    });

    // Expose for testing
    window._tracea = {
        renderRCAWarningBannerIfNeeded: renderRCAWarningBannerIfNeeded,
    };
})();