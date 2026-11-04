import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { get } from 'svelte/store';
import { auth, authReady, logoutInProgress, projectSwitching, setAuth } from '$lib/stores/auth';
import { refreshAuthState } from '$lib/utils/authSession';
import { adminInventoryScope, setAdminInventoryScope } from '$lib/stores/adminInventoryScope';
import { siteConfig } from '$lib/config/site';
import { t } from '$lib/i18n/ns/admin-ops';
import { experienceUuid, recentReplayQuery, recentReplayRows, replayCause, replayHttpStatus, replayQuery, replayRows, replaySource, replayStatus, replayValue, retainedReplayMessage, type ExperienceRecentQuery, type ExperienceRecentResponse, type ExperienceReplayEvent, type ExperienceReplayQuery, type ExperienceReplayResponse } from '../experienceReplay';

const mocks = vi.hoisted(() => ({ get: vi.fn(), baseUrl: 'https://api.example.invalid' }));
vi.mock('$lib/api/client', () => {
	class ApiError extends Error { constructor(public status: number, message: string) { super(message); } }
	return { api: { get: mocks.get }, ApiError, getBaseUrl: () => mocks.baseUrl, fetchWithAuth: vi.fn() };
});
import { ApiError } from '$lib/api/client';
import ExperienceReplayPanel from '../ExperienceReplayPanel.svelte';

const segment = '11111111-1111-4111-8111-111111111111';
const action = '22222222-2222-4222-8222-222222222222';
const event = '33333333-3333-4333-8333-333333333333';
const query: ExperienceReplayQuery = { segmentId: segment, actionId: '', domainId: '', projectId: '', includeAnonymous: false };
function row(overrides: Partial<ExperienceReplayEvent> = {}): ExperienceReplayEvent {
	return { id: 1, event_id: event, segment_id: segment, page_view_id: segment, action_id: action, caused_by_event_id: null,
		trace_id: segment, span_id: event, parent_span_id: null, source: 'browser', actor: { user_id: 'user-a', project_id: 'project-a' },
		received_at: '2026-11-04T00:00:01Z', occurred_at: '2026-11-04T00:00:00Z', client_seq: 1, client_monotonic_ms: 10,
		route: '/dashboard', feature: 'compute', action: 'create', component: 'compute.create', frontend_build: '1.0.0',
		catalog_revision: 'retained-revision', backend_build: '1.0.0', redaction_revision: 1, event_type: 'message.presented',
		payload: { key: 'test.message', locale: 'ko', tone: 'warning', restoration: 'restored' }, request_id: null, stage: null,
		status: null, http_status: null, operation_id: null, resource_ref: null, ...overrides };
}
function response(events = [row()]): ExperienceReplayResponse {
	return { schema_version: 2, events, has_more: false, coverage: { partial: true, reasons: ['clock_order_unknown'], remote_spans: 'unavailable', screen_tail: 'unknown' },
		catalogs: [{ revision: 'retained-revision', key: 'test.message', locale: 'ko', template: '<img src="https://evil.invalid/secret" onerror="alert(1)"><script>alert(1)</script>' }] };
}
const recentQuery: ExperienceRecentQuery = { userId: '', days: 1, domainId: '', projectId: '', includeAnonymous: false };
function recentResponse(): ExperienceRecentResponse {
	return { schema_version: 2, segments: [{ segment_id: segment, user_id: 'user-a', project_id: 'project-a',
		last_received_at: '2026-11-04T00:00:01Z', event_count: 8 }], has_more: false,
		coverage: { partial: true, reasons: ['clock_order_unknown'] } };
}
async function lookupRecent() {
	await fireEvent.click(screen.getByRole('button', { name: t('experience.recentSearch') }));
}
async function search() {
	await fireEvent.input(screen.getByLabelText(t('experience.segmentId')), { target: { value: segment } });
	await fireEvent.click(screen.getByRole('button', { name: t('experience.search') }));
}
function renewOwner() {
	const current = get(auth);
	setAuth(refreshAuthState({
		token: 'rotated-token', user_id: current.userId!, username: current.username ?? 'Admin', expires_at: null,
		project_id: current.projectId!, project_name: current.projectName ?? 'Project',
		domain_id: current.domainId!, domain_name: 'Domain', identity_domain_id: current.identityDomainId!,
		identity_domain_name: 'Home', roles: current.roles, is_system_admin: current.isSystemAdmin,
		can_write: current.canWrite, is_domain_manager: current.isDomainManager, can_create_domain: current.canCreateDomain,
	}, current));
}

