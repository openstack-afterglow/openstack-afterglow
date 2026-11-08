import type { PermissionState } from '$lib/stores/servicePermissions';
import { setImmediate as nextTurn } from 'node:timers/promises';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, within } from '@testing-library/svelte';
import { tick } from 'svelte';
import { writable, type Writable } from 'svelte/store';

const mocks = vi.hoisted(() => ({
	get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn(), downloadBlob: vi.fn(),
	confirm: vi.fn(), toastSuccess: vi.fn(), toastError: vi.fn(), download: vi.fn(),
	qr: vi.fn(),
	refresh: [] as (() => unknown)[],
}));
vi.mock('$lib/api/client', () => ({
	api: { get: mocks.get, post: mocks.post, patch: mocks.patch, delete: mocks.delete, downloadBlob: mocks.downloadBlob },
	ApiError: class ApiError extends Error {
		constructor(public status: number, message: string) { super(message); }
	},
}));
vi.mock('$lib/stores/auth', () => ({
	auth: writable({ token: 'token-a', projectId: 'project-a', userId: 'user-a', isSystemAdmin: false, roles: ['member'] }),
	authReady: writable(true), projectSwitching: writable(false),
}));
vi.mock('$lib/stores/servicePermissions', () => ({
	serviceCapabilities: writable<(leaf: string) => boolean>(() => false),
	observedProjectPermissions: writable<PermissionState>({ permissions: null, loading: false, error: '' }),
}));
vi.mock('qrcode', () => ({ default: { toDataURL: mocks.qr } }));
vi.mock('$lib/config/site', () => ({ siteConfig: writable({ services: { waygate: true } }) }));
vi.mock('$lib/stores/toast', () => ({ toast: { success: mocks.toastSuccess, error: mocks.toastError } }));
vi.mock('$lib/stores/confirm.svelte', () => ({ confirmDialog: mocks.confirm }));
vi.mock('$lib/utils/downloadBlob', () => ({ downloadBlobAs: mocks.download }));
vi.mock('$lib/utils/autoRefresh.svelte', () => ({
	createAutoRefresh: (refresh: () => unknown) => {
		mocks.refresh.push(refresh);
		return { active: false, intervalSeconds: 15, intervalOptions: [15] };
	},
}));

import { auth } from '$lib/stores/auth';
import { observedProjectPermissions, serviceCapabilities } from '$lib/stores/servicePermissions';
import { t as commonT } from '$lib/i18n/ns/common';
import { ApiError } from '$lib/api/client';
import { t } from '$lib/i18n/ns/waygate';
import type { WaygateClient, WaygateServer } from '$lib/types/waygate';
import WaygateWorkspace from '../WaygateWorkspace.svelte';
import { getLocale, initLocale } from '$lib/i18n/runtime.svelte';

const base = '/api/v1/waygate/servers';
const capabilityStore = serviceCapabilities as Writable<(leaf: string) => boolean>;
const allWaygateLeaves = [
	'waygate-inventory_reader', 'waygate-connect_user', 'waygate-clients_editor',
	'waygate-clients_admin', 'waygate-gateways_editor', 'waygate-gateways_admin', 'waygate-routing_admin',
];
function grant(...leaves: string[]) {
	capabilityStore.set((leaf) => leaves.includes(leaf));
}
const server = (project: string) => ({
	id: `server-${project}`, project_id: `project-${project}`, name: `gateway-${project}`,
	status: 'ACTIVE', tunnel_cidr: '10.240.0.0/24', listen_port: 51820,
	dns: null as WaygateServer['dns'], persistent_keepalive: 25,
	created_at: '2026-09-20T00:00:00Z',
});
const client = {
	id: 'client-a', name: 'laptop-a', enabled: true, online: false,
	owner_user_id: 'user-a',
	tunnel_ip: '10.240.0.2', rx_bytes: 100, tx_bytes: 200,
	last_reported_at: '2026-09-20T00:00:00Z',
	last_handshake_at: null, created_at: '2026-09-20T00:00:00Z',
	dns: null as WaygateClient['dns'], mtu: null as WaygateClient['mtu'],
	// Absent optional inheritance flags intentionally model explicit legacy settings.
	persistent_keepalive: 0, psk_enabled: false,
};

function deferred<T>() {
	let resolve!: (value: T) => void;
	let reject!: (error: Error) => void;
	const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no; });
	return { promise, resolve, reject };
}
function switchProject(projectId: string | null) {
	auth.update((value) => ({ ...value, projectId }));
}
async function openDetail() {
	await fireEvent.click(await screen.findByText('gateway-a'));
	await screen.findByText('laptop-a');
}
const originalLocale = getLocale();
async function settle() {
	// Drain the API adapter's promise chain before asserting absence of stale effects.
	await nextTurn();
	await tick();
}

const originalAnimate = Object.getOwnPropertyDescriptor(Element.prototype, 'animate');
beforeEach(() => {
	vi.resetAllMocks();
	mocks.refresh.length = 0;
	auth.update((value) => ({ ...value, token: 'token-a', projectId: 'project-a', userId: 'user-a', isSystemAdmin: false, roles: ['member'] }));
	(observedProjectPermissions as Writable<PermissionState>).set({ permissions: null, loading: false, error: '' });
	grant(...allWaygateLeaves);
	Element.prototype.animate = vi.fn().mockReturnValue({ finished: Promise.resolve(), cancel: vi.fn(), play: vi.fn() });
	vi.stubGlobal('matchMedia', vi.fn((query: string) => ({
		matches: false, media: query, onchange: null,
		addListener: vi.fn(), removeListener: vi.fn(), addEventListener: vi.fn(),
		removeEventListener: vi.fn(), dispatchEvent: vi.fn(),
	})));
	mocks.confirm.mockResolvedValue(true);
	mocks.get.mockImplementation((path: string, _token: string, projectId: string) => {
		if (path === base) return Promise.resolve([server(projectId === 'project-b' ? 'b' : 'a')]);
		if (path === `${base}/server-a`) return Promise.resolve(server('a'));
		if (path === `${base}/server-b`) return Promise.resolve(server('b'));
		if (path.endsWith('/clients')) return Promise.resolve(projectId === 'project-a' ? [client] : []);
		if (path === '/api/v1/networks') return Promise.resolve([]);
		if (path.endsWith('/networks')) return Promise.resolve([]);
		throw new Error(`Unexpected GET ${path}`);
	});
});
afterEach(() => {
	cleanup();
	vi.unstubAllGlobals();
	initLocale(originalLocale);
	if (originalAnimate) Object.defineProperty(Element.prototype, 'animate', originalAnimate);
	else Reflect.deleteProperty(Element.prototype, 'animate');
});

	it('prunes hidden selections so bulk actions and visible selection share one set', async () => {
		mocks.get.mockResolvedValueOnce([server('a'), { ...server('b'), project_id: 'project-a' }]);
		render(WaygateWorkspace);
		await screen.findByText('gateway-b');
		await fireEvent.click(screen.getByRole('checkbox', { name: t('project.selection.server', { name: 'gateway-a' }) }));
		await fireEvent.click(screen.getByRole('checkbox', { name: t('project.selection.server', { name: 'gateway-b' }) }));
		const search = screen.getByRole('searchbox', { name: commonT('table.search') });
		await fireEvent.input(search, { target: { value: '^gateway-a$' } });
		expect(screen.queryByText('gateway-b')).toBeNull();
		await fireEvent.input(search, { target: { value: '' } });
		expect((screen.getByRole('checkbox', { name: t('project.selection.server', { name: 'gateway-a' }) }) as HTMLInputElement).checked).toBe(true);
		expect((screen.getByRole('checkbox', { name: t('project.selection.server', { name: 'gateway-b' }) }) as HTMLInputElement).checked).toBe(false);
		await fireEvent.input(search, { target: { value: '^missing$' } });
		expect(screen.queryByLabelText(t('project.selection.bulkActions'))).toBeNull();
		await fireEvent.input(search, { target: { value: '' } });
		expect((screen.getByRole('checkbox', { name: t('project.selection.server', { name: 'gateway-a' }) }) as HTMLInputElement).checked).toBe(false);
		expect((screen.getByRole('checkbox', { name: t('project.selection.server', { name: 'gateway-b' }) }) as HTMLInputElement).checked).toBe(false);
	});

