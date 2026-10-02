// @vitest-environment node
import { describe, expect, it } from 'vitest';
import type { SecurityGroupRule } from '$lib/types/securityGroup';
import { buildSecurityGroupUnion, type SecurityGroupUnionGroup } from '../securityGroupUnion';

function rule(overrides: Partial<SecurityGroupRule> = {}): SecurityGroupRule {
	return {
		id: 'rule', direction: 'ingress', ethertype: 'IPv4', protocol: 'tcp',
		port_range_min: 22, port_range_max: 22,
		remote_ip_prefix: null, remote_group_id: null,
		...overrides,
	};
}

function group(id: string, rules: SecurityGroupRule[], name = id): SecurityGroupUnionGroup {
	return { id, name, rules };
}

function rows(rules: SecurityGroupRule[]) {
	return buildSecurityGroupUnion([group('applied', rules)], ['applied']).rows;
}

describe('security group exact union', () => {
	it('selects only applied groups and collapses semantic duplicates across rule and group IDs', () => {
		const result = buildSecurityGroupUnion([
			group('a', [rule({ id: 'first' }), rule({ id: 'second' })]),
			group('b', [rule({ id: 'third', remote_ip_prefix: '0.0.0.0/0' })]),
			group('unrelated', [rule({ protocol: null, port_range_min: null, port_range_max: null })]),
		], ['b', 'a', 'a', 'b']);
		expect(result.appliedGroupIds).toEqual(['a', 'b']);
		expect(result.missingGroupIds).toEqual([]);
		expect(result.rows).toEqual([expect.objectContaining({
			protocol: 'tcp', portRangeMin: 22, portRangeMax: 22,
			remote: { kind: 'cidr', value: '0.0.0.0/0' },
			protocolLabel: 'TCP', portLabel: '22', remoteLabel: '전체 (0.0.0.0/0)',
		})]);
	});

	it.each(['tcp', 'udp', 'sctp'])('merges overlapping and adjacent %s intervals across groups, but preserves gaps and bounds', (protocol) => {
		const range = (min: number, max: number) => rule({ protocol, port_range_min: min, port_range_max: max });
		const result = buildSecurityGroupUnion([
			group('a', [range(85, 88), range(101, 105), range(1, 1), range(65535, 65535)]),
			group('b', [range(80, 90), range(91, 99), range(100, 100), range(107, 109), range(2, 2), range(65534, 65534)]),
		], ['a', 'b']);
		expect(result.rows.map((row) => [row.portRangeMin, row.portRangeMax]))
			.toEqual([[1, 2], [80, 105], [107, 109], [65534, 65535]]);
		expect(result.rows.find((row) => row.portRangeMin === 80)?.portLabel).toBe('80–105');
		expect(result.rows.map((row) => row.protocolLabel)).toEqual(Array(4).fill(protocol.toUpperCase()));
	});

	it.each(['tcp', 'udp', 'sctp'])('lets unrestricted %s ports subsume narrower intervals only in their bucket', (protocol) => {
		const result = rows([
			rule({ protocol, port_range_min: 80, port_range_max: 90 }),
			rule({ protocol, port_range_min: null, port_range_max: null }),
			rule({ protocol, port_range_min: 443, port_range_max: 443 }),
			rule({ protocol, direction: 'egress' }),
		]);
		expect(result).toEqual(expect.arrayContaining([
			expect.objectContaining({ direction: 'ingress', protocol, portRangeMin: null, portRangeMax: null, portLabel: '전체' }),
			expect.objectContaining({ direction: 'egress', protocol, portRangeMin: 22, portRangeMax: 22 }),
		]));
		expect(result).toHaveLength(2);
	});

	it('canonicalizes a merged full transport domain to the same semantic row as unrestricted ports', () => {
		expect(rows([
			rule({ port_range_min: 1, port_range_max: 32767 }),
			rule({ port_range_min: 32768, port_range_max: 65535 }),
		])).toEqual(rows([rule({ port_range_min: null, port_range_max: null })]));
	});

	it.each([null, 'any'])('normalizes all-protocol %s and subsumes only the same exact target/direction/IP version', (protocol) => {
		const result = rows([
			rule(),
			rule({ protocol: 'udp' }),
			rule({ protocol: 'icmp', port_range_min: 8, port_range_max: 0 }),
			rule({ protocol: '47', port_range_min: null, port_range_max: null }),
			rule({ protocol, port_range_min: null, port_range_max: null }),
			rule({ direction: 'egress' }),
			rule({ ethertype: 'IPv6' }),
			rule({ remote_ip_prefix: '10.0.0.0/24' }),
			rule({ remote_group_id: '0.0.0.0/0' }),
		]);
		expect(result).toHaveLength(5);
		expect(result.filter((row) => row.protocol === null)).toEqual([expect.objectContaining({
			direction: 'ingress', ethertype: 'IPv4', remote: { kind: 'cidr', value: '0.0.0.0/0' },
			protocolLabel: '전체', portLabel: '전체', portRangeMin: null, portRangeMax: null,
		})]);
		expect(result.filter((row) => row.protocol === 'tcp').map((row) => [row.direction, row.ethertype, row.remote]))
			.toEqual(expect.arrayContaining([
				['egress', 'IPv4', { kind: 'cidr', value: '0.0.0.0/0' }],
				['ingress', 'IPv6', { kind: 'cidr', value: '::/0' }],
				['ingress', 'IPv4', { kind: 'cidr', value: '10.0.0.0/24' }],
				['ingress', 'IPv4', { kind: 'group', value: '0.0.0.0/0' }],
			]));
	});

	it('never merges adjacent intervals across direction, IP version, protocol, target kind, or exact CIDR', () => {
		const result = rows([
			rule({ remote_group_id: '0.0.0.0/0' }),
			rule({ remote_group_id: '0.0.0.0/0', direction: 'egress', port_range_min: 23, port_range_max: 23 }),
			rule({ remote_group_id: '0.0.0.0/0', ethertype: 'IPv6', port_range_min: 23, port_range_max: 23 }),
			rule({ remote_group_id: '0.0.0.0/0', protocol: 'udp', port_range_min: 23, port_range_max: 23 }),
			rule({ remote_group_id: '0.0.0.0/0', protocol: 'sctp', port_range_min: 23, port_range_max: 23 }),
			rule({ port_range_min: 23, port_range_max: 23 }),
			rule({ remote_ip_prefix: '10.0.0.0/8', port_range_min: 23, port_range_max: 23 }),
			rule({ remote_ip_prefix: '10.0.0.0/24', port_range_min: 24, port_range_max: 24 }),
		]);
		expect(result.map((row) => [row.direction, row.ethertype, row.protocol, row.remote, row.portRangeMin, row.portRangeMax]))
			.toEqual(expect.arrayContaining([
				['ingress', 'IPv4', 'tcp', { kind: 'group', value: '0.0.0.0/0' }, 22, 22],
				['egress', 'IPv4', 'tcp', { kind: 'group', value: '0.0.0.0/0' }, 23, 23],
				['ingress', 'IPv6', 'tcp', { kind: 'group', value: '0.0.0.0/0' }, 23, 23],
				['ingress', 'IPv4', 'udp', { kind: 'group', value: '0.0.0.0/0' }, 23, 23],
				['ingress', 'IPv4', 'sctp', { kind: 'group', value: '0.0.0.0/0' }, 23, 23],
				['ingress', 'IPv4', 'tcp', { kind: 'cidr', value: '0.0.0.0/0' }, 23, 23],
				['ingress', 'IPv4', 'tcp', { kind: 'cidr', value: '10.0.0.0/8' }, 23, 23],
				['ingress', 'IPv4', 'tcp', { kind: 'cidr', value: '10.0.0.0/24' }, 24, 24],
			]));
		expect(result).toHaveLength(8);
		expect(new Set(result.map((row) => row.key)).size).toBe(8);
	});

	it.each(['icmp', 'ipv6-icmp'])('treats %s bounds as type/code, preserving zero and distinct pairs without interval merging', (protocol) => {
		const ethertype = protocol === 'icmp' ? 'IPv4' : 'IPv6';
		const pair = (type: number | null, code: number | null) => rule({ protocol, ethertype, port_range_min: type, port_range_max: code });
		const result = rows([
			pair(8, 0), pair(8, 1), pair(9, 0), pair(0, -1), pair(8, -1), pair(8, null),
			pair(-1, -1), pair(null, null),
		]);
		expect(result.map((row) => [row.portRangeMin, row.portRangeMax, row.portLabel])).toEqual(expect.arrayContaining([
			[8, 0, '유형 8 · 코드 0'], [8, 1, '유형 8 · 코드 1'], [9, 0, '유형 9 · 코드 0'],
			[0, null, '유형 0 · 코드 전체'], [8, null, '유형 8 · 코드 전체'],
			[null, null, '유형 전체 · 코드 전체'],
		]));
		expect(result).toHaveLength(6);
	});

	it.each([
		['6', 'tcp', 'TCP', 80, 90, '80–90'],
		['17', 'udp', 'UDP', 53, 53, '53'],
		['132', 'sctp', 'SCTP', 22, 22, '22'],
		['1', 'icmp', 'ICMP', 8, 0, '유형 8 · 코드 0'],
		['58', 'ipv6-icmp', 'ICMPv6', 128, 0, '유형 128 · 코드 0'],
		['icmpv6', 'ipv6-icmp', 'ICMPv6', 0, -1, '유형 0 · 코드 전체'],
	] as const)('deduplicates protocol alias %s with %s', (alias, protocol, protocolLabel, min, max, portLabel) => {
		const ethertype = protocol === 'ipv6-icmp' ? 'IPv6' : 'IPv4';
		const result = rows([
			rule({ protocol: alias, ethertype, port_range_min: min, port_range_max: max }),
			rule({ protocol, ethertype, port_range_min: min, port_range_max: max }),
		]);
		expect(result).toEqual([expect.objectContaining({ protocol, protocolLabel, portLabel })]);
	});

	it('retains unknown numeric and named non-port protocols instead of implying TCP ports', () => {
		const result = rows(['47', 'gre', '253'].map((protocol) => rule({ protocol, port_range_min: null, port_range_max: null })));
		expect(result.map((row) => [row.protocol, row.protocolLabel, row.portRangeMin, row.portRangeMax, row.portLabel]))
			.toEqual(expect.arrayContaining([
				['47', '47', null, null, '해당 없음'],
				['gre', 'gre', null, null, '해당 없음'],
				['253', '253', null, null, '해당 없음'],
			]));
		expect(result).toHaveLength(3);
	});

	it('defaults CIDR by ethertype, keeps explicit prefixes, and resolves remote names without selecting their rules', () => {
		const fullId = 'b142a290-7e89-4d21-9e1f-6ff447bc58b0';
		const result = buildSecurityGroupUnion([
			group('applied', [
				rule({ ethertype: 'IPv6' }), rule({ ethertype: 'IPv6', remote_ip_prefix: '::/0' }),
				rule({ remote_ip_prefix: '192.0.2.0/24' }),
				rule({ remote_group_id: 'named' }), rule({ remote_group_id: 'unnamed' }),
				rule({ remote_group_id: fullId }),
			]),
			group('named', [rule({ protocol: null, port_range_min: null, port_range_max: null })], 'database'),
			group('unnamed', [], ''),
		], ['applied']);
		expect(result.rows.map((row) => [row.remote, row.remoteLabel])).toEqual(expect.arrayContaining([
			[{ kind: 'cidr', value: '::/0' }, '전체 (::/0)'],
			[{ kind: 'cidr', value: '192.0.2.0/24' }, '192.0.2.0/24'],
			[{ kind: 'group', value: 'named' }, '보안 그룹: database'],
			[{ kind: 'group', value: 'unnamed' }, '보안 그룹: unnamed'],
			[{ kind: 'group', value: fullId }, `보안 그룹: ${fullId}`],
		]));
		expect(result.rows).toHaveLength(5);
		expect(result.missingGroupIds).toEqual([]);
	});

	it('deduplicates and reports missing applied IDs, including when no groups resolve', () => {
		const groups = [group('present', [])];
		expect(buildSecurityGroupUnion(groups, ['z-missing', 'present', 'a-missing', 'z-missing', 'present']))
			.toEqual({ appliedGroupIds: ['present'], missingGroupIds: ['a-missing', 'z-missing'], rows: [] });
		expect(buildSecurityGroupUnion([], ['missing', 'missing']))
			.toEqual({ appliedGroupIds: [], missingGroupIds: ['missing'], rows: [] });
		expect(buildSecurityGroupUnion([group('unselected', [rule()])], []))
			.toEqual({ appliedGroupIds: [], missingGroupIds: [], rows: [] });
	});

	it('has stable rows and keys under input permutations or source-ID changes, without mutating frozen input', () => {
		const groups = [
			group('b', [rule({ port_range_min: 8080, port_range_max: 8080 }), rule({ protocol: 'icmp', port_range_min: 8, port_range_max: 0 })]),
			group('a', [rule({ port_range_min: 100, port_range_max: 100 }), rule(), rule({ direction: 'egress', remote_ip_prefix: '192.0.2.0/24' })]),
		];
		const groupIds = ['b', 'a', 'missing', 'a'];
		const before = structuredClone({ groups, groupIds });
		for (const item of groups) {
			for (const source of item.rules) Object.freeze(source);
			Object.freeze(item.rules);
			Object.freeze(item);
		}
		Object.freeze(groups);
		Object.freeze(groupIds);
		const result = buildSecurityGroupUnion(groups, groupIds);
		expect(result).toEqual(buildSecurityGroupUnion(
			[...groups].reverse().map((item) => ({ ...item, rules: [...item.rules].reverse() })),
			[...groupIds].reverse(),
		));
		expect(result.rows).toEqual(buildSecurityGroupUnion(
			groups.map((item) => ({ ...item, id: `${item.id}-new`, rules: item.rules.map((source, index) => ({ ...source, id: `new-${index}` })) })),
			['a-new', 'b-new'],
		).rows);
		expect({ groups, groupIds }).toEqual(before);
		expect(result.rows.filter((row) => row.direction === 'ingress' && row.protocol === 'tcp')
			.map((row) => row.portLabel)).toEqual(['22', '100', '8080']);
	});
});
