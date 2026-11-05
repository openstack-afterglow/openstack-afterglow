import { setImmediate as nextTurn } from 'node:timers/promises';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/svelte';
import { tick } from 'svelte';
import { get } from 'svelte/store';
import { acceptAuthVerification, auth, authReady, getAuthVerificationEpoch, projectSwitching, setAuth } from '$lib/stores/auth';
import { siteConfig } from '$lib/config/site';
import { api } from '$lib/api/client';
import { refreshAuthState } from '$lib/utils/authSession';
import { captureFlowExperience, type CapturedFlowExperience } from '$lib/stores/__tests__/experienceFlowHarness';
import * as experience from '$lib/utils/experience';
import ContainerPage from '../+page.svelte';
import FilePage from '../../../../file-storage/[id]/+page.svelte';

const route = vi.hoisted(() => ({ set: null as null | ((id: string) => void) }));
vi.mock('$app/environment', () => ({ browser: true }));
vi.mock('$app/navigation', () => ({ goto: vi.fn() }));
vi.mock('$app/stores', async () => {
	// The mock factory is hoisted before static imports; its store must be loaded here.
	const { writable } = await import('svelte/store');
	const page = writable({ params: { id: 'resource-a' }, url: new URL('http://localhost/dashboard'), data: {} });
	route.set = id => page.set({ params: { id }, url: new URL('http://localhost/dashboard'), data: {} });
	return { page };
});

const container = { uuid: 'resource-a', name: 'CONTAINER_NAME_CANARY', status: 'Running', status_reason: null,
	image: 'image', command: null, cpu: 1, memory: '512', created_at: null, addresses: null };
const share = { id: 'resource-a', name: 'SHARE_NAME_CANARY', status: 'available', size: 10, share_proto: 'NFS',
	export_locations: [], export_location_details: [], metadata: {}, project_id: 'project-a', created_at: null,
	is_public: false, library_name: null, library_version: null, built_at: null, progress: null, user_id: null,
	user_name: null, access_rules_status: null, host: null, availability_zone: null, share_type_name: null, share_network_id: null };
const cases = [
	{ kind: 'container', Page: ContainerPage, base: '/api/v1/containers', route: '/dashboard/containers/instances/:id', key: 'dashboard-container-logs', name: container.name,
		detail: container, secondary: '/logs', value: { logs: 'LOG_BODY_CANARY' }, empty: { logs: '' } },
	{ kind: 'file_storage', Page: FilePage, base: '/api/v1/file-storage', route: '/dashboard/file-storage/:id', key: 'dashboard-file-storage-detail', name: share.name,
		detail: share, secondary: '/access-rules', value: [{ id: 'rule', access_to: 'RULE_TARGET_CANARY', access_level: 'ro', state: 'active', access_key: null }], empty: [] },
] as const;
let flow: CapturedFlowExperience | undefined;
let requests: { url: URL; headers: Headers; method: string }[] = [];
let respond: (url: URL) => Response | Promise<Response>;
function json(value: unknown, status = 200) { return new Response(JSON.stringify(value), { status, headers: { 'Content-Type': 'application/json', 'X-Request-Id': `req-${'a'.repeat(32)}` } }); }
async function settle() { for (let i = 0; i < 5; i += 1) { await nextTurn(); await tick(); } }
function capture(path: string) {
	// Real collector + real API client, only HTTP provider/diagnostic receivers are fixtures.
	flow = captureFlowExperience(path, () => get(auth), async (input, init) => {
		const url = new URL(String(input), 'https://afterglow.test');
		requests.push({ url, headers: new Headers(init?.headers), method: init?.method ?? 'GET' });
		return respond(url);
	});
	return flow;
}
function renew() {
	setAuth(refreshAuthState({ token: 'renewed-token', refresh_token: 'renewed-refresh', user_id: 'user', username: 'user',
		domain_id: 'domain', domain_name: 'Domain', identity_domain_id: 'domain', identity_domain_name: 'Domain',
		project_id: 'project-a', project_name: 'Project', roles: ['member'], is_system_admin: false,
		can_write: true, is_domain_manager: false, can_create_domain: false,
		available_domains: [{ id: 'domain', name: 'Domain' }], auth_method: 'password',
		expires_at: new Date(Date.now() + 3_600_000).toISOString(),
	}, get(auth)));
}
beforeEach(() => {
	vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout', 'setInterval', 'clearInterval', 'Date'] });
	localStorage.clear(); api.clearPrefetchCache(); requests = [];
	auth.set({ sessionId: 'detail-session', token: 'TOKEN_CANARY', refreshToken: 'refresh', accessExpiresAt: null,
		userId: 'user', username: 'user', projectId: 'project-a', projectName: 'Project', availableProjects: [], roles: ['member'],
		isSystemAdmin: false, canWrite: true, canCreateDomain: false, federated: false, domainId: 'domain', domainName: 'Domain',
		identityDomainId: 'domain', identityDomainName: 'Domain', isDomainManager: false });
	expect(acceptAuthVerification(getAuthVerificationEpoch(), {})).toBe(true);
	projectSwitching.set(false); route.set!('resource-a');
	siteConfig.update(c => ({ ...c, runtime: { ...c.runtime, api_base: 'https://afterglow.test' } }));
	vi.spyOn(document, 'hidden', 'get').mockReturnValue(false);
	vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(null);
});
afterEach(() => {
	cleanup(); flow?.collector.destroy(); flow = undefined;
	vi.useRealTimers(); vi.restoreAllMocks(); localStorage.clear();
});