describe('Waygate workspace project isolation', () => {
	it('retains stable client status and owner facets when locale changes', async () => {
		initLocale('en');
		render(WaygateWorkspace);
		await openDetail();
		for (const key of ['project.client.status', 'project.client.owner'] as const) {
			const label = commonT('table.filterColumn', { column: t(key) });
			await fireEvent.click(screen.getByRole('button', { name: label }));
			const menu = within(screen.getByRole('dialog', { name: label }));
			await fireEvent.click(menu.getByRole('button', { name: commonT('table.selectNone') }));
			await fireEvent.click(menu.getByRole('checkbox'));
			await fireEvent.click(menu.getByRole('button', { name: commonT('actions.close') }));
		}
		initLocale('ko');
		await tick();
		expect(screen.getByText('laptop-a')).toBeTruthy();
		for (const key of ['project.client.status', 'project.client.owner'] as const) {
			const label = commonT('table.filterColumn', { column: t(key) });
			await fireEvent.click(screen.getByRole('button', { name: label }));
			const menu = within(screen.getByRole('dialog', { name: label }));
			expect((menu.getByRole('checkbox') as HTMLInputElement).checked).toBe(true);
			await fireEvent.click(menu.getByRole('button', { name: commonT('actions.close') }));
		}
	});

	it('retains display conditions through token renewal without retaining mutation or selection lifetimes', async () => {
		const confirmation = deferred<boolean>();
		mocks.confirm.mockReturnValue(confirmation.promise);
		render(WaygateWorkspace);
		await screen.findByText('gateway-a');
		const search = () => screen.getByRole('searchbox', { name: commonT('table.search') }) as HTMLInputElement;
		await fireEvent.input(search(), { target: { value: '^gateway-a$' } });
		const name = t('project.server.label');
		await fireEvent.click(screen.getByRole('button', { name: commonT('table.sortColumn', { column: name, direction: commonT('table.none') }) }));
		await fireEvent.click(screen.getByRole('button', { name: commonT('table.sortColumn', { column: name, direction: commonT('table.ascending') }) }));
		await fireEvent.click(screen.getByRole('button', { name: commonT('table.filterColumn', { column: name }) }));
		const menu = within(screen.getByRole('dialog', { name: commonT('table.filterColumn', { column: name }) }));
		await fireEvent.click(menu.getByRole('button', { name: commonT('table.selectNone') }));
		await fireEvent.click(menu.getByRole('checkbox', { name: 'gateway-a' }));
		await fireEvent.click(menu.getByRole('button', { name: commonT('actions.close') }));
		const gatewaySelection = screen.getByRole('checkbox', { name: t('project.selection.server', { name: 'gateway-a' }) });
		await fireEvent.click(gatewaySelection);
		await fireEvent.click(within(gatewaySelection.closest<HTMLElement>('article, tr')!).getByRole('button', { name: t('project.actions.delete') }));
		auth.update(value => ({ ...value, token: 'renewed-token' }));
		await settle();
		confirmation.resolve(true);
		await settle();
		expect(mocks.delete).not.toHaveBeenCalled();
		expect(search().value).toBe('^gateway-a$');
		expect(screen.getByRole('button', { name: commonT('table.sortColumn', { column: name, direction: commonT('table.descending') }) })).toBeTruthy();
		expect((screen.getByRole('checkbox', { name: 'gateway-a 선택' }) as HTMLInputElement).checked).toBe(false);
		await fireEvent.click(screen.getByRole('button', { name: commonT('table.filterColumn', { column: name }) }));
		const restored = within(screen.getByRole('dialog', { name: commonT('table.filterColumn', { column: name }) }));
		expect((restored.getByRole('checkbox', { name: 'gateway-a' }) as HTMLInputElement).checked).toBe(true);
		await fireEvent.click(restored.getByRole('button', { name: commonT('actions.close') }));
		switchProject('project-b');
		await screen.findByText('gateway-b');
		expect(search().value).toBe('');
		expect(screen.getByRole('button', { name: commonT('table.sortColumn', { column: name, direction: commonT('table.none') }) })).toBeTruthy();
		expect(screen.queryByRole('button', { name: commonT('table.resetView') })).toBeNull();
	});

	it('keeps display state during authority revalidation and clears it on a changed authoritative result', async () => {
		const permissions = observedProjectPermissions as Writable<PermissionState>;
		const authority = { is_owner: false, is_manager: false, can_write: true, service_permissions: { waygate: ['waygate-inventory_reader'] } };
		permissions.set({ permissions: authority, loading: false, error: '' });
		render(WaygateWorkspace);
		await screen.findByText('gateway-a');
		await fireEvent.input(screen.getByRole('searchbox', { name: commonT('table.search') }), { target: { value: '^gateway-a$' } });
		permissions.set({ permissions: null, loading: true, error: '' });
		await tick();
		expect((screen.getByRole('searchbox', { name: commonT('table.search') }) as HTMLInputElement).value).toBe('^gateway-a$');
		permissions.set({ permissions: authority, loading: false, error: '' });
		await tick();
		expect((screen.getByRole('searchbox', { name: commonT('table.search') }) as HTMLInputElement).value).toBe('^gateway-a$');
		permissions.set({ permissions: { ...authority, can_write: false }, loading: false, error: '' });
		await settle();
		expect((screen.getByRole('searchbox', { name: commonT('table.search') }) as HTMLInputElement).value).toBe('');
	});

	it('does not request an implicit admin all-project view, including callbacks from a retired timer', async () => {
		switchProject(null);
		render(WaygateWorkspace, { admin: true });
		expect(screen.getByRole('heading', { name: 'Waygate 관리' })).toBeTruthy();
		expect(screen.getByText('ADMIN / WAYGATE')).toBeTruthy();
		await tick();
		expect(mocks.get).not.toHaveBeenCalled();
		expect(screen.queryByRole('button', { name: '+ Waygate 서버 생성' })).toBeNull();
		switchProject('project-a');
		await screen.findByText('gateway-a');
		const retiredRefresh = [...mocks.refresh];
		switchProject(null);
		await tick();
		mocks.get.mockClear();
		for (const refresh of retiredRefresh) await refresh();
		expect(mocks.get).not.toHaveBeenCalled();
		expect(screen.queryByText('gateway-a')).toBeNull();
	});

	it('ignores a late list response after switching projects', async () => {
		const oldList = deferred<unknown[]>();
		mocks.get.mockImplementation((path: string, _token: string, projectId: string) => {
			if (path !== base) throw new Error(`Unexpected GET ${path}`);
			return projectId === 'project-a' ? oldList.promise : Promise.resolve([server('b')]);
		});
		render(WaygateWorkspace);
		expect(screen.getByRole('heading', { name: 'Waygate' })).toBeTruthy();
		expect(screen.getByText('NETWORK / WAYGATE')).toBeTruthy();
		await tick();
		switchProject('project-b');
		await screen.findByText('gateway-b');
		oldList.resolve([server('a')]);
		await settle();
		expect(screen.queryByText('gateway-a')).toBeNull();
		expect(screen.getByText('gateway-b')).toBeTruthy();
	});

	it('clears selection, detail and traffic and discards pending network choices', async () => {
		const choices = deferred<unknown[]>();
		render(WaygateWorkspace, { admin: true });
		await screen.findByText('gateway-a');
		await fireEvent.click(screen.getByRole('checkbox', { name: 'gateway-a 선택' }));
		await openDetail();
		expect(screen.getByRole('region', { name: 'laptop-a 클라이언트 기준 트래픽' })).toBeTruthy();
		mocks.get.mockImplementationOnce(() => choices.promise);
		await fireEvent.click(screen.getByRole('button', { name: '+ 네트워크 연결' }));
		switchProject('project-b');
		await screen.findByText('gateway-b');
		choices.resolve([{ id: 'network-a', name: 'old-network', is_external: false }]);
		await settle();
		expect(screen.queryByRole('region', { name: 'laptop-a 클라이언트 기준 트래픽' })).toBeNull();
		expect(screen.queryByRole('button', { name: '연결할 네트워크 선택' })).toBeNull();
		expect(screen.queryByLabelText('선택한 Waygate 서버 일괄 작업')).toBeNull();
		expect((screen.getByRole('checkbox', { name: 'gateway-b 선택' }) as HTMLInputElement).checked).toBe(false);
		await fireEvent.click(screen.getByText('gateway-b'));
		expect(screen.queryByText('old-network')).toBeNull();
		expect(screen.queryByText('laptop-a')).toBeNull();
	});

	it('does not confirm an old-project deletion even when returning to the same project', async () => {
		const confirmation = deferred<boolean>();
		mocks.confirm.mockReturnValue(confirmation.promise);
		render(WaygateWorkspace);
		await screen.findByText('gateway-a');
		await fireEvent.click(screen.getByRole('button', { name: /^삭제$/ }));
		switchProject('project-b');
		switchProject('project-a');
		confirmation.resolve(true);
		await settle();
		expect(mocks.delete).not.toHaveBeenCalled();
	});

	it.each(['success', 'failure'])('does not publish mutation %s or refresh the new project from an old callback', async (outcome) => {
		const creation = deferred<unknown>();
		mocks.post.mockReturnValue(creation.promise);
		render(WaygateWorkspace);
		await screen.findByText('gateway-a');
		await fireEvent.click(screen.getByRole('button', { name: '+ Waygate 서버 생성' }));
		await fireEvent.input(screen.getByRole('textbox', { name: t('project.server.expectedClients') }), { target: { value: '30' } });
		await fireEvent.click(screen.getByRole('button', { name: /^생성$/ }));
		switchProject('project-b');
		await screen.findByText('gateway-b');
		mocks.get.mockClear();
		if (outcome === 'success') creation.resolve(server('a'));
		else creation.reject(new Error('old-project-failure'));
		await settle();
		expect(screen.queryByText('old-project-failure')).toBeNull();
		expect(mocks.toastError).not.toHaveBeenCalled();
		expect(mocks.toastSuccess).not.toHaveBeenCalled();
		expect(mocks.get).not.toHaveBeenCalled();
	});

	it('ignores pending clients and attachments after opening detail in the next project', async () => {
		const clients = deferred<unknown[]>();
		const attachments = deferred<unknown[]>();
		mocks.get.mockImplementation((path: string, _token: string, projectId: string) => {
			if (path === base) return Promise.resolve([server(projectId === 'project-b' ? 'b' : 'a')]);
			if (path === `${base}/server-a`) return Promise.resolve(server('a'));
			if (path === `${base}/server-b`) return Promise.resolve(server('b'));
			if (path.endsWith('/clients')) return projectId === 'project-a' ? clients.promise : Promise.resolve([]);
			if (path === '/api/v1/networks') return Promise.resolve([]);
			if (path.endsWith('/networks')) return projectId === 'project-a' ? attachments.promise : Promise.resolve([]);
			throw new Error(`Unexpected GET ${path}`);
		});
		render(WaygateWorkspace);
		await fireEvent.click(await screen.findByText('gateway-a'));
		switchProject('project-b');
		await fireEvent.click(await screen.findByText('gateway-b'));
		clients.resolve([client]);
		attachments.resolve([{ id: 1, network_id: 'old-attached-network', status: 'ACTIVE', nat_mode: 'snat' }]);
		await settle();
		expect(screen.queryByText('laptop-a')).toBeNull();
		expect(screen.queryByText('old-attached-network')).toBeNull();
		expect(screen.getByText('발급된 클라이언트가 없습니다')).toBeTruthy();
	});

	it('does not download old-project secrets when a pending config resolves', async () => {
		const config = deferred<{ blob: Blob; filename: string }>();
		mocks.downloadBlob.mockReturnValue(config.promise);
		render(WaygateWorkspace);
		await openDetail();
		await fireEvent.click(screen.getByRole('button', { name: 'laptop-a .conf 다운로드' }));
		switchProject('project-b');
		await screen.findByText('gateway-b');
		config.resolve({ blob: new Blob(['private-key']), filename: 'old.conf' });
		await settle();
		expect(mocks.download).not.toHaveBeenCalled();
		expect(mocks.toastSuccess).not.toHaveBeenCalled();
	});
});

