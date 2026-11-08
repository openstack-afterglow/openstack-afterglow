import { beforeEach, describe, expect, it, vi } from 'vitest';

const viewport = vi.hoisted(() => ({ current: true }));
vi.mock('../viewport', () => ({ tutorialViewport: viewport }));
vi.mock('$app/navigation', () => ({ goto: vi.fn() }));

import { isTourActive, startTour, stopTour } from '../engine';

beforeEach(() => {
	stopTour();
	sessionStorage.clear();
});

describe('tutorials below tablet width', () => {
	it('refuses to start any tour on mobile, including deep-link and resume starts', async () => {
		viewport.current = false;
		expect(await startTour('buckets')).toBe(false);
		expect(await startTour('buckets', 3)).toBe(false);
		expect(isTourActive()).toBe(false);
		expect(sessionStorage.length).toBe(0);
	});
});
