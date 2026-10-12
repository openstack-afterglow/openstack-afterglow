import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { createSceneMotion, type SceneMotionState } from '../sceneMotion';

interface MotionPreference {
	matches: boolean;
	addEventListener(event: string, listener: () => void): void;
	removeEventListener(event: string, listener: () => void): void;
}
let preference: MotionPreference;
let preferenceChange: (() => void) | undefined;
let visibility: DocumentVisibilityState;
const originalVisibility = Object.getOwnPropertyDescriptor(document, 'visibilityState');

class SceneObserver {
	static instances: SceneObserver[] = [];
	readonly disconnect = vi.fn();
	constructor(readonly callback: IntersectionObserverCallback) { SceneObserver.instances.push(this); }
	observe() {}
	unobserve() {}
	takeRecords() { return []; }
	visible(node: Element, isIntersecting: boolean) { this.callback([{ target: node, isIntersecting } as IntersectionObserverEntry], this as unknown as IntersectionObserver); }
}

function scene() {
	const node = document.createElement('div');
	const graphic = document.createElement('svg');
	node.append(graphic);
	document.body.append(node);
	let state: SceneMotionState = 'static';
	const controller = createSceneMotion(node, (next) => { state = next; });
	return { node, graphic, controller, observer: SceneObserver.instances.at(-1)!, state: () => state };
}

beforeEach(() => {
	SceneObserver.instances = [];
	visibility = 'visible';
	preferenceChange = undefined;
	Object.defineProperty(document, 'visibilityState', { configurable: true, get: () => visibility });
	preference = { matches: false, addEventListener: vi.fn((_event, fn) => { preferenceChange = fn; }), removeEventListener: vi.fn() };
	vi.stubGlobal('matchMedia', () => preference);
	vi.stubGlobal('IntersectionObserver', SceneObserver);
});

afterEach(() => {
	document.body.replaceChildren();
	vi.unstubAllGlobals();
	if (originalVisibility) Object.defineProperty(document, 'visibilityState', originalVisibility);
	else Reflect.deleteProperty(document, 'visibilityState');
});

describe('finite explanatory scene motion', () => {
	it('does not begin in a hidden document and pauses when an active scene leaves view', () => {
		visibility = 'hidden';
		const current = scene();
		current.observer.visible(current.node, true);
		expect(current.state()).toBe('static');
		visibility = 'visible';
		document.dispatchEvent(new Event('visibilitychange'));
		expect(current.state()).toBe('playing');
		current.observer.visible(current.node, false);
		expect(current.state()).toBe('paused');
		current.observer.visible(current.node, true);
		expect(current.state()).toBe('playing');
		visibility = 'hidden';
		document.dispatchEvent(new Event('visibilitychange'));
		expect(current.state()).toBe('paused');
		current.controller.destroy();
	});

	it('finishes only when every delayed phase is finished and does not autoplay again', () => {
		const current = scene();
		let animations = [{ playState: 'finished' }, { playState: 'running' }];
		Object.assign(current.node, { getAnimations: () => animations });
		current.observer.visible(current.node, true);
		current.graphic.dispatchEvent(new Event('animationend', { bubbles: true }));
		expect(current.state()).toBe('playing');
		animations = [{ playState: 'finished' }];
		current.graphic.dispatchEvent(new Event('animationend', { bubbles: true }));
		expect(current.state()).toBe('static');
		current.observer.visible(current.node, false);
		current.observer.visible(current.node, true);
		expect(current.state()).toBe('static');
		current.controller.replay();
		expect(current.state()).toBe('playing');
		current.controller.destroy();
	});

	it('makes a paused scene complete when reduced motion becomes active, until an explicit replay', () => {
		const current = scene();
		current.observer.visible(current.node, true);
		current.observer.visible(current.node, false);
		preference.matches = true;
		preferenceChange?.();
		expect(current.state()).toBe('static');
		preference.matches = false;
		preferenceChange?.();
		current.observer.visible(current.node, true);
		expect(current.state()).toBe('static');
		current.controller.replay();
		expect(current.state()).toBe('playing');
		current.controller.destroy();
	});

	it.each(['IntersectionObserver', 'matchMedia'])('keeps a complete static scene when %s is unavailable', (api) => {
		vi.stubGlobal(api, undefined);
		const current = scene();
		current.controller.replay();
		expect(current.state()).toBe('static');
		current.controller.destroy();
	});

	it('ignores stale callbacks after destruction without affecting a new scene', () => {
		const old = scene();
		old.controller.destroy();
		const current = scene();
		old.observer.visible(old.node, true);
		old.controller.replay();
		expect(old.state()).toBe('static');
		expect(current.state()).toBe('static');
		current.observer.visible(current.node, true);
		expect(current.state()).toBe('playing');
		current.controller.destroy();
	});
});
