// Shareable result cards. Source: frontend/src/share.ts (compiled to share.js).
//
// - Owner's choice: a student can share a study-streak, CGPA or quiz-score card, for example to
//   WhatsApp status. The 1080x1920 picture is drawn in this browser on a canvas.
// - Nothing is stored and nothing is sent to UniCommand: the picture goes only where the student
//   sends it, through the phone's own share sheet (Web Share), or it is saved as a download.
// - No images or external files are loaded. Without JavaScript the share buttons stay hidden.

type Card = { emoji: string; headline: string; subline: string; file: string; text: string };

const WIDTH = 1080;
const HEIGHT = 1920;
const SITE = 'unicommand.com.ng';

function cardFor(kind: string, data: DOMStringMap): Card | null {
  if (kind === 'streak') {
    const days = Number(data.shareValue);
    const best = Number(data.shareBest);
    if (!Number.isInteger(days) || days < 1) return null;
    const bestLine = Number.isInteger(best) && best > days ? `My best is ${best} days. ` : '';
    return {
      emoji: '\u{1F525}', headline: `${days}-day study streak`,
      subline: `${bestLine}Studying every day with UniCommand.`, file: 'unicommand-streak.png',
      text: `I'm on a ${days}-day study streak on UniCommand \u{1F525}`,
    };
  }
  if (kind === 'cgpa') {
    const value = data.shareValue ?? '';
    const max = data.shareMax ?? '';
    if (!/^\d\.\d{2}$/.test(value) || !/^\d\.\d{2}$/.test(max)) return null;
    return {
      emoji: '\u{1F393}', headline: `${value} / ${max}`,
      subline: 'My CGPA so far. Tracking my road to the top with UniCommand.', file: 'unicommand-cgpa.png',
      text: `My CGPA is ${value} / ${max}. I track it on UniCommand \u{1F393}`,
    };
  }
  if (kind === 'quiz') {
    const score = Number(data.shareValue);
    const total = Number(data.shareTotal);
    if (!Number.isInteger(score) || !Number.isInteger(total) || total < 1 || score < 0 || score > total) return null;
    return {
      emoji: '\u{1F9E0}', headline: `I scored ${score}/${total}`,
      subline: 'on a practice quiz made from my own notes. Can you beat me?', file: 'unicommand-quiz.png',
      text: `I scored ${score}/${total} on a UniCommand practice quiz \u{1F9E0} Can you beat me?`,
    };
  }
  return null;
}

/** Breaks text into lines that fit the given width. */
function wrap(context: CanvasRenderingContext2D, text: string, width: number): string[] {
  const lines: string[] = [];
  let line = '';
  for (const word of text.split(' ')) {
    const next = line ? `${line} ${word}` : word;
    if (line && context.measureText(next).width > width) {
      lines.push(line);
      line = word;
    } else {
      line = next;
    }
  }
  if (line) lines.push(line);
  return lines;
}

function roundRect(context: CanvasRenderingContext2D, x: number, y: number, w: number, h: number, r: number): void {
  context.beginPath();
  context.moveTo(x + r, y);
  context.arcTo(x + w, y, x + w, y + h, r);
  context.arcTo(x + w, y + h, x, y + h, r);
  context.arcTo(x, y + h, x, y, r);
  context.arcTo(x, y, x + w, y, r);
  context.closePath();
}

