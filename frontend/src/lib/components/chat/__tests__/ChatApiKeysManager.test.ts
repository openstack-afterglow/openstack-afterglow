import { grantLumen, pendingLumen, setVerifiedLumenActor } from './lumenPermissionFixture';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';
import { tick } from 'svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { get } from 'svelte/store';
import { auth, projectSwitching } from '$lib/stores/auth';
import { initSiteConfig } from '$lib/config/site';
import { t } from '$lib/i18n/ns/chat-settings';
import { initLocale, intlLocale } from '$lib/i18n/runtime.svelte';
import { ApiError } from '$lib/api/client';

const mocks = vi.hoisted(() => ({ get: vi.fn(), patch: vi.fn(), post: vi.fn(), delete: vi.fn(), confirm: vi.fn() }));
vi.mock('$lib/api/client', () => ({
	api: { get: mocks.get, patch: mocks.patch, post: mocks.post, delete: mocks.delete },
	ApiError: class extends Error { constructor(public status: number, message: string, public code?: string) { super(message); } }
}));
vi.mock('$lib/stores/confirm.svelte', () => ({ confirmDialog: mocks.confirm }));

import ChatApiKeysManager from '../ChatApiKeysManager.svelte';

const discovery = {
	endpoints: {
		openai: { sdk_base_url: 'https://inference.example/tenant/v1' },
		anthropic: { sdk_base_url: 'https://inference.example/tenant' },
		gateway: { base_url: 'https://inference.example/tenant/v1/claude-gateway' }
	},
	clients: {
		codex: { base_url: 'https://inference.example/tenant/v1' }
	}
};

const apiKey = {
	id: 17,
	name: '내 CLI',
	key_prefix: 'lm_test',
	scopes: ['chat'],
	is_active: true,
	last_used_at: null,
	created_at: '2026-09-09T00:00:00Z',
	revoked_at: null,
	expires_at: null,
	owner_monthly_credit_limit: null,
	admin_monthly_credit_limit: null,
	system_monthly_credit_limit: '1000',
	effective_monthly_credit_limit: '1000',
	month_credited_cost: '12.5',
	owner_weekly_credit_limit: null,
	system_weekly_credit_limit: '0',
	effective_weekly_credit_limit: '1000',
	week_credited_cost: '3.25'
};

const permissionsPath = '/api/v1/projects/current/permissions';

const pool = {
	domain_id: 'domain-1', balance_credits: '12', reserved_credits: '1', monthly_used_credits: '3',
	manager_monthly_limit_credits: null, admin_ceiling_credits: '9000000000.00000001', is_active: true,
};
const policyPath = '/api/v1/chat/api-keys/issuance-policy';
const issuanceGrants = ['lumen-keys_editor', 'lumen-inventory_reader', 'lumen-chat_user', 'lumen-images_user', 'lumen-audio_user', 'lumen-tools_user'];

function policy(grants = issuanceGrants, monthly: string | null = '1000', weekly: string | null = '250') {
	const scopeCapabilities: Record<string, string[]> = {
		'models:read': ['lumen-inventory_reader'],
		'compat:completions:write': ['lumen-chat_user'],
		'compat:images:write': ['lumen-images_user'],
		'compat:audio:write': ['lumen-audio_user'],
		'compat:realtime:write': ['lumen-audio_user'],
		'embeddings:write': ['lumen-chat_user'],
		'decisions:write': ['lumen-chat_user'],
		'native:tools:execute': ['lumen-tools_user']
	};
	return {
		monthly_credit_limit: monthly, weekly_credit_limit: weekly,
		allowed_scopes: Object.keys(scopeCapabilities).filter((scope) => scopeCapabilities[scope].every((leaf) => grants.includes(leaf))),
		scope_capabilities: scopeCapabilities
	};
}

function response(path: string, _project?: string) {
	if (path === policyPath) return policy();
	if (path.endsWith('/compat')) return discovery;
	if (path.endsWith('/api-keys')) return [apiKey];
	throw new Error(`Unexpected GET ${path}`);
}

async function openCreation() {
	await fireEvent.click(screen.getByRole('button', { name: t('apiKeys.newKey') }));
	return screen.findByRole('dialog', { name: t('apiKeys.newKey') });
}

async function readyToCreate(dialog: HTMLElement) {
	const submit = within(dialog).getByRole('button', { name: t('apiKeys.create') });
	await waitFor(() => expect((submit as HTMLButtonElement).disabled).toBe(false));
	return submit;
}

const noReplay = { replayOnUnauthorized: false };

function enableTargetProject() {
	auth.update((state) => ({ ...state, availableProjects: [
		{ id: 'project-1', name: 'Project' }, { id: 'project-2', name: 'Target' }
	] }));
}

function examples(container: HTMLElement): string {
	return Array.from(container.querySelectorAll('pre code'), (code) => code.textContent).join('\n');
}

