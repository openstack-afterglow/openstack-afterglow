import { fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { get } from 'svelte/store';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { auth, authReady, projectSwitching, logoutInProgress, setAuth } from '$lib/stores/auth';
import { refreshAuthState } from '$lib/utils/authSession';
import { t } from '$lib/i18n/ns/admin-identity';
import { t as td } from '$lib/i18n/ns/domain-admin';
import { t as tp } from '$lib/i18n/ns/compute-pools';
import { t as gpuT } from '$lib/i18n/ns/gpu-quota-requests';
import QuotasPage from '../../../../../routes/admin/quotas/+page.svelte';

const mocks = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), put: vi.fn(), metadata: vi.fn() }));
vi.mock('$lib/api/client', () => ({
	api: { get: mocks.get, post: mocks.post, put: mocks.put, delete: vi.fn() },
	ApiError: class ApiError extends Error {},
}));
vi.mock('$lib/stores/projectNames', () => ({ projectNames: { loadMetadata: mocks.metadata } }));
const originalAuth = get(auth);

describe('quota domain and dependent project pickers', () => {
	beforeEach(() => {
		vi.resetAllMocks();
		projectSwitching.set(false); logoutInProgress.set(false);
		auth.set({ ...originalAuth, token: 'token', userId: 'admin', projectId: 'admin-project', domainId: 'admin-domain', identityDomainId: 'admin-domain', isSystemAdmin: true, sessionId: 'quota-picker-session' });
		authReady.set(true);
		mocks.metadata.mockResolvedValue({ failed: false, projects: [
			{ id: 'p-a', name: 'Same name', domain_id: 'd-a' },
			{ id: 'p-b', name: 'Same name', domain_id: 'd-b' },
			{ id: 'p-unknown', name: 'Unknown domain' },
		] });
		mocks.get.mockImplementation((path: string) => {
			if (path.startsWith('/api/v1/admin/gpu-quota-requests?')) return Promise.resolve({ items: [], next_cursor: null });
			if (path === '/api/v1/admin/domains') return Promise.resolve({ items: [{ id: 'd-a', name: 'Domain A', enabled: true }, { id: 'd-b', name: 'Domain B', enabled: true }] });
			const poolDomain = path.match(/^\/api\/v1\/admin\/domains\/([^/]+)\/compute-pool$/)?.[1];
			if (poolDomain) return Promise.resolve({ domain_id: poolDomain, state: 'unmanaged', revision: 0, enabled: false, limits: {}, project_limits: {}, usage: {}, available: {}, projects: [], policy_ready: false, control_scope: 'afterglow', gpu_profiles: [] });
			return Promise.resolve({ compute: { cores: { limit: 8, in_use: 2 } }, volume: null, network: null, file_storage: null });
		});
		mocks.post.mockResolvedValue({ operations: [], errors: [] });
	});
	it('exposes the GPU review queue before domain selection and opens the existing pool editor without granting quota', async () => {
		const previous = mocks.get.getMockImplementation()!;
		mocks.get.mockImplementation((path: string) => path.startsWith('/api/v1/admin/gpu-quota-requests?') ? Promise.resolve({ items: [{ id: '11111111111111111111111111111111', domain_id: 'd-b', project_id: 'p-b', requester_id: 'manager', gpu_profile_name: 'approved-gpu', resource_class: 'CUSTOM_PCI_10DE_2684', additional: 2, baseline_limit: 1, target_limit: 3, pool_revision: 2, reason: '', status: 'pending', created_at: '2026-10-31T00:00:00Z', reviewer_id: null, reviewed_at: null, note: '' }], next_cursor: null }) : previous(path));
		render(QuotasPage);
		await screen.findByRole('heading', { name: gpuT('queueTitle') });
		await screen.findByText('approved-gpu');
		expect(screen.queryByRole('region', { name: tp('title') })).toBeNull();
		await fireEvent.click(screen.getByRole('button', { name: gpuT('openDomain') }));
		await waitFor(() => expect(mocks.get).toHaveBeenCalledWith('/api/v1/admin/domains/d-b/compute-pool', 'token', 'admin-project', { cache: 'no-store' }));
		expect(screen.getByRole('region', { name: tp('title') })).toBeTruthy();
		expect(mocks.put).not.toHaveBeenCalled(); expect(mocks.post).not.toHaveBeenCalled();
	});


	it('offers all domains independently, filters same-name projects by UUID ownership and removes the old quota form on domain change', async () => {
		render(QuotasPage);
		const domainPicker = await screen.findByRole('button', { name: td('scope.domain') });
		expect(domainPicker.textContent).toContain(td('scope.choose'));
		await fireEvent.click(domainPicker);
		await fireEvent.click(await screen.findByRole('option', { name: /Domain A/ }));
		await fireEvent.click(screen.getByRole('button', { name: t('quotaSelector.label') }));
		expect(await screen.findByRole('option', { name: /p-a/ })).toBeTruthy();
		expect(screen.queryByRole('option', { name: /p-b/ })).toBeNull();
		expect(screen.queryByRole('option', { name: /Unknown domain/ })).toBeNull();
		await fireEvent.click(screen.getByRole('option', { name: /p-a/ }));
		await waitFor(() => expect(screen.getByDisplayValue('8')).toBeTruthy());
		expect(mocks.get).toHaveBeenCalledWith('/api/v1/admin/quotas/p-a', 'token', 'admin-project');

		await fireEvent.click(screen.getByRole('button', { name: td('scope.domain') }));
		await fireEvent.click(await screen.findByRole('option', { name: /Domain B/ }));
		expect(screen.queryByDisplayValue('8')).toBeNull();
		await fireEvent.click(screen.getByRole('button', { name: t('quotaSelector.label') }));
		expect(await screen.findByRole('option', { name: /p-b/ })).toBeTruthy();
		expect(screen.queryByRole('option', { name: /p-a/ })).toBeNull();
		expect(mocks.get).not.toHaveBeenCalledWith('/api/v1/admin/quotas/p-b', expect.anything(), expect.anything());
	});

	it('uses fresh credentials when a ready page changes authority without remounting', async () => {
		render(QuotasPage);
		await screen.findByRole('button', { name: td('scope.domain') });
		auth.set({ ...get(auth), token: 'fresh-token', sessionId: 'replacement-session' });
		authReady.set(true);
		await waitFor(() => expect(mocks.metadata).toHaveBeenLastCalledWith('fresh-token', 'admin-project', 'admin'));
		await waitFor(() => expect(mocks.get).toHaveBeenCalledWith('/api/v1/admin/domains', 'fresh-token', 'admin-project'));
		await screen.findByRole('button', { name: td('scope.domain') });
		await fireEvent.click(screen.getByRole('button', { name: t('quotaSelector.label') }));
		expect(await screen.findByRole('option', { name: /p-a/ })).toBeTruthy();
	});

	it('preserves picker selection and unsaved project quota inputs through a same-session bearer refresh', async () => {
		render(QuotasPage);
		await screen.findByRole('button', { name: td('scope.domain') });
		await fireEvent.click(screen.getByRole('button', { name: t('quotaSelector.label') }));
		await fireEvent.click(await screen.findByRole('option', { name: /p-a/ }));
		const cores = await screen.findByTestId('quota-compute-cores');
		await fireEvent.input(cores, { target: { value: '17' } });
		setAuth(refreshAuthState({
			token: 'refreshed-bearer', user_id: 'admin', username: 'admin',
			domain_id: 'admin-domain', domain_name: 'Admin domain',
			identity_domain_id: 'admin-domain', identity_domain_name: 'Admin domain',
			project_id: 'admin-project', project_name: 'Admin project', expires_at: '2030-01-01T00:00:00Z',
		}, get(auth)));
		expect(get(authReady)).toBe(true);
		await waitFor(() => expect(screen.getByTestId('quota-compute-cores')).toBe(cores));
		expect((cores as HTMLInputElement).value).toBe('17');
		expect(screen.getByRole('button', { name: t('quotaSelector.label') }).textContent).toContain('Same name');
	});

	it.each(['active', 'paused', 'failed', 'pending'] as const)('submits native CPU/RAM edits on the administrator route independently of %s pool lookup', async state => {
		let limits = { cores: 8, ram: 16384 };
		mocks.get.mockImplementation((path: string) => {
			if (path.startsWith('/api/v1/admin/gpu-quota-requests?')) return Promise.resolve({ items: [], next_cursor: null });
			if (path === '/api/v1/admin/domains') return Promise.resolve({ items: [{ id: 'd-a', name: 'Domain A', enabled: true }] });
			if (path.endsWith('/compute-pool')) return state === 'failed' ? Promise.reject(new Error('pool lookup failed')) : state === 'pending' ? new Promise(() => {}) : Promise.resolve({ domain_id: 'd-a', state, enabled: state === 'active', revision: 3, limits: { CPU: 100, MEMORY_MB: 999999 }, project_limits: {}, usage: {}, available: {}, projects: [], policy_ready: true, control_scope: 'afterglow', gpu_profiles: [] });
			if (path === '/api/v1/admin/quotas/p-a') return Promise.resolve({ compute: { cores: { limit: limits.cores, in_use: 2, reserved: 1 }, ram: { limit: limits.ram, in_use: 2048, reserved: 1024 } }, volume: null, network: null, file_storage: null });
			throw new Error(`Unexpected path: ${path}`);
		});
		mocks.put.mockImplementation(async () => { limits = { cores: 12, ram: 24576 }; return { success: true, status: 'updated', updated: ['compute'], errors: {} }; });
		render(QuotasPage);
		await fireEvent.click(await screen.findByRole('button', { name: td('scope.domain') }));
		await fireEvent.click(await screen.findByRole('option', { name: /Domain A/ }));
		await fireEvent.click(screen.getByRole('button', { name: t('quotaSelector.label') }));
		await fireEvent.click(await screen.findByRole('option', { name: /p-a/ }));
		const cores = await screen.findByTestId('quota-compute-cores') as HTMLInputElement;
		expect(cores.value).toBe('8');
		expect((screen.getByTestId('quota-compute-ram') as HTMLInputElement).value).toBe('16384');
		expect(screen.getByRole('region', { name: tp('title') })).toBeTruthy();
		await waitFor(() => expect(mocks.get).toHaveBeenCalledWith('/api/v1/admin/domains/d-a/compute-pool', 'token', 'admin-project', { cache: 'no-store' }));
		if (state === 'active' || state === 'paused') await screen.findByText(tp(`poolState.${state}`));
		if (state === 'failed') await screen.findByText(tp('loadFailed'));
		await fireEvent.input(cores, { target: { value: '12' } });
		await fireEvent.input(screen.getByTestId('quota-compute-ram'), { target: { value: '24576' } });
		await fireEvent.click(screen.getByTestId('save-compute-btn'));
		await waitFor(() => expect(mocks.put).toHaveBeenCalledExactlyOnceWith('/api/v1/admin/quotas/p-a', { cores: 12, ram: 24576 }, 'token', 'admin-project'));
		await waitFor(() => expect((screen.getByTestId('save-compute-btn') as HTMLButtonElement).disabled).toBe(true));
		expect(mocks.get.mock.calls.filter(([path]) => path === '/api/v1/admin/quotas/p-a')).toHaveLength(2);
		expect(get(auth).projectId).toBe('admin-project');
		expect(get(auth).domainId).toBe('admin-domain');
	});
});
