import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';
import { tick } from 'svelte';
import { get, writable } from 'svelte/store';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { EnrollmentPolicy, SignupRequest, SignupRequestPage } from '$lib/types/enrollmentPolicy';

vi.mock('$lib/stores/auth', () => ({
	auth: writable({ token: 'token-a', projectId: 'project-a', userId: 'user-a', sessionId: 'session-a', domainId: 'domain-a', identityDomainId: 'home-a', isSystemAdmin: true }),
	authReady: writable(true), projectSwitching: writable(false), logoutInProgress: writable(false),
}));
const mocks = vi.hoisted(() => ({ get: vi.fn(), put: vi.fn(), post: vi.fn() }));
vi.mock('$lib/api/client', () => ({
	api: { get: mocks.get, put: mocks.put, post: mocks.post },
	ApiError: class ApiError extends Error {
		constructor(public status: number, message: string) { super(message); }
	},
}));

import { ApiError } from '$lib/api/client';
import { auth, authReady, projectSwitching, logoutInProgress } from '$lib/stores/auth';
import { initLocale } from '$lib/i18n/runtime.svelte';
import { t } from '$lib/i18n/ns/admin-system';
import AdminEnrollmentPolicyPanel from '../AdminEnrollmentPolicyPanel.svelte';

const policyPath = '/api/v1/admin/enrollment-policy';
const queuePath = '/api/v1/admin/signup-requests';
const initialAuth = get(auth);
const readOptions = { refresh: true, cache: 'no-store', replayOnUnauthorized: false };
const writeOptions = { cache: 'no-store', replayOnUnauthorized: false };
function policy(overrides: Partial<EnrollmentPolicy> = {}): EnrollmentPolicy {
	return { revision: 7, public_signup_enabled: false, approval_mode: 'admin',
		personal_quotas: { instances: 0, cores: -1, ram: 1024 },
		quota_fields: { compute: ['instances', 'cores', 'ram', 'future_native_key'] },
		defaults_future_only: true, smtp_configured: false, ...overrides };
}
function request(id = 'request-a', status: SignupRequest['status'] = 'pending'): SignupRequest {
	return { id, source: 'oidc', email: `${id}@example.test`, domain_id: 'organization-a', provider_id: 'oidc-provider-a', status,
		created_at: '2026-10-19T01:00:00Z', reviewed_at: status === 'pending' ? null : '2026-10-19T02:00:00Z',
		reviewed_by_user_id: status === 'pending' ? null : 'reviewer-a' };
}
function page(items = [request()], next_cursor: string | null = null): SignupRequestPage { return { items, next_cursor }; }
function deferred<T>() {
	let resolve!: (value: T) => void;
	let reject!: (reason: unknown) => void;
	const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no; });
	return { promise, resolve, reject };
}
async function settle() { await Promise.resolve(); await tick(); }
async function loaded() {
	await screen.findByRole('form', { name: t('enrollment.policyForm') });
	await screen.findByRole('article', { name: t('enrollment.requestLabel', { email: request().email, id: request().id }) });
}
function submit() { return fireEvent.submit(screen.getByRole('form', { name: t('enrollment.policyForm') })); }
function row(value: SignupRequest) { return screen.getByRole('article', { name: t('enrollment.requestLabel', { email: value.email, id: value.id }) }); }
function field(name: string) { return screen.getByRole('textbox', { name }) as HTMLInputElement; }
function button(key: Parameters<typeof t>[0]) { return screen.getByRole('button', { name: t(key) }) as HTMLButtonElement; }

beforeEach(() => {
	vi.resetAllMocks(); initLocale('en');
	auth.set({ ...initialAuth }); authReady.set(true); projectSwitching.set(false); logoutInProgress.set(false);
	mocks.get.mockImplementation((path: string) => Promise.resolve(path === policyPath ? policy() : page()));
	mocks.put.mockResolvedValue(policy({ revision: 8 }));
	mocks.post.mockResolvedValue(request('request-a', 'approved'));
});
afterEach(() => {
	cleanup(); auth.set({ ...initialAuth }); authReady.set(true); projectSwitching.set(false); logoutInProgress.set(false); initLocale('ko');
});

