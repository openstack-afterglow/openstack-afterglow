import { t } from '$lib/i18n/ns/instance';
import type { SecurityGroup, SecurityGroupRule } from '$lib/types/securityGroup';

export type SecurityGroupUnionGroup = Pick<SecurityGroup, 'id' | 'name'> & {
	readonly rules: readonly SecurityGroupRule[];
};

export type SecurityGroupRemote = { kind: 'cidr' | 'group'; value: string };

interface UnionRule {
	direction: string;
	ethertype: string;
	protocol: string | null;
	/** Transport bounds, or ICMP type/code. Null means any; non-port protocols use null. */
	portRangeMin: number | null;
	portRangeMax: number | null;
	remote: SecurityGroupRemote;
}

export interface SecurityGroupUnionRow extends UnionRule {
	/** Semantic identity: excludes source group/rule IDs and display names. */
	key: string;
	protocolLabel: string;
	portLabel: string;
	remoteLabel: string;
}

export interface SecurityGroupUnion {
	appliedGroupIds: string[];
	missingGroupIds: string[];
	rows: SecurityGroupUnionRow[];
}

function normalizeProtocol(protocol: string | null): string | null {
	switch (protocol?.toLowerCase()) {
		case undefined:
		case 'any': return null;
		case '6':
		case 'tcp': return 'tcp';
		case '17':
		case 'udp': return 'udp';
		case '132':
		case 'sctp': return 'sctp';
		case '1':
		case 'icmp': return 'icmp';
		case '58':
		case 'icmpv6':
		case 'ipv6-icmp': return 'ipv6-icmp';
		default: return protocol;
	}
}

function isTransport(protocol: string | null): boolean {
	return protocol === 'tcp' || protocol === 'udp' || protocol === 'sctp';
}

function normalizeRule(rule: SecurityGroupRule): UnionRule {
	const protocol = normalizeProtocol(rule.protocol);
	let min = rule.port_range_min;
	let max = rule.port_range_max;
	if (protocol === 'icmp' || protocol === 'ipv6-icmp') {
		if (min === -1) min = null;
		if (max === -1) max = null;
	} else if (!isTransport(protocol)) {
		min = null;
		max = null;
	}
	return {
		direction: rule.direction,
		ethertype: rule.ethertype,
		protocol,
		portRangeMin: min,
		portRangeMax: max,
		remote: rule.remote_group_id
			? { kind: 'group', value: rule.remote_group_id }
			: { kind: 'cidr', value: rule.remote_ip_prefix ?? (rule.ethertype === 'IPv6' ? '::/0' : '0.0.0.0/0') },
	};
}

function ruleKey(rule: UnionRule): string {
	return JSON.stringify([
		rule.direction, rule.ethertype, rule.remote.kind, rule.remote.value,
		rule.protocol, rule.portRangeMin, rule.portRangeMax,
	]);
}

function mergeTransport(rules: UnionRule[]): UnionRule[] {
	const anyPorts = rules.find((rule) => rule.portRangeMin === null);
	if (anyPorts) return [anyPorts];

	// Only newly normalized records are sorted/mutated, never API objects.
	rules.sort((a, b) => a.portRangeMin! - b.portRangeMin! || a.portRangeMax! - b.portRangeMax!);
	const merged: UnionRule[] = [];
	for (const rule of rules) {
		const previous = merged.at(-1);
		if (previous && rule.portRangeMin! <= previous.portRangeMax! + 1) {
			previous.portRangeMax = Math.max(previous.portRangeMax!, rule.portRangeMax!);
		} else {
			merged.push(rule);
		}
	}
	for (const rule of merged) {
		if (rule.portRangeMin === 1 && rule.portRangeMax === 65535) {
			rule.portRangeMin = null;
			rule.portRangeMax = null;
		}
	}
	return merged;
}

function protocolLabel(protocol: string | null): string {
	if (protocol === null) return t('securityGroupUnion.any');
	if (isTransport(protocol)) return protocol.toUpperCase();
	if (protocol === 'ipv6-icmp') return 'ICMPv6';
	if (protocol === 'icmp') return 'ICMP';
	return protocol;
}

