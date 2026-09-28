import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, within } from '@testing-library/svelte';
import { writable } from 'svelte/store';
import type { SecurityGroup } from '$lib/types/securityGroup';

const mocks = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), delete: vi.fn() }));
vi.mock('$lib/api/client', () => ({ api: mocks, ApiError: class ApiError extends Error { status = 500; } }));
vi.mock('$lib/stores/auth', () => ({ auth: writable({ token: 'token', projectId: 'project-a' }) }));
vi.mock('$lib/stores/confirm.svelte', () => ({ confirmDialog: vi.fn().mockResolvedValue(true) }));
vi.mock('$lib/stores/toast', () => ({ toast: { success: vi.fn(), warning: vi.fn(), error: vi.fn() } }));
vi.mock('$lib/utils/autoRefresh.svelte', () => ({
	createAutoRefresh: () => ({ active: false, intervalSeconds: 60, intervalOptions: [10, 15, 30, 60] }),
}));

import { auth } from '$lib/stores/auth';
import Page from '../+page.svelte';

const groups: SecurityGroup[] = [
	{ id: 'sg-web', name: 'web', description: '', rules: [{
		id: 'rule-1', direction: 'ingress', protocol: 'tcp', port_range_min: 22, port_range_max: 22,
		remote_ip_prefix: null, remote_group_id: 'sg-db', ethertype: 'IPv4',
	}] },
	{ id: 'sg-db', name: 'db', description: '', rules: [] },
];

function installApi(quota = { security_group: { limit: 10, in_use: 2 }, security_group_rule: { limit: 20, in_use: 1 } }, listedGroups: SecurityGroup[] = groups) {
	mocks.get.mockImplementation(async (path: string) => {
		if (path === '/api/v1/security-groups') return listedGroups;
		if (path === '/api/v1/security-groups/quota') return quota;
		if (path === '/api/v1/security-groups/sg-web/instances') return [{ id: 'vm-1', name: 'vm-main', status: 'ACTIVE' }];
		if (path === '/api/v1/security-groups/sg-db/instances') return [];
		throw new Error(`Unexpected GET ${path}`);
	});
	mocks.post.mockResolvedValue({ id: 'created' });
	mocks.delete.mockResolvedValue(undefined);
}

