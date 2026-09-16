import { fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { get } from 'svelte/store';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { auth, clearAuth, logoutInProgress, setAuth } from '$lib/stores/auth';

const { goto, api, ApiError, beginSessionRevocation, endSessionRevocation } = vi.hoisted(() => ({
	goto: vi.fn(),
	api: {
		get: vi.fn(),
		delete: vi.fn(),
		post: vi.fn(),
	},
	ApiError: class ApiError extends Error {},
	beginSessionRevocation: vi.fn(() => Promise.resolve(null)),
	endSessionRevocation: vi.fn(),
}));

vi.mock('$app/navigation', () => ({ goto }));
vi.mock('$lib/api/client', () => ({ api, ApiError, beginSessionRevocation, endSessionRevocation }));

import SecuritySection from '../SecuritySection.svelte';

const session = {
	jti: 'session-1',
	origin_ip: '192.0.2.10',
	last_ip: '192.0.2.10',
	last_seen: 1_720_000_000,
	user_agent: 'test-browser',
	blacklisted: false,
};

describe('SecuritySection logout navigation', () => {
	beforeEach(() => {
		vi.clearAllMocks();
		clearAuth();
		logoutInProgress.set(false);
		sessionStorage.clear();
		setAuth({
			token: 'token',
			refreshToken: 'refresh-token',
			userId: 'user',
			username: 'user',
			projectId: 'project',
			projectName: 'Project',
			accessExpiresAt: null,
			roles: [],
		});
		api.get.mockResolvedValue({ sessions: [session], count: 1 });
		api.delete.mockResolvedValue({});
		api.post.mockResolvedValue({});
		goto.mockResolvedValue(undefined);
	});

	afterEach(() => {
		vi.useRealTimers();
	});

	it('replaces history with the login page after removing the final session', async () => {
		api.get
			.mockResolvedValueOnce({ sessions: [session], count: 1 })
			.mockResolvedValueOnce({ sessions: [], count: 0 });
		render(SecuritySection);

		await waitFor(() => expect(screen.getByRole('button', { name: '제거' })).toBeTruthy());
		await fireEvent.click(screen.getByRole('button', { name: '제거' }));
		await fireEvent.click(screen.getByRole('button', { name: '확인' }));

		await waitFor(() => expect(get(auth).token).toBeNull());
		expect(get(logoutInProgress)).toBe(false);
		expect(goto).toHaveBeenCalledWith('/login', { replaceState: true });
	});

	it('replaces history with the login page after logging out every session', async () => {
		render(SecuritySection);

		await fireEvent.click(screen.getByRole('button', { name: '모든 위치에서 로그아웃' }));
		await fireEvent.click(screen.getByRole('button', { name: '확인' }));

		// 지연 없이 곧바로 이동한다. 1.5초 타이머가 다시 들어오면 waitFor 기본 대기 안에
		// goto 가 호출되지 않아 이 단정이 깨진다.
		await waitFor(() => expect(goto).toHaveBeenCalledWith('/login', { replaceState: true }));
		expect(get(auth).token).toBeNull();
		await waitFor(() => expect(get(logoutInProgress)).toBe(false));
	});

});