describe('AdminEnrollmentPolicyPanel consumer', () => {
	it('loads fresh policy and pending queue once without a second authority verification; uses API fields rather than a fixed service list', async () => {
		render(AdminEnrollmentPolicyPanel); await loaded();
		expect(mocks.get.mock.calls).toEqual([
			[policyPath, 'token-a', 'project-a', readOptions],
			[`${queuePath}?status=pending`, 'token-a', 'project-a', readOptions],
		]);
		expect(field('Instances').value).toBe('0'); expect(field('vCPUs').value).toBe('-1');
		expect(field(t('enrollment.quotaKey', { key: 'future_native_key' })).value).toBe('');
		expect(screen.queryByRole('textbox', { name: 'Volumes' })).toBeNull();
		expect(screen.getByText(t('enrollment.futureOnly'))).toBeTruthy();
		expect(screen.getByText(t('enrollment.smtpMissing'))).toBeTruthy();
		expect(screen.getByText(t('enrollment.mailUnconfirmed'))).toBeTruthy();
	});

	it('saves exactly one CAS revision with explicit zero, unlimited and omitted/native defaults; uses returned revision on the next edit', async () => {
		const saving = deferred<EnrollmentPolicy>(); mocks.put.mockReturnValueOnce(saving.promise);
		render(AdminEnrollmentPolicyPanel); await loaded();
		await fireEvent.click(screen.getByRole('checkbox', { name: t('enrollment.publicEmail') }));
		await fireEvent.change(screen.getByRole('combobox', { name: t('enrollment.approvalMode') }), { target: { value: 'auto' } });
		await fireEvent.input(field('RAM (MiB)'), { target: { value: '' } });
		await fireEvent.input(field(t('enrollment.quotaKey', { key: 'future_native_key' })), { target: { value: '42' } });
		await submit(); await submit();
		expect(mocks.put.mock.calls).toEqual([[policyPath, { revision: 7, public_signup_enabled: true, approval_mode: 'auto',
			personal_quotas: { instances: 0, cores: -1, future_native_key: 42 } }, 'token-a', 'project-a', writeOptions]]);
		expect(button('enrollment.saving').disabled).toBe(true);
		expect(button('enrollment.reloadPolicy').disabled).toBe(true);
		saving.resolve(policy({ revision: 8, public_signup_enabled: true, approval_mode: 'auto', personal_quotas: { instances: 0, cores: -1, future_native_key: 42 } }));
		await screen.findByText(t('enrollment.saved'));
		expect(field('RAM (MiB)').value).toBe('');
		await submit(); expect(mocks.put.mock.calls[1][1].revision).toBe(8);
	});

	it.each(['-2', '1.5', '1e3', 'NaN', '9007199254740992'])('does not submit invalid quota %s', async value => {
		render(AdminEnrollmentPolicyPanel); await loaded();
		await fireEvent.input(field('Instances'), { target: { value } }); await submit();
		await screen.findByText(t('enrollment.invalidQuota')); expect(mocks.put).not.toHaveBeenCalled();
	});

	it('does not replay or silently reload a revision conflict; explicit reload discards the draft and enables a new CAS save', async () => {
		mocks.put.mockRejectedValueOnce(new ApiError(409, 'policy_revision_conflict'));
		render(AdminEnrollmentPolicyPanel); await loaded();
		await fireEvent.input(field('Instances'), { target: { value: '99' } }); await submit();
		await screen.findByText(t('enrollment.conflict'));
		expect(button('enrollment.save').disabled).toBe(true);
		await submit(); expect(mocks.put).toHaveBeenCalledTimes(1); expect(mocks.get).toHaveBeenCalledTimes(2);
		mocks.get.mockImplementation((path: string) => Promise.resolve(path === policyPath ? policy({ revision: 12, personal_quotas: { instances: 3 } }) : page()));
		await fireEvent.click(button('enrollment.reloadPolicy'));
		await waitFor(() => expect(field('Instances').value).toBe('3'));
		expect(button('enrollment.save').disabled).toBe(false); expect(screen.queryByText(t('enrollment.conflict'))).toBeNull();
		await submit(); expect(mocks.put.mock.calls[1][1].revision).toBe(12); expect(mocks.put.mock.calls[1][1].personal_quotas).toEqual({ instances: 3 });
	});

	it('distinguishes failed reads from empty and never automatically retries an uncertain save', async () => {
		mocks.get.mockRejectedValueOnce(new Error('offline'));
		render(AdminEnrollmentPolicyPanel);
		await screen.findByText(t('enrollment.loadFailed'));
		expect(screen.queryByRole('form')).toBeNull(); expect(mocks.get).toHaveBeenCalledTimes(2);
		await fireEvent.click(button('enrollment.reloadPolicy')); await screen.findByRole('form');
		mocks.put.mockRejectedValueOnce(new Error('connection lost')); await submit();
		await screen.findByText(t('enrollment.saveFailed')); await submit();
		expect(mocks.put).toHaveBeenCalledTimes(1); expect(button('enrollment.save').disabled).toBe(true);
	});

	it('keeps complete safe identity, state and review information together with actions only on pending requests', async () => {
		const values = [request(), request('approved', 'approved'), request('rejected', 'rejected'), request('consumed', 'consumed')];
		mocks.get.mockImplementation((path: string) => Promise.resolve(path === policyPath ? policy({ smtp_configured: true }) : page(values)));
		render(AdminEnrollmentPolicyPanel); await loaded();
		for (const value of values) {
			const queries = within(row(value));
			for (const text of [value.email, value.id, value.domain_id!, value.provider_id!, value.created_at, t(`enrollment.status.${value.status}`), t('enrollment.source.oidc')]) {
				expect(queries.getByText(text)).toBeTruthy();
			}
			if (value.reviewed_at) { expect(queries.getByText(value.reviewed_at)).toBeTruthy(); expect(queries.getByText(value.reviewed_by_user_id!)).toBeTruthy(); }
			expect(queries.queryByRole('button', { name: t('enrollment.approve') }) !== null).toBe(value.status === 'pending');
			expect(queries.queryByRole('button', { name: t('enrollment.reject') }) !== null).toBe(value.status === 'pending');
		}
		expect(screen.getByText(t('enrollment.smtpReady'))).toBeTruthy(); expect(mocks.post).not.toHaveBeenCalled();
	});

	it.each(['approve', 'reject'] as const)('requires an explicit %s decision and prevents duplicate/cross-row mutations without native creation', async action => {
		const decision = deferred<SignupRequest>(); mocks.post.mockReturnValueOnce(decision.promise);
		mocks.get.mockImplementation((path: string) => Promise.resolve(path === policyPath ? policy() : page([request(), request('request-b')])));
		render(AdminEnrollmentPolicyPanel); await loaded();
		expect(mocks.post).not.toHaveBeenCalled();
		await fireEvent.click(within(row(request())).getByRole('button', { name: t(`enrollment.${action}`) }));
		await fireEvent.click(within(row(request('request-b'))).getByRole('button', { name: t('enrollment.approve') }));
		expect(mocks.post.mock.calls).toEqual([[`${queuePath}/request-a/${action}`, {}, 'token-a', 'project-a', writeOptions]]);
		expect(button('enrollment.reloadQueue').disabled).toBe(true);
		expect((screen.getByRole('combobox', { name: t('enrollment.filter') }) as HTMLSelectElement).disabled).toBe(true);
		decision.resolve(request('request-a', action === 'approve' ? 'approved' : 'rejected'));
		await screen.findByText(t('enrollment.decisionRecorded', { email: request().email, status: t(`enrollment.status.${action === 'approve' ? 'approved' : 'rejected'}`) }));
		expect(screen.queryByRole('article', { name: t('enrollment.requestLabel', { email: request().email, id: request().id }) })).toBeNull();
		expect(row(request('request-b'))).toBeTruthy(); expect(mocks.put).not.toHaveBeenCalled(); expect(mocks.get).toHaveBeenCalledTimes(2);
	});

	it('renders the returned decision status in all-status view rather than assuming the requested transition', async () => {
		render(AdminEnrollmentPolicyPanel); await loaded();
		await fireEvent.change(screen.getByRole('combobox', { name: t('enrollment.filter') }), { target: { value: 'all' } });
		await screen.findByRole('article'); mocks.post.mockResolvedValueOnce(request('request-a', 'consumed'));
		await fireEvent.click(button('enrollment.approve'));
		await within(row(request())).findByText(t('enrollment.status.consumed'));
		expect(screen.queryByRole('button', { name: t('enrollment.approve') })).toBeNull();
		expect(screen.getByText(t('enrollment.mailUnconfirmed'))).toBeTruthy();
	});

	it('follows opaque cursors, supports previous pages, and resets pagination for every status filter', async () => {
		const opaque = 'next+/=?opaque';
		mocks.get.mockImplementation((path: string) => Promise.resolve(path === policyPath ? policy()
			: path.includes('cursor=') ? page([request('page-two')]) : page([request()], opaque)));
		render(AdminEnrollmentPolicyPanel); await loaded(); await fireEvent.click(button('enrollment.next'));
		await screen.findByText('page-two@example.test'); expect(screen.queryByText(request().email)).toBeNull();
		expect(button('enrollment.next').disabled).toBe(true);
		expect(mocks.get.mock.calls.at(-1)).toEqual([`${queuePath}?status=pending&cursor=${encodeURIComponent(opaque)}`, 'token-a', 'project-a', readOptions]);
		await fireEvent.click(button('enrollment.previous')); await screen.findByText(request().email);
		expect(button('enrollment.previous').disabled).toBe(true);
		for (const status of ['approved', 'rejected', 'all', 'pending']) {
			await fireEvent.change(screen.getByRole('combobox', { name: t('enrollment.filter') }), { target: { value: status } });
			await screen.findByRole('article');
			expect(mocks.get.mock.calls.at(-1)).toEqual([`${queuePath}?status=${status}`, 'token-a', 'project-a', readOptions]);
			expect(button('enrollment.previous').disabled).toBe(true);
		}
	});

	it('discards late filter pages and requires explicit reload after failed review instead of replaying', async () => {
		const older = deferred<SignupRequestPage>();
		render(AdminEnrollmentPolicyPanel); await loaded();
		mocks.get.mockReturnValueOnce(older.promise).mockResolvedValueOnce(page([request('current')]));
		const filter = screen.getByRole('combobox', { name: t('enrollment.filter') });
		await fireEvent.change(filter, { target: { value: 'approved' } });
		await fireEvent.change(filter, { target: { value: 'all' } });
		await screen.findByText('current@example.test'); older.resolve(page([request('late')])); await settle();
		expect(screen.queryByText('late@example.test')).toBeNull();
		mocks.post.mockRejectedValueOnce(new ApiError(409, 'request_already_reviewed'));
		await fireEvent.click(button('enrollment.approve')); await screen.findByText(t('enrollment.decisionFailed'));
		expect(screen.queryByRole('article')).toBeNull(); expect(mocks.post).toHaveBeenCalledTimes(1);
		await fireEvent.click(button('enrollment.reloadQueue')); await screen.findByRole('article');
		expect(mocks.post).toHaveBeenCalledTimes(1);
	});

	it('preserves stored quotas for services not exposed for editing by the current API', async () => {
		mocks.get.mockImplementation((path: string) => Promise.resolve(path === policyPath
			? policy({ personal_quotas: { instances: 0, shares: 5 }, quota_fields: { compute: ['instances'] } }) : page()));
		render(AdminEnrollmentPolicyPanel); await loaded();
		expect(screen.queryByRole('textbox', { name: 'Shares' })).toBeNull();
		await fireEvent.input(field('Instances'), { target: { value: '' } }); await submit();
		expect(mocks.put.mock.calls[0][1].personal_quotas).toEqual({ shares: 5 });
	});

	it('distinguishes persisted approval with failed notification from an unknown review outcome and never retries mail by approving again', async () => {
		mocks.post.mockRejectedValueOnce(new ApiError(503, 'signup_approval_notification_failed; approval remains approved'));
		render(AdminEnrollmentPolicyPanel); await loaded(); await fireEvent.click(button('enrollment.approve'));
		await screen.findByText(t('enrollment.notificationFailed'));
		expect(screen.queryByText(t('enrollment.decisionFailed'))).toBeNull(); expect(screen.queryByRole('article')).toBeNull();
		mocks.get.mockResolvedValueOnce(page([request('request-a', 'approved')]));
		await fireEvent.change(screen.getByRole('combobox', { name: t('enrollment.filter') }), { target: { value: 'approved' } });
		const approved = await screen.findByRole('article', { name: t('enrollment.requestLabel', { email: request().email, id: request().id }) });
		await within(approved).findByText(t('enrollment.status.approved'));
		expect(screen.queryByRole('button', { name: t('enrollment.approve') })).toBeNull(); expect(mocks.post).toHaveBeenCalledTimes(1);
	});

	it('does not present a queue failure as verified empty', async () => {
		mocks.get.mockImplementation((path: string) => path === policyPath ? Promise.resolve(policy()) : Promise.reject(new Error('unavailable')));
		render(AdminEnrollmentPolicyPanel); await screen.findByText(t('enrollment.queueFailed'));
		expect(screen.queryByText(t('enrollment.empty'))).toBeNull(); expect(screen.queryByRole('article')).toBeNull();
	});

	it('waits for root readiness and hides private data and late mutation results on authority loss', async () => {
		authReady.set(false); render(AdminEnrollmentPolicyPanel); await settle(); expect(mocks.get).not.toHaveBeenCalled();
		authReady.set(true); await loaded();
		const save = deferred<EnrollmentPolicy>(); mocks.put.mockReturnValueOnce(save.promise); await submit();
		authReady.set(false); await settle();
		expect(screen.queryByRole('form')).toBeNull(); expect(screen.queryByRole('article')).toBeNull();
		expect(button('enrollment.reloadPolicy').disabled).toBe(true);
		save.resolve(policy({ personal_quotas: { instances: 999 } })); await settle();
		expect(screen.queryByText(t('enrollment.saved'))).toBeNull(); expect(screen.queryByRole('textbox', { name: 'Instances' })).toBeNull();
	});

	it.each(['token', 'projectId', 'sessionId', 'userId', 'domainId', 'identityDomainId', 'isSystemAdmin', 'readiness', 'switching', 'logout'])(
		'ignores same-tick %s ABA late read responses, including restored identical credentials', async kind => {
			const oldPolicy = deferred<EnrollmentPolicy>(); const oldPage = deferred<SignupRequestPage>();
			mocks.get.mockReturnValueOnce(oldPolicy.promise).mockReturnValueOnce(oldPage.promise);
			render(AdminEnrollmentPolicyPanel); await waitFor(() => expect(mocks.get).toHaveBeenCalledTimes(2));
			if (kind === 'readiness') { authReady.set(false); authReady.set(true); }
			else if (kind === 'switching') { projectSwitching.set(true); projectSwitching.set(false); }
			else if (kind === 'logout') { logoutInProgress.set(true); logoutInProgress.set(false); }
			else {
				auth.set({ ...initialAuth, [kind]: kind === 'isSystemAdmin' ? false : 'different-owner' }); auth.set({ ...initialAuth });
			}
			oldPolicy.resolve(policy({ personal_quotas: { instances: 999 } })); oldPage.resolve(page([request('late-private-identity')]));
			await loaded(); await settle();
			expect(field('Instances').value).toBe('0'); expect(screen.queryByText('late-private-identity@example.test')).toBeNull();
			expect(mocks.get).toHaveBeenCalledTimes(4);
		},
	);

	it.each(['save', 'review'] as const)('hides same-tick session ABA %s success without replaying the accepted mutation', async action => {
		const save = deferred<EnrollmentPolicy>(); const decision = deferred<SignupRequest>();
		render(AdminEnrollmentPolicyPanel); await loaded();
		mocks.put.mockReturnValueOnce(save.promise); mocks.post.mockReturnValueOnce(decision.promise);
		if (action === 'save') await submit(); else await fireEvent.click(button('enrollment.approve'));
		auth.set({ ...initialAuth, sessionId: 'session-b' }); auth.set({ ...initialAuth });
		save.resolve(policy({ personal_quotas: { instances: 999 } })); decision.resolve(request('request-a', 'approved'));
		await loaded(); await settle();
		expect(field('Instances').value).toBe('0');
		expect(within(row(request())).getByText(t('enrollment.status.pending'))).toBeTruthy();
		expect(screen.queryByText(t('enrollment.saved'))).toBeNull();
		expect(screen.queryByText(t('enrollment.decisionRecorded', { email: request().email, status: t('enrollment.status.approved') }))).toBeNull();
		expect(mocks.put).toHaveBeenCalledTimes(action === 'save' ? 1 : 0); expect(mocks.post).toHaveBeenCalledTimes(action === 'review' ? 1 : 0);
	});
});