describe('Waygate attachment network names', () => {
	const attachment = (networkId: string, id = 1) => ({ id, network_id: networkId, status: 'ACTIVE', nat_mode: 'snat' });

	it('loads names on detail open without opening the attachment modal and retains the ID as a tooltip', async () => {
		const catalog = deferred<unknown[]>();
		mocks.get.mockImplementation((path: string) => {
			if (path === base) return Promise.resolve([server('a')]);
			if (path === `${base}/server-a`) return Promise.resolve(server('a'));
			if (path === '/api/v1/networks') return catalog.promise;
			if (path.endsWith('/clients')) return Promise.resolve([client]);
			if (path.endsWith('/networks')) return Promise.resolve([attachment('network-a')]);
			throw new Error(`Unexpected GET ${path}`);
		});
		render(WaygateWorkspace);
		await openDetail();
		expect(screen.getByText('네트워크 이름 확인 불가')).toBeTruthy();
		expect(screen.getByText('network-a').getAttribute('title')).toBe('network-a');
		expect(mocks.get).toHaveBeenCalledWith('/api/v1/networks', 'token-a', 'project-a', { refresh: true });
		catalog.resolve([{ id: 'network-a', name: '  production-net  ', is_external: false }]);
		await settle();
		expect(screen.getByText('production-net')).toBeTruthy();
		expect(screen.getByText('network-a').getAttribute('title')).toBe('network-a');
		expect(screen.queryByRole('button', { name: '연결할 네트워크 선택' })).toBeNull();
	});

	it.each(['unknown', 'blank', 'failure'])('keeps the attachment usable with an ID when the catalog name is %s', async (kind) => {
		mocks.get.mockImplementation((path: string) => {
			if (path === base) return Promise.resolve([server('a')]);
			if (path === `${base}/server-a`) return Promise.resolve(server('a'));
			if (path === '/api/v1/networks') {
				if (kind === 'failure') return Promise.reject(new Error('catalog unavailable'));
				return Promise.resolve(kind === 'unknown' ? [] : [{ id: 'network-a', name: '   ' }]);
			}
			if (path.endsWith('/clients')) return Promise.resolve([client]);
			if (path.endsWith('/networks')) return Promise.resolve([attachment('network-a')]);
			throw new Error(`Unexpected GET ${path}`);
		});
		render(WaygateWorkspace);
		await openDetail();
		await settle();
		expect(screen.getByText(kind === 'blank' ? '이름 없는 네트워크' : '네트워크 이름 확인 불가')).toBeTruthy();
		expect(screen.getByText('network-a').getAttribute('title')).toBe('network-a');
		expect(screen.getByRole('button', { name: '해제' }).hasAttribute('disabled')).toBe(false);
		expect(screen.getByText('laptop-a')).toBeTruthy();
	});

	it.each(['resolved', 'pending'])('does not reuse a %s catalog after changing project with the same network ID', async (state) => {
		const oldCatalog = deferred<unknown[]>();
		const newCatalog = deferred<unknown[]>();
		mocks.get.mockImplementation((path: string, _token: string, projectId: string) => {
			if (path === base) return Promise.resolve([server(projectId === 'project-a' ? 'a' : 'b')]);
			if (path === `${base}/server-a`) return Promise.resolve(server('a'));
			if (path === `${base}/server-b`) return Promise.resolve(server('b'));
			if (path === '/api/v1/networks') return projectId === 'project-a' ? oldCatalog.promise : newCatalog.promise;
			if (path.endsWith('/clients')) return Promise.resolve([]);
			if (path.endsWith('/networks')) return Promise.resolve([attachment('shared-id')]);
			throw new Error(`Unexpected GET ${path}`);
		});
		render(WaygateWorkspace);
		await fireEvent.click(await screen.findByText('gateway-a'));
		if (state === 'resolved') {
			oldCatalog.resolve([{ id: 'shared-id', name: 'private-project-a-name' }]);
			await screen.findByText('private-project-a-name');
		}
		switchProject('project-b');
		await fireEvent.click(await screen.findByText('gateway-b'));
		await settle();
		expect(screen.getByText('네트워크 이름 확인 불가')).toBeTruthy();
		expect(screen.getByText('shared-id')).toBeTruthy();
		expect(screen.queryByText('private-project-a-name')).toBeNull();
		newCatalog.resolve([{ id: 'shared-id', name: 'project-b-name' }]);
		await screen.findByText('project-b-name');
		if (state === 'pending') oldCatalog.resolve([{ id: 'shared-id', name: 'private-project-a-name' }]);
		await settle();
		expect(screen.getByText('project-b-name')).toBeTruthy();
		expect(screen.queryByText('private-project-a-name')).toBeNull();
		expect(mocks.get).toHaveBeenCalledWith('/api/v1/networks', 'token-a', 'project-b', { refresh: true });
	});
});

