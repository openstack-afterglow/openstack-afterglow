import { afterEach, describe, expect, it } from 'vitest';
import { cleanup, fireEvent, render, screen, within } from '@testing-library/svelte';
import type { SecurityGroup, SecurityGroupRule } from '$lib/types/securityGroup';
import SecurityGroupUnion from '../SecurityGroupUnion.svelte';

afterEach(cleanup);

function rule(id: string, overrides: Partial<SecurityGroupRule> = {}): SecurityGroupRule {
	return {
		id,
		direction: 'ingress',
		ethertype: 'IPv4',
		protocol: 'tcp',
		port_range_min: 22,
		port_range_max: 22,
		remote_ip_prefix: '10.20.0.0/24',
		remote_group_id: null,
		...overrides,
	};
}

function group(id: string, rules: SecurityGroupRule[], name = id): SecurityGroup {
	return { id, name, description: '', rules };
}

const ssh = group('sg-ssh', [rule('ssh')]);
const unrelated = group('sg-unapplied', [rule('unapplied', {
	port_range_min: 5432,
	port_range_max: 5432,
	remote_ip_prefix: '192.0.2.0/24',
})]);

function cells(tableName: string): string[][] {
	return within(screen.getByRole('table', { name: tableName })).getAllByRole('row')
		.slice(1)
		.map((row) => within(row).getAllByRole('cell').map((cell) => cell.textContent ?? ''));
}

async function expandDirections() {
	await fireEvent.click(screen.getByRole('button', { name: '인바운드 허용 규칙 펼치기' }));
	await fireEvent.click(screen.getByRole('button', { name: '아웃바운드 허용 규칙 펼치기' }));
}

