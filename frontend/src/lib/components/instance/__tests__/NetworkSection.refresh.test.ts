import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';
import { tick } from 'svelte';
import { writable } from 'svelte/store';
import type { InstanceDetailController } from '$lib/stores/instanceDetailController.svelte';
import type { SecurityGroup } from '$lib/types/securityGroup';
import type { PortInfo } from '$lib/types/networks';
import Wrapper from './_NetworkSectionWrapper.svelte';

const { mockFetch, noMockMatch } = vi.hoisted(() => ({ mockFetch: vi.fn(), noMockMatch: Symbol('no-mock-match') }));
vi.mock('$app/environment', () => ({ browser: true }));
vi.mock('$lib/config/site', () => ({ siteConfig: writable({ runtime: { api_base: 'http://localhost:8000' } }) }));
vi.mock('$lib/stores/auth', () => ({
	auth: writable({ token: 'token', projectId: 'project', refreshToken: null, accessExpiresAt: null }),
	canWrite: writable(true),
	logoutInProgress: writable(false),
}));
vi.mock('$lib/mockup/transport', () => ({
	getActiveMockupProfile: () => null,
	maybeMockJson: async () => noMockMatch,
	maybeMockBlob: async () => noMockMatch,
	maybeMockK3sStream: () => null,
	symbolNoMatch: noMockMatch,
}));
vi.mock('$lib/utils/autoRefresh.svelte', () => ({
	createAutoRefresh: () => ({ active: false, intervalSeconds: 30, intervalOptions: [30], setBoost: vi.fn() }),
}));
vi.mock('$lib/stores/toast', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

const groups: SecurityGroup[] = [22, 443].map((port, index) => ({
	id: index ? 'web' : 'default', name: index ? 'web' : 'default', description: '',
	rules: [{
		id: `rule-${port}`, direction: 'ingress', protocol: 'tcp', ethertype: 'IPv4',
		port_range_min: port, port_range_max: port, remote_ip_prefix: '0.0.0.0/0', remote_group_id: null,
	}],
}));
const iface: PortInfo = {
	id: 'port', network_id: 'network', mac_address: 'fa:16:3e:00:00:01',
	name: null, device_owner: 'compute:nova', project_id: 'project',
	fixed_ips: [{ ip_address: '192.0.2.10' }], security_group_ids: ['web'], status: 'ACTIVE',
};
const snapshot = (ids: string[]) => ({ ports: [{ ...iface, security_group_ids: ids }], security_groups: groups });
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });
const policy = () => within(screen.getByRole('region', { name: '적용된 허용 규칙' }));

function routeRequests(getGroups: (url: URL) => Promise<Response>, saveGroups = async () => json({})) {
	mockFetch.mockImplementation((input: string, init: RequestInit) => {
		const url = new URL(input);
		if (init.method === 'POST') return saveGroups();
		if (url.pathname.endsWith('/security-groups')) return getGroups(url);
		if (url.pathname.endsWith('/interfaces')) return Promise.resolve(json([iface]));
		if (url.pathname.endsWith('/owner')) return Promise.resolve(json({ display: '' }));
		if (/\/instances\/[^/]+$/.test(url.pathname)) {
			return Promise.resolve(json({ id: url.pathname.split('/').at(-1), project_id: 'project', name: 'instance', status: 'ACTIVE', ip_addresses: [] }));
		}
		return Promise.resolve(json([]));
	});
}

async function renderDetail(id: string) {
	const source = { id, projectId: 'project' };
	let controller: InstanceDetailController | undefined;
	const view = render(Wrapper, { source, onReady: (value) => { controller = value; } });
	await fireEvent.click(await screen.findByRole('button', { name: '인바운드 허용 규칙 펼치기' }));
	return { view, source, controller: controller! };
}

beforeEach(() => {
	mockFetch.mockReset();
	vi.stubGlobal('fetch', mockFetch);
});
afterEach(() => vi.unstubAllGlobals());

describe('NetworkSection with the real request broker', () => {
	it('keeps the saved policy when a pre-save poll completes after the mutation', async () => {
		const preSave = Promise.withResolvers<Response>();
		let polling = false;
		routeRequests(async (url) => {
			if (url.searchParams.get('refresh') === 'true') return json(snapshot(['default']));
			return polling ? preSave.promise : json(snapshot(['default', 'web']));
		});
		const { controller, source } = await renderDetail('saved-instance');
		polling = true;
		await controller.fetchInstance(source.id, { silent: true });
		await controller.saveSgEdit('port', ['default']);
		preSave.resolve(json(snapshot(['default', 'web'])));
		await preSave.promise;
		await waitFor(() => expect(policy().getByRole('cell', { name: '22' })).toBeTruthy());
		await waitFor(() => expect(policy().queryByRole('cell', { name: '443' })).toBeNull());
	});

	it('preserves a visible policy during silent polling and retains a failure until recovery succeeds', async () => {
		const pending = Promise.withResolvers<Response>();
		const recovery = Promise.withResolvers<Response>();
		let getGroups = async () => json(snapshot(['web']));
		routeRequests(() => getGroups());
		const { controller, source } = await renderDetail('polling-instance');
		try {
			getGroups = () => pending.promise;
			await controller.fetchInstance(source.id, { silent: true });
			await tick();
			expect(policy().getByRole('cell', { name: '443' })).toBeTruthy();
			pending.resolve(json({ detail: 'offline' }, 503));
			await screen.findByRole('alert');
			expect(policy().queryByRole('table')).toBeNull();

			getGroups = () => recovery.promise;
			await controller.fetchInstance(source.id, { silent: true });
			await tick();
			expect(policy().getByRole('alert').textContent).toContain('offline');
			expect(policy().queryByRole('table')).toBeNull();
			recovery.resolve(json(snapshot(['default'])));
			await waitFor(() => expect(policy().getByRole('cell', { name: '22' })).toBeTruthy());
			expect(policy().queryByRole('alert')).toBeNull();
			expect(policy().queryByRole('cell', { name: '443' })).toBeNull();
		} finally {
			pending.resolve(json({ detail: 'offline' }, 503));
			recovery.resolve(json(snapshot(['default'])));
			await Promise.all([pending.promise, recovery.promise]);
		}
	});

	it('clears the previous snapshot when navigating to another instance whose group lookup fails', async () => {
		const next = Promise.withResolvers<Response>();
		routeRequests(async (url) => url.pathname.includes('/other-instance/') ? next.promise : json(snapshot(['web'])));
		const { view, controller } = await renderDetail('initial-instance');
		try {
			await view.rerender({ source: { id: 'other-instance', projectId: 'project' } });
			await waitFor(() => expect(policy().queryByRole('table')).toBeNull());
			expect(controller.allSecurityGroups).toEqual([]);
			next.resolve(json({ detail: 'other instance offline' }, 503));
			await screen.findByRole('alert');
			expect(policy().queryByRole('cell', { name: '443' })).toBeNull();
		} finally {
			next.resolve(json({ detail: 'other instance offline' }, 503));
			await next.promise;
		}
	});
});
