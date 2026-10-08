import { setImmediate as nextTurn } from 'node:timers/promises';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, within } from '@testing-library/svelte';
import { tick } from 'svelte';
import { writable } from 'svelte/store';

const mocks = vi.hoisted(() => ({ get: vi.fn(), patch: vi.fn(), toastError: vi.fn() }));
vi.mock('$lib/api/client', () => ({
	api: { get: mocks.get, patch: mocks.patch },
	ApiError: class ApiError extends Error {
		constructor(public status: number, message: string) { super(message); }
	},
}));
vi.mock('$lib/stores/auth', () => ({ auth: writable({ token: 'token-a', projectId: 'project-a' }) }));
vi.mock('$lib/stores/servicePermissions', () => ({ serviceCapabilities: writable<(leaf: string) => boolean>((leaf) => [
	'waygate-inventory_reader', 'waygate-connect_user', 'waygate-clients_editor',
	'waygate-clients_admin', 'waygate-gateways_editor', 'waygate-gateways_admin', 'waygate-routing_admin',
].includes(leaf)) }));
vi.mock('$lib/config/site', () => ({ siteConfig: writable({ services: { waygate: true } }) }));
vi.mock('$lib/stores/toast', () => ({ toast: { success: vi.fn(), error: mocks.toastError } }));
// Exercise the real autoRefresh controller, preferences and visibility listeners.
import { auth } from '$lib/stores/auth';
import { ApiError } from '$lib/api/client';
import WaygateWorkspace from '../WaygateWorkspace.svelte';

const base = '/api/v1/waygate/servers';
const clientsPath = `${base}/server-a/clients`;
const detailPath = `${base}/server-a`;
const attachmentsPath = `${base}/server-a/networks`;
const catalogPath = '/api/v1/networks';
const server = (id: string) => ({
	id: `server-${id}`, project_id: 'project-a', name: `gateway-${id}`, status: 'ACTIVE',
	tunnel_cidr: '10.240.0.0/24', listen_port: 51820, created_at: '2026-09-20T00:00:00Z',
	dns: null, persistent_keepalive: 25,
});
const client = (name: string) => ({
	id: name, name, enabled: true, online: false, tunnel_ip: '10.240.0.2',
	rx_bytes: 100, tx_bytes: 200, last_reported_at: '2026-09-20T00:00:00Z',
	last_handshake_at: null, created_at: '2026-09-20T00:00:00Z',
	dns: null, mtu: null,
	persistent_keepalive: 0, psk_enabled: false,
});
const attachment = (networkId: string) => ({
	id: 1, network_id: networkId, status: 'ACTIVE', nat_mode: 'snat',
});
function deferred<T>() {
	let resolve!: (value: T) => void;
	let reject!: (reason: Error) => void;
	const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no; });
	return { promise, resolve, reject };
}
function calls(path: string) {
	return mocks.get.mock.calls.filter(([requested]) => requested === path).length;
}
async function settle() {
	await nextTurn();
	await tick();
}
async function advance(milliseconds: number) {
	await vi.advanceTimersByTimeAsync(milliseconds);
	await settle();
}
function panel() {
	return within(screen.getByRole('dialog', { name: 'Waygate 서버 상세' }));
}
function peers() {
	return within(panel().getByRole('group', { name: accessibleName => accessibleName === '클라이언트 자동 새로고침' }));
}
function metadata() {
	return within(panel().getByRole('group', { name: accessibleName => accessibleName === '서버 및 네트워크 자동 새로고침' }));
}
async function openDetail() {
	await settle();
	await fireEvent.click(within(screen.getByRole('row', { name: /gateway-a/ })).getByText('gateway-a'));
	await settle();
}
let hidden = false;
async function setHidden(value: boolean) {
	hidden = value;
	document.dispatchEvent(new Event('visibilitychange'));
	await settle();
}
const originalAnimate = Object.getOwnPropertyDescriptor(Element.prototype, 'animate');

