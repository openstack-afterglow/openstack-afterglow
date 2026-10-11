import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { writable } from 'svelte/store';
import { tick } from 'svelte';
import { setLocale } from '$lib/i18n/runtime.svelte';
import { t } from '$lib/i18n/ns/admin-network';
import type { AdminSubnetDetail } from '$lib/types/networks';

const { mockGet } = vi.hoisted(() => ({ mockGet: vi.fn() }));
vi.mock('$lib/api/client', () => ({
	api: { get: mockGet },
	ApiError: class ApiError extends Error { status = 503; },
}));
vi.mock('$lib/stores/auth', () => ({
	auth: writable({ token: 'token-a', userId: 'user-a', projectId: 'project-a' }),
}));
import { auth } from '$lib/stores/auth';
import SubnetIpInventory from '../SubnetIpInventory.svelte';
import { subnetFixture } from './subnetFixture';

const initialAuth = { token: 'token-a', userId: 'user-a', projectId: 'project-a' };
function deferred<T>() {
	let resolve!: (value: T) => void;
	let reject!: (reason: Error) => void;
	const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no; });
	return { promise, resolve, reject };
}
function setAuth(value: typeof initialAuth) {
	auth.set(value as Parameters<typeof auth.set>[0]);
}
beforeEach(() => {
	mockGet.mockReset();
	setAuth(initialAuth);
	setLocale('en');
});

