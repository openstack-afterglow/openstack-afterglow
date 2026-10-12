import { REDUCED_MOTION_QUERY } from '$lib/design/tokens';

export type SceneMotionState = 'static' | 'playing' | 'paused';

export interface SceneMotionController {
	replay(): void;
	destroy(): void;
}

/** A concept scene plays once, pauses when unseen, and always has a complete static frame. */
export function createSceneMotion(node: HTMLElement, onstate: (state: SceneMotionState) => void): SceneMotionController {
	const preference = typeof window.matchMedia === 'function' ? window.matchMedia(REDUCED_MOTION_QUERY) : undefined;
	let visible = false;
	let started = false;
	let complete = false;
	let destroyed = false;
	let state: SceneMotionState = 'static';
	const supported = typeof window.IntersectionObserver === 'function';

	function setState(next: SceneMotionState) {
		if (destroyed || next === state) return;
		state = next;
		onstate(next);
	}

	function sync() {
		if (!supported || !preference || preference.matches) {
			complete = true;
			setState('static');
			return;
		}
		if (complete) return;
		if (visible && document.visibilityState !== 'hidden') {
			started = true;
			setState('playing');
		} else if (started) {
			setState('paused');
		}
	}

	const observer = supported ? new window.IntersectionObserver((entries) => {
		if (destroyed) return;
		for (const entry of entries) {
			if (entry.target === node) visible = entry.isIntersecting;
		}
		sync();
	}, { threshold: 0.18, rootMargin: '0px 0px -48px 0px' }) : undefined;

	function finish(event: AnimationEvent) {
		if (!started || complete || event.target === node || typeof node.getAnimations !== 'function') return;
		if (node.getAnimations({ subtree: true }).some((animation) => animation.playState !== 'finished' && animation.playState !== 'idle')) return;
		complete = true;
		setState('static');
	}

	observer?.observe(node);
	preference?.addEventListener('change', sync);
	document.addEventListener('visibilitychange', sync);
	node.addEventListener('animationend', finish);
	sync();

	return {
		replay() {
			if (destroyed) return;
			complete = false;
			started = true;
			sync();
		},
		destroy() {
			destroyed = true;
			observer?.disconnect();
			preference?.removeEventListener('change', sync);
			document.removeEventListener('visibilitychange', sync);
			node.removeEventListener('animationend', finish);
		},
	};
}
