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
