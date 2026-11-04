import { fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { tick } from 'svelte';
import { get as getStore } from 'svelte/store';
import { acceptAuthVerification, auth, authReady, getAuthVerificationEpoch } from '$lib/stores/auth';
import { siteConfig } from '$lib/config/site';
import { ApiError } from '$lib/api/client';
import { t } from '$lib/i18n/ns/admin-system';
import type { NotionTarget } from '$lib/components/admin/notion/NotionTargetCard.svelte';
import type * as ClientModule from '$lib/api/client';

const apiMocks = vi.hoisted(() => ({ get: vi.fn(), put: vi.fn(), delete: vi.fn(), fetchWithAuth: vi.fn() }));

vi.mock('$lib/api/client', async (importOriginal) => {
	const actual = await importOriginal<typeof ClientModule>();
	return { ...actual, api: apiMocks, fetchWithAuth: apiMocks.fetchWithAuth };
});
vi.mock('$lib/stores/confirm.svelte', () => ({ confirmDialog: vi.fn() }));
vi.mock('$lib/stores/toast', () => ({ toast: { error: vi.fn() } }));

import NotionAdminPage from '../+page.svelte';

function establishVerifiedAdmin() {
	auth.set({
		...getStore(auth), sessionId: 'notion-admin-session', token: 'token', refreshToken: 'refresh-token',
		userId: 'admin', username: 'Admin', domainId: 'home', domainName: 'Home',
		identityDomainId: 'home', identityDomainName: 'Home', projectId: 'admin-project',
		projectName: 'Admin project', roles: ['admin'], isSystemAdmin: true, canWrite: true,
		isDomainManager: false, canCreateDomain: false,
	});
	expect(acceptAuthVerification(getAuthVerificationEpoch(), {})).toBe(true);
}

function target(label: string): NotionTarget {
	return {
		id: 1, label, api_key: 'masked', database_id: 'database-id',
		users_database_id: '', hypervisors_database_id: '', gpu_spec_database_id: '',
		enabled: true, interval_minutes: 10, last_sync: null, hypervisors_last_sync: null,
		gpu_spec_last_sync: null, created_at: '2026-11-04T00:00:00Z', updated_at: '2026-11-04T00:00:00Z'
	};
}

type Boundary = 'project-aba' | 'actor' | 'roles' | 'readiness' | 'backend-aba';

function crossBoundary(boundary: Boundary) {
	if (boundary === 'project-aba') {
		const initialAuth = getStore(auth);
		auth.update(state => ({ ...state, projectId: 'other-project' }));
		auth.set(initialAuth);
	} else if (boundary === 'actor') {
		auth.update(state => ({ ...state, userId: 'other-admin', sessionId: 'other-session' }));
	} else if (boundary === 'roles') {
		auth.update(state => ({ ...state, roles: ['reader'], canWrite: false }));
	} else if (boundary === 'readiness') {
		authReady.set(false);
	} else {
		const initialSite = getStore(siteConfig);
		siteConfig.update(state => ({ ...state, runtime: { ...state.runtime, api_base: 'https://other-api.example.test' } }));
		siteConfig.set(initialSite);
	}
	if (boundary === 'project-aba' || boundary === 'actor') {
		expect(acceptAuthVerification(getAuthVerificationEpoch(), {})).toBe(true);
	}
}

describe('Notion admin global synchronization gate', () => {
	beforeEach(() => {
		vi.clearAllMocks();
		establishVerifiedAdmin();
		apiMocks.get.mockImplementation((path: string) => {
			if (path === '/api/v1/admin/notion/targets') return Promise.resolve([]);
			if (path === '/api/v1/admin/runtime-settings') {
				return Promise.resolve({ settings: [{ key: 'notion.sync_enabled', value: false }], errors: [] });
			}
			return Promise.resolve([]);
		});
		apiMocks.put.mockResolvedValue({ key: 'notion.sync_enabled', value: true });
	});

	it('loads and updates the persisted global synchronization gate', async () => {
		render(NotionAdminPage);
		const toggle = await screen.findByRole('button', { name: '동기화 꺼짐' });
		await waitFor(() => expect((toggle as HTMLButtonElement).disabled).toBe(false));
		await fireEvent.click(toggle);

		await waitFor(() => expect(apiMocks.put).toHaveBeenCalledWith(
			'/api/v1/admin/runtime-settings/notion.sync_enabled',
			{ value: true },
			'token',
			'admin-project'
		));
		expect(await screen.findByRole('button', { name: '동기화 켜짐' })).toBeTruthy();
	});

	it('keeps the local gate usable when Drover runtime settings are unavailable', async () => {
		const baseGet = apiMocks.get.getMockImplementation()!;
		apiMocks.get.mockImplementation(async (path: string) => {
			const result = await baseGet(path);
			return path === '/api/v1/admin/runtime-settings'
				? { ...result, errors: [{ service: 'drover', status: 503 }] }
				: result;
		});
		render(NotionAdminPage);
		const toggle = await screen.findByRole('button', { name: '동기화 꺼짐' });
		await waitFor(() => expect((toggle as HTMLButtonElement).disabled).toBe(false));
		await fireEvent.click(toggle);
		await waitFor(() => expect(apiMocks.put).toHaveBeenCalledWith(
			'/api/v1/admin/runtime-settings/notion.sync_enabled', { value: true }, 'token', 'admin-project'
		));
		expect(await screen.findByRole('button', { name: '동기화 켜짐' })).toBeTruthy();
	});

	it('can enable the returned unset gate rather than treating it as an unknown row', async () => {
		apiMocks.get.mockImplementation((path: string) => Promise.resolve(path === '/api/v1/admin/runtime-settings'
			? { settings: [{ key: 'notion.sync_enabled', value: null, state: 'missing' }], errors: [] }
			: []));
		render(NotionAdminPage);
		const toggle = await screen.findByRole('button', { name: t('notion.form.enabled') }) as HTMLButtonElement;
		expect(screen.getByText(t('policies.state.missing'))).toBeTruthy();
		expect(screen.queryByRole('button', { name: t('notion.gate.disabled') })).toBeNull();
		expect(toggle.disabled).toBe(false);
		await fireEvent.click(toggle);
		await waitFor(() => expect(apiMocks.put).toHaveBeenCalledWith(
			'/api/v1/admin/runtime-settings/notion.sync_enabled', { value: true }, 'token', 'admin-project'
		));
		expect(await screen.findByRole('button', { name: '동기화 켜짐' })).toBeTruthy();
	});

	it.each(['absent', 'unavailable', 'failed', 'pending'] as const)('does not submit a fabricated false gate when its persisted row is %s', async (mode) => {
		const pending = Promise.withResolvers<{ settings: unknown[]; errors: unknown[] }>();
		apiMocks.get.mockImplementation((path: string) => {
			if (path !== '/api/v1/admin/runtime-settings') return Promise.resolve([]);
			if (mode === 'failed') return Promise.reject(new Error('offline'));
			if (mode === 'pending') return pending.promise;
			if (mode === 'unavailable') return Promise.resolve({
				settings: [{ key: 'notion.sync_enabled', value: null, state: 'unavailable' }], errors: []
			});
			return Promise.resolve({ settings: [], errors: [{ service: 'drover', status: 503 }] });
		});
		render(NotionAdminPage);
		const toggle = await screen.findByRole('button', { name: '조회 불가' }) as HTMLButtonElement;
		if (mode === 'absent' || mode === 'unavailable') await screen.findByText('등록된 Notion 연동 대상이 없습니다.');
		if (mode === 'failed') await screen.findByRole('alert');
		expect(toggle.disabled).toBe(true);
		await fireEvent.click(toggle);
		expect(apiMocks.put).not.toHaveBeenCalled();
		pending.resolve({ settings: [], errors: [] });
	});

	it('retains nonempty target cards when the runtime request fails and locks the unknown gate', async () => {
		apiMocks.get.mockImplementation((path: string) => path === '/api/v1/admin/runtime-settings'
			? Promise.reject(new ApiError(503, 'internal-token https://private.example.test'))
			: Promise.resolve([target('Existing synchronization target')]));
		render(NotionAdminPage);
		expect(await screen.findByText('Existing synchronization target')).toBeTruthy();
		expect((await screen.findByRole('alert')).textContent).toContain(t('notion.page.loadFailed', { status: 503 }));
		expect(screen.queryByText(t('notion.empty.title'))).toBeNull();
		expect(screen.queryByText(/internal-token|private\.example/)).toBeNull();
		const toggle = screen.getByRole('button', { name: t('policies.state.unavailable') }) as HTMLButtonElement;
		expect(toggle.disabled).toBe(true);
		await fireEvent.click(toggle);
		expect(apiMocks.put).not.toHaveBeenCalled();
	});

	it('keeps a known runtime gate usable when the targets request fails without claiming the list is empty', async () => {
		apiMocks.get.mockImplementation((path: string) => path === '/api/v1/admin/notion/targets'
			? Promise.reject(new ApiError(503, 'private-target-source-error'))
			: Promise.resolve({ settings: [{ key: 'notion.sync_enabled', value: false }], errors: [] }));
		render(NotionAdminPage);
		expect((await screen.findByRole('alert')).textContent).toContain(t('notion.page.loadFailed', { status: 503 }));
		expect(screen.queryByText(t('notion.empty.title'))).toBeNull();
		const toggle = await screen.findByRole('button', { name: t('notion.gate.disabled') }) as HTMLButtonElement;
		expect(toggle.disabled).toBe(false);
		await fireEvent.click(toggle);
		await waitFor(() => expect(apiMocks.put).toHaveBeenCalledWith(
			'/api/v1/admin/runtime-settings/notion.sync_enabled', { value: true }, 'token', 'admin-project'
		));
		expect(await screen.findByRole('button', { name: t('notion.gate.enabled') })).toBeTruthy();
	});

	it.each(['targets', 'runtime'] as const)('applies the successful independent result while %s remains pending', async pendingKind => {
		const pending = Promise.withResolvers<unknown>();
		apiMocks.get.mockImplementation((path: string) => {
			const isTargets = path === '/api/v1/admin/notion/targets';
			if (isTargets === (pendingKind === 'targets')) return pending.promise;
			return Promise.resolve(isTargets
				? [target('Independently loaded target')]
				: { settings: [{ key: 'notion.sync_enabled', value: false }], errors: [] });
		});
		const page = render(NotionAdminPage);
		try {
			if (pendingKind === 'runtime') {
				expect(await screen.findByText('Independently loaded target')).toBeTruthy();
				const toggle = screen.getByRole('button', { name: t('policies.state.unavailable') }) as HTMLButtonElement;
				expect(toggle.disabled).toBe(true);
				await fireEvent.click(toggle);
				expect(apiMocks.put).not.toHaveBeenCalled();
			} else {
				const toggle = await screen.findByRole('button', { name: t('notion.gate.disabled') }) as HTMLButtonElement;
				expect(toggle.disabled).toBe(false);
				await fireEvent.click(toggle);
				await waitFor(() => expect(apiMocks.put).toHaveBeenCalledWith(
					'/api/v1/admin/runtime-settings/notion.sync_enabled', { value: true }, 'token', 'admin-project'
				));
			}
		} finally {
			page.unmount();
			pending.resolve(pendingKind === 'targets' ? [] : { settings: [], errors: [] });
		}
	});

	it('preserves explicit true and false choices rather than confusing either with unset', async () => {
		apiMocks.get.mockImplementation((path: string) => Promise.resolve(path === '/api/v1/admin/runtime-settings'
			? { settings: [{ key: 'notion.sync_enabled', value: true }], errors: [] }
			: []));
		render(NotionAdminPage);
		const enabled = await screen.findByRole('button', { name: t('notion.gate.enabled') });
		expect(screen.queryByText(t('policies.state.missing'))).toBeNull();
		await fireEvent.click(enabled);
		await waitFor(() => expect(apiMocks.put).toHaveBeenLastCalledWith(
			'/api/v1/admin/runtime-settings/notion.sync_enabled', { value: false }, 'token', 'admin-project'
		));
		const disabled = await screen.findByRole('button', { name: t('notion.gate.disabled') });
		expect(screen.queryByText(t('policies.state.missing'))).toBeNull();
		await fireEvent.click(disabled);
		await waitFor(() => expect(apiMocks.put).toHaveBeenLastCalledWith(
			'/api/v1/admin/runtime-settings/notion.sync_enabled', { value: true }, 'token', 'admin-project'
		));
	});

	it.each<Boundary>(['project-aba', 'actor', 'roles', 'readiness', 'backend-aba'])(
		'ignores late target and runtime reads across a %s boundary', async boundary => {
			const oldTargets = Promise.withResolvers<NotionTarget[]>();
			const oldRuntime = Promise.withResolvers<{ settings: unknown[]; errors: unknown[] }>();
			let targetsCalls = 0;
			let runtimeCalls = 0;
			apiMocks.get.mockImplementation((path: string) => {
				if (path === '/api/v1/admin/notion/targets') {
					return ++targetsCalls === 1 ? oldTargets.promise : Promise.resolve([target('Current target')]);
				}
				return ++runtimeCalls === 1 ? oldRuntime.promise : Promise.reject(new ApiError(503, 'unavailable'));
			});
			const page = render(NotionAdminPage);
			try {
				await waitFor(() => expect(runtimeCalls).toBe(1));
				crossBoundary(boundary);
				if (boundary !== 'readiness') {
					await waitFor(() => expect(runtimeCalls).toBe(2));
					expect(await screen.findByText('Current target')).toBeTruthy();
				}
				oldTargets.resolve([target('Stale target')]);
				oldRuntime.resolve({ settings: [{ key: 'notion.sync_enabled', value: true }], errors: [] });
				await Promise.all([oldTargets.promise, oldRuntime.promise]);
				await tick();
				expect(screen.queryByText('Stale target')).toBeNull();
				const toggle = screen.getByRole('button', { name: t('policies.state.unavailable') }) as HTMLButtonElement;
				expect(toggle.disabled).toBe(true);
				await fireEvent.click(toggle);
				expect(apiMocks.put).not.toHaveBeenCalled();
			} finally {
				page.unmount();
			}
		}
	);

	it.each<Boundary>(['project-aba', 'actor', 'roles', 'readiness', 'backend-aba'])(
		'does not publish an old gate save across a %s boundary', async boundary => {
			const oldSave = Promise.withResolvers<{ key: string; value: boolean }>();
			apiMocks.put.mockReturnValueOnce(oldSave.promise);
			const page = render(NotionAdminPage);
			try {
				await fireEvent.click(await screen.findByRole('button', { name: t('notion.gate.disabled') }));
				await waitFor(() => expect(apiMocks.put).toHaveBeenCalledTimes(1));
				apiMocks.get.mockImplementation((path: string) => path === '/api/v1/admin/runtime-settings'
					? Promise.resolve({ settings: [{ key: 'notion.sync_enabled', value: null, state: 'missing' }], errors: [] })
					: Promise.resolve([]));
				crossBoundary(boundary);
				if (boundary !== 'readiness') await screen.findByText(t('policies.state.missing'));
				oldSave.resolve({ key: 'notion.sync_enabled', value: true });
				await oldSave.promise;
				await tick();
				expect(screen.queryByRole('button', { name: t('notion.gate.enabled') })).toBeNull();
				if (boundary === 'readiness') {
					const toggle = screen.getByRole('button', { name: t('policies.state.unavailable') }) as HTMLButtonElement;
					expect(toggle.disabled).toBe(true);
					await fireEvent.click(toggle);
					expect(apiMocks.put).toHaveBeenCalledTimes(1);
				} else {
					expect(screen.getByText(t('policies.state.missing'))).toBeTruthy();
					const toggle = screen.getByRole('button', { name: t('notion.form.enabled') }) as HTMLButtonElement;
					expect(toggle.disabled).toBe(false);
					await fireEvent.click(toggle);
					await waitFor(() => expect(apiMocks.put).toHaveBeenCalledTimes(2));
				}
			} finally {
				page.unmount();
			}
		}
	);

	it('does not publish an old-backend save error into the current known gate', async () => {
		const oldSave = Promise.withResolvers<unknown>();
		apiMocks.put.mockReturnValueOnce(oldSave.promise);
		const page = render(NotionAdminPage);
		try {
			await fireEvent.click(await screen.findByRole('button', { name: t('notion.gate.disabled') }));
			await waitFor(() => expect(apiMocks.put).toHaveBeenCalledTimes(1));
			const initialLoads = apiMocks.get.mock.calls.length;
			crossBoundary('backend-aba');
			await waitFor(() => expect(apiMocks.get.mock.calls.length).toBe(initialLoads + 2));
			await screen.findByRole('button', { name: t('notion.gate.disabled') });
			oldSave.reject(new ApiError(401, 'stale-private-source-error'));
			await oldSave.promise.catch(() => {});
			await tick();
			expect(screen.queryByRole('alert')).toBeNull();
			expect(screen.queryByText(/stale-private-source-error/)).toBeNull();
			const toggle = screen.getByRole('button', { name: t('notion.gate.disabled') }) as HTMLButtonElement;
			expect(toggle.disabled).toBe(false);
			await fireEvent.click(toggle);
			await waitFor(() => expect(apiMocks.put).toHaveBeenCalledTimes(2));
		} finally {
			page.unmount();
		}
	});

	it.each(['before', 'after'] as const)('keeps a pending gate save locked across a target refresh settling %s the write', async readOrder => {
		const oldSave = Promise.withResolvers<unknown>();
		const refreshRuntime = Promise.withResolvers<{ settings: unknown[]; errors: unknown[] }>();
		let runtimeCalls = 0;
		apiMocks.get.mockImplementation((path: string) => {
			if (path === '/api/v1/admin/notion/targets') return Promise.resolve([target('Refreshable target')]);
			return ++runtimeCalls === 1
				? Promise.resolve({ settings: [{ key: 'notion.sync_enabled', value: false }], errors: [] })
				: refreshRuntime.promise;
		});
		apiMocks.put.mockReturnValueOnce(oldSave.promise);
		apiMocks.fetchWithAuth.mockResolvedValueOnce(Response.json({ message: 'Synchronization completed' }));
		const page = render(NotionAdminPage);
		try {
			await screen.findByText('Refreshable target');
			await fireEvent.click(await screen.findByRole('button', { name: t('notion.gate.disabled') }));
			await waitFor(() => expect(apiMocks.put).toHaveBeenCalledTimes(1));
			await fireEvent.click(screen.getByRole('button', { name: t('notion.card.syncNow') }));
			await waitFor(() => expect(runtimeCalls).toBe(2));
			await screen.findByText('Refreshable target');
			expect((screen.getByRole('button', { name: t('notion.card.syncNow') }) as HTMLButtonElement).disabled).toBe(false);
			if (readOrder === 'before') {
				refreshRuntime.resolve({ settings: [{ key: 'notion.sync_enabled', value: false }], errors: [] });
				await refreshRuntime.promise;
				await tick();
			}
			const saving = screen.getByRole('button', { name: t('notion.gate.saving') }) as HTMLButtonElement;
			expect(saving.disabled).toBe(true);
			await fireEvent.click(saving);
			expect(apiMocks.put).toHaveBeenCalledTimes(1);
			oldSave.resolve({ key: 'notion.sync_enabled', value: true });
			await oldSave.promise;
			await screen.findByRole('button', { name: t('notion.gate.enabled') });
			if (readOrder === 'after') {
				refreshRuntime.resolve({ settings: [{ key: 'notion.sync_enabled', value: false }], errors: [] });
				await refreshRuntime.promise;
				await tick();
			}
			const enabled = screen.getByRole('button', { name: t('notion.gate.enabled') }) as HTMLButtonElement;
			expect(enabled.disabled).toBe(false);
			expect(screen.queryByRole('button', { name: t('notion.gate.disabled') })).toBeNull();
		} finally {
			page.unmount();
			oldSave.resolve({});
			refreshRuntime.resolve({ settings: [], errors: [] });
		}
	});

	it('reports a synchronization failure with its actual status without displaying the source body', async () => {
		apiMocks.get.mockImplementation((path: string) => Promise.resolve(path === '/api/v1/admin/notion/targets'
			? [target('Failed synchronization target')]
			: { settings: [{ key: 'notion.sync_enabled', value: null, state: 'missing' }], errors: [] }));
		apiMocks.fetchWithAuth.mockResolvedValueOnce(Response.json(
			{ detail: 'internal-token https://private.example.test' }, { status: 409 }
		));
		render(NotionAdminPage);
		await screen.findByText('Failed synchronization target');
		await fireEvent.click(screen.getByRole('button', { name: t('notion.card.syncNow') }));
		expect(await screen.findByText(`${t('notion.sync.failed')} (409)`)).toBeTruthy();
		expect(screen.queryByText(/internal-token|private\.example/)).toBeNull();
		expect((screen.getByRole('button', { name: t('notion.card.syncNow') }) as HTMLButtonElement).disabled).toBe(false);
	});
});
