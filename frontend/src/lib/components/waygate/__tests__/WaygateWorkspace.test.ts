import { setImmediate as nextTurn } from 'node:timers/promises';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, within } from '@testing-library/svelte';
import { tick } from 'svelte';
import { writable } from 'svelte/store';

const mocks = vi.hoisted(() => ({
	get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn(), downloadBlob: vi.fn(),
	confirm: vi.fn(), toastSuccess: vi.fn(), toastError: vi.fn(), download: vi.fn(),
	refresh: [] as (() => unknown)[],
}));
vi.mock('$lib/api/client', () => ({
	api: { get: mocks.get, post: mocks.post, patch: mocks.patch, delete: mocks.delete, downloadBlob: mocks.downloadBlob },
	ApiError: class ApiError extends Error {
		constructor(public status: number, message: string) { super(message); }
	},
}));
vi.mock('$lib/stores/auth', () => ({ auth: writable({ token: 'token-a', projectId: 'project-a' }) }));
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
import { ApiError } from '$lib/api/client';
import WaygateWorkspace from '../WaygateWorkspace.svelte';

const base = '/api/v1/waygate/servers';
const server = (project: string) => ({
	id: `server-${project}`, project_id: `project-${project}`, name: `gateway-${project}`,
	status: 'ACTIVE', tunnel_cidr: '10.240.0.0/24', listen_port: 51820,
	created_at: '2026-09-20T00:00:00Z',
});
const client = {
	id: 'client-a', name: 'laptop-a', enabled: true, online: false,
	tunnel_ip: '10.240.0.2', rx_bytes: 100, tx_bytes: 200,
	last_reported_at: '2026-09-20T00:00:00Z',
	last_handshake_at: null, created_at: '2026-09-20T00:00:00Z',
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
async function settle() {
	// Drain the API adapter's promise chain before asserting absence of stale effects.
	await nextTurn();
	await tick();
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
	if (originalAnimate) Object.defineProperty(Element.prototype, 'animate', originalAnimate);
	else Reflect.deleteProperty(Element.prototype, 'animate');
});

describe('Waygate workspace project isolation', () => {
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
	const inheritedRequest = { name: 'new-laptop', inherit_dns: true, inherit_persistent_keepalive: true, mtu: null };
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
		mocks.post.mockResolvedValue({ ...inheritedClient, name: 'new-laptop', tunnel_conf: '[Interface]\nPrivateKey = test-key' });
	});

	async function openIssuance() {
		await fireEvent.click(screen.getByRole('button', { name: '+ 클라이언트 발급' }));
		const modal = within(screen.getByRole('dialog', { name: 'Waygate 클라이언트 발급' }));
		await fireEvent.input(modal.getByLabelText('이름', { exact: false }), { target: { value: 'new-laptop' } });
		return modal;
	}

	function settingMode(field: 'DNS' | 'PersistentKeepalive') {
		return within(screen.getByRole('group', { name: accessibleName => accessibleName === `${field} 설정 방식` }));
	}

	async function fillServerSettings(dns: string, keepalive: string) {
		await fireEvent.input(screen.getByLabelText('DNS', { exact: true }), { target: { value: dns } });
		await fireEvent.input(screen.getByLabelText(/PersistentKeepalive/, { selector: 'input' }), { target: { value: keepalive } });
	}

	it('creates a named server with DNS and disabled keepalive but no server MTU', async () => {
		mocks.post.mockImplementation(async (_path: string, body: typeof currentServer) => {
			currentServer = { ...currentServer, ...body };
			return currentServer;
		});
		render(WaygateWorkspace);
		await screen.findByText('gateway-a');
		await fireEvent.click(screen.getByRole('button', { name: '+ Waygate 서버 생성' }));
		const modal = within(screen.getByRole('dialog', { name: 'Waygate 서버 생성' }));
		await fireEvent.input(modal.getByLabelText('이름', { exact: true }), { target: { value: 'office-gateway' } });
		expect(modal.queryByLabelText('MTU', { exact: true })).toBeNull();
		await fillServerSettings('1.1.1.1,8.8.8.8', '0');
		await fireEvent.click(modal.getByRole('button', { name: accessibleName => accessibleName === '생성' }));
		await settle();
		expect(mocks.post).toHaveBeenCalledExactlyOnceWith(base, { name: 'office-gateway', ...updatedDefaults }, 'token-a', 'project-a');
		expect(screen.getByText('office-gateway')).toBeTruthy();
		expect(screen.queryByRole('dialog', { name: 'Waygate 서버 생성' })).toBeNull();
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
		expect(mocks.patch).toHaveBeenCalledExactlyOnceWith(`${base}/server-a`, updatedDefaults, 'token-a', 'project-a');
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
		{ field: 'DNS' as const, label: /^DNS$/, value: '', override: { inherit_dns: false, dns: null } },
		{ field: 'DNS' as const, label: /^DNS$/, value: defaults.dns, override: { inherit_dns: false, dns: defaults.dns } },
		{ field: 'PersistentKeepalive' as const, label: /PersistentKeepalive/, value: '0', override: { inherit_persistent_keepalive: false, persistent_keepalive: 0 } },
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
		expect(mocks.patch).toHaveBeenCalledWith(`${base}/server-a`, defaults, 'token-a', 'project-a');
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