beforeEach(() => {
	vi.resetAllMocks();
	// Leave timeout/RAF real for Svelte transitions and Testing Library; only the
	// production interval clock and Date are advanced by these tests.
	vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval', 'Date'] });
	vi.setSystemTime(new Date('2026-09-20T00:00:00Z'));
	localStorage.clear();
	hidden = false;
	vi.spyOn(document, 'hidden', 'get').mockImplementation(() => hidden);
	auth.update((value) => ({ ...value, token: 'token-a', projectId: 'project-a' }));
	Element.prototype.animate = vi.fn().mockReturnValue({ finished: Promise.resolve(), cancel: vi.fn(), play: vi.fn() });
	vi.stubGlobal('matchMedia', vi.fn((query: string) => ({
		matches: false, media: query, onchange: null,
		addListener: vi.fn(), removeListener: vi.fn(), addEventListener: vi.fn(),
		removeEventListener: vi.fn(), dispatchEvent: vi.fn(),
	})));
	mocks.get.mockImplementation((path: string) => {
		if (path === base) return Promise.resolve([server('a'), server('b')]);
		if (path === detailPath) return Promise.resolve(server('a'));
		if (path === `${base}/server-b`) return Promise.resolve(server('b'));
		if (path === catalogPath) return Promise.resolve([{ id: 'network-a', name: 'production-net' }]);
		if (path.endsWith('/clients')) return Promise.resolve([client(path === clientsPath ? 'laptop-a' : 'laptop-b')]);
		if (path.endsWith('/networks')) return Promise.resolve([attachment('network-a')]);
		throw new Error(`Unexpected GET ${path}`);
	});
});
afterEach(() => {
	cleanup();
	vi.useRealTimers();
	vi.restoreAllMocks();
	vi.unstubAllGlobals();
	localStorage.clear();
	if (originalAnimate) Object.defineProperty(Element.prototype, 'animate', originalAnimate);
	else Reflect.deleteProperty(Element.prototype, 'animate');
});

