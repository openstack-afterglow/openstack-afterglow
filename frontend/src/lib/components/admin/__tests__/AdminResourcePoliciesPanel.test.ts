import { fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const apiMocks = vi.hoisted(() => ({ get: vi.fn(), put: vi.fn() }));
const { get, put } = apiMocks;

vi.mock('$lib/api/client', () => ({
	api: apiMocks,
	ApiError: class ApiError extends Error {}
}));

import AdminResourcePoliciesPanel from '../AdminResourcePoliciesPanel.svelte';

async function openBuilderFlavorPicker(): Promise<HTMLButtonElement> {
	const trigger = (await screen.findByRole('button', {
		name: 'Builder flavor 검색 및 선택'
	})) as HTMLButtonElement;
	await waitFor(() => expect(trigger.disabled).toBe(false));
	await fireEvent.click(trigger);
	return trigger;
}

describe('AdminResourcePoliciesPanel', () => {
	let builderOptions: Array<{ id: string; name: string }>;

	beforeEach(() => {
		document.cookie = 'afterglow_resource_policy_draft=; path=/; max-age=0';
		get.mockReset();
		put.mockReset();
		builderOptions = [
			{ id: 'flavor-1', name: 'CPU build' },
			{ id: 'flavor-2', name: 'GPU build' }
		];
		get.mockImplementation((path: string) => {
			if (path === '/api/v1/admin/resource-policies') {
				return Promise.resolve([
					{
						key: 'builder.flavor',
						resource_kind: 'flavor',
						title: 'Builder flavor',
						group: 'Builder',
						help_text: 'Default flavor for service-project builds.',
						execution_scope: 'service',
						dependency: null,
						required_when: null,
						external_only: false,
						shared_only: false,
						state: 'missing',
						resource_id: null,
						resource_name: null
					}
				]);
			}
			if (path === '/api/v1/admin/runtime-settings') {
				return Promise.resolve([
					{
						key: 'k3s.version',
						title: 'K3s version',
						help_text: 'Version used for new K3s clusters.',
						value: 'v1.32.0+k3s1',
						state: 'configured'
					}
				]);
			}
			if (path.endsWith('/catalog/builder.flavor')) {
				return Promise.resolve({ options: builderOptions });
			}
			if (path.includes('/catalog/')) {
				return Promise.resolve({ options: [] });
			}
			return Promise.resolve([]);
		});
		put.mockResolvedValue({ key: 'builder.flavor', resource_id: 'flavor-1', resource_name: 'CPU build' });
	});

	it('discovers an admin-scoped catalog and persists only the selected ID', async () => {
		render(AdminResourcePoliciesPanel, { token: 'token', projectId: 'admin-project' });

		await waitFor(() => expect(get).toHaveBeenCalledWith(
			'/api/v1/admin/resource-policies/catalog/builder.flavor',
			'token',
			'admin-project'
		));
		const trigger = await openBuilderFlavorPicker();
		await fireEvent.click(await screen.findByRole('option', { name: /CPU build/ }));
		expect(document.cookie).toContain('builder.flavor');

		const policyRow = trigger.closest('.policy-row') as HTMLElement | null;
		if (!policyRow) throw new Error('Builder flavor policy row was not rendered');
		await fireEvent.click(within(policyRow).getByRole('button', { name: '저장' }));

		await waitFor(() => expect(put).toHaveBeenCalledWith(
			'/api/v1/admin/resource-policies/builder.flavor',
			{ resource_id: 'flavor-1' },
			'token',
			'admin-project'
		));
		await waitFor(() => expect(document.cookie).not.toContain('builder.flavor'));
	});

	it('selects the only discovered catalog option as an unsaved default', async () => {
		builderOptions = [{ id: 'flavor-only', name: 'Only flavor' }];
		render(AdminResourcePoliciesPanel, { token: 'token', projectId: 'admin-project' });

		await screen.findByText('Only flavor');
		expect(document.cookie).toContain('flavor-only');
		expect(put).not.toHaveBeenCalled();
	});

	it('filters the catalog picker by resource name or ID', async () => {
		render(AdminResourcePoliciesPanel, { token: 'token', projectId: 'admin-project' });

		await openBuilderFlavorPicker();
		const search = screen.getByRole('combobox', { name: '이름 또는 ID로 검색' });
		await fireEvent.input(search, { target: { value: 'gpu' } });
		expect(screen.getByRole('option', { name: /GPU build/ })).toBeTruthy();
		expect(screen.queryByRole('option', { name: /CPU build/ })).toBeNull();

		await fireEvent.input(search, { target: { value: 'flavor-1' } });
		expect(screen.getByRole('option', { name: /CPU build/ })).toBeTruthy();
		expect(screen.queryByRole('option', { name: /GPU build/ })).toBeNull();
	});

	it('retries a failed catalog lookup when the picker opens', async () => {
		const baseGet = get.getMockImplementation();
		if (!baseGet) throw new Error('api.get implementation was not configured');
		let attempts = 0;
		get.mockImplementation((path: string, ...rest: unknown[]) => {
			if (path.endsWith('/catalog/builder.flavor')) {
				attempts += 1;
				if (attempts === 1) return Promise.reject(new Error('catalog unavailable'));
			}
			return baseGet(path, ...rest);
		});
		render(AdminResourcePoliciesPanel, { token: 'token', projectId: 'admin-project' });

		await waitFor(() => expect(attempts).toBe(1));
		await openBuilderFlavorPicker();

		expect(await screen.findByRole('option', { name: /CPU build/ })).toBeTruthy();
		expect(attempts).toBe(2);
	});

	it('clears a selection through the explicit no-selection option', async () => {
		builderOptions = [{ id: 'flavor-only', name: 'Only flavor' }];
		render(AdminResourcePoliciesPanel, { token: 'token', projectId: 'admin-project' });

		await screen.findByText('Only flavor');
		const trigger = await openBuilderFlavorPicker();
		await fireEvent.click(screen.getByRole('option', { name: '선택 안 함' }));

		const policyRow = trigger.closest('.policy-row') as HTMLElement | null;
		if (!policyRow) throw new Error('Builder flavor policy row was not rendered');
		expect(within(policyRow).queryByText('flavor-only')).toBeNull();

		await fireEvent.click(within(policyRow).getByRole('button', { name: '저장' }));
		await waitFor(() => expect(put).toHaveBeenCalledWith(
			'/api/v1/admin/resource-policies/builder.flavor',
			{ resource_id: null },
			'token',
			'admin-project'
		));
	});

	it('supports keyboard navigation and selection in the catalog picker', async () => {
		render(AdminResourcePoliciesPanel, { token: 'token', projectId: 'admin-project' });

		const trigger = await openBuilderFlavorPicker();
		const search = screen.getByRole('combobox', { name: '이름 또는 ID로 검색' });
		await fireEvent.keyDown(search, { key: 'ArrowDown' });
		await fireEvent.keyDown(search, { key: 'ArrowDown' });
		await fireEvent.keyDown(search, { key: 'Enter' });

		expect(trigger.textContent).toContain('GPU build');
		expect(document.cookie).toContain('flavor-2');
		expect(screen.queryByRole('listbox')).toBeNull();
		expect(document.activeElement).toBe(trigger);
	});

	it('renders Drover-owned K3s network and volume policy definitions', async () => {
		render(AdminResourcePoliciesPanel, { token: 'token', projectId: 'admin-project' });

		expect(screen.getByText('K3s volume availability zone')).toBeTruthy();
		expect(screen.getByText('K3s default network')).toBeTruthy();
		await waitFor(() => expect(get).toHaveBeenCalledWith(
			'/api/v1/admin/resource-policies/catalog/k3s.volume_availability_zone',
			'token',
			'admin-project'
		));
		await waitFor(() => expect(get).toHaveBeenCalledWith(
			'/api/v1/admin/resource-policies/catalog/k3s.default_network',
			'token',
			'admin-project'
		));
	});

	it.each([
		['null root', 'null'],
		['null scope', '{"admin-project":null}'],
		['null policies', '{"admin-project":{"policies":null,"runtime":{}}}'],
		['non-string values', '{"admin-project":{"policies":{"builder.flavor":42},"runtime":{"k3s.version":true}}}']
	])('ignores malformed draft cookie: %s', async (_name, rawCookie) => {
		document.cookie = `afterglow_resource_policy_draft=${encodeURIComponent(rawCookie)}; path=/`;
		render(AdminResourcePoliciesPanel, { token: 'token', projectId: 'admin-project' });

		const trigger = (await screen.findByRole('button', {
			name: 'Builder flavor 검색 및 선택'
		})) as HTMLButtonElement;
		await waitFor(() => expect(trigger.textContent).toContain('이름 또는 ID로 검색·선택'));
		await screen.findByText('Builder flavor');
	});

});
