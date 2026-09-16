import { cleanup, fireEvent, render, screen } from '@testing-library/svelte';
import { afterEach, describe, expect, it } from 'vitest';
import EndpointsTable from '../EndpointsTable.svelte';
import StoragePoolsList from '../StoragePoolsList.svelte';
import type { EndpointGroup, StoragePool } from '$lib/types/adminServices';

afterEach(cleanup);

const endpoints: EndpointGroup[] = [
	{
		service_id: 'compute-east',
		name: 'nova',
		service: 'compute',
		region: 'RegionOne',
		endpoints: {
			public: 'https://nova.public.example/v2',
			internal: 'https://nova.internal.example/v2',
		},
	},
	{
		service_id: 'identity-east',
		name: 'keystone',
		service: 'identity',
		region: 'RegionOne',
		endpoints: { public: 'https://identity.public.example/v3' },
	},
	{
		service_id: 'compute-west',
		name: 'nova-west',
		service: 'compute',
		region: 'RegionTwo',
		endpoints: { admin: 'https://nova.west.example/v2' },
	},
];

const pools: StoragePool[] = [
	{
		name: 'hundred-gib',
		volume_backend_name: 'ceph-a',
		driver_version: '6.0',
		storage_protocol: 'ceph',
		vendor_name: 'Ceph',
		total_capacity_gb: 100,
		free_capacity_gb: 40,
		allocated_capacity_gb: 60,
	},
	{
		name: 'nine-gib',
		volume_backend_name: 'ceph-b',
		driver_version: '6.1',
		storage_protocol: 'ceph',
		vendor_name: 'Ceph',
		total_capacity_gb: 9,
		free_capacity_gb: 3,
		allocated_capacity_gb: 6,
	},
	{
		name: 'twenty-gib',
		volume_backend_name: 'lvm',
		driver_version: '3.4',
		storage_protocol: 'iSCSI',
		vendor_name: 'LVM',
		total_capacity_gb: 20,
		free_capacity_gb: 5,
		allocated_capacity_gb: 15,
	},
];

describe('admin service endpoint and storage pool lists', () => {
	it('filters endpoints by exact service type and region without hiding their URLs', async () => {
		const { rerender } = render(EndpointsTable, {
			props: { endpoints, loading: false, emptyMessage: 'No endpoints' },
		});

		await fireEvent.change(screen.getByLabelText('서비스 유형'), { target: { value: 'value:compute' } });
		await fireEvent.change(screen.getByLabelText('리전'), { target: { value: 'value:RegionOne' } });

		expect(screen.getByRole('cell', { name: 'nova' })).toBeTruthy();
		expect(screen.getByText('https://nova.public.example/v2')).toBeTruthy();
		expect(screen.getByText('https://nova.internal.example/v2')).toBeTruthy();
		expect(screen.queryByRole('cell', { name: 'nova-west' })).toBeNull();
		expect(screen.queryByRole('cell', { name: 'keystone' })).toBeNull();

		await rerender({ endpoints: [...endpoints], loading: false, emptyMessage: 'No endpoints' });
		expect(screen.getByRole('cell', { name: 'nova' })).toBeTruthy();
		expect(screen.queryByRole('cell', { name: 'nova-west' })).toBeNull();
	});

	it('searches endpoint hosts, distinguishes no matches, and resets the full endpoint list', async () => {
		render(EndpointsTable, { props: { endpoints, loading: false, emptyMessage: 'No endpoints' } });
		const search = screen.getByLabelText('검색');

		await fireEvent.input(search, { target: { value: 'nova.internal.example' } });
		expect(screen.getByRole('cell', { name: 'nova' })).toBeTruthy();
		expect(screen.queryByRole('cell', { name: 'keystone' })).toBeNull();

		await fireEvent.input(search, { target: { value: 'does-not-exist' } });
		expect(screen.queryByRole('table')).toBeNull();

		await fireEvent.click(screen.getByRole('button', { name: '필터·정렬 초기화' }));
		expect(screen.getByRole('cell', { name: 'nova' })).toBeTruthy();
		expect(screen.getByRole('cell', { name: 'keystone' })).toBeTruthy();
		expect(screen.getByRole('cell', { name: 'nova-west' })).toBeTruthy();
	});

	it('sorts storage pools by numeric capacity rather than formatted capacity text', async () => {
		render(StoragePoolsList, { props: { pools, loading: false, emptyMessage: 'No pools' } });

		await fireEvent.change(screen.getByLabelText('정렬 기준'), { target: { value: 'total_capacity' } });

		expect(screen.getAllByRole('article').map((pool) => pool.getAttribute('aria-label'))).toEqual([
			'nine-gib 스토리지 풀',
			'twenty-gib 스토리지 풀',
			'hundred-gib 스토리지 풀',
		]);
	});
});
