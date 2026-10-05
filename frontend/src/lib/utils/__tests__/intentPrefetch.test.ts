import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { createIntentPrefetchScheduler } from '../intentPrefetch';

beforeEach(() => {
	vi.useFakeTimers();
	Reflect.deleteProperty(window, 'requestIdleCallback');
	Reflect.deleteProperty(window, 'cancelIdleCallback');
});

afterEach(() => {
	vi.useRealTimers();
});

describe('intent prefetch scheduler', () => {
	it('immediate intent reuses the scheduled speculation', () => {
		const run = vi.fn();
		const scheduler = createIntentPrefetchScheduler();
		scheduler.schedule('next', run);

		scheduler.intent('next', run);
		expect(run).toHaveBeenCalledOnce();
		vi.advanceTimersByTime(200);
		expect(run).toHaveBeenCalledOnce();
	});

	it('runs scheduled speculation when the browser becomes idle', () => {
		const idle = { callback: null as (() => void) | null };
		Object.assign(window, {
			requestIdleCallback: vi.fn((callback: () => void) => {
				idle.callback = callback;
				return 7;
			}),
			cancelIdleCallback: vi.fn(),
		});
		const run = vi.fn();
		const scheduler = createIntentPrefetchScheduler();
		scheduler.schedule('next', run);

		idle.callback?.();
		expect(run).toHaveBeenCalledOnce();
	});

	it('cancels and aborts superseded speculation', () => {
		const signals: AbortSignal[] = [];
		const scheduler = createIntentPrefetchScheduler();
		scheduler.schedule('old', (signal) => { signals.push(signal); });
		scheduler.intent('old', (signal) => { signals.push(signal); });
		expect(signals[0].aborted).toBe(false);

		scheduler.schedule('new', vi.fn());
		expect(signals[0].aborted).toBe(true);
		scheduler.cancel();
	});
});