describe('Waygate visible detail polling', () => {
	it('fetches clients immediately and every second independently of 15-second server and attachment refresh', async () => {
		render(WaygateWorkspace);
		await settle();
		expect(calls(clientsPath)).toBe(0);
		await openDetail();
		expect(panel().getByText('laptop-a')).toBeTruthy();
		expect(calls(clientsPath)).toBe(1);
		expect(calls(base)).toBe(1);
		expect(calls(attachmentsPath)).toBe(1);
		expect(calls(catalogPath)).toBe(1);
		expect(calls(detailPath)).toBe(1);
		await advance(999);
		expect(calls(clientsPath)).toBe(1);
		await advance(1);
		expect(calls(clientsPath)).toBe(2);
		expect(calls(attachmentsPath)).toBe(1);
		await advance(14_000);
		expect(calls(clientsPath)).toBe(16);
		expect(calls(base)).toBe(1);
		expect(calls(detailPath)).toBe(2);
		expect(calls(attachmentsPath)).toBe(2);
		expect(calls(catalogPath)).toBe(1);
		// Exactly 16 calls also catches an extra client request from the 15s panel refresh.
		expect(mocks.get).toHaveBeenCalledWith(clientsPath, 'token-a', 'project-a', { refresh: true });
	});

	it('keeps loaded empty lists visible during unchanged peer and attachment polls', async () => {
		const nextClients = deferred<unknown[]>();
		const nextAttachments = deferred<unknown[]>();
		let clientReads = 0;
		let attachmentReads = 0;
		mocks.get.mockImplementation((path: string) => {
			if (path === base) return Promise.resolve([server('a')]);
			if (path === detailPath) return Promise.resolve(server('a'));
			if (path === clientsPath) return ++clientReads === 1 ? Promise.resolve([]) : nextClients.promise;
			if (path === attachmentsPath) return ++attachmentReads === 1 ? Promise.resolve([]) : nextAttachments.promise;
			if (path === catalogPath) return Promise.resolve([]);
			throw new Error(`Unexpected GET ${path}`);
		});
		render(WaygateWorkspace);
		await openDetail();
		const emptyClients = panel().getByText('발급된 클라이언트가 없습니다');
		const emptyNetworks = panel().getByText(/연결된 테넌트 네트워크가 없습니다/);
		await advance(15_000);
		expect(calls(clientsPath)).toBe(2);
		expect(calls(attachmentsPath)).toBe(2);
		expect(panel().getByText('발급된 클라이언트가 없습니다')).toBe(emptyClients);
		expect(panel().getByText(/연결된 테넌트 네트워크가 없습니다/)).toBe(emptyNetworks);
		expect(panel().queryByRole('status', { name: '불러오는 중' })).toBeNull();
		// Background polls of already-loaded lists must not put the detail refresh controls into their busy state.
		const detailDialog = within(screen.getByRole('dialog', { name: 'Waygate 서버 상세' }));
		expect(detailDialog.queryAllByTitle('로딩 중…')).toHaveLength(0);
		for (const refresh of detailDialog.getAllByTitle('지금 새로고침')) expect((refresh as HTMLButtonElement).disabled).toBe(false);
		nextClients.resolve([]);
		nextAttachments.resolve([]);
		await settle();
		expect(panel().getByText('발급된 클라이언트가 없습니다')).toBe(emptyClients);
		expect(panel().getByText(/연결된 테넌트 네트워크가 없습니다/)).toBe(emptyNetworks);
		mocks.get.mockRejectedValueOnce(new ApiError(503, 'clients temporarily unavailable'));
		await advance(1000);
		expect(panel().getByText('발급된 클라이언트가 없습니다')).toBe(emptyClients);
		expect(panel().getByText('clients temporarily unavailable')).toBeTruthy();
		expect(panel().queryByRole('status', { name: '불러오는 중' })).toBeNull();
		mocks.get.mockResolvedValueOnce([client('new-client')]);
		await advance(1000);
		expect(panel().getByText('new-client')).toBeTruthy();
		expect(panel().queryByText('발급된 클라이언트가 없습니다')).toBeNull();
		expect(panel().queryByText('clients temporarily unavailable')).toBeNull();
	});

	it('turns peer polling Off without stopping metadata and manually refreshes only clients', async () => {
		render(WaygateWorkspace);
		await openDetail();
		await fireEvent.click(peers().getByRole('button', { name: accessibleName => accessibleName === 'Off' }));
		mocks.get.mockClear();
		await advance(30_000);
		expect(calls(clientsPath)).toBe(0);
		for (const path of [detailPath, attachmentsPath]) expect(calls(path)).toBe(2);
		for (const path of [base, catalogPath]) expect(calls(path)).toBe(0);
		mocks.get.mockClear();
		await fireEvent.click(peers().getByRole('button', { name: accessibleName => accessibleName === '새로고침' }));
		await settle();
		expect(calls(clientsPath)).toBe(1);
		for (const path of [base, detailPath, attachmentsPath, catalogPath]) expect(calls(path)).toBe(0);
		expect(peers().getByRole('button', { name: accessibleName => accessibleName === 'Off' }).getAttribute('aria-pressed')).toBe('true');
	});

	it('turns metadata Off without stopping peers and manually refreshes detail, catalog and peers', async () => {
		render(WaygateWorkspace);
		await openDetail();
		await fireEvent.click(metadata().getByRole('button', { name: accessibleName => accessibleName === 'Off' }));
		mocks.get.mockClear();
		await advance(30_000);
		expect(calls(clientsPath)).toBe(30);
		for (const path of [base, detailPath, attachmentsPath, catalogPath]) expect(calls(path)).toBe(0);
		mocks.get.mockClear();
		await fireEvent.click(metadata().getByRole('button', { name: accessibleName => accessibleName === '새로고침' }));
		await settle();
		expect(calls(clientsPath)).toBe(1);
		for (const path of [detailPath, attachmentsPath, catalogPath]) expect(calls(path)).toBe(1);
		expect(calls(base)).toBe(0);
	});

	it.each([1, 2, 5, 10, 15, 30, 60])('runs peers at the selected %is cadence independently of metadata', async (seconds) => {
		render(WaygateWorkspace);
		await openDetail();
		await fireEvent.click(metadata().getByRole('button', { name: accessibleName => accessibleName === '30s' }));
		await fireEvent.click(peers().getByRole('button', { name: accessibleName => accessibleName === `${seconds}s` }));
		await settle();
		mocks.get.mockClear();
		await advance(seconds * 1000 - 1);
		expect(calls(clientsPath)).toBe(0);
		await advance(1);
		expect(calls(clientsPath)).toBe(1);
		for (const path of [detailPath, attachmentsPath]) expect(calls(path)).toBe(Math.floor(seconds / 30));
		for (const path of [base, catalogPath]) expect(calls(path)).toBe(0);
		expect(metadata().getByRole('button', { name: accessibleName => accessibleName === '30s' }).getAttribute('aria-pressed')).toBe('true');
	});

	it.each([
		[false, 'dashboard-network-waygate'],
		[true, 'admin-waygate'],
	] as const)('migrates legacy detail Off without copying its cadence to peers (admin=%s)', async (admin, key) => {
		localStorage.setItem(`autoRefresh.${key}-detail.active`, 'false');
		localStorage.setItem(`autoRefresh.${key}-detail.interval`, '30');
		render(WaygateWorkspace, { admin });
		await openDetail();
		expect(panel().getByText('laptop-a')).toBeTruthy();
		for (const control of [peers(), metadata()]) {
			expect(control.getByRole('button', { name: accessibleName => accessibleName === 'Off' }).getAttribute('aria-pressed')).toBe('true');
		}
		await advance(30_000);
		expect(calls(clientsPath)).toBe(1);
		expect(calls(attachmentsPath)).toBe(1);
		expect(localStorage.getItem(`autoRefresh.${key}-peers.active`)).toBe('false');
		expect(localStorage.getItem(`autoRefresh.${key}-peers.interval`)).toBe('1');
		expect(localStorage.getItem(`autoRefresh.${key}-detail.interval`)).toBe('30');
	});

	it('retains the saved metadata interval while new peers default to one second', async () => {
		localStorage.setItem('autoRefresh.dashboard-network-waygate-detail.interval', '30');
		render(WaygateWorkspace);
		await openDetail();
		expect(metadata().getByRole('button', { name: accessibleName => accessibleName === '30s' }).getAttribute('aria-pressed')).toBe('true');
		expect(peers().getByRole('button', { name: accessibleName => accessibleName === '1s' }).getAttribute('aria-pressed')).toBe('true');
		mocks.get.mockClear();
		await advance(1000);
		expect(calls(clientsPath)).toBe(1);
		for (const path of [base, detailPath, attachmentsPath, catalogPath]) expect(calls(path)).toBe(0);
	});

	it.each([
		[false, 'dashboard-network-waygate'],
		[true, 'admin-waygate'],
	] as const)('restores an existing peer preference instead of migrating legacy Off again (admin=%s)', async (admin, key) => {
		localStorage.setItem(`autoRefresh.${key}-detail.active`, 'false');
		localStorage.setItem(`autoRefresh.${key}-peers.active`, 'true');
		localStorage.setItem(`autoRefresh.${key}-peers.interval`, '5');
		render(WaygateWorkspace, { admin });
		await openDetail();
		expect(peers().getByRole('button', { name: accessibleName => accessibleName === '5s' }).getAttribute('aria-pressed')).toBe('true');
		mocks.get.mockClear();
		await advance(4999);
		expect(calls(clientsPath)).toBe(0);
		await advance(1);
		expect(calls(clientsPath)).toBe(1);
		for (const path of [base, attachmentsPath, catalogPath]) expect(calls(path)).toBe(0);
	});

	it('stops detail requests on close and restores independent cadences on reopen', async () => {
		render(WaygateWorkspace);
		await openDetail();
		await fireEvent.click(peers().getByRole('button', { name: accessibleName => accessibleName === '5s' }));
		await fireEvent.click(metadata().getByRole('button', { name: accessibleName => accessibleName === '30s' }));
		await fireEvent.click(panel().getByRole('button', { name: '패널 닫기 버튼' }));
		await settle();
		mocks.get.mockClear();
		await advance(30_000);
		expect(calls(clientsPath)).toBe(0);
		expect(calls(attachmentsPath)).toBe(0);
		expect(calls(detailPath)).toBe(0);
		expect(calls(catalogPath)).toBe(0);
		expect(calls(base)).toBe(2);
		await openDetail();
		expect(calls(clientsPath)).toBe(1);
		expect(calls(attachmentsPath)).toBe(1);
		expect(calls(detailPath)).toBe(1);
		expect(peers().getByRole('button', { name: accessibleName => accessibleName === '5s' }).getAttribute('aria-pressed')).toBe('true');
		expect(metadata().getByRole('button', { name: accessibleName => accessibleName === '30s' }).getAttribute('aria-pressed')).toBe('true');
		mocks.get.mockClear();
		await advance(5000);
		expect(calls(clientsPath)).toBe(1);
		for (const path of [base, detailPath, attachmentsPath, catalogPath]) expect(calls(path)).toBe(0);
	});

	it('stops all hidden polling and refreshes current detail on visibility return, then stops after unmount', async () => {
		const view = render(WaygateWorkspace);
		await openDetail();
		await setHidden(true);
		mocks.get.mockClear();
		await advance(45_000);
		expect(mocks.get).not.toHaveBeenCalled();
		await setHidden(false);
		expect(calls(clientsPath)).toBe(1);
		expect(calls(base)).toBe(0);
		expect(calls(detailPath)).toBe(1);
		expect(calls(attachmentsPath)).toBe(1);
		await advance(1000);
		expect(calls(clientsPath)).toBe(2);
		await view.unmount();
		mocks.get.mockClear();
		await setHidden(true);
		await setHidden(false);
		await advance(30_000);
		expect(mocks.get).not.toHaveBeenCalled();
	});

	it.each(['peers', 'metadata'] as const)('keeps %s Off through a visibility cycle while the other controller resumes', async (paused) => {
		render(WaygateWorkspace);
		await openDetail();
		await fireEvent.click((paused === 'peers' ? peers() : metadata()).getByRole('button', { name: accessibleName => accessibleName === 'Off' }));
		await setHidden(true);
		mocks.get.mockClear();
		await advance(45_000);
		expect(mocks.get).not.toHaveBeenCalled();
		await setHidden(false);
		expect(calls(clientsPath)).toBe(paused === 'peers' ? 0 : 1);
		for (const path of [detailPath, attachmentsPath]) expect(calls(path)).toBe(paused === 'metadata' ? 0 : 1);
		for (const path of [base, catalogPath]) expect(calls(path)).toBe(0);
		await advance(15_000);
		expect(calls(clientsPath)).toBe(paused === 'peers' ? 0 : 16);
		for (const path of [detailPath, attachmentsPath]) expect(calls(path)).toBe(paused === 'metadata' ? 0 : 2);
		for (const path of [base, catalogPath]) expect(calls(path)).toBe(0);
	});

	it('does not overlap slow requests per endpoint while independent endpoints continue polling', async () => {
		render(WaygateWorkspace);
		await openDetail();
		const clients = deferred<unknown[]>();
		const serverDetail = deferred<unknown>();
		const attachments = deferred<unknown[]>();
		mocks.get.mockClear();
		mocks.get.mockImplementation((path: string) => {
			if (path === clientsPath) return clients.promise;
			if (path === detailPath) return serverDetail.promise;
			if (path === attachmentsPath) return attachments.promise;
			if (path === catalogPath) return Promise.resolve([]);
			throw new Error(`Unexpected GET ${path}`);
		});
		await advance(31_000);
		for (const path of [clientsPath, detailPath, attachmentsPath]) expect(calls(path)).toBe(1);
		expect(calls(catalogPath)).toBe(0);
		expect(calls(base)).toBe(0);
		clients.resolve([client('fresh-client')]);
		await settle();
		expect(panel().getByText('fresh-client')).toBeTruthy();
		await advance(1000);
		expect(calls(clientsPath)).toBe(2);
		for (const path of [detailPath, attachmentsPath]) expect(calls(path)).toBe(1);
		expect(calls(catalogPath)).toBe(0);
		serverDetail.resolve(server('a'));
		attachments.resolve([attachment('new-network')]);
		await settle();
		expect(panel().getByText('네트워크 이름 확인 불가')).toBeTruthy();
		expect(panel().getByText('new-network')).toBeTruthy();
		await advance(13_000);
		for (const path of [detailPath, attachmentsPath]) expect(calls(path)).toBe(2);
		expect(calls(catalogPath)).toBe(0);
	});

	it.each(['success', 'failure'])('keeps the new server polling while the previous server timed request has a late %s', async (outcome) => {
		render(WaygateWorkspace);
		await openDetail();
		await fireEvent.click(peers().getByRole('button', { name: accessibleName => accessibleName === '2s' }));
		const oldPoll = deferred<unknown[]>();
		mocks.get.mockImplementationOnce(() => oldPoll.promise);
		await advance(2000);
		expect(calls(clientsPath)).toBe(2);
		await fireEvent.click(panel().getByRole('button', { name: '패널 닫기 버튼' }));
		await settle();
		await fireEvent.click(screen.getByText('gateway-b'));
		await settle();
		const nextClientsPath = `${base}/server-b/clients`;
		expect(panel().getByText('laptop-b')).toBeTruthy();
		expect(calls(nextClientsPath)).toBe(1);
		await advance(2000);
		expect(calls(nextClientsPath)).toBe(2);
		expect(calls(clientsPath)).toBe(2);
		if (outcome === 'success') oldPoll.resolve([client('retired-server-poll')]);
		else oldPoll.reject(new ApiError(503, 'retired server polling error'));
		await settle();
		expect(panel().getByText('laptop-b')).toBeTruthy();
		expect(screen.queryByText('retired-server-poll')).toBeNull();
		expect(screen.queryByText('retired server polling error')).toBeNull();
		await advance(2000);
		expect(calls(nextClientsPath)).toBe(3);
		expect(calls(clientsPath)).toBe(2);
	});

	it('shows a client polling failure and recovers on the next cadence rather than leaving the request guard locked', async () => {
		render(WaygateWorkspace);
		await openDetail();
		mocks.get.mockRejectedValueOnce(new ApiError(503, 'telemetry unavailable'));
		await advance(1000);
		expect(panel().getByText('telemetry unavailable')).toBeTruthy();
		expect(panel().getByText('laptop-a')).toBeTruthy();
		mocks.get.mockResolvedValueOnce([client('recovered-client')]);
		await advance(1000);
		expect(panel().queryByText('telemetry unavailable')).toBeNull();
		expect(panel().getByText('recovered-client')).toBeTruthy();
		expect(panel().queryByText('laptop-a')).toBeNull();
	});

	it.each(['success', 'failure'])('discards stale client and attachment %s when another server detail opens', async (outcome) => {
		const clients = deferred<unknown[]>();
		const attachments = deferred<unknown[]>();
		mocks.get.mockImplementation((path: string) => {
			if (path === base) return Promise.resolve([server('a'), server('b')]);
			if (path === detailPath) return Promise.resolve(server('a'));
			if (path === `${base}/server-b`) return Promise.resolve(server('b'));
			if (path === clientsPath) return clients.promise;
			if (path === attachmentsPath) return attachments.promise;
			if (path === catalogPath) return Promise.resolve([]);
			if (path.endsWith('/clients')) return Promise.resolve([client('laptop-b')]);
			if (path.endsWith('/networks')) return Promise.resolve([attachment('network-b')]);
			throw new Error(`Unexpected GET ${path}`);
		});
		render(WaygateWorkspace);
		await openDetail();
		await fireEvent.click(panel().getByRole('button', { name: '패널 닫기 버튼' }));
		await settle();
		await fireEvent.click(screen.getByText('gateway-b'));
		await settle();
		if (outcome === 'success') {
			clients.resolve([client('old-client')]);
			attachments.resolve([attachment('old-network')]);
		} else {
			clients.reject(new ApiError(503, 'old client error'));
			attachments.reject(new ApiError(503, 'old attachment error'));
		}
		await settle();
		expect(panel().getByText('laptop-b')).toBeTruthy();
		expect(panel().getByText('network-b')).toBeTruthy();
		for (const stale of ['old-client', 'old-network', 'old client error', 'old attachment error']) {
			expect(screen.queryByText(stale)).toBeNull();
		}
		await advance(1000);
		expect(calls(clientsPath)).toBe(1);
		expect(calls(`${base}/server-b/clients`)).toBe(2);
	});

	it('queues fresh detail on same-server reopen without overlapping the retired request even while paused', async () => {
		localStorage.setItem('autoRefresh.dashboard-network-waygate-detail.active', 'false');
		const clients = deferred<unknown[]>();
		const attachments = deferred<unknown[]>();
		let clientRequests = 0;
		let attachmentRequests = 0;
		mocks.get.mockImplementation((path: string) => {
			if (path === base) return Promise.resolve([server('a')]);
			if (path === detailPath) return Promise.resolve(server('a'));
			if (path === catalogPath) return Promise.resolve([]);
			if (path === clientsPath) return ++clientRequests === 1 ? clients.promise : Promise.resolve([client('fresh-client')]);
			if (path === attachmentsPath) return ++attachmentRequests === 1 ? attachments.promise : Promise.resolve([attachment('fresh-network')]);
			throw new Error(`Unexpected GET ${path}`);
		});
		render(WaygateWorkspace);
		await openDetail();
		await fireEvent.click(panel().getByRole('button', { name: '패널 닫기 버튼' }));
		await settle();
		await openDetail();
		await advance(2000);
		expect(calls(clientsPath)).toBe(1);
		expect(calls(attachmentsPath)).toBe(1);
		clients.resolve([client('retired-client')]);
		attachments.resolve([attachment('retired-network')]);
		await settle();
		expect(calls(clientsPath)).toBe(2);
		expect(calls(attachmentsPath)).toBe(2);
		expect(panel().getByText('fresh-client')).toBeTruthy();
		expect(panel().getByText('fresh-network')).toBeTruthy();
		expect(screen.queryByText('retired-client')).toBeNull();
		expect(screen.queryByText('retired-network')).toBeNull();
	});

	it.each(['success', 'failure'])('discards a pre-mutation polling %s and queues current client state without overlap', async (outcome) => {
		render(WaygateWorkspace);
		await openDetail();
		const pending = deferred<unknown[]>();
		const current = deferred<unknown[]>();
		mocks.get.mockImplementationOnce(() => pending.promise).mockImplementationOnce(() => current.promise);
		await advance(1000);
		mocks.patch.mockResolvedValue({ ...client('laptop-a'), enabled: false });
		await fireEvent.click(panel().getByRole('button', { name: 'laptop-a 비활성화' }));
		await settle();
		expect(mocks.patch).toHaveBeenCalledExactlyOnceWith(`${clientsPath}/laptop-a`, { enabled: false }, 'token-a', 'project-a');
		expect(calls(clientsPath)).toBe(2);
		if (outcome === 'success') pending.resolve([client('stale-before-mutation')]);
		else pending.reject(new ApiError(503, 'pre-mutation error'));
		await settle();
		expect(calls(clientsPath)).toBe(3);
		expect(panel().getByText('laptop-a')).toBeTruthy();
		expect(screen.queryByText('stale-before-mutation')).toBeNull();
		expect(screen.queryByText('pre-mutation error')).toBeNull();
		current.resolve([{ ...client('laptop-a'), enabled: false }]);
		await settle();
		expect(panel().getByRole('button', { name: 'laptop-a 활성화' })).toBeTruthy();
		expect(panel().queryByRole('button', { name: 'laptop-a 비활성화' })).toBeNull();
	});

	it.each(['success', 'failure'])('discards an in-flight client %s after hiding the page and fetches current data when visible again', async (outcome) => {
		render(WaygateWorkspace);
		await openDetail();
		const pending = deferred<unknown[]>();
		mocks.get.mockImplementationOnce(() => pending.promise);
		await advance(1000);
		await setHidden(true);
		if (outcome === 'success') pending.resolve([client('hidden-stale-client')]);
		else pending.reject(new ApiError(503, 'hidden stale error'));
		await settle();
		expect(panel().getByText('laptop-a')).toBeTruthy();
		expect(screen.queryByText('hidden-stale-client')).toBeNull();
		expect(screen.queryByText('hidden stale error')).toBeNull();
		mocks.get.mockImplementation((path: string) => {
			if (path === base) return Promise.resolve([server('a'), server('b')]);
			if (path === detailPath) return Promise.resolve(server('a'));
			if (path === clientsPath) return Promise.resolve([client('visible-current-client')]);
			if (path === catalogPath || path === attachmentsPath) return Promise.resolve([]);
			throw new Error(`Unexpected GET ${path}`);
		});
		await setHidden(false);
		expect(panel().getByText('visible-current-client')).toBeTruthy();
		expect(screen.queryByText('laptop-a')).toBeNull();
	});
});
