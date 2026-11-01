/** Adapted from output/afterglow-loading/loading.js; keep the authored glyph field intact. */
import { AFTERGLOW_CSS_VAR } from '$lib/design/tokens';

export type AfterglowGeometry = { width: number; height: number; horizon: number; radius: number; centerX: number; centerY: number };

export function afterglowGeometry(width: number, height: number): AfterglowGeometry {
	const horizon = height * .575;
	const radius = Math.min(width * .25, height * .218, 235);
	return { width, height, horizon, radius, centerX: width * .5, centerY: horizon - radius - height * .036 };
}

// Public vocabulary only; never feed resource names, identifiers or credentials into the scene.
const terms = ['OpenStack', 'Afterglow', 'Nova', 'Neutron', 'Cinder', 'Glance',
	'Keystone', 'Placement', 'Ceph', 'Swift', 'Manila', 'Octavia', 'Heat', 'Trove',
	'Palimpsest', 'Drover', 'Lumen', 'Waygate', 'KVM', 'cloud-init', 'vCPU', 'RAM',
	'volume', 'subnet', 'flavor', 'snapshot', 'project', 'image'];
const density = '.:;+=*#%@';
const noise = (n: number) => { const x = Math.sin(n * 127.1 + 311.7) * 43758.5453; return x - Math.floor(x); };
type Column = { speed: number; phase: number; length: number; active: boolean };

export function createAfterglowScene(canvas: HTMLCanvasElement, host: HTMLElement) {
	let ctx: CanvasRenderingContext2D | null;
	try { ctx = canvas.getContext('2d', { alpha: false }); } catch { return null; }
	if (!ctx) return null;
	let background = '';
	let colors: string[] = [];
	const opacity = Array.from({ length: 32 }, (_, i) => .035 + (i / 31) ** .7 * .90);
	function refreshPalette() {
		const style = getComputedStyle(host);
		const color = (token: string) => style.getPropertyValue(token.slice(4, -1)).trim();
		background = color(AFTERGLOW_CSS_VAR.base);
		const warm = color(AFTERGLOW_CSS_VAR.warm), light = color(AFTERGLOW_CSS_VAR.light), ink = color(AFTERGLOW_CSS_VAR.ink);
		colors = Array.from({ length: 32 }, (_, i) => i > 27 ? ink : i > 20 ? light : warm);
	}
	refreshPalette();
	let geometry = afterglowGeometry(0, 0);
	let cellX = 8, cellY = 12, rows = 0;
	let columns: Column[] = [];
	// Optional pointer light (landing hero): glyphs near the mouse brighten softly.
	let pointer: { x: number; y: number; strength: number } | null = null;
	function setPointer(next: { x: number; y: number; strength: number } | null) { pointer = next && next.strength > 0 ? next : null; }

	function resize(width: number, height: number, resolution = 1.5) {
		geometry = afterglowGeometry(width, height);
		const scale = Math.min(devicePixelRatio || 1, resolution, Math.sqrt(2400000 / (width * height)));
		canvas.width = Math.floor(width * scale); canvas.height = Math.floor(height * scale);
		ctx!.setTransform(scale, 0, 0, scale, 0, 0);
		cellX = Math.max(7, width / 200); cellY = cellX * 1.5;
		rows = Math.ceil(height / cellY);
		ctx!.font = `${cellY * .88}px ui-monospace, SFMono-Regular, Consolas, monospace`;
		ctx!.textBaseline = 'top';
		columns = Array.from({ length: Math.ceil(width / cellX) }, (_, i) => ({
			speed: 1.8 + noise(i + 2) * 3.2, phase: noise(i + 8),
			length: 12 + Math.floor(noise(i + 4) * 25), active: noise(i + 25) > .34,
		}));
	}

	function draw(time: number) {
		const { width, height, horizon, radius, centerX, centerY } = geometry;
		if (!width || !height) return;
		// Only the flat backdrop and upright glyphs are painted: no rasterized ring or water shapes.
		ctx!.globalAlpha = 1;
		ctx!.fillStyle = background; ctx!.fillRect(0, 0, width, height);
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
					light *= (1 - depth) ** 2 * (.24 + .30 * (Math.sin(y * .6 + time * .8) * .5 + .5));
					light += (Math.sin(row * 1.7 + x * .012 - time * .55) * .5 + .5) ** 12 * .095 * (1 - depth);
				}
				const tail = head - row;
				const rain = !water && col.active && tail >= 0 && tail < col.length
					? (1 - tail / col.length) ** 1.6 * .30 * Math.min(1, (horizon - y) / 55) : 0;
				const ambient = noise(seed + 19) > .65 ? .018 : 0;
				if (pointer) {
					const reach = Math.max(70, Math.min(width, height) * .14);
					const near = Math.hypot(x - pointer.x, y - pointer.y) / reach;
					if (near < 2.2) light += Math.exp(-(near * near)) * .34 * pointer.strength;
				}
				light = Math.min(1, light + rain + ambient);
				if (light < .024) continue;
				let character: string;
				if (rain > light * .35) {
					const index = ((row - Math.floor(head - col.length)) % stream.length + stream.length) % stream.length;
					character = stream[index];
					if (noise(column * 191 + row * 17 + mutation * 43) > .88) {
						const word = terms[(column + row + mutation) % terms.length];
						character = word[(row + mutation) % word.length];
					}
				} else {
					const level = Math.min(density.length - 1, Math.floor(light * density.length));
					character = noise(seed + 6) > .68 ? stream[row % stream.length] : density[level];
				}
				const scan = .93 + .07 * Math.sin(row * .7 - time * .35);
				const level = Math.min(31, Math.floor(light * scan * 31));
				ctx!.fillStyle = colors[level];
				ctx!.globalAlpha = opacity[level];
				ctx!.fillText(character, x, y);
			}
		}
	}
	return { resize, draw, refreshPalette, setPointer };
}
