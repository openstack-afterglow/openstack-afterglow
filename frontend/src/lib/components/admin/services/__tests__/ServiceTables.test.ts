import { cleanup, fireEvent, render, screen, within } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import type { NetworkAgent, Service } from '$lib/types/adminServices';
import NetworkAgentTable from '../NetworkAgentTable.svelte';
import ServiceTable from '../ServiceTable.svelte';
import { COMPUTE_COLUMNS } from '../serviceColumns';
import { setLocale } from '$lib/i18n/runtime.svelte';
import { t } from '$lib/i18n/ns/admin-ops';
import { t as commonT } from '$lib/i18n/ns/common';
import { clearColumn, setColumnValues, sortColumn } from './tableInteractions';
beforeEach(() => setLocale('en'));

afterEach(cleanup);


function tableColumn(column: number): string[] {
	return screen.getAllByRole('row').slice(1).map((row) => {
		const cell = within(row).getAllByRole('cell')[column];
		return cell.textContent?.trim() ?? '';
	});
}

const agents: NetworkAgent[] = [
	{
		id: 'agent-null', binary: 'neutron-openvswitch-agent', host: 'host-a', agent_type: 'Open vSwitch agent',
		availability_zone: 'zone-a', alive: null, admin_state_up: false, updated_at: '2026-09-14T10:00:00Z',
	},
	{
		id: 'agent-down', binary: 'neutron-openvswitch-agent', host: 'host-a', agent_type: 'Open vSwitch agent',
		availability_zone: 'zone-a', alive: false, admin_state_up: false, updated_at: '2026-09-14T10:01:00Z',
	},
	{
		id: 'agent-up', binary: 'neutron-l3-agent', host: 'host-b', agent_type: 'L3 agent',
		availability_zone: 'zone-b', alive: true, admin_state_up: true, updated_at: '2026-09-14T10:02:00Z',
	},
];

describe('NetworkAgentTable', () => {
	it('combines multiple values within a column and intersects other columns while preserving unknown alive', async () => {
		render(NetworkAgentTable, { props: { agents, loading: false, emptyMessage: 'No data' } });
		await setColumnValues(t('services.columns.host'), ['host-a']);
		await setColumnValues(t('services.columns.alive'), [t('services.state.down'), commonT('table.missing')]);
		expect(tableColumn(2)).toEqual(['host-a', 'host-a']);
		await setColumnValues(t('services.columns.alive'), [commonT('table.missing')]);
		expect(tableColumn(2)).toEqual(['host-a']);
		await setColumnValues(t('services.columns.adminState'), []);
		expect(tableColumn(2)).toEqual([]);
		expect(screen.getAllByRole('columnheader')).toHaveLength(7);
	});

	it('cycles natural host sorting ascending, descending and incoming order', async () => {
		const sortable = [
			{ ...agents[1], id: 'two', host: 'host2' },
			{ ...agents[0], id: 'ten', host: 'host10' },
			{ ...agents[2], id: 'one', host: 'host1' },
		];
		render(NetworkAgentTable, { props: { agents: sortable, loading: false, emptyMessage: 'No data' } });
		await sortColumn(t('services.columns.host'));
		expect(tableColumn(2)).toEqual(['host1', 'host2', 'host10']);
		await sortColumn(t('services.columns.host'));
		expect(tableColumn(2)).toEqual(['host10', 'host2', 'host1']);
		await sortColumn(t('services.columns.host'));
		expect(tableColumn(2)).toEqual(['host2', 'host10', 'host1']);
	});

	it('retains regex, filters and descending sort through loading and absent-value refresh', async () => {
		const rendered = render(NetworkAgentTable, { props: { agents, loading: false, emptyMessage: 'No data' } });
		await fireEvent.input(screen.getByRole('searchbox'), { target: { value: '^host-(a|b)$' } });
		await setColumnValues(t('services.columns.host'), ['host-a']);
		await sortColumn(t('services.columns.updated'));
		await sortColumn(t('services.columns.updated'));
		expect(tableColumn(2)).toEqual(['host-a', 'host-a']);
		await rendered.rerender({ agents: [{ ...agents[2], id: 'new', host: 'host-b' }], loading: true, emptyMessage: 'No data' });
		expect(tableColumn(2)).toEqual([]);
		await clearColumn(t('services.columns.host'));
		expect(tableColumn(2)).toEqual(['host-b']);
		await fireEvent.input(screen.getByRole('searchbox'), { target: { value: '[' } });
		expect(tableColumn(2)).toEqual([]);
		expect(screen.getByRole('searchbox').getAttribute('aria-invalid')).toBe('true');
	});
});

describe('ServiceTable', () => {
	it('filters Status and State independently and keeps invalid timestamps last in descending order', async () => {
		const services: Service[] = [
			{ id: 'enabled-up', binary: 'nova-compute', host: 'host-1', status: 'enabled', state: 'up', zone: 'zone-a', updated_at: null, disabled_reason: null },
			{ id: 'enabled-down', binary: 'nova-compute', host: 'host-2', status: 'enabled', state: 'down', zone: 'zone-a', updated_at: '2026-09-14T10:00:00Z', disabled_reason: 'maintenance' },
			{ id: 'disabled-up', binary: 'nova-compute', host: 'host-3', status: 'disabled', state: 'up', zone: 'zone-b', updated_at: 'invalid', disabled_reason: 'manual' },
		];
		render(ServiceTable, { props: { services, columns: COMPUTE_COLUMNS, loading: false, emptyMessage: 'No data' } });
		await setColumnValues(t('services.columns.status'), ['enabled']);
		await setColumnValues(t('services.columns.state'), ['down']);
		expect(tableColumn(1)).toEqual(['host-2']);
		await clearColumn(t('services.columns.status'));
		await clearColumn(t('services.columns.state'));
		await sortColumn(t('services.columns.updated'));
		await sortColumn(t('services.columns.updated'));
		expect(tableColumn(1)).toEqual(['host-2', 'host-1', 'host-3']);
	});
});
