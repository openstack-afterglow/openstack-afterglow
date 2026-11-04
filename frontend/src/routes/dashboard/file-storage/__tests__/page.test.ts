import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';
import { tick } from 'svelte';
import { get } from 'svelte/store';
import { acceptAuthVerification, auth, authReady, getAuthVerificationEpoch, projectSwitching, setAuth } from '$lib/stores/auth';
import { betaFeatures, DEFAULT_BETA_FEATURES } from '$lib/stores/betaFeatures';
import { captureFlowExperience, type CapturedFlowExperience } from '$lib/stores/__tests__/experienceFlowHarness';
import { refreshAuthState } from '$lib/utils/authSession';

const { api } = vi.hoisted(() => ({
	api: { get: vi.fn(), delete: vi.fn(), post: vi.fn(), prefetch: vi.fn(), withExperience: vi.fn() },
}));
vi.mock('$lib/api/client', () => ({ api, ApiError: class ApiError extends Error {} }));

import Page from '../+page.svelte';

const flows: CapturedFlowExperience[] = [];
afterEach(() => {
	cleanup();
	for (const flow of flows.splice(0)) flow.collector.destroy();
	vi.restoreAllMocks();
});

describe('dashboard file-storage refresh ownership', () => {
	beforeEach(() => {
		vi.clearAllMocks();
		api.withExperience.mockReturnValue(api);
		api.prefetch.mockResolvedValue(undefined);
		betaFeatures.set({ ...DEFAULT_BETA_FEATURES });
		api.get.mockImplementation((path: string) => {
			if (path === '/api/v1/file-storage') return Promise.resolve([]);
			if (path === '/api/v1/file-storage/quota') return Promise.resolve(null);
			return Promise.resolve([]);
		});
		auth.set({ sessionId: 'file-wizard-session', token: 'token', refreshToken: 'refresh', accessExpiresAt: null,
			userId: 'user', username: 'user', projectId: 'project', projectName: 'project', availableProjects: [], roles: ['member'],
			isSystemAdmin: false, canWrite: true, canCreateDomain: false, federated: false, domainId: 'domain-1', domainName: 'Domain',
			identityDomainId: 'domain-1', identityDomainName: 'Domain', isDomainManager: false });
		expect(acceptAuthVerification(getAuthVerificationEpoch(), {})).toBe(true);
		projectSwitching.set(false);
	});

	it('issues one explicit list and quota round on mount', async () => {
		render(Page);
		await waitFor(() => expect(api.get).toHaveBeenCalledWith('/api/v1/file-storage', 'token', 'project', undefined));
		expect(api.get).toHaveBeenCalledWith('/api/v1/file-storage/quota', 'token', 'project');
		expect(api.get.mock.calls.filter(([path]) => path === '/api/v1/file-storage')).toHaveLength(1);
	});

	it('initializes the mounted wizard once and observes metadata failure and close without recording the draft', async () => {
		const flow = captureFlowExperience('/dashboard/file-storage', () => get(auth));
		flows.push(flow);
		const listing = api.get.getMockImplementation()!;
		api.get.mockImplementation((path: string, ...args: unknown[]) => path === '/api/v1/file-storage/types'
			? Promise.reject(new Error('PRIVATE_METADATA_CANARY')) : listing(path, ...args));
		render(Page);
		await fireEvent.click(await screen.findByRole('button', { name: '+ 파일 스토리지 생성' }));
		const dialog = await screen.findByRole('dialog');
		const name = within(dialog).getByPlaceholderText('my-file-storage');
		await fireEvent.input(name, { target: { value: 'PRIVATE_DRAFT_CANARY' } });
		await waitFor(() => expect(api.get.mock.calls.filter(([path]) => path === '/api/v1/file-storage/types')).toHaveLength(1));
		await waitFor(async () => expect((await flow.flush()).some((event) => event.payload.state === 'error')).toBe(true));
		await tick();
		expect((name as HTMLInputElement).value).toBe('PRIVATE_DRAFT_CANARY');
		expect(api.get.mock.calls.filter(([path]) => path === '/api/v1/file-storage/types')).toHaveLength(1);
		await fireEvent.click(within(dialog).getByRole('button', { name: '취소' }));
		const events = await flow.flush();
		const opened = events.find((event) => event.event_type === 'action.started' && event.feature === 'file_storage');
		expect(opened?.action_id).toBeTruthy();
		expect(events.some((event) => event.event_type === 'result.applied' && event.action_id === opened?.action_id)).toBe(true);
		expect(events.some((event) => event.payload.state === 'disabled')).toBe(true);
		expect(JSON.stringify(events)).not.toMatch(/PRIVATE_DRAFT_CANARY|PRIVATE_METADATA_CANARY/);
		expect(api.post).not.toHaveBeenCalled();
	});

	it('discards closed metadata and keeps the reopened wizard draft and selected type', async () => {
		const flow = captureFlowExperience('/dashboard/file-storage', () => get(auth));
		flows.push(flow);
		const old = Promise.withResolvers<unknown[]>();
		let metadataReads = 0;
		const listing = api.get.getMockImplementation()!;
		api.get.mockImplementation((path: string, ...args: unknown[]) => {
			if (path !== '/api/v1/file-storage/types') return listing(path, ...args);
			metadataReads += 1;
			return metadataReads === 1 ? old.promise : Promise.resolve([
				{ id: 'new-type', name: 'new-type', is_default: true, supported_protocols: ['CEPHFS'] },
			]);
		});
		render(Page);
		await fireEvent.click(await screen.findByRole('button', { name: '+ 파일 스토리지 생성' }));
		await waitFor(() => expect(metadataReads).toBe(1));
		await fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: '취소' }));
		await fireEvent.click(screen.getByRole('button', { name: '+ 파일 스토리지 생성' }));
		const dialog = await screen.findByRole('dialog');
		const name = within(dialog).getByPlaceholderText('my-file-storage');
		await fireEvent.input(name, { target: { value: 'REOPENED_DRAFT_CANARY' } });
		await within(dialog).findByRole('option', { name: /new-type/ });
		old.resolve([{ id: 'old-type', name: 'old-type', is_default: true }]);
		await tick();
		await waitFor(async () => expect((await flow.flush()).some((event) => event.event_type === 'result.discarded')).toBe(true));
		expect(within(dialog).queryByRole('option', { name: /old-type/ })).toBeNull();
		expect((name as HTMLInputElement).value).toBe('REOPENED_DRAFT_CANARY');
		expect(metadataReads).toBe(2);
		expect(api.post).not.toHaveBeenCalled();
	});

	it('discards an unmounted wizard metadata response instead of publishing a result', async () => {
		const flow = captureFlowExperience('/dashboard/file-storage', () => get(auth));
		flows.push(flow);
		const pending = Promise.withResolvers<unknown[]>();
		const listing = api.get.getMockImplementation()!;
		api.get.mockImplementation((path: string, ...args: unknown[]) => path === '/api/v1/file-storage/types'
			? pending.promise : listing(path, ...args));
		const view = render(Page);
		await fireEvent.click(await screen.findByRole('button', { name: '+ 파일 스토리지 생성' }));
		await waitFor(() => expect(api.get.mock.calls.some(([path]) => path === '/api/v1/file-storage/types')).toBe(true));
		view.unmount();
		pending.resolve([]);
		await tick();
		const events = await flow.flush();
		expect(events.some((event) => event.event_type === 'result.discarded' && event.payload.reason === 'unmounted')).toBe(true);
		expect(events.some((event) => event.event_type === 'result.applied')).toBe(false);
	});

	it('applies pending metadata and preserves the draft across a verified same-owner token renewal', async () => {
		const pending = Promise.withResolvers<unknown[]>();
		const listing = api.get.getMockImplementation()!;
		api.get.mockImplementation((path: string, ...args: unknown[]) => path === '/api/v1/file-storage/types'
			? pending.promise : listing(path, ...args));
		render(Page);
		await fireEvent.click(await screen.findByRole('button', { name: '+ 파일 스토리지 생성' }));
		const dialog = await screen.findByRole('dialog');
		const name = within(dialog).getByPlaceholderText('my-file-storage');
		await fireEvent.input(name, { target: { value: 'RENEWAL_DRAFT_CANARY' } });
		await waitFor(() => expect(api.get.mock.calls.filter(([path]) => path === '/api/v1/file-storage/types')).toHaveLength(1));
		const current = get(auth);
		setAuth(refreshAuthState({
			token: 'renewed-token', refresh_token: 'renewed-refresh', user_id: 'user', username: 'user',
			domain_id: 'domain-1', domain_name: 'Domain', identity_domain_id: 'domain-1', identity_domain_name: 'Domain',
			project_id: 'project', project_name: 'project', roles: ['member'], is_system_admin: false,
			can_write: true, is_domain_manager: false, can_create_domain: false,
			available_domains: [{ id: 'domain-1', name: 'Domain' }], auth_method: 'password',
			expires_at: new Date(Date.now() + 3_600_000).toISOString(),
		}, current));
		expect(get(authReady)).toBe(true);
		pending.resolve([{ id: 'verified-type', name: 'verified-type', is_default: true }]);
		await within(dialog).findByRole('option', { name: /verified-type/ });
		expect((name as HTMLInputElement).value).toBe('RENEWAL_DRAFT_CANARY');
		expect(api.get.mock.calls.filter(([path]) => path === '/api/v1/file-storage/types')).toHaveLength(1);
		expect(api.post).not.toHaveBeenCalled();
	});

	it.each(['actor', 'project', 'logout-ABA'] as const)('rejects old metadata after a %s logical-owner transition', async (transition) => {
		const pending = Promise.withResolvers<unknown[]>();
		const listing = api.get.getMockImplementation()!;
		api.get.mockImplementation((path: string, ...args: unknown[]) => path === '/api/v1/file-storage/types'
			? pending.promise : listing(path, ...args));
		render(Page);
		await fireEvent.click(await screen.findByRole('button', { name: '+ 파일 스토리지 생성' }));
		const dialog = await screen.findByRole('dialog');
		await waitFor(() => expect(api.get.mock.calls.filter(([path]) => path === '/api/v1/file-storage/types')).toHaveLength(1));
		if (transition === 'actor') auth.update((state) => ({ ...state, userId: 'other-user' }));
		if (transition === 'project') auth.update((state) => ({ ...state, projectId: 'other-project' }));
		if (transition === 'logout-ABA') {
			const previous = get(auth);
			auth.set({ ...previous, token: null });
			auth.set(previous);
		}
		pending.resolve([{ id: 'old-owner-type', name: 'OLD_OWNER_METADATA_CANARY', is_default: true }]);
		await pending.promise;
		await tick(); await tick();
		expect(within(dialog).queryByRole('option', { name: /OLD_OWNER_METADATA_CANARY/ })).toBeNull();
		expect(api.post).not.toHaveBeenCalled();
	});
});
