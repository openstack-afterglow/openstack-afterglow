import { beforeEach, describe, it, expect, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/svelte';
import type { K3sNodegroup } from '$lib/types/k3s';
import { writable, type Writable } from 'svelte/store';
import { serviceCapabilities } from '$lib/stores/servicePermissions';
vi.mock('$lib/stores/servicePermissions', () => ({ serviceCapabilities: writable<(leaf: string) => boolean>(() => false) }));

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
	beforeEach(() => (serviceCapabilities as Writable<(leaf: string) => boolean>).set(() => false));
	it('separates editor and administrator nodegroup controls and responds to downgrade', async () => {
		const onEdit = vi.fn();
		const onDelete = vi.fn();
		(serviceCapabilities as Writable<(leaf: string) => boolean>).set((leaf) => leaf === 'drover-clusters_editor');
		render(K3sNodegroupCard, { nodegroup: buildNodegroup(), onEdit, onDelete });
		await fireEvent.click(screen.getByRole('button', { name: '수정' }));
		expect(onEdit).toHaveBeenCalledOnce();
		expect(screen.queryByRole('button', { name: '삭제' })).toBeNull();
		(serviceCapabilities as Writable<(leaf: string) => boolean>).set((leaf) => leaf === 'drover-clusters_admin');
		await vi.waitFor(() => expect(screen.queryByRole('button', { name: '수정' })).toBeNull());
		await fireEvent.click(screen.getByRole('button', { name: '삭제' }));
		expect(onDelete).toHaveBeenCalledOnce();
		(serviceCapabilities as Writable<(leaf: string) => boolean>).set(() => false);
		await vi.waitFor(() => expect(screen.queryByRole('button', { name: '삭제' })).toBeNull());
	});
	it('shows GPU and in-flight badges for stampede nodegroups with GPU capacity', () => {
		render(K3sNodegroupCard, {
			props: {
				nodegroup: buildNodegroup(),
			},
		});

		expect(screen.getByText('gpu-workers')).toBeTruthy();
		expect(screen.getByText('Stampede')).toBeTruthy();
		expect(screen.getByText('GPU 4')).toBeTruthy();
		const provisioning = screen.getByRole('status');
		expect(provisioning.textContent).toMatch(/\+?2\b/);
		expect(provisioning.getAttribute('data-variant')).toBe('pulse');
		const vmCounts = screen.getByText((_, element) =>
			element?.tagName === 'SPAN' && /\b1\s*\/\s*2\b/.test(element.textContent ?? ''),
		);
		expect(vmCounts.previousElementSibling?.textContent?.match(/\d+/g)).toEqual(['2']);
	});
});
