import { tick } from 'svelte';
import { writable, get } from 'svelte/store';
import { MOTION_DURATION_MS } from '$lib/design/tokens';
import { prefersReducedMotion } from '$lib/utils/motion';
import { ROUTE_SCENE_PART_SELECTOR, startSceneTransition } from '$lib/utils/routeScene';

/**
 * Console entry scene: after a password login or SSO callback has published the session, the auth artwork
 * grows across the screen, shows the real handoff state, and reveals the console once the real navigation
 * settled. The overlay is decoration over actual work: it never invents progress and never waits longer than
 * its own entrance motion after navigation finished.
 */
export type ConsoleEntryPhase = 'idle' | 'entering' | 'revealing';
export type ConsoleEntryMethod = 'password' | 'sso';

export interface ConsoleEntryOrigin {
	/** Offset from the viewport center to the auth artwork center, in px. */
	x: number;
	y: number;
}

export interface ConsoleEntryState {
	id: number;
	phase: ConsoleEntryPhase;
	method: ConsoleEntryMethod;
	/** `true` once the destination route has been applied (or the navigation ended). */
	opened: boolean;
	origin: ConsoleEntryOrigin;
	/**
	 * `true` when a View Transition carries the entrance: the login's own artwork grows into the overlay,
	 * so the overlay's CSS entrance is off. `false` uses the translate/opacity fallback from `origin`.
	 */
	scene: boolean;
}

const IDLE: ConsoleEntryState = { id: 0, phase: 'idle', method: 'password', opened: false, origin: { x: 0, y: 0 }, scene: false };
const state = writable<ConsoleEntryState>(IDLE);
export const consoleEntry = { subscribe: state.subscribe };

let serial = 0;
const entered = new Map<number, () => void>();
const timers = new Set<ReturnType<typeof setTimeout>>();

/** A missing animationend (detached overlay, jsdom, hidden tab) must not hold the scene. */
const SAFETY_MARGIN_MS = 120;

function schedule(callback: () => void, ms: number) {
	const timer = setTimeout(() => { timers.delete(timer); callback(); }, ms);
	timers.add(timer);
}

function measureOrigin(): ConsoleEntryOrigin {
	if (typeof document === 'undefined' || typeof window === 'undefined') return { x: 0, y: 0 };
	const art = document.querySelector<HTMLElement>(ROUTE_SCENE_PART_SELECTOR);
	const box = art?.getBoundingClientRect();
	if (!box || box.width <= 0 || box.height <= 0) return { x: 0, y: 0 };
	return {
		x: Math.round(box.left + box.width / 2 - window.innerWidth / 2),
		y: Math.round(box.top + box.height / 2 - window.innerHeight / 2),
	};
}

function waitForEntrance(id: number): Promise<void> {
	if (prefersReducedMotion()) return Promise.resolve();
	return new Promise((resolve) => {
		const done = () => { entered.delete(id); resolve(); };
		entered.set(id, done);
		schedule(done, MOTION_DURATION_MS.scene + SAFETY_MARGIN_MS);
	});
}

/** The overlay reports that its entrance motion finished. */
export function markConsoleEntryEntered(id: number) {
	entered.get(id)?.();
}

function reveal(id: number) {
	const current = get(state);
	if (current.id !== id || current.phase !== 'entering') return;
	if (prefersReducedMotion()) { state.set(IDLE); return; }
	state.set({ ...current, phase: 'revealing' });
	schedule(() => finishConsoleEntry(id), MOTION_DURATION_MS.scene + SAFETY_MARGIN_MS);
}

/** The overlay reports that its reveal motion finished (or the safety timer fired). */
export function finishConsoleEntry(id: number) {
	if (get(state).id === id) state.set(IDLE);
}

/**
 * Runs the real post-login navigation inside the console entry scene. The navigation starts immediately;
 * the reveal waits only for whichever of the navigation and the entrance motion finishes last. Errors from
 * `navigate` propagate to the caller after the scene has started to reveal the page that is now shown.
 */
export async function enterConsole<T>(navigate: () => Promise<T>, method: ConsoleEntryMethod): Promise<T> {
	const id = ++serial;
	const entering: ConsoleEntryState = { id, phase: 'entering', method, opened: false, origin: measureOrigin(), scene: false };
	let entrance: Promise<void>;
	const transition = startSceneTransition('console-enter', async () => {
		state.set({ ...entering, scene: true });
		await tick();
	});
	if (transition) {
		// The old snapshot is taken before navigation can change the page underneath.
		await transition.updated;
		if (get(state).id !== id) state.set({ ...entering, scene: true });
		entrance = transition.finished;
	} else {
		state.set(entering);
		entrance = waitForEntrance(id);
	}
	try {
		return await navigate();
	} finally {
		const current = get(state);
		if (current.id === id) state.set({ ...current, opened: true });
		void entrance.then(() => reveal(id));
	}
}

/** Test/teardown helper: drops any scene and pending timers. */
export function resetConsoleEntry() {
	for (const timer of timers) clearTimeout(timer);
	timers.clear();
	entered.clear();
	state.set(IDLE);
}
