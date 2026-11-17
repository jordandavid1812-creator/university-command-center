// AI study pages only. Progressive enhancement: every page works without this file.
// AI-generated text is only ever inserted with textContent, never as HTML.
// Nothing is stored in the browser and no request is made except the Send form's own POST.
(() => {
  'use strict';
  const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  const el = (tag, attributes = {}, text = '') => {
    const node = document.createElement(tag);
    Object.entries(attributes).forEach(([name, value]) => node.setAttribute(name, value));
    if (text) node.textContent = text;
    return node;
  };
  const animate = (node, frames, options) => {
    if (!reduceMotion && node.animate) node.animate(frames, { easing: 'cubic-bezier(.2,.7,.2,1)', fill: 'both', ...options });
  };
  const announce = (() => {
    let region;
    return (message) => {
      if (!region) {
        region = el('p', { class: 'sr-only', role: 'status', 'aria-live': 'polite' });
        document.body.appendChild(region);
      }
      region.textContent = '';
      window.setTimeout(() => { region.textContent = message; }, 50);
    };
  })();

  // Gentle staggered entrance. Content is visible without JavaScript and if animations are off.
  const reveal = () => {
    document.querySelectorAll('[data-ai-reveal]').forEach((node, index) => {
      animate(node, [{ opacity: 0, transform: 'translateY(12px)' }, { opacity: 1, transform: 'none' }],
        { duration: 420, delay: Math.min(index, 12) * 60 });
    });
  };

  // Show a waiting animation once a Send button is pressed (site.js already prevents repeats).
  const waitOnSend = () => {
    document.querySelectorAll('form[data-ai-send]').forEach((form) => {
      form.addEventListener('submit', () => {
        const wait = document.querySelector('[data-ai-wait]');
        if (wait) wait.hidden = false;
        // One request at a time: the other provider's button stops too.
        document.querySelectorAll('form[data-ai-send] button').forEach((button) => { button.disabled = true; });
      });
    });
  };

  // --- Confetti for a perfect quiz (decorative, skipped when motion is reduced) ---
  const confetti = () => {
    if (reduceMotion) return;
    const canvas = el('canvas', { 'aria-hidden': 'true' });
    Object.assign(canvas.style, { position: 'fixed', inset: '0', width: '100%', height: '100%', pointerEvents: 'none', zIndex: '50' });
    document.body.appendChild(canvas);
    const context = canvas.getContext('2d');
    if (!context) { canvas.remove(); return; }
    canvas.width = window.innerWidth;
    canvas.height = window.innerHeight;
    const colours = ['#176B5B', '#E8B75C', '#254C87', '#A52839', '#146344'];
    const pieces = Array.from({ length: 140 }, () => ({
      x: Math.random() * canvas.width, y: -20 - Math.random() * canvas.height * 0.4,
      vx: (Math.random() - 0.5) * 4, vy: 2 + Math.random() * 4, size: 5 + Math.random() * 6,
      spin: Math.random() * Math.PI, colour: colours[Math.floor(Math.random() * colours.length)],
    }));
    const started = performance.now();
    const frame = (now) => {
      context.clearRect(0, 0, canvas.width, canvas.height);
      pieces.forEach((piece) => {
        piece.x += piece.vx; piece.y += piece.vy; piece.vy += 0.05; piece.spin += 0.1;
        context.save();
        context.translate(piece.x, piece.y);
        context.rotate(piece.spin);
        context.fillStyle = piece.colour;
        context.fillRect(-piece.size / 2, -piece.size / 4, piece.size, piece.size / 2);
        context.restore();
      });
      if (now - started < 3200) window.requestAnimationFrame(frame); else canvas.remove();
    };
    window.requestAnimationFrame(frame);
  };

  const countUp = (node, target, total) => {
    if (reduceMotion) { node.textContent = `${target} / ${total}`; return; }
    const started = performance.now();
    const step = (now) => {
      const progress = Math.min(1, (now - started) / 900);
      node.textContent = `${Math.round(target * (1 - Math.pow(1 - progress, 3)))} / ${total}`;
      if (progress < 1) window.requestAnimationFrame(step);
    };
    window.requestAnimationFrame(step);
  };

  // --- Interactive quiz ---
  const quiz = (root) => {
    const questions = Array.from(root.querySelectorAll('.ai-question'));
    if (!questions.length) return;
    root.classList.add('ai-js');
    const bar = el('div', { class: 'ai-score' });
    const label = el('span', {}, `Score 0 / ${questions.length}`);
    const progress = el('div', { class: 'ai-progress', role: 'progressbar', 'aria-valuemin': '0',
      'aria-valuemax': String(questions.length), 'aria-valuenow': '0', 'aria-label': 'Questions answered' });
    const fill = el('span');
    progress.appendChild(fill);
    bar.append(label, progress);
    root.prepend(bar);
    const final = el('div', { class: 'ai-final', hidden: '' });
    root.appendChild(final);
    let answered = 0;
    let score = 0;

    const finish = () => {
      final.replaceChildren();
      const number = el('strong');
      final.append(el('p', {}, 'Quiz complete'), number,
        el('p', {}, score === questions.length ? 'Perfect score. Brilliant work!' :
          score >= questions.length / 2 ? 'Good effort. Review the ones you missed.' : 'Keep practising. Read the reasons and try again.'));
      const again = el('button', { class: 'button', type: 'button' }, 'Try again');
      again.addEventListener('click', reset);
      final.appendChild(again);
      final.hidden = false;
      animate(final, [{ opacity: 0, transform: 'scale(.94)' }, { opacity: 1, transform: 'none' }], { duration: 450 });
      countUp(number, score, questions.length);
      announce(`Quiz complete. You scored ${score} out of ${questions.length}.`);
      if (score === questions.length) confetti();
      final.scrollIntoView({ behavior: reduceMotion ? 'auto' : 'smooth', block: 'center' });
    };

    const update = () => {
      label.textContent = `Score ${score} / ${questions.length}`;
      progress.setAttribute('aria-valuenow', String(answered));
      fill.style.width = `${(answered / questions.length) * 100}%`;
    };

    const choose = (question, button) => {
      const correct = Number(question.dataset.correct);
      const chosen = Number(button.dataset.index);
      const buttons = Array.from(question.querySelectorAll('.ai-option'));
      buttons.forEach((option) => { option.disabled = true; });
      buttons[correct].dataset.state = 'right';
      const right = chosen === correct;
      if (!right) button.dataset.state = 'wrong';
      const reason = question.querySelector('.ai-reason');
      const feedback = question.querySelector('.ai-feedback');
      feedback.dataset.state = right ? 'right' : 'wrong';
      feedback.textContent = (right ? 'Correct! ' : `Not quite. The answer is ${'ABCD'[correct]}. `) + (reason ? reason.textContent : '');
      animate(feedback, [{ opacity: 0, transform: 'translateY(-4px)' }, { opacity: 1, transform: 'none' }], { duration: 300 });
      if (!right) animate(button, [{ transform: 'translateX(0)' }, { transform: 'translateX(-6px)' }, { transform: 'translateX(6px)' }, { transform: 'translateX(0)' }], { duration: 300 });
      else animate(button, [{ transform: 'scale(1)' }, { transform: 'scale(1.03)' }, { transform: 'scale(1)' }], { duration: 300 });
      announce(feedback.textContent);
      answered += 1;
      if (right) score += 1;
      update();
      if (answered === questions.length) window.setTimeout(finish, reduceMotion ? 0 : 500);
    };

    questions.forEach((question) => {
      const details = question.querySelector('.ai-answer');
      if (details) details.hidden = true;
      question.querySelectorAll('.ai-options li').forEach((item) => {
        const index = Number(item.dataset.index);
        const button = el('button', { class: 'ai-option', type: 'button', 'data-index': String(index) });
        button.append(el('strong', {}, `${'ABCD'[index]}. `), document.createTextNode(item.textContent));
        button.addEventListener('click', () => choose(question, button));
        item.replaceChildren(button);
      });
      question.appendChild(el('p', { class: 'ai-feedback', 'aria-hidden': 'true' }));
    });

    function reset() {
      answered = 0;
      score = 0;
      questions.forEach((question) => {
        question.querySelectorAll('.ai-option').forEach((option) => { option.disabled = false; delete option.dataset.state; });
        const feedback = question.querySelector('.ai-feedback');
        feedback.textContent = '';
        delete feedback.dataset.state;
      });
      final.hidden = true;
      update();
      questions[0].scrollIntoView({ behavior: reduceMotion ? 'auto' : 'smooth', block: 'start' });
      const first = questions[0].querySelector('.ai-option');
      if (first) first.focus({ preventScroll: true });
    }
    update();
  };

  // --- Flashcard deck ---
  const cards = (list) => {
    const all = Array.from(list.querySelectorAll('.ai-card')).map((item) => ({
      front: item.querySelector('.ai-card-front').textContent.trim(),
      back: item.querySelector('.ai-card-back').textContent.trim(),
    }));
    if (!all.length) return;
    let deck = all.slice();
    let position = 0;
    const known = new Set();
    const review = new Set();

    const root = el('div', { class: 'ai-deck', role: 'region', 'aria-label': 'Flashcard deck' });
    const flip = el('button', { class: 'ai-flip', type: 'button', 'aria-pressed': 'false' });
    const inner = el('span', { class: 'ai-flip-inner' });
    const front = el('span', { class: 'ai-face ai-face-front' });
    const back = el('span', { class: 'ai-face ai-face-back' });
    inner.append(front, back);
    flip.appendChild(inner);
    const count = el('p', { class: 'ai-deck-count', 'aria-live': 'polite' });
    const piles = el('p', { class: 'ai-piles' });
    const button = (text, handler) => {
      const node = el('button', { class: 'button secondary', type: 'button' }, text);
      node.addEventListener('click', handler);
      return node;
    };
    const controls = el('div', { class: 'ai-deck-bar' });
    const marks = el('div', { class: 'ai-deck-bar' });

    const show = (direction = 0) => {
      const card = deck[position];
      flip.setAttribute('aria-pressed', 'false');
      front.textContent = card.front;
      back.textContent = card.back;
      flip.setAttribute('aria-label', `Card ${position + 1}: ${card.front}. Press to flip.`);
      count.textContent = `Card ${position + 1} of ${deck.length}`;
      piles.textContent = `Known ${known.size} · Review again ${review.size}`;
      if (direction) animate(flip, [{ opacity: 0, transform: `translateX(${direction * 40}px)` }, { opacity: 1, transform: 'none' }], { duration: 320 });
    };
    const move = (step) => {
      position = (position + step + deck.length) % deck.length;
      show(step);
    };
    const mark = (set, other) => {
      const card = deck[position];
      set.add(card.front);
      other.delete(card.front);
      if (known.size === all.length) {
        piles.textContent = `Known ${known.size} · Review again 0`;
        announce('You know every card in this deck. Well done!');
        if (!reduceMotion) confetti();
      }
      move(1);
    };

    flip.addEventListener('click', () => {
      const turned = flip.getAttribute('aria-pressed') !== 'true';
      flip.setAttribute('aria-pressed', String(turned));
      announce(turned ? `Answer: ${deck[position].back}` : deck[position].front);
    });
    root.addEventListener('keydown', (event) => {
      if (event.key === 'ArrowRight') { move(1); event.preventDefault(); }
      if (event.key === 'ArrowLeft') { move(-1); event.preventDefault(); }
    });
    controls.append(button('← Previous', () => move(-1)), count, button('Next →', () => move(1)));
    marks.append(button('I know it', () => mark(known, review)), button('Review again', () => mark(review, known)),
      button('Shuffle', () => {
        for (let i = deck.length - 1; i > 0; i -= 1) {
          const j = Math.floor(Math.random() * (i + 1));
          [deck[i], deck[j]] = [deck[j], deck[i]];
        }
        position = 0;
        show(1);
        announce('Deck shuffled.');
      }),
      button('Study review pile', () => {
        const pile = all.filter((card) => review.has(card.front));
        if (!pile.length) { announce('Your review pile is empty.'); return; }
        deck = pile;
        position = 0;
        show(1);
        announce(`Studying ${pile.length} cards from your review pile.`);
      }),
      button('All cards', () => { deck = all.slice(); position = 0; show(1); }));
    root.append(flip, controls, marks, piles);
    list.hidden = true;
    list.after(root);
    show();
  };

  // --- Copy result ---
  const copy = (actions) => {
    const source = document.getElementById('ai-result-text');
    if (!source) return;
    // The Clipboard API needs a secure page (127.0.0.1 and localhost are); otherwise fall back.
    const write = async (text) => {
      if (navigator.clipboard && window.isSecureContext) return navigator.clipboard.writeText(text);
      const area = el('textarea', { readonly: '', 'aria-hidden': 'true' });
      area.value = text;
      Object.assign(area.style, { position: 'fixed', top: '-1000px', opacity: '0' });
      document.body.appendChild(area);
      area.select();
      const copied = document.execCommand('copy');
      area.remove();
      if (!copied) throw new Error('copy failed');
      return undefined;
    };
    const status = el('span', { class: 'ai-copied', role: 'status' });
    const button = el('button', { class: 'button', type: 'button' }, 'Copy');
    button.addEventListener('click', async () => {
      try {
        await write(source.content.textContent);
        status.textContent = 'Copied';
        animate(status, [{ opacity: 0 }, { opacity: 1 }], { duration: 200 });
      } catch (error) {
        status.textContent = 'Copy failed. Use Download as text instead.';
      }
      window.setTimeout(() => { status.textContent = ''; }, 2500);
    });
    actions.prepend(button);
    actions.appendChild(status);
  };

  // After the browser's Back button, the confirm page is usable again (site.js restores only
  // the buttons it disabled itself).
  window.addEventListener('pageshow', () => {
    document.querySelectorAll('form[data-ai-send] button').forEach((button) => { button.disabled = false; });
    const wait = document.querySelector('[data-ai-wait]');
    if (wait) wait.hidden = true;
  });

  // Printouts show every quiz answer.
  window.addEventListener('beforeprint', () => {
    document.querySelectorAll('.ai-answer').forEach((details) => { details.hidden = false; details.open = true; });
  });

  const start = () => {
    document.querySelectorAll('[data-ai-quiz]').forEach(quiz);
    document.querySelectorAll('[data-ai-cards]').forEach(cards);
    document.querySelectorAll('[data-ai-actions]').forEach(copy);
    waitOnSend();
    reveal();
  };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start); else start();
})();