beforeEach(() => {
	vi.clearAllMocks();
	mocks.baseUrl = 'https://api.example.invalid';
	projectSwitching.set(false);
	logoutInProgress.set(false);
	auth.update(current => ({ ...current, token: 'test-token', sessionId: 'session-a', userId: 'user-a', identityDomainId: 'home-a',
		domainId: 'domain-a', projectId: 'project-a', isSystemAdmin: true, roles: ['system_admin'] }));
	authReady.set(true);
	adminInventoryScope.set({ domainId: '', projectId: '', revision: 0 });
	mocks.get.mockResolvedValue(response());
});
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); });

describe('exact diagnostic projection', () => {
	it('keeps browser-reported HTTP status separate from actual server transport completion', () => {
		expect(replayHttpStatus(row({ source: 'api', event_type: 'request.completed', http_status: 202, payload: { http_status: 200 } }))).toBe(202);
		expect(replayHttpStatus(row({ source: 'api', event_type: 'operation.accepted', http_status: 202 }))).toBeNull();
		expect(replayHttpStatus(row({ source: 'browser', http_status: 202, payload: { http_status: 201 } }))).toBe(201);
		expect(replayHttpStatus(row({ source: 'browser', http_status: 202, payload: {} }))).toBeNull();
		expect(replayStatus('observed')).toBe('events.observed');
	});
	it('does not promote unknown sources or accepted/cancel-requested states to success', () => {
		expect(replaySource('unsupported-remote')).toBe('experience.unknown');
		expect(replayStatus('accepted')).toBe('experience.statusAccepted');
		expect(replayStatus('cancel_requested')).toBe('experience.statusCancelRequested');
		expect(replayStatus('outcome_unknown')).toBe('experience.statusOutcomeUnknown');
	});
	it('maps finite diagnostic reasons and leaves unsupported values unknown', () => {
		expect(replayValue('reason', 'smtp_accepted')).toBe('experience.reasonSmtpAccepted');
		expect(replayValue('reason', 'clock_order_unknown')).toBe('experience.reasonClockOrderUnknown');
		expect(replayValue('reason', 'raw-new-server-value')).toBe('experience.unknown');
	});
	it('constructs only bounded diagnostic endpoints with explicit anonymous selection', () => {
		expect(replayQuery(query)).toBe(`/api/v1/admin/experiences?segment_id=${segment}&limit=200&include_anonymous=false`);
		expect(replayQuery({ ...query, actionId: action }, true)).toContain('/api/v1/admin/experiences/export?');
		expect(replayQuery(query, true)).toContain('limit=2000');
		expect(() => replayQuery({ ...query, segmentId: 'https://evil.invalid/a' })).toThrow();
		expect(() => replayQuery({ ...query, includeAnonymous: true, projectId: 'project-a' })).toThrow();
		expect(experienceUuid.test(segment.toUpperCase().replace('11111111', 'AAAAAAAA'))).toBe(false);
	});
	it('never substitutes the newest catalogue or another language for retained history', () => {
		const result = response();
		expect(retainedReplayMessage(row(), result.catalogs)).toContain('<script>');
		expect(retainedReplayMessage(row({ catalog_revision: 'missing-old' }), result.catalogs)).toBeNull();
		expect(retainedReplayMessage(row({ payload: { key: 'test.message', locale: 'en', restoration: 'restored' } }), result.catalogs)).toBeNull();
		expect(retainedReplayMessage(row({ payload: { key: 'test.message', locale: 'ko', restoration: 'redacted' } }), result.catalogs)).toBeNull();
	});
	it('rejects cross-segment, cross-action, explicit cross-project and anonymous rows', () => {
		const result = response([row(), row({ id: 2, segment_id: action }), row({ id: 3, action_id: event }),
			row({ id: 4, actor: { user_id: 'other-user', project_id: 'other-project' } }), row({ id: 5, actor: { user_id: null, project_id: null } })]);
		expect(replayRows(result, { ...query, actionId: action, projectId: 'project-a' }).map(item => item.id)).toEqual([1]);
	});
	it('resolves causal references only inside the same segment and verified actor/project', () => {
		const child = row({ id: 2, event_id: action, caused_by_event_id: event });
		expect(replayCause(child, [row()])?.event_id).toBe(event);
		expect(replayCause(child, [row({ actor: { user_id: 'user-a', project_id: 'other-project' } })])).toBeUndefined();
		expect(replayCause(child, [row({ segment_id: action })])).toBeUndefined();
	});
});