beforeEach(() => {
	vi.clearAllMocks();
	mocks.get.mockReset();
	auth.update((state) => ({ ...state, token: 'token', projectId: 'project-a' }));
	vi.stubGlobal('matchMedia', vi.fn((query: string) => ({ matches: query.includes('min-width: 768px'), addEventListener: vi.fn(), removeEventListener: vi.fn() })));
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

describe('project security-group management', () => {
	it('shows quota and attached VM; submits default CIDR and a single TCP port from within the rule table', async () => {
		installApi();
		render(Page);
		expect(await screen.findByText('vm-main')).toBeTruthy();
		expect(screen.getByRole('link', { name: /vm-main/ }).getAttribute('href')).toBe('/dashboard/compute/instances/vm-1');
		expect(screen.getByLabelText('프로젝트 보안 그룹 쿼터').textContent).toMatch(/2\s*\/\s*10/);
		const table = screen.getByLabelText('보안 그룹 규칙');
		expect(within(table).getByTitle('sg-db').textContent).toContain('db');
		await fireEvent.click(within(table).getByRole('button', { name: '+ 규칙 추가' }));
		await fireEvent.change(screen.getByLabelText('프로토콜'), { target: { value: 'tcp' } });
		await fireEvent.input(screen.getByLabelText('시작 포트'), { target: { value: '8443' } });
		expect(screen.getByText('비우면 시작 포트와 동일')).toBeTruthy();
		await fireEvent.click(screen.getByRole('button', { name: '새 규칙 추가' }));
		await vi.waitFor(() => expect(mocks.post).toHaveBeenCalledWith('/api/v1/security-groups/sg-web/rules', expect.objectContaining({
			protocol: 'tcp', port_range_min: 8443, port_range_max: 8443, remote_ip_prefix: '0.0.0.0/0',
		}), 'token', 'project-a'));
	});

	it('identifies IPv4 and IPv6 in a dedicated table column, including an open IPv6 target', async () => {
		installApi(undefined, [{ ...groups[0], rules: [...groups[0].rules, {
			id: 'rule-v6', direction: 'egress', protocol: null, port_range_min: null, port_range_max: null,
			remote_ip_prefix: null, remote_group_id: null, ethertype: 'IPv6',
		}] }, groups[1]]);
		render(Page);
		await screen.findByText('vm-main');
		const table = within(screen.getByLabelText('보안 그룹 규칙'));
		expect(table.getByText('IP 버전')).toBeTruthy();
		expect(table.getByText('IPv4')).toBeTruthy();
		expect(table.getByText('IPv6')).toBeTruthy();
		expect(table.getByText('::/0')).toBeTruthy();
	});

	it('copies a group-targeted rule for explicit remove/recreate without deleting before confirmation', async () => {
		installApi();
		render(Page);
		await screen.findByText('vm-main');
		await fireEvent.click(screen.getByRole('button', { name: '수정' }));
		expect((screen.getByLabelText('원격 대상 유형') as HTMLSelectElement).value).toBe('group');
		expect((screen.getByLabelText('원격 보안 그룹') as HTMLSelectElement).value).toBe('sg-db');
		expect(mocks.delete).not.toHaveBeenCalled();
		await fireEvent.click(screen.getByRole('button', { name: '기존 규칙 제거' }));
		await vi.waitFor(() => expect(mocks.delete).toHaveBeenCalledWith('/api/v1/security-groups/sg-web/rules/rule-1', 'token', 'project-a'));
		expect(screen.getByRole('button', { name: '새 규칙 추가' })).toBeTruthy();
		await fireEvent.click(screen.getByRole('button', { name: '새 규칙 추가' }));
		await vi.waitFor(() => expect(mocks.post).toHaveBeenCalledWith('/api/v1/security-groups/sg-web/rules', expect.objectContaining({ remote_group_id: 'sg-db' }), 'token', 'project-a'));
		expect(mocks.post.mock.calls[0][1]).not.toHaveProperty('remote_ip_prefix');
	});

	it('prevents creating more resources when the current project quota is exhausted', async () => {
		installApi({ security_group: { limit: 2, in_use: 2 }, security_group_rule: { limit: 1, in_use: 1 } });
		render(Page);
		await screen.findByText('vm-main');
		expect(screen.getByRole('button', { name: '+ 보안 그룹 생성' })).toHaveProperty('disabled', true);
		await fireEvent.click(screen.getByRole('button', { name: '수정' }));
		expect(screen.getByRole('button', { name: '새 규칙 추가' })).toHaveProperty('disabled', true);
		expect(screen.getByRole('button', { name: '기존 규칙 제거' })).toHaveProperty('disabled', false);
	});

	it('discards previous-project group and quota responses after rescope', async () => {
		const oldGroups = Promise.withResolvers<SecurityGroup[]>();
		const oldQuota = Promise.withResolvers<{ security_group: { limit: number; in_use: number }; security_group_rule: { limit: number; in_use: number } }>();
		mocks.get.mockImplementation((path: string, _token: string, project: string) => {
			if (project === 'project-a' && path === '/api/v1/security-groups') return oldGroups.promise;
			if (project === 'project-a' && path === '/api/v1/security-groups/quota') return oldQuota.promise;
			if (path === '/api/v1/security-groups') return Promise.resolve([{ id: 'sg-b', name: 'project-b-group', description: '', rules: [] }]);
			if (path === '/api/v1/security-groups/quota') return Promise.resolve({ security_group: { limit: 5, in_use: 1 }, security_group_rule: { limit: 10, in_use: 0 } });
			if (path === '/api/v1/security-groups/sg-b/instances') return Promise.resolve([]);
			throw new Error(`Unexpected GET ${path}`);
		});
		render(Page);
		await vi.waitFor(() => expect(mocks.get).toHaveBeenCalledWith('/api/v1/security-groups/quota', 'token', 'project-a'));
		auth.update((state) => ({ ...state, projectId: 'project-b' }));
		expect(await screen.findByRole('button', { name: 'project-b-group 0' })).toBeTruthy();
		oldGroups.resolve(groups);
		oldQuota.resolve({ security_group: { limit: 200, in_use: 199 }, security_group_rule: { limit: 1000, in_use: 999 } });
		await Promise.all([oldGroups.promise, oldQuota.promise]);
		await vi.waitFor(() => expect(screen.getByLabelText('프로젝트 보안 그룹 쿼터').textContent).toMatch(/1\s*\/\s*5/));
		expect(screen.queryByRole('button', { name: 'web 1' })).toBeNull();
	});
});
