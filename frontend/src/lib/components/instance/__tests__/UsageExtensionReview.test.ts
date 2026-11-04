import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { tick } from 'svelte';
import { writable } from 'svelte/store';
import { initLocale } from '$lib/i18n/runtime.svelte';
import { t } from '$lib/i18n/ns/usage-schedule';
import type { UsageExtensionPage, UsageExtensionPolicy, UsageExtensionRequest } from '$lib/types/instanceUsage';

const transport = vi.hoisted(() => ({ get: vi.fn(), put: vi.fn(), post: vi.fn() }));
vi.mock('$lib/api/client', () => ({ api: transport, ApiError: class ApiError extends Error {} }));
vi.mock('$lib/stores/auth', () => ({
	auth: writable({ token: 'token-a', projectId: 'project-a', userId: 'actor-a', sessionId: 'login-a',
		domainId: 'working-domain', identityDomainId: 'identity-domain', roles: ['member'], isDomainManager: false,
		isSystemAdmin: false, canWrite: true }),
	authReady: writable(true), projectSwitching: writable(false),
}));
import { auth, authReady, projectSwitching } from '$lib/stores/auth';
import UsageExtensionReview from '../UsageExtensionReview.svelte';

const policyPath = '/api/v1/instances/usage-extension-policy';
const requestsPath = '/api/v1/instances/usage-extension-requests';
const policy = (overrides: Partial<UsageExtensionPolicy> = {}): UsageExtensionPolicy => ({
	domain_id: 'working-domain', review_required: true, revision: 'policy-a', can_manage: false, ...overrides,
});
const request = (overrides: Partial<UsageExtensionRequest> = {}): UsageExtensionRequest => ({
	id: 'request-a', domain_id: 'working-domain', project_id: 'project-a', instance_id: 'vm-a', instance_name: 'Research VM',
	requested_by: 'actor-a', requested_at: '2099-01-01T00:00:00Z', expires_at: '2099-03-01T00:00:00Z', reason: 'Continue research',
	schedule_revision: 'schedule-a', policy_revision: 'policy-a', revision: 'request-revision-a', status: 'pending',
	reviewed_by: null, reviewed_at: null, can_review: false, ...overrides,
});
function reads(nextPolicy = policy(), items = [request()], next_cursor: string | null = null) {
	transport.get.mockImplementation(async (url: string) => url.startsWith(policyPath) ? nextPolicy : { items, next_cursor });
}
async function ready() { await screen.findByText('Research VM'); await waitFor(() => expect(screen.getByRole<HTMLButtonElement>('button', { name: t('refresh') }).disabled).toBe(false)); }
beforeEach(() => {
	transport.get.mockReset(); transport.put.mockReset(); transport.post.mockReset();
	auth.set({ token: 'token-a', refreshToken: null, accessExpiresAt: null, userId: 'actor-a', username: 'actor',
		projectId: 'project-a', projectName: 'A', availableProjects: [], roles: ['member'], isSystemAdmin: false,
		canWrite: true, federated: false, domainId: 'working-domain', domainName: 'Working',
		identityDomainId: 'identity-domain', isDomainManager: false, sessionId: 'login-a' });
	authReady.set(true); projectSwitching.set(false); initLocale('en'); reads();
});
afterEach(cleanup);

