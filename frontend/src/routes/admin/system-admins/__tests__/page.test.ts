import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';
import { tick } from 'svelte';
import { writable } from 'svelte/store';
import { auth } from '$lib/stores/auth';
import { initLocale } from '$lib/i18n/runtime.svelte';

const { mockGet, mockPost, confirm } = vi.hoisted(() => ({ mockGet: vi.fn(), mockPost: vi.fn(), confirm: vi.fn() }));

vi.mock('$lib/api/client', () => ({ api: { get: mockGet, post: mockPost }, ApiError: Error }));
vi.mock('$lib/stores/confirm.svelte', () => ({ confirmDialog: confirm }));
vi.mock('$lib/stores/auth', () => ({
	auth: writable({ token: 'token', projectId: 'project', userId: 'operator', sessionId: 'login', isSystemAdmin: true }),
	authReady: writable(true),
	projectSwitching: writable(false),
	isAdmin: writable(true),
	isMockAuthActive: () => false,
}));

import Page from '../+page.svelte';

const alice = { user_id: 'alice', name: 'Alice', email: 'alice@example.test', enabled: true };
const bob = { user_id: 'bob', name: 'Bob', email: 'bob@example.test', enabled: true };
let admins = [alice];

async function openGrant() {
	await fireEvent.click(screen.getByRole('button', { name: '+ 추가' }));
	const dialog = screen.getByRole('dialog');
	const selector = await within(dialog).findByRole('button', { name: '도메인' });
	await waitFor(() => expect((selector as HTMLButtonElement).disabled).toBe(false));
	await fireEvent.click(selector);
	await fireEvent.click(await screen.findByRole('option', { name: /Tenant/ }));
	await within(dialog).findByText('Bob');
	await fireEvent.click(within(dialog).getByRole('button', { name: '권한 부여' }));
}