describe('Waygate server defaults and dynamic client inheritance', () => {
	const defaults = { dns: '9.9.9.9', persistent_keepalive: 40 };
	const updatedDefaults = { dns: '1.1.1.1, 8.8.8.8', persistent_keepalive: 0 };
	// The owner field starts empty: issuance sends an explicit unassigned owner.
	const inheritedRequest = { name: 'new-laptop', mtu: null, owner_user_id: null };
	const inheritedClient = { ...client, ...defaults, mtu: null, inherit_dns: true, inherit_persistent_keepalive: true };
	let currentServer = { ...server('a'), ...defaults };
	let currentClients: Array<typeof client & { dns?: string | null; mtu?: number | null; inherit_dns?: boolean; inherit_persistent_keepalive?: boolean }>;

	beforeEach(() => {
		currentServer = { ...server('a'), ...defaults };
		currentClients = [client];
		mocks.get.mockImplementation((path: string, _token: string, projectId: string) => {
			if (path === base) return Promise.resolve(projectId === 'project-a' ? [currentServer] : [server('b')]);
			if (path === `${base}/server-a`) return Promise.resolve(currentServer);
			if (path === `${base}/server-b`) return Promise.resolve(server('b'));
			if (path === '/api/v1/networks' || path.endsWith('/networks')) return Promise.resolve([]);
			if (path.endsWith('/clients')) return Promise.resolve(currentClients);
			throw new Error(`Unexpected GET ${path}`);
		});
		mocks.post.mockResolvedValue({ ...inheritedClient, name: 'new-laptop', psk_enabled: true, tunnel_conf: '[Interface]\nPrivateKey = test-key' });
	});

	async function openIssuance() {
		await fireEvent.click(screen.getByRole('button', { name: '+ 클라이언트 발급' }));
		const modal = within(screen.getByRole('dialog', { name: 'Waygate 클라이언트 발급' }));
		await fireEvent.input(modal.getByRole('textbox', { name: t('settings.name') }), { target: { value: 'new-laptop' } });
		return modal;
	}

	function settingMode(field: 'DNS' | 'PersistentKeepalive') {
		return within(screen.getByRole('group', { name: accessibleName => accessibleName === `${field} 설정 방식` }));
	}

	async function fillServerSettings(dns: string, keepalive: string, expectedClients?: string) {
		await fireEvent.input(screen.getByLabelText('DNS', { exact: true }), { target: { value: dns } });
		await fireEvent.input(screen.getByLabelText(/PersistentKeepalive/, { selector: 'input' }), { target: { value: keepalive } });
		if (expectedClients !== undefined) {
			await fireEvent.input(screen.getByRole('textbox', { name: t('project.server.expectedClients') }), { target: { value: expectedClients } });
		}
	}

	it('creates a named server with DNS, disabled keepalive and the declared client count but no server MTU', async () => {
		mocks.post.mockImplementation(async (_path: string, body: typeof currentServer) => {
			currentServer = { ...currentServer, ...body };
			return currentServer;
		});
		render(WaygateWorkspace);
		await screen.findByText('gateway-a');
		await fireEvent.click(screen.getByRole('button', { name: '+ Waygate 서버 생성' }));
		const modal = within(screen.getByRole('dialog', { name: 'Waygate 서버 생성' }));
		await fireEvent.input(modal.getByRole('textbox', { name: t('settings.name') }), { target: { value: 'office-gateway' } });
		expect(modal.queryByLabelText('MTU', { exact: true })).toBeNull();
		await fillServerSettings('1.1.1.1,8.8.8.8', '0', '30');
		expect(modal.getByText(t('project.server.expectedClientsTier', { tier: t('project.server.tier.small') }))).toBeTruthy();
		await fireEvent.click(modal.getByRole('button', { name: accessibleName => accessibleName === '생성' }));
		await settle();
		expect(mocks.post).toHaveBeenCalledExactlyOnceWith(base, { name: 'office-gateway', ...updatedDefaults, expected_clients: 30 }, 'token-a', 'project-a', { timeoutMs: 58_000 });
		expect(screen.getByText('office-gateway')).toBeTruthy();
		expect(screen.queryByRole('dialog', { name: 'Waygate 서버 생성' })).toBeNull();
	});

	it.each(['', '0', '1001', '2.5'])('requires a declared client count of 1..1000 before creating (input=%j)', async (value) => {
		render(WaygateWorkspace);
		await screen.findByText('gateway-a');
		await fireEvent.click(screen.getByRole('button', { name: '+ Waygate 서버 생성' }));
		const modal = within(screen.getByRole('dialog', { name: 'Waygate 서버 생성' }));
		await fillServerSettings('1.1.1.1', '25', value);
		await fireEvent.click(modal.getByRole('button', { name: accessibleName => accessibleName === '생성' }));
		await settle();
		const input = modal.getByRole('textbox', { name: t('project.server.expectedClients') });
		expect(modal.getByText(t('validation.expectedClients', { max: 1000 }))).toBeTruthy();
		expect(input.getAttribute('aria-invalid')).toBe('true');
		expect(document.activeElement).toBe(input);
		expect(mocks.post).not.toHaveBeenCalled();
	});

	it('announces the large tier above 50 clients and shows the applied tier read-only in details', async () => {
		currentServer = { ...currentServer, expected_clients: 120, flavor_tier: 'large' } as typeof currentServer;
		render(WaygateWorkspace);
		await screen.findByText('gateway-a');
		await fireEvent.click(screen.getByRole('button', { name: '+ Waygate 서버 생성' }));
		const modal = within(screen.getByRole('dialog', { name: 'Waygate 서버 생성' }));
		await fireEvent.input(modal.getByRole('textbox', { name: t('project.server.expectedClients') }), { target: { value: '51' } });
		expect(modal.getByText(t('project.server.expectedClientsTier', { tier: t('project.server.tier.large') }))).toBeTruthy();
		await fireEvent.click(modal.getByRole('button', { name: t('project.actions.cancel') }));
		await openDetail();
		const details = screen.getByText(t('project.server.flavorTier')).closest('dl')!;
		expect(within(details).getByText('120')).toBeTruthy();
		expect(within(details).getByText(t('project.server.tier.large'))).toBeTruthy();
	});

	it.each([
		['client deadline', () => new DOMException('signal timed out', 'TimeoutError')],
		['proxy 503', () => new ApiError(503, 'waygate 서비스를 사용할 수 없습니다')],
		['load balancer 504', () => new ApiError(504, 'Gateway Timeout')],
	])('reports an unconfirmed create and shows the server the backend created after a %s', async (_name, failure) => {
		mocks.post.mockImplementation(async (_path: string, body: typeof currentServer) => {
			currentServer = { ...currentServer, ...body };
			throw failure();
		});
		render(WaygateWorkspace);
		await screen.findByText('gateway-a');
		await fireEvent.click(screen.getByRole('button', { name: '+ Waygate 서버 생성' }));
		const modal = within(screen.getByRole('dialog', { name: 'Waygate 서버 생성' }));
		await fireEvent.input(modal.getByRole('textbox', { name: t('settings.name') }), { target: { value: 'office-gateway' } });
		await fillServerSettings('1.1.1.1,8.8.8.8', '0', '10');
		await fireEvent.click(modal.getByRole('button', { name: accessibleName => accessibleName === '생성' }));
		await settle();
		expect(await screen.findByText(t('project.error.unconfirmed'))).toBeTruthy();
		expect(screen.getByText('office-gateway')).toBeTruthy();
	});

	it('keeps a definite backend rejection as a hard create failure without refreshing the list', async () => {
		mocks.post.mockRejectedValue(new ApiError(422, 'DNS 형식이 올바르지 않습니다'));
		render(WaygateWorkspace);
		await screen.findByText('gateway-a');
		await fireEvent.click(screen.getByRole('button', { name: '+ Waygate 서버 생성' }));
		const modal = within(screen.getByRole('dialog', { name: 'Waygate 서버 생성' }));
		await fireEvent.input(modal.getByRole('textbox', { name: t('settings.name') }), { target: { value: 'office-gateway' } });
		await fillServerSettings('1.1.1.1,8.8.8.8', '0', '10');
		await fireEvent.click(modal.getByRole('button', { name: accessibleName => accessibleName === '생성' }));
		await settle();
		expect(await screen.findByText('DNS 형식이 올바르지 않습니다')).toBeTruthy();
		expect(screen.queryByText(t('project.error.unconfirmed'))).toBeNull();
		expect(screen.queryByText('office-gateway')).toBeNull();
	});

	it('refreshes effective inherited client values immediately after a server defaults PATCH', async () => {
		currentClients = [inheritedClient];
		mocks.patch.mockImplementation(async () => {
			currentServer = { ...currentServer, ...updatedDefaults };
			currentClients = [{ ...inheritedClient, ...updatedDefaults }];
			return currentServer;
		});
		render(WaygateWorkspace);
		await openDetail();
		expect(screen.getByText(`${defaults.dns} · 서버 기본값`)).toBeTruthy();
		await fireEvent.click(screen.getByRole('button', { name: '서버 기본값 설정' }));
		const modal = within(screen.getByRole('dialog', { name: '서버 기본값 설정' }));
		expect((modal.getByLabelText('DNS') as HTMLInputElement).value).toBe(defaults.dns);
		expect(modal.queryByLabelText('MTU', { exact: true })).toBeNull();
		expect((modal.getByLabelText(/PersistentKeepalive/, { selector: 'input' }) as HTMLInputElement).value).toBe('40');
		await fillServerSettings('1.1.1.1,8.8.8.8', '0');
		mocks.get.mockClear();
		await fireEvent.click(modal.getByRole('button', { name: '저장' }));
		await settle();
		expect(mocks.patch).toHaveBeenCalledExactlyOnceWith(`${base}/server-a`, updatedDefaults, 'token-a', 'project-a', { timeoutMs: 58_000 });
		expect(mocks.get).toHaveBeenCalledWith(`${base}/server-a/clients`, 'token-a', 'project-a', { refresh: true });
		expect(screen.queryByRole('dialog', { name: '서버 기본값 설정' })).toBeNull();
		expect(screen.getByText(`${updatedDefaults.dns} · 서버 기본값`)).toBeTruthy();
		expect(screen.getByText('자동 · 비활성화 · 서버 기본값')).toBeTruthy();
		expect(screen.queryByText(`${defaults.dns} · 서버 기본값`)).toBeNull();
		const issue = await openIssuance();
		expect(issue.getByText(updatedDefaults.dns)).toBeTruthy();
		await fireEvent.click(issue.getByRole('button', { name: accessibleName => accessibleName === '발급' }));
		await settle();
		expect(mocks.post).toHaveBeenCalledExactlyOnceWith(`${base}/server-a/clients`, inheritedRequest, 'token-a', 'project-a');
	});

	it('issues with dynamic DNS and keepalive inheritance by default and a client-only automatic MTU', async () => {
		render(WaygateWorkspace);
		await openDetail();
		const modal = await openIssuance();
		for (const field of ['DNS', 'PersistentKeepalive'] as const) {
			expect(settingMode(field).getByRole('button', { name: '서버 기본값 사용' }).getAttribute('aria-pressed')).toBe('true');
		}
		expect(modal.getByText(defaults.dns)).toBeTruthy();
		expect((modal.getByLabelText('MTU') as HTMLInputElement).value).toBe('');
		await fireEvent.click(modal.getByRole('button', { name: accessibleName => accessibleName === '발급' }));
		await settle();
		expect(mocks.post).toHaveBeenCalledExactlyOnceWith(`${base}/server-a/clients`, inheritedRequest, 'token-a', 'project-a');
	});

	it.each([
		{ field: 'DNS' as const, label: /^DNS$/, value: '', override: { dns: null } },
		{ field: 'DNS' as const, label: /^DNS$/, value: defaults.dns, override: { dns: defaults.dns } },
		{ field: 'PersistentKeepalive' as const, label: /PersistentKeepalive/, value: '0', override: { persistent_keepalive: 0 } },
	])('submits explicit $field value "$value" independently of the other inherited field', async ({ field, label, value, override }) => {
		render(WaygateWorkspace);
		await openDetail();
		const modal = await openIssuance();
		await fireEvent.click(settingMode(field).getByRole('button', { name: '직접 지정' }));
		await fireEvent.input(modal.getByLabelText(label, { selector: 'input' }), { target: { value } });
		await fireEvent.click(modal.getByRole('button', { name: accessibleName => accessibleName === '발급' }));
		await settle();
		expect(mocks.post).toHaveBeenCalledExactlyOnceWith(`${base}/server-a/clients`, { ...inheritedRequest, ...override }, 'token-a', 'project-a');
	});

	it('drops old explicit values when an issuance draft switches back to inheritance while preserving client MTU', async () => {
		render(WaygateWorkspace);
		await openDetail();
		const modal = await openIssuance();
		for (const field of ['DNS', 'PersistentKeepalive'] as const) {
			await fireEvent.click(settingMode(field).getByRole('button', { name: '직접 지정' }));
		}
		await fireEvent.input(modal.getByLabelText('DNS', { exact: true }), { target: { value: '4.4.4.4' } });
		await fireEvent.input(modal.getByLabelText(/PersistentKeepalive/, { selector: 'input' }), { target: { value: '17' } });
		await fireEvent.input(modal.getByLabelText('MTU'), { target: { value: '1280' } });
		for (const field of ['DNS', 'PersistentKeepalive'] as const) {
			await fireEvent.click(settingMode(field).getByRole('button', { name: '서버 기본값 사용' }));
		}
		await fireEvent.click(modal.getByRole('button', { name: accessibleName => accessibleName === '발급' }));
		await settle();
		expect(mocks.post).toHaveBeenCalledExactlyOnceWith(`${base}/server-a/clients`, { ...inheritedRequest, mtu: 1280 }, 'token-a', 'project-a');
	});

	it('treats absent legacy inheritance flags as explicit and can opt into both defaults without pinning old values', async () => {
		currentClients = [{ ...client, dns: '4.4.4.4', mtu: 1280, persistent_keepalive: 17 }];
		mocks.patch.mockResolvedValue({ ...inheritedClient, mtu: 1280 });
		render(WaygateWorkspace);
		await openDetail();
		await fireEvent.click(screen.getByRole('button', { name: 'laptop-a 설정' }));
		const modal = within(screen.getByRole('dialog', { name: 'laptop-a 설정' }));
		expect((modal.getByLabelText('DNS', { exact: true }) as HTMLInputElement).value).toBe('4.4.4.4');
		expect((modal.getByLabelText(/PersistentKeepalive/, { selector: 'input' }) as HTMLInputElement).value).toBe('17');
		for (const field of ['DNS', 'PersistentKeepalive'] as const) {
			expect(settingMode(field).getByRole('button', { name: '직접 지정' }).getAttribute('aria-pressed')).toBe('true');
			await fireEvent.click(settingMode(field).getByRole('button', { name: '서버 기본값 사용' }));
		}
		await fireEvent.click(modal.getByRole('button', { name: accessibleName => accessibleName === '저장' }));
		await settle();
		expect(mocks.patch).toHaveBeenCalledExactlyOnceWith(`${base}/server-a/clients/client-a`, {
			inherit_dns: true, inherit_persistent_keepalive: true, mtu: 1280,
		}, 'token-a', 'project-a');
		expect(screen.queryByRole('dialog', { name: 'laptop-a 설정' })).toBeNull();
	});

	it('updates an open inherited draft when server defaults refresh without submitting copied values', async () => {
		render(WaygateWorkspace);
		await openDetail();
		const modal = await openIssuance();
		currentServer = { ...currentServer, ...updatedDefaults };
		for (const refresh of mocks.refresh) await refresh();
		await settle();
		expect(modal.getByText(updatedDefaults.dns)).toBeTruthy();
		expect(modal.queryByText(defaults.dns)).toBeNull();
		await fireEvent.click(modal.getByRole('button', { name: accessibleName => accessibleName === '발급' }));
		await settle();
		expect(mocks.post).toHaveBeenCalledExactlyOnceWith(`${base}/server-a/clients`, inheritedRequest, 'token-a', 'project-a');
	});

	it('preserves an unsuccessful defaults edit for retry and only refreshes clients after a successful PATCH', async () => {
		currentClients = [inheritedClient];
		mocks.patch.mockRejectedValueOnce(new ApiError(422, 'defaults rejected')).mockImplementationOnce(async () => {
			currentClients = [{ ...inheritedClient, ...updatedDefaults }];
			return { ...currentServer, ...updatedDefaults };
		});
		render(WaygateWorkspace);
		await openDetail();
		await fireEvent.click(screen.getByRole('button', { name: '서버 기본값 설정' }));
		const modal = within(screen.getByRole('dialog', { name: '서버 기본값 설정' }));
		await fillServerSettings(updatedDefaults.dns, '0');
		mocks.get.mockClear();
		await fireEvent.click(modal.getByRole('button', { name: '저장' }));
		await settle();
		expect(modal.getByText('defaults rejected')).toBeTruthy();
		expect((modal.getByLabelText('DNS') as HTMLInputElement).value).toBe(updatedDefaults.dns);
		expect(screen.getByText(`${defaults.dns} · 서버 기본값`)).toBeTruthy();
		expect(mocks.get).not.toHaveBeenCalled();
		expect(mocks.toastSuccess).not.toHaveBeenCalled();
		await fireEvent.click(modal.getByRole('button', { name: '저장' }));
		await settle();
		expect(screen.queryByRole('dialog', { name: '서버 기본값 설정' })).toBeNull();
		expect(screen.getByText(`${updatedDefaults.dns} · 서버 기본값`)).toBeTruthy();
		expect(mocks.patch).toHaveBeenCalledTimes(2);
		expect(mocks.get).toHaveBeenCalledWith(`${base}/server-a/clients`, 'token-a', 'project-a', { refresh: true });
	});

	it.each(['success', 'failure'])('discards a defaults PATCH %s after changing project', async (outcome) => {
		const saving = deferred<unknown>();
		mocks.patch.mockReturnValue(saving.promise);
		render(WaygateWorkspace);
		await openDetail();
		await fireEvent.click(screen.getByRole('button', { name: '서버 기본값 설정' }));
		await fireEvent.click(within(screen.getByRole('dialog', { name: '서버 기본값 설정' })).getByRole('button', { name: '저장' }));
		expect(mocks.patch).toHaveBeenCalledWith(`${base}/server-a`, defaults, 'token-a', 'project-a', { timeoutMs: 58_000 });
		switchProject('project-b');
		await screen.findByText('gateway-b');
		mocks.get.mockClear();
		if (outcome === 'success') saving.resolve({ ...currentServer, ...updatedDefaults });
		else saving.reject(new ApiError(500, 'old defaults failure'));
		await settle();
		expect(screen.getByText('gateway-b')).toBeTruthy();
		expect(screen.queryByText('gateway-a')).toBeNull();
		expect(screen.queryByText('old defaults failure')).toBeNull();
		expect(mocks.toastSuccess).not.toHaveBeenCalled();
		expect(mocks.toastError).not.toHaveBeenCalled();
		expect(mocks.get).not.toHaveBeenCalled();
	});

	it('does not let a list request started before saving overwrite the successful defaults PATCH', async () => {
		const oldList = deferred<unknown[]>();
		mocks.patch.mockResolvedValue({ ...currentServer, ...updatedDefaults });
		render(WaygateWorkspace);
		await openDetail();
		mocks.get.mockImplementation((path: string) => {
			if (path === base) return oldList.promise;
			if (path === `${base}/server-a`) return Promise.resolve(currentServer);
			if (path.endsWith('/clients')) return Promise.resolve([client]);
			if (path === '/api/v1/networks' || path.endsWith('/networks')) return Promise.resolve([]);
			throw new Error(`Unexpected GET ${path}`);
		});
		const refreshes = mocks.refresh.map((refresh) => refresh());
		await fireEvent.click(screen.getByRole('button', { name: '서버 기본값 설정' }));
		await fillServerSettings(updatedDefaults.dns, '0');
		await fireEvent.click(within(screen.getByRole('dialog', { name: '서버 기본값 설정' })).getByRole('button', { name: '저장' }));
		await settle();
		oldList.resolve([currentServer]);
		await Promise.all(refreshes);
		await settle();
		const issue = await openIssuance();
		expect(issue.getByText(updatedDefaults.dns)).toBeTruthy();
		expect(issue.queryByText(defaults.dns)).toBeNull();
		await fireEvent.click(issue.getByRole('button', { name: accessibleName => accessibleName === '발급' }));
		await settle();
		expect(mocks.post).toHaveBeenCalledExactlyOnceWith(`${base}/server-a/clients`, inheritedRequest, 'token-a', 'project-a');
	});
});