describe('usage extension policy and reviewer queue', () => {
	it('shows ordinary project members their requests without manufacturing reviewer or policy authority', async () => {
		render(UsageExtensionReview); await ready();
		expect(screen.getByText(t('pendingWarning'))).toBeTruthy();
		expect(screen.getByText(t('reviewRequired'))).toBeTruthy();
		expect(screen.queryByRole('button', { name: t('approve') })).toBeNull();
		expect(screen.queryByRole('button', { name: t('policySave') })).toBeNull();
		expect(screen.queryByRole('combobox', { name: t('reviewScope') })).toBeNull();
		expect(transport.get).toHaveBeenCalledWith(requestsPath, 'token-a', 'project-a', expect.objectContaining({ cache: 'no-store' }));
	});

	it.each(['approve', 'reject'] as const)('lets an exact project administrator %s without entering the system-admin console', async decision => {
		auth.update(value => ({ ...value, roles: ['project_admin'] }));
		reads(policy(), [request({ can_review: true })]);
		transport.post.mockResolvedValue(request({ can_review: false, status: decision === 'approve' ? 'approved' : 'rejected', revision: 'reviewed' }));
		render(UsageExtensionReview); await ready();
		await fireEvent.click(screen.getByRole('button', { name: t(decision) }));
		await screen.findByText(t('reviewSaved'));
		expect(transport.post).toHaveBeenCalledWith(`${requestsPath}/request-a/review`, { decision, revision: 'request-revision-a' },
			'token-a', 'project-a', { signal: expect.any(AbortSignal), replayOnUnauthorized: false });
		expect(screen.getByText(t(decision === 'approve' ? 'request.approved' : 'request.rejected'))).toBeTruthy();
		expect(transport.put).not.toHaveBeenCalled();
	});

	it('uses the current working domain, never credential-home domain, for a domain-manager queue and policy', async () => {
		auth.update(value => ({ ...value, isDomainManager: true }));
		reads(policy({ can_manage: true }), [request({ can_review: true })]);
		render(UsageExtensionReview); await ready();
		await fireEvent.change(screen.getByRole('combobox', { name: t('reviewScope') }), { target: { value: 'domain' } });
		await ready();
		expect(transport.get).toHaveBeenCalledWith(`${requestsPath}?domain_id=working-domain`, 'token-a', 'project-a', expect.any(Object));
		expect(transport.get).toHaveBeenCalledWith(`${policyPath}?domain_id=working-domain`, 'token-a', 'project-a', expect.any(Object));
		expect(transport.get.mock.calls.some(([url]) => url.includes('identity-domain'))).toBe(false);
		transport.put.mockResolvedValue(policy({ can_manage: true, review_required: false, revision: 'policy-b' }));
		await fireEvent.change(screen.getByRole('combobox', { name: t('policyTitle') }), { target: { value: 'false' } });
		await fireEvent.click(screen.getByRole('button', { name: t('policySave') }));
		await screen.findByText(t('automatic'));
		expect(transport.put).toHaveBeenCalledWith(`${policyPath}?domain_id=working-domain`, { review_required: false, revision: 'policy-a' },
			'token-a', 'project-a', { signal: expect.any(AbortSignal), replayOnUnauthorized: false });
		expect(screen.getByText(t('request.pending'))).toBeTruthy();
	});

	it('loads, changes policy and reviews a domain request without a selected project', async () => {
		auth.update(value => ({ ...value, projectId: null, projectName: null, isDomainManager: true }));
		reads(policy({ can_manage: true }), [request({ project_id: 'domain-project', can_review: true })]);
		render(UsageExtensionReview); await ready();
		expect(screen.getByRole<HTMLSelectElement>('combobox', { name: t('reviewScope') }).value).toBe('domain');
		expect(screen.getByRole<HTMLOptionElement>('option', { name: t('projectScope') }).disabled).toBe(true);
		expect(transport.get).toHaveBeenCalledWith(`${requestsPath}?domain_id=working-domain`, 'token-a', undefined, expect.any(Object));
		expect(transport.get).toHaveBeenCalledWith(`${policyPath}?domain_id=working-domain`, 'token-a', undefined, expect.any(Object));
		expect(transport.get.mock.calls.every(([url]) => url.endsWith('?domain_id=working-domain'))).toBe(true);
		transport.put.mockResolvedValue(policy({ can_manage: true, review_required: false, revision: 'policy-b' }));
		await fireEvent.change(screen.getByRole('combobox', { name: t('policyTitle') }), { target: { value: 'false' } });
		await fireEvent.click(screen.getByRole('button', { name: t('policySave') }));
		await screen.findByText(t('automatic'));
		expect(transport.put).toHaveBeenCalledWith(`${policyPath}?domain_id=working-domain`, { review_required: false, revision: 'policy-a' },
			'token-a', undefined, { signal: expect.any(AbortSignal), replayOnUnauthorized: false });
		transport.post.mockResolvedValue(request({ project_id: 'domain-project', can_review: false, status: 'approved' }));
		await fireEvent.click(screen.getByRole('button', { name: t('approve') }));
		await screen.findByText(t('reviewSaved'));
		expect(transport.post).toHaveBeenCalledWith(`${requestsPath}/request-a/review`, { decision: 'approve', revision: 'request-revision-a' },
			'token-a', undefined, { signal: expect.any(AbortSignal), replayOnUnauthorized: false });
	});

	it('does not read a projectless domain queue without manager authority or verified readiness', async () => {
		auth.update(value => ({ ...value, projectId: null, projectName: null }));
		render(UsageExtensionReview); await tick();
		expect(transport.get).not.toHaveBeenCalled();
		authReady.set(false);
		auth.update(value => ({ ...value, isDomainManager: true }));
		await tick();
		expect(transport.get).not.toHaveBeenCalled();
		authReady.set(true); await ready();
		expect(transport.get).toHaveBeenCalledWith(`${requestsPath}?domain_id=working-domain`, 'token-a', undefined, expect.any(Object));
	});

	it('does not infer domain policy management from system-admin or project-admin presentation roles', async () => {
		auth.update(value => ({ ...value, roles: ['admin', 'project_admin'], isSystemAdmin: true }));
		render(UsageExtensionReview); await ready();
		expect(screen.queryByRole('form', { name: t('policyTitle') })).toBeNull();
	});

	it('keeps policy-read failure distinct from automatic policy and request inventory', async () => {
		transport.get.mockImplementation(async (url: string) => {
			if (url.startsWith(policyPath)) throw new Error('Unavailable');
			return { items: [request()], next_cursor: null };
		});
		render(UsageExtensionReview); await ready();
		expect(screen.getByText(t('policyFailed'))).toBeTruthy();
		expect(screen.queryByText(t('automatic'))).toBeNull();
		expect(screen.getByText('Continue research')).toBeTruthy();
	});

	it('does not turn failed or foreign-project inventory into an empty or reviewable queue', async () => {
		reads(policy(), [request({ project_id: 'foreign-project', reason: 'Foreign private reason', can_review: true })]);
		render(UsageExtensionReview);
		await screen.findByText(t('requestsFailed'));
		expect(screen.queryByText('Foreign private reason')).toBeNull();
		expect(screen.queryByText(t('requestsEmpty'))).toBeNull();
		expect(screen.queryByRole('button', { name: t('approve') })).toBeNull();
	});

	it('requires an explicit fresh read after an uncertain review and never replays it', async () => {
		reads(policy(), [request({ can_review: true })]); transport.post.mockRejectedValue(new Error('Uncertain'));
		render(UsageExtensionReview); await ready();
		await fireEvent.click(screen.getByRole('button', { name: t('approve') }));
		await screen.findByText(t('operationFailed'));
		expect(screen.getByRole<HTMLButtonElement>('button', { name: t('approve') }).disabled).toBe(true);
		expect(transport.post).toHaveBeenCalledTimes(1);
		await fireEvent.click(screen.getByRole('button', { name: t('refresh') })); await ready();
		expect(transport.post).toHaveBeenCalledTimes(1);
	});

	it.each(['applying', 'uncertain', 'stale'] as const)('never presents %s review outcomes as a successful approval or an action to replay', async status => {
		reads(policy(), [request({ can_review: true })]);
		transport.post.mockResolvedValue(request({ status, can_review: true }));
		render(UsageExtensionReview); await ready();
		await fireEvent.click(screen.getByRole('button', { name: t('approve') }));
		await screen.findByText(t(`request.${status}`));
		expect(screen.queryByText(t('reviewSaved'))).toBeNull();
		expect(screen.queryByRole('button', { name: t('approve') })).toBeNull();
		expect(screen.queryByRole('button', { name: t('reject') })).toBeNull();
		expect(transport.post).toHaveBeenCalledTimes(1);
	});

	it('discards old request results after same-tick logical-login ABA', async () => {
		const old = Promise.withResolvers<UsageExtensionPage>();
		transport.get.mockImplementation((url: string) => url.startsWith(policyPath) ? Promise.resolve(policy()) : old.promise);
		render(UsageExtensionReview); await waitFor(() => expect(transport.get).toHaveBeenCalledTimes(2));
		reads(policy(), [request({ reason: 'Fresh result' })]);
		auth.update(value => ({ ...value, sessionId: 'login-b' }));
		auth.update(value => ({ ...value, sessionId: 'login-a' }));
		await screen.findByText('Fresh result');
		old.resolve({ items: [request({ reason: 'Old private result' })], next_cursor: null }); await tick();
		expect(screen.queryByText('Old private result')).toBeNull();
	});

	it('clears private content and ignores an in-flight review when readiness is lost', async () => {
		reads(policy(), [request({ can_review: true })]);
		const pending = Promise.withResolvers<UsageExtensionRequest>(); transport.post.mockReturnValue(pending.promise);
		render(UsageExtensionReview); await ready(); await fireEvent.click(screen.getByRole('button', { name: t('approve') }));
		authReady.set(false); await tick();
		expect(screen.queryByText('Continue research')).toBeNull();
		pending.resolve(request({ reason: 'Old reviewed private result', status: 'approved' })); await tick();
		expect(screen.queryByText('Old reviewed private result')).toBeNull();
		expect(screen.queryByText(t('reviewSaved'))).toBeNull();
	});

	it('preserves a same-owner in-flight review across bearer renewal', async () => {
		reads(policy(), [request({ can_review: true })]);
		const pending = Promise.withResolvers<UsageExtensionRequest>(); transport.post.mockReturnValue(pending.promise);
		render(UsageExtensionReview); await ready(); await fireEvent.click(screen.getByRole('button', { name: t('approve') }));
		const signal = transport.post.mock.calls[0][4].signal;
		auth.update(value => ({ ...value, token: 'renewed-token' })); await tick();
		expect(signal.aborted).toBe(false);
		pending.resolve(request({ status: 'approved', can_review: false })); await screen.findByText(t('reviewSaved'));
		expect(transport.get).toHaveBeenCalledTimes(2);
	});

	it('loads successive cursor pages and deduplicates rows moved by live review transitions', async () => {
		reads(policy(), [request()], 'cursor-a');
		render(UsageExtensionReview); await ready();
		transport.get.mockImplementation(async (url: string) => {
			if (url === `${requestsPath}?cursor=cursor-a`) return {
				items: [request({ status: 'approved', reason: 'Reviewed while paging' }),
					request({ id: 'request-b', instance_name: 'Older pending VM', reason: 'Older request' })],
				next_cursor: 'cursor-b',
			};
			if (url === `${requestsPath}?cursor=cursor-b`) return {
				items: [request({ id: 'request-c', instance_name: 'Oldest pending VM', reason: 'Still reachable' })],
				next_cursor: null,
			};
			throw new Error('Unexpected page');
		});
		await fireEvent.click(screen.getByRole('button', { name: t('loadMore') }));
		await screen.findByText('Older pending VM');
		expect(screen.getAllByText('Research VM')).toHaveLength(1);
		expect(screen.getByText('Reviewed while paging')).toBeTruthy();
		await fireEvent.click(screen.getByRole('button', { name: t('loadMore') }));
		await screen.findByText('Oldest pending VM');
		expect(screen.getByText('Still reachable')).toBeTruthy();
		expect(screen.queryByRole('button', { name: t('loadMore') })).toBeNull();
		expect(transport.get.mock.calls.filter(([url]) => url.startsWith(policyPath))).toHaveLength(1);
		expect(transport.get).toHaveBeenCalledWith(`${requestsPath}?cursor=cursor-b`, 'token-a', 'project-a',
			expect.objectContaining({ cache: 'no-store' }));
	});

	it('retains loaded requests and the cursor after a failed page without reporting an empty queue', async () => {
		reads(policy(), [request()], 'cursor-a');
		render(UsageExtensionReview); await ready();
		transport.get.mockRejectedValueOnce(new Error('Page unavailable'));
		await fireEvent.click(screen.getByRole('button', { name: t('loadMore') }));
		await screen.findByText(t('requestsFailed'));
		expect(screen.getByText('Continue research')).toBeTruthy();
		expect(screen.queryByText(t('requestsEmpty'))).toBeNull();
		transport.get.mockResolvedValueOnce({ items: [request({ id: 'request-b', instance_name: 'Retried older VM' })], next_cursor: null });
		await fireEvent.click(screen.getByRole('button', { name: t('loadMore') }));
		await screen.findByText('Retried older VM');
		expect(transport.get.mock.calls.filter(([url]) => url === `${requestsPath}?cursor=cursor-a`)).toHaveLength(2);
		expect(screen.queryByText(t('requestsFailed'))).toBeNull();
	});

	it('clears a projectless domain cursor and ignores its late page when manager scope is replaced', async () => {
		auth.update(value => ({ ...value, projectId: null, projectName: null, isDomainManager: true }));
		reads(policy({ can_manage: true }), [request()], 'domain-cursor');
		render(UsageExtensionReview); await ready();
		const pending = Promise.withResolvers<UsageExtensionPage>();
		transport.get.mockReturnValueOnce(pending.promise);
		await fireEvent.click(screen.getByRole('button', { name: t('loadMore') }));
		const pageCall = transport.get.mock.calls.find(([url]) => url.includes('cursor=domain-cursor'))!;
		expect(pageCall[0]).toBe(`${requestsPath}?domain_id=working-domain&cursor=domain-cursor`);
		expect(pageCall[2]).toBeUndefined();
		reads(policy(), [request({ project_id: 'project-b', reason: 'Fresh project queue' })]);
		auth.update(value => ({ ...value, projectId: 'project-b', isDomainManager: false }));
		await screen.findByText('Fresh project queue');
		expect(pageCall[3].signal.aborted).toBe(true);
		expect(transport.get).toHaveBeenCalledWith(requestsPath, 'token-a', 'project-b', expect.objectContaining({ cache: 'no-store' }));
		pending.resolve({ items: [request({ reason: 'Old private domain page' })], next_cursor: 'old-next' });
		await tick();
		expect(screen.queryByText('Old private domain page')).toBeNull();
		expect(screen.queryByRole('button', { name: t('loadMore') })).toBeNull();
	});

	it('preserves an in-flight page across same-owner bearer renewal', async () => {
		reads(policy(), [request()], 'cursor-a');
		render(UsageExtensionReview); await ready();
		const pending = Promise.withResolvers<UsageExtensionPage>();
		transport.get.mockReturnValueOnce(pending.promise);
		await fireEvent.click(screen.getByRole('button', { name: t('loadMore') }));
		const signal = transport.get.mock.lastCall![3].signal;
		auth.update(value => ({ ...value, token: 'renewed-token' })); await tick();
		expect(signal.aborted).toBe(false);
		pending.resolve({ items: [request({ id: 'request-b', instance_name: 'Renewed page VM' })], next_cursor: null });
		await screen.findByText('Renewed page VM');
		expect(transport.get).toHaveBeenCalledTimes(3);
	});

	it.each(['ko', 'en', 'ja', 'zh-CN', 'bn', 'ms', 'nb', 'sw', 'vi'] as const)('provides policy, review and follow-up copy in %s', async locale => {
		initLocale(locale); render(UsageExtensionReview); await ready();
		expect(screen.getByRole('heading', { name: t('reviewTitle') })).toBeTruthy();
		for (const key of ['extensionLimit', 'reasonFollowup', 'pendingWarning', 'policyHelp', 'request.uncertain', 'loadMore'] as const) {
			expect(t(key)).not.toBe(key);
		}
	});
});
