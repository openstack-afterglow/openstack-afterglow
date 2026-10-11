import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/svelte';
import type { SubnetDetail } from '$lib/types/networks';
import SubnetSection from '../SubnetSection.svelte';

const sampleSubnets: SubnetDetail[] = [
	{
		id: 'sub-abc-123',
		name: 'public-subnet-1',
		cidr: '192.168.1.0/24',
		ip_version: 4,
		gateway_ip: '192.168.1.1',
		dhcp_enabled: true,
	},
];

describe('SubnetSection Component', () => {
	it('renders subnet title as an accessible link to /admin/subnets/{id}', () => {
		render(SubnetSection, {
			props: {
				subnets: sampleSubnets,
				onAdd: vi.fn(),
				onSave: vi.fn(),
				onDelete: vi.fn(),
				deletingSubnetId: null,
				addError: '',
				saveError: '',
				addingSubnet: false,
				savingSubnet: false,
			},
		});

		const link = screen.getByRole('link', { name: 'public-subnet-1' });
		expect(link).toBeTruthy();
		expect(link.getAttribute('href')).toBe('/admin/subnets/sub-abc-123');
	});
});