describe('Waygate effective service capabilities', () => {
	it.each(['member', 'project_owner', 'project_admin', 'waygate_admin'])('does not infer grants from the %s display role or admin presentation', async (role) => {
		grant(); // Also represents pending/failed permission resolution.
		auth.update((value) => ({ ...value, roles: [role], isSystemAdmin: true }));
		render(WaygateWorkspace, { admin: true });
		await openDetail();
		for (const name of ['+ Waygate 서버 생성', '서버 기본값 설정', '서버 삭제', '+ 클라이언트 발급', 'laptop-a 설정', 'laptop-a 삭제', 'laptop-a 비활성화', 'laptop-a .conf 다운로드', 'laptop-a QR', '+ 네트워크 연결', '설정 내보내기', '가져오기']) {
			expect(screen.queryByRole('button', { name })).toBeNull();
		}
		expect(screen.queryByRole('checkbox', { name: 'gateway-a 선택' })).toBeNull();
		expect(mocks.post).not.toHaveBeenCalled();
		expect(mocks.patch).not.toHaveBeenCalled();
		expect(mocks.delete).not.toHaveBeenCalled();
		expect(mocks.downloadBlob).not.toHaveBeenCalled();
	});

	it.each([
		{ owner: 'user-a', enabled: true, allowed: true },
		{ owner: 'user-b', enabled: true, allowed: false },
		{ owner: null, enabled: true, allowed: false },
		{ owner: undefined, enabled: true, allowed: false },
		{ owner: '', enabled: true, allowed: false },
		{ owner: 'user-a', enabled: false, allowed: false },
	])('connect-only profile access: owner=$owner enabled=$enabled', async ({ owner, enabled, allowed }) => {
		grant('waygate-connect_user');
		const get = mocks.get.getMockImplementation()!;
		mocks.get.mockImplementation((path: string, ...args: unknown[]) => path.endsWith('/clients')
			? Promise.resolve([{ ...client, owner_user_id: owner, enabled }]) : get(path, ...args));
		const blob = new Blob(['owned-profile']);
		mocks.downloadBlob.mockResolvedValue({ blob, filename: 'owned.conf' });
		render(WaygateWorkspace);
		await openDetail();
		expect(!!screen.queryByRole('button', { name: 'laptop-a .conf 다운로드' })).toBe(allowed);
		expect(!!screen.queryByRole('button', { name: 'laptop-a QR' })).toBe(allowed);
		expect(screen.queryByRole('button', { name: 'laptop-a 설정' })).toBeNull();
		if (allowed) {
			await fireEvent.click(screen.getByRole('button', { name: 'laptop-a .conf 다운로드' }));
			await settle();
			expect(mocks.downloadBlob).toHaveBeenCalledExactlyOnceWith(`${base}/server-a/clients/client-a/config`, 'token-a', 'project-a');
			expect(mocks.download).toHaveBeenCalledExactlyOnceWith(blob, 'owned.conf');
		} else {
			expect(mocks.downloadBlob).not.toHaveBeenCalled();
		}
	});

	it('does not treat a matching owner as a grant without connect capability', async () => {
		grant('waygate-inventory_reader');
		const get = mocks.get.getMockImplementation()!;
		mocks.get.mockImplementation((path: string, ...args: unknown[]) => path.endsWith('/clients')
			? Promise.resolve([{ ...client, owner_user_id: 'user-a' }]) : get(path, ...args));
		render(WaygateWorkspace);
		await openDetail();
		expect(screen.queryByRole('button', { name: 'laptop-a .conf 다운로드' })).toBeNull();
		expect(screen.queryByRole('button', { name: 'laptop-a QR' })).toBeNull();
	});

	it('lets a client editor assign a legacy owner without downloading its profile', async () => {
		grant('waygate-clients_editor', 'waygate-connect_user');
		const get = mocks.get.getMockImplementation()!;
		mocks.get.mockImplementation((path: string, ...args: unknown[]) => path.endsWith('/clients')
			? Promise.resolve([{ ...client, owner_user_id: null }]) : get(path, ...args));
		mocks.patch.mockResolvedValue({ ...client, owner_user_id: 'user-b' });
		render(WaygateWorkspace);
		await openDetail();
		expect(screen.getByRole('button', { name: '+ 클라이언트 발급' })).toBeTruthy();
		expect(screen.queryByRole('button', { name: 'laptop-a .conf 다운로드' })).toBeNull();
		expect(screen.queryByRole('button', { name: 'laptop-a QR' })).toBeNull();
		for (const name of ['+ Waygate 서버 생성', '서버 기본값 설정', '서버 삭제', 'laptop-a 삭제', 'laptop-a 비활성화', '+ 네트워크 연결', '설정 내보내기']) {
			expect(screen.queryByRole('button', { name })).toBeNull();
		}
		const title = t('project.client.namedSettings', { name: client.name });
		await fireEvent.click(screen.getByRole('button', { name: title }));
		const modal = within(screen.getByRole('dialog', { name: title }));
		expect((modal.getByLabelText('MTU') as HTMLInputElement).value).toBe('');
		await fireEvent.input(modal.getByRole('textbox', { name: t('project.client.owner') }), { target: { value: 'user-b' } });
		await fireEvent.click(modal.getByRole('button', { name: t('project.actions.save') }));
		await settle();
		expect(mocks.patch).toHaveBeenCalledExactlyOnceWith(`${base}/server-a/clients/client-a`, {
			inherit_dns: false, dns: null, inherit_persistent_keepalive: false,
			persistent_keepalive: 0, mtu: null, owner_user_id: 'user-b',
		}, 'token-a', 'project-a');
		expect(screen.queryByRole('dialog', { name: title })).toBeNull();
		expect(mocks.downloadBlob).not.toHaveBeenCalled();
		expect(mocks.download).not.toHaveBeenCalled();
		expect(mocks.delete).not.toHaveBeenCalled();
	});

	it('keeps gateway editing independent of client administration and gateway deletion', async () => {
		grant('waygate-gateways_editor');
		render(WaygateWorkspace);
		await openDetail();
		expect(screen.getByRole('button', { name: '+ Waygate 서버 생성' })).toBeTruthy();
		expect(screen.getByRole('button', { name: '서버 기본값 설정' })).toBeTruthy();
		for (const name of ['서버 삭제', '+ 클라이언트 발급', 'laptop-a 설정', 'laptop-a .conf 다운로드', '설정 내보내기', '+ 네트워크 연결']) {
			expect(screen.queryByRole('button', { name })).toBeNull();
		}
	});

	it.each([
		{ leaves: ['waygate-gateways_admin'], routing: false, backup: false, gatewayDelete: true, clientDelete: false },
		{ leaves: ['waygate-clients_admin'], routing: false, backup: false, gatewayDelete: false, clientDelete: true },
		{ leaves: ['waygate-routing_admin'], routing: true, backup: false, gatewayDelete: false, clientDelete: false },
		{ leaves: ['waygate-clients_admin', 'waygate-routing_admin'], routing: true, backup: true, gatewayDelete: false, clientDelete: true },
	])('keeps admin leaves independent: $leaves', async ({ leaves, routing, backup, gatewayDelete, clientDelete }) => {
		grant(...leaves);
		render(WaygateWorkspace);
		await openDetail();
		expect(!!screen.queryByRole('button', { name: '+ 네트워크 연결' })).toBe(routing);
		expect(!!screen.queryByRole('button', { name: '설정 내보내기' })).toBe(backup);
		expect(!!screen.queryByRole('button', { name: '가져오기' })).toBe(backup);
		expect(!!screen.queryByRole('button', { name: '서버 삭제' })).toBe(gatewayDelete);
		expect(!!screen.queryByRole('button', { name: 'laptop-a 삭제' })).toBe(clientDelete);
		expect(!!screen.queryByRole('button', { name: 'laptop-a 비활성화' })).toBe(clientDelete);
	});

	it('rechecks gateway deletion after confirmation when permission is revoked', async () => {
		grant('waygate-gateways_admin');
		const confirmation = deferred<boolean>();
		mocks.confirm.mockReturnValue(confirmation.promise);
		render(WaygateWorkspace);
		await screen.findByText('gateway-a');
		await fireEvent.click(screen.getByRole('button', { name: /^삭제$/ }));
		grant();
		confirmation.resolve(true);
		await settle();
		expect(mocks.delete).not.toHaveBeenCalled();
	});

	it('rechecks client revocation after confirmation when permission is revoked', async () => {
		grant('waygate-clients_admin');
		const confirmation = deferred<boolean>();
		mocks.confirm.mockReturnValue(confirmation.promise);
		render(WaygateWorkspace);
		await openDetail();
		await fireEvent.click(screen.getByRole('button', { name: 'laptop-a 삭제' }));
		grant('waygate-clients_editor');
		confirmation.resolve(true);
		await settle();
		expect(mocks.delete).not.toHaveBeenCalled();
	});

	it('removes the submit control from an open client settings modal on downgrade', async () => {
		grant('waygate-clients_editor');
		render(WaygateWorkspace);
		await openDetail();
		await fireEvent.click(screen.getByRole('button', { name: 'laptop-a 설정' }));
		grant('waygate-connect_user');
		await tick();
		const modal = within(screen.getByRole('dialog', { name: 'laptop-a 설정' }));
		expect(modal.queryByRole('button', { name: '저장' })).toBeNull();
		expect(mocks.patch).not.toHaveBeenCalled();
	});

	it('does not publish a pending profile download after capability revocation', async () => {
		grant('waygate-connect_user');
		const config = deferred<{ blob: Blob; filename: string }>();
		mocks.downloadBlob.mockReturnValue(config.promise);
		render(WaygateWorkspace);
		await openDetail();
		await fireEvent.click(screen.getByRole('button', { name: 'laptop-a .conf 다운로드' }));
		grant();
		config.resolve({ blob: new Blob(['secret']), filename: 'secret.conf' });
		await settle();
		expect(mocks.download).not.toHaveBeenCalled();
	});

	it('renders the administrator workspace controls when the server grants exact leaves', async () => {
		auth.update((value) => ({ ...value, isSystemAdmin: true }));
		render(WaygateWorkspace, { admin: true });
		await openDetail();
		expect(screen.getByRole('heading', { name: 'Waygate 관리' })).toBeTruthy();
		for (const name of ['+ Waygate 서버 생성', '서버 삭제', '+ 클라이언트 발급', 'laptop-a 삭제', '+ 네트워크 연결', '설정 내보내기']) {
			expect(screen.getByRole('button', { name })).toBeTruthy();
		}
	});

	it.each([
		{ leaf: 'waygate-clients_admin', enabled: false, action: 'laptop-a 활성화', next: true },
		{ leaf: 'waygate-clients_admin', enabled: true, action: 'laptop-a 비활성화', next: false },
	])('uses $leaf for $action', async ({ leaf, enabled, action, next }) => {
		grant(leaf);
		const get = mocks.get.getMockImplementation()!;
		mocks.get.mockImplementation((path: string, ...args: unknown[]) => path.endsWith('/clients')
			? Promise.resolve([{ ...client, enabled }]) : get(path, ...args));
		mocks.patch.mockResolvedValue({ ...client, enabled: next });
		render(WaygateWorkspace);
		await openDetail();
		await fireEvent.click(screen.getByRole('button', { name: action }));
		await settle();
		expect(mocks.patch).toHaveBeenCalledExactlyOnceWith(`${base}/server-a/clients/client-a`, { enabled: next }, 'token-a', 'project-a');
	});

	it('allows credential export only with both native credential administration leaves', async () => {
		grant('waygate-clients_admin', 'waygate-routing_admin');
		mocks.post.mockResolvedValue({ encrypted: 'fixture', export_scope: 'caller_owned_and_unassigned_profiles', excluded_assigned_client_count: 2, excluded_assigned_client_ids: ['foreign-a', 'foreign-b'] });
		render(WaygateWorkspace);
		await openDetail();
		await fireEvent.click(screen.getByRole('button', { name: '설정 내보내기' }));
		const modal = within(screen.getByRole('dialog', { name: '설정 내보내기' }));
		await fireEvent.input(modal.getByPlaceholderText('8자 이상'), { target: { value: 'fixture-passphrase' } });
		await fireEvent.click(modal.getByRole('button', { name: '내보내기' }));
		await settle();
		expect(mocks.post).toHaveBeenCalledExactlyOnceWith(`${base}/server-a/export`, { passphrase: 'fixture-passphrase' }, 'token-a', 'project-a');
		expect(mocks.download).toHaveBeenCalledWith(expect.any(Blob), 'gateway-a-waygate-export.json');
		expect(screen.getByText(/다른 사용자에게 할당된 프로필 2개가 제외되었습니다/)).toBeTruthy();
		expect(screen.getAllByText(/전체 프로젝트 백업이 아닙니다/).length).toBeGreaterThan(0);
	});

	it('uses routing authority for detach without gateway or client administration', async () => {
		grant('waygate-routing_admin');
		const get = mocks.get.getMockImplementation()!;
		mocks.get.mockImplementation((path: string, ...args: unknown[]) => path === `${base}/server-a/networks`
			? Promise.resolve([{ id: 1, network_id: 'network-a', status: 'ACTIVE', nat_mode: 'snat' }]) : get(path, ...args));
		mocks.delete.mockResolvedValue(undefined);
		render(WaygateWorkspace);
		await openDetail();
		await fireEvent.click(screen.getByRole('button', { name: '해제' }));
		await settle();
		expect(mocks.delete).toHaveBeenCalledExactlyOnceWith(`${base}/server-a/networks/1`, 'token-a', 'project-a', { timeoutMs: 58_000 });
	});

	it('uses the owned-profile endpoint for QR and clears displayed secrets on permission loss', async () => {
		grant('waygate-connect_user');
		const get = mocks.get.getMockImplementation()!;
		mocks.get.mockImplementation((path: string, ...args: unknown[]) => path.endsWith('/clients')
			? Promise.resolve([{ ...client, owner_user_id: 'user-a' }]) : get(path, ...args));
		mocks.downloadBlob.mockResolvedValue({ blob: { text: async () => 'owned-profile' }, filename: 'owned.conf' });
		mocks.qr.mockResolvedValue('data:image/png;base64,fixture');
		render(WaygateWorkspace);
		await openDetail();
		await fireEvent.click(screen.getByRole('button', { name: 'laptop-a QR' }));
		await screen.findByAltText('WireGuard 설정 QR 코드');
		expect(mocks.downloadBlob).toHaveBeenCalledExactlyOnceWith(`${base}/server-a/clients/client-a/config`, 'token-a', 'project-a');
		expect(mocks.qr).toHaveBeenCalledWith('owned-profile', expect.any(Object));
		grant();
		await settle();
		expect(screen.queryByAltText('WireGuard 설정 QR 코드')).toBeNull();
	});

	it('discards a pending own-profile download after the polled owner changes', async () => {
		grant('waygate-connect_user');
		let owner = 'user-a';
		const get = mocks.get.getMockImplementation()!;
		mocks.get.mockImplementation((path: string, ...args: unknown[]) => path.endsWith('/clients')
			? Promise.resolve([{ ...client, owner_user_id: owner }]) : get(path, ...args));
		const config = deferred<{ blob: Blob; filename: string }>();
		mocks.downloadBlob.mockReturnValue(config.promise);
		render(WaygateWorkspace);
		await openDetail();
		await fireEvent.click(screen.getByRole('button', { name: 'laptop-a .conf 다운로드' }));
		owner = 'user-b';
		for (const refresh of mocks.refresh) await refresh();
		config.resolve({ blob: new Blob(['secret']), filename: 'secret.conf' });
		await settle();
		expect(mocks.download).not.toHaveBeenCalled();
		expect(screen.queryByRole('button', { name: 'laptop-a .conf 다운로드' })).toBeNull();
	});
});

