import { setImmediate as nextTurn } from 'node:timers/promises';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, within } from '@testing-library/svelte';
import { tick } from 'svelte';
import { writable } from 'svelte/store';

const mocks = vi.hoisted(() => ({
	get: vi.fn(), toastSuccess: vi.fn(), toastError: vi.fn(),
	refresh: [] as (() => unknown)[],
}));
vi.mock('$lib/api/client', () => ({
	api: { get: mocks.get, post: vi.fn(), patch: vi.fn(), delete: vi.fn(), downloadBlob: vi.fn() },
	ApiError: class ApiError extends Error {
		constructor(public status: number, message: string) { super(message); }
	},
}));
vi.mock('$lib/stores/auth', () => ({
	auth: writable({ token: 'token-a', projectId: 'project-a', userId: 'user-a', isSystemAdmin: false, roles: ['member'] }),
	authReady: writable(true), projectSwitching: writable(false),
}));
vi.mock('$lib/stores/servicePermissions', () => ({
	serviceCapabilities: writable<(leaf: string) => boolean>((leaf) => leaf === 'waygate-inventory_reader'),
	observedProjectPermissions: writable({ permissions: null, loading: false, error: '' }),
}));
vi.mock('$lib/config/site', () => ({ siteConfig: writable({ services: { waygate: true } }) }));
vi.mock('$lib/stores/toast', () => ({ toast: { success: mocks.toastSuccess, error: mocks.toastError } }));
// Capture the list, panel and peer refresh callbacks in creation order.
vi.mock('$lib/utils/autoRefresh.svelte', () => ({
	createAutoRefresh: (refresh: () => unknown) => {
		mocks.refresh.push(refresh);
		return { active: false, intervalSeconds: 15, intervalOptions: [15], refresh };
	},
}));

import { auth } from '$lib/stores/auth';
import { ApiError } from '$lib/api/client';
import { t } from '$lib/i18n/ns/waygate';
import type { WaygateDiagnosticsHint, WaygateServerDiagnostics } from '$lib/types/waygate';
import WaygateWorkspace from '../WaygateWorkspace.svelte';

const base = '/api/v1/waygate/servers';
const diagnosticsPath = (project: string) => `${base}/server-${project}/diagnostics`;
const consolePath = '/api/v1/instances/vm-a/log?length=200';
const server = (project: string, vm: string | null = `vm-${project}`) => ({
	id: `server-${project}`, project_id: `project-${project}`, name: `gateway-${project}`,
	status: 'ACTIVE', status_reason: null, server_vm_id: vm, endpoint_ip: '203.0.113.10',
	tunnel_cidr: '10.240.0.0/24', listen_port: 51820, dns: null, persistent_keepalive: 25,
	created_at: '2026-11-08T00:00:00Z', last_status_reported_at: null, peer_count: null,
});
const diagnostics = (overrides: Partial<WaygateServerDiagnostics> = {}): WaygateServerDiagnostics => ({
	verdict: 'ok',
	checked_at: '2026-11-08T00:10:00Z',
	agent: { install_mode: 'prebuilt', image_id: 'image-0.1.4', source: 'glance', report_interval_seconds: 1 },
	last_register_at: '2026-11-08T00:00:00Z',
	last_desired_state_at: '2026-11-08T00:09:50Z',
	last_status_at: '2026-11-08T00:09:59Z',
	last_status: { peers: 2, reported_at: '2026-11-08T00:09:59Z' },
	expected: { enabled_clients: 2, attachments: 0 },
	hints: [],
	...overrides,
});

type Handler = (path: string, projectId: string) => unknown;
let diagnosticsHandler: Handler;
let consoleHandler: Handler;
let serverVm: string | null;

async function settle() {
	await nextTurn();
	await tick();
}
function calls(path: string) {
	return mocks.get.mock.calls.filter(([requested]) => requested === path).length;
}
function panel() {
	return within(screen.getByRole('dialog', { name: t('project.server.details') }));
}
function section() {
	return within(panel().getByRole('region', { name: t('project.diagnostics.heading') }));
}
async function openDetail(project = 'a') {
	await fireEvent.click(await screen.findByText(`gateway-${project}`));
	await settle();
}
function panelTick() {
	return mocks.refresh[1]();
}
function relative(at: string, checkedAt: string) {
	const seconds = Math.round((Date.parse(checkedAt) - Date.parse(at)) / 1000);
	const format = new Intl.RelativeTimeFormat('ko', { numeric: 'auto' });
	return seconds < 60 ? format.format(-seconds, 'second') : format.format(-Math.floor(seconds / 60), 'minute');
}

