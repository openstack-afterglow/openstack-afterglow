import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { get } from 'svelte/store';
import type { Component } from 'svelte';
import { auth } from '$lib/stores/auth';
import { setAdminInventoryScope } from '$lib/stores/adminInventoryScope';
import { projectNames } from '$lib/stores/projectNames';
import { initLocale } from '$lib/i18n/runtime.svelte';
import type { ApiError } from '$lib/api/errors';
import Routers from '../../../../routes/admin/routers/+page.svelte';
import FloatingIps from '../../../../routes/admin/floating-ips/+page.svelte';
import Ports from '../../../../routes/admin/ports/+page.svelte';

const mocks = vi.hoisted(() => ({ get: vi.fn(), prefetch: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn() }));
vi.mock('$lib/api/client', async () => ({ api: mocks, ...(await vi.importActual<{ ApiError: typeof ApiError }>('$lib/api/errors')) }));
vi.mock('$lib/utils/autoRefresh.svelte', () => ({ createAutoRefresh: () => ({ active: false, intervalSeconds: 30, intervalOptions: [15, 30, 60] }) }));
const initial = get(auth);
const foreignExternalNetwork = {
	id: 'external-domain-b', name: 'External Domain B', project_id: 'project-b', is_external: true, is_shared: true,
	status: 'ACTIVE', subnets: [],
};
const pages: { name: string; page: Component; inventoryPath: string }[] = [
	{ name: 'routers', page: Routers, inventoryPath: '/api/v1/admin/all-routers' },
	{ name: 'floating IPs', page: FloatingIps, inventoryPath: '/api/v1/admin/all-floating-ips' },
	{ name: 'ports', page: Ports, inventoryPath: '/api/v1/admin/all-ports' },
];
beforeEach(() => {
	vi.resetAllMocks(); initLocale('en');
	auth.set({ ...initial, token: 'token', sessionId: 'session', userId: 'operator', projectId: 'workspace', domainId: 'home', isSystemAdmin: true });
	setAdminInventoryScope('domain-a', 'project-a'); projectNames.invalidate();
	vi.stubGlobal('matchMedia', vi.fn(() => ({ matches: false, addEventListener: vi.fn(), removeEventListener: vi.fn() })));
	mocks.prefetch.mockResolvedValue(undefined);
	mocks.get.mockImplementation((path: string) => {
		if (path === '/api/v1/admin/all-networks') return Promise.resolve([foreignExternalNetwork]);
		if (path.startsWith('/api/v1/admin/all-networks?')) return Promise.resolve([]);
		if (path === '/api/v1/admin/domains') return Promise.resolve({ items: [{ id: 'domain-a', name: 'Domain A', enabled: true }, { id: 'domain-b', name: 'Domain B', enabled: true }] });
		if (path === '/api/v1/admin/projects/names') return Promise.resolve([{ id: 'project-a', name: 'Project A', domain_id: 'domain-a' }, { id: 'project-b', name: 'Project B', domain_id: 'domain-b' }]);
		if (path.startsWith('/api/v1/admin/all-ports')) return Promise.resolve({ items: [], next_marker: null });
		return Promise.resolve([]);
	});
});
afterEach(() => { cleanup(); auth.set(initial); projectNames.invalidate(); initLocale('ko'); vi.unstubAllGlobals(); });

describe('mutation network options are independent of observation filters', () => {
	it.each(pages)('retains a valid external network from another domain for $name', async ({ name, page, inventoryPath }) => {
		render(page);
		await waitFor(() => expect(mocks.get.mock.calls.some(([path]) => String(path).startsWith(inventoryPath))).toBe(true));
		const listCall = mocks.get.mock.calls.find(([path]) => String(path).startsWith(inventoryPath));
		const listUrl = new URL(String(listCall?.[0]), 'https://test.invalid');
		expect(listUrl.searchParams.get('domain_id')).toBe('domain-a');
		expect(listUrl.searchParams.get('project_id')).toBe('project-a');
		const trigger = screen.getByRole('button', { name: '+ Create' });
		if (name !== 'ports') {
			await fireEvent.pointerEnter(trigger);
			expect(mocks.prefetch).toHaveBeenCalledWith('/api/v1/admin/all-networks', 'token', 'workspace');
		}
		await fireEvent.click(trigger);
		expect(await screen.findByRole('option', { name: 'External Domain B' })).toBeTruthy();
		expect(mocks.get).toHaveBeenCalledWith('/api/v1/admin/all-networks', 'token', 'workspace');
	});
});