for (const c of cases) describe(`${c.kind} mounted legacy detail ownership`, () => {
	beforeEach(() => {
		localStorage.setItem(`autoRefresh.${c.key}.active`, 'false');
		respond = url => json(url.pathname.endsWith(c.secondary) ? c.value : c.detail);
	});
	it('links the very first physical reads to passive owners and actual ready DOM with polling OFF and no loop', async () => {
		const captured = capture(c.route); render(c.Page); await settle();
		expect(screen.getByRole('heading', { name: c.name })).toBeTruthy();
		expect(requests).toHaveLength(2);
		for (const request of requests) {
			expect(request.method).toBe('GET');
			expect(request.headers.get('X-Afterglow-Experience-Span')).toMatch(/^[a-f0-9-]{36}$/);
			expect(request.headers.has('X-Afterglow-Experience-Action')).toBe(false);
		}
		await vi.advanceTimersByTimeAsync(60_000); await settle();
		expect(requests).toHaveLength(2);
		const events = (await captured.flush()).filter(e => e.feature === c.kind);
		expect(events.some(e => e.payload.state === 'loading')).toBe(true);
		expect(events.some(e => e.payload.state === 'ready')).toBe(true);
		expect(events.filter(e => e.event_type === 'result.committed')).toHaveLength(2);
		expect(events.filter(e => e.event_type === 'result.received' && e.payload.http_status === 200).length).toBeGreaterThanOrEqual(2);
		expect(events.some(e => e.event_type === 'action.started')).toBe(false);
		expect(JSON.stringify(events)).not.toMatch(/TOKEN_CANARY|NAME_CANARY|LOG_BODY_CANARY|RULE_TARGET_CANARY/);
	});
	it('commits an initial real HTTP503 to error DOM, never empty or a diagnostic retry', async () => {
		respond = url => json(url.pathname.endsWith(c.secondary) ? c.empty : { detail: 'PROVIDER_BODY_CANARY' }, url.pathname.endsWith(c.secondary) ? 200 : 503);
		const captured = capture(c.route); render(c.Page); await settle();
		expect(screen.getByRole('alert')).toBeTruthy();
		expect(screen.queryByRole('heading', { name: c.name })).toBeNull();
		const events = (await captured.flush()).filter(e => e.feature === c.kind);
		expect(events.some(e => e.payload.state === 'error')).toBe(true);
		expect(events.some(e => e.event_type === 'result.received' && e.payload.http_status === 503)).toBe(true);
		expect(events.some(e => e.event_type === 'result.committed')).toBe(true);
		await vi.advanceTimersByTimeAsync(60_000); await settle();
		expect(requests.filter(r => !r.url.pathname.endsWith(c.secondary))).toHaveLength(1);
		expect(JSON.stringify(events)).not.toContain('PROVIDER_BODY_CANARY');
	});
	it('distinguishes a valid empty secondary read from its failed read and manual refresh issues exactly one round', async () => {
		respond = url => json(url.pathname.endsWith(c.secondary) ? c.empty : c.detail);
		const captured = capture(c.route); render(c.Page); await settle();
		let events = (await captured.flush()).filter(e => e.feature === c.kind);
		expect(events.some(e => e.payload.state === 'empty')).toBe(true);
		respond = url => json(url.pathname.endsWith(c.secondary) ? { detail: 'PROVIDER_BODY_CANARY' } : c.detail, url.pathname.endsWith(c.secondary) ? 503 : 200);
		await fireEvent.click(screen.getByTitle('지금 새로고침')); await settle();
		expect(requests).toHaveLength(c.kind === 'container' ? 3 : 4);
		expect(requests.at(-1)!.headers.get('X-Afterglow-Experience-Action')).toMatch(/^[a-f0-9-]{36}$/);
		events = (await captured.flush()).filter(e => e.feature === c.kind);
		expect(events.filter(e => e.event_type === 'action.started')).toHaveLength(1);
		expect(events.some(e => e.payload.state === 'error')).toBe(true);
		expect(events.some(e => e.event_type === 'result.committed' && e.action_id)).toBe(true);
		if (c.kind === 'file_storage') { expect(screen.getByRole('alert')).toBeTruthy(); expect(screen.queryByText('접근 규칙이 없습니다')).toBeNull(); }
		expect(JSON.stringify(events)).not.toContain('PROVIDER_BODY_CANARY');
	});
	it('owns polling passively and does not synthesize human refresh actions', async () => {
		localStorage.setItem(`autoRefresh.${c.key}.active`, 'true');
		const captured = capture(c.route); render(c.Page); await settle();
		await vi.advanceTimersByTimeAsync(15_000); await settle();
		expect(requests).toHaveLength(c.kind === 'container' ? 3 : 4);
		const events = (await captured.flush()).filter(e => e.feature === c.kind);
		expect(events.some(e => e.event_type === 'action.started' || e.action_id)).toBe(false);
	});
	it.each(['identity', 'project', 'authority', 'readiness', 'base', 'route'] as const)('rejects pending success after same-tick %s ABA and uses a fresh request', async transition => {
		const pending = Promise.withResolvers<Response>(); let reads = 0;
		respond = url => {
			if (url.pathname.endsWith(c.secondary)) return json(c.value);
			if (++reads === 1) return pending.promise;
			return json({ ...c.detail, name: 'FRESH_RESULT' });
		};
		const captured = capture(c.route); render(c.Page); await settle();
		const original = get(auth);
		if (transition === 'base') {
			siteConfig.update(v => ({ ...v, runtime: { ...v.runtime, api_base: 'https://other.test' } }));
			siteConfig.update(v => ({ ...v, runtime: { ...v.runtime, api_base: 'https://afterglow.test' } }));
		} else if (transition === 'route') { route.set!('resource-b'); route.set!('resource-a'); }
		else if (transition === 'readiness') { authReady.set(false); authReady.set(true); }
		else {
			auth.update(v => ({ ...v, ...(transition === 'identity' ? { userId: 'other' } : transition === 'project' ? { projectId: 'other' } : { canWrite: false }) }));
			auth.set(original); acceptAuthVerification(getAuthVerificationEpoch(), {});
		}
		await settle();
		expect(screen.getByRole('heading', { name: 'FRESH_RESULT' })).toBeTruthy();
		expect(reads).toBe(2);
		pending.resolve(json({ ...c.detail, name: 'STALE_RESULT' })); await settle();
		expect(screen.queryByRole('heading', { name: 'STALE_RESULT' })).toBeNull();
		const events = (await captured.flush()).filter(e => e.feature === c.kind);
		expect(events.some(e => e.event_type === 'result.discarded')).toBe(true);
	});
	it.each([200, 503])('does not apply or commit a request completed after unmount (HTTP%s)', async status => {
		const pending = Promise.withResolvers<Response>();
		respond = url => url.pathname.endsWith(c.secondary) ? json(c.value) : pending.promise;
		const captured = capture(c.route); const view = render(c.Page); await settle();
		view.unmount(); pending.resolve(json(status === 200 ? c.detail : { detail: 'LATE_ERROR_CANARY' }, status)); await settle();
		const events = (await captured.flush()).filter(e => e.feature === c.kind);
		expect(events.some(e => e.event_type === 'result.committed')).toBe(false);
		expect(events.some(e => e.event_type === 'result.discarded' && e.payload.reason === 'unmounted')).toBe(true);
	});
	it('preserves settled DOM and pending independent reads during mapped renewal, then uses the new token manually', async () => {
		const pending = Promise.withResolvers<Response>();
		respond = url => url.pathname.endsWith(c.secondary) ? pending.promise : json(c.detail);
		capture(c.route); render(c.Page); await settle();
		expect(screen.getByRole('heading', { name: c.name })).toBeTruthy();
		renew(); await settle(); expect(get(authReady)).toBe(true);
		expect(requests).toHaveLength(2);
		pending.resolve(json(c.value)); await settle();
		expect(screen.getByRole('heading', { name: c.name })).toBeTruthy();
		await fireEvent.click(screen.getByTitle('지금 새로고침')); await settle();
		expect(requests.at(-1)!.headers.get('Authorization')).toBe('Bearer renewed-token');
	});
	it('keeps a pending primary read across mapped same-owner renewal without another GET', async () => {
		const pending = Promise.withResolvers<Response>();
		respond = url => url.pathname.endsWith(c.secondary) ? json(c.value) : pending.promise;
		const captured = capture(c.route); render(c.Page); await settle();
		const before = requests.length;
		renew(); await settle(); expect(requests).toHaveLength(before);
		pending.resolve(json(c.detail)); await settle();
		expect(screen.getByRole('heading', { name: c.name })).toBeTruthy();
		expect(requests.filter(r => !r.url.pathname.endsWith(c.secondary))).toHaveLength(1);
		const events = (await captured.flush()).filter(e => e.feature === c.kind);
		expect(events.some(e => e.event_type === 'result.committed')).toBe(true);
	});
	it('renders a valid absent primary response as empty rather than error or a blank result', async () => {
		respond = url => json(url.pathname.endsWith(c.secondary) ? c.empty : null);
		const captured = capture(c.route); render(c.Page); await settle();
		expect(screen.queryByRole('alert')).toBeNull();
		expect(screen.getByRole('status').textContent).toContain(c.kind === 'container' ? '컨테이너가 없습니다' : '파일 스토리지가 없습니다');
		const events = (await captured.flush()).filter(e => e.feature === c.kind);
		expect(events.some(e => e.payload.state === 'empty')).toBe(true);
		expect(events.some(e => e.event_type === 'result.committed')).toBe(true);
	});
	it('does not publish an obsolete read error after resource replacement', async () => {
		const pending = Promise.withResolvers<Response>(); let first = true;
		respond = url => {
			if (url.pathname.endsWith(c.secondary)) return json(c.value);
			if (first) { first = false; return pending.promise; }
			return json({ ...c.detail, id: 'resource-b', uuid: 'resource-b', name: 'CURRENT_RESULT' });
		};
		const captured = capture(c.route); render(c.Page); await settle();
		route.set!('resource-b'); await settle();
		pending.resolve(json({ detail: 'OBSOLETE_ERROR_CANARY' }, 503)); await settle();
		expect(screen.getByRole('heading', { name: 'CURRENT_RESULT' })).toBeTruthy();
		expect(screen.queryByRole('alert')).toBeNull();
		const events = (await captured.flush()).filter(e => e.feature === c.kind);
		expect(events.some(e => e.event_type === 'result.discarded')).toBe(true);
		expect(JSON.stringify(events)).not.toContain('OBSOLETE_ERROR_CANARY');
	});
	it('rechecks the actual DOM owner after assignment before emitting a commit', async () => {
		const newer = Promise.withResolvers<Response>();
		respond = url => url.pathname.includes('resource-b') ? newer.promise : json(url.pathname.endsWith(c.secondary) ? c.value : c.detail);
		const captured = capture(c.route);
		const applied = experience.experienceApplied;
		let switched = false;
		vi.spyOn(experience, 'experienceApplied').mockImplementation((...args) => {
			const completion = applied(...args);
			if (!switched) { switched = true; route.set!('resource-b'); }
			return completion;
		});
		const view = render(c.Page); await settle();
		const events = (await captured.flush()).filter(e => e.feature === c.kind);
		expect(events.some(e => e.event_type === 'result.applied')).toBe(true);
		expect(events.some(e => e.event_type === 'result.discarded' && e.payload.stage === 'dom')).toBe(true);
		expect(events.some(e => e.event_type === 'result.committed')).toBe(false);
		view.unmount(); newer.resolve(json(null)); await settle();
	});
});

