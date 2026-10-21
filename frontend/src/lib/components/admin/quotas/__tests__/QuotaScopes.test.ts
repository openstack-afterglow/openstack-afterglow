import { fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { get } from 'svelte/store';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { auth, authReady, projectSwitching, logoutInProgress, setAuth } from '$lib/stores/auth';
import { refreshAuthState } from '$lib/utils/authSession';
import { t } from '$lib/i18n/ns/admin-identity';
import { t as td } from '$lib/i18n/ns/domain-admin';
import QuotasPage from '../../../../../routes/admin/quotas/+page.svelte';

const mocks = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), metadata: vi.fn() }));
vi.mock('$lib/api/client', () => ({
	api: { get: mocks.get, post: mocks.post, put: vi.fn(), delete: vi.fn() },
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
			if (path === '/api/v1/admin/domains') return Promise.resolve({ items: [{ id: 'd-a', name: 'Domain A', enabled: true }, { id: 'd-b', name: 'Domain B', enabled: true }] });
			if (path === '/api/v1/admin/gpu-aliases') return Promise.resolve({ aliases: [] });
			if (path.includes('/gpu-quotas/')) return Promise.resolve([]);
			return Promise.resolve({ compute: { cores: { limit: 8, in_use: 2 } }, volume: null, network: null, file_storage: null });
		});
		mocks.post.mockResolvedValue({ operations: [], errors: [] });
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
});