describe('ChatApiKeysManager', () => {
	it('opens a creation modal and issues only scopes allowed by the current project grants', async () => {
		grantLumen('lumen-keys_editor', 'lumen-chat_user');
		mocks.get.mockImplementation((path: string, _token: string, project: string) => Promise.resolve(
			path === policyPath ? policy(['lumen-keys_editor', 'lumen-chat_user']) : response(path, project)
		));
		render(ChatApiKeysManager);
		expect(screen.queryByRole('dialog')).toBeNull();
		expect(screen.queryByLabelText(t('apiKeys.nameLabel'))).toBeNull();
		const dialog = await openCreation();
		expect(mocks.post).not.toHaveBeenCalled();
		await fireEvent.click(await readyToCreate(dialog));
		await waitFor(() => expect(mocks.post).toHaveBeenCalledWith('/api/v1/chat/api-keys', {
			name: '', scopes: ['compat:completions:write', 'embeddings:write', 'decisions:write'], expires_at: null, monthly_credit_limit: null
		}, 'browser-token', 'project-1', noReplay));
		await screen.findByText('one-time-secret');
		expect(screen.queryByRole('dialog', { name: t('apiKeys.newKey') })).toBeNull();
	});
	it('permits key editing but not revocation with the keys editor leaf', async () => {
		grantLumen('lumen-keys_editor');
		mocks.get.mockImplementation((path: string, _token: string, project: string) => Promise.resolve(
			path === policyPath ? policy(['lumen-keys_editor']) : response(path, project)
		));
		render(ChatApiKeysManager);
		const rename = await screen.findByRole('button', { name: t('apiKeys.rename') });
		expect(rename.hasAttribute('disabled')).toBe(false);
		expect(screen.getByRole('button', { name: t('apiKeys.revoke') }).hasAttribute('disabled')).toBe(true);
		const dialog = await openCreation();
		await waitFor(() => expect(mocks.get).toHaveBeenCalledWith(policyPath, 'browser-token', 'project-1', { refresh: true }));
		expect(within(dialog).queryByRole('checkbox', { name: /compat:images:write/ })).toBeNull();
		expect(within(dialog).getByRole('button', { name: t('apiKeys.create') }).hasAttribute('disabled')).toBe(true);
		await fireEvent.click(within(dialog).getByRole('button', { name: t('apiKeys.create') }));
		expect(mocks.post).not.toHaveBeenCalled();
	});
	beforeEach(() => {
		vi.resetAllMocks();
		initLocale('ko');
		auth.set({
			token: 'browser-token', refreshToken: null, accessExpiresAt: null,
			userId: 'user-1', username: 'tester', projectId: 'project-1', projectName: 'Project',
			availableProjects: [], roles: [], isSystemAdmin: false, federated: false, domainId: 'domain-1', domainName: 'Domain', isDomainManager: false
		});
		mocks.patch.mockResolvedValue({});
		mocks.delete.mockResolvedValue({});
		mocks.confirm.mockResolvedValue(true);
		mocks.post.mockResolvedValue({ key: 'one-time-secret', key_prefix: 'prefix' });
		mocks.get.mockImplementation((path: string, _token: string, project: string) => Promise.resolve(response(path, project)));
	});

	it('shows no project selector or service keys and validates the personal ceiling', async () => {
		enableTargetProject();
		setVerifiedLumenActor(get(auth));
		mocks.get.mockImplementation((path: string) => Promise.resolve(path === policyPath ? policy(issuanceGrants, '25', '10') : response(path)));
		render(ChatApiKeysManager);
		const dialog = await openCreation();
		const submit = await readyToCreate(dialog);
		expect(within(dialog).queryByLabelText(t('apiKeys.project'))).toBeNull();
		expect(screen.queryByRole('heading', { name: t('apiKeys.serviceTitle') })).toBeNull();
		expect(mocks.get.mock.calls.some(([path]) => path === permissionsPath || path.endsWith('/service-keys') || path.endsWith('/domain-pool'))).toBe(false);
		const monthly = within(dialog).getByLabelText(t('apiKeys.monthlyLimit'));
		await fireEvent.input(monthly, { target: { value: '26' } });
		await fireEvent.click(submit);
		expect(within(dialog).getByRole('alert').id).toBe(`${monthly.id}-message`);
		expect(mocks.post).not.toHaveBeenCalled();
		await fireEvent.input(monthly, { target: { value: '25' } });
		await fireEvent.input(within(dialog).getByLabelText(t('apiKeys.nameLabel')), { target: { value: '  Personal CLI  ' } });
		await fireEvent.click(submit);
		await screen.findByText('one-time-secret');
		expect(mocks.post).toHaveBeenCalledWith('/api/v1/chat/api-keys', {
			name: 'Personal CLI',
			scopes: ['models:read', 'compat:completions:write', 'compat:images:write', 'compat:audio:write', 'compat:realtime:write', 'embeddings:write', 'decisions:write'],
			expires_at: null, monthly_credit_limit: '25'
		}, 'browser-token', 'project-1', noReplay);
		await fireEvent.click(screen.getByRole('button', { name: t('apiKeys.done') }));
		expect(screen.queryByText('one-time-secret')).toBeNull();
	});

	it('keeps submission blocked while issuance policy is pending, then fails closed', async () => {
		const pending = Promise.withResolvers<unknown>();
		mocks.get.mockImplementation((path: string) => path === policyPath ? pending.promise : Promise.resolve(response(path)));
		render(ChatApiKeysManager);
		const dialog = await openCreation();
		await waitFor(() => expect(mocks.get).toHaveBeenCalledWith(policyPath, 'browser-token', 'project-1', { refresh: true }));
		const submit = within(dialog).getByRole('button', { name: t('apiKeys.create') });
		expect(submit.hasAttribute('disabled')).toBe(true);
		await fireEvent.click(submit);
		expect(mocks.post).not.toHaveBeenCalled();
		pending.reject(new Error('offline'));
		await within(dialog).findByRole('alert');
		expect(submit.hasAttribute('disabled')).toBe(true);
	});

	it('ignores old policy after a project switch closes and reopens the issuance form', async () => {
		const pending = Promise.withResolvers<unknown>();
		mocks.get.mockImplementation((path: string, _token: string, project: string) => {
			if (path === policyPath) return project === 'project-1' ? pending.promise : Promise.resolve(policy(issuanceGrants, '3'));
			return Promise.resolve(response(path));
		});
		render(ChatApiKeysManager);
		await openCreation();
		auth.update((state) => ({ ...state, projectId: 'project-2' }));
		await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
		const dialog = await openCreation();
		const submit = await readyToCreate(dialog);
		pending.resolve(policy(issuanceGrants, '1'));
		await tick();
		await fireEvent.input(within(dialog).getByLabelText(t('apiKeys.monthlyLimit')), { target: { value: '3' } });
		await fireEvent.click(submit);
		await screen.findByText('one-time-secret');
		expect(mocks.post).toHaveBeenCalledWith('/api/v1/chat/api-keys', expect.objectContaining({ monthly_credit_limit: '3' }), 'browser-token', 'project-2', noReplay);
	});

	it('lets a verified domain manager list, issue and revoke domain-owned keys', async () => {
		setVerifiedLumenActor({ ...get(auth), isDomainManager: true });
		let serviceKeys: unknown[] = [];
		const serviceKey = { ...apiKey, id: 29, name: 'Nightly job', key_prefix: 'service-prefix', owner_domain_id: 'domain-1', key_kind: 'service' };
		mocks.get.mockImplementation(async (path: string) => {
			if (path.endsWith('/service-keys')) return serviceKeys;
			if (path.endsWith('/domain-pool')) return pool;
			return response(path);
		});
		mocks.post.mockImplementation(async () => { serviceKeys = [serviceKey]; return { key: 'service-secret-fixture' }; });
		mocks.delete.mockImplementation(async () => { serviceKeys = [{ ...serviceKey, is_active: false }]; });
		render(ChatApiKeysManager);
		const manager = await screen.findByRole('region', { name: t('apiKeys.serviceTitle') });
		await within(manager).findByText(t('apiKeys.serviceEmpty'));
		await fireEvent.click(within(manager).getByRole('button', { name: t('apiKeys.newServiceKey') }));
		const dialog = await screen.findByRole('dialog', { name: t('apiKeys.newServiceKey') });
		expect(within(dialog).queryByLabelText(/native:tools:execute/)).toBeNull();
		await fireEvent.input(within(dialog).getByLabelText(t('apiKeys.nameLabel')), { target: { value: 'Nightly job' } });
		await fireEvent.click(within(dialog).getByRole('checkbox', { name: /decisions:write/ }));
		await fireEvent.click(within(dialog).getByRole('button', { name: t('apiKeys.create') }));
		await screen.findByText('service-secret-fixture');
		expect(mocks.post).toHaveBeenCalledWith('/api/v1/chat/service-keys', {
			name: 'Nightly job', scopes: ['models:read', 'compat:completions:write', 'decisions:write']
		}, 'browser-token', 'project-1', expect.objectContaining(noReplay));
		await fireEvent.click(screen.getByRole('button', { name: t('apiKeys.done') }));
		expect(screen.queryByText('service-secret-fixture')).toBeNull();
		await within(manager).findByText('Nightly job');
		await fireEvent.click(within(manager).getByRole('button', { name: t('apiKeys.revoke') }));
		await within(manager).findByText(t('apiKeys.revoked'));
		expect(mocks.delete).toHaveBeenCalledWith('/api/v1/chat/service-keys/29', 'browser-token', 'project-1', expect.objectContaining(noReplay));
	});

	it('checks eight-digit manager limits, supports zero, and reports native billing errors', async () => {
		setVerifiedLumenActor({ ...get(auth), isDomainManager: true });
		mocks.get.mockImplementation(async (path: string) => {
			if (path.endsWith('/service-keys')) return [];
			if (path.endsWith('/domain-pool')) return pool;
			return response(path);
		});
		mocks.patch.mockRejectedValueOnce(new ApiError(409, 'native message', 'domain_credit_insufficient'));
		mocks.patch.mockResolvedValueOnce({ ...pool, manager_monthly_limit_credits: '0' });
		render(ChatApiKeysManager);
		const managerPool = await screen.findByRole('region', { name: t('domainBilling.title') });
		const limit = await within(managerPool).findByLabelText(t('domainBilling.managerLimit'));
		const save = within(managerPool).getByRole('button', { name: t('apiKeys.save') });
		await fireEvent.input(limit, { target: { value: '9000000000.00000002' } });
		await fireEvent.click(save);
		await within(managerPool).findByText(t('domainBilling.overCeiling'));
		expect(mocks.patch).not.toHaveBeenCalled();
		await fireEvent.input(limit, { target: { value: '9000000000.00000001' } });
		await fireEvent.click(save);
		await within(managerPool).findByText(t('domainBilling.insufficient'));
		await fireEvent.input(limit, { target: { value: '0' } });
		await fireEvent.click(save);
		await waitFor(() => expect(mocks.patch).toHaveBeenLastCalledWith('/api/v1/chat/domain-pool', { manager_monthly_limit_credits: '0' }, 'browser-token', 'project-1', expect.objectContaining(noReplay)));
	});

	it('accepts an unlimited personal policy without requiring inventory-reader authority', async () => {
		grantLumen('lumen-keys_editor', 'lumen-chat_user');
		mocks.get.mockImplementation((path: string, _token: string, project: string) => Promise.resolve(
			path === policyPath ? policy(['lumen-keys_editor', 'lumen-chat_user'], null, null) : response(path, project)
		));
		render(ChatApiKeysManager);
		const dialog = await openCreation();
		const submit = await readyToCreate(dialog);
		await fireEvent.input(within(dialog).getByLabelText(t('apiKeys.monthlyLimit')), { target: { value: '' } });
		await fireEvent.click(submit);
		await waitFor(() => expect(mocks.post).toHaveBeenCalledWith('/api/v1/chat/api-keys', {
			name: '', scopes: ['compat:completions:write', 'embeddings:write', 'decisions:write'], expires_at: null, monthly_credit_limit: null
		}, 'browser-token', 'project-1', noReplay));
		expect(mocks.get.mock.calls.some(([path]) => path === '/api/v1/chat/usage')).toBe(false);
	});

	it('submits restricted scopes and a custom expiry rather than the all-allowed defaults', async () => {
		render(ChatApiKeysManager);
		const dialog = await openCreation();
		await readyToCreate(dialog);
		await fireEvent.click(within(dialog).getByRole('button', { name: t('apiKeys.permissions.restricted') }));
		await fireEvent.click(within(dialog).getByRole('checkbox', { name: /models:read/ }));
		await fireEvent.click(within(dialog).getByRole('checkbox', { name: /compat:images:write/ }));
		await fireEvent.change(within(dialog).getByLabelText(t('apiKeys.expiry')), { target: { value: 'custom' } });
		await fireEvent.input(within(dialog).getByLabelText(t('apiKeys.expiry.date')), { target: { value: '2099-01-02' } });
		await fireEvent.click(await readyToCreate(dialog));
		await waitFor(() => expect(mocks.post).toHaveBeenCalledWith('/api/v1/chat/api-keys', {
			name: '', scopes: ['compat:completions:write', 'compat:images:write'], expires_at: new Date('2099-01-02T00:00:00').toISOString(), monthly_credit_limit: null
		}, 'browser-token', 'project-1', noReplay));
	});

	it('issues read-only scopes without retaining write grants', async () => {
		mocks.get.mockImplementation((path: string, _token: string, project: string) => Promise.resolve(
			path === policyPath ? {
				...policy(), allowed_scopes: ['models:read', 'usage:read', 'compat:completions:write'],
				scope_capabilities: { ...policy().scope_capabilities, 'usage:read': ['lumen-inventory_reader'] }
			} : response(path, project)
		));
		render(ChatApiKeysManager);
		const dialog = await openCreation();
		await readyToCreate(dialog);
		await fireEvent.click(within(dialog).getByRole('button', { name: t('apiKeys.permissions.readOnly') }));
		await fireEvent.click(await readyToCreate(dialog));
		await waitFor(() => expect(mocks.post).toHaveBeenCalledWith('/api/v1/chat/api-keys', {
			name: '', scopes: ['models:read'], expires_at: null, monthly_credit_limit: null
		}, 'browser-token', 'project-1', noReplay));
	});

	it('never expands issuance beyond the policy scope ceiling even when project grants are broader', async () => {
		mocks.get.mockImplementation((path: string, _token: string, project: string) => Promise.resolve(
			path === policyPath ? policy(['lumen-keys_editor', 'lumen-chat_user']) : response(path, project)
		));
		render(ChatApiKeysManager);
		const dialog = await openCreation();
		await readyToCreate(dialog);
		expect(within(dialog).queryByRole('checkbox', { name: /compat:images:write/ })).toBeNull();
		await fireEvent.click(await readyToCreate(dialog));
		await waitFor(() => expect(mocks.post).toHaveBeenCalledWith('/api/v1/chat/api-keys', {
			name: '', scopes: ['compat:completions:write', 'embeddings:write', 'decisions:write'], expires_at: null, monthly_credit_limit: null
		}, 'browser-token', 'project-1', noReplay));
	});

	it('does not treat an issuance policy scope as authority without the current capability', async () => {
		grantLumen('lumen-keys_editor');
		render(ChatApiKeysManager);
		const dialog = await openCreation();
		await within(dialog).findByText(t('apiKeys.target.noScopes'));
		await fireEvent.click(within(dialog).getByRole('button', { name: t('apiKeys.create') }));
		expect(mocks.post).not.toHaveBeenCalled();
	});

	it.each(['', '2001-01-02'])('rejects custom expiry %j without sending a creation request', async (date) => {
		render(ChatApiKeysManager);
		const dialog = await openCreation();
		await readyToCreate(dialog);
		await fireEvent.change(within(dialog).getByLabelText(t('apiKeys.expiry')), { target: { value: 'custom' } });
		const input = within(dialog).getByLabelText(t('apiKeys.expiry.date'));
		await fireEvent.input(input, { target: { value: date } });
		await fireEvent.click(await readyToCreate(dialog));
		expect(within(dialog).getByRole('alert').id).toBe(`${input.id}-message`);
		expect(mocks.post).not.toHaveBeenCalled();
	});

	it('resets custom date and validation errors when an invalid draft is cancelled', async () => {
		render(ChatApiKeysManager);
		const dialog = await openCreation();
		await readyToCreate(dialog);
		await fireEvent.change(within(dialog).getByLabelText(t('apiKeys.expiry')), { target: { value: 'custom' } });
		await fireEvent.input(within(dialog).getByLabelText(t('apiKeys.expiry.date')), { target: { value: '2001-01-02' } });
		await fireEvent.click(await readyToCreate(dialog));
		await within(dialog).findByRole('alert');
		await fireEvent.click(within(dialog).getByRole('button', { name: t('apiKeys.cancel') }));
		const reopened = await openCreation();
		await readyToCreate(reopened);
		await fireEvent.change(within(reopened).getByLabelText(t('apiKeys.expiry')), { target: { value: 'custom' } });
		expect((within(reopened).getByLabelText(t('apiKeys.expiry.date')) as HTMLInputElement).value).toBe('');
		expect(within(reopened).queryByRole('alert')).toBeNull();
		expect(mocks.post).not.toHaveBeenCalled();
	});

	it.each(['cancel', 'escape'] as const)('resets every draft on modal %s and reopens against the current project', async (dismissal) => {
		render(ChatApiKeysManager);
		const dialog = await openCreation();
		await readyToCreate(dialog);
		await fireEvent.input(within(dialog).getByLabelText(t('apiKeys.nameLabel')), { target: { value: 'Abandoned key' } });
		await fireEvent.input(within(dialog).getByLabelText(t('apiKeys.monthlyLimit')), { target: { value: '100' } });
		await fireEvent.click(within(dialog).getByRole('button', { name: t('apiKeys.permissions.readOnly') }));
		await fireEvent.change(within(dialog).getByLabelText(t('apiKeys.expiry')), { target: { value: 'custom' } });
		await fireEvent.input(within(dialog).getByLabelText(t('apiKeys.expiry.date')), { target: { value: '2099-01-02' } });
		if (dismissal === 'cancel') await fireEvent.click(within(dialog).getByRole('button', { name: t('apiKeys.cancel') }));
		else await fireEvent.keyDown(dialog, { key: 'Escape' });
		await waitFor(() => expect(screen.queryByRole('dialog', { name: t('apiKeys.newKey') })).toBeNull());
		expect(mocks.post).not.toHaveBeenCalled();
		const reopened = await openCreation();
		expect((within(reopened).getByLabelText(t('apiKeys.nameLabel')) as HTMLInputElement).value).toBe('');
		expect((within(reopened).getByLabelText(t('apiKeys.monthlyLimit')) as HTMLInputElement).value).toBe('');
		expect((within(reopened).getByLabelText(t('apiKeys.expiry')) as HTMLSelectElement).value).toBe('never');
		expect(within(reopened).queryByLabelText(t('apiKeys.expiry.date'))).toBeNull();
		await fireEvent.click(await readyToCreate(reopened));
		await waitFor(() => expect(mocks.post).toHaveBeenCalledWith('/api/v1/chat/api-keys', {
			name: '', scopes: ['models:read', 'compat:completions:write', 'compat:images:write', 'compat:audio:write', 'compat:realtime:write', 'embeddings:write', 'decisions:write'], expires_at: null, monthly_credit_limit: null
		}, 'browser-token', 'project-1', noReplay));
	});

	it.each(['token', 'userId', 'projectId'] as const)('discards a late one-time secret after an auth %s ABA transition', async (field) => {
		const pending = Promise.withResolvers<{ key: string; key_prefix: string }>();
		mocks.post.mockReturnValueOnce(pending.promise);
		render(ChatApiKeysManager);
		const dialog = await openCreation();
		await fireEvent.click(await readyToCreate(dialog));
		await waitFor(() => expect(mocks.post).toHaveBeenCalledTimes(1));
		const owner = get(auth);
		auth.set({ ...owner, [field]: `${owner[field]}-other` });
		auth.set(owner);
		await tick();
		const listRequests = mocks.get.mock.calls.filter(([path]) => path === '/api/v1/chat/api-keys').length;
		pending.resolve({ key: 'stale-owner-secret', key_prefix: 'old' });
		await pending.promise;
		await tick();
		expect(screen.queryByText('stale-owner-secret')).toBeNull();
		expect(screen.queryByRole('dialog', { name: t('apiKeys.issued.title') })).toBeNull();
		expect(mocks.get.mock.calls.filter(([path]) => path === '/api/v1/chat/api-keys')).toHaveLength(listRequests);
		const fresh = await openCreation();
		await fireEvent.click(await readyToCreate(fresh));
		await screen.findByText('one-time-secret');
		expect(screen.queryByText('stale-owner-secret')).toBeNull();
	});

	it('discards a late secret after synchronous project switching begins and ends', async () => {
		const pending = Promise.withResolvers<{ key: string; key_prefix: string }>();
		mocks.post.mockReturnValueOnce(pending.promise);
		render(ChatApiKeysManager);
		const dialog = await openCreation();
		await fireEvent.click(await readyToCreate(dialog));
		await waitFor(() => expect(mocks.post).toHaveBeenCalledTimes(1));
		// Project selection is disabled during submission; the auth project is the authoritative boundary.
		projectSwitching.set(true);
		projectSwitching.set(false);
		pending.resolve({ key: 'switching-secret', key_prefix: 'old' });
		await pending.promise;
		await tick();
		expect(screen.queryByText('switching-secret')).toBeNull();
		expect(screen.queryByRole('dialog', { name: t('apiKeys.newKey') })).toBeNull();
	});

	it.each(['', 'Permission service unavailable'])('masks an issued secret during pending permissions %j and restores it only if still allowed', async (permissionError) => {
		render(ChatApiKeysManager);
		await fireEvent.click(await readyToCreate(await openCreation()));
		await screen.findByText('one-time-secret');
		pendingLumen(permissionError);
		await tick();
		expect(screen.queryByText('one-time-secret')).toBeNull();
		expect(screen.queryByRole('button', { name: t('apiKeys.copy') })).toBeNull();
		grantLumen(...issuanceGrants);
		await screen.findByText('one-time-secret');
		expect(mocks.post).toHaveBeenCalledTimes(1);
	});

	it.each(['lumen-keys_editor', 'lumen-chat_user'])('permanently erases an issued secret when %s is denied after pending', async (denied) => {
		render(ChatApiKeysManager);
		await fireEvent.click(await readyToCreate(await openCreation()));
		await screen.findByText('one-time-secret');
		pendingLumen();
		await tick();
		grantLumen(...issuanceGrants.filter((leaf) => leaf !== denied));
		await tick();
		grantLumen(...issuanceGrants);
		await tick();
		expect(screen.queryByText('one-time-secret')).toBeNull();
		expect(screen.queryByRole('dialog', { name: t('apiKeys.issued.title') })).toBeNull();
		expect(mocks.post).toHaveBeenCalledTimes(1);
	});

	it('does not publish a response received while permissions are pending after they recover', async () => {
		const pending = Promise.withResolvers<{ key: string; key_prefix: string }>();
		mocks.post.mockReturnValueOnce(pending.promise);
		render(ChatApiKeysManager);
		await fireEvent.click(await readyToCreate(await openCreation()));
		await waitFor(() => expect(mocks.post).toHaveBeenCalledTimes(1));
		pendingLumen();
		pending.resolve({ key: 'pending-permission-secret', key_prefix: 'old' });
		await pending.promise;
		await tick();
		grantLumen(...issuanceGrants);
		await tick();
		expect(screen.queryByText('pending-permission-secret')).toBeNull();
		expect(screen.queryByRole('dialog', { name: t('apiKeys.issued.title') })).toBeNull();
	});

	it('filters revoked keys by default and toggles accurate counts without exposing revoked actions', async () => {
		mocks.get.mockImplementation((path: string, _token: string, project: string) => Promise.resolve(
			path.endsWith('/api-keys') ? [apiKey, { ...apiKey, id: 18, name: 'Revoked CLI', key_prefix: 'lm_revoked', is_active: false, revoked_at: '2026-09-10T00:00:00Z' }] : response(path, project)
		));
		render(ChatApiKeysManager);
		await screen.findByText(apiKey.name);
		expect(screen.queryByText('Revoked CLI')).toBeNull();
		const requests = mocks.get.mock.calls.length;
		await fireEvent.click(screen.getByRole('button', { name: t('apiKeys.showAll', { count: 2 }) }));
		await screen.findByText('Revoked CLI');
		expect(screen.getByText(/lm_revoked/)).toBeTruthy();
		for (const key of ['apiKeys.rename', 'apiKeys.setLimits', 'apiKeys.revoke'] as const) expect(screen.getAllByRole('button', { name: t(key) })).toHaveLength(1);
		expect(mocks.patch).not.toHaveBeenCalled();
		expect(mocks.delete).not.toHaveBeenCalled();
		await fireEvent.click(screen.getByRole('button', { name: t('apiKeys.activeOnly', { count: 1 }) }));
		expect(screen.queryByText('Revoked CLI')).toBeNull();
		expect(screen.getByText(apiKey.name)).toBeTruthy();
		expect(mocks.get.mock.calls).toHaveLength(requests);
	});

	it('shows expiry metadata and distinguishes expired active keys from revoked keys', async () => {
		const expired = '2001-01-02T00:00:00Z';
		const future = '2099-01-02T00:00:00Z';
		mocks.get.mockImplementation((path: string, _token: string, project: string) => Promise.resolve(
			path.endsWith('/api-keys') ? [
				{ ...apiKey, name: 'Expired CLI', expires_at: expired },
				{ ...apiKey, id: 18, name: 'Future CLI', expires_at: future },
				{ ...apiKey, id: 19, name: 'No-expiry CLI' }
			] : response(path, project)
		));
		render(ChatApiKeysManager);
		await screen.findByText('Expired CLI');
		expect(screen.getAllByText(t('apiKeys.expired'))).toHaveLength(1);
		expect(screen.getByText(t('apiKeys.expiresAt', { date: new Date(expired).toLocaleString(intlLocale()) }))).toBeTruthy();
		expect(screen.getByText(t('apiKeys.expiresAt', { date: new Date(future).toLocaleString(intlLocale()) }))).toBeTruthy();
		expect(screen.getByText(t('apiKeys.expiry.never'))).toBeTruthy();
		expect(screen.getAllByRole('button', { name: t('apiKeys.rename') })).toHaveLength(3);
		expect(mocks.patch).not.toHaveBeenCalled();
		expect(mocks.delete).not.toHaveBeenCalled();
	});

	it('revokes an active key only after confirmation and refreshes the filtered list', async () => {
		let revoked = false;
		mocks.delete.mockImplementation(async () => { revoked = true; });
		mocks.get.mockImplementation((path: string, _token: string, project: string) => Promise.resolve(
			path.endsWith('/api-keys') ? [{ ...apiKey, is_active: !revoked, revoked_at: revoked ? '2026-09-10T00:00:00Z' : null }] : response(path, project)
		));
		render(ChatApiKeysManager);
		await fireEvent.click(await screen.findByRole('button', { name: t('apiKeys.revoke') }));
		await waitFor(() => expect(mocks.delete).toHaveBeenCalledWith('/api/v1/chat/api-keys/17', 'browser-token', 'project-1', noReplay));
		expect(mocks.confirm).toHaveBeenCalledTimes(1);
		await waitFor(() => expect(screen.queryByText(apiKey.name)).toBeNull());
		await fireEvent.click(screen.getByRole('button', { name: t('apiKeys.showAll', { count: 1 }) }));
		await screen.findByText(apiKey.name);
		expect(screen.queryByRole('button', { name: t('apiKeys.revoke') })).toBeNull();
	});

	it('does not revoke when the confirmation is cancelled', async () => {
		mocks.confirm.mockResolvedValue(false);
		render(ChatApiKeysManager);
		await fireEvent.click(await screen.findByRole('button', { name: t('apiKeys.revoke') }));
		expect(mocks.confirm).toHaveBeenCalledTimes(1);
		expect(mocks.delete).not.toHaveBeenCalled();
		expect(screen.getByText(apiKey.name)).toBeTruthy();
	});

	afterEach(() => {
		cleanup();
		initLocale('ko');
		initSiteConfig({ lumen_installer_configured: false, lumen_external_url: '' });
	});

	it('shows download-only installer commands when configured even if SDK discovery fails', async () => {
		initSiteConfig({ lumen_installer_configured: true });
		mocks.get.mockImplementation(async (path: string) => {
			if (path.endsWith('/compat')) throw new Error('offline');
			return response(path);
		});
		render(ChatApiKeysManager);
		await screen.findByRole('alert');
		const { origin } = window.location;
		const posix = screen.getByRole('region', { name: t('apiKeys.installer.posixLabel') });
		const windows = screen.getByRole('region', { name: t('apiKeys.installer.windowsLabel') });
		expect(posix.textContent).toBe(`curl -fsSL '${origin}/install/lumen.sh' | sh`);
		expect(windows.textContent).toBe(`irm '${origin}/install/lumen.ps1' | iex`);
		expect(screen.getByRole('link', { name: t('apiKeys.installer.viewPosix') }).getAttribute('href')).toBe(`${origin}/install/lumen.sh`);
		expect(screen.getByRole('link', { name: t('apiKeys.installer.viewWindows') }).getAttribute('href')).toBe(`${origin}/install/lumen.ps1`);
	});

	it('hides installers when no public URL is configured, even with valid SDK discovery', async () => {
		render(ChatApiKeysManager);
		await screen.findByRole('tab', { name: t('apiKeys.guide.codexTab') });
		expect(screen.getByText(t('apiKeys.installer.unavailable'))).toBeTruthy();
		expect(screen.queryByRole('button', { name: t('apiKeys.installer.copyPosix') })).toBeNull();
		expect(screen.queryByRole('button', { name: t('apiKeys.installer.copyWindows') })).toBeNull();
		expect(screen.queryByRole('link', { name: t('apiKeys.installer.viewPosix') })).toBeNull();
		expect(screen.queryByRole('link', { name: t('apiKeys.installer.viewWindows') })).toBeNull();
	});

	it('shows SDK examples only for the configured public Lumen URL, independent of discovery', async () => {
		render(ChatApiKeysManager);
		await screen.findByRole('tab', { name: t('apiKeys.guide.codexTab') });
		expect(screen.queryByRole('heading', { name: t('apiKeys.sdk.title') })).toBeNull();
		cleanup();

		initSiteConfig({ lumen_installer_configured: true, lumen_external_url: 'https://lumen.public.example' });
		mocks.get.mockImplementation(async (path: string) => {
			if (path.endsWith('/compat')) throw new Error('offline');
			return response(path);
		});
		render(ChatApiKeysManager);
		await screen.findByRole('heading', { name: t('apiKeys.sdk.title') });
		const example = screen.getByRole('region', { name: 'OpenAI · Python' }).textContent;
		expect(example).toContain('base_url="https://lumen.public.example/v1"');
		expect(example).not.toContain('inference.example');
	});

	it('switches a single accessible guide without refetching discovery', async () => {
		render(ChatApiKeysManager);
		const codexTab = await screen.findByRole('tab', { name: t('apiKeys.guide.codexTab') });
		const codexPanel = screen.getByRole('tabpanel', { name: t('apiKeys.guide.codexTab') });
		expect(codexTab.getAttribute('aria-controls')).toBe(codexPanel.id);
		const discoveryRequests = mocks.get.mock.calls.filter(([path]) => String(path).endsWith('/compat')).length;

		for (const key of ['apiKeys.guide.claudeCodeTab', 'apiKeys.guide.openaiTab', 'apiKeys.guide.claudeTab', 'apiKeys.guide.codexTab'] as const) {
			const name = t(key);
			await fireEvent.click(screen.getByRole('tab', { name }));
			expect(screen.getAllByRole('tabpanel')).toEqual([screen.getByRole('tabpanel', { name })]);
			expect(screen.getByRole('tab', { name }).getAttribute('aria-selected')).toBe('true');
		}
		expect(mocks.get.mock.calls.filter(([path]) => String(path).endsWith('/compat'))).toHaveLength(discoveryRequests);
	});

	it('keeps key management available but hides examples until discovery retry succeeds', async () => {
		let unavailable = true;
		mocks.get.mockImplementation((path: string) => {
			if (path.endsWith('/compat')) return unavailable ? Promise.reject(new Error('offline')) : Promise.resolve(discovery);
			return Promise.resolve([]);
		});
		const { container } = render(ChatApiKeysManager);
		await screen.findByRole('alert');
		expect(container.querySelector('pre')).toBeNull();
		expect(screen.getByRole('button', { name: t('apiKeys.newKey') })).toBeTruthy();
		unavailable = false;
		await fireEvent.click(screen.getByRole('button', { name: t('apiKeys.guide.reload') }));
		await waitFor(() => expect(examples(container)).toContain(discovery.clients.codex.base_url));
		expect(screen.getByRole('tab', { name: t('apiKeys.guide.codexTab') }).getAttribute('aria-selected')).toBe('true');
		expect(screen.queryByRole('alert')).toBeNull();
	});

	it.each([
		'https://user:password@inference.example/v1',
		'https://inference.example/v1?key=private',
		'https://inference.example/v1#private',
		'https://inference.example/v1\n',
		'https://inference.example\\private/v1'
	])('hides all executable examples for unsafe discovery URL %j', async (url) => {
		mocks.get.mockImplementation((path: string) => Promise.resolve(path.endsWith('/compat') ? {
			endpoints: {
				openai: { sdk_base_url: url },
				anthropic: discovery.endpoints.anthropic,
				gateway: discovery.endpoints.gateway
			},
			clients: discovery.clients,
		} : []));
		const { container } = render(ChatApiKeysManager);
		await screen.findByRole('alert');
		expect(container.querySelector('pre')).toBeNull();
		expect(container.textContent).not.toContain(url);
	});

	it('does not replace the current project endpoint with a late response from the previous project', async () => {
		let resolvePrevious!: (value: typeof discovery) => void;
		const previous = new Promise<typeof discovery>((resolve) => { resolvePrevious = resolve; });
		mocks.get.mockImplementation((path: string, _token: string, project: string) => {
			if (!path.endsWith('/compat')) return Promise.resolve([]);
			return project === 'project-1' ? previous : Promise.resolve(discovery);
		});
		const { container } = render(ChatApiKeysManager);
		await waitFor(() => expect(mocks.get).toHaveBeenCalledWith('/api/v1/chat/compat', 'browser-token', 'project-1'));
		auth.update((state) => ({ ...state, projectId: 'project-2' }));
		await waitFor(() => expect(examples(container)).toContain(discovery.clients.codex.base_url));
		resolvePrevious({
			endpoints: {
				openai: { sdk_base_url: 'https://previous.example/v1' },
				anthropic: { sdk_base_url: 'https://previous.example' },
				gateway: { base_url: 'https://previous.example/v1/claude-gateway' }
			},
			clients: { codex: { base_url: 'https://previous.example/v1' } }
		});
		await previous;
		await tick();
		expect(examples(container)).toContain(discovery.clients.codex.base_url);
		expect(examples(container)).not.toContain('previous.example');
	});

	it('renames an active API key in place', async () => {
		render(ChatApiKeysManager);

		await fireEvent.click(await screen.findByRole('button', { name: t('apiKeys.rename') }));
		const input = screen.getByRole('textbox', { name: t('apiKeys.nameLabel') });
		await fireEvent.input(input, { target: { value: '새 이름' } });
		await fireEvent.click(screen.getByRole('button', { name: t('apiKeys.save') }));

		await waitFor(() => {
			expect(mocks.patch).toHaveBeenCalledWith(
				'/api/v1/chat/api-keys/17',
				{ name: '새 이름' },
				'browser-token',
				'project-1'
			);
		});
	});

	it('rejects limits above the user quota and saves valid nullable limits', async () => {
		render(ChatApiKeysManager);

		await fireEvent.click(await screen.findByRole('button', { name: t('apiKeys.setLimits') }));
		const monthly = screen.getByLabelText(t('apiKeys.monthlyLimit'));
		const weekly = screen.getByLabelText(t('apiKeys.weeklyLimit'));
		await fireEvent.input(monthly, { target: { value: '2000' } });
		await fireEvent.click(screen.getByRole('button', { name: t('apiKeys.save') }));

		expect(screen.getByRole('alert').id).toBe(`${monthly.id}-message`);
		expect(mocks.patch).not.toHaveBeenCalled();

		await fireEvent.input(monthly, { target: { value: '500' } });
		await fireEvent.input(weekly, { target: { value: '' } });
		await fireEvent.click(screen.getByRole('button', { name: t('apiKeys.save') }));

		await waitFor(() => {
			expect(mocks.patch).toHaveBeenCalledWith(
				'/api/v1/chat/api-keys/17/limits',
				{ monthly_credit_limit: '500', weekly_credit_limit: null },
				'browser-token',
				'project-1'
			);
		});
	});

	it('blocks a limit above the administrator ceiling before sending a request', async () => {
		mocks.get.mockImplementation((path: string) => Promise.resolve(
			path.endsWith('/compat')
				? discovery
				: path.endsWith('/api-keys')
					? [{ ...apiKey, admin_monthly_credit_limit: '500', effective_monthly_credit_limit: '500' }]
					: []
		));
		render(ChatApiKeysManager);

		await fireEvent.click(await screen.findByRole('button', { name: t('apiKeys.setLimits') }));
		const monthly = screen.getByLabelText(t('apiKeys.monthlyLimit'));
		await fireEvent.input(monthly, { target: { value: '800' } });
		await fireEvent.click(screen.getByRole('button', { name: t('apiKeys.save') }));

		expect(screen.getByRole('alert').id).toBe(`${monthly.id}-message`);
		expect(mocks.patch).not.toHaveBeenCalled();
	});
});
