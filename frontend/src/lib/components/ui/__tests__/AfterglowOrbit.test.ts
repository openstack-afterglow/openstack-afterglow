import { cleanup, render } from '@testing-library/svelte';
import { tick } from 'svelte';
import { afterEach, beforeEach, describe, expect, it, vi, type Mock } from 'vitest';
import AfterglowOrbit from '../AfterglowOrbit.svelte';
import { afterglowGeometry, createAfterglowScene } from '../afterglowLoadingScene';

let hidden: boolean;
let intersect: IntersectionObserverCallback;
let resize: ResizeObserverCallback;
let intersectionDisconnect: Mock;
let resizeDisconnect: Mock;
let motion: MediaQueryList;
let motionChanged: EventTarget;
let reduced: boolean;
let frames: Map<number, FrameRequestCallback>;
let context: CanvasRenderingContext2D;
let frameId: number;

beforeEach(() => {
	hidden = false; reduced = false; frames = new Map(); frameId = 0;
	intersectionDisconnect = vi.fn(); resizeDisconnect = vi.fn();
	context = { setTransform: vi.fn(), fillRect: vi.fn(), fillText: vi.fn() } as unknown as CanvasRenderingContext2D;
	vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(context);
	vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockReturnValue({ width: 320, height: 480 } as DOMRect);
	vi.spyOn(document, 'hidden', 'get').mockImplementation(() => hidden);
	motionChanged = new EventTarget();
	motion = {
		get matches() { return reduced; },
		addEventListener: vi.fn((...args: Parameters<EventTarget['addEventListener']>) => motionChanged.addEventListener(...args)),
		removeEventListener: vi.fn((...args: Parameters<EventTarget['removeEventListener']>) => motionChanged.removeEventListener(...args)),
	} as unknown as MediaQueryList;
	vi.stubGlobal('matchMedia', vi.fn(() => motion));
	vi.stubGlobal('requestAnimationFrame', vi.fn((callback: FrameRequestCallback) => { frames.set(++frameId, callback); return frameId; }));
	vi.stubGlobal('cancelAnimationFrame', vi.fn((id: number) => { frames.delete(id); }));
	vi.stubGlobal('IntersectionObserver', class {
		constructor(callback: IntersectionObserverCallback) { intersect = callback; }
		observe = vi.fn();
		disconnect = intersectionDisconnect;
	});
	vi.stubGlobal('ResizeObserver', class {
		constructor(callback: ResizeObserverCallback) { resize = callback; }
		observe = vi.fn();
		disconnect = resizeDisconnect;
	});
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });

function advanceFrame(now: number) {
	const pending = [...frames.values()];
	frames.clear();
	for (const callback of pending) callback(now);
}

