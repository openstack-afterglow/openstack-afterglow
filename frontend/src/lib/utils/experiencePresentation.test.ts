import { afterEach, describe, expect, it, vi } from 'vitest';
import { experiencePresentation } from './experiencePresentation';
import { experienceMessage, experienceState, recordExperience, type ExperienceContext } from './experience';
import type { ExperienceMessageMetadata } from '$lib/i18n/experienceMessages';

vi.mock('./experience', () => ({
	experienceMessage: vi.fn(), experienceState: vi.fn(), recordExperience: vi.fn(),
}));

const context = { segmentId: 'explicit-owner-context' } as ExperienceContext;
const message: ExperienceMessageMetadata = Object.freeze({ key: 'common:actions.confirm', locale: 'en', catalog_revision: 'a'.repeat(64), tone: 'neutral', restoration: 'restored' });

function intersectionFixture() {
	let callback: IntersectionObserverCallback | undefined;
	let observer: IntersectionObserver | undefined;
	const observe = vi.fn();
	const disconnect = vi.fn();
	class Observer implements IntersectionObserver {
		readonly root = null;
		readonly rootMargin = '0px';
		readonly scrollMargin = '0px';
		readonly thresholds = [0];
		constructor(handler: IntersectionObserverCallback) { callback = handler; observer = this; }
		observe = observe;
		disconnect = disconnect;
		unobserve = vi.fn();
		takeRecords(): IntersectionObserverEntry[] { return []; }
	}
	vi.stubGlobal('IntersectionObserver', Observer);
	return {
		observe, disconnect,
		emit(node: HTMLElement, visible: boolean) {
			const bounds = node.getBoundingClientRect();
			const entry: IntersectionObserverEntry = {
				target: node,
				isIntersecting: visible,
				intersectionRatio: visible ? 1 : 0,
				boundingClientRect: bounds,
				intersectionRect: bounds,
				rootBounds: null,
				time: performance.now(),
			};
			if (observer) callback?.([entry], observer);
		},
	};
}

afterEach(() => { vi.clearAllMocks(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });

describe('explicit semantic primitive presentation', () => {
	it('does not observe or infer anything from legacy text without both explicit inputs', () => {
		const fixture = intersectionFixture();
		const node = document.createElement('div');
		node.textContent = 'secret raw failure';
		const action = experiencePresentation(node, { context });
		expect(fixture.observe).not.toHaveBeenCalled();
		action.update({ message });
		expect(fixture.observe).not.toHaveBeenCalled();
		expect(experienceMessage).not.toHaveBeenCalled();
		expect(recordExperience).not.toHaveBeenCalled();
		action.destroy();
	});

	it('reports actual intersection/document exposure, never text or inferred business completion', () => {
		const fixture = intersectionFixture();
		vi.spyOn(document, 'visibilityState', 'get').mockReturnValue('visible');
		const node = document.createElement('div');
		Object.defineProperty(node, 'textContent', { get() { throw new Error('text scraping forbidden'); } });
		const action = experiencePresentation(node, { context, message, state: 'loading' });
		expect(experienceMessage).not.toHaveBeenCalled();
		fixture.emit(node, true);
		expect(recordExperience).toHaveBeenCalledWith(context, 'view.exposure_changed', { visibility: 'visible' });
		expect(experienceMessage).toHaveBeenCalledExactlyOnceWith(context, message);
		expect(experienceState).toHaveBeenCalledWith(context, 'loading', undefined);
		action.update({ context, message: { ...message }, state: 'ready', step: 2 });
		expect(experienceMessage).toHaveBeenCalledTimes(1);
		expect(experienceState).toHaveBeenLastCalledWith(context, 'ready', 2);
		fixture.emit(node, false);
		expect(recordExperience).toHaveBeenLastCalledWith(context, 'view.exposure_changed', { visibility: 'hidden' });
		action.destroy();
		expect(fixture.disconnect).toHaveBeenCalledOnce();
	});

	it('does not manufacture visibility if IntersectionObserver is unavailable', () => {
		vi.stubGlobal('IntersectionObserver', undefined);
		const action = experiencePresentation(document.createElement('div'), { context, message });
		expect(recordExperience).not.toHaveBeenCalled();
		expect(experienceMessage).not.toHaveBeenCalled();
		action.destroy();
	});
});
