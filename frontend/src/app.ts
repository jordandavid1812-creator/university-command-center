// Motion layer for the student website. Source: frontend/src/app.ts (compiled to app.js).
//
// Rules this file keeps:
// - Every page works and shows all content without JavaScript. Nothing starts hidden in
//   the HTML or CSS; this script hides an element only just before it animates it in.
// - "Reduce motion" in the device settings turns all of this off.
// - Numbers are never changed in the page text. The count-up is drawn on top of the real
//   value as CSS generated content, so screen readers, copy and tests see the true number.
// - Nothing is stored and nothing is sent anywhere.

const REVEAL = [
  '.main-content > .page-heading', '.main-content > .notice', '.panel', '.metric', '.ai-tool-card',
  '.standing-chart', '.dashboard-attention', '.ai-question', '.ai-deck', '.table-scroll', '.empty-state',
].join(',');
const COUNTERS = '.metric strong, .dashboard-gpa strong, .standing-result';
const RIPPLE = '.button, button, .main-content a, .public-nav a';
const EASE = 'cubic-bezier(.2,.75,.2,1)';

const root = document.documentElement;
const calm = window.matchMedia('(prefers-reduced-motion: reduce)');
const finePointer = window.matchMedia('(hover: hover) and (pointer: fine)');

function inView(element: Element): boolean {
  const box = element.getBoundingClientRect();
  return box.top < window.innerHeight && box.bottom > 0;
}

/** Shows an element at once, cancelling any animation still running on it. */
function settle(element: HTMLElement): void {
  element.removeAttribute('data-reveal');
  element.getAnimations().forEach((animation) => animation.finish());
}

/** Slides and fades one element in. `delay` staggers neighbours. */
function enter(element: HTMLElement, delay: number): void {
  element.removeAttribute('data-reveal');
  element.animate(
    [{ opacity: 0, transform: 'translateY(22px) scale(.985)' }, { opacity: 1, transform: 'none' }],
    { duration: 620, delay, easing: EASE, fill: 'backwards' },
  );
  startCounters(element);
  growChart(element);
}

/** Position among visible siblings that animate together, for a gentle stagger. */
function staggerIndex(element: Element, group: Element[]): number {
  return Math.min(group.indexOf(element), 6);
}

/** Finishes every entrance, count-up and chart animation now (used before printing). */
function finishAll(): void {
  document.querySelectorAll<HTMLElement>('[data-reveal]').forEach(settle);
  document.querySelectorAll<HTMLElement>('.ucc-counting').forEach(stopCount);
  document.getAnimations().forEach((animation) => {
    // Endless animations (such as a waiting spinner) cannot be finished; leave them alone.
    if (animation.effect?.getComputedTiming().endTime !== Infinity) animation.finish();
  });
}

/** True when this page load should not replay entrance motion: an automatic refresh
 *  (the AI "still working" page reloads every few seconds), a reload, or Back/Forward. */
function quietEntrance(): boolean {
  if (document.querySelector('meta[http-equiv="refresh" i]')) return true;
  const navigation = performance.getEntriesByType('navigation')[0] as PerformanceNavigationTiming | undefined;
  return navigation?.type === 'reload' || navigation?.type === 'back_forward';
}

