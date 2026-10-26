import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/svelte';
import { flushSync, tick } from 'svelte';
import AutoRefreshWrapper from './_AutoRefreshWrapper.svelte';

const storage: Record<string, string> = {};
vi.stubGlobal('localStorage', {
	getItem: (key: string) => storage[key] ?? null,
	setItem: (key: string, val: string) => {
		storage[key] = val;
	},
	removeItem: (key: string) => {
		delete storage[key];
	},
});

function deferred(): { promise: Promise<void>; resolve: () => void } {
	return Promise.withResolvers<void>();
}

describe('createAutoRefresh (via component)', () => {
	beforeEach(() => {
		Object.keys(storage).forEach((k) => delete storage[k]);
		Object.defineProperty(document, 'hidden', { get: () => false, configurable: true });
		Object.defineProperty(navigator, 'onLine', { get: () => true, configurable: true });
	});

	afterEach(() => {
		vi.useRealTimers();
	});

	it('defaultActive=false 이면 active가 false로 렌더링', () => {
		render(AutoRefreshWrapper, { defaultActive: false, invokeOnMount: false });
		flushSync();
		expect(screen.getByTestId('active').textContent).toBe('false');
	});

	it('defaultActive=true 이면 active가 true로 렌더링', () => {
		render(AutoRefreshWrapper, { defaultActive: true, invokeOnMount: false });
		flushSync();
		expect(screen.getByTestId('active').textContent).toBe('true');
	});

	it('defaultInterval이 interval로 렌더링', () => {
		render(AutoRefreshWrapper, { defaultInterval: 15, defaultActive: false });
		flushSync();
		expect(screen.getByTestId('interval').textContent).toBe('15');
	});

	it('localStorage에서 저장된 active 상태 복원', async () => {
		storage['autoRefresh.test-key.active'] = 'false';
		render(AutoRefreshWrapper, { defaultActive: true, invokeOnMount: false });
		// $effect가 microtask로 실행됨 — tick()으로 스케줄러 플러시
		await tick();
		flushSync();
		expect(screen.getByTestId('active').textContent).toBe('false');
	});

	it('localStorage에서 저장된 interval 복원', async () => {
		storage['autoRefresh.test-key.interval'] = '60';
		render(AutoRefreshWrapper, { defaultInterval: 30, defaultActive: false });
		await tick();
		flushSync();
		expect(screen.getByTestId('interval').textContent).toBe('60');
	});

	it('fn이 interval마다 호출됨', async () => {
		vi.useFakeTimers();
		const fn = vi.fn();
		render(AutoRefreshWrapper, { fn, defaultActive: true, invokeOnMount: false, defaultInterval: 10 });
		await tick();
		flushSync();
		vi.advanceTimersByTime(10_000);
		expect(fn).toHaveBeenCalled();
	});

	it('실행 중 강제 새로고침 요청을 한 번의 후행 라운드로 합침', async () => {
		const first = deferred();
		const second = deferred();
		const fn = vi.fn()
			.mockReturnValueOnce(first.promise)
			.mockReturnValueOnce(second.promise);
		render(AutoRefreshWrapper, { fn, defaultActive: true, invokeOnMount: true });
		await tick();
		await vi.waitFor(() => expect(fn).toHaveBeenCalledOnce());

		await fireEvent.click(screen.getByTestId('force-refresh'));
		await fireEvent.click(screen.getByTestId('force-refresh'));
		expect(fn).toHaveBeenCalledOnce();

		first.resolve();
		await vi.waitFor(() => expect(fn).toHaveBeenCalledTimes(2));
		expect(fn).toHaveBeenNthCalledWith(1, false);
		expect(fn).toHaveBeenNthCalledWith(2, true);
		second.resolve();
		await tick();
		expect(fn).toHaveBeenCalledTimes(2);
	});

	it('waits a full interval after a slow round settles instead of fixed-timer catch-up', async () => {
		vi.useFakeTimers();
		const pending = deferred();
		const fn = vi.fn().mockReturnValueOnce(pending.promise);
		render(AutoRefreshWrapper, { fn, defaultActive: true, invokeOnMount: true, defaultInterval: 10 });
		await tick();
		expect(fn).toHaveBeenCalledOnce();
		await vi.advanceTimersByTimeAsync(29_000);
		expect(fn).toHaveBeenCalledOnce();
		pending.resolve();
		await vi.advanceTimersByTimeAsync(0);
		await vi.advanceTimersByTimeAsync(9_999);
		expect(fn).toHaveBeenCalledOnce();
		await vi.advanceTimersByTimeAsync(1);
		expect(fn).toHaveBeenCalledTimes(2);
	});

	it('changes intervals, boost and active preference without immediate duplicate requests', async () => {
		vi.useFakeTimers();
		const fn = vi.fn();
		render(AutoRefreshWrapper, { fn, defaultActive: true, invokeOnMount: true });
		await tick();
		expect(fn).toHaveBeenCalledOnce();
		await fireEvent.click(screen.getByTestId('change-interval'));
		await fireEvent.click(screen.getByTestId('boost'));
		await fireEvent.click(screen.getByTestId('toggle-active'));
		await fireEvent.click(screen.getByTestId('toggle-active'));
		expect(fn).toHaveBeenCalledOnce();
		await vi.advanceTimersByTimeAsync(4_000);
		expect(fn).toHaveBeenCalledTimes(2);
	});

	it('pauses offline and hidden polling and coalesces simultaneous wakeups', async () => {
		vi.useFakeTimers();
		const pending = deferred();
		const fn = vi.fn().mockReturnValueOnce(pending.promise);
		Object.defineProperty(navigator, 'onLine', { get: () => false, configurable: true });
		render(AutoRefreshWrapper, { fn, invokeOnMount: true });
		await tick();
		await vi.advanceTimersByTimeAsync(60_000);
		expect(fn).not.toHaveBeenCalled();
		Object.defineProperty(navigator, 'onLine', { get: () => true, configurable: true });
		window.dispatchEvent(new Event('online'));
		document.dispatchEvent(new Event('visibilitychange'));
		expect(fn).toHaveBeenCalledOnce();
		Object.defineProperty(document, 'hidden', { get: () => true, configurable: true });
		document.dispatchEvent(new Event('visibilitychange'));
		pending.resolve();
		await vi.advanceTimersByTimeAsync(120_000);
		expect(fn).toHaveBeenCalledOnce();
	});

	it('does not dispatch a queued manual refresh after unmount', async () => {
		const pending = deferred();
		const fn = vi.fn().mockReturnValueOnce(pending.promise);
		const mounted = render(AutoRefreshWrapper, { fn, invokeOnMount: true });
		await tick();
		await fireEvent.click(screen.getByTestId('force-refresh'));
		mounted.unmount();
		pending.resolve();
		await tick();
		expect(fn).toHaveBeenCalledOnce();
	});
});
