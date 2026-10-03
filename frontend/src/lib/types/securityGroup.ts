import type { QuotaItem } from './quotas';

export interface SecurityGroupRule {
	id: string;
	direction: string;
	protocol: string | null;
	port_range_min: number | null;
	port_range_max: number | null;
	remote_ip_prefix: string | null;
	ethertype: string;
	remote_group_id: string | null;
}

export interface SecurityGroup {
	id: string;
	name: string;
	description: string;
	rules: SecurityGroupRule[];
}

export interface SecurityGroupQuota {
	security_group: QuotaItem;
	security_group_rule: QuotaItem;
}

export interface SecurityGroupInstance {
	id: string;
	name: string;
	status: string;
}

export interface SecurityGroupRuleDraft {
	direction: string;
	protocol: string;
	port_range_min: string;
	port_range_max: string;
	remote_ip_prefix: string;
	remote_group_id: string;
	ethertype: string;
}
