import { afterEach, beforeEach, describe, expect, it, vi, type Mock } from 'vitest';
import { get } from 'svelte/store';
import { tick } from 'svelte';
import { beginExperienceAction, beginExperienceLoad, beginExperienceRequest, experienceApplied, experienceHealth, experienceMessage, experienceRequest, experienceState, installExperienceCollector, recordExperience, type ExperienceCollectorController } from '../experience';
import type { InteractionOwner } from '../interactionAudit';

vi.mock('svelte', () => ({ tick: vi.fn(() => Promise.resolve()) }));
const originalFetch = window.fetch;
let collector: ExperienceCollectorController;
let owner: InteractionOwner;
let changed: () => void;
let enabled: boolean;
let suppressed: boolean;
let baseUrl: string;
let route: string;
let transport: Mock;
const contract = { schema_version: 2, enabled: true, redaction_revision: 1, max_batch_events: 20, max_body_bytes: 32768 };
function batches() { return transport.mock.calls.filter(([url]) => String(url).endsWith('/experience-events')).map(([, init]) => JSON.parse(init.body)); }
function rows() { return batches().flatMap(batch => batch.events); }
function mount() {
	collector = installExperienceCollector({ getOwner: () => owner, getRoute: () => route, getBaseUrl: () => baseUrl, isEnabled: () => enabled, isSuppressed: () => suppressed, subscribeOwner: callback => { changed = callback; return () => {}; }, frontendBuild: '1.2.3', catalogRevision: 'source-1' });
}
beforeEach(() => {
	vi.useFakeTimers();
	vi.mocked(tick).mockImplementation(() => Promise.resolve());
	owner = { token: 'private-token', sessionId: 'session-a', userId: 'user-a', identityDomainId: 'home-a', domainId: 'domain-a', projectId: 'project-a' };
	enabled = true; suppressed = false; baseUrl = 'http://localhost:8000';
	route = '/(console)/dashboard/compute/instances/[id]';
	transport = vi.fn(async (url: string, init?: RequestInit) => {
		if (url.endsWith('/experience-contract')) return Response.json(contract);
		const events = JSON.parse(String(init?.body)).events;
		return Response.json({ schema_version: 2, accepted: events.length, duplicates: 0 }, { status: 201 });
	});
	window.fetch = transport as typeof fetch;
	mount();
});
afterEach(() => { collector.destroy(); window.fetch = originalFetch; vi.useRealTimers(); });