describe('Waygate client admin leaf without editor', () => {
	it.each([true, false])('allows revocation toggles but not editing or another owner’s secrets (enabled=%s)', async (enabled) => {
		grant('waygate-clients_admin', 'waygate-connect_user');
		const get = mocks.get.getMockImplementation()!;
		mocks.get.mockImplementation((path: string, ...args: unknown[]) => path.endsWith('/clients')
			? Promise.resolve([{ ...client, enabled, owner_user_id: 'user-b' }]) : get(path, ...args));
		render(WaygateWorkspace);
		await openDetail();
		expect(screen.queryByRole('button', { name: '+ 클라이언트 발급' })).toBeNull();
		expect(screen.queryByRole('button', { name: 'laptop-a 설정' })).toBeNull();
		expect(!!screen.queryByRole('button', { name: 'laptop-a 활성화' })).toBe(!enabled);
		expect(screen.queryByRole('button', { name: 'laptop-a .conf 다운로드' })).toBeNull();
		expect(screen.queryByRole('button', { name: 'laptop-a QR' })).toBeNull();
		expect(screen.getByRole('button', { name: 'laptop-a 삭제' })).toBeTruthy();
		expect(!!screen.queryByRole('button', { name: 'laptop-a 비활성화' })).toBe(enabled);
	});
});