describe('operator replay surface', () => {
	it('keeps page-one records, applied scope and export when page two fails', async () => {
		mocks.get.mockResolvedValueOnce({ ...response(), has_more: true }).mockRejectedValueOnce(new ApiError(503, 'SQL unavailable'));
		render(ExperienceReplayPanel);
		await search();
		await screen.findByText(response().catalogs[0].template);
		await fireEvent.click(screen.getByRole('button', { name: t('experience.more') }));
		await screen.findByText(t('experience.sqlError'));
		expect(screen.getByText(response().catalogs[0].template)).not.toBeNull();
		expect((screen.getByRole('button', { name: t('experience.export') }) as HTMLButtonElement).disabled).toBe(false);
		expect((screen.getByRole('button', { name: t('experience.more') }) as HTMLButtonElement).disabled).toBe(false);
	});
	it.each([401, 403, 404])('retires loaded private rows when page two returns HTTP %s', async (status) => {
		mocks.get.mockResolvedValueOnce({ ...response(), has_more: true }).mockRejectedValueOnce(new ApiError(status, 'fresh scope refused'));
		render(ExperienceReplayPanel);
		await search();
		await screen.findByText(response().catalogs[0].template);
		await fireEvent.click(screen.getByRole('button', { name: t('experience.more') }));
		await screen.findByText(t(status === 404 ? 'experience.unavailable' : 'experience.denied'));
		expect(screen.queryByText(response().catalogs[0].template)).toBeNull();
		expect((screen.getByRole('button', { name: t('experience.export') }) as HTMLButtonElement).disabled).toBe(true);
		expect(screen.queryByRole('button', { name: t('experience.more') })).toBeNull();
	});
	it.each([401, 403, 404])('retires loaded private rows when export returns HTTP %s', async (status) => {
		mocks.get.mockResolvedValueOnce({ ...response(), has_more: true }).mockRejectedValueOnce(new ApiError(status, 'fresh export refused'));
		render(ExperienceReplayPanel);
		await search();
		await screen.findByText(response().catalogs[0].template);
		await fireEvent.click(screen.getByRole('button', { name: t('experience.export') }));
		await screen.findByText(t(status === 404 ? 'experience.unavailable' : 'experience.denied'));
		expect(screen.queryByText(response().catalogs[0].template)).toBeNull();
		expect((screen.getByRole('button', { name: t('experience.export') }) as HTMLButtonElement).disabled).toBe(true);
		expect(screen.queryByRole('button', { name: t('experience.more') })).toBeNull();
	});
	it('uses the unfiltered minimum ID and can continue an entirely filtered page', async () => {
		mocks.get.mockResolvedValueOnce({ ...response([row({ id: 80, segment_id: action })]), has_more: true })
			.mockResolvedValueOnce(response([row({ id: 70 })]));
		render(ExperienceReplayPanel);
		await search();
		await screen.findByText(t('experience.empty'));
		const more = screen.getByRole('button', { name: t('experience.more') });
		expect((more as HTMLButtonElement).disabled).toBe(false);
		await fireEvent.click(more);
		await screen.findByText(response().catalogs[0].template);
		expect(mocks.get.mock.calls[1][0]).toBe(replayQuery(query, false, 80));
	});
	it('merges pages in descending storage ID order, not arrival or wall-clock order', async () => {
		mocks.get.mockResolvedValueOnce({ ...response([row({ id: 100, event_id: event })]), has_more: true })
			.mockResolvedValueOnce(response([row({ id: 70, event_id: segment }), row({ id: 90, event_id: action })]));
		const { container } = render(ExperienceReplayPanel);
		await search();
		await screen.findByText(response().catalogs[0].template);
		await fireEvent.click(screen.getByRole('button', { name: t('experience.more') }));
		await waitFor(() => expect(container.querySelectorAll('[data-experience-event]')).toHaveLength(3));
		expect(Array.from(container.querySelectorAll('[data-experience-event]'), element => element.querySelector('dd')?.textContent)).toEqual([event, action, segment]);
	});
	it('localizes fixed state, stage, exposure, tone and focus values and distinguishes absent cause references', async () => {
		mocks.get.mockResolvedValue(response([
			row({ id: 3, event_type: 'view.state_changed', stage: 'mcp.dispatch', payload: { state: 'ready', step: 2, reason: 'lease_lost' } }),
			row({ id: 2, event_type: 'view.exposure_changed', payload: { visibility: 'hidden', focused: false } }),
			row({ id: 1, payload: { tone: 'warning', locale: 'ko', restoration: 'unavailable' } }),
		]));
		const { container } = render(ExperienceReplayPanel);
		await search();
		await screen.findByText(t('experience.messageUnavailable'));
		const descriptions = Array.from(container.querySelectorAll('[data-experience-event] > p'), element => element.textContent).join(' ');
		for (const raw of ['mcp.dispatch', 'ready', 'hidden', 'false', 'warning', 'lease_lost']) expect(descriptions).not.toContain(raw);
		for (const label of ['stageMcpDispatch', 'stateReady', 'visibilityHidden', 'focusNo', 'toneWarning', 'causeNone'] as const)
			expect(descriptions).toContain(t(`experience.${label}`));
		expect(descriptions).toContain(t('experience.step', { step: 2 }));
		expect(descriptions).toContain(t('experience.reasonLeaseLost'));
		expect(container.querySelector('[data-experience-coverage]')?.textContent).toContain(t('experience.reasonClockOrderUnknown'));
		expect(container.querySelector('[data-experience-coverage]')?.textContent).not.toContain('clock_order_unknown');
	});
	it('does not fetch before a human searches and renders hostile retained text without active markup or resource joins', async () => {
		const { container } = render(ExperienceReplayPanel);
		expect(mocks.get).not.toHaveBeenCalled();
		await search();
		await screen.findByText(response().catalogs[0].template);
		expect(container.querySelector('img, iframe, script, a[href]')).toBeNull();
		expect(screen.getByText(t('experience.coverageNotice'))).not.toBeNull();
		expect(mocks.get).toHaveBeenCalledTimes(1);
		expect(mocks.get.mock.calls[0][0]).toBe(replayQuery(query));
		expect(mocks.get.mock.calls[0][3]).toMatchObject({ cache: 'no-store', replayOnUnauthorized: false });
	});
	it('shows the linked business request rather than the browser batch receipt as the result request', async () => {
		const businessRequest = `req-${'a'.repeat(32)}`;
		const ingestReceipt = `req-${'b'.repeat(32)}`;
		mocks.get.mockResolvedValue(response([row({
			event_type: 'result.received', request_id: ingestReceipt,
			payload: { stage: 'response', http_status: 200, request_id: businessRequest },
		})]));
		render(ExperienceReplayPanel);
		await search();
		await screen.findByText(businessRequest);
		expect(screen.queryByText(ingestReceipt)).toBeNull();
	});
	it('aborts and fences an in-flight response across same-tick scope ABA', async () => {
		const { promise, resolve } = Promise.withResolvers<ExperienceReplayResponse>();
		mocks.get.mockReturnValue(promise);
		render(ExperienceReplayPanel);
		await search();
		const signal = mocks.get.mock.calls[0][3].signal as AbortSignal;
		setAdminInventoryScope('other-domain', 'other-project');
		setAdminInventoryScope('', '');
		resolve(response());
		await waitFor(() => expect(screen.getByText(t('experience.stale'))).not.toBeNull());
		expect(signal.aborted).toBe(true);
		expect(screen.queryByText(response().catalogs[0].template)).toBeNull();
		expect((screen.getByLabelText(t('experience.segmentId')) as HTMLInputElement).value).toBe('');
	});
	it('keeps a same-owner token rotation but clears results on readiness loss', async () => {
		render(ExperienceReplayPanel);
		await search();
		await screen.findByText(response().catalogs[0].template);
		renewOwner();
		expect(screen.getByText(response().catalogs[0].template)).not.toBeNull();
		authReady.set(false);
		await waitFor(() => expect(screen.queryByText(response().catalogs[0].template)).toBeNull());
		expect(get(auth).token).toBe('rotated-token');
	});
	it('clears private results as explicit logout starts, before credentials are removed', async () => {
		render(ExperienceReplayPanel);
		await search();
		await screen.findByText(response().catalogs[0].template);
		logoutInProgress.set(true);
		await waitFor(() => expect(screen.queryByText(response().catalogs[0].template)).toBeNull());
		expect((screen.getByRole('button', { name: t('experience.search') }) as HTMLButtonElement).disabled).toBe(true);
	});
	it('asks for anonymous inclusion only after explicit unscoped selection and accepts server refusal', async () => {
		mocks.get.mockRejectedValue(new ApiError(403, 'anonymous disabled'));
		render(ExperienceReplayPanel);
		await fireEvent.change(screen.getByLabelText(t('experience.anonymous')), { target: { value: 'include' } });
		await search();
		await screen.findByText(t('experience.denied'));
		expect(mocks.get.mock.calls[0][0]).toBe(replayQuery({ ...query, includeAnonymous: true }));
	});
	it.each([[403, 'denied'], [404, 'unavailable'], [503, 'sqlError']] as const)('distinguishes HTTP %s from verified empty', async (status, key) => {
		mocks.get.mockRejectedValue(new ApiError(status, '<script>private SQL error</script>'));
		render(ExperienceReplayPanel);
		await search();
		await screen.findByText(t(`experience.${key}`));
		expect(screen.queryByText(t('experience.empty'))).toBeNull();
		expect(screen.queryByText('<script>private SQL error</script>')).toBeNull();
	});
	it('keeps verified empty distinct from idle and exports only after an explicit click', async () => {
		mocks.get.mockResolvedValue(response([]));
		render(ExperienceReplayPanel);
		await search();
		await screen.findByText(t('experience.empty'));
		expect(mocks.get).toHaveBeenCalledTimes(1);
		const create = vi.fn(() => 'blob:owned-readonly-json');
		const revoke = vi.fn();
		vi.stubGlobal('URL', class extends URL { static createObjectURL = create; static revokeObjectURL = revoke; });
		const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
		await fireEvent.click(screen.getByRole('button', { name: t('experience.export') }));
		await screen.findByText(t('experience.exportComplete'));
		expect(mocks.get.mock.calls[1][0]).toBe(replayQuery(query, true));
		expect(create).toHaveBeenCalledWith(expect.any(Blob));
		expect(click).toHaveBeenCalledTimes(1);
		expect(revoke).toHaveBeenCalledWith('blob:owned-readonly-json');
		click.mockRestore(); vi.unstubAllGlobals();
	});
});