describe('explicit privacy-safe semantic observations', () => {
	it('captures a child setup load before mount and reuses its page ID for the single committed initial view', async () => {
		const childLoad = beginExperienceLoad('compute', 'resource.list')!;
		expect(childLoad).toBeDefined();
		recordExperience(childLoad, 'result.received', { http_status: 200 });
		await collector.flush();
		expect(rows().some(row => row.event_type === 'view.entered')).toBe(false);
		collector.navigate(route);
		collector.navigate(route);
		await collector.flush();
		expect(rows().filter(row => row.event_type === 'view.entered')).toHaveLength(1);
		expect(rows().every(row => row.page_view_id === childLoad.pageViewId)).toBe(true);
	});
	it('binds destination child loads before afterNavigate without prematurely claiming view entry', async () => {
		const previous = beginExperienceLoad('compute', 'resource.list')!;
		route = '/dashboard/volumes';
		const destination = beginExperienceLoad('block_storage', 'resource.list')!;
		expect(destination.route).toBe('/dashboard/volumes');
		expect(destination.pageViewId).not.toBe(previous.pageViewId);
		expect(experienceRequest(destination).headers['X-Afterglow-Page']).toBe('/dashboard/volumes');
		recordExperience(destination, 'result.received', { http_status: 200 });
		recordExperience(previous, 'result.received', { http_status: 200 });
		await collector.flush();
		expect(rows().some(row => row.event_type === 'view.entered')).toBe(false);
		expect(rows().find(row => row.page_view_id === previous.pageViewId).route).toBe('/dashboard/compute/instances/:id');
		collector.navigate(route);
		await collector.flush();
		expect(rows().find(row => row.event_type === 'view.entered').page_view_id).toBe(destination.pageViewId);
	});
	it('filters anonymous protected pages before batching while preserving public login and exact logout observations', async () => {
		owner = { token: null, userId: null, projectId: null, domainId: null }; changed();
		expect(beginExperienceLoad('compute', 'resource.list')).toBeUndefined();
		route = '/login';
		const login = beginExperienceAction('auth', 'sign_in', 'auth.login')!;
		experienceState(login, 'ready');
		route = '/admin/events';
		expect(beginExperienceLoad('admin', 'admin.events')).toBeUndefined();
		route = '/logout';
		const logout = beginExperienceAction('auth', 'sign_out', 'page')!;
		experienceState(logout, 'ready');
		route = '/logout/[id]';
		expect(beginExperienceLoad('auth', 'page')).toBeUndefined();
		await collector.flush();
		expect(rows()).toHaveLength(4);
		expect(rows().every(row => row.route === '/login' || row.route === '/logout')).toBe(true);
	});
	it('attributes canonical compute page views, exposure and unlinked API loads to compute rather than Activity', async () => {
		route = '/compute/instances'; collector.navigate(route);
		const ctx = beginExperienceRequest('GET')!;
		expect(ctx.feature).toBe('compute'); expect(ctx.actionId).toBeUndefined();
		recordExperience(ctx, 'result.received', { http_status: 200 });
		await collector.flush();
		expect(rows().map(row => row.event_type)).toEqual(['view.entered', 'view.exposure_changed', 'result.received']);
		expect(rows().every(row => row.feature === 'compute')).toBe(true);
	});
	it.each([
		['/dashboard/volumes', 'block_storage'],
		['/dashboard/file-storage', 'file_storage'],
		['/dashboard/object-storage', 'object_storage'],
		['/dashboard/network', 'network'],
		['/dashboard/iam', 'iam'],
		['/dashboard/chat', 'lumen'],
		['/admin/users', 'admin'],
		['/login', 'auth'],
		['/:id', 'activity'],
	])('uses the fixed canonical feature map for %s', async (destination, feature) => {
		route = destination; collector.navigate(route);
		expect(beginExperienceRequest('GET')?.feature).toBe(feature);
	});
	it('captures source-owned polling loads without an invented human action or click edge', async () => {
		const ctx = beginExperienceLoad('container', 'resource.list')!;
		expect(ctx.action).toBe('load'); expect(ctx.actionId).toBeUndefined(); expect(ctx.rootEventId).toBeUndefined();
		experienceState(ctx, 'ready'); await collector.flush();
		expect(rows()).toHaveLength(1);
		expect(rows()[0]).toMatchObject({ feature: 'container', action: 'load', component: 'resource.list', event_type: 'view.state_changed' });
		expect(rows()[0].action_id).toBeUndefined();
	});
	it('fences tutorial suppression ABA synchronously even when it completes during one pending action', async () => {
		const ctx = beginExperienceAction('compute', 'create', 'compute.create')!;
		suppressed = true; changed();
		suppressed = false; changed();
		expect(recordExperience(ctx, 'result.received', { http_status: 202 })).toBeUndefined();
		await collector.flush();
		expect(transport).not.toHaveBeenCalled();
	});
	it('keeps overlapping actions separate through awaits, with unique attempt child spans', async () => {
		const first = beginExperienceAction('compute', 'create', 'compute.create')!;
		const second = beginExperienceAction('block_storage', 'create', 'block_storage.create')!;
		const firstSend = experienceRequest(first, 1), retry = experienceRequest(first, 2), secondSend = experienceRequest(second, 1);
		expect(firstSend.headers['X-Afterglow-Experience-Action']).toBe(first.actionId);
		expect(secondSend.headers['X-Afterglow-Experience-Action']).toBe(second.actionId);
		expect(retry.headers['X-Afterglow-Experience-Span']).not.toBe(firstSend.headers['X-Afterglow-Experience-Span']);
		expect(retry.headers['X-Afterglow-Experience-Attempt']).toBe('2');
		await Promise.resolve();
		experienceState(first, 'loading'); experienceState(second, 'ready');
		await collector.flush();
		expect(rows().filter(row => row.action_id === first.actionId).map(row => row.feature)).toEqual(['compute', 'compute']);
		expect(rows().find(row => row.event_type === 'view.state_changed' && row.feature === 'compute').caused_by_event_id).toBe(first.rootEventId);
		expect(JSON.stringify(rows())).not.toContain('private-token');
		expect(rows()[0].route).toBe('/dashboard/compute/instances/:id');
	});
	it('preserves same-owner rotation but fences project/home/user/session ABA and disabled tutorial/mock modes', async () => {
		const first = beginExperienceAction('auth', 'verify', 'auth.verification')!;
		owner = { ...owner, token: 'renewed-private' }; changed();
		experienceState(first, 'ready'); await collector.flush();
		expect(rows()).toHaveLength(2);
		const sent = transport.mock.calls.find(([url]) => String(url).endsWith('/experience-events'))!;
		expect(sent[1].headers.Authorization).toBe('Bearer renewed-private');
		for (const field of ['projectId', 'identityDomainId', 'userId', 'sessionId', 'domainId'] as const) {
			const ctx = beginExperienceAction('auth', 'verify', 'auth.verification')!;
			const old = owner[field]; owner = { ...owner, [field]: 'other' }; changed(); owner = { ...owner, [field]: old }; changed();
			expect(recordExperience(ctx, 'result.applied', { stage: 'state' })).toBeUndefined();
		}
		suppressed = true; changed(); expect(beginExperienceAction('auth', 'view', 'page')).toBeUndefined();
		suppressed = false; enabled = false; changed(); expect(beginExperienceAction('auth', 'view', 'page')).toBeUndefined();
		await collector.flush(); expect(rows()).toHaveLength(2);
	});
	it('records state application and DOM commit distinctly and rejects superseded same-owner commits', async () => {
		const pending = Promise.withResolvers<void>(); vi.mocked(tick).mockImplementationOnce(() => pending.promise);
		let current = true;
		const ctx = beginExperienceAction('compute', 'refresh', 'resource.list')!;
		const applied = experienceApplied(ctx, { http_status: 202 }, () => current);
		current = false; pending.resolve(); await applied; await collector.flush();
		expect(rows().map(row => row.event_type)).toEqual(['action.started', 'result.applied', 'result.discarded']);
		expect(rows().at(-1).payload).toMatchObject({ stage: 'dom', reason: 'stale' });
		expect(rows().some(row => row.event_type === 'result.committed')).toBe(false);
	});
	it('fences a DOM tick spanning logout and does not claim authenticated application from the anonymous segment', async () => {
		const pending = Promise.withResolvers<void>(); vi.mocked(tick).mockImplementationOnce(() => pending.promise);
		const ctx = beginExperienceAction('auth', 'sign_in', 'auth.login')!;
		const applied = experienceApplied(ctx, {}, () => true);
		owner = { token: null, userId: null, domainId: null, projectId: null }; changed();
		pending.resolve(); await applied; await collector.flush();
		expect(transport).not.toHaveBeenCalled();
		expect(get(experienceHealth).dropped).toBe(2);
	});
	it('leaves DOM commitment unknown without an explicit current-state assertion', async () => {
		const ctx = beginExperienceAction('compute', 'load', 'resource.list')!;
		await experienceApplied(ctx, { http_status: 201 });
		await collector.flush();
		expect(rows().map(row => row.event_type)).toEqual(['action.started', 'result.applied']);
	});
	it('records a positive DOM commit only after the explicit live-state assertion survives the tick', async () => {
		const ctx = beginExperienceAction('compute', 'load', 'resource.list')!;
		await experienceApplied(ctx, { http_status: 202 }, () => true);
		await collector.flush();
		expect(rows().map(row => row.event_type)).toEqual(['action.started', 'result.applied', 'result.committed']);
		expect(rows().at(-1).payload.stage).toBe('dom');
	});
	it('preserves only source-owned IAM selector kinds under the approved semantic fence', async () => {
		const ctx = beginExperienceAction('iam', 'select', 'page')!;
		recordExperience(ctx, 'view.state_changed', { state: 'ready', selection_kind: 'project' });
		const wrongAction = beginExperienceAction('iam', 'view', 'page')!;
		recordExperience(wrongAction, 'view.state_changed', { state: 'ready', selection_kind: 'home' });
		await collector.flush();
		expect(rows().find(row => row.action === 'select' && row.event_type === 'view.state_changed').payload).toEqual({ state: 'ready', selection_kind: 'project' });
		expect(rows().find(row => row.action === 'view' && row.event_type === 'view.state_changed').payload).toEqual({ state: 'ready' });
	});
	it('drops unapproved payload fields and restricts MCP selection enums to the consent component', async () => {
		const ctx = beginExperienceAction('mcp', 'select', 'mcp.consent')!;
		recordExperience(ctx, 'view.state_changed', { state: 'ready', access: 'read', selection: 'some', raw: 'private-value' } as never);
		const unrelated = beginExperienceAction('compute', 'view', 'page')!;
		recordExperience(unrelated, 'view.state_changed', { state: 'ready', access: 'manage', selection: 'all' });
		experienceMessage(ctx, { key: 'auth:login.title', locale: 'zh-CN', catalog_revision: 'a'.repeat(64), tone: 'info', restoration: 'restored' });
		await collector.flush();
		expect(rows().find(row => row.feature === 'mcp' && row.event_type === 'view.state_changed').payload).toEqual({ state: 'ready', access: 'read', selection: 'some' });
		expect(rows().find(row => row.feature === 'compute' && row.event_type === 'view.state_changed').payload).toEqual({ state: 'ready' });
		expect(rows().find(row => row.event_type === 'message.presented').payload.locale).toBe('zh-CN');
		expect(JSON.stringify(rows())).not.toContain('private-value');
	});
});