describe('authored Afterglow glyph scene', () => {
	it('keeps the canvas decorative and shares the actual halo geometry with pending content', () => {
		const ongeometry = vi.fn();
		const { container } = render(AfterglowOrbit, { ongeometry });
		const artwork = container.querySelector('.afterglow-orbit')!;
		expect(artwork.getAttribute('aria-hidden')).toBe('true');
		expect(container.querySelector('canvas')?.getAttribute('aria-hidden')).toBe('true');
		expect(container.querySelector('[role="progressbar"]')).toBeNull();
		expect(container.querySelector('iframe')).toBeNull();
		expect(context.fillText).toHaveBeenCalled();
		expect(ongeometry).toHaveBeenLastCalledWith(afterglowGeometry(320, 480));
		const geometry = afterglowGeometry(784, 724);
		expect(geometry.radius).toBe(724 * .218);
		expect(geometry.centerX).toBe(392);
		expect(geometry.centerY).toBe(724 * .575 - geometry.radius - 724 * .036);
		expect(geometry.centerY).not.toBe(362);
	});

	it('pauses offscreen, hidden, and settled artwork and releases every observation on unmount', async () => {
		const removeVisibility = vi.spyOn(document, 'removeEventListener');
		const view = render(AfterglowOrbit, { active: true });
		const artwork = view.container.querySelector('.afterglow-orbit')!;
		expect(artwork.getAttribute('data-running')).toBe('true');
		intersect([{ isIntersecting: false } as IntersectionObserverEntry], {} as IntersectionObserver);
		await tick();
		expect(artwork.getAttribute('data-running')).toBe('false');
		expect(frames.size).toBe(0);
		intersect([{ isIntersecting: true } as IntersectionObserverEntry], {} as IntersectionObserver);
		hidden = true;
		document.dispatchEvent(new Event('visibilitychange'));
		await tick();
		expect(frames.size).toBe(0);
		hidden = false;
		document.dispatchEvent(new Event('visibilitychange'));
		await tick();
		expect(artwork.getAttribute('data-running')).toBe('true');
		await view.rerender({ active: false });
		expect(artwork.getAttribute('data-running')).toBe('false');
		expect(frames.size).toBe(0);
		view.unmount();
		expect(intersectionDisconnect).toHaveBeenCalledOnce();
		expect(resizeDisconnect).toHaveBeenCalledOnce();
		expect(motion.removeEventListener).toHaveBeenCalledWith('change', expect.any(Function));
		expect(removeVisibility).toHaveBeenCalledWith('visibilitychange', expect.any(Function));
	});

	it('draws a static reduced-motion frame and reacts to preference changes without restarting elapsed time', async () => {
		reduced = true;
		const view = render(AfterglowOrbit);
		expect(context.fillText).toHaveBeenCalled();
		expect(frames.size).toBe(0);
		expect(view.container.querySelector('.afterglow-orbit')?.getAttribute('data-running')).toBe('false');
		reduced = false; motionChanged.dispatchEvent(new Event('change'));
		await tick();
		expect(frames.size).toBe(1);
		reduced = true; motionChanged.dispatchEvent(new Event('change'));
		await tick();
		expect(frames.size).toBe(0);
		const draws = vi.mocked(context.fillRect).mock.calls.length;
		resize([], {} as ResizeObserver);
		expect(context.fillRect).toHaveBeenCalledTimes(draws + 1);
		expect(frames.size).toBe(0);
	});

	it('caps redraws at 24fps and bounds high-DPR backing storage', () => {
		const view = render(AfterglowOrbit);
		const draws = vi.mocked(context.fillRect).mock.calls.length;
		advanceFrame(100); advanceFrame(120); advanceFrame(140);
		expect(context.fillRect).toHaveBeenCalledTimes(draws);
		advanceFrame(142);
		expect(context.fillRect).toHaveBeenCalledTimes(draws + 1);
		const canvas = view.container.querySelector('canvas')!;
		vi.stubGlobal('devicePixelRatio', 3);
		const scene = createAfterglowScene(canvas, canvas.parentElement!)!;
		scene.resize(784, 724);
		expect(canvas.width).toBe(1176);
		expect(canvas.height).toBe(1086);
		scene.resize(4000, 3000);
		expect(canvas.width * canvas.height).toBeLessThanOrEqual(2_400_000);
	});

	it('redraws live root appearance and palette changes while reduced-motion stays static, without per-frame style reads', async () => {
		reduced = true;
		const originalClass = document.documentElement.className;
		const originalStyle = document.documentElement.style.cssText;
		document.documentElement.classList.remove('light');
		const backgrounds: string[] = [];
		vi.mocked(context.fillRect).mockImplementation(() => { backgrounds.push(String(context.fillStyle)); });
		const styles = vi.spyOn(globalThis, 'getComputedStyle').mockImplementation(() => ({
			getPropertyValue: (token: string) => token === '--afterglow-artwork-base'
				? document.documentElement.classList.contains('light') ? '#f2f3f6' : '#101113'
				: document.documentElement.style.getPropertyValue('--color-accent') || '#7da3ff',
		}) as CSSStyleDeclaration);
		const view = render(AfterglowOrbit);
		try {
			expect(styles).toHaveBeenCalledOnce();
			const draws = vi.mocked(context.fillRect).mock.calls.length;
			document.documentElement.classList.add('light');
			await Promise.resolve(); await tick();
			expect(styles).toHaveBeenCalledTimes(2);
			expect(context.fillRect).toHaveBeenCalledTimes(draws + 1);
			expect(backgrounds.at(-1)).toBe('#f2f3f6');
			expect(frames.size).toBe(0);
			document.documentElement.style.setProperty('--color-accent', '#3352cf');
			await Promise.resolve(); await tick();
			expect(styles).toHaveBeenCalledTimes(3);
			expect(context.fillStyle).toBe('#3352cf');
			reduced = false; motionChanged.dispatchEvent(new Event('change'));
			advanceFrame(100); advanceFrame(150); advanceFrame(200);
			expect(styles).toHaveBeenCalledTimes(3);
			await view.rerender({ active: false });
			document.documentElement.classList.remove('light');
			await Promise.resolve(); await tick();
			expect(backgrounds.at(-1)).toBe('#101113');
			expect(styles).toHaveBeenCalledTimes(4);
			expect(frames.size).toBe(0);
			view.unmount();
			const settledDraws = vi.mocked(context.fillRect).mock.calls.length;
			document.documentElement.classList.add('light');
			await Promise.resolve(); await tick();
			expect(styles).toHaveBeenCalledTimes(4);
			expect(context.fillRect).toHaveBeenCalledTimes(settledDraws);
			expect(frames.size).toBe(0);
		} finally {
			cleanup();
			document.documentElement.className = originalClass;
			document.documentElement.style.cssText = originalStyle;
		}
	});

	it('brightens glyphs around a mouse pointer only when interactive, ignores touch and releases listeners', () => {
		reduced = true;
		vi.mocked(HTMLElement.prototype.getBoundingClientRect).mockReturnValue({ left: 0, top: 0, width: 320, height: 480 } as DOMRect);
		const removeWindow = vi.spyOn(window, 'removeEventListener');
		render(AfterglowOrbit);
		const baseline = vi.mocked(context.fillText).mock.calls.length;
		cleanup();
		const view = render(AfterglowOrbit, { interactive: true });
		vi.mocked(context.fillText).mockClear();
		const move = (pointerType: string) => window.dispatchEvent(Object.assign(new MouseEvent('pointermove', { clientX: 160, clientY: 330 }), { pointerType }));
		move('touch');
		expect(frames.size).toBe(0);
		move('mouse');
		advanceFrame(16);
		expect(vi.mocked(context.fillText).mock.calls.length).toBeGreaterThan(baseline);
		view.unmount();
		expect(removeWindow).toHaveBeenCalledWith('pointermove', expect.any(Function));
	});

	it('keeps the geometry and DOM status usable if the canvas context is unavailable', () => {
		vi.mocked(HTMLCanvasElement.prototype.getContext).mockReturnValue(null);
		const ongeometry = vi.fn();
		const { container } = render(AfterglowOrbit, { ongeometry });
		expect(container.querySelector('.afterglow-orbit')?.getAttribute('data-renderer')).toBe('fallback');
		expect(frames.size).toBe(0);
		expect(ongeometry).toHaveBeenCalledWith(afterglowGeometry(320, 480));
	});
});