const originalAnimate = Object.getOwnPropertyDescriptor(Element.prototype, 'animate');
beforeEach(() => {
	vi.resetAllMocks();
	mocks.refresh.length = 0;
	auth.update((value) => ({ ...value, token: 'token-a', projectId: 'project-a' }));
	Element.prototype.animate = vi.fn().mockReturnValue({ finished: Promise.resolve(), cancel: vi.fn(), play: vi.fn() });
	vi.stubGlobal('matchMedia', vi.fn((query: string) => ({
		matches: false, media: query, onchange: null,
		addListener: vi.fn(), removeListener: vi.fn(), addEventListener: vi.fn(),
		removeEventListener: vi.fn(), dispatchEvent: vi.fn(),
	})));
	serverVm = 'vm-a';
	diagnosticsHandler = () => Promise.resolve(diagnostics());
	consoleHandler = () => Promise.resolve({ output: 'cloud-init finished\nWaygate agent: desired-state sync + status report\n' });
	mocks.get.mockImplementation((path: string, _token: string, projectId: string) => {
		const project = projectId === 'project-b' ? 'b' : 'a';
		if (path === base) return Promise.resolve([server(project, project === 'a' ? serverVm : 'vm-b')]);
		if (path === `${base}/server-${project}`) return Promise.resolve(server(project, project === 'a' ? serverVm : 'vm-b'));
		if (path.endsWith('/diagnostics')) return diagnosticsHandler(path, projectId);
		if (path.startsWith('/api/v1/instances/')) return consoleHandler(path, projectId);
		if (path.endsWith('/clients') || path.endsWith('/networks')) return Promise.resolve([]);
		throw new Error(`Unexpected GET ${path}`);
	});
});
afterEach(() => {
	cleanup();
	vi.unstubAllGlobals();
	if (originalAnimate) Object.defineProperty(Element.prototype, 'animate', originalAnimate);
	else Reflect.deleteProperty(Element.prototype, 'animate');
});

