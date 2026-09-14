import { cleanup, fireEvent, render, screen, within } from '@testing-library/svelte';
import { afterEach, describe, expect, it } from 'vitest';
import type { NetworkAgent, Service } from '$lib/types/adminServices';
import NetworkAgentTable from '../NetworkAgentTable.svelte';
import ServiceTable from '../ServiceTable.svelte';
import { COMPUTE_COLUMNS } from '../serviceColumns';

afterEach(cleanup);

function optionValue(label: string, optionLabel: string): string {
	const select = screen.getByLabelText(label) as HTMLSelectElement;
	const option = [...select.options].find((item) => item.textContent === optionLabel);
	if (!option) throw new Error(`Missing ${optionLabel} option for ${label}`);
	return option.value;
}

async function selectOption(label: string, optionLabel: string) {
	const select = screen.getByLabelText(label) as HTMLSelectElement;
	await fireEvent.change(select, { target: { value: optionValue(label, optionLabel) } });
}

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
	it('AND-combines Host, Alive, and Admin State while keeping unknown Alive distinct from down', async () => {
		render(NetworkAgentTable, { props: { agents, loading: false, emptyMessage: '데이터 없음' } });

		await selectOption('Host', 'host-a');
		await selectOption('Alive', 'down');
		await selectOption('Admin State', 'DOWN');
		expect(tableColumn(2)).toEqual(['host-a']);
		expect(tableColumn(4)).toEqual(['down']);

		await selectOption('Alive', '미확인');
		expect(tableColumn(2)).toEqual(['host-a']);
		expect(tableColumn(4)).toEqual(['미확인']);

		await selectOption('Admin State', 'UP');
		expect(screen.queryByRole('table')).toBeNull();
	});

	it('sorts hosts naturally in both directions', async () => {
		const sortable = [
			{ ...agents[0], id: 'ten', host: 'host10' },
			{ ...agents[1], id: 'two', host: 'host2' },
			{ ...agents[2], id: 'one', host: 'host1' },
		];
		render(NetworkAgentTable, { props: { agents: sortable, loading: false, emptyMessage: '데이터 없음' } });

		const hostSort = screen.getByRole('button', { name: 'Host 정렬' });
		await fireEvent.click(hostSort);
		expect(tableColumn(2)).toEqual(['host1', 'host2', 'host10']);
		await fireEvent.click(hostSort);
		expect(tableColumn(2)).toEqual(['host10', 'host2', 'host1']);
	});

	it('keeps a filter through refreshed rows and recovers after a zero-match refresh', async () => {
		const view = render(NetworkAgentTable, { props: { agents, loading: false, emptyMessage: '데이터 없음' } });
		await selectOption('Host', 'host-a');

		const refreshed = [
			{ ...agents[0], id: 'agent-refreshed', host: 'host-a', updated_at: '2026-09-14T11:00:00Z' },
			{ ...agents[2], id: 'agent-other', host: 'host-c' },
		];
		await view.rerender({ agents: refreshed, loading: true, emptyMessage: '데이터 없음' });
		expect(tableColumn(2)).toEqual(['host-a']);

		await view.rerender({ agents: [{ ...agents[2], id: 'agent-only', host: 'host-c' }], loading: false, emptyMessage: '데이터 없음' });
		expect(screen.queryByRole('table')).toBeNull();
		expect(screen.getByRole('option', { name: 'host-a (현재 데이터 없음)' })).toBeTruthy();

		await selectOption('Host', '전체');
		expect(tableColumn(2)).toEqual(['host-c']);
	});
});

describe('ServiceTable', () => {
	it('filters Status and State independently', async () => {
		const services: Service[] = [
			{ id: 'enabled-up', binary: 'nova-compute', host: 'host-1', status: 'enabled', state: 'up', zone: 'zone-a', updated_at: null, disabled_reason: null },
			{ id: 'enabled-down', binary: 'nova-compute', host: 'host-2', status: 'enabled', state: 'down', zone: 'zone-a', updated_at: null, disabled_reason: 'maintenance' },
			{ id: 'disabled-up', binary: 'nova-compute', host: 'host-3', status: 'disabled', state: 'up', zone: 'zone-b', updated_at: null, disabled_reason: 'manual' },
		];
		render(ServiceTable, { props: { services, columns: COMPUTE_COLUMNS, loading: false, emptyMessage: '데이터 없음' } });

		await selectOption('Status', 'enabled');
		await selectOption('State', 'down');
		expect(tableColumn(1)).toEqual(['host-2']);
		expect(screen.getByText('maintenance')).toBeTruthy();

		await selectOption('State', 'up');
		expect(tableColumn(1)).toEqual(['host-1']);
		expect(screen.queryByText('maintenance')).toBeNull();
	});
});
