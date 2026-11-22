import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { get } from 'svelte/store';
import { MOTION_DURATION_MS } from '$lib/design/tokens';
import { consoleEntry, enterConsole, finishConsoleEntry, markConsoleEntryEntered, resetConsoleEntry } from '../consoleEntry';

function setReducedMotion(matches: boolean) {
	window.matchMedia = ((query: string) => ({
		media: query, matches, onchange: null,
		addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {}, dispatchEvent: () => false,
	})) as typeof window.matchMedia;
}

describe('consoleEntry', () => {
	const originalMatchMedia = window.matchMedia;
	beforeEach(() => {
		vi.useFakeTimers();
		setReducedMotion(false);
		resetConsoleEntry();
	});
	afterEach(() => {
		resetConsoleEntry();
		vi.useRealTimers();
		window.matchMedia = originalMatchMedia;
		document.body.innerHTML = '';
	});

	it('enters from the auth artwork, waits for the real navigation, then reveals and settles', async () => {
		document.body.innerHTML = '<section data-route-scene-part="art"></section>';
		document.querySelector('section')!.getBoundingClientRect = () => ({ left: 0, top: 64, width: 512, height: 640, right: 512, bottom: 704, x: 0, y: 64, toJSON() {} });
		let finishNavigation!: () => void;
		const navigate = vi.fn(() => new Promise<void>((resolve) => { finishNavigation = resolve; }));
		const result = enterConsole(navigate, 'password');

		const entering = get(consoleEntry);
		expect(navigate).toHaveBeenCalledOnce();
		expect(entering).toMatchObject({ phase: 'entering', method: 'password', opened: false });
		expect(entering.origin).toEqual({ x: 256 - Math.round(window.innerWidth / 2), y: 384 - Math.round(window.innerHeight / 2) });

		// Entrance finished first: the overlay keeps stating the real, still-pending handoff.
		markConsoleEntryEntered(entering.id);
		await Promise.resolve();
		expect(get(consoleEntry).phase).toBe('entering');

		finishNavigation();
		await result;
		await Promise.resolve();
		expect(get(consoleEntry)).toMatchObject({ phase: 'revealing', opened: true });

		finishConsoleEntry(entering.id);
		expect(get(consoleEntry).phase).toBe('idle');
	});

	it('does not add a wait beyond its own entrance motion and recovers from a missing animationend', async () => {
		await enterConsole(async () => undefined, 'sso');
		expect(get(consoleEntry)).toMatchObject({ phase: 'entering', method: 'sso', opened: true });
		await vi.advanceTimersByTimeAsync(MOTION_DURATION_MS.scene + 120);
		expect(get(consoleEntry).phase).toBe('revealing');
		await vi.advanceTimersByTimeAsync(MOTION_DURATION_MS.scene + 120);
		expect(get(consoleEntry).phase).toBe('idle');
	});

	it('reveals the page that is shown when navigation fails and rethrows', async () => {
		await expect(enterConsole(async () => { throw new Error('navigation failed'); }, 'password')).rejects.toThrow('navigation failed');
		expect(get(consoleEntry).opened).toBe(true);
		await vi.advanceTimersByTimeAsync(MOTION_DURATION_MS.scene * 2 + 240);
		expect(get(consoleEntry).phase).toBe('idle');
	});

	it('is immediate under reduced motion', async () => {
		setReducedMotion(true);
		await enterConsole(async () => undefined, 'password');
		await Promise.resolve();
		await Promise.resolve();
		expect(get(consoleEntry).phase).toBe('idle');
	});

	it('ignores stale completions from an earlier scene', async () => {
		await enterConsole(async () => undefined, 'password');
		const first = get(consoleEntry).id;
		const second = enterConsole(() => new Promise<void>(() => {}), 'sso');
		finishConsoleEntry(first);
		markConsoleEntryEntered(first);
		expect(get(consoleEntry)).toMatchObject({ phase: 'entering', method: 'sso', opened: false });
		void second;
	});
});
