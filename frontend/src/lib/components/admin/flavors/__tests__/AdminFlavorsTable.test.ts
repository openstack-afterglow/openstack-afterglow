import { render, screen, within } from '@testing-library/svelte';
import { describe, expect, it, vi } from 'vitest';
import type { Flavor } from '$lib/types/flavor';
import AdminFlavorsTable from '../AdminFlavorsTable.svelte';

function flavor(overrides: Partial<Flavor>): Flavor {
	return {
		id: 'flavor-id',
		name: 'flavor-name',
		vcpus: 8,
		ram: 16384,
		disk: 0,
		is_public: false,
		description: null,
		extra_specs: {},
		is_gpu: true,
		gpu_count: 1,
		...overrides,
	};
}

function rowFor(name: string): HTMLElement {
	const row = screen.getByText(name).closest('tr');
	expect(row).not.toBeNull();
	return row as HTMLElement;
}

describe('AdminFlavorsTable access-policy badges', () => {
	it('shows the effective access mode only beside Private GPU flavors', () => {
		render(AdminFlavorsTable, {
			flavors: [
				flavor({
					id: 'quota-gpu',
					name: 'quota.gpu',
					extra_specs: { 'afterglow:access_mode': 'gpu_quota' },
				}),
				flavor({
					id: 'manual-gpu',
					name: 'manual.gpu',
					extra_specs: { 'afterglow:access_mode': 'manual' },
				}),
				flavor({
					id: 'public-gpu',
					name: 'public.gpu',
					is_public: true,
					extra_specs: { 'afterglow:access_mode': 'gpu_quota' },
				}),
				flavor({
					id: 'private-cpu',
					name: 'private.cpu',
					is_gpu: false,
					gpu_count: 0,
					extra_specs: { 'afterglow:access_mode': 'manual' },
				}),
			],
			totalUnfiltered: 4,
			pageSize: 20,
			refreshing: false,
			onManage: vi.fn(),
			onDelete: vi.fn().mockResolvedValue(undefined),
		});

		const quotaRow = within(rowFor('quota.gpu'));
		expect(quotaRow.getByText('Private')).toBeTruthy();
		expect(quotaRow.getByText('Quota 연동')).toBeTruthy();
		expect(quotaRow.getByTitle('접근 권한 관리 정책: GPU Quota 연동')).toBeTruthy();

		const manualRow = within(rowFor('manual.gpu'));
		expect(manualRow.getByText('Private')).toBeTruthy();
		expect(manualRow.getByText('수동')).toBeTruthy();
		expect(manualRow.getByTitle('접근 권한 관리 정책: 수동 관리')).toBeTruthy();

		expect(within(rowFor('public.gpu')).queryByText(/Quota 연동|수동/)).toBeNull();
		expect(within(rowFor('private.cpu')).queryByText(/Quota 연동|수동/)).toBeNull();
	});
});
