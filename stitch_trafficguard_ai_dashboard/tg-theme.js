/**
 * tg-theme.js — Shared theme manager for TrafficGuard AI
 * Loaded by every screen. Reads/writes localStorage('tg_theme').
 * The bootstrap snippet in each <head> has already applied the class;
 * this just wires up the toggle button and keeps the icon in sync.
 */
(function () {
  const KEY = 'tg_theme';

  function currentTheme() {
    return localStorage.getItem(KEY) || 'light';
  }

  function applyTheme(theme) {
    document.documentElement.className = theme;
    localStorage.setItem(KEY, theme);
    // Update every toggle icon on the page
    document.querySelectorAll('[data-theme-toggle]').forEach(function (btn) {
      var icon = btn.querySelector('.material-symbols-outlined');
      if (icon) icon.textContent = theme === 'dark' ? 'light_mode' : 'dark_mode';
    });
  }

  function toggle() {
    applyTheme(currentTheme() === 'dark' ? 'light' : 'dark');
  }

  // Wire up any button with data-theme-toggle attribute
  function wireButtons() {
    document.querySelectorAll('[data-theme-toggle]').forEach(function (btn) {
      // Set initial icon
      var icon = btn.querySelector('.material-symbols-outlined');
      if (icon) icon.textContent = currentTheme() === 'dark' ? 'light_mode' : 'dark_mode';
      // Only attach once
      if (!btn.dataset.themeWired) {
        btn.dataset.themeWired = '1';
        btn.addEventListener('click', toggle);
      }
    });
  }

  // Run after DOM is ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', wireButtons);
  } else {
    wireButtons();
  }

  // Expose for inline use
  window.TGTheme = { toggle: toggle, apply: applyTheme, current: currentTheme };
})();