it('preserves the file access-rule draft across mapped renewal and clears it on resource replacement', async () => {
	localStorage.setItem('autoRefresh.dashboard-file-storage-detail.active', 'false');
	respond = url => json(url.pathname.endsWith('/access-rules') ? [] : { ...share, id: url.pathname.split('/').at(-1) });
	capture('/dashboard/file-storage/:id'); render(FilePage); await settle();
	await fireEvent.click(screen.getByRole('button', { name: '+ 추가' }));
	const field = screen.getByPlaceholderText('예: 10.0.0.0/24');
	await fireEvent.input(field, { target: { value: 'DRAFT_CANARY' } });
	renew(); await settle(); expect((field as HTMLInputElement).value).toBe('DRAFT_CANARY'); expect(requests).toHaveLength(2);
	route.set!('resource-b'); await settle(); expect(screen.queryByDisplayValue('DRAFT_CANARY')).toBeNull();
});

it.each([200, 503])('starts the container polling deadline only after a slow initial logs read settles (HTTP%s)', async status => {
	localStorage.setItem('autoRefresh.dashboard-container-logs.active', 'true');
	const initialLogs = Promise.withResolvers<Response>();
	let logReads = 0;
	respond = url => {
		if (!url.pathname.endsWith('/logs')) return json(container);
		return ++logReads === 1 ? initialLogs.promise : json({ logs: 'FRESH_LOG_CANARY' });
	};
	const captured = capture('/dashboard/containers/instances/:id');
	render(ContainerPage); await settle();
	expect(screen.getByRole('heading', { name: container.name })).toBeTruthy();
	expect((screen.getByTitle('로딩 중…') as HTMLButtonElement).disabled).toBe(true);
	expect(requests).toHaveLength(2);
	await vi.advanceTimersByTimeAsync(16_000); await settle();
	expect(logReads).toBe(1);
	expect(requests).toHaveLength(2);
	initialLogs.resolve(json(status === 200 ? { logs: 'INITIAL_LOG_CANARY' } : { detail: 'PRIVATE_LOG_ERROR_CANARY' }, status));
	await settle();
	expect((screen.getByTitle('지금 새로고침') as HTMLButtonElement).disabled).toBe(false);
	await vi.advanceTimersByTimeAsync(14_999); await settle();
	expect(logReads).toBe(1);
	await vi.advanceTimersByTimeAsync(1); await settle();
	expect(logReads).toBe(2);
	expect(requests).toHaveLength(3);
	const events = (await captured.flush()).filter(e => e.feature === 'container');
	expect(events.some(e => e.event_type === 'action.started' || e.action_id)).toBe(false);
	expect(JSON.stringify(events)).not.toMatch(/INITIAL_LOG_CANARY|FRESH_LOG_CANARY|PRIVATE_LOG_ERROR_CANARY/);
});

