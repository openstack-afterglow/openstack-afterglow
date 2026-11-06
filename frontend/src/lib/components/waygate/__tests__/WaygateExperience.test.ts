import { setImmediate as nextTurn } from 'node:timers/promises';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/svelte';
import { tick } from 'svelte';
import { get, writable } from 'svelte/store';
import type { ExperienceContext } from '$lib/utils/experience';
import { captureFlowExperience } from '$lib/stores/__tests__/experienceFlowHarness';

const transport = vi.hoisted(() => ({ get: vi.fn() }));
const requests = vi.hoisted(() => [] as { context?: ExperienceContext }[]);
vi.mock('$lib/api/client', () => ({
	ApiError: class ApiError extends Error {
		constructor(public status: number, message: string) { super(message); }
	},
	api: {
		get: transport.get,
		withExperience(context?: ExperienceContext) {
			return { get: (path: string, token?: string, projectId?: string) => {
				requests.push({ context });
				return transport.get(path, token, projectId);
			} };
		},
	},
}));
vi.mock('$lib/stores/auth', () => ({
	auth: writable({ token: 'TOKEN_CANARY', userId: 'user-a', projectId: 'project-a', domainId: 'domain-a' }),
	authReady: writable(true), projectSwitching: writable(false),
}));
vi.mock('$lib/stores/servicePermissions', () => ({
	serviceCapabilities: writable((leaf: string) => leaf === 'waygate-inventory_reader'),
	observedProjectPermissions: writable({ permissions: null, loading: false, error: '' }),
}));
vi.mock('$lib/config/site', () => ({ siteConfig: writable({ services: { waygate: true } }) }));
vi.mock('$lib/stores/toast', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
import { auth } from '$lib/stores/auth';
import { ApiError } from '$lib/api/client';
import { t } from '$lib/i18n/ns/waygate';
import { t as commonT } from '$lib/i18n/ns/common';
import WaygateWorkspace from '../WaygateWorkspace.svelte';

const server = {
	id: 'SERVER_ID_CANARY', project_id: 'project-a', name: 'GATEWAY_NAME_CANARY', status: 'ACTIVE',
	tunnel_cidr: '10.240.0.0/24', listen_port: 51820, created_at: '2026-09-20T00:00:00Z',
	dns: null, persistent_keepalive: 25,
};
const base = '/api/v1/waygate/servers';
const collectors: (() => void)[] = [];
const originalAnimate = Object.getOwnPropertyDescriptor(Element.prototype, 'animate');
function capture() {
	const flow = captureFlowExperience('/dashboard/network/waygate', () => get(auth));
	collectors.push(flow.collector.destroy);
	return flow;
}
async function settle() { await nextTurn(); await tick(); }
beforeEach(() => {
	vi.resetAllMocks(); requests.length = 0;
	vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout', 'setInterval', 'clearInterval', 'Date'] });
	localStorage.clear();
	auth.update(owner => ({ ...owner, token: 'TOKEN_CANARY', userId: 'user-a', projectId: 'project-a', domainId: 'domain-a' }));
	vi.spyOn(document, 'hidden', 'get').mockReturnValue(false);
	Element.prototype.animate = vi.fn().mockReturnValue({ finished: Promise.resolve(), cancel: vi.fn(), play: vi.fn() });
	vi.stubGlobal('matchMedia', vi.fn((query: string) => ({ matches: false, media: query, onchange: null, addListener: vi.fn(), removeListener: vi.fn(), addEventListener: vi.fn(), removeEventListener: vi.fn(), dispatchEvent: vi.fn() })));
	transport.get.mockImplementation((path: string) => {
		if (path === base) return Promise.resolve([server]);
		throw new Error('Unexpected native transport request');
	});
});
afterEach(() => {
	cleanup();
	for (const destroy of collectors.splice(0)) destroy();
	vi.useRealTimers(); vi.restoreAllMocks(); vi.unstubAllGlobals(); localStorage.clear();
	if (originalAnimate) Object.defineProperty(Element.prototype, 'animate', originalAnimate);
	else Reflect.deleteProperty(Element.prototype, 'animate');
});

describe('Waygate list actual collector observations', () => {
	it('serializes passive mount and polling assignments as ready then empty without inventing human actions', async () => {
		const flow = capture();
		render(WaygateWorkspace); await settle();
		expect(screen.getAllByText(server.name).length).toBeGreaterThan(0);
		let events = (await flow.flush()).filter(event => event.feature === 'waygate');
		expect(events.some(event => event.payload.state === 'ready')).toBe(true);
		expect(events.some(event => event.event_type === 'result.committed')).toBe(true);
		transport.get.mockResolvedValueOnce([]);
		await vi.advanceTimersByTimeAsync(15_000); await settle();
		expect(transport.get).toHaveBeenCalledTimes(2);
		expect(screen.getByText(t('project.empty.servers'))).toBeTruthy();
		events = (await flow.flush()).filter(event => event.feature === 'waygate');
		expect(events.some(event => event.payload.state === 'empty')).toBe(true);
		expect(events.filter(event => event.event_type === 'result.committed')).toHaveLength(2);
		expect(events.some(event => event.event_type === 'action.started' || event.action_id)).toBe(false);
		expect(JSON.stringify(events)).not.toMatch(/TOKEN_CANARY|SERVER_ID_CANARY|GATEWAY_NAME_CANARY/);
	});

	it('does not describe an initial failed inventory read as an empty inventory', async () => {
		transport.get.mockRejectedValueOnce(new ApiError(503, 'PROVIDER_BODY_CANARY'));
		const flow = capture();
		render(WaygateWorkspace); await settle();
		expect(screen.getByRole('alert').textContent).toContain(t('project.error.fetchStatus', { status: 503 }));
		expect(screen.queryByText(t('project.empty.servers'))).toBeNull();
		const events = (await flow.flush()).filter(event => event.feature === 'waygate');
		expect(events.some(event => event.payload.state === 'error')).toBe(true);
		expect(events.some(event => event.payload.state === 'empty')).toBe(false);
		expect(events.some(event => event.event_type === 'result.committed')).toBe(true);
		expect(JSON.stringify(events)).not.toContain('PROVIDER_BODY_CANARY');
	});

	it('preserves the visible gateway through refresh503 and serializes the real action error and DOM application without private provider text', async () => {
		const flow = capture();
		render(WaygateWorkspace); await settle();
		transport.get.mockRejectedValueOnce(new ApiError(503, 'PROVIDER_BODY_CANARY'));
		await fireEvent.click(screen.getByRole('button', { name: commonT('autoRefresh.refreshNow') })); await settle();
		expect(screen.getAllByText(server.name).length).toBeGreaterThan(0);
		expect(screen.getByText(t('project.error.fetchStatus', { status: 503 }))).toBeTruthy();
		const context = requests.at(-1)!.context!;
		expect(context.action).toBe('refresh'); expect(context.actionId).toBeTruthy();
		const events = (await flow.flush()).filter(event => event.action_id === context.actionId);
		expect(events.some(event => event.event_type === 'action.started')).toBe(true);
		expect(events.some(event => event.payload.state === 'loading')).toBe(true);
		expect(events.some(event => event.payload.state === 'error')).toBe(true);
		expect(events.some(event => event.payload.state === 'empty')).toBe(false);
		expect(events.some(event => event.event_type === 'result.applied')).toBe(true);
		expect(events.some(event => event.event_type === 'result.committed')).toBe(true);
		expect(JSON.stringify(await flow.flush())).not.toMatch(/PROVIDER_BODY_CANARY|TOKEN_CANARY|SERVER_ID_CANARY|GATEWAY_NAME_CANARY/);
	});

	it('does not serialize a state or DOM application from an unresolved list after its component unmounts', async () => {
		const pending = Promise.withResolvers<unknown[]>();
		transport.get.mockReturnValueOnce(pending.promise);
		const flow = capture();
		const view = render(WaygateWorkspace); await settle();
		view.unmount(); pending.resolve([server]); await settle();
		const events = (await flow.flush()).filter(event => event.feature === 'waygate');
		expect(screen.queryByText(server.name)).toBeNull();
		expect(events.some(event => event.event_type === 'result.applied' || event.event_type === 'result.committed')).toBe(false);
		expect(events.some(event => event.payload.state === 'ready')).toBe(false);
		expect(events.some(event => event.event_type === 'result.discarded')).toBe(true);
	});

	it('keeps a late old-project reply out of the replacement workspace and its serialized applied results', async () => {
		const pending = Promise.withResolvers<unknown[]>();
		transport.get.mockReturnValueOnce(pending.promise);
		const flow = capture();
		render(WaygateWorkspace); await settle();
		const oldContext = requests[0].context!;
		await flow.flush();
		transport.get.mockResolvedValueOnce([]);
		auth.update(owner => ({ ...owner, token: 'NEW_TOKEN_CANARY', projectId: 'project-b' }));
		flow.collector.syncOwner(); await settle();
		pending.resolve([server]); await settle();
		expect(screen.queryByText(server.name)).toBeNull();
		expect(screen.getByText(t('project.empty.servers'))).toBeTruthy();
		const events = await flow.flush();
		expect(events.some(event => event.feature === 'waygate' && event.payload.state === 'empty')).toBe(true);
		expect(events.some(event => 'span_id' in event && event.span_id === oldContext.spanId && ['result.applied', 'result.committed'].includes(event.event_type))).toBe(false);
		expect(JSON.stringify(events)).not.toMatch(/TOKEN_CANARY|SERVER_ID_CANARY|GATEWAY_NAME_CANARY/);
	});
});
