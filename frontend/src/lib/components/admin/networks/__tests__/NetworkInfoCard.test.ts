import { render, screen } from '@testing-library/svelte';
import { describe, expect, it } from 'vitest';
import type { AdminNetworkDetail } from '$lib/types/networks';
import NetworkInfoCard from '../NetworkInfoCard.svelte';

const baseNetwork: AdminNetworkDetail = {
	id: 'net-1234-5678-90ab-cdef',
	name: 'admin-net',
	status: 'ACTIVE',
	subnets: ['sub-1', 'sub-2'],
	is_external: true,
	is_shared: false,
	subnet_details: [],
	routers: [],
	project_id: 'proj-1',
	provider_network_type: null,
	provider_segmentation_id: null,
	provider_physical_network: null,
};

describe('NetworkInfoCard', () => {
	it('keeps the full owner ID independently of a resolved owner name', async () => {
		const { rerender } = render(NetworkInfoCard, { network: baseNetwork, ownerName: 'Owner project' });
		expect(screen.getByText('Owner project')).toBeTruthy();
		expect(screen.getByText('proj-1')).toBeTruthy();
		await rerender({ network: baseNetwork, ownerName: undefined });
		expect(screen.queryByText('Owner project')).toBeNull();
		expect(screen.getByText('proj-1')).toBeTruthy();
	});

	it('shows VLAN segmentation and physical network metadata', () => {
		const vlanNetwork: AdminNetworkDetail = {
			...baseNetwork,
			provider_network_type: 'vlan',
			provider_segmentation_id: 100,
			provider_physical_network: 'physnet1',
		};

		render(NetworkInfoCard, {
			props: { network: vlanNetwork },
		});

		expect(screen.getByText('VLAN')).toBeTruthy();
		expect(screen.getByText('100')).toBeTruthy();
		expect(screen.getByText('physnet1')).toBeTruthy();
	});

	it('removes physical network metadata when the provider changes to VXLAN with no physical network', async () => {
		const vxlanNetwork: AdminNetworkDetail = {
			...baseNetwork,
			provider_network_type: 'vxlan',
			provider_segmentation_id: 5001,
			provider_physical_network: null,
		};

		const { rerender } = render(NetworkInfoCard, {
			props: { network: { ...baseNetwork, provider_network_type: 'vlan', provider_physical_network: 'physnet1' } },
		});
		expect(screen.getByText('physnet1')).toBeTruthy();
		await rerender({ network: vxlanNetwork });

		expect(screen.getByText('VXLAN')).toBeTruthy();
		expect(screen.getByText('5001')).toBeTruthy();
		expect(screen.queryByText('physnet1')).toBeNull();
	});

	it('renders em dash when segmentation ID is missing for VLAN or VXLAN', () => {
		const missingIdNetwork: AdminNetworkDetail = {
			...baseNetwork,
			provider_network_type: 'vlan',
			provider_segmentation_id: null,
			provider_physical_network: 'physnet2',
		};

		render(NetworkInfoCard, {
			props: { network: missingIdNetwork },
		});

		expect(screen.getByText('—')).toBeTruthy();
	});

	it('omits provider metadata for flat/unrelated or absent provider type', () => {
		const flatNetwork: AdminNetworkDetail = {
			...baseNetwork,
			provider_network_type: 'flat',
			provider_segmentation_id: null,
			provider_physical_network: 'physnet1',
		};

		render(NetworkInfoCard, {
			props: { network: flatNetwork },
		});

		expect(screen.queryByText('flat')).toBeNull();
		expect(screen.queryByText('physnet1')).toBeNull();
	});
});