describe('system administrator mutation readback', () => {
	beforeEach(() => {
		vi.resetAllMocks();
		initLocale('ko');
		vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(null);
		auth.update(state => ({ ...state, token: 'token', projectId: 'project', userId: 'operator', sessionId: 'login', isSystemAdmin: true }));
		admins = [alice];
		confirm.mockResolvedValue(true);
		mockGet.mockImplementation(async (path: string) => {
			if (path.endsWith('/system-roles')) return [...admins];
			// Deliberately stale: the page must not display a second inventory snapshot.
			if (path.endsWith('/security-policy')) return { system_admin_count: 99 };
			if (path === '/api/v1/admin/domains') return { items: [{ id: 'domain', name: 'Tenant', enabled: true }] };
			if (path.startsWith('/api/v1/admin/users?')) return { items: [{ ...bob, id: bob.user_id }], next_marker: null };
			throw new Error(`unexpected GET ${path}`);
		});
		mockPost.mockImplementation(async (path: string) => {
			admins = path.endsWith('/grant') ? [alice, bob] : [alice];
			return { status: path.endsWith('/grant') ? 'granted' : 'revoked' };
		});
	});

	it('derives the policy count from the exact table snapshot, not a separate policy GET', async () => {
		render(Page);
		await screen.findByText('Alice');
		expect((await screen.findByText(/system:all/)).textContent).toContain('(1명)');
		expect(mockGet).toHaveBeenCalledTimes(1);
	});

	it.each([false, true])('forces grant readback and shows success with token rotation=%s', async rotate => {
		const pending = Promise.withResolvers<{ status: string }>();
		mockPost.mockReturnValue(pending.promise);
		render(Page);
		await screen.findByText('Alice');
		await openGrant();
		if (rotate) {
			auth.update(state => ({ ...state, token: 'rotated-token' }));
			await tick();
		}
		admins = [alice, bob];
		pending.resolve({ status: 'granted' });
		await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
		expect(await screen.findByText('시스템 관리자 권한을 부여했습니다.')).toBeTruthy();
		expect(await screen.findByText('Bob')).toBeTruthy();
		expect(screen.getByText(/system:all/).textContent).toContain('(2명)');
		expect(mockGet).toHaveBeenLastCalledWith('/api/v1/admin/identity/system-roles', rotate ? 'rotated-token' : 'token', 'project', { refresh: true });

		admins = [alice];
		await fireEvent.click(screen.getByRole('button', { name: '지금 새로고침' }));
		await waitFor(() => expect(screen.queryByText('Bob')).toBeNull());
		expect(screen.getByText(/system:all/).textContent).toContain('(1명)');
		expect(screen.queryByText('시스템 관리자 권한을 부여했습니다.')).toBeNull();
		expect(mockGet).toHaveBeenLastCalledWith('/api/v1/admin/identity/system-roles', rotate ? 'rotated-token' : 'token', 'project', { refresh: true });
	});

	it('keeps a failed grant visible after token rotation', async () => {
		const pending = Promise.withResolvers<never>();
		mockPost.mockReturnValue(pending.promise);
		render(Page);
		await screen.findByText('Alice');
		await openGrant();
		auth.update(state => ({ ...state, token: 'rotated-token' }));
		await tick();
		pending.reject(new Error('native grant denied'));
		expect((await screen.findByRole('alert')).textContent).toContain('native grant denied');
		expect(screen.getByRole('dialog')).toBeTruthy();
	});

	it.each([false, true])('forces revoke readback and shows success with token rotation=%s', async rotate => {
		const pending = Promise.withResolvers<{ status: string }>();
		mockPost.mockReturnValue(pending.promise);
		admins = [alice, bob];
		render(Page);
		await screen.findByText('Bob');
		const row = screen.getByText('Bob').closest('tr')!;
		await fireEvent.click(within(row).getByRole('button', { name: '회수' }));
		if (rotate) {
			auth.update(state => ({ ...state, token: 'rotated-token' }));
			await tick();
		}
		admins = [alice];
		pending.resolve({ status: 'revoked' });
		await waitFor(() => expect(screen.queryByText('Bob')).toBeNull());
		expect(await screen.findByText('시스템 관리자 권한을 회수했습니다.')).toBeTruthy();
		expect(screen.getByText(/system:all/).textContent).toContain('(1명)');
		expect(mockGet).toHaveBeenLastCalledWith('/api/v1/admin/identity/system-roles', rotate ? 'rotated-token' : 'token', 'project', { refresh: true });
	});

	it('keeps a failed revoke visible after token rotation', async () => {
		const pending = Promise.withResolvers<never>();
		mockPost.mockReturnValue(pending.promise);
		admins = [alice, bob];
		render(Page);
		await screen.findByText('Bob');
		await fireEvent.click(within(screen.getByText('Bob').closest('tr')!).getByRole('button', { name: '회수' }));
		auth.update(state => ({ ...state, token: 'rotated-token' }));
		await tick();
		pending.reject(new Error('native revoke denied'));
		expect((await screen.findByRole('alert')).textContent).toContain('native revoke denied');
		expect(screen.getByText('Bob')).toBeTruthy();
	});

	it('does not revoke itself when confirmation is cancelled', async () => {
		admins = [alice, bob];
		auth.update(state => ({ ...state, userId: alice.user_id }));
		confirm.mockResolvedValue(false);
		render(Page);
		await screen.findByText('Alice');
		await fireEvent.click(within(screen.getByText('Alice').closest('tr')!).getByRole('button', { name: '회수' }));
		expect(confirm).toHaveBeenCalledOnce();
		expect(mockPost).not.toHaveBeenCalled();
	});

	it('leaves the last administrator revoke disabled', async () => {
		render(Page);
		await screen.findByText('Alice');
		const row = within(screen.getByText('Alice').closest('tr')!);
		expect(row.queryByRole('button', { name: '회수' })).toBeNull();
		expect(row.getByTitle('마지막 system admin은 회수할 수 없습니다')).toBeTruthy();
	});

	it('rejects a late list across a same-tick scope ABA transition', async () => {
		const pending = Promise.withResolvers<typeof admins>();
		mockGet.mockReturnValueOnce(pending.promise);
		render(Page);
		await waitFor(() => expect(mockGet).toHaveBeenCalledOnce());
		auth.update(state => ({ ...state, projectId: 'other-project' }));
		auth.update(state => ({ ...state, projectId: 'project' }));
		admins = [bob];
		await screen.findByText('Bob');
		pending.resolve([alice]);
		await tick();
		expect(screen.queryByText('Alice')).toBeNull();
	});

	it('preserves an in-flight read across token renewal', async () => {
		const pending = Promise.withResolvers<typeof admins>();
		mockGet.mockReturnValue(pending.promise);
		render(Page);
		await waitFor(() => expect(mockGet).toHaveBeenCalled());
		auth.update(state => ({ ...state, token: 'rotated-token' }));
		await tick();
		pending.resolve([alice]);
		expect(await screen.findByText('Alice')).toBeTruthy();
	});

	it('shows lockout recovery only for a verified empty list', async () => {
		admins = [];
		render(Page);
		expect(await screen.findByText('Lockout 위험')).toBeTruthy();
		expect(screen.getByRole('alert').textContent).toContain('system:all');
	});

	it('does not substitute an empty policy when the inventory fails', async () => {
		mockGet.mockRejectedValue(new Error('native system-role access denied'));
		render(Page);
		expect(await screen.findByText('native system-role access denied')).toBeTruthy();
		expect(screen.queryByText('Lockout 위험')).toBeNull();
		expect(screen.queryByText(/system:all/)).toBeNull();
	});
});