function setUpReveals(): void {
  window.addEventListener('beforeprint', finishAll);
  if (quietEntrance()) return;
  const focused = document.activeElement;
  const targets = Array.from(document.querySelectorAll<HTMLElement>(REVEAL))
    // Skip anything not on screen at all (hidden, or inside a closed section), cards inside
    // another animated card (they move with it), AI page parts that ai.js already animates,
    // and whatever holds keyboard focus right now.
    .filter((element) => element.getClientRects().length > 0 && !element.parentElement?.closest(REVEAL)
      && !element.closest('[data-ai-reveal]') && !(focused && focused !== document.body && element.contains(focused)));
  const first = targets.filter(inView);
  first.forEach((element) => enter(element, 80 + staggerIndex(element, first) * 70));
  const later = targets.filter((element) => !first.includes(element));
  if (!('IntersectionObserver' in window) || later.length === 0) {
    later.forEach((element) => { startCounters(element); growChart(element); });
    return;
  }
  const observer = new IntersectionObserver((entries) => {
    const arriving = entries.filter((entry) => entry.isIntersecting).map((entry) => entry.target as HTMLElement);
    arriving.forEach((element, index) => {
      observer.unobserve(element);
      enter(element, index * 80);
    });
    // Threshold 0 and no margin: any visible pixel counts, so a section many screens tall, or a
    // small one at the very bottom of the page, always appears.
  }, { threshold: 0 });
  later.forEach((element) => {
    element.setAttribute('data-reveal', 'waiting');
    observer.observe(element);
  });
  // Never leave anything hidden when it is needed: keyboard focus and links to a section show
  // it straight away, printing finishes everything (see finishAll), and a find-in-page jump
  // scrolls the section into view, which starts its entrance.
  const showAll = (): void => {
    document.querySelectorAll<HTMLElement>('[data-reveal]').forEach(settle);
    observer.disconnect();
  };
  document.addEventListener('focusin', (event) => {
    const holder = (event.target as Element).closest<HTMLElement>('[data-reveal]');
    if (holder) { observer.unobserve(holder); settle(holder); startCounters(holder); growChart(holder); }
  });
  window.addEventListener('hashchange', showAll);
  window.addEventListener('beforeprint', () => observer.disconnect());
  if (location.hash) showAll();
}

/** Counts a number up from zero, drawn over the real text, which never changes. */
function countUp(element: HTMLElement): void {
  if (element.dataset.counted) return;
  element.dataset.counted = 'true';
  // Only plain numbers such as 12 or 3.78; anything else is left exactly as it is.
  const match = /^\s*(\d{1,6})(?:\.(\d{1,4}))?\s*$/.exec(element.textContent ?? '');
  if (!match || element.children.length > 0) return;
  const places = match[2]?.length ?? 0;
  const target = Number(`${match[1]}${places ? `.${match[2]}` : ''}`);
  if (!Number.isFinite(target) || target === 0) return;
  // The moving number is CSS generated content, so it is never part of the page text.
  element.style.setProperty('--ucc-ink', getComputedStyle(element).color);
  element.classList.add('ucc-counting');
  element.dataset.countNow = (0).toFixed(places);
  const started = performance.now();
  const duration = 900;
  const frame = (now: number): void => {
    if (!element.classList.contains('ucc-counting')) return; // stopped early (printing)
    const progress = Math.min((now - started) / duration, 1);
    const eased = 1 - Math.pow(1 - progress, 3);
    element.dataset.countNow = (target * eased).toFixed(places);
    if (progress < 1) {
      requestAnimationFrame(frame);
    } else {
      stopCount(element);
    }
  };
  requestAnimationFrame(frame);
}

/** Ends a count-up and shows the real number again. */
function stopCount(element: HTMLElement): void {
  element.classList.remove('ucc-counting');
  delete element.dataset.countNow;
  element.style.removeProperty('--ucc-ink');
}

function startCounters(scope: HTMLElement): void {
  if (scope.matches(COUNTERS)) countUp(scope);
  scope.querySelectorAll<HTMLElement>(COUNTERS).forEach(countUp);
}

/** Grows the semester bars from the baseline and draws the CGPA line across. */
function growChart(scope: HTMLElement): void {
  scope.querySelectorAll<SVGPathElement>('.standing-bar path').forEach((bar, index) => {
    bar.animate([{ transform: 'scaleY(0)' }, { transform: 'scaleY(1)' }],
      { duration: 700, delay: 150 + index * 90, easing: EASE, fill: 'backwards' });
  });
  scope.querySelectorAll<SVGLineElement>('.standing-cgpa').forEach((line) => {
    // Grows from the left; the line keeps its own dash pattern throughout.
    line.animate([{ transform: 'scaleX(0)' }, { transform: 'scaleX(1)' }],
      { duration: 900, delay: 400, easing: EASE, fill: 'backwards' });
  });
}

