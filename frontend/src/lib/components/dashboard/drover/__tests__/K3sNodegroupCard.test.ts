import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/svelte';
import type { K3sNodegroup } from '$lib/types/k3s';

import K3sNodegroupCard from '../K3sNodegroupCard.svelte';

function buildNodegroup(overrides: Partial<K3sNodegroup> = {}): K3sNodegroup {
	return {
		id: 'ng-1',
		cluster_id: 'cluster-1',
		name: 'gpu-workers',
		role: 'agent',
		node_count: 2,
		flavor_id: 'gpu.large',
		image_id: null,
		labels: {},
		taints: [],
		is_default: false,
		stampede_enabled: true,
		min_size: 0,
		max_size: 5,
		stampede_state: {
			capacity: {
				allocatable: { gpu: 4 },
			},
			in_flight_count: 2,
		},
		vms: [
			{ vm_id: 'vm-1', name: 'gpu-1', status: 'RUNNING' },
			{ vm_id: 'vm-2', name: 'gpu-2', status: 'BUILD' },
		],
		created_at: '2026-07-03T10:00:00Z',
		updated_at: '2026-07-03T10:00:00Z',
		...overrides,
	};
}

describe('K3sNodegroupCard', () => {
	it('shows GPU and in-flight badges for stampede nodegroups with GPU capacity', () => {
		render(K3sNodegroupCard, {
			props: {
				nodegroup: buildNodegroup(),
			},
		});

		expect(screen.getByText('gpu-workers')).toBeTruthy();
		expect(screen.getByText('Stampede')).toBeTruthy();
		expect(screen.getByText('GPU 4')).toBeTruthy();
		expect(screen.getByRole('status').textContent).toContain('+2');
		expect(screen.getByText((_, element) => element?.tagName === 'SPAN' && /(^|\D)1\/2$/.test(element.textContent?.replace(/\s+/g, '') ?? ''))).toBeTruthy();
	});
});
