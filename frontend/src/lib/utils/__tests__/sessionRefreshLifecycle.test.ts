import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { startSessionRefreshLifecycle } from '../sessionRefreshLifecycle';
import type { SessionRefreshState } from '../sessionRefreshLifecycle';

const NOW = new Date('2026-09-11T00:00:00Z');

function realSession(accessExpiresAt: number): SessionRefreshState {
	return {
		token: 'access-token',
		refreshToken: 'refresh-token',
		accessExpiresAt,
		isMock: false,
		isLoggingOut: false,
	};
}

describe('startSessionRefreshLifecycle', () => {
	let stop: (() => void) | undefined;
	let ownVisibilityStateDescriptor: PropertyDescriptor | undefined;

	beforeEach(() => {
		vi.useFakeTimers();
		vi.setSystemTime(NOW);
		ownVisibilityStateDescriptor = Object.getOwnPropertyDescriptor(document, 'visibilityState');
		Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'visible' });
	});

	afterEach(() => {
		stop?.();
		stop = undefined;
		if (ownVisibilityStateDescriptor) {
			Object.defineProperty(document, 'visibilityState', ownVisibilityStateDescriptor);
		} else {
			Reflect.deleteProperty(document, 'visibilityState');
		}
		vi.useRealTimers();
	});

	it('refreshes when focus resumes after the token enters the leeway before the fallback timer', () => {
		const refreshSession = vi.fn().mockResolvedValue('refreshed-token');
		let session = realSession(Math.floor(NOW.getTime() / 1000) + 121);
		stop = startSessionRefreshLifecycle({ getSession: () => session, refreshSession });

		expect(refreshSession).not.toHaveBeenCalled();

		vi.setSystemTime(new Date(NOW.getTime() + 2_000));
		window.dispatchEvent(new Event('focus'));

		expect(refreshSession).toHaveBeenCalledOnce();
	});

	it('reads the latest real session state only when the document becomes visible', () => {
		const refreshSession = vi.fn().mockResolvedValue('refreshed-token');
		let session: SessionRefreshState = {
			token: null,
			refreshToken: null,
			accessExpiresAt: null,
			isMock: false,
			isLoggingOut: false,
		};
		stop = startSessionRefreshLifecycle({ getSession: () => session, refreshSession });

		session = realSession(Math.floor(NOW.getTime() / 1000) + 120);
		Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'hidden' });
		document.dispatchEvent(new Event('visibilitychange'));
		expect(refreshSession).not.toHaveBeenCalled();

		Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'visible' });
		document.dispatchEvent(new Event('visibilitychange'));

		expect(refreshSession).toHaveBeenCalledOnce();
	});

	it('keeps the 60-second fallback for an expiring session without a resume event', () => {
		const refreshSession = vi.fn().mockResolvedValue('refreshed-token');
		const session = realSession(Math.floor(NOW.getTime() / 1000) + 180);
		stop = startSessionRefreshLifecycle({ getSession: () => session, refreshSession });

		vi.advanceTimersByTime(60_000);

		expect(refreshSession).toHaveBeenCalledOnce();
	});

	it('contains transient refresh failures so a later resume can retry', async () => {
		const refreshSession = vi.fn()
			.mockRejectedValueOnce(new Error('temporary network failure'))
			.mockResolvedValueOnce('refreshed-token');
		const session = realSession(Math.floor(NOW.getTime() / 1000) + 1);
		stop = startSessionRefreshLifecycle({ getSession: () => session, refreshSession });

		await Promise.resolve();
		window.dispatchEvent(new Event('focus'));

		expect(refreshSession).toHaveBeenCalledTimes(2);
	});

	it.each([
		['fresh', realSession(Math.floor(NOW.getTime() / 1000) + 600)],
		['mock', { ...realSession(Math.floor(NOW.getTime() / 1000) + 1), isMock: true }],
		['logging-out', { ...realSession(Math.floor(NOW.getTime() / 1000) + 1), isLoggingOut: true }],
	] as const)('does not refresh a %s session', (_name, session) => {
		const refreshSession = vi.fn().mockResolvedValue('refreshed-token');
		stop = startSessionRefreshLifecycle({ getSession: () => session, refreshSession });

		window.dispatchEvent(new Event('focus'));
		document.dispatchEvent(new Event('visibilitychange'));
		vi.advanceTimersByTime(60_000);

		expect(refreshSession).not.toHaveBeenCalled();
	});

	it('removes resume listeners and the fallback timer on disposal', () => {
		const refreshSession = vi.fn().mockResolvedValue('refreshed-token');
		const session = realSession(Math.floor(NOW.getTime() / 1000) + 1);
		stop = startSessionRefreshLifecycle({ getSession: () => session, refreshSession });
		expect(refreshSession).toHaveBeenCalledOnce();

		stop();
		stop = undefined;
		window.dispatchEvent(new Event('focus'));
		document.dispatchEvent(new Event('visibilitychange'));
		vi.advanceTimersByTime(60_000);

		expect(refreshSession).toHaveBeenCalledOnce();
	});
});