describe('Waygate agent connection diagnostics', () => {
	it('loads diagnostics on panel open and on each panel auto-refresh tick, never on peer ticks', async () => {
		render(WaygateWorkspace);
		await openDetail();
		expect(mocks.get).toHaveBeenCalledWith(diagnosticsPath('a'), 'token-a', 'project-a', { refresh: true });
		expect(calls(diagnosticsPath('a'))).toBe(1);
		await mocks.refresh[2]();
		await settle();
		expect(calls(diagnosticsPath('a'))).toBe(1);
		await panelTick();
		await settle();
		expect(calls(diagnosticsPath('a'))).toBe(2);
	});

	it.each([
		['ok', [] as WaygateDiagnosticsHint[]],
		['never_connected', ['agent_never_reported']],
		['not_polling', ['agent_not_polling', 'image_agent_outdated']],
		['not_reporting', ['agent_status_stale']],
		['peer_mismatch', ['peers_mismatch']],
	] as const)('renders the %s verdict, times, peers and localized hints', async (verdict, hints) => {
		const value = diagnostics({
			verdict,
			hints: [...hints],
			last_register_at: verdict === 'never_connected' ? null : '2026-11-08T00:00:00Z',
			last_status: verdict === 'peer_mismatch' ? { peers: 0, reported_at: '2026-11-08T00:09:59Z' } : diagnostics().last_status,
		});
		diagnosticsHandler = () => Promise.resolve(value);
		render(WaygateWorkspace);
		await openDetail();
		expect(section().getByTestId('waygate-diagnostics-verdict').textContent).toBe(t(`project.diagnostics.verdict.${verdict}`));
		for (const hint of hints) expect(section().getByText(t(`project.diagnostics.hint.${hint}`))).toBeTruthy();
		expect(section().queryAllByRole('listitem')).toHaveLength(hints.length);
		if (verdict === 'never_connected') expect(section().getByText(t('project.diagnostics.never'))).toBeTruthy();
		else expect(section().getByText(relative('2026-11-08T00:00:00Z', value.checked_at))).toBeTruthy();
		expect(section().getByText(relative('2026-11-08T00:09:50Z', value.checked_at))).toBeTruthy();
		expect(section().getByText(t('project.diagnostics.peersValue', { reported: verdict === 'peer_mismatch' ? '0' : '2', expected: 2 }))).toBeTruthy();
		expect(mocks.toastError).not.toHaveBeenCalled();
	});

	it('renders unknown verdicts and hint codes neutrally plus agent self-diagnostics', async () => {
		diagnosticsHandler = () => Promise.resolve(diagnostics({
			verdict: 'future_state', hints: ['future_hint', 'future_hint'],
			last_status: { peers: 1, reported_at: '2026-11-08T00:09:59Z', diagnostics: { reconcile_ok: false, wg_interface_up: true, error: 'wg_sync_failed' } },
		}));
		render(WaygateWorkspace);
		await openDetail();
		expect(section().getByTestId('waygate-diagnostics-verdict').textContent).toBe(t('project.diagnostics.verdict.unknown', { verdict: 'future_state' }));
		expect(section().getAllByText(t('project.diagnostics.hint.unknown', { code: 'future_hint' }))).toHaveLength(1);
		expect(section().getByText(t('project.diagnostics.selfCheck.reconcile', { state: 'failed' }))).toBeTruthy();
		expect(section().getByText(t('project.diagnostics.selfCheck.interface', { state: 'up' }))).toBeTruthy();
		expect(section().getByText(t('project.diagnostics.selfCheck.error', { error: 'wg_sync_failed' }))).toBeTruthy();
	});

	it('shows reported peers as unknown when the agent reports its WireGuard interface down', async () => {
		diagnosticsHandler = () => Promise.resolve(diagnostics({
			verdict: 'peer_mismatch', hints: ['peers_mismatch'],
			last_status: { peers: 0, reported_at: '2026-11-08T00:09:59Z', diagnostics: { wg_interface_up: false, error: 'wg_show_failed' } },
		}));
		render(WaygateWorkspace);
		await openDetail();
		expect(section().getByText(t('project.diagnostics.peersValue', { reported: '-', expected: 2 }))).toBeTruthy();
		expect(section().getByText(t('project.diagnostics.selfCheck.interface', { state: 'down' }))).toBeTruthy();
		expect(section().getByText(t('project.diagnostics.selfCheck.reconcile', { state: 'unknown' }))).toBeTruthy();
	});

	it.each([404, 405])('degrades to a neutral note on %s from an older Waygate and stops asking', async (status) => {
		diagnosticsHandler = () => Promise.reject(new ApiError(status, 'Not Found'));
		render(WaygateWorkspace);
		await openDetail();
		expect(section().getByText(t('project.diagnostics.unsupported'))).toBeTruthy();
		expect(panel().queryByRole('alert')).toBeNull();
		await panelTick();
		await panelTick();
		await settle();
		expect(calls(diagnosticsPath('a'))).toBe(1);
		expect(mocks.toastError).not.toHaveBeenCalled();
		// The console log stays available for diagnosing an older gateway.
		expect(section().getByRole('button', { name: t('project.diagnostics.console.open') })).toBeTruthy();
	});

	it('keeps the last verdict on a transient failure without toasts and recovers on the next tick', async () => {
		let reads = 0;
		diagnosticsHandler = () => {
			reads += 1;
			if (reads === 1) return Promise.reject(new ApiError(503, 'waygate unavailable'));
			if (reads === 3) return Promise.reject(new ApiError(502, 'bad gateway'));
			return Promise.resolve(diagnostics({ verdict: 'not_polling', hints: ['agent_not_polling'] }));
		};
		render(WaygateWorkspace);
		await openDetail();
		expect(section().getByText(t('project.diagnostics.error', { error: 'waygate unavailable' }))).toBeTruthy();
		await panelTick();
		await settle();
		expect(section().getByTestId('waygate-diagnostics-verdict').textContent).toBe(t('project.diagnostics.verdict.not_polling'));
		await panelTick();
		await settle();
		expect(section().getByTestId('waygate-diagnostics-verdict').textContent).toBe(t('project.diagnostics.verdict.not_polling'));
		expect(section().getByText(t('project.diagnostics.staleError', { error: 'bad gateway' }))).toBeTruthy();
		await panelTick();
		await settle();
		expect(section().queryByText(t('project.diagnostics.staleError', { error: 'bad gateway' }))).toBeNull();
		expect(mocks.toastError).not.toHaveBeenCalled();
	});

	it('drops a pending diagnostics response after a project switch', async () => {
		const old = Promise.withResolvers<WaygateServerDiagnostics>();
		diagnosticsHandler = (_path, projectId) => projectId === 'project-a'
			? old.promise
			: Promise.resolve(diagnostics({ verdict: 'ok' }));
		render(WaygateWorkspace);
		await openDetail('a');
		auth.update((value) => ({ ...value, projectId: 'project-b' }));
		await openDetail('b');
		expect(section().getByTestId('waygate-diagnostics-verdict').textContent).toBe(t('project.diagnostics.verdict.ok'));
		old.resolve(diagnostics({ verdict: 'not_polling', hints: ['image_agent_outdated'] }));
		await settle();
		expect(section().getByTestId('waygate-diagnostics-verdict').textContent).toBe(t('project.diagnostics.verdict.ok'));
		expect(screen.queryByText(t('project.diagnostics.hint.image_agent_outdated'))).toBeNull();
		expect(mocks.get).toHaveBeenCalledWith(diagnosticsPath('b'), 'token-a', 'project-b', { refresh: true });
	});

	it('loads, refreshes and hides the gateway VM console log through the instance endpoint', async () => {
		render(WaygateWorkspace);
		await openDetail();
		expect(calls(consolePath)).toBe(0);
		await fireEvent.click(section().getByRole('button', { name: t('project.diagnostics.console.open') }));
		await settle();
		expect(mocks.get).toHaveBeenCalledWith(consolePath, 'token-a', 'project-a', { refresh: true });
		const log = section().getByLabelText(t('project.diagnostics.console.label'));
		expect(log.textContent).toContain('desired-state sync + status report');
		consoleHandler = () => Promise.resolve({ output: 'second read' });
		await fireEvent.click(section().getByRole('button', { name: t('project.diagnostics.console.refresh') }));
		await settle();
		expect(calls(consolePath)).toBe(2);
		expect(section().getByLabelText(t('project.diagnostics.console.label')).textContent).toBe('second read');
		// Console reads are manual only; panel ticks never re-read it.
		await panelTick();
		await settle();
		expect(calls(consolePath)).toBe(2);
		await fireEvent.click(section().getByRole('button', { name: t('project.diagnostics.console.hide') }));
		expect(section().queryByLabelText(t('project.diagnostics.console.label'))).toBeNull();
	});

	it.each([
		[500, 'Nova failed', () => t('project.diagnostics.console.error', { error: 'Nova failed' })],
		[409, 'console_log_unavailable', () => t('project.diagnostics.console.unavailable')],
	] as const)('shows a console log error state for %s', async (status, message, expected) => {
		consoleHandler = () => Promise.reject(new ApiError(status, message));
		render(WaygateWorkspace);
		await openDetail();
		await fireEvent.click(section().getByRole('button', { name: t('project.diagnostics.console.open') }));
		await settle();
		expect(section().getByRole('alert').textContent).toContain(expected());
		expect(section().queryByLabelText(t('project.diagnostics.console.label'))).toBeNull();
		consoleHandler = () => Promise.resolve({ output: '' });
		await fireEvent.click(section().getByRole('button', { name: t('project.diagnostics.console.refresh') }));
		await settle();
		expect(section().queryByRole('alert')).toBeNull();
		expect(section().getByLabelText(t('project.diagnostics.console.label')).textContent).toBe(t('project.diagnostics.console.empty'));
		expect(mocks.toastError).not.toHaveBeenCalled();
	});

	it('explains that the console log needs an assigned gateway VM', async () => {
		serverVm = null;
		render(WaygateWorkspace);
		await openDetail();
		expect(section().getByText(t('project.diagnostics.console.noVm'))).toBeTruthy();
		expect(section().queryByRole('button', { name: t('project.diagnostics.console.open') })).toBeNull();
	});
});
