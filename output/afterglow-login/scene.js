/* Text-only scene: every visible mark is an upright glyph, never a drawn shape. */
(() => {
  'use strict';
  const root = document.querySelector('.afterglow-loading');
  if (!root) return;
  const canvas = root.querySelector('canvas');
  const ctx = canvas.getContext('2d', { alpha: false });
  const button = root.querySelector('button');
  if (!ctx) { button.hidden = true; return; }
  const reduceMotion = matchMedia('(prefers-reduced-motion: reduce)');
  const params = new URLSearchParams(location.search);
  const themes = ['afterglow', 'accent', 'violet', 'cyan', 'jade', 'pearl'];
  root.dataset.theme = themes.includes(params.get('theme')) ? params.get('theme') : 'afterglow';
  const preview = params.get('preview') === '1';
  if (preview) root.classList.add('is-preview');
  const terms = ['OpenStack', 'Afterglow', 'Nova', 'Neutron', 'Cinder', 'Glance',
    'Keystone', 'Placement', 'Ceph', 'Swift', 'Manila', 'Octavia', 'Heat', 'Trove',
    'Palimpsest', 'Drover', 'Lumen', 'Waygate', 'KVM', 'cloud-init', 'vCPU', 'RAM',
    'volume', 'subnet', 'flavor', 'snapshot', 'project', 'image'];
  const density = '.:;+=*#%@';
  const noise = (n) => { const x = Math.sin(n * 127.1 + 311.7) * 43758.5453; return x - Math.floor(x); };
  const rgba = (color, alpha) => `rgb(${color} / ${alpha})`;
  let width = 0, height = 0, scale = 1, cellX = 8, cellY = 12, columns = [], palette;
  let frame = 0, last = 0, elapsed = preview ? 8 : 0;
  let paused = preview || reduceMotion.matches, disposed = false;
  function rgb(cssColor) {
    const probe = document.createElement('span'); probe.style.color = cssColor; root.append(probe);
    const result = getComputedStyle(probe).color.match(/[\d.]+/g).slice(0, 3).join(' ');
    probe.remove(); return result;
  }
  function resize() {
    const box = root.getBoundingClientRect();
    width = Math.max(1, box.width); height = Math.max(1, box.height);
    scale = Math.min(devicePixelRatio || 1, 1.5, Math.sqrt(2400000 / (width * height)));
    canvas.width = Math.round(width * scale); canvas.height = Math.round(height * scale);
    ctx.setTransform(scale, 0, 0, scale, 0, 0);
    cellX = Math.max(7, width / 200); cellY = cellX * 1.5;
    palette = { base: rgb('var(--color-surface-canvas)'), warm: rgb('var(--color-warm)'), light: rgb('var(--color-warm-2)'), ink: rgb('var(--color-ink-0)') };
    columns = Array.from({ length: Math.ceil(width / cellX) }, (_, i) => ({
      speed: 1.8 + noise(i + 2) * 3.2, phase: noise(i + 8),
      length: 12 + Math.floor(noise(i + 4) * 25), active: noise(i + 25) > .34
    }));
    draw(elapsed);
  }
  function draw(time) {
    if (!width) return;
    // Only flat background fill and fillText are used. Analytic fields determine
    // the character density/color, but no geometric artwork is rasterized.
    ctx.fillStyle = rgba(palette.base, 1); ctx.fillRect(0, 0, width, height);
    ctx.font = `${cellY * .88}px ui-monospace, SFMono-Regular, Consolas, monospace`;
    ctx.textBaseline = 'top';
    const horizon = height * .575;
    const radius = Math.min(width * .25, height * .218, 235);
    const centerX = width * .5, centerY = horizon - radius - height * .036;
    const rows = Math.ceil(height / cellY);
    const colors = Array.from({ length: 32 }, (_, i) => rgba(i > 27 ? palette.ink : i > 20 ? palette.light : palette.warm, .035 + (i / 31) ** .7 * .90));
    for (let column = 0; column < columns.length; column++) {
      const col = columns[column];
      const travel = horizon / cellY + col.length + 8;
      const head = ((time * col.speed + col.phase * travel) % travel) - 4;
      const epoch = Math.floor(time / (3.5 + noise(column + 80) * 3) + col.phase * 7);
      const stream = terms[(column * 7 + epoch) % terms.length] + ':' + terms[(column * 11 + epoch + 3) % terms.length];
      const mutation = Math.floor(time * (2 + noise(column + 130) * 1.5));
      const x = column * cellX;
      for (let row = 0; row < rows; row++) {
        const y = row * cellY;
        const seed = column * 137 + row * 353;
        const water = y >= horizon;
        const depth = water ? (y - horizon) / (height - horizon) : 0;
        const offset = water ? Math.sin(y * .12 - time * .9) * (3 + depth * 12) : 0;
        const sampleY = water ? horizon - (y - horizon) * 1.12 : y;
        const distance = Math.hypot(x + offset - centerX, sampleY - centerY);
        const edge = (distance - radius) / Math.max(cellY * .8, radius * .035);
        const halo = (distance - radius) / Math.max(cellY * 2.6, radius * .13);
        let light = Math.exp(-(edge * edge)) * .66 + Math.exp(-(halo * halo)) * .13;
        light *= .72 + noise(seed + 32) * .40;
        if (water) {
          // Full-width reflected interference is encoded in glyph brightness.
          light *= (1 - depth) ** 2 * (.24 + .30 * (Math.sin(y * .6 + time * .8) * .5 + .5));
          light += (Math.sin(row * 1.7 + x * .012 - time * .55) * .5 + .5) ** 12 * .095 * (1 - depth);
        }
        const tail = head - row;
        const rain = !water && col.active && tail >= 0 && tail < col.length
          ? (1 - tail / col.length) ** 1.6 * .30 * Math.min(1, (horizon - y) / 55) : 0;
        const ambient = noise(seed + 19) > .65 ? .018 : 0;
        light = Math.min(1, light + rain + ambient);
        if (light < .024) continue;
        let character;
        if (rain > light * .35) {
          const index = ((row - Math.floor(head - col.length)) % stream.length + stream.length) % stream.length;
          character = stream[index];
          if (noise(column * 191 + row * 17 + mutation * 43) > .88) {
            const word = terms[(column + row + mutation) % terms.length];
            character = word[(row + mutation) % word.length];
          }
        } else {
          // Denser glyphs build the bright contour; sparse punctuation builds air/water.
          const level = Math.min(density.length - 1, Math.floor(light * density.length));
          character = noise(seed + 6) > .68 ? stream[row % stream.length] : density[level];
        }
        // Slow scan modulation affects characters themselves, never an overlay shape.
        const scan = .93 + .07 * Math.sin(row * .7 - time * .35);
        ctx.fillStyle = colors[Math.min(31, Math.floor(light * scan * 31))];
        ctx.fillText(character, x, y);
      }
    }
  }
  function tick(now) {
    frame = 0;
    if (paused || document.hidden || disposed) return;
    if (!last) last = now;
    const delta = now - last;
    if (delta >= 1000 / 24) { elapsed += Math.min(delta, 80) / 1000; last = now; draw(elapsed); }
    frame = requestAnimationFrame(tick);
  }
  function sync() {
    cancelAnimationFrame(frame); frame = 0; last = 0;
    button.setAttribute('aria-pressed', String(paused));
    button.textContent = paused ? '애니메이션 재생' : '애니메이션 일시정지';
    if (!paused && !document.hidden && !disposed) frame = requestAnimationFrame(tick);
  }
  const toggle = () => { paused = !paused; sync(); };
  const motionChange = () => { paused = preview || reduceMotion.matches; sync(); draw(elapsed); };
  button.addEventListener('click', toggle);
  reduceMotion.addEventListener('change', motionChange);
  document.addEventListener('visibilitychange', sync);
  const observer = new ResizeObserver(resize); observer.observe(root);
  resize(); sync();
  window.afterglowLoading = Object.freeze({
    refresh: resize,
    setStatus(text) { const target = root.querySelector('[data-loading-status]'); if (target) target.textContent = String(text); },
    destroy() {
      disposed = true; cancelAnimationFrame(frame); observer.disconnect();
      button.removeEventListener('click', toggle); reduceMotion.removeEventListener('change', motionChange);
      document.removeEventListener('visibilitychange', sync);
      delete window.afterglowLoading;
    }
  });
})();
