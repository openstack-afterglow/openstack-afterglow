import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, within } from '@testing-library/svelte';
import { writable } from 'svelte/store';
import type { SecurityGroup, SecurityGroupRule } from '$lib/types/securityGroup';

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
	const inventory = structuredClone(listedGroups);
	const otherRuleUsage = quota.security_group_rule.in_use - inventory.reduce((sum, group) => sum + group.rules.length, 0);
	let nextId = 0;
	mocks.get.mockImplementation(async (path: string) => {
		if (path === '/api/v1/security-groups') return structuredClone(inventory);
		if (path === '/api/v1/security-groups/quota') return {
			...quota, security_group_rule: { ...quota.security_group_rule, in_use: otherRuleUsage + inventory.reduce((sum, group) => sum + group.rules.length, 0) },
		};
		if (path === '/api/v1/security-groups/sg-web/instances') return [{ id: 'vm-1', name: 'vm-main', status: 'ACTIVE' }];
		if (path === '/api/v1/security-groups/sg-db/instances') return [];
		throw new Error(`Unexpected GET ${path}`);
	});
	mocks.post.mockImplementation(async (path: string, body: Partial<SecurityGroupRule>) => {
		if (path !== '/api/v1/security-groups/sg-web/rules') throw new Error(`Unexpected POST ${path}`);
		const created: SecurityGroupRule = {
			id: `created-${++nextId}`, direction: body.direction!, ethertype: body.ethertype!, protocol: body.protocol ?? null,
			port_range_min: body.port_range_min ?? null, port_range_max: body.port_range_max ?? null,
			remote_ip_prefix: body.remote_ip_prefix ?? null, remote_group_id: body.remote_group_id ?? null,
		};
		inventory[0].rules.push(created);
		return structuredClone(created);
	});
	mocks.delete.mockImplementation(async (path: string) => {
		const id = path.split('/').at(-1);
		const index = inventory[0].rules.findIndex((rule) => rule.id === id);
		if (index < 0) throw new Error(`Missing rule ${id}`);
		inventory[0].rules.splice(index, 1);
	});
}