function portLabel(rule: UnionRule): string {
	if (rule.protocol === null) return t('securityGroupUnion.any');
	if (rule.protocol === 'icmp' || rule.protocol === 'ipv6-icmp') {
		const any = t('securityGroupUnion.any');
		return t('securityGroupUnion.icmpTypeCode', {
			type: rule.portRangeMin === null ? any : String(rule.portRangeMin),
			code: rule.portRangeMax === null ? any : String(rule.portRangeMax),
		});
	}
	if (!isTransport(rule.protocol)) return t('securityGroupUnion.notApplicable');
	if (rule.portRangeMin === null) return t('securityGroupUnion.any');
	return rule.portRangeMin === rule.portRangeMax
		? String(rule.portRangeMin)
		: `${rule.portRangeMin}–${rule.portRangeMax}`;
}

function remoteLabel(remote: SecurityGroupRemote, groups: ReadonlyMap<string, SecurityGroupUnionGroup>): string {
	if (remote.kind === 'group') return t('securityGroupUnion.remoteGroup', { name: groups.get(remote.value)?.name || remote.value });
	return remote.value === '0.0.0.0/0' || remote.value === '::/0'
		? t('securityGroupUnion.anyCidr', { cidr: remote.value })
		: remote.value;
}

function compareText(left: string | null, right: string | null): number {
	if (left === right) return 0;
	if (left === null) return -1;
	if (right === null) return 1;
	return left < right ? -1 : 1;
}

/**
 * Exact union of only the requested groups. Project groups also resolve remote
 * names, but their rules are never implicitly selected. Missing IDs stay visible.
 * CIDRs are exact strings (no containment calculus); ICMP pairs are deduped, not
 * interval-merged or wildcard-subsumed. IDs use code-unit ordering; rows sort by
 * semantic dimensions, then numeric bounds. This is not an authorization decision.
 *
 * Returned applied IDs are the resolved subset; missing IDs are reported once.
 * Full 1–65535 transport coverage is canonicalized to null bounds (any ports).
 * Rows carry display labels in the active locale (translated at call time)
 * alongside normalized semantic fields; keys and ordering never use labels.
 */
export function buildSecurityGroupUnion(
	groups: readonly SecurityGroupUnionGroup[],
	groupIds: readonly string[],
): SecurityGroupUnion {
	const groupsById = new Map(groups.map((group) => [group.id, group]));
	const appliedGroupIds: string[] = [];
	const missingGroupIds: string[] = [];
	const targets = new Map<string, UnionRule[]>();
	for (const id of [...new Set(groupIds)].sort()) {
		const group = groupsById.get(id);
		if (!group) {
			missingGroupIds.push(id);
			continue;
		}
		appliedGroupIds.push(id);
		for (const source of group.rules) {
			const rule = normalizeRule(source);
			const key = JSON.stringify([rule.direction, rule.ethertype, rule.remote.kind, rule.remote.value]);
			const bucket = targets.get(key);
			if (bucket) bucket.push(rule);
			else targets.set(key, [rule]);
		}
	}

	const union: UnionRule[] = [];
	for (const rules of targets.values()) {
		const anyProtocol = rules.find((rule) => rule.protocol === null);
		if (anyProtocol) {
			union.push(anyProtocol);
			continue;
		}
		const transports = new Map<string, UnionRule[]>();
		const otherRules = new Map<string, UnionRule>();
		for (const rule of rules) {
			if (!isTransport(rule.protocol)) {
				otherRules.set(ruleKey(rule), rule);
				continue;
			}
			const bucket = transports.get(rule.protocol!);
			if (bucket) bucket.push(rule);
			else transports.set(rule.protocol!, [rule]);
		}
		for (const bucket of transports.values()) union.push(...mergeTransport(bucket));
		union.push(...otherRules.values());
	}

	const rows = union.map((rule): SecurityGroupUnionRow => ({
		...rule,
		key: ruleKey(rule),
		protocolLabel: protocolLabel(rule.protocol),
		portLabel: portLabel(rule),
		remoteLabel: remoteLabel(rule.remote, groupsById),
	}));
	rows.sort((a, b) =>
		compareText(a.direction, b.direction) || compareText(a.ethertype, b.ethertype)
		|| compareText(a.remote.kind, b.remote.kind) || compareText(a.remote.value, b.remote.value)
		|| compareText(a.protocol, b.protocol)
		|| (a.portRangeMin ?? -1) - (b.portRangeMin ?? -1)
		|| (a.portRangeMax ?? -1) - (b.portRangeMax ?? -1));
	return { appliedGroupIds, missingGroupIds, rows };
}
