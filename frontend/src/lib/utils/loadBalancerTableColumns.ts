import { t } from '$lib/i18n/ns/network-resources';
import { t as tc } from '$lib/i18n/ns/common';
import type { Listener, Pool, Member } from '$lib/types/loadbalancer';
import type { TableColumn } from './tableView.svelte';

export const listenerColumns = (): TableColumn<Listener>[] => [
	{ key: 'name', label: t('network.labels.name'), value: row => row.name || row.id },
	{ key: 'protocol', label: t('securityGroup.rules.protocol'), value: row => row.protocol },
	{ key: 'port', label: t('lb.form.port'), value: row => row.protocol_port },
	{ key: 'status', label: t('network.labels.status'), value: row => row.status },
];

export const poolColumns = (): TableColumn<Pool>[] => [
	{ key: 'name', label: t('network.labels.name'), value: row => row.name || row.id },
	{ key: 'protocol', label: t('securityGroup.rules.protocol'), value: row => row.protocol },
	{ key: 'algorithm', label: tc('table.algorithm'), value: row => row.lb_algorithm, format: value => t('lb.algorithm.label', { algorithm: String(value) }) },
	{ key: 'status', label: t('network.labels.status'), value: row => row.status },
];

export const memberColumns = (): TableColumn<Member>[] => [
	{ key: 'address', label: t('lb.form.ipAddress'), value: row => row.address },
	{ key: 'port', label: t('lb.form.port'), value: row => row.protocol_port },
	{ key: 'weight', label: t('lb.form.weight'), value: row => row.weight },
	{ key: 'status', label: t('network.labels.status'), value: row => row.status },
];
