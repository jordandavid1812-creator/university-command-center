// Deadline pop-ups. Source: frontend/src/reminders.ts (compiled to reminders.js).
//
// - Off until the student turns them on in Settings and the browser allows notifications.
// - At most one pop-up a day, when the dashboard is opened, and only if something is due today
//   or tomorrow. It shows counts only (never titles), so nothing private appears on a lock screen.
// - Browser storage holds only "on" and the date of the last pop-up: no titles, grades or ids.
// - Without JavaScript nothing changes: the dashboard's "Due this week" section still works.

const PREFERENCE = 'ucc-reminders';
const LAST_SHOWN = 'ucc-reminded-on';
const supported = 'Notification' in window;

function read(key: string): string | null {
  try { return window.localStorage.getItem(key); } catch { return null; }
}

function write(key: string, value: string | null): void {
  try {
    if (value === null) window.localStorage.removeItem(key); else window.localStorage.setItem(key, value);
  } catch { /* storage blocked: pop-ups simply stay off */ }
}

function isOn(): boolean {
  return supported && Notification.permission === 'granted' && read(PREFERENCE) === 'on';
}

/** The Settings switch. */
function setUpSettings(): void {
  const box = document.querySelector<HTMLElement>('[data-reminders]');
  const status = document.querySelector<HTMLElement>('[data-reminders-status]');
  const turnOn = document.querySelector<HTMLButtonElement>('[data-reminders-on]');
  const turnOff = document.querySelector<HTMLButtonElement>('[data-reminders-off]');
  if (!box || !status || !turnOn || !turnOff) return;
  if (!supported) {
    status.textContent = 'This browser cannot show pop-ups. The dashboard still lists what is due this week.';
    return;
  }
  const show = (): void => {
    box.hidden = false;
    turnOn.hidden = isOn();
    turnOff.hidden = !isOn();
    status.textContent = Notification.permission === 'denied'
      ? 'Pop-ups are blocked for this site in your browser settings. Allow notifications there, then turn them on here.'
      : isOn() ? 'Pop-ups are on in this browser.' : 'Pop-ups are off in this browser.';
  };
  turnOn.addEventListener('click', () => {
    Notification.requestPermission().then((answer) => {
      if (answer === 'granted') write(PREFERENCE, 'on');
      show();
    }, show);
  });
  turnOff.addEventListener('click', () => { write(PREFERENCE, null); show(); });
  show();
}

interface DueSoon { date: string; today: number; tomorrow: number; week: number }

function counts(): DueSoon | null {
  const element = document.getElementById('ucc-due-soon');
  if (!element) return null;
  try {
    const data = JSON.parse(element.textContent ?? '') as DueSoon;
    const whole = (value: unknown): boolean => Number.isInteger(value) && (value as number) >= 0;
    if (/^\d{4}-\d{2}-\d{2}$/.test(data.date) && whole(data.today) && whole(data.tomorrow) && whole(data.week)) {
      return data;
    }
  } catch { /* not shown */ }
  return null;
}

function plural(count: number): string {
  return `${count} assignment${count === 1 ? '' : 's'}`;
}

/** Once a day, on the dashboard: "2 assignments due today · 1 assignment due tomorrow". */
function remind(): void {
  const due = counts();
  if (!due || !isOn() || read(LAST_SHOWN) === due.date || due.today + due.tomorrow === 0) return;
  const parts = [];
  if (due.today) parts.push(`${plural(due.today)} due today`);
  if (due.tomorrow) parts.push(`${plural(due.tomorrow)} due tomorrow`);
  new Notification('UniCommand', { body: parts.join(' · '), tag: 'ucc-deadlines' });
  write(LAST_SHOWN, due.date);
}

function start(): void {
  setUpSettings();
  remind();
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', start);
} else {
  start();
}

export {};
