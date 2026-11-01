/** Pure glyph formatters shared by app primitives and the standalone theme catalog. */

/** @typedef {'dots'|'bars'|'brackets'|'spinner'|'wave'} StatusSignal */

/** @param {number|null|undefined} value @returns {number|null} */
function percentage(value) {
  return typeof value === 'number' && Number.isFinite(value) ? Math.max(0, Math.min(100, value)) : null;
}

/** @param {number} step @param {number} length */
function frame(step, length) {
  const safe = Number.isFinite(step) ? Math.floor(step) : 0;
  return ((safe % length) + length) % length;
}

/**
 * A determinate text bar or an unknown traveling segment. The caller owns time/state.
 * @param {number|null|undefined} value
 * @param {number} [step]
 * @param {boolean} [active]
 * @returns {string}
 */
export function linearProgress(value, step = 14, active = false) {
  const pct = percentage(value), cells = 26;
  if (pct !== null) {
    const filled = Math.round(pct / 100 * cells);
    return '[' + '#'.repeat(filled) + '·'.repeat(cells - filled) + ']';
  }
  const head = frame(step, cells);
  return '[' + Array.from({ length: cells }, (_, index) => active && frame(index - head, cells) < 5 ? '#' : '·').join('') + ']';
}

/**
 * A text-only ring, clockwise from twelve o'clock. Unknown work never invents a percentage.
 * @param {number|null|undefined} value
 * @param {number} [step]
 * @param {boolean} [active]
 * @returns {string}
 */
export function circularProgress(value, step = 14, active = false) {
  const pct = percentage(value);
  const width = 25, height = 13;
  const grid = Array.from({ length: height }, () => Array.from({ length: width }, () => ' '));
  /** @type {Array<{x:number,y:number}>} */
  const points = [];
  const seen = new Set();
  // Sample once clockwise; rounded coordinates form a fixed monospace ellipse.
  for (let index = 0; index < 72; index++) {
    const angle = index / 72 * Math.PI * 2 - Math.PI / 2;
    const x = Math.round(12 + Math.cos(angle) * 11), y = Math.round(6 + Math.sin(angle) * 5);
    const key = x + ':' + y;
    if (!seen.has(key)) { seen.add(key); points.push({ x, y }); }
  }
  const filled = pct === null ? 0 : Math.round(pct / 100 * points.length);
  const head = frame(step, points.length);
  points.forEach(({ x, y }, index) => {
    const lit = pct === null ? active && frame(index - head, points.length) < 7 : index < filled;
    grid[y][x] = lit ? '#' : '·';
  });
  if (pct !== null) {
    const label = Math.round(pct) + '%';
    const left = Math.floor((width - label.length) / 2);
    [...label].forEach((letter, index) => { grid[6][left + index] = letter; });
  }
  return grid.map(row => row.join('')).join('\n');
}

/** @param {StatusSignal} type @param {number} [step] @returns {string} */
export function statusSignal(type, step = 14) {
  const sequences = {
    dots: ['[·  ]', '[ · ]', '[  ·]', '[ · ]'],
    bars: ['[|  ]', '[|| ]', '[|||]', '[ ||]', '[  |]'],
    brackets: ['[:  ]', '[:: ]', '[:::]', '[ ::]', '[  :]'],
    // Same width as the settled glyphs. Rotation order is | / - \; index 2 is `|` so the frozen
    // first visible step (14) never reads as a settled `[ / ]` or `[ - ]`.
    spinner: ['[ - ]', '[ \\ ]', '[ | ]', '[ / ]'],
    wave: ['[~]']
  };
  const sequence = sequences[type] ?? sequences.dots;
  return sequence[frame(step, sequence.length)];
}

/** @typedef {'success'|'failed'|'blocked'|'canceled'|'info'} SettledSignal */

/**
 * Static glyph for a finished state: done, failed, needs permission/attention, canceled.
 * Settled states never rotate.
 * @param {SettledSignal} outcome @returns {string}
 */
export function settledSignal(outcome) {
  const glyphs = { success: '[ + ]', failed: '[ ! ]', blocked: '[ / ]', canceled: '[ - ]', info: '[ · ]' };
  return glyphs[outcome] ?? glyphs.info;
}
