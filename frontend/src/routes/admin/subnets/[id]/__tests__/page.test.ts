import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/svelte';
import { writable, type Writable } from 'svelte/store';
import type { AdminSubnetDetail } from '$lib/types/networks';
import { setLocale } from '$lib/i18n/runtime.svelte';
import { page } from '$app/stores';
import { tick } from 'svelte';
import { t } from '$lib/i18n/ns/admin-network';

const { mockGet } = vi.hoisted(() => ({ mockGet: vi.fn() }));

vi.mock('$app/stores', () => ({
	page: writable({ params: { id: 'sub-100' }, data: {} }),
}));

vi.mock('$lib/stores/auth', () => ({
	auth: writable({ token: 'token', userId: 'admin-user', projectId: 'admin-project' }),
}));

vi.mock('$lib/api/client', () => ({
	api: { get: mockGet },
	ApiError: class ApiError extends Error {
		status: number;
		constructor(message: string, status = 500) {
			super(message);
			this.status = status;
		}
	},
}));

import Page from '../+page.svelte';

import { subnetFixture as sampleSubnetDetail } from '$lib/components/admin/networks/__tests__/subnetFixture';
const routePage = page as unknown as Writable<{ params: { id: string }; data: Record<string, never> }>;

beforeEach(() => {
	mockGet.mockReset();
	routePage.set({ params: { id: 'sub-100' }, data: {} });
	setLocale('ko');
});

describe('Admin Subnet Detail Page (/admin/subnets/[id])', () => {
	it('renders warning alert and port-sourced DHCP rows when scheduler data is unavailable', async () => {
		const partialSubnet: AdminSubnetDetail = {
			...sampleSubnetDetail,
			dhcp_agent_data_available: false,
			dhcp_bindings: [
				{
					agent_id: null,
					host: 'ovn-chassis-02',
					binary: null,
					availability_zone: null,
					alive: null,
					admin_state_up: null,
					source: 'port',
					ip_addresses: ['10.200.0.3'],
					port_ids: ['port-ovn-dhcp'],
				},
			],
		};
		mockGet.mockResolvedValueOnce(partialSubnet);

		render(Page);

		expect(await screen.findByText('ovn-chassis-02')).toBeTruthy();
		expect(screen.getByText(t('subnetDetailPage.schedulerUnavailable')).closest('[role="status"]')).toBeTruthy();
		expect(screen.getByText('10.200.0.3')).toBeTruthy();
		expect(screen.getByText('port-ovn-dhcp')).toBeTruthy();
	});

	it('paginates dense allocation tables at twenty rows', async () => {
		const allocations = Array.from({ length: 21 }, (_, index) => ({
			ip_address: `10.200.0.${index + 101}`,
			port_id: `port-${index + 101}`,
			port_name: `workload-port-${index + 101}`,
			device_owner: 'compute:nova',
			device_id: `instance-${index + 101}`,
			device_name: null,
			project_id: 'proj-admin-1',
			binding_host_id: `compute-${index + 1}`,
		}));
		mockGet.mockResolvedValueOnce({ ...sampleSubnetDetail, allocations });

		render(Page);

		expect(await screen.findByText('10.200.0.101')).toBeTruthy();
		expect(screen.getByText('10.200.0.120')).toBeTruthy();
		expect(screen.queryByText('10.200.0.121')).toBeNull();

		await fireEvent.click(screen.getByRole('button', { name: '다음 →' }));
		expect(screen.getByText('10.200.0.121')).toBeTruthy();
		expect(screen.queryByText('10.200.0.101')).toBeNull();
	});

	it('paginates the port tab independently', async () => {
		const ports = Array.from({ length: 21 }, (_, index) => ({
			id: `port-${index + 101}`,
			name: `workload-port-${index + 101}`,
			status: 'ACTIVE',
			mac_address: `fa:16:3e:00:00:${String(index + 1).padStart(2, '0')}`,
			device_owner: 'compute:nova',
			device_id: `instance-${index + 101}`,
			device_name: null,
			project_id: 'proj-admin-1',
			ip_addresses: [`10.200.0.${index + 101}`],
			binding_host_id: `compute-${index + 1}`,
		}));
		mockGet.mockResolvedValueOnce({ ...sampleSubnetDetail, ports });

		render(Page);
		await screen.findByText('10.200.0.15');
		await fireEvent.click(screen.getByRole('button', { name: '포트 · 21' }));

		expect(screen.getByText('workload-port-101')).toBeTruthy();
		expect(screen.getByText('workload-port-120')).toBeTruthy();
		expect(screen.queryByText('workload-port-121')).toBeNull();

		await fireEvent.click(screen.getByRole('button', { name: '다음 →' }));
		expect(screen.getByText('workload-port-121')).toBeTruthy();
		expect(screen.queryByText('workload-port-101')).toBeNull();
	});

	it('renders error alert when API fetch fails', async () => {
		mockGet.mockRejectedValueOnce(new Error('네트워크 연결 오류'));

		render(Page);

		expect(await screen.findByRole('alert')).toBeTruthy();
		expect(screen.getByText('네트워크 연결 오류')).toBeTruthy();
	});
	it('clears standalone metadata on route changes and rejects the old refresh response', async () => {
		let resolveOld!: (detail: AdminSubnetDetail) => void;
		const oldRefresh = new Promise<AdminSubnetDetail>((resolve) => { resolveOld = resolve; });
		mockGet.mockResolvedValueOnce(sampleSubnetDetail).mockReturnValueOnce(oldRefresh).mockResolvedValueOnce({
			...sampleSubnetDetail, id: 'sub-next', name: 'next-subnet', network_id: 'next-network', network_name: 'next-network-name',
		});
		render(Page);
		await screen.findByText('sub-100');
		await fireEvent.click(screen.getByRole('button', { name: t('subnetDetailPage.refresh') }));
		routePage.set({ params: { id: 'sub-next' }, data: {} });
		await screen.findByText('sub-next');
		resolveOld(sampleSubnetDetail);
		await tick();
		expect(screen.queryByText('sub-100')).toBeNull();
		expect(screen.queryByText('production-network')).toBeNull();
		expect(screen.getByRole('link', { name: 'next-network-name' }).getAttribute('href')).toBe('/admin/networks/next-network');
	});
});