describe('per-subnet inventory request lifecycle', () => {
	it('shows loading, a real failure, retry and a refreshed authoritative inventory', async () => {
		const request = deferred<AdminSubnetDetail>();
		mockGet.mockReturnValueOnce(request.promise).mockResolvedValueOnce(subnetFixture);
		render(SubnetIpInventory, { subnetId: 'sub-100' });
		expect(await screen.findByText(t('subnetDetailPage.loading'))).toBeTruthy();
		request.reject(new Error('Authoritative ports failed'));
		expect(await screen.findByText('Authoritative ports failed')).toBeTruthy();
		expect(screen.queryByText(t('subnetDetailPage.allocationsEmpty'))).toBeNull();
		await fireEvent.click(screen.getByRole('button', { name: t('subnetDetailPage.retry') }));
		expect(await screen.findByText('10.200.0.15')).toBeTruthy();
		expect(screen.queryByText('Authoritative ports failed')).toBeNull();
	});

	it('keeps current rows and pagination through refresh loading, failure, retry and success', async () => {
		const allocations = Array.from({ length: 21 }, (_, i) => ({ ...subnetFixture.allocations[0], ip_address: `10.200.0.${101 + i}` }));
		const detail = { ...subnetFixture, allocations };
		const refresh = deferred<AdminSubnetDetail>();
		mockGet.mockResolvedValueOnce(detail).mockReturnValueOnce(refresh.promise).mockResolvedValueOnce({ ...detail });
		render(SubnetIpInventory, { subnetId: 'sub-100' });
		await screen.findByText('10.200.0.101');
		await fireEvent.click(screen.getByRole('button', { name: /Next/ }));
		expect(screen.getByText('10.200.0.121')).toBeTruthy();
		await fireEvent.click(screen.getByRole('button', { name: t('subnetDetailPage.refresh') }));
		expect(screen.getByText('10.200.0.121')).toBeTruthy();
		refresh.reject(new Error('Refresh unavailable'));
		await screen.findByText('Refresh unavailable');
		expect(screen.getByText('10.200.0.121')).toBeTruthy();
		await fireEvent.click(screen.getByRole('button', { name: t('subnetDetailPage.retry') }));
		await waitFor(() => expect(screen.queryByText('Refresh unavailable')).toBeNull());
		expect(screen.getByText('10.200.0.121')).toBeTruthy();
		expect(screen.queryByText('10.200.0.101')).toBeNull();
	});

	it.each(['success', 'failure'] as const)('ignores late old-target %s without clearing current loading', async (outcome) => {
		const old = deferred<AdminSubnetDetail>();
		const current = deferred<AdminSubnetDetail>();
		mockGet.mockReturnValueOnce(old.promise).mockReturnValueOnce(current.promise);
		const view = render(SubnetIpInventory, { subnetId: 'sub-100' });
		await waitFor(() => expect(mockGet).toHaveBeenCalledTimes(1));
		await view.rerender({ subnetId: 'sub-next' });
		await waitFor(() => expect(mockGet).toHaveBeenCalledTimes(2));
		if (outcome === 'success') old.resolve(subnetFixture); else old.reject(new Error('Old target failure'));
		await tick();
		expect(screen.queryByText('10.200.0.15')).toBeNull();
		expect(screen.queryByText('Old target failure')).toBeNull();
		expect(screen.getByRole('button', { name: t('subnetDetailPage.refresh') }).hasAttribute('disabled')).toBe(true);
		current.resolve({ ...subnetFixture, id: 'sub-next', allocations: [{ ...subnetFixture.allocations[0], ip_address: '10.200.0.99' }] });
		expect(await screen.findByText('10.200.0.99')).toBeTruthy();
	});

	it.each(['token', 'userId', 'projectId'] as const)('fences late old-auth responses on %s change', async (field) => {
		const old = deferred<AdminSubnetDetail>();
		mockGet.mockReturnValueOnce(old.promise).mockResolvedValueOnce({ ...subnetFixture, allocations: [{ ...subnetFixture.allocations[0], ip_address: '10.200.0.99' }] });
		render(SubnetIpInventory, { subnetId: 'sub-100' });
		await waitFor(() => expect(mockGet).toHaveBeenCalledTimes(1));
		setAuth({ ...initialAuth, [field]: `${field}-new` });
		expect(await screen.findByText('10.200.0.99')).toBeTruthy();
		old.resolve(subnetFixture);
		await tick();
		expect(screen.queryByText('10.200.0.15')).toBeNull();
		expect(screen.getByText('10.200.0.99')).toBeTruthy();
	});

	it('removes previously loaded data on an auth transition before publishing the new response', async () => {
		const next = deferred<AdminSubnetDetail>();
		mockGet.mockResolvedValueOnce(subnetFixture).mockReturnValueOnce(next.promise);
		render(SubnetIpInventory, { subnetId: 'sub-100' });
		await screen.findByText('10.200.0.15');
		setAuth({ ...initialAuth, projectId: 'project-next' });
		await tick();
		expect(screen.queryByText('10.200.0.15')).toBeNull();
		expect(screen.queryByText('web-instance')).toBeNull();
		next.reject(new Error('New scope denied'));
		expect(await screen.findByText('New scope denied')).toBeTruthy();
		expect(screen.queryByText('10.200.0.15')).toBeNull();
	});

	it('does not fetch without a token and invalidates pending data on logout', async () => {
		auth.set({ ...initialAuth, token: null } as Parameters<typeof auth.set>[0]);
		const pending = deferred<AdminSubnetDetail>();
		mockGet.mockReturnValueOnce(pending.promise);
		render(SubnetIpInventory, { subnetId: 'sub-100' });
		await tick();
		expect(mockGet).not.toHaveBeenCalled();
		setAuth(initialAuth);
		await waitFor(() => expect(mockGet).toHaveBeenCalledTimes(1));
		auth.set({ ...initialAuth, token: null } as Parameters<typeof auth.set>[0]);
		await tick();
		pending.resolve(subnetFixture);
		await tick();
		expect(screen.queryByText('10.200.0.15')).toBeNull();
		expect(screen.queryByText(t('subnetDetailPage.allocationsEmpty'))).toBeNull();
	});

	it('does not expose a response after collapse/unmount and reloads a fresh mount', async () => {
		const pending = deferred<AdminSubnetDetail>();
		mockGet.mockReturnValueOnce(pending.promise).mockResolvedValueOnce({ ...subnetFixture, allocations: [{ ...subnetFixture.allocations[0], ip_address: '10.200.0.99' }] });
		const first = render(SubnetIpInventory, { subnetId: 'sub-100' });
		await waitFor(() => expect(mockGet).toHaveBeenCalledTimes(1));
		first.unmount();
		render(SubnetIpInventory, { subnetId: 'sub-100' });
		await screen.findByText('10.200.0.99');
		pending.resolve(subnetFixture);
		await tick();
		expect(screen.queryByText('10.200.0.15')).toBeNull();
	});
});