describe('bounded diagnostics transport only', () => {
	it('is default-off without contract discovery or transport, and old servers remain unsupported without v1 downgrade', async () => {
		route = '/login'; enabled = false; changed(); collector.navigate(route); await collector.flush(); expect(transport).not.toHaveBeenCalled();
		enabled = true; changed(); transport.mockResolvedValue(new Response(null, { status: 404 }));
		beginExperienceAction('auth', 'sign_in', 'auth.login'); await collector.flush();
		expect(get(experienceHealth).status).toBe('unsupported');
		expect(beginExperienceAction('auth', 'sign_in', 'auth.login')).toBeUndefined();
		await collector.flush(); expect(transport).toHaveBeenCalledTimes(1);
		expect(transport.mock.calls[0][0]).toContain('/experience-contract');
	});
	it('backs off unavailable capability discovery without extending event deadlines', async () => {
		transport.mockImplementation(async () => new Response(null, { status: 503 }));
		beginExperienceAction('compute', 'create', 'compute.create');
		await collector.flush(); expect(transport).toHaveBeenCalledTimes(1);
		await collector.flush(); expect(transport).toHaveBeenCalledTimes(1);
		vi.setSystemTime(Date.now() + 1499); await collector.flush(); expect(transport).toHaveBeenCalledTimes(1);
		vi.setSystemTime(Date.now() + 1); await collector.flush(); expect(transport).toHaveBeenCalledTimes(2);
		vi.setSystemTime(Date.now() + 1500); await collector.flush(); expect(transport).toHaveBeenCalledTimes(2);
		vi.setSystemTime(Date.now() + 1500); await collector.flush(); expect(transport).toHaveBeenCalledTimes(3);
		vi.setSystemTime(Date.now() + 61000); await collector.flush();
		expect(get(experienceHealth).dropped).toBeGreaterThanOrEqual(1);
		expect(batches()).toHaveLength(0);
	});
	it('retries an ambiguous telemetry transmission with identical IDs once, never repeats it a third time', async () => {
		const normal = transport.getMockImplementation()!;
		transport.mockImplementation((url, init) => String(url).endsWith('/experience-contract') ? normal(url, init) : Promise.reject(new Error('private-network-detail')));
		beginExperienceAction('compute', 'create', 'compute.create');
		await collector.flush(); await collector.flush(); await collector.flush();
		expect(batches()[0]).toEqual(batches()[1]);
		const originalId = batches()[0].events[0].event_id;
		expect(batches()[2].events.some((row: { event_id: string }) => row.event_id === originalId)).toBe(false);
		expect(JSON.stringify(batches())).not.toContain('private-network-detail');
	});
	it('bounds queue to 200 and each request to 20 events/32KiB, reporting loss without input/DOM capture', async () => {
		const ctx = beginExperienceAction('activity', 'view', 'page')!;
		for (let i = 0; i < 240; ++i) experienceState(ctx, 'ready');
		expect(get(experienceHealth)).toMatchObject({ queued: 200, dropped: 41 });
		await collector.flush(); await collector.flush();
		for (const batch of batches()) { expect(batch.events.length).toBeLessThanOrEqual(20); expect(new TextEncoder().encode(JSON.stringify(batch)).byteLength).toBeLessThanOrEqual(32768); }
		for (let i = 0; i < 12; ++i) await collector.flush();
		expect(rows().find(row => row.event_type === 'telemetry.gap').payload).toMatchObject({ reason: 'queue_overflow', count: 41 });
	});
	it('expires original events after 60 seconds even while the contract is unavailable', async () => {
		beginExperienceAction('compute', 'create', 'compute.create');
		vi.setSystemTime(Date.now() + 61000);
		await collector.flush();
		expect(rows().map(row => row.event_type)).toEqual(['telemetry.gap']);
		expect(rows()[0].payload).toEqual({ reason: 'deadline', count: 1 });
	});
	it('fences in-flight acknowledgements and drops old-owner payloads on API-origin changes', async () => {
		const response = Promise.withResolvers<Response>();
		const normal = transport.getMockImplementation()!;
		transport.mockImplementation((url, init) => String(url).endsWith('/experience-contract') ? normal(url, init) : response.promise);
		beginExperienceAction('compute', 'create', 'compute.create'); const flushing = collector.flush();
		await Promise.resolve(); await Promise.resolve(); await Promise.resolve();
		baseUrl = 'http://localhost:9000'; changed(); response.resolve(Response.json({ schema_version: 2, accepted: 1, duplicates: 0 }, { status: 201 })); await flushing;
		expect(get(experienceHealth).sent).toBe(0);
		expect(get(experienceHealth).queued).toBe(0);
	});
});
