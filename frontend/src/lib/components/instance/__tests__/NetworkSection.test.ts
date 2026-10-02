import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';
import { writable } from 'svelte/store';
import { tick } from 'svelte';
import type { SecurityGroup, SecurityGroupRule } from '$lib/types/securityGroup';
import type { PortInfo } from '$lib/types/networks';

interface SecurityGroupSnapshot {
	ports: PortInfo[];
	security_groups: SecurityGroup[];
}

const { mockGet, mockPost } = vi.hoisted(() => ({ mockGet: vi.fn(), mockPost: vi.fn() }));
vi.mock('$lib/api/client', () => ({
	api: { get: mockGet, post: mockPost, put: vi.fn(), delete: vi.fn() },
	ApiError: class ApiError extends Error {},
}));
vi.mock('$lib/stores/auth', () => ({
	auth: writable({ token: 'token', projectId: 'project' }),
	canWrite: writable(true),
}));
vi.mock('$lib/utils/autoRefresh.svelte', () => ({
	createAutoRefresh: () => ({ active: false, intervalSeconds: 30, intervalOptions: [30], setBoost: vi.fn() }),
}));
vi.mock('$lib/stores/toast', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import Wrapper from './_NetworkSectionWrapper.svelte';

const source = { id: 'instance', projectId: 'project' };
const rule = (port: number): SecurityGroupRule => ({
	id: `rule-${port}`, direction: 'ingress', protocol: 'tcp', ethertype: 'IPv4',
	port_range_min: port, port_range_max: port, remote_ip_prefix: '0.0.0.0/0', remote_group_id: null,
});
const groups: SecurityGroup[] = [
	{ id: 'default', name: 'default', description: '', rules: [rule(22)] },
	{ id: 'web', name: 'web', description: '', rules: [rule(443)] },
	{ id: 'cached', name: 'cached', description: '', rules: [rule(12345)] },
];
const iface: PortInfo = {
	id: 'port', network_id: 'network', mac_address: 'fa:16:3e:00:00:01',
	name: null, device_owner: 'compute:nova', project_id: 'project',
	fixed_ips: [{ ip_address: '192.0.2.10' }], security_group_ids: ['cached'], status: 'ACTIVE',
};
const ancillary = (path: string): unknown => {
	if (path.endsWith('/interfaces')) return [iface];
	if (path.endsWith('/owner')) return { display: '' };
	if (path === '/api/v1/instances/instance') return { id: 'instance', name: 'instance', status: 'ACTIVE', ip_addresses: [] };
	return [];
};
const snapshot = (ids: string[]): SecurityGroupSnapshot => ({ ports: [{ ...iface, security_group_ids: ids }], security_groups: groups });
const policy = () => within(screen.getByRole('region', { name: '적용된 허용 규칙' }));

beforeEach(() => { mockGet.mockReset(); mockPost.mockReset(); });

describe('NetworkSection saved security policies', () => {
	it('uses the security-group snapshot over cached interface IDs and changes allowances only after save', async () => {
		let savedIds = ['default', 'web'];
		mockGet.mockImplementation((path: string) => Promise.resolve(path.endsWith('/security-groups') ? snapshot(savedIds) : ancillary(path)));
		mockPost.mockImplementation(async () => { savedIds = ['default']; });
		render(Wrapper, { source });
		await fireEvent.click(await screen.findByRole('button', { name: '인바운드 허용 규칙 펼치기' }));
		expect(policy().getByRole('cell', { name: '443' })).toBeTruthy();
		expect(policy().queryByRole('cell', { name: '12345' })).toBeNull();

		await fireEvent.click(screen.getByRole('button', { name: '편집' }));
		await fireEvent.click(screen.getByRole('checkbox', { name: /^web/ }));
		expect(policy().getByRole('cell', { name: '443' })).toBeTruthy();
		await fireEvent.click(screen.getByRole('button', { name: '취소' }));
		expect(policy().getByRole('cell', { name: '443' })).toBeTruthy();

		await fireEvent.click(screen.getByRole('button', { name: '편집' }));
		await fireEvent.click(screen.getByRole('checkbox', { name: /^web/ }));
		await fireEvent.click(screen.getByRole('button', { name: '저장' }));
		await waitFor(() => expect(policy().queryByRole('cell', { name: '443' })).toBeNull());
		await waitFor(() => expect(policy().getByRole('cell', { name: '22' })).toBeTruthy());
		expect(policy().queryByRole('cell', { name: '12345' })).toBeNull();
	});

	it('does not present a failed refresh as empty rules or keep previous allowances visible', async () => {
		let failed = false;
		mockGet.mockImplementation((path: string) => {
			if (path.endsWith('/security-groups')) return failed ? Promise.reject(new Error('offline')) : Promise.resolve(snapshot(['web']));
			return Promise.resolve(ancillary(path));
		});
		const view = render(Wrapper, { source });
		await fireEvent.click(await screen.findByRole('button', { name: '인바운드 허용 규칙 펼치기' }));
		expect(policy().getByRole('cell', { name: '443' })).toBeTruthy();
		failed = true;
		await view.rerender({ source: { ...source } });
		await waitFor(() => expect(policy().getByRole('alert')).toBeTruthy());
		expect(policy().queryByRole('table')).toBeNull();
		expect(screen.getByRole('button', { name: '편집' }).hasAttribute('disabled')).toBe(true);
		failed = false;
		await view.rerender({ source: { ...source } });
		await waitFor(() => expect(policy().getByRole('cell', { name: '443' })).toBeTruthy());
		expect(policy().queryByRole('alert')).toBeNull();
	});

	it('ignores an earlier security-group failure after a newer snapshot succeeds', async () => {
		const earlier = Promise.withResolvers<SecurityGroupSnapshot>();
		let first = true;
		mockGet.mockImplementation((path: string) => {
			if (path.endsWith('/security-groups')) {
				if (first) { first = false; return earlier.promise; }
				return Promise.resolve(snapshot(['default']));
			}
			return Promise.resolve(ancillary(path));
		});
		const view = render(Wrapper, { source });
		await screen.findByRole('region', { name: '적용된 허용 규칙' });
		expect(policy().queryByRole('table')).toBeNull();
		await view.rerender({ source: { ...source } });
		await fireEvent.click(await screen.findByRole('button', { name: '인바운드 허용 규칙 펼치기' }));
		await waitFor(() => expect(policy().getByRole('cell', { name: '22' })).toBeTruthy());
		earlier.reject(new Error('old request failure'));
		await Promise.allSettled([earlier.promise]);
		await tick();
		await waitFor(() => expect(policy().queryByRole('alert')).toBeNull());
		expect(policy().getByRole('cell', { name: '22' })).toBeTruthy();
		expect(policy().queryByRole('cell', { name: '443' })).toBeNull();
	});

	it('keeps each interface disclosure attached to its port when polling changes interface order', async () => {
		const firstPort = { ...iface, security_group_ids: ['default'] };
		const secondPort = { ...iface, id: 'second-port', security_group_ids: ['web'] };
		let ports = [firstPort, secondPort];
		mockGet.mockImplementation((path: string) => Promise.resolve(
			path.endsWith('/security-groups') ? { ports, security_groups: groups }
				: path.endsWith('/interfaces') ? ports : ancillary(path)
		));
		const view = render(Wrapper, { source });
		await waitFor(() => expect(screen.getAllByRole('button', { name: '인바운드 허용 규칙 펼치기' })).toHaveLength(2));
		await fireEvent.click(within(screen.getAllByRole('region', { name: '적용된 허용 규칙' })[0]).getByRole('button', { name: '인바운드 허용 규칙 펼치기' }));
		ports = [secondPort, firstPort];
		await view.rerender({ source: { ...source } });
		await waitFor(() => expect(screen.getByRole('cell', { name: '22' })).toBeTruthy());
		const regions = screen.getAllByRole('region', { name: '적용된 허용 규칙' });
		expect(within(regions[0]).queryByRole('table')).toBeNull();
		expect(within(regions[0]).getByRole('button', { name: '인바운드 허용 규칙 펼치기' }).getAttribute('aria-expanded')).toBe('false');
		expect(within(regions[1]).getByRole('cell', { name: '22' })).toBeTruthy();
		expect(within(regions[1]).queryByRole('cell', { name: '443' })).toBeNull();
	});
});