describe('Waygate final native profile ownership contract', () => {
	it.each(['waygate-clients_editor', 'waygate-clients_admin'])('does not let %s bypass ownership even with connect permission', async (leaf) => {
		grant(leaf, 'waygate-connect_user');
		const get = mocks.get.getMockImplementation()!;
		mocks.get.mockImplementation((path: string, ...args: unknown[]) => path.endsWith('/clients')
			? Promise.resolve([
				{ ...client, owner_user_id: 'user-b' },
				{ ...client, id: 'legacy', name: 'legacy', owner_user_id: null },
				{ ...client, id: 'disabled', name: 'disabled', enabled: false },
			]) : get(path, ...args));
		render(WaygateWorkspace);
		await openDetail();
		for (const name of ['laptop-a', 'legacy', 'disabled']) {
			expect(screen.queryByRole('button', { name: `${name} .conf 다운로드` })).toBeNull();
			expect(screen.queryByRole('button', { name: `${name} QR` })).toBeNull();
		}
		// Only the client editing leaf may register the caller on an unassigned profile; another owner is never claimable.
		const claimable = leaf === 'waygate-clients_editor';
		expect(!!screen.queryByRole('button', { name: t('project.client.claimDownload', { name: 'legacy' }) })).toBe(claimable);
		expect(!!screen.queryByRole('button', { name: t('project.client.claimQr', { name: 'legacy' }) })).toBe(claimable);
		expect(!!screen.queryByRole('button', { name: t('project.client.claimNamed', { name: 'legacy' }) })).toBe(claimable);
		for (const name of ['laptop-a', 'disabled']) {
			expect(screen.queryByRole('button', { name: t('project.client.claimDownload', { name }) })).toBeNull();
			expect(screen.queryByRole('button', { name: t('project.client.claimNamed', { name }) })).toBeNull();
		}
		expect(mocks.downloadBlob).not.toHaveBeenCalled();
		expect(mocks.patch).not.toHaveBeenCalled();
	});

	it.each([true, false])('never gives an editor an enabled toggle (enabled=%s)', async (enabled) => {
		grant('waygate-clients_editor');
		const get = mocks.get.getMockImplementation()!;
		mocks.get.mockImplementation((path: string, ...args: unknown[]) => path.endsWith('/clients')
			? Promise.resolve([{ ...client, enabled }]) : get(path, ...args));
		render(WaygateWorkspace);
		await openDetail();
		expect(screen.queryByRole('button', { name: 'laptop-a 활성화' })).toBeNull();
		expect(screen.queryByRole('button', { name: 'laptop-a 비활성화' })).toBeNull();
		expect(screen.queryByRole('button', { name: 'laptop-a .conf 다운로드' })).toBeNull();
		expect(mocks.patch).not.toHaveBeenCalled();
	});

	it('makes a known owner immutable and omits ownership from ordinary settings updates', async () => {
		grant('waygate-clients_editor');
		mocks.patch.mockResolvedValue({ ...client, dns: '9.9.9.9' });
		render(WaygateWorkspace);
		await openDetail();
		const title = t('project.client.namedSettings', { name: client.name });
		await fireEvent.click(screen.getByRole('button', { name: title }));
		const modal = within(screen.getByRole('dialog', { name: title }));
		const owner = modal.getByRole('textbox', { name: t('project.client.owner') }) as HTMLInputElement;
		expect(owner.value).toBe('user-a');
		expect(owner.disabled).toBe(true);
		expect(modal.queryByRole('button', { name: t('project.client.assignSelf') })).toBeNull();
		expect((modal.getByLabelText('MTU') as HTMLInputElement).value).toBe('');
		await fireEvent.input(modal.getByRole('textbox', { name: 'DNS' }), { target: { value: '9.9.9.9' } });
		await fireEvent.click(modal.getByRole('button', { name: t('project.actions.save') }));
		await settle();
		expect(mocks.patch).toHaveBeenCalledExactlyOnceWith(`${base}/server-a/clients/client-a`, {
			inherit_dns: false, dns: '9.9.9.9', inherit_persistent_keepalive: false,
			persistent_keepalive: 0, mtu: null,
		}, 'token-a', 'project-a');
		expect(mocks.patch.mock.calls[0][1]).not.toHaveProperty('owner_user_id');
		expect(screen.queryByRole('dialog', { name: title })).toBeNull();
	});

	it.each([
		{ owner: 'user-b', conf: null, download: false },
		{ owner: 'user-a', conf: null, download: false },
		{ owner: 'user-a', conf: 'owned-profile', download: true },
	])('handles issuance owner=$owner plaintext=$conf without fabricating a download', async ({ owner, conf, download }) => {
		mocks.post.mockResolvedValue({
			...client, name: 'new-laptop', owner_user_id: owner, tunnel_conf: conf,
			persistent_keepalive: 25, psk_enabled: true,
			inherit_dns: true, inherit_persistent_keepalive: true,
		});
		render(WaygateWorkspace);
		await openDetail();
		await fireEvent.click(screen.getByRole('button', { name: t('project.actions.issueClient') }));
		const title = t('project.client.issueTitle');
		const modal = within(screen.getByRole('dialog', { name: title }));
		await fireEvent.input(modal.getByRole('textbox', { name: t('settings.name') }), { target: { value: 'new-laptop' } });
		await fireEvent.input(modal.getByRole('textbox', { name: t('project.client.owner') }), { target: { value: owner } });
		await fireEvent.click(modal.getByRole('button', { name: t('project.actions.issue') }));
		await settle();
		expect(mocks.post).toHaveBeenCalledExactlyOnceWith(`${base}/server-a/clients`, { name: 'new-laptop', mtu: null, owner_user_id: owner }, 'token-a', 'project-a');
		expect(mocks.download).toHaveBeenCalledTimes(download ? 1 : 0);
		expect(mocks.downloadBlob).not.toHaveBeenCalled();
		if (download) {
			expect(mocks.download).toHaveBeenCalledWith(expect.any(Blob), 'new-laptop.conf');
			const plaintext = await new Promise<string>((resolve, reject) => {
				const reader = new FileReader();
				reader.onload = () => resolve(String(reader.result));
				reader.onerror = () => reject(reader.error);
				reader.readAsText(mocks.download.mock.calls[0][0] as Blob);
			});
			expect(plaintext).toBe(conf);
			expect(mocks.toastSuccess).toHaveBeenCalledWith(t('project.toast.clientIssued'));
		} else {
			expect(mocks.toastSuccess).toHaveBeenCalledWith(t('project.toast.clientIssuedNoProfile'));
		}
		expect(screen.queryByRole('dialog', { name: title })).toBeNull();
	});
});

describe('Waygate optional owner and self registration', () => {
	let currentClients: Array<Omit<typeof client, 'owner_user_id'> & { owner_user_id: string | null }>;

	beforeEach(() => {
		grant('waygate-clients_editor', 'waygate-connect_user');
		currentClients = [{ ...client, owner_user_id: null }];
		const get = mocks.get.getMockImplementation()!;
		mocks.get.mockImplementation((path: string, ...args: unknown[]) => path.endsWith('/clients')
			? Promise.resolve(currentClients) : get(path, ...args));
		mocks.patch.mockImplementation(async (_path: string, body: { owner_user_id: string }) => {
			currentClients = [{ ...client, owner_user_id: body.owner_user_id }];
			return currentClients[0];
		});
		mocks.downloadBlob.mockResolvedValue({ blob: new Blob(['owned-profile']), filename: 'laptop-a.conf' });
	});

	it('issues without a prefilled owner while keeping an explicit assign-to-me action', async () => {
		render(WaygateWorkspace);
		await openDetail();
		await fireEvent.click(screen.getByRole('button', { name: t('project.actions.issueClient') }));
		const modal = within(screen.getByRole('dialog', { name: t('project.client.issueTitle') }));
		const owner = modal.getByRole('textbox', { name: t('project.client.owner') }) as HTMLInputElement;
		expect(owner.value).toBe('');
		expect(modal.getByText(t('project.client.ownerIssueHelp'))).toBeTruthy();
		await fireEvent.click(modal.getByRole('button', { name: t('project.client.assignSelf') }));
		expect(owner.value).toBe('user-a');
	});

	it('shows the unassigned state and registers the caller with the existing owner PATCH', async () => {
		render(WaygateWorkspace);
		await openDetail();
		expect(screen.getByText(t('project.client.ownerUnassigned'), { selector: 'span' })).toBeTruthy();
		await fireEvent.click(screen.getByRole('button', { name: t('project.client.claimNamed', { name: 'laptop-a' }) }));
		await settle();
		expect(mocks.patch).toHaveBeenCalledExactlyOnceWith(`${base}/server-a/clients/client-a`, { owner_user_id: 'user-a' }, 'token-a', 'project-a');
		expect(mocks.toastSuccess).toHaveBeenCalledWith(t('project.toast.clientClaimed', { name: 'laptop-a' }));
		expect(await screen.findByRole('button', { name: 'laptop-a .conf 다운로드' })).toBeTruthy();
		expect(screen.queryByRole('button', { name: t('project.client.claimNamed', { name: 'laptop-a' }) })).toBeNull();
		expect(mocks.downloadBlob).not.toHaveBeenCalled();
	});

	it('claims an unassigned profile before downloading its config', async () => {
		render(WaygateWorkspace);
		await openDetail();
		await fireEvent.click(screen.getByRole('button', { name: t('project.client.claimDownload', { name: 'laptop-a' }) }));
		await settle();
		expect(mocks.patch).toHaveBeenCalledExactlyOnceWith(`${base}/server-a/clients/client-a`, { owner_user_id: 'user-a' }, 'token-a', 'project-a');
		expect(mocks.downloadBlob).toHaveBeenCalledExactlyOnceWith(`${base}/server-a/clients/client-a/config`, 'token-a', 'project-a');
		expect(mocks.patch.mock.invocationCallOrder[0]).toBeLessThan(mocks.downloadBlob.mock.invocationCallOrder[0]);
		expect(mocks.download).toHaveBeenCalledExactlyOnceWith(expect.any(Blob), 'laptop-a.conf');
	});

	it('claims an unassigned profile before rendering its QR code', async () => {
		mocks.qr.mockResolvedValue('data:image/png;base64,claimed');
		mocks.downloadBlob.mockResolvedValue({ blob: { text: async () => 'owned-profile' }, filename: 'laptop-a.conf' });
		render(WaygateWorkspace);
		await openDetail();
		await fireEvent.click(screen.getByRole('button', { name: t('project.client.claimQr', { name: 'laptop-a' }) }));
		const image = await screen.findByRole('img', { name: t('project.qr.alt') });
		expect(image.getAttribute('src')).toBe('data:image/png;base64,claimed');
		expect(mocks.patch).toHaveBeenCalledExactlyOnceWith(`${base}/server-a/clients/client-a`, { owner_user_id: 'user-a' }, 'token-a', 'project-a');
		expect(mocks.downloadBlob).toHaveBeenCalledExactlyOnceWith(`${base}/server-a/clients/client-a/config`, 'token-a', 'project-a');
		expect(mocks.qr).toHaveBeenCalledWith('owned-profile', expect.any(Object));
	});

	it.each([
		{ status: 409, message: () => t('project.error.claimConflict'), owner: 'user-b' },
		{ status: 403, message: () => t('project.error.claimForbidden'), owner: null },
	])('reports a $status claim failure clearly and never downloads', async ({ status, message, owner }) => {
		mocks.patch.mockImplementation(async () => {
			currentClients = [{ ...client, owner_user_id: owner }];
			throw new ApiError(status, 'native refusal');
		});
		render(WaygateWorkspace);
		await openDetail();
		await fireEvent.click(screen.getByRole('button', { name: t('project.client.claimDownload', { name: 'laptop-a' }) }));
		await settle();
		expect(mocks.toastError).toHaveBeenCalledExactlyOnceWith(message());
		expect(mocks.downloadBlob).not.toHaveBeenCalled();
		expect(mocks.download).not.toHaveBeenCalled();
		if (status === 409) {
			// The lost race refreshes to the authoritative owner, so no claim action remains.
			await vi.waitFor(() => expect(screen.getByText('user-b')).toBeTruthy());
			expect(screen.queryByRole('button', { name: t('project.client.claimDownload', { name: 'laptop-a' }) })).toBeNull();
		}
	});

	it('does not offer self registration to a connect-only user', async () => {
		grant('waygate-connect_user');
		render(WaygateWorkspace);
		await openDetail();
		expect(screen.getByText(t('project.client.ownerUnassigned'), { selector: 'span' })).toBeTruthy();
		for (const name of [t('project.client.claimNamed', { name: 'laptop-a' }), t('project.client.claimDownload', { name: 'laptop-a' }), t('project.client.claimQr', { name: 'laptop-a' })]) {
			expect(screen.queryByRole('button', { name })).toBeNull();
		}
	});
});

