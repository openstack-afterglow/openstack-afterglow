import { fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { tick } from 'svelte';
import { get as getStore } from 'svelte/store';
import { acceptAuthVerification, auth, authReady, getAuthVerificationEpoch, setAuth } from '$lib/stores/auth';
import { refreshAuthState } from '$lib/utils/authSession';
import { siteConfig } from '$lib/config/site';
import type * as ApiErrors from '$lib/api/errors';

const apiMocks = vi.hoisted(() => ({ get: vi.fn(), put: vi.fn() }));
const { get, put } = apiMocks;

vi.mock('$lib/api/client', async () => {
	const { ApiError } = await vi.importActual<typeof ApiErrors>('$lib/api/errors');
	return { api: apiMocks, ApiError };
});

import AdminResourcePoliciesPanel from '../AdminResourcePoliciesPanel.svelte';
import { t } from '$lib/i18n/ns/admin-system';
import { ApiError } from '$lib/api/errors';

async function openBuilderFlavorPicker(): Promise<HTMLButtonElement> {
	const trigger = (await screen.findByRole('button', {
		name: t('policies.searchLabel', { title: t('policies.definition.builderFlavor.title') })
	})) as HTMLButtonElement;
	await waitFor(() => expect(trigger.disabled).toBe(false));
	await fireEvent.click(trigger);
	return trigger;
}

function establishVerifiedAdmin() {
	auth.set({
		...getStore(auth), sessionId: 'policy-admin-session', token: 'token', refreshToken: 'refresh-token',
		userId: 'admin', username: 'Admin', domainId: 'home', domainName: 'Home',
		identityDomainId: 'home', identityDomainName: 'Home', projectId: 'admin-project',
		projectName: 'Admin project', roles: ['admin'], isSystemAdmin: true, canWrite: true,
		isDomainManager: false, canCreateDomain: false,
	});
	expect(acceptAuthVerification(getAuthVerificationEpoch(), {})).toBe(true);
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
				return Promise.resolve({ policies: [
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
					},
					{
						key: 'waygate.image', state: 'configured', resource_id: 'image-saved',
						resource_name: 'Saved Waygate image'
					}
				], errors: [] });
			}
			if (path === '/api/v1/admin/runtime-settings') {
				return Promise.resolve({ settings: [
					{
						key: 'k3s.version',
						title: 'K3s version',
						help_text: 'Version used for new K3s clusters.',
						value: 'v1.32.0+k3s1',
						state: 'configured'
					},
					{ key: 'notion.sync_enabled', value: false, state: 'configured' }
				], errors: [] });
			}
			if (path.includes('/resource-policies/catalog?')) {
				const keys = new URL(path, 'http://fixture.test').searchParams.getAll('keys');
				return Promise.resolve({ catalogs: keys.map((key) => ({
					key, options: key === 'builder.flavor' ? builderOptions : []
				})) });
			}
			if (path.includes('/resource-policies/catalog/')) {
				return Promise.resolve({ key: path.split('/').at(-1), options: [] });
			}
			return Promise.resolve([]);
		});
		put.mockResolvedValue({ key: 'builder.flavor', resource_id: 'flavor-1', resource_name: 'CPU build' });
	});

	it.each(['stale', 'unavailable'] as const)('retains edit semantics for an actually returned local policy whose state is %s', async (state) => {
		const baseGet = get.getMockImplementation()!;
		get.mockImplementation(async (path: string, ...rest: unknown[]) => {
			const result = await baseGet(path, ...rest);
			return path === '/api/v1/admin/resource-policies'
				? { ...result, policies: result.policies.map((policy: { key: string }) => policy.key === 'builder.flavor'
					? { ...policy, state, resource_id: 'old-flavor' }
					: policy) }
				: result;
		});
		render(AdminResourcePoliciesPanel, { token: 'token', projectId: 'admin-project' });
		const picker = await openBuilderFlavorPicker();
		await fireEvent.click(await screen.findByRole('option', { name: /CPU build/ }));
		const save = within(picker.closest('.policy-row')!).getByRole('button', { name: t('policies.save') }) as HTMLButtonElement;
		expect(save.disabled).toBe(false);
		await fireEvent.click(save);
		await waitFor(() => expect(put).toHaveBeenCalledWith(
			'/api/v1/admin/resource-policies/builder.flavor', { resource_id: 'flavor-1' }, 'token', 'admin-project'
		));
	});

	it('blocks Drover policy discovery and writes without blocking the local builder', async () => {
		const baseGet = get.getMockImplementation()!;
		get.mockImplementation(async (path: string, ...rest: unknown[]) => {
			const result = await baseGet(path, ...rest);
			return path === '/api/v1/admin/resource-policies'
				? {
					policies: [...result.policies, { key: 'k3s.server_image', state: 'configured', resource_id: 'k3s-saved' }],
					errors: [{ service: 'drover', status: 403 }]
				}
				: result;
		});
		render(AdminResourcePoliciesPanel, { token: 'token', projectId: 'admin-project' });
		await openBuilderFlavorPicker();
		const row = screen.getByText('k3s.server_image').closest<HTMLElement>('.policy-row')!;
		const failure = within(row).getByRole('alert');
		expect(failure.textContent).toContain('Drover');
		expect(failure.textContent).toContain(t('policies.state.unavailable'));
		expect(failure.textContent).toContain('403');
		expect(within(row).queryByText(t('policies.catalogFailed'))).toBeNull();
		expect(within(row).queryByText('k3s-saved')).toBeNull();
		const picker = within(row).getByRole('button', { name: t('policies.searchLabel', { title: t('policies.definition.k3sServerImage.title') }) }) as HTMLButtonElement;
		expect(picker.disabled).toBe(true);
		await fireEvent.click(picker);
		await fireEvent.click(within(row).getByRole('button', { name: t('policies.save') }));
		expect(get.mock.calls.some(([path]) => path.includes('/catalog/k3s.'))).toBe(false);
		expect(put).not.toHaveBeenCalled();
	});

	it('keeps a local draft and catalog usable while failed Waygate policies stay unavailable', async () => {
		const baseGet = get.getMockImplementation()!;
		get.mockImplementation(async (path: string, ...rest: unknown[]) => {
			const result = await baseGet(path, ...rest);
			if (path === '/api/v1/admin/resource-policies') {
				return { ...result, errors: [{ service: 'waygate', status: 503 }] };
			}
			return result;
		});
		render(AdminResourcePoliciesPanel, { token: 'token', projectId: 'admin-project' });

		const trigger = await openBuilderFlavorPicker();
		await fireEvent.click(await screen.findByRole('option', { name: /GPU build/ }));
		expect(trigger.textContent).toContain('GPU build');
		expect(document.cookie).toContain('flavor-2');
		for (const key of ['waygate.image', 'waygate.flavor', 'waygate.provider_network', 'waygate.floating_network']) {
			const row = screen.getByText(key).closest<HTMLElement>('.policy-row')!;
			const failure = within(row).getByRole('alert');
			expect(failure.textContent).toContain('Waygate');
			expect(failure.textContent).toContain(t('policies.state.unavailable'));
			expect(failure.textContent).toContain('503');
			expect(within(row).queryByText(t('policies.catalogFailed'))).toBeNull();
			expect(within(row.querySelector<HTMLElement>('.policy-copy')!).getByText(new RegExp(t('policies.state.unavailable')))).toBeTruthy();
			expect(within(row).queryByText('image-saved')).toBeNull();
			const picker = within(row).getByRole('button', { name: /검색/ }) as HTMLButtonElement;
			const save = within(row).getByRole('button', { name: t('policies.save') }) as HTMLButtonElement;
			expect(picker.disabled).toBe(true);
			expect(save.disabled).toBe(true);
			await fireEvent.click(picker);
			await fireEvent.click(save);
		}
		expect(get.mock.calls.some(([path]) => path.includes('/catalog/waygate.'))).toBe(false);
		expect(put).not.toHaveBeenCalled();

		put.mockResolvedValueOnce({ key: 'builder.flavor', resource_id: 'flavor-2', resource_name: 'GPU build' });
		await fireEvent.click(within(trigger.closest('.policy-row')!).getByRole('button', { name: t('policies.save') }));
		await waitFor(() => expect(put).toHaveBeenCalledWith(
			'/api/v1/admin/resource-policies/builder.flavor', { resource_id: 'flavor-2' }, 'token', 'admin-project'
		));
		expect(get.mock.calls.filter(([path]) => path === '/api/v1/admin/resource-policies')).toHaveLength(1);
		expect(get.mock.calls.some(([path]) => path.includes('/catalog/waygate.'))).toBe(false);
	});

	it.each([
		['waygate.image', 'Waygate', 'response'],
		['waygate.image', 'Waygate', 'http'],
		['waygate.image', 'Waygate', 'network'],
		['k3s.server_image', 'Drover', 'response'],
		['k3s.server_image', 'Drover', 'http'],
		['k3s.server_image', 'Drover', 'network']
	] as const)('keeps local and sibling catalogs usable when %s has a %s %s catalog failure', async (key, service, failureKind) => {
		const baseGet = get.getMockImplementation()!;
		let failing = true;
		get.mockImplementation(async (path: string, ...rest: unknown[]) => {
			if (path === `/api/v1/admin/resource-policies/catalog/${key}`) {
				if (!failing) return { key, options: [{ id: 'recovered-image', name: 'Recovered image' }] };
				if (failureKind === 'http') throw new ApiError(503, 'private upstream URL/token detail');
				if (failureKind === 'network') throw new Error('private upstream URL/token detail');
				return { key, error: { status: 503, detail: 'private upstream URL/token detail' } };
			}
			if (path.endsWith('/catalog/waygate.flavor')) {
				return { key: 'waygate.flavor', options: [{ id: 'remote-flavor', name: 'Healthy remote flavor' }] };
			}
			const result = await baseGet(path, ...rest);
			if (path === '/api/v1/admin/resource-policies') {
				return {
					...result,
					policies: [...result.policies,
						...(key.startsWith('k3s.') ? [{ key, state: 'configured', resource_id: 'saved-k3s-image' }] : []),
						{ key: 'waygate.flavor', state: 'missing', resource_id: null }
					]
				};
			}
			return result;
		});
		render(AdminResourcePoliciesPanel, { token: 'token', projectId: 'admin-project' });
		const builder = await openBuilderFlavorPicker();
		await fireEvent.click(await screen.findByRole('option', { name: /GPU build/ }));
		const row = screen.getByText(key).closest<HTMLElement>('.policy-row')!;
		const failure = await within(row).findByRole('alert');
		expect(failure.textContent).toContain(service);
		expect(failure.textContent).toContain(t('policies.state.unavailable'));
		if (failureKind === 'network') expect(failure.textContent).not.toContain('HTTP');
		else expect(failure.textContent).toContain('503');
		expect(within(row).queryByText(t('policies.catalogFailed'))).toBeNull();
		expect(screen.queryByText('private upstream URL/token detail')).toBeNull();
		expect(await screen.findByText('Healthy remote flavor')).toBeTruthy();
		const sibling = screen.getByText('waygate.flavor').closest<HTMLElement>('.policy-row')!;
		expect(within(sibling).queryByRole('alert')).toBeNull();
		expect((within(sibling).getByRole('button', { name: t('policies.save') }) as HTMLButtonElement).disabled).toBe(false);
		put.mockResolvedValueOnce({ key: 'builder.flavor', resource_id: 'flavor-2', resource_name: 'GPU build' });
		await fireEvent.click(within(builder.closest<HTMLElement>('.policy-row')!).getByRole('button', { name: t('policies.save') }));
		await waitFor(() => expect(put).toHaveBeenCalledWith(
			'/api/v1/admin/resource-policies/builder.flavor', { resource_id: 'flavor-2' }, 'token', 'admin-project'
		));
		failing = false;
		await fireEvent.click(within(row).getByRole('button', {
			name: t('policies.searchLabel', { title: t(key === 'waygate.image'
				? 'policies.definition.waygateImage.title' : 'policies.definition.k3sServerImage.title') })
		}));
		expect(await screen.findByRole('option', { name: /Recovered image/ })).toBeTruthy();
		expect(within(row).queryByRole('alert')).toBeNull();
		expect(get.mock.calls.filter(([path]) => path === `/api/v1/admin/resource-policies/catalog/${key}`)).toHaveLength(2);
		expect(put).toHaveBeenCalledTimes(1);
	});

	it.each([true, false])('requires an explicit boolean choice before saving an actually returned unset Notion setting as %s', async (choice) => {
		const baseGet = get.getMockImplementation()!;
		get.mockImplementation(async (path: string, ...rest: unknown[]) => {
			const result = await baseGet(path, ...rest);
			return path === '/api/v1/admin/runtime-settings'
				? { settings: [{ key: 'notion.sync_enabled', value: null, state: 'missing' }], errors: [] }
				: result;
		});
		render(AdminResourcePoliciesPanel, { token: 'token', projectId: 'admin-project' });
		await openBuilderFlavorPicker();
		const row = screen.getByText('notion.sync_enabled').closest<HTMLElement>('.runtime-row')!;
		const toggle = within(row).getByRole('combobox') as HTMLSelectElement;
		expect(toggle.disabled).toBe(false);
		expect(toggle.value).toBe('');
		expect(toggle.selectedOptions[0].textContent).toBe(t('policies.state.missing'));
		expect(within(row).queryByText(t('policies.state.unavailable'))).toBeNull();
		const save = within(row).getByRole('button', { name: t('policies.save') }) as HTMLButtonElement;
		expect(save.disabled).toBe(true);
		await fireEvent.click(save);
		expect(put).not.toHaveBeenCalled();
		await fireEvent.change(toggle, { target: { value: String(choice) } });
		expect(save.disabled).toBe(false);
		put.mockResolvedValueOnce({ key: 'notion.sync_enabled', value: choice, state: 'configured' });
		await fireEvent.click(save);
		await waitFor(() => expect(put).toHaveBeenCalledWith(
			'/api/v1/admin/runtime-settings/notion.sync_enabled', { value: choice }, 'token', 'admin-project'
		));
		expect(put).toHaveBeenCalledTimes(1);
	});

	it.each([true, false])('retains an explicitly configured Notion value of %s', async (value) => {
		const baseGet = get.getMockImplementation()!;
		get.mockImplementation(async (path: string, ...rest: unknown[]) => {
			const result = await baseGet(path, ...rest);
			return path === '/api/v1/admin/runtime-settings'
				? { settings: [{ key: 'notion.sync_enabled', value, state: 'configured' }], errors: [] }
				: result;
		});
		render(AdminResourcePoliciesPanel, { token: 'token', projectId: 'admin-project' });
		await openBuilderFlavorPicker();
		const row = screen.getByText('notion.sync_enabled').closest<HTMLElement>('.runtime-row')!;
		const toggle = within(row).getByRole('combobox') as HTMLSelectElement;
		expect(toggle.value).toBe(String(value));
		expect(toggle.selectedOptions[0].textContent).toBe(t(value ? 'policies.enabled' : 'policies.disabled'));
		expect(toggle.disabled).toBe(false);
		expect((within(row).getByRole('button', { name: t('policies.save') }) as HTMLButtonElement).disabled).toBe(false);
		expect(put).not.toHaveBeenCalled();
	});

	it.each(['omitted', 'unavailable'] as const)('keeps an %s Notion setting unknown and write-disabled', async (state) => {
		const baseGet = get.getMockImplementation()!;
		get.mockImplementation(async (path: string, ...rest: unknown[]) => {
			const result = await baseGet(path, ...rest);
			return path === '/api/v1/admin/runtime-settings'
				? { settings: state === 'omitted' ? [] : [{ key: 'notion.sync_enabled', value: null, state }], errors: [] }
				: result;
		});
		render(AdminResourcePoliciesPanel, { token: 'token', projectId: 'admin-project' });
		await openBuilderFlavorPicker();
		const row = screen.getByText('notion.sync_enabled').closest<HTMLElement>('.runtime-row')!;
		const toggle = within(row).getByRole('combobox') as HTMLSelectElement;
		expect(toggle.disabled).toBe(true);
		expect(toggle.value).toBe('');
		expect(toggle.selectedOptions[0].textContent).toBe(t('policies.state.unavailable'));
		const save = within(row).getByRole('button', { name: t('policies.save') }) as HTMLButtonElement;
		expect(save.disabled).toBe(true);
		await fireEvent.change(toggle, { target: { value: 'true' } });
		await fireEvent.click(save);
		expect(put).not.toHaveBeenCalled();
	});

	it('keeps local Notion editable when Drover runtime settings fail', async () => {
		const baseGet = get.getMockImplementation()!;
		get.mockImplementation(async (path: string, ...rest: unknown[]) => {
			const result = await baseGet(path, ...rest);
			return path === '/api/v1/admin/runtime-settings'
				? { ...result, errors: [{ service: 'drover', status: 503 }] }
				: result;
		});
		render(AdminResourcePoliciesPanel, { token: 'token', projectId: 'admin-project' });
		await openBuilderFlavorPicker();
		const droverRow = screen.getByText('k3s.version').closest<HTMLElement>('.runtime-row')!;
		const failure = within(droverRow).getByRole('alert');
		expect(failure.textContent).toContain('Drover');
		expect(failure.textContent).toContain(t('policies.state.unavailable'));
		expect(failure.textContent).toContain('503');
		expect(within(droverRow).getByText(t('policies.state.unavailable'))).toBeTruthy();
		const version = within(droverRow).getByRole('textbox') as HTMLInputElement;
		expect(version.disabled).toBe(true);
		expect(version.value).toBe('');
		await fireEvent.input(version, { target: { value: 'unverified-version' } });
		await fireEvent.click(within(droverRow).getByRole('button', { name: t('policies.save') }));
		expect(put).not.toHaveBeenCalled();
		const notionRow = screen.getByText('notion.sync_enabled').closest<HTMLElement>('.runtime-row')!;
		const toggle = within(notionRow).getByRole('combobox') as HTMLSelectElement;
		expect(toggle.disabled).toBe(false);
		await fireEvent.change(toggle, { target: { value: 'true' } });
		put.mockResolvedValueOnce({ key: 'notion.sync_enabled', value: true, state: 'configured' });
		await fireEvent.click(within(notionRow).getByRole('button', { name: t('policies.save') }));
		await waitFor(() => expect(put).toHaveBeenCalledWith(
			'/api/v1/admin/runtime-settings/notion.sync_enabled', { value: true }, 'token', 'admin-project'
		));
	});

	it.each(['refresh', 'owner'] as const)('recovers failed remote rows on an explicit %s change without reloading on drafts', async (boundary) => {
		const baseGet = get.getMockImplementation()!;
		let unavailable = true;
		get.mockImplementation(async (path: string, ...rest: unknown[]) => {
			const result = await baseGet(path, ...rest);
			return path === '/api/v1/admin/resource-policies' && unavailable
				? { ...result, errors: [{ service: 'waygate', status: 503 }] }
				: result;
		});
		const panel = render(AdminResourcePoliciesPanel, { token: 'token', projectId: 'admin-project' });
		const builder = await openBuilderFlavorPicker();
		await fireEvent.click(await screen.findByRole('option', { name: /GPU build/ }));
		const waygate = screen.getByText('waygate.image').closest<HTMLElement>('.policy-row')!;
		const picker = within(waygate).getByRole('button', {
			name: t('policies.searchLabel', { title: t('policies.definition.waygateImage.title') })
		}) as HTMLButtonElement;
		expect(picker.disabled).toBe(true);
		expect(get.mock.calls.filter(([path]) => path === '/api/v1/admin/resource-policies')).toHaveLength(1);
		unavailable = false;
		if (boundary === 'refresh') await fireEvent.click(screen.getByRole('button', { name: t('branding.refresh') }));
		else await panel.rerender({ token: 'token', projectId: 'new-project' });
		await waitFor(() => expect(picker.disabled).toBe(false));
		await waitFor(() => expect(get.mock.calls.filter(([path]) => path.endsWith('/catalog/waygate.image'))).toHaveLength(1));
		expect(within(waygate).queryByText(t('policies.catalogFailed'))).toBeNull();
		expect(within(waygate).getByText('image-saved')).toBeTruthy();
		if (boundary === 'refresh') expect(builder.textContent).toContain('GPU build');
		expect(put).not.toHaveBeenCalled();
		expect(get.mock.calls.filter(([path]) => path === '/api/v1/admin/resource-policies')).toHaveLength(2);
	});

	it('discards an old-owner partial failure after the new owner has recovered', async () => {
		const baseGet = get.getMockImplementation()!;
		const old = Promise.withResolvers<{ policies: unknown[]; errors: Array<{ service: string; status: number }> }>();
		let first = true;
		get.mockImplementation((path: string, ...rest: unknown[]) => {
			if (path === '/api/v1/admin/resource-policies' && first) {
				first = false;
				return old.promise;
			}
			return baseGet(path, ...rest);
		});
		const panel = render(AdminResourcePoliciesPanel, { token: 'token', projectId: 'old-project' });
		await waitFor(() => expect(first).toBe(false));
		await panel.rerender({ token: 'token', projectId: 'new-project' });
		await openBuilderFlavorPicker();
		const row = screen.getByText('waygate.image').closest<HTMLElement>('.policy-row')!;
		old.resolve({ policies: [], errors: [{ service: 'waygate', status: 503 }] });
		await old.promise;
		await tick();
		expect(within(row).getByText('image-saved')).toBeTruthy();
		expect(within(row).queryByText(t('policies.catalogFailed'))).toBeNull();
		expect((within(row).getByRole('button', { name: t('policies.save') }) as HTMLButtonElement).disabled).toBe(false);
	});

	it.each(['policy', 'runtime'] as const)('blocks stale or default %s writes after a globally failed refresh', async (kind) => {
		const baseGet = get.getMockImplementation()!;
		let fail = false;
		const failedPath = kind === 'policy' ? '/api/v1/admin/resource-policies' : '/api/v1/admin/runtime-settings';
		get.mockImplementation((path: string, ...rest: unknown[]) => {
			if (path === failedPath && fail) return Promise.reject(new Error('offline'));
			return baseGet(path, ...rest);
		});
		render(AdminResourcePoliciesPanel, { token: 'token', projectId: 'admin-project' });
		await openBuilderFlavorPicker();
		await fireEvent.click(await screen.findByRole('option', { name: /GPU build/ }));
		const runtimeInput = screen.getByRole('textbox', { name: t('policies.valueLabel', { title: t('policies.runtime.versionTitle') }) });
		await fireEvent.input(runtimeInput, { target: { value: 'draft-version' } });
		const draft = document.cookie;
		fail = true;
		await fireEvent.click(screen.getByRole('button', { name: t('branding.refresh') }));
		await screen.findByText(t(kind === 'policy' ? 'policies.loadFailed' : 'policies.runtimeLoadFailed'));
		const rows = kind === 'policy'
			? [screen.getByText('builder.flavor').closest<HTMLElement>('.policy-row')!]
			: ['k3s.version', 'notion.sync_enabled'].map(key => screen.getByText(key).closest<HTMLElement>('.runtime-row')!);
		for (const row of rows) {
			const save = within(row).getByRole('button', { name: t('policies.save') }) as HTMLButtonElement;
			expect(save.disabled).toBe(true);
			await fireEvent.click(save);
		}
		expect(document.cookie).toBe(draft);
		expect(put).not.toHaveBeenCalled();
		if (kind === 'policy') {
			expect((screen.getByRole('textbox', { name: t('policies.valueLabel', { title: t('policies.runtime.versionTitle') }) }) as HTMLInputElement).disabled).toBe(false);
		} else {
			expect((screen.getByRole('button', { name: t('policies.searchLabel', { title: t('policies.definition.builderFlavor.title') }) }) as HTMLButtonElement).disabled).toBe(false);
		}
	});

	it('blocks saves and catalog reads until persisted values have loaded', async () => {
		const policies = Promise.withResolvers<{ policies: unknown[]; errors: unknown[] }>();
		const runtime = Promise.withResolvers<{ settings: unknown[]; errors: unknown[] }>();
		get.mockImplementation((path: string) => path === '/api/v1/admin/resource-policies' ? policies.promise : runtime.promise);
		render(AdminResourcePoliciesPanel, { token: 'token', projectId: 'admin-project' });
		const notionRow = screen.getByText('notion.sync_enabled').closest<HTMLElement>('.runtime-row')!;
		const notionToggle = within(notionRow).getByRole('combobox') as HTMLSelectElement;
		expect(notionToggle.value).toBe('');
		expect(notionToggle.selectedOptions[0].textContent).toBe(t('policies.state.unavailable'));
		for (const button of screen.getAllByRole('button', { name: t('policies.save') })) {
			expect((button as HTMLButtonElement).disabled).toBe(true);
			await fireEvent.click(button);
		}
		expect(put).not.toHaveBeenCalled();
		expect(get.mock.calls.some(([path]) => path.includes('/catalog'))).toBe(false);
		policies.resolve({ policies: [], errors: [] });
		runtime.resolve({ settings: [], errors: [] });
		await tick();
		for (const button of screen.getAllByRole('button', { name: t('policies.save') })) {
			expect((button as HTMLButtonElement).disabled).toBe(true);
		}
		expect(get.mock.calls.some(([path]) => path.includes('/catalog'))).toBe(false);
	});

	it('discovers an admin-scoped catalog and persists only the selected ID', async () => {
		render(AdminResourcePoliciesPanel, { token: 'token', projectId: 'admin-project' });

		await waitFor(() => expect(get).toHaveBeenCalledWith(
			expect.stringContaining('/api/v1/admin/resource-policies/catalog?'),
			'token',
			'admin-project',
			{ cache: 'no-store' }
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
			if (path.includes('/resource-policies/catalog?')) {
				attempts += 1;
				if (attempts === 1) return Promise.resolve({ catalogs: [{
					key: 'builder.flavor', error: { status: 503, detail: 'unavailable' }
				}] });
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

	it('batches initial discovery and retries only the failed key', async () => {
		const baseGet = get.getMockImplementation()!;
		let first = true;
		get.mockImplementation((path: string, ...rest: unknown[]) => {
			if (path.includes('/resource-policies/catalog?') && first) {
				first = false;
				const keys = new URL(path, 'http://fixture.test').searchParams.getAll('keys');
				return Promise.resolve({ catalogs: keys.map(key => key === 'builder.flavor'
					? { key, error: { status: 503, detail: 'unavailable' } }
					: { key, options: [] }) });
			}
			return baseGet(path, ...rest);
		});
		render(AdminResourcePoliciesPanel, { token: 'token', projectId: 'admin-project' });
		await waitFor(() => expect(screen.getByText(t('policies.catalogFailed'))).toBeTruthy());
		const batchCalls = () => get.mock.calls.filter(([path]) => path.includes('/resource-policies/catalog?'));
		expect(batchCalls()).toHaveLength(1);
		expect(new URL(batchCalls()[0][0], 'http://fixture.test').searchParams.getAll('keys')).not.toContain('waygate.image');
		await openBuilderFlavorPicker();
		expect(await screen.findByRole('option', { name: /CPU build/ })).toBeTruthy();
		expect(batchCalls()).toHaveLength(2);
		expect(new URL(batchCalls()[1][0], 'http://fixture.test').searchParams.getAll('keys')).toEqual(['builder.flavor']);
	});

	it('ignores a catalog response after project A to B to A including its automatic draft', async () => {
		const baseGet = get.getMockImplementation()!;
		const old = Promise.withResolvers<{ catalogs: unknown[] }>();
		let first = true;
		get.mockImplementation((path: string, ...rest: unknown[]) => {
			if (path.includes('/resource-policies/catalog?') && first) {
				first = false;
				return old.promise;
			}
			return baseGet(path, ...rest);
		});
		const panel = render(AdminResourcePoliciesPanel, { token: 'token', projectId: 'project-a' });
		await waitFor(() => expect(first).toBe(false));
		await panel.rerender({ token: 'token', projectId: 'project-b' });
		await waitFor(() => expect(get).toHaveBeenCalledWith(
			'/api/v1/admin/resource-policies', 'token', 'project-b', { cache: 'no-store' }
		));
		await panel.rerender({ token: 'token', projectId: 'project-a' });
		await waitFor(() => expect(get.mock.calls.filter(
			([path]) => path.includes('/resource-policies/catalog?')
		)).toHaveLength(3));
		old.resolve({ catalogs: [{ key: 'builder.flavor', options: [{ id: 'stale-only', name: 'Stale only' }] }] });
		await old.promise;
		await openBuilderFlavorPicker();
		expect(screen.queryByRole('option', { name: /Stale only/ })).toBeNull();
		expect(screen.getByRole('option', { name: /CPU build/ })).toBeTruthy();
		expect(document.cookie).not.toContain('stale-only');
	});

	it('preserves settled catalogs through same-project token renewal', async () => {
		establishVerifiedAdmin();
		const baseGet = get.getMockImplementation()!;
		get.mockImplementation(async (path: string, ...rest: unknown[]) => {
			const result = await baseGet(path, ...rest);
			return path === '/api/v1/admin/runtime-settings'
				? { settings: [{ key: 'notion.sync_enabled', value: null, state: 'missing' }], errors: [] }
				: result;
		});
		const panel = render(AdminResourcePoliciesPanel, { token: 'token', projectId: 'admin-project' });
		await openBuilderFlavorPicker();
		await fireEvent.click(await screen.findByRole('option', { name: /GPU build/ }));
		const notionRow = screen.getByText('notion.sync_enabled').closest<HTMLElement>('.runtime-row')!;
		const toggle = within(notionRow).getByRole('combobox') as HTMLSelectElement;
		expect(toggle.value).toBe('');
		await fireEvent.change(toggle, { target: { value: 'true' } });
		const draft = document.cookie;
		expect(draft).toContain('flavor-2');
		const trigger = await openBuilderFlavorPicker();
		const calls = get.mock.calls.length;
		const current = getStore(auth);
		setAuth(refreshAuthState({
			token: 'renewed-token', refresh_token: 'renewed-refresh', user_id: current.userId!, username: 'Admin',
			domain_id: 'home', domain_name: 'Home', identity_domain_id: 'home', identity_domain_name: 'Home',
			project_id: 'admin-project', project_name: 'Admin project', roles: ['admin'], is_system_admin: true,
			can_write: true, is_domain_manager: false, can_create_domain: false,
			available_domains: [{ id: 'home', name: 'Home' }], auth_method: 'password',
			expires_at: new Date(Date.now() + 3_600_000).toISOString(),
		}, current));
		expect(getStore(authReady)).toBe(true);
		await panel.rerender({ token: 'renewed-token', projectId: 'admin-project' });
		expect(get.mock.calls).toHaveLength(calls);
		expect(screen.getByRole('option', { name: /CPU build/ })).toBeTruthy();
		expect(trigger.textContent).toContain('GPU build');
		expect(document.cookie).toBe(draft);
		expect(toggle.value).toBe('true');
		expect((within(notionRow).getByRole('button', { name: t('policies.save') }) as HTMLButtonElement).disabled).toBe(false);
		expect(put).not.toHaveBeenCalled();
	});

	it.each(['roles', 'readiness', 'backend', 'backend-aba'] as const)('rejects late catalogs after a %s boundary change', async boundary => {
		establishVerifiedAdmin();
		const baseGet = get.getMockImplementation()!;
		const old = Promise.withResolvers<{ catalogs: unknown[] }>();
		let first = true;
		get.mockImplementation((path: string, ...rest: unknown[]) => {
			if (path.includes('/resource-policies/catalog?') && first) {
				first = false;
				return old.promise;
			}
			return baseGet(path, ...rest);
		});
		const initialSite = getStore(siteConfig);
		const panel = render(AdminResourcePoliciesPanel, { token: 'token', projectId: 'admin-project' });
		try {
			await waitFor(() => expect(first).toBe(false));
			if (boundary === 'roles') auth.update(state => ({ ...state, roles: ['reader'], canWrite: false }));
			else if (boundary === 'readiness') authReady.set(false);
			else {
				siteConfig.update(state => ({ ...state, runtime: { ...state.runtime, api_base: 'https://other-api.example.test' } }));
				if (boundary === 'backend-aba') siteConfig.set(initialSite);
			}
			await waitFor(() => expect(get.mock.calls.filter(([path]) => path.includes('/resource-policies/catalog?'))).toHaveLength(2));
			old.resolve({ catalogs: [{ key: 'builder.flavor', options: [{ id: 'stale-only', name: 'Stale only' }] }] });
			await old.promise;
			await openBuilderFlavorPicker();
			expect(screen.queryByRole('option', { name: /Stale only/ })).toBeNull();
			expect(screen.getByRole('option', { name: /CPU build/ })).toBeTruthy();
			expect(document.cookie).not.toContain('stale-only');
		} finally {
			panel.unmount();
			siteConfig.set(initialSite);
		}
	});

	it.each(['policy', 'runtime'] as const)('does not publish a completed old-backend %s save after same-tick backend ABA', async kind => {
		establishVerifiedAdmin();
		const completedWrite = Promise.withResolvers<Record<string, unknown>>();
		put.mockReturnValueOnce(completedWrite.promise);
		const initialSite = getStore(siteConfig);
		const panel = render(AdminResourcePoliciesPanel, { token: 'token', projectId: 'admin-project' });
		try {
			const picker = await openBuilderFlavorPicker();
			let row: HTMLElement;
			if (kind === 'policy') {
				await fireEvent.click(await screen.findByRole('option', { name: /GPU build/ }));
				row = picker.closest('.policy-row')!;
			} else {
				await fireEvent.click(picker);
				const input = screen.getByRole('textbox', { name: t('policies.valueLabel', { title: t('policies.runtime.versionTitle') }) });
				await fireEvent.input(input, { target: { value: 'v1.33.0+k3s1' } });
				row = input.closest('.runtime-row')!;
			}
			const draft = document.cookie;
			await fireEvent.click(within(row).getByRole('button', { name: t('policies.save') }));
			await waitFor(() => expect(put).toHaveBeenCalledTimes(1));
			const loads = get.mock.calls.filter(([path]) => path === '/api/v1/admin/resource-policies').length;
			siteConfig.update(state => ({ ...state, runtime: { ...state.runtime, api_base: 'https://other-api.example.test' } }));
			siteConfig.set(initialSite);
			await waitFor(() => expect(get.mock.calls.filter(([path]) => path === '/api/v1/admin/resource-policies')).toHaveLength(loads + 1));
			completedWrite.resolve(kind === 'policy'
				? { key: 'builder.flavor', resource_id: 'flavor-2', resource_name: 'GPU build' }
				: { key: 'k3s.version', value: 'v1.33.0+k3s1' });
			await completedWrite.promise;
			await tick();
			expect(put).toHaveBeenCalledTimes(1);
			expect(document.cookie).toBe(draft);
			const notice = kind === 'policy'
				? t('policies.saved', { title: t('policies.definition.builderFlavor.title') })
				: t('policies.runtimeSaved', { title: t('policies.runtime.versionTitle') });
			expect(screen.queryByText(notice)).toBeNull();
			if (kind === 'policy') expect(picker.textContent).toContain('GPU build');
			else expect((screen.getByRole('textbox', { name: t('policies.valueLabel', { title: t('policies.runtime.versionTitle') }) }) as HTMLInputElement).value).toBe('v1.33.0+k3s1');
		} finally {
			panel.unmount();
			siteConfig.set(initialSite);
		}
	});

	it('settles local catalogs while a remote catalog is still pending, without forwarding batch keys', async () => {
		const baseGet = get.getMockImplementation()!;
		const remote = Promise.withResolvers<{ key: string; options: unknown[] }>();
		builderOptions = [{ id: 'local-only', name: 'Local only' }];
		get.mockImplementation((path: string, ...rest: unknown[]) => {
			if (path.endsWith('/catalog/waygate.image')) return remote.promise;
			return baseGet(path, ...rest);
		});
		render(AdminResourcePoliciesPanel, { token: 'token', projectId: 'admin-project' });
		expect(await screen.findByText('Local only')).toBeTruthy();
		expect(get).toHaveBeenCalledWith(
			'/api/v1/admin/resource-policies/catalog/waygate.image', 'token', 'admin-project',
			{ cache: 'no-store' }
		);
		const batch = get.mock.calls.find(([path]) => path.includes('/resource-policies/catalog?'))!;
		const keys = new URL(batch[0], 'http://fixture.test').searchParams.getAll('keys');
		expect(keys.every(key => !key.startsWith('waygate.') && !key.startsWith('k3s.'))).toBe(true);
		remote.resolve({ key: 'waygate.image', options: [] });
	});



});