beforeEach(() => {
	vi.clearAllMocks();
	mocks.get.mockReset();
	mocks.post.mockReset();
	mocks.delete.mockReset();
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
		const table = screen.getByRole('region', { name: '보안 그룹 규칙' });
		expect(within(table).getByTitle('sg-db').textContent).toContain('db');
		await fireEvent.click(within(table).getByRole('button', { name: '+ 규칙 추가' }));
		await fireEvent.change(screen.getByLabelText('프로토콜'), { target: { value: 'tcp' } });
		await fireEvent.input(screen.getByLabelText('시작 포트'), { target: { value: '8443' } });
		expect(screen.getByText('비우면 시작 포트와 동일')).toBeTruthy();
		expect(screen.queryByRole('button', { name: '+ 규칙 추가' })).toBeNull();
		await fireEvent.click(screen.getByRole('button', { name: '추가' }));
		expect(await within(table).findByText('8443')).toBeTruthy();
		expect(within(table).getByText('0.0.0.0/0')).toBeTruthy();
		expect(screen.queryByRole('form', { name: '새 규칙' })).toBeNull();
	});

	it('identifies IPv4 and IPv6 in a dedicated table column, including an open IPv6 target', async () => {
		installApi(undefined, [{ ...groups[0], rules: [...groups[0].rules, {
			id: 'rule-v6', direction: 'egress', protocol: null, port_range_min: null, port_range_max: null,
			remote_ip_prefix: null, remote_group_id: null, ethertype: 'IPv6',
		}] }, groups[1]]);
		render(Page);
		await screen.findByText('vm-main');
		const table = within(screen.getByRole('region', { name: '보안 그룹 규칙' }));
		expect(table.getByText('IPv4')).toBeTruthy();
		expect(table.getByText('IPv6')).toBeTruthy();
		expect(table.getByText('::/0')).toBeTruthy();
	});

	it('saves an edited group-targeted rule without duplicating the rule or changing its target', async () => {
		installApi();
		render(Page);
		await screen.findByText('vm-main');
		await fireEvent.click(screen.getByRole('button', { name: '수정' }));
		await fireEvent.input(screen.getByLabelText('시작 포트'), { target: { value: '8443' } });
		await fireEvent.input(screen.getByLabelText('끝 포트'), { target: { value: '' } });
		await fireEvent.click(screen.getByRole('button', { name: '저장' }));
		const table = within(screen.getByRole('region', { name: '보안 그룹 규칙' }));
		expect(await table.findByText('8443')).toBeTruthy();
		expect(table.queryByText('22')).toBeNull();
		expect(table.getByTitle('sg-db').textContent).toContain('db');
		expect(screen.queryByRole('form', { name: '규칙 수정' })).toBeNull();
		expect(screen.getByRole('button', { name: 'web 1' })).toBeTruthy();
	});

	it('allows replacement at a full quota, but prevents adding more resources', async () => {
		installApi({ security_group: { limit: 2, in_use: 2 }, security_group_rule: { limit: 1, in_use: 1 } });
		render(Page);
		await screen.findByText('vm-main');
		expect(screen.getByRole('button', { name: '+ 보안 그룹 생성' })).toHaveProperty('disabled', true);
		await fireEvent.click(screen.getByRole('button', { name: '+ 규칙 추가' }));
		expect(screen.getByRole('button', { name: '추가' })).toHaveProperty('disabled', true);
		await fireEvent.click(screen.getByRole('button', { name: '취소' }));
		await fireEvent.click(screen.getByRole('button', { name: '수정' }));
		expect(screen.getByRole('button', { name: '저장' })).toHaveProperty('disabled', false);
		expect(screen.getByText(/규칙 쿼터가 가득 차 기존 규칙을 먼저 제거/)).toBeTruthy();
		await fireEvent.input(screen.getByLabelText('시작 포트'), { target: { value: '443' } });
		await fireEvent.input(screen.getByLabelText('끝 포트'), { target: { value: '443' } });
		await fireEvent.click(screen.getByRole('button', { name: '저장' }));
		expect(await within(screen.getByRole('region', { name: '보안 그룹 규칙' })).findByText('443')).toBeTruthy();
		expect(screen.getByRole('button', { name: 'web 1' })).toBeTruthy();
	});

	it('opens one editor between the selected rule and the following rule, and cancel performs no writes', async () => {
		installApi(undefined, [{ ...groups[0], rules: [groups[0].rules[0],
			{ ...groups[0].rules[0], id: 'rule-2', port_range_min: 443, port_range_max: 443 },
			{ ...groups[0].rules[0], id: 'rule-3', port_range_min: 3389, port_range_max: 3389 },
		] }, groups[1]]);
		render(Page);
		await screen.findByText('vm-main');
		let edits = screen.getAllByRole('button', { name: '수정' });
		await fireEvent.click(edits[1]);
		let form = screen.getByRole('form', { name: '규칙 수정' });
		expect(edits[1].compareDocumentPosition(form) & Node.DOCUMENT_POSITION_FOLLOWING).not.toBe(0);
		expect(form.compareDocumentPosition(edits[2]) & Node.DOCUMENT_POSITION_FOLLOWING).not.toBe(0);
		await fireEvent.click(edits[0]);
		form = screen.getByRole('form', { name: '규칙 수정' });
		edits = screen.getAllByRole('button', { name: '수정' });
		expect(form.compareDocumentPosition(edits[1]) & Node.DOCUMENT_POSITION_FOLLOWING).not.toBe(0);
		await fireEvent.input(screen.getByLabelText('시작 포트'), { target: { value: '9999' } });
		await fireEvent.click(screen.getByRole('button', { name: '취소' }));
		expect(screen.queryByRole('form', { name: '규칙 수정' })).toBeNull();
		expect(within(screen.getByRole('region', { name: '보안 그룹 규칙' })).getByText('22')).toBeTruthy();
		expect(mocks.post).not.toHaveBeenCalled();
		expect(mocks.delete).not.toHaveBeenCalled();
	});

	it('closes an unchanged edit without removing or recreating the rule', async () => {
		installApi();
		render(Page);
		await screen.findByText('vm-main');
		await fireEvent.click(screen.getByRole('button', { name: '수정' }));
		await fireEvent.click(screen.getByRole('button', { name: '저장' }));
		expect(screen.queryByRole('form', { name: '규칙 수정' })).toBeNull();
		expect(within(screen.getByRole('region', { name: '보안 그룹 규칙' })).getByText('22')).toBeTruthy();
		expect(mocks.post).not.toHaveBeenCalled();
		expect(mocks.delete).not.toHaveBeenCalled();
	});

	it.each([
		['192.0.2.999/32', 'IPv4', /올바른 CIDR/],
		['192.0.2.1/33', 'IPv4', /올바른 CIDR/],
		['2001:db8:::1/64', 'IPv6', /올바른 CIDR/],
		['2001:db8::/64', 'IPv4', /선택한 IP 버전/],
		['192.0.2.0/24', 'IPv6', /선택한 IP 버전/],
	])('rejects %s with %s before any rule mutation', async (cidr, version, error) => {
		installApi({ security_group: { limit: 10, in_use: 2 }, security_group_rule: { limit: 1, in_use: 1 } });
		render(Page);
		await screen.findByText('vm-main');
		await fireEvent.click(screen.getByRole('button', { name: '수정' }));
		await fireEvent.change(screen.getByLabelText('원격 대상 유형'), { target: { value: 'cidr' } });
		await fireEvent.change(screen.getByLabelText('IP 버전'), { target: { value: version } });
		await fireEvent.input(screen.getByLabelText('원격 IP 대역'), { target: { value: cidr } });
		await fireEvent.click(screen.getByRole('button', { name: '저장' }));
		expect(screen.getByRole('alert').textContent).toMatch(error);
		expect(within(screen.getByRole('region', { name: '보안 그룹 규칙' })).getByText('22')).toBeTruthy();
		expect(mocks.post).not.toHaveBeenCalled();
		expect(mocks.delete).not.toHaveBeenCalled();
	});

	it('keeps the original rule and draft when create-first replacement fails', async () => {
		installApi();
		mocks.post.mockRejectedValueOnce(new Error('creation unavailable'));
		render(Page);
		await screen.findByText('vm-main');
		await fireEvent.click(screen.getByRole('button', { name: '수정' }));
		await fireEvent.input(screen.getByLabelText('시작 포트'), { target: { value: '443' } });
		await fireEvent.input(screen.getByLabelText('끝 포트'), { target: { value: '443' } });
		await fireEvent.click(screen.getByRole('button', { name: '저장' }));
		expect((await screen.findByRole('alert')).textContent).toContain('creation unavailable');
		expect(within(screen.getByRole('region', { name: '보안 그룹 규칙' })).getByText('22')).toBeTruthy();
		expect(screen.getByLabelText('시작 포트')).toHaveProperty('value', '443');
		expect(mocks.delete).not.toHaveBeenCalled();
	});

	it('restores the original rule at a full quota when replacement creation fails, keeping the edited draft', async () => {
		installApi({ security_group: { limit: 10, in_use: 2 }, security_group_rule: { limit: 1, in_use: 1 } });
		mocks.post.mockRejectedValueOnce(new Error('replacement unavailable'));
		render(Page);
		await screen.findByText('vm-main');
		await fireEvent.click(screen.getByRole('button', { name: '수정' }));
		await fireEvent.input(screen.getByLabelText('시작 포트'), { target: { value: '443' } });
		await fireEvent.input(screen.getByLabelText('끝 포트'), { target: { value: '443' } });
		await fireEvent.click(screen.getByRole('button', { name: '저장' }));
		expect((await screen.findByRole('alert')).textContent).toContain('replacement unavailable');
		expect(within(screen.getByRole('region', { name: '보안 그룹 규칙' })).getByText('22')).toBeTruthy();
		expect(screen.getByLabelText('시작 포트')).toHaveProperty('value', '443');
		await fireEvent.click(screen.getByRole('button', { name: '저장' }));
		expect(await within(screen.getByRole('region', { name: '보안 그룹 규칙' })).findByText('443')).toBeTruthy();
		expect(screen.getByRole('button', { name: 'web 1' })).toBeTruthy();
	});

	it('reports failed restoration and lets the preserved draft save without removing a missing rule again', async () => {
		installApi({ security_group: { limit: 10, in_use: 2 }, security_group_rule: { limit: 1, in_use: 1 } });
		mocks.post.mockRejectedValueOnce(new Error('replacement unavailable')).mockRejectedValueOnce(new Error('restoration unavailable'));
		render(Page);
		await screen.findByText('vm-main');
		await fireEvent.click(screen.getByRole('button', { name: '수정' }));
		await fireEvent.input(screen.getByLabelText('시작 포트'), { target: { value: '443' } });
		await fireEvent.input(screen.getByLabelText('끝 포트'), { target: { value: '443' } });
		await fireEvent.click(screen.getByRole('button', { name: '저장' }));
		expect((await screen.findByRole('alert')).textContent).toContain('기존 규칙은 제거된 상태');
		expect(within(screen.getByRole('region', { name: '보안 그룹 규칙' })).queryByText('22')).toBeNull();
		expect(screen.getByLabelText('시작 포트')).toHaveProperty('value', '443');
		await fireEvent.click(screen.getByRole('button', { name: '저장' }));
		expect(await within(screen.getByRole('region', { name: '보안 그룹 규칙' })).findByText('443')).toBeTruthy();
		expect(mocks.delete).toHaveBeenCalledTimes(1);
	});

	it('shows partial application and both policies when deleting the old rule fails after creation', async () => {
		installApi();
		mocks.delete.mockRejectedValueOnce(new Error('removal unavailable'));
		render(Page);
		await screen.findByText('vm-main');
		await fireEvent.click(screen.getByRole('button', { name: '수정' }));
		await fireEvent.input(screen.getByLabelText('시작 포트'), { target: { value: '443' } });
		await fireEvent.input(screen.getByLabelText('끝 포트'), { target: { value: '443' } });
		await fireEvent.click(screen.getByRole('button', { name: '저장' }));
		expect((await screen.findByRole('alert')).textContent).toContain('새 규칙은 생성됐지만 기존 규칙 제거에 실패');
		const table = within(screen.getByRole('region', { name: '보안 그룹 규칙' }));
		expect(table.getByText('22')).toBeTruthy();
		expect(table.getByText('443')).toBeTruthy();
		expect(screen.queryByRole('form', { name: '규칙 수정' })).toBeNull();
	});

	it.each([['0', '22'], ['443', '22']])('rejects invalid port range %s-%s without removing the rule', async (min, max) => {
		installApi({ security_group: { limit: 10, in_use: 2 }, security_group_rule: { limit: 1, in_use: 1 } });
		render(Page);
		await screen.findByText('vm-main');
		await fireEvent.click(screen.getByRole('button', { name: '수정' }));
		await fireEvent.input(screen.getByLabelText('시작 포트'), { target: { value: min } });
		await fireEvent.input(screen.getByLabelText('끝 포트'), { target: { value: max } });
		await fireEvent.click(screen.getByRole('button', { name: '저장' }));
		expect(screen.getByRole('alert').textContent).toContain('포트는 1–65535');
		expect(within(screen.getByRole('region', { name: '보안 그룹 규칙' })).getByText('22')).toBeTruthy();
		expect(mocks.post).not.toHaveBeenCalled();
		expect(mocks.delete).not.toHaveBeenCalled();
	});

	it.each([
		[{ remote_group_id: 'foreign-group' }, /현재 프로젝트의 원격 보안 그룹/],
		[{ remote_group_id: 'sg-db', remote_ip_prefix: '192.0.2.0/24' }, /동시에 지정할 수 없습니다/],
	])('rejects an invalid remote target %o before replacement', async (target, error) => {
		installApi(undefined, [{ ...groups[0], rules: [{ ...groups[0].rules[0], ...target }] }, groups[1]]);
		render(Page);
		await screen.findByText('vm-main');
		await fireEvent.click(screen.getByRole('button', { name: '수정' }));
		await fireEvent.click(screen.getByRole('button', { name: '저장' }));
		expect(screen.getByRole('alert').textContent).toMatch(error);
		expect(within(screen.getByRole('region', { name: '보안 그룹 규칙' })).getByText('22')).toBeTruthy();
		expect(mocks.post).not.toHaveBeenCalled();
		expect(mocks.delete).not.toHaveBeenCalled();
	});

	it('saves an edited rule as a new rule when refresh shows the original was already removed elsewhere', async () => {
		installApi();
		render(Page);
		await screen.findByText('vm-main');
		await fireEvent.click(screen.getByRole('button', { name: '수정' }));
		await fireEvent.input(screen.getByLabelText('시작 포트'), { target: { value: '443' } });
		await fireEvent.input(screen.getByLabelText('끝 포트'), { target: { value: '443' } });
		await mocks.delete('/api/v1/security-groups/sg-web/rules/rule-1');
		mocks.delete.mockClear();
		await fireEvent.click(screen.getByRole('button', { name: '새로고침' }));
		await vi.waitFor(() => expect(within(screen.getByRole('region', { name: '보안 그룹 규칙' })).queryByText('22')).toBeNull());
		await fireEvent.click(screen.getByRole('button', { name: '저장' }));
		expect(await within(screen.getByRole('region', { name: '보안 그룹 규칙' })).findByText('443')).toBeTruthy();
		expect(mocks.delete).not.toHaveBeenCalled();
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
