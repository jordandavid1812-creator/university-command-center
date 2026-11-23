// Load the motion layer, deadline pop-ups and share cards (built from frontend/src/*.ts) from the same folder.
// Without JavaScript, or if they fail to load, every page still shows everything.
const siteScript = document.currentScript;
if (siteScript instanceof HTMLScriptElement && siteScript.src) {
  for (const name of ['app.js', 'reminders.js', 'share.js']) import(new URL(name, siteScript.src).href).catch(() => {});
}

// Progressive feedback only. Every form remains functional without JavaScript.
// No grades, credentials or ownership data are copied into browser storage.
document.addEventListener('submit', (event) => {
  const form = event.target;
  if (!(form instanceof HTMLFormElement) || form.method.toLowerCase() !== 'post' || event.defaultPrevented) return;
  if (form.getAttribute('aria-busy') === 'true') {
    event.preventDefault();
    return;
  }
  form.setAttribute('aria-busy', 'true');
  form.querySelectorAll('button[type="submit"],button:not([type])').forEach((button) => {
    if (!button.disabled) {
      button.dataset.busyOriginal = button.textContent;
      button.disabled = true;
      button.textContent = 'Working…';
    }
  });
  const status = document.createElement('span');
  status.className = 'sr-only';
  status.dataset.busyStatus = 'true';
  status.setAttribute('role', 'status');
  status.textContent = 'Your request is being processed.';
  form.appendChild(status);
});

// Restore controls after browser back/forward cache navigation.
window.addEventListener('pageshow', () => {
  document.querySelectorAll('[data-busy-original]').forEach((button) => {
    button.textContent = button.dataset.busyOriginal;
    button.disabled = false;
    delete button.dataset.busyOriginal;
  });
  document.querySelectorAll('form[aria-busy]').forEach((form) => form.removeAttribute('aria-busy'));
  document.querySelectorAll('[data-busy-status]').forEach((status) => status.remove());
});

// Server-rendered errors stay readable without JavaScript. Move keyboard focus
// only after a failed submission; never move focus on successful GET navigation.
window.addEventListener('DOMContentLoaded', () => {
  document.querySelector('#error-summary')?.focus();
});

// Print buttons (hidden until this script runs; without JavaScript the page explains Ctrl+P).
document.querySelectorAll('[data-print]').forEach((button) => {
  button.hidden = false;
  button.addEventListener('click', () => window.print());
});
// "Download PDF" opens the summary with ?save=pdf: open the save window once, after it has loaded.
if (document.querySelector('[data-print]') && new URLSearchParams(location.search).get('save') === 'pdf') {
  window.addEventListener('load', () => window.setTimeout(() => window.print(), 300), { once: true });
}
