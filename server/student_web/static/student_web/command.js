"use strict";
// Command Centre (dashboard). Source: frontend/src/command.ts (compiled to command.js).
//
// - "What if?": tap a grade for an ungraded course and see the CGPA, class and ladder move.
//   Worked out in this browser from numbers already on the page. Nothing is saved or sent.
// - Celebrations: finishing Today's mission, a new level or a streak milestone shows one short
//   moment (confetti and a gentle vibration where supported). The browser remembers only which
//   moments were shown (for example "mission-2026-11-27", "level-3"); never grades or names.
// - Without JavaScript the picker stays hidden and everything else is already on the page.
const STORE = 'ucc-celebrated';
const MILESTONES = [3, 7, 14, 30, 60, 100];
const reduceMotion = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches;
function readData() {
    const node = document.getElementById('ucc-whatif');
    if (!node?.textContent)
        return null;
    try {
        return JSON.parse(node.textContent);
    }
    catch {
        return null;
    }
}
/** The class for a CGPA: the highest band whose lowest CGPA it reaches. */
function classFor(cgpa, bands) {
    return [...bands].sort((a, b) => b.low - a.low).find((band) => cgpa + 1e-9 >= band.low) ?? null;
}
function setupWhatIf(root) {
    const data = readData();
    const panel = root.querySelector('[data-cc-whatif]');
    const number = root.querySelector('[data-cc-cgpa]');
    if (!data || !panel || !number)
        return;
    const badge = root.querySelector('[data-cc-badge]');
    const reset = root.querySelector('[data-cc-reset]');
    const pin = root.querySelector('.ladder-pin');
    const className = root.querySelector('.ladder-class');
    const next = root.querySelector('.ladder-next');
    const actual = { text: number.textContent ?? '', pin: pin?.style.left ?? '', name: className?.textContent ?? '',
        next: next ? [...next.childNodes].map((node) => node.cloneNode(true)) : [] };
    const picked = new Map();
    const toggle = root.querySelector('[data-cc-toggle]');
    if (toggle) {
        toggle.hidden = false;
        toggle.addEventListener('click', () => {
            const open = toggle.getAttribute('aria-expanded') !== 'true';
            toggle.setAttribute('aria-expanded', String(open));
            panel.hidden = !open;
            if (open)
                panel.querySelector('.cc-chip')?.focus();
        });
    }
    else {
        panel.hidden = false;
    }
    const render = () => {
        if (!picked.size) {
            number.textContent = actual.text;
            if (pin)
                pin.style.left = actual.pin;
            if (className)
                className.textContent = actual.name;
            if (next)
                next.replaceChildren(...actual.next.map((node) => node.cloneNode(true)));
            if (badge)
                badge.hidden = true;
            if (reset)
                reset.hidden = true;
            return;
        }
        let points = data.points;
        let units = data.units;
        for (const course of data.courses) {
            const grade = picked.get(course.code);
            if (grade === undefined)
                continue;
            points += (data.grades[grade] ?? 0) * course.units;
            units += course.units;
        }
        const cgpa = units > 0 ? points / units : 0;
        number.textContent = cgpa.toFixed(2);
        if (pin)
            pin.style.left = `${Math.min(100, (cgpa / data.max) * 100)}%`;
        const band = classFor(cgpa, data.bands);
        if (className)
            className.textContent = band ? band.name : 'Below the Pass band';
        if (next) {
            next.textContent = '';
            const strong = document.createElement('strong');
            strong.textContent = `With these grades your CGPA would be ${cgpa.toFixed(2)}.`;
            next.append(strong, ' This is only a what-if. Your saved grades have not changed.');
        }
        if (badge)
            badge.hidden = false;
        if (reset)
            reset.hidden = false;
    };
    panel.addEventListener('click', (event) => {
        const chip = event.target.closest('.cc-chip');
        if (!chip)
            return;
        const code = chip.dataset.code ?? '';
        const grade = chip.dataset.grade ?? '';
        const again = picked.get(code) === grade;
        panel.querySelectorAll(`.cc-chip[data-code="${CSS.escape(code)}"]`)
            .forEach((other) => other.setAttribute('aria-pressed', 'false'));
        if (again)
            picked.delete(code);
        else {
            picked.set(code, grade);
            chip.setAttribute('aria-pressed', 'true');
        }
        render();
    });
    reset?.addEventListener('click', () => {
        picked.clear();
        panel.querySelectorAll('.cc-chip').forEach((chip) => chip.setAttribute('aria-pressed', 'false'));
        render();
    });
}
function shown() {
    try {
        return new Set(JSON.parse(localStorage.getItem(STORE) ?? '[]'));
    }
    catch {
        return new Set();
    }
}
function remember(keys) {
    try {
        localStorage.setItem(STORE, JSON.stringify([...keys].slice(-40)));
    }
    catch { /* private mode: fine */ }
}
function confetti(canvas) {
    const context = canvas.getContext('2d');
    if (!context)
        return;
    const scale = window.devicePixelRatio || 1;
    canvas.width = innerWidth * scale;
    canvas.height = innerHeight * scale;
    context.scale(scale, scale);
    const colours = ['#E8B75C', '#C99A3C', '#FFFFFF', '#5E9F86', '#9CC6B4'];
    const pieces = Array.from({ length: 110 }, () => ({
        x: innerWidth / 2, y: innerHeight / 2.4, vx: (Math.random() - .5) * 13, vy: -Math.random() * 12 - 4,
        size: 5 + Math.random() * 6, spin: Math.random() * 6, colour: colours[Math.floor(Math.random() * colours.length)]
    }));
    const start = performance.now();
    const frame = (now) => {
        context.clearRect(0, 0, innerWidth, innerHeight);
        for (const p of pieces) {
            p.vy += .32;
            p.x += p.vx;
            p.y += p.vy;
            p.spin += .2;
            context.save();
            context.translate(p.x, p.y);
            context.rotate(p.spin);
            context.fillStyle = p.colour;
            context.fillRect(-p.size / 2, -p.size / 3, p.size, p.size * .66);
            context.restore();
        }
        if (now - start < 2600)
            requestAnimationFrame(frame);
        else
            context.clearRect(0, 0, innerWidth, innerHeight);
    };
    requestAnimationFrame(frame);
}
function celebrate(medal, title, text) {
    const previous = document.activeElement;
    const overlay = document.createElement('div');
    overlay.className = 'cc-celebrate';
    overlay.setAttribute('role', 'dialog');
    overlay.setAttribute('aria-modal', 'true');
    overlay.setAttribute('aria-labelledby', 'cc-celebrate-title');
    const canvas = document.createElement('canvas');
    const card = document.createElement('div');
    card.className = 'cc-celebrate-card';
    const icon = document.createElement('p');
    icon.className = 'cc-medal';
    icon.setAttribute('aria-hidden', 'true');
    icon.textContent = medal;
    const heading = document.createElement('h2');
    heading.id = 'cc-celebrate-title';
    heading.textContent = title;
    const body = document.createElement('p');
    body.textContent = text;
    const close = document.createElement('button');
    close.type = 'button';
    close.textContent = 'Keep going';
    card.append(icon, heading, body, close);
    overlay.append(canvas, card);
    document.body.append(overlay);
    const done = () => { overlay.remove(); document.removeEventListener('keydown', onKey); previous?.focus?.(); };
    const onKey = (event) => { if (event.key === 'Escape' || event.key === 'Tab') {
        event.preventDefault();
        if (event.key === 'Escape')
            done();
        else
            close.focus();
    } };
    close.addEventListener('click', done);
    overlay.addEventListener('click', (event) => { if (event.target === overlay)
        done(); });
    document.addEventListener('keydown', onKey);
    close.focus();
    if (!reduceMotion()) {
        confetti(canvas);
        try {
            navigator.vibrate?.([30, 50, 30]);
        }
        catch { /* not supported */ }
    }
}
function setupCelebrations(root) {
    if (!(Number(root.dataset.ccLevel) >= 1))
        return; // no Command Centre data: remember nothing
    const keys = shown();
    const firstVisit = !keys.size;
    const today = root.dataset.ccToday ?? '';
    const level = Number(root.dataset.ccLevel);
    const streak = Number(root.dataset.ccStreak);
    const done = Number(root.dataset.ccDone);
    const total = Number(root.dataset.ccTotal);
    const moments = [];
    if (Number.isInteger(level) && level > 1 && !keys.has(`level-${level}`)) {
        const name = root.querySelector('.cc-level-name')?.textContent ?? `Level ${level}`;
        moments.push([`level-${level}`, '\u{1F3C5}', 'You levelled up!', `${name}. Your effort is adding up.`]);
    }
    if (MILESTONES.includes(streak) && !keys.has(`streak-${streak}-${today}`)) {
        moments.push([`streak-${streak}-${today}`, '\u{1F525}', `${streak}-day streak!`, `${streak} days in a row. That is how First Class is built.`]);
    }
    if (total > 0 && done === total && !keys.has(`mission-${today}`)) {
        moments.push([`mission-${today}`, '\u{1F3AF}', 'Mission complete!', 'All three steps done today. See you tomorrow.']);
    }
    // The very first visit only records where you are, so nobody is congratulated for nothing.
    for (const [key] of moments)
        keys.add(key);
    if (firstVisit) {
        keys.add(`level-${level}`);
        remember(keys);
        return;
    }
    remember(keys);
    const best = moments[moments.length - 1];
    if (best)
        window.setTimeout(() => celebrate(best[1], best[2], best[3]), 500);
}
function start() {
    const root = document.querySelector('[data-cc]');
    if (!root)
        return;
    setupWhatIf(root);
    setupCelebrations(root);
}
if (document.readyState === 'loading')
    document.addEventListener('DOMContentLoaded', start);
else
    start();