describe('Waygate attachment interface and routing', () => {
	const visible = [
		{ id: 'net-own', name: 'own-net', is_external: false, is_shared: false, project_id: 'project-a' },
		{ id: 'net-provider', name: 'provider-net', is_external: true, is_shared: false, project_id: 'admin-project' },
		{ id: 'net-shared', name: 'shared-net', is_external: false, is_shared: true, project_id: 'admin-project' },
	];
	const attachment = {
		id: 7, server_id: 'server-a', project_id: 'project-a', network_id: 'net-own', subnet_id: 'subnet-own', port_id: 'port-1',
		cidr: '10.20.0.0/24', nat_mode: 'snat', status: 'ACTIVE', created_at: null, updated_at: null,
	};
	let currentAttachments: Array<typeof attachment & { allowed_ips?: string[] }>;

	beforeEach(() => {
		currentAttachments = [];
		mocks.get.mockImplementation((path: string) => {
			if (path === base) return Promise.resolve([server('a')]);
			if (path === `${base}/server-a`) return Promise.resolve(server('a'));
			if (path.endsWith('/clients')) return Promise.resolve([client]);
			if (path === `${base}/server-a/networks`) return Promise.resolve(currentAttachments);
			if (path === '/api/v1/networks') return Promise.resolve(visible);
			if (path === '/api/v1/networks/net-provider') {
				return Promise.resolve({ ...visible[1], subnets: ['subnet-provider'], routers: [], subnet_details: [
					{ id: 'subnet-provider', name: 'provider-subnet', cidr: '203.0.113.0/24', ip_version: 4, gateway_ip: null, dhcp_enabled: false },
				] });
			}
			throw new Error(`Unexpected GET ${path}`);
		});
		mocks.post.mockResolvedValue({ ...attachment, network_id: 'net-provider', allowed_ips: [] });
	});

	async function openAttach() {
		render(WaygateWorkspace);
		await openDetail();
		await fireEvent.click(screen.getByRole('button', { name: t('project.actions.attachNetwork') }));
		await vi.waitFor(() => expect(mocks.get).toHaveBeenCalledWith('/api/v1/networks', 'token-a', 'project-a', { refresh: true }));
		const modal = within(screen.getByRole('dialog', { name: t('project.network.attachTitle') }));
		await fireEvent.click(modal.getByRole('button', { name: t('project.network.selectAttach') }));
		return modal;
	}

	it('offers provider/external and shared networks with their kind and keeps routing separate', async () => {
		const modal = await openAttach();
		expect((await screen.findByRole('option', { name: /own-net/ })).textContent).not.toContain(t('project.network.kindShared'));
		expect(screen.getByRole('option', { name: /provider-net/ }).textContent).toContain(t('project.network.kindExternal'));
		expect(screen.getByRole('option', { name: /shared-net/ }).textContent).toContain(t('project.network.kindShared'));
		await fireEvent.click(screen.getByRole('option', { name: /provider-net/ }));
		expect(await modal.findByText(new RegExp(t('project.network.providerNotice').replace(/[.*+?^${}()|[\]\\]/g, '\\$&')))).toBeTruthy();
		const routing = modal.getByRole('textbox', { name: t('project.network.allowedIps') }) as HTMLTextAreaElement;
		expect(routing.value).toBe('');
		await fireEvent.click(await modal.findByRole('button', { name: t('project.network.addSubnetCidr', { cidr: '203.0.113.0/24' }) }));
		expect(routing.value).toBe('203.0.113.0/24');
		await fireEvent.input(routing, { target: { value: '203.0.113.9/24, 203.0.113.0/24\nfd00::1/64' } });
		await fireEvent.click(modal.getByRole('button', { name: t('project.actions.attach') }));
		await settle();
		expect(mocks.post).toHaveBeenCalledExactlyOnceWith(`${base}/server-a/networks`, {
			network_id: 'net-provider', subnet_id: 'subnet-provider', nat_mode: 'snat', allowed_ips: ['203.0.113.0/24', 'fd00::/64'],
		}, 'token-a', 'project-a', { timeoutMs: 58_000 });
	});

	it.each([
		['0.0.0.0/0', () => t('validation.allowedIps.defaultRoute', { value: '0.0.0.0/0' })],
		['10.240.0.0/16', () => t('validation.allowedIps.tunnelOverlap', { value: '10.240.0.0/16', tunnel: '10.240.0.0/24' })],
		['10.20.0.0/33', () => t('validation.allowedIps.invalid', { value: '10.20.0.0/33' })],
	])('rejects routing entry %s client-side without attaching', async (value, message) => {
		const modal = await openAttach();
		await fireEvent.click(await screen.findByRole('option', { name: /provider-net/ }));
		await modal.findByRole('button', { name: t('project.network.addSubnetCidr', { cidr: '203.0.113.0/24' }) });
		await fireEvent.input(modal.getByRole('textbox', { name: t('project.network.allowedIps') }), { target: { value } });
		await fireEvent.click(modal.getByRole('button', { name: t('project.actions.attach') }));
		await settle();
		expect(modal.getByText(message())).toBeTruthy();
		expect(mocks.post).not.toHaveBeenCalled();
	});

	it('shows each attachment routing list and edits it through the attachment PATCH', async () => {
		currentAttachments = [{ ...attachment, allowed_ips: ['10.20.0.0/24'] }];
		mocks.patch.mockImplementation(async (_path: string, body: { allowed_ips: string[] }) => {
			currentAttachments = [{ ...attachment, allowed_ips: body.allowed_ips }];
			return currentAttachments[0];
		});
		render(WaygateWorkspace);
		await openDetail();
		// The interface CIDR and the separately stored routing entry are both shown.
		await vi.waitFor(() => expect(screen.getAllByText('10.20.0.0/24')).toHaveLength(2));
		await fireEvent.click(screen.getByRole('button', { name: t('project.network.editAllowedIps', { name: 'own-net' }) }));
		const modal = within(screen.getByRole('dialog', { name: t('project.network.editAllowedIpsTitle') }));
		const routing = modal.getByRole('textbox', { name: t('project.network.allowedIps') }) as HTMLTextAreaElement;
		expect(routing.value).toBe('10.20.0.0/24');
		await fireEvent.input(routing, { target: { value: '' } });
		await fireEvent.click(modal.getByRole('button', { name: t('project.actions.save') }));
		await settle();
		expect(mocks.patch).toHaveBeenCalledExactlyOnceWith(`${base}/server-a/networks/7`, { allowed_ips: [] }, 'token-a', 'project-a');
		expect(mocks.toastSuccess).toHaveBeenCalledWith(t('project.toast.allowedIpsSaved'));
		expect(await screen.findByText(t('project.network.allowedIpsNone'))).toBeTruthy();
	});

	it.each([
		['a legacy attachment without routing', { allowed_ips: undefined, status: 'ACTIVE' }],
		['a non-ACTIVE attachment', { allowed_ips: ['10.20.0.0/24'], status: 'BUILD' }],
	])('does not offer routing edits for %s', async (_name, override) => {
		currentAttachments = [{ ...attachment, ...override }];
		render(WaygateWorkspace);
		await openDetail();
		await screen.findByText(attachment.network_id);
		expect(screen.queryByRole('button', { name: t('project.network.editAllowedIps', { name: 'own-net' }) })).toBeNull();
	});
});
