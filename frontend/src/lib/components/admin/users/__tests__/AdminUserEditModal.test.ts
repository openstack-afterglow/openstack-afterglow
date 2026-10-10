import { fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { writable } from 'svelte/store';

const mocks = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }));
vi.mock('$lib/api/client', () => ({
	api: mocks,
	ApiError: class ApiError extends Error {},
}));
vi.mock('$lib/stores/auth', () => ({ auth: writable({ token: 'token', projectId: 'admin-project' }) }));

import AdminUserEditModal from '../AdminUserEditModal.svelte';

const user = { id: 'user-1', name: 'Alice', email: 'alice@example.test', enabled: true, domain_id: null, default_project_id: null, created_at: null };

describe('administrator user session revocation', () => {
	beforeEach(() => {
		mocks.get.mockReset().mockResolvedValue({ sessions: [], count: 0 });
		mocks.post.mockReset();
	});

	it('keeps revocation visible after the confirmation closes until the request settles', async () => {
		const request = Promise.withResolvers<{ revoked_count: number }>();
		mocks.post.mockReturnValueOnce(request.promise);
		render(AdminUserEditModal, { user, onUpdate: vi.fn() });
		await screen.findByText('활성 세션 없음');
		await fireEvent.click(screen.getByRole('button', { name: '전체 세션 강제 폐기 (Keystone 직접 폐기 포함)' }));
		await fireEvent.click(screen.getByRole('button', { name: '확인' }));

		const busyButton = screen.getByRole('button', { name: '폐기 중...' });
		expect(busyButton.getAttribute('aria-busy')).toBe('true');
		expect((busyButton as HTMLButtonElement).disabled).toBe(true);
		expect(screen.getByRole('status').textContent).toContain('폐기 중...');
		expect(screen.queryByRole('button', { name: '확인' })).toBeNull();

		request.resolve({ revoked_count: 2 });
		expect(await screen.findByText('세션 2개가 폐기되었습니다.')).toBeTruthy();
		await waitFor(() => expect(screen.queryByText('폐기 중...')).toBeNull());
		expect(screen.getByRole('button', { name: '전체 세션 강제 폐기 (Keystone 직접 폐기 포함)' }).getAttribute('aria-busy')).toBe('false');
	});
});