describe('SecurityGroupUnion applied policy', () => {
	it('unions only applied groups and separates direction, IP version, and source/destination headers', async () => {
		const web = group('sg-web', [
			rule('web-a', { port_range_min: 80, port_range_max: 85 }),
			rule('dns', {
				direction: 'egress',
				ethertype: 'IPv6',
				protocol: 'udp',
				port_range_min: 53,
				port_range_max: 53,
				remote_ip_prefix: '2001:db8::/64',
			}),
		]);
		const webExtension = group('sg-web-extension', [
			rule('web-b', { port_range_min: 84, port_range_max: 90 }),
		]);
		render(SecurityGroupUnion, {
			groupIds: [web.id, webExtension.id, web.id],
			groups: [unrelated, webExtension, web],
		});
		await expandDirections();

		expect(cells('인바운드 허용 규칙')).toEqual([['IPv4', 'TCP', '80–90', '10.20.0.0/24']]);
		expect(cells('아웃바운드 허용 규칙')).toEqual([['IPv6', 'UDP', '53', '2001:db8::/64']]);
		expect(screen.queryByRole('cell', { name: '5432' })).toBeNull();
		expect(screen.queryByRole('cell', { name: '192.0.2.0/24' })).toBeNull();
	});

	it('displays ICMP type/code including zero and resolves remote names without applying their rules', async () => {
		const remoteId = 'cc7aef79-bde3-4616-a0ea-b984da0e3ff8';
		const missingRemoteId = '227393d2-bb2d-479d-946c-199f8e678b8e';
		const remote = group(remoteId, [rule('remote-only', { port_range_min: 8443, port_range_max: 8443 })], '운영 클라이언트');
		const applied = group('sg-icmp', [
			rule('echo-reply', {
				protocol: 'icmp', port_range_min: 0, port_range_max: 0,
				remote_ip_prefix: null, remote_group_id: remoteId,
			}),
			rule('echo-request', {
				protocol: 'icmp', port_range_min: 8, port_range_max: null,
				remote_ip_prefix: null, remote_group_id: missingRemoteId,
			}),
			rule('icmp-v6', {
				direction: 'egress', ethertype: 'IPv6', protocol: '58',
				port_range_min: null, port_range_max: null, remote_ip_prefix: null,
			}),
		]);
		render(SecurityGroupUnion, { groupIds: [applied.id], groups: [applied, remote] });
		await expandDirections();

		const reply = screen.getByRole('row', { name: 'IPv4 ICMP 유형 0 · 코드 0 보안 그룹: 운영 클라이언트' });
		expect(within(reply).getByRole('cell', { name: '보안 그룹: 운영 클라이언트' }).getAttribute('title')).toBe(remoteId);
		const request = screen.getByRole('row', { name: `IPv4 ICMP 유형 8 · 코드 전체 보안 그룹: ${missingRemoteId}` });
		expect(within(request).getByRole('cell', { name: `보안 그룹: ${missingRemoteId}` }).getAttribute('title')).toBe(missingRemoteId);
		expect(cells('아웃바운드 허용 규칙')).toEqual([['IPv6', 'ICMPv6', '유형 전체 · 코드 전체', '전체 (::/0)']]);
		expect(screen.queryByRole('cell', { name: '8443' })).toBeNull();
	});

	it('replaces previous applied port and group rows and recomputes ranges when props change', async () => {
		const previousRemote = group('sg-old-remote', [], '이전 클라이언트');
		const previous = group('sg-old', [rule('previous', {
			remote_ip_prefix: null, remote_group_id: previousRemote.id,
		})]);
		const nextRemote = group('sg-new-remote', [], '새 클라이언트');
		const nextA = group('sg-new-a', [rule('next-a', {
			port_range_min: 8000, port_range_max: 8005,
			remote_ip_prefix: null, remote_group_id: nextRemote.id,
		})]);
		const nextB = group('sg-new-b', [rule('next-b', {
			port_range_min: 8006, port_range_max: 8010,
			remote_ip_prefix: null, remote_group_id: nextRemote.id,
		})]);
		const groups = [previous, previousRemote, nextA, nextB, nextRemote];
		const { rerender } = render(SecurityGroupUnion, { groupIds: [previous.id], groups });
		await fireEvent.click(screen.getByRole('button', { name: '인바운드 허용 규칙 펼치기' }));
		expect(cells('인바운드 허용 규칙')).toEqual([['IPv4', 'TCP', '22', '보안 그룹: 이전 클라이언트']]);

		await rerender({ groupIds: [nextA.id, nextB.id], groups });
		expect(cells('인바운드 허용 규칙')).toEqual([['IPv4', 'TCP', '8000–8010', '보안 그룹: 새 클라이언트']]);
		expect(screen.queryByRole('cell', { name: '22' })).toBeNull();
		expect(screen.queryByRole('cell', { name: '보안 그룹: 이전 클라이언트' })).toBeNull();

		await rerender({ groupIds: [nextA.id], groups: [
			nextA, { ...nextRemote, name: '변경된 클라이언트' },
		] });
		expect(cells('인바운드 허용 규칙')).toEqual([['IPv4', 'TCP', '8000–8005', '보안 그룹: 변경된 클라이언트']]);
		expect(screen.queryByRole('cell', { name: '8000–8010' })).toBeNull();
		expect(screen.queryByRole('cell', { name: '보안 그룹: 새 클라이언트' })).toBeNull();
	});

	it('keeps an empty direction explicit without hiding the populated direction', async () => {
		render(SecurityGroupUnion, { groupIds: [ssh.id], groups: [ssh] });
		await expandDirections();
		expect(cells('인바운드 허용 규칙')).toEqual([['IPv4', 'TCP', '22', '10.20.0.0/24']]);
		expect(within(screen.getByRole('table', { name: '아웃바운드 허용 규칙' }))
			.getByRole('cell', { name: '아웃바운드 허용 규칙이 없습니다.' })).not.toBeNull();
	});

	it('keeps disclosure choices independent across directions and interfaces', async () => {
		const both = group('sg-both', [rule('ssh'), rule('dns', {
			direction: 'egress', protocol: 'udp', port_range_min: 53, port_range_max: 53,
		})]);
		const web = group('sg-web', [rule('https', { port_range_min: 443, port_range_max: 443 })]);
		const first = within(render(SecurityGroupUnion, { groupIds: [both.id], groups: [both] }).container);
		const second = within(render(SecurityGroupUnion, { groupIds: [web.id], groups: [web] }).container);
		expect(first.queryByRole('table')).toBeNull();
		expect(second.queryByRole('table')).toBeNull();
		expect(first.getByRole('button', { name: '인바운드 허용 규칙 펼치기' }).getAttribute('aria-expanded')).toBe('false');

		await fireEvent.click(first.getByRole('button', { name: '인바운드 허용 규칙 펼치기' }));
		expect(first.getByRole('table', { name: '인바운드 허용 규칙' })).toBeTruthy();
		expect(first.queryByRole('table', { name: '아웃바운드 허용 규칙' })).toBeNull();
		expect(second.queryByRole('table')).toBeNull();
		expect(first.getByRole('button', { name: '인바운드 허용 규칙 접기' }).getAttribute('aria-expanded')).toBe('true');

		await fireEvent.click(second.getByRole('button', { name: '인바운드 허용 규칙 펼치기' }));
		expect(second.getByRole('cell', { name: '443' })).toBeTruthy();
		await fireEvent.click(first.getByRole('button', { name: '아웃바운드 허용 규칙 펼치기' }));
		expect(first.getByRole('cell', { name: '53' })).toBeTruthy();
		await fireEvent.click(first.getByRole('button', { name: '인바운드 허용 규칙 접기' }));
		expect(first.queryByRole('table', { name: '인바운드 허용 규칙' })).toBeNull();
		expect(first.getByRole('table', { name: '아웃바운드 허용 규칙' })).toBeTruthy();
		expect(second.getByRole('cell', { name: '443' })).toBeTruthy();
	});
});