it.each([200, 503])('does not carry a second joined file refresh action into the next passive poll (rules HTTP%s)', async status => {
	localStorage.setItem('autoRefresh.dashboard-file-storage-detail.active', 'true');
	const delayedRules = Promise.withResolvers<Response>();
	let rulesReads = 0;
	respond = url => {
		if (!url.pathname.endsWith('/access-rules')) return json(share);
		return ++rulesReads === 2 ? delayedRules.promise : json([]);
	};
	const captured = capture('/dashboard/file-storage/:id');
	render(FilePage); await settle();
	await captured.flush();
	await fireEvent.click(screen.getByTitle('지금 새로고침')); await settle();
	expect(requests).toHaveLength(4);
	// Detail settled, but this same forced cycle still owns the pending rules request.
	expect((screen.getByTitle('지금 새로고침') as HTMLButtonElement).disabled).toBe(false);
	await fireEvent.click(screen.getByTitle('지금 새로고침')); await settle();
	expect(requests).toHaveLength(4);
	delayedRules.resolve(json(status === 200 ? [] : { detail: 'DELAYED_RULE_ERROR_CANARY' }, status));
	await settle(); await captured.flush();
	const beforePoll = captured.events.length;
	await vi.advanceTimersByTimeAsync(15_000); await settle();
	expect(requests).toHaveLength(6);
	for (const request of requests.slice(-2)) expect(request.headers.has('X-Afterglow-Experience-Action')).toBe(false);
	const pollEvents = (await captured.flush()).slice(beforePoll).filter(e => e.feature === 'file_storage');
	expect(pollEvents.some(e => e.event_type === 'result.committed')).toBe(true);
	expect(pollEvents.some(e => e.event_type === 'action.started' || e.action_id)).toBe(false);
	expect(JSON.stringify(pollEvents)).not.toContain('DELAYED_RULE_ERROR_CANARY');
});