/** A thin bar at the top of the window that fills as you scroll down the page. */
function setUpProgress(): void {
  const bar = document.createElement('div');
  bar.className = 'ucc-progress';
  bar.setAttribute('aria-hidden', 'true');
  document.body.append(bar);
  let queued = false;
  const update = (): void => {
    queued = false;
    const room = document.documentElement.scrollHeight - window.innerHeight;
    const share = room > 0 ? Math.min(window.scrollY / room, 1) : 0;
    bar.style.transform = `scaleX(${share})`;
    bar.classList.toggle('is-active', room > 40);
  };
  const queue = (): void => {
    if (!queued) { queued = true; requestAnimationFrame(update); }
  };
  window.addEventListener('scroll', queue, { passive: true });
  window.addEventListener('resize', queue);
  update();
}

/** A soft highlight that glides between menu items as the pointer or keyboard moves. */
function setUpMenuGlide(): void {
  document.querySelectorAll<HTMLElement>('.sidebar nav').forEach((nav) => {
    const glide = document.createElement('span');
    glide.className = 'ucc-glide';
    glide.setAttribute('aria-hidden', 'true');
    nav.prepend(glide);
    nav.classList.add('has-glide');
    const moveTo = (link: HTMLElement | null): void => {
      if (!link) { glide.style.opacity = '0'; return; }
      glide.style.opacity = '1';
      glide.style.transform = `translateY(${link.offsetTop}px)`;
      glide.style.height = `${link.offsetHeight}px`;
    };
    const home = (): void => moveTo(nav.querySelector<HTMLElement>('.nav-link.active'));
    nav.addEventListener('pointerover', (event) => moveTo((event.target as Element).closest<HTMLElement>('.nav-link')));
    nav.addEventListener('focusin', (event) => moveTo((event.target as Element).closest<HTMLElement>('.nav-link')));
    nav.addEventListener('pointerleave', home);
    nav.addEventListener('focusout', () => setTimeout(() => { if (!nav.contains(document.activeElement)) home(); }));
    window.addEventListener('resize', home);
    home();
  });
}

/** A ripple from the exact spot a button is pressed. */
function setUpRipples(): void {
  document.addEventListener('pointerdown', (event) => {
    const control = (event.target as Element).closest<HTMLElement>(RIPPLE);
    if (!control || (control as HTMLButtonElement).disabled || control.closest('.ai-flip')) return;
    const box = control.getBoundingClientRect();
    const size = Math.max(box.width, box.height) * 2.2;
    const ripple = document.createElement('span');
    ripple.className = 'ucc-ripple';
    ripple.setAttribute('aria-hidden', 'true');
    ripple.style.width = ripple.style.height = `${size}px`;
    ripple.style.left = `${event.clientX - box.left - size / 2}px`;
    ripple.style.top = `${event.clientY - box.top - size / 2}px`;
    control.classList.add('has-ripple');
    control.append(ripple);
    ripple.animate([{ transform: 'scale(0)', opacity: 0.35 }, { transform: 'scale(1)', opacity: 0 }],
      { duration: 650, easing: 'ease-out' }).finished.then(() => ripple.remove(), () => ripple.remove());
  });
}

/** Cards light up softly under the mouse pointer (mouse and trackpad only). */
function setUpSpotlight(): void {
  if (!finePointer.matches) return;
  document.addEventListener('pointermove', (event) => {
    const card = (event.target as Element).closest<HTMLElement>('.panel, .metric, .ai-tool-card');
    if (!card) return;
    const box = card.getBoundingClientRect();
    card.style.setProperty('--ucc-x', `${event.clientX - box.left}px`);
    card.style.setProperty('--ucc-y', `${event.clientY - box.top}px`);
  }, { passive: true });
}

function start(): void {
  if (calm.matches) {
    root.classList.add('ucc-calm');
    return;
  }
  root.classList.add('ucc-motion');
  setUpReveals();
  setUpProgress();
  setUpMenuGlide();
  setUpRipples();
  setUpSpotlight();
}

// If the setting changes while a page is open, stop at once: show everything as it is.
calm.addEventListener('change', () => {
  if (!calm.matches) return;
  root.classList.replace('ucc-motion', 'ucc-calm');
  finishAll();
});

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', start);
} else {
  start();
}

export {};