describe('SecurityGroupUnion policy availability', () => {
	it('prioritizes loading over errors and stale or partial permissions', async () => {
		const { rerender } = render(SecurityGroupUnion, {
			groupIds: [ssh.id], groups: [ssh], loading: false, error: '',
		});
		await fireEvent.click(screen.getByRole('button', { name: '인바운드 허용 규칙 펼치기' }));
		expect(screen.getByRole('cell', { name: '22' })).not.toBeNull();

		await rerender({
			groupIds: [ssh.id, 'sg-unavailable'], groups: [ssh], loading: true, error: '조회 실패',
		});
		expect(screen.getByRole('status').textContent).toContain('불러오는 중');
		expect(screen.queryByRole('alert')).toBeNull();
		expect(screen.queryByRole('table')).toBeNull();
		expect(screen.queryByRole('cell', { name: '22' })).toBeNull();
		expect(screen.queryByText('적용된 보안 그룹에 허용 규칙이 없습니다.')).toBeNull();
	});

	it('shows retrieval failure rather than partial rows or a misleading no-group state', async () => {
		const { rerender } = render(SecurityGroupUnion, {
			groupIds: [ssh.id, 'sg-unavailable'], groups: [ssh], error: '프로젝트 조회 실패',
		});
		expect(screen.getByRole('alert').textContent).toContain('프로젝트 조회 실패');
		expect(screen.queryByRole('table')).toBeNull();
		expect(screen.queryByRole('cell', { name: '22' })).toBeNull();
		expect(screen.queryByText('sg-unavailable')).toBeNull();

		await rerender({ groupIds: [], groups: [], error: '프로젝트 조회 실패' });
		expect(screen.getByRole('alert').textContent).toContain('프로젝트 조회 실패');
		expect(screen.queryByText('이 인터페이스에 적용된 보안 그룹이 없습니다.')).toBeNull();
	});

	it('names unavailable applied groups by full ID and suppresses the known partial union', () => {
		const missingId = '814d68b3-1a4d-4fa1-8942-183619f480e3';
		render(SecurityGroupUnion, { groupIds: [ssh.id, missingId], groups: [ssh] });
		const alert = within(screen.getByRole('alert'));
		expect(alert.getByText(missingId)).not.toBeNull();
		expect(screen.queryByRole('table')).toBeNull();
		expect(screen.queryByRole('cell', { name: '22' })).toBeNull();
		expect(screen.queryByText('적용된 보안 그룹에 허용 규칙이 없습니다.')).toBeNull();
	});

	it('distinguishes no applied group from applied groups with no allow rules', async () => {
		const empty = group('sg-empty', []);
		const { rerender } = render(SecurityGroupUnion, { groupIds: [], groups: [ssh, empty] });
		expect(screen.getByText('이 인터페이스에 적용된 보안 그룹이 없습니다.')).not.toBeNull();
		expect(screen.queryByRole('table')).toBeNull();
		expect(screen.queryByText('적용된 보안 그룹에 허용 규칙이 없습니다.')).toBeNull();

		await rerender({ groupIds: [empty.id], groups: [ssh, empty] });
		expect(screen.getByText('적용된 보안 그룹에 허용 규칙이 없습니다.')).not.toBeNull();
		expect(screen.queryByText('이 인터페이스에 적용된 보안 그룹이 없습니다.')).toBeNull();
		expect(screen.queryByRole('table')).toBeNull();
	});
});