/** Draws the card; returns the canvas, or null if this browser cannot draw. */
export function draw(card: Card): HTMLCanvasElement | null {
  const canvas = document.createElement('canvas');
  canvas.width = WIDTH;
  canvas.height = HEIGHT;
  const context = canvas.getContext('2d');
  if (!context) return null;
  const font = 'system-ui, -apple-system, "Segoe UI", Roboto, Arial, sans-serif';
  const background = context.createLinearGradient(0, 0, WIDTH, HEIGHT);
  background.addColorStop(0, '#0f4d40');
  background.addColorStop(0.55, '#176b5b');
  background.addColorStop(1, '#1f8a72');
  context.fillStyle = background;
  context.fillRect(0, 0, WIDTH, HEIGHT);
  // Soft circles for depth.
  context.fillStyle = 'rgba(255,255,255,0.06)';
  context.beginPath(); context.arc(980, 260, 300, 0, Math.PI * 2); context.fill();
  context.beginPath(); context.arc(80, 1650, 360, 0, Math.PI * 2); context.fill();

  // Brand.
  context.fillStyle = '#ffffff';
  roundRect(context, 90, 120, 120, 120, 28);
  context.fill();
  context.fillStyle = '#176b5b';
  context.font = `700 52px ${font}`;
  context.textAlign = 'center';
  context.textBaseline = 'middle';
  context.fillText('UC', 150, 182);
  context.textAlign = 'left';
  context.fillStyle = '#ffffff';
  context.font = `700 56px ${font}`;
  context.fillText('UniCommand', 240, 182);

  // Emoji, headline, subline.
  context.textAlign = 'center';
  context.font = `260px ${font}`;
  context.fillText(card.emoji, WIDTH / 2, 640);
  context.font = `800 112px ${font}`;
  let y = 900;
  for (const line of wrap(context, card.headline, 900)) {
    context.fillText(line, WIDTH / 2, y);
    y += 128;
  }
  context.fillStyle = '#d7f3ea';
  context.font = `500 54px ${font}`;
  y += 30;
  for (const line of wrap(context, card.subline, 860)) {
    context.fillText(line, WIDTH / 2, y);
    y += 74;
  }

  // Call to action.
  context.fillStyle = '#e8b75c';
  roundRect(context, 190, 1560, 700, 130, 65);
  context.fill();
  context.fillStyle = '#1d1a0e';
  context.font = `800 58px ${font}`;
  context.fillText(SITE, WIDTH / 2, 1626);
  context.fillStyle = '#d7f3ea';
  context.font = `500 40px ${font}`;
  context.fillText('Free for students · GPA, deadlines & AI study tools', WIDTH / 2, 1780, 960);
  return canvas;
}

function say(button: HTMLElement, message: string): void {
  let status = button.parentElement?.querySelector<HTMLElement>('[data-share-status]');
  if (!status) {
    status = document.createElement('span');
    status.className = 'share-status muted';
    status.setAttribute('role', 'status');
    status.setAttribute('data-share-status', '');
    button.after(status);
  }
  status.textContent = message;
}

async function share(button: HTMLButtonElement): Promise<void> {
  const card = cardFor(button.dataset.shareCard ?? '', button.dataset);
  const canvas = card ? draw(card) : null;
  if (!card || !canvas) { say(button, 'Sharing is not available in this browser.'); return; }
  const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, 'image/png'));
  if (!blob) { say(button, 'Sharing is not available in this browser.'); return; }
  const file = new File([blob], card.file, { type: 'image/png' });
  const text = `${card.text} https://${SITE}`;
  if (navigator.canShare && navigator.canShare({ files: [file] })) {
    try {
      await navigator.share({ files: [file], text });
      say(button, 'Shared!');
    } catch (error) {
      if (!(error instanceof DOMException && error.name === 'AbortError')) say(button, 'Could not share. Try again.');
    }
    return;
  }
  // No share sheet (most computers): save the picture instead.
  const link = document.createElement('a');
  link.href = URL.createObjectURL(blob);
  link.download = card.file;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(link.href), 10_000);
  say(button, 'Picture saved. Post it to your WhatsApp status or anywhere you like.');
}

function activate(button: HTMLButtonElement): void {
  if (button.dataset.shareReady) return;
  button.dataset.shareReady = '1';
  button.hidden = false;
  button.addEventListener('click', () => { void share(button); });
}

function start(): void {
  document.querySelectorAll<HTMLButtonElement>('button[data-share-card]').forEach(activate);
  // The interactive quiz (ai.js) announces its result; offer a share button under it.
  document.addEventListener('ucc:quiz-finished', (event) => {
    const detail = (event as CustomEvent<{ score: number; total: number }>).detail;
    const final = event.target;
    if (!(final instanceof HTMLElement) || !detail) return;
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'button secondary';
    button.textContent = '\u{1F4F8} Share my score';
    button.dataset.shareCard = 'quiz';
    button.dataset.shareValue = String(detail.score);
    button.dataset.shareTotal = String(detail.total);
    final.appendChild(button);
    activate(button);
  });
}

if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start); else start();