describe('recent support-code discovery', () => {
	it('bounds the diagnostic query and validates row metadata without operational joins', () => {
		expect(recentReplayQuery(recentQuery)).toBe('/api/v1/admin/experiences/segments?days=1&limit=20&include_anonymous=false');
		expect(recentReplayQuery({ ...recentQuery, userId: 'user-a', days: 30, domainId: 'domain-a', projectId: 'project-a' }))
			.toContain('user_id=user-a&domain_id=domain-a&project_id=project-a');
		expect(() => recentReplayQuery({ ...recentQuery, userId: 'x'.repeat(65) })).toThrow();
		expect(() => recentReplayQuery({ ...recentQuery, days: 2 as 1 })).toThrow();
		expect(() => recentReplayQuery({ ...recentQuery, includeAnonymous: true, domainId: 'domain-a' })).toThrow();
		const valid = recentResponse().segments[0];
		const result = { ...recentResponse(), segments: [valid,
			{ ...valid, segment_id: 'https://evil.invalid' }, { ...valid, event_count: -1 },
			{ ...valid, last_received_at: '2026-11-04T00:00:01' }, { ...valid, user_id: '' },
			{ ...valid, project_id: 'other-project' }, { ...valid, user_id: 'other-user' }] };
		expect(recentReplayRows(result, { ...recentQuery, userId: 'user-a', projectId: 'project-a' })).toEqual([valid]);
	});
	it('requires human lookup, then code selection and a separate exact query before export', async () => {
		mocks.get.mockResolvedValueOnce(recentResponse()).mockResolvedValue(response());
		render(ExperienceReplayPanel);
		expect(mocks.get).not.toHaveBeenCalled();
		await lookupRecent();
		await screen.findByRole('button', { name: t('experience.recentSelectCode', { code: segment }) });
		expect(mocks.get.mock.calls[0][0]).toBe(recentReplayQuery(recentQuery));
		expect(mocks.get.mock.calls[0][3]).toMatchObject({ cache: 'no-store', replayOnUnauthorized: false });
		await fireEvent.click(screen.getByRole('button', { name: t('experience.recentSelectCode', { code: segment }) }));
		expect((screen.getByLabelText(t('experience.segmentId')) as HTMLInputElement).value).toBe(segment);
		expect((screen.getByLabelText(t('experience.actionId')) as HTMLInputElement).value).toBe('');
		expect(mocks.get).toHaveBeenCalledTimes(1);
		await fireEvent.click(screen.getByRole('button', { name: t('experience.search') }));
		await screen.findByText(response().catalogs[0].template);
		const create = vi.fn(() => 'blob:recent-discovery-export');
		vi.stubGlobal('URL', class extends URL { static createObjectURL = create; static revokeObjectURL = vi.fn(); });
		vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
		await fireEvent.click(screen.getByRole('button', { name: t('experience.export') }));
		await screen.findByText(t('experience.exportComplete'));
		expect(mocks.get.mock.calls.map(call => call[0])).toEqual([recentReplayQuery(recentQuery), replayQuery(query), replayQuery(query, true)]);
		expect(create).toHaveBeenCalledWith(expect.any(Blob));
	});
	it('uses only explicit current scope and filter values, and never fetches usernames or resources', async () => {
		setAdminInventoryScope('domain-a', 'project-a');
		mocks.get.mockResolvedValue(recentResponse());
		render(ExperienceReplayPanel);
		await fireEvent.input(screen.getByLabelText(t('experience.recentUserId')), { target: { value: ' user-a ' } });
		await fireEvent.change(screen.getByLabelText(t('experience.recentDays')), { target: { value: '7' } });
		expect(mocks.get).not.toHaveBeenCalled();
		await lookupRecent();
		await screen.findByRole('button', { name: t('experience.recentSelectCode', { code: segment }) });
		expect(mocks.get.mock.calls[0][0]).toBe(recentReplayQuery({ ...recentQuery, userId: 'user-a', days: 7, domainId: 'domain-a', projectId: 'project-a' }));
		expect((screen.getByLabelText(t('experience.anonymous')) as HTMLSelectElement).disabled).toBe(true);
		expect(mocks.get).toHaveBeenCalledTimes(1);
	});
	it('shows loading and clears data when recent filters change without auto-querying', async () => {
		const pending = Promise.withResolvers<ExperienceRecentResponse>();
		mocks.get.mockReturnValue(pending.promise);
		render(ExperienceReplayPanel);
		await lookupRecent();
		await screen.findByText(t('experience.recentLoading'));
		const signal = mocks.get.mock.calls[0][3].signal as AbortSignal;
		await fireEvent.change(screen.getByLabelText(t('experience.recentDays')), { target: { value: '30' } });
		pending.resolve(recentResponse());
		await waitFor(() => expect(screen.queryByText(t('experience.recentLoading'))).toBeNull());
		expect(signal.aborted).toBe(true);
		expect(screen.queryByRole('button', { name: t('experience.recentSelectCode', { code: segment }) })).toBeNull();
		expect(mocks.get).toHaveBeenCalledTimes(1);
	});
	it('aborts same-tick scope ABA and clears previous-owner user filters and lookback', async () => {
		const pending = Promise.withResolvers<ExperienceRecentResponse>();
		mocks.get.mockReturnValue(pending.promise);
		render(ExperienceReplayPanel);
		await fireEvent.input(screen.getByLabelText(t('experience.recentUserId')), { target: { value: 'private-old-user' } });
		await fireEvent.change(screen.getByLabelText(t('experience.recentDays')), { target: { value: '30' } });
		await lookupRecent();
		const signal = mocks.get.mock.calls[0][3].signal as AbortSignal;
		setAdminInventoryScope('other-domain', 'other-project');
		setAdminInventoryScope('', '');
		pending.resolve(recentResponse());
		await waitFor(() => expect((screen.getByLabelText(t('experience.recentUserId')) as HTMLInputElement).value).toBe(''));
		expect((screen.getByLabelText(t('experience.recentDays')) as HTMLSelectElement).value).toBe('1');
		expect(signal.aborted).toBe(true);
		expect(screen.queryByRole('button', { name: t('experience.recentSelectCode', { code: segment }) })).toBeNull();
	});
	it('permits bearer rotation but clears discovery and filters for another identity', async () => {
		const pending = Promise.withResolvers<ExperienceRecentResponse>();
		mocks.get.mockReturnValue(pending.promise);
		render(ExperienceReplayPanel);
		await fireEvent.input(screen.getByLabelText(t('experience.recentUserId')), { target: { value: 'user-a' } });
		await lookupRecent();
		renewOwner();
		pending.resolve(recentResponse());
		await screen.findByRole('button', { name: t('experience.recentSelectCode', { code: segment }) });
		auth.update(current => ({ ...current, userId: 'user-b' }));
		await waitFor(() => expect(screen.queryByRole('button', { name: t('experience.recentSelectCode', { code: segment }) })).toBeNull());
		expect((screen.getByLabelText(t('experience.recentUserId')) as HTMLInputElement).value).toBe('');
	});
	it('fences base-URL ABA synchronously and clears filters before a late result', async () => {
		const pending = Promise.withResolvers<ExperienceRecentResponse>();
		mocks.get.mockReturnValue(pending.promise);
		render(ExperienceReplayPanel);
		await lookupRecent();
		const signal = mocks.get.mock.calls[0][3].signal as AbortSignal;
		mocks.baseUrl = 'https://other.example.invalid';
		siteConfig.update(current => ({ ...current }));
		mocks.baseUrl = 'https://api.example.invalid';
		siteConfig.update(current => ({ ...current }));
		pending.resolve(recentResponse());
		await waitFor(() => expect(screen.queryByText(t('experience.recentLoading'))).toBeNull());
		expect(signal.aborted).toBe(true);
		expect(screen.queryByRole('button', { name: t('experience.recentSelectCode', { code: segment }) })).toBeNull();
	});
	it.each([() => authReady.set(false), () => logoutInProgress.set(true), () => projectSwitching.set(true)])('clears discovery when authority readiness is lost', async (revoke) => {
		mocks.get.mockResolvedValue(recentResponse());
		render(ExperienceReplayPanel);
		await lookupRecent();
		await screen.findByRole('button', { name: t('experience.recentSelectCode', { code: segment }) });
		revoke();
		await waitFor(() => expect(screen.queryByRole('button', { name: t('experience.recentSelectCode', { code: segment }) })).toBeNull());
		expect((screen.getByRole('button', { name: t('experience.recentSearch') }) as HTMLButtonElement).disabled).toBe(true);
	});
	it('aborts discovery on unmount without publishing a late result', async () => {
		const pending = Promise.withResolvers<ExperienceRecentResponse>();
		mocks.get.mockReturnValue(pending.promise);
		const { unmount } = render(ExperienceReplayPanel);
		await lookupRecent();
		const signal = mocks.get.mock.calls[0][3].signal as AbortSignal;
		await unmount();
		pending.resolve(recentResponse());
		expect(signal.aborted).toBe(true);
	});
	it.each([[401, 'denied'], [403, 'denied'], [404, 'unavailable'], [503, 'sqlError'], [500, 'failed']] as const)('does not mislabel recent HTTP %s as empty', async (status, key) => {
		mocks.get.mockRejectedValue(new ApiError(status, '<script>private database failure</script>'));
		render(ExperienceReplayPanel);
		await lookupRecent();
		await screen.findByText(t(`experience.${key}`));
		expect(screen.queryByText(t('experience.recentEmpty'))).toBeNull();
		expect(screen.queryByText('<script>private database failure</script>')).toBeNull();
	});
	it('distinguishes verified empty from idle, and labels partial stored-row observations', async () => {
		mocks.get.mockResolvedValue({ ...recentResponse(), segments: [], has_more: true });
		render(ExperienceReplayPanel);
		expect(screen.getByText(t('experience.recentIdle'))).not.toBeNull();
		await lookupRecent();
		await screen.findByText(t('experience.recentEmpty'));
		expect(screen.getByText(t('experience.recentPartial'))).not.toBeNull();
		expect(screen.queryByText(t('experience.recentIdle'))).toBeNull();
	});
	it.each([401, 403, 404])('retires a loaded exact timeline when recent disclosure returns HTTP %s', async (status) => {
		mocks.get.mockResolvedValueOnce(response()).mockRejectedValueOnce(new ApiError(status, 'authority refused'));
		render(ExperienceReplayPanel);
		await search();
		await screen.findByText(response().catalogs[0].template);
		await lookupRecent();
		await screen.findByText(t(status === 404 ? 'experience.unavailable' : 'experience.denied'));
		expect(screen.queryByText(response().catalogs[0].template)).toBeNull();
		expect((screen.getByRole('button', { name: t('experience.export') }) as HTMLButtonElement).disabled).toBe(true);
	});
	it('renders provided identities as escaped text and omits invalid UUIDs and cross-project rows', async () => {
		const safe = recentResponse().segments[0];
		setAdminInventoryScope('domain-a', 'project-a');
		mocks.get.mockResolvedValue({ ...recentResponse(), segments: [
			{ ...safe, user_id: '<img src=x onerror=alert(1)>' }, { ...safe, segment_id: 'https://evil.invalid' },
			{ ...safe, segment_id: action, project_id: 'other-project' }] });
		const { container } = render(ExperienceReplayPanel);
		await lookupRecent();
		await screen.findByText('<img src=x onerror=alert(1)>');
		expect(container.querySelector('img, script, a[href]')).toBeNull();
		expect(screen.getAllByRole('button', { name: t('experience.recentSelectCode', { code: segment }) })).toHaveLength(1);
		expect(screen.queryByRole('button', { name: t('experience.recentSelectCode', { code: action }) })).toBeNull();
	});
	it('requires explicit anonymous inclusion and never newly attributes unknown owners', async () => {
		const anonymous = { ...recentResponse().segments[0], user_id: '', project_id: '' };
		mocks.get.mockResolvedValue({ ...recentResponse(), segments: [anonymous] });
		render(ExperienceReplayPanel);
		await fireEvent.change(screen.getByLabelText(t('experience.anonymous')), { target: { value: 'include' } });
		await lookupRecent();
		await screen.findByText(t('experience.recentUnknownOwner'));
		expect(mocks.get.mock.calls[0][0]).toBe(recentReplayQuery({ ...recentQuery, includeAnonymous: true }));
	});
});
