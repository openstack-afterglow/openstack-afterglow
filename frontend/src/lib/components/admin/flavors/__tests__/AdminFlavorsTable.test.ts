import { fireEvent, render, screen, within } from '@testing-library/svelte';
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

describe('AdminFlavorsTable native flavor management', () => {
	it('retains explicit public/private identity and manages the exact flavor regardless of obsolete specs', async () => {
		const onManage = vi.fn();
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
			onManage,
			onDelete: vi.fn().mockResolvedValue(undefined),
		});

		const quotaRow = within(rowFor('quota.gpu'));
		expect(quotaRow.getByText('Private')).toBeTruthy();
		await fireEvent.click(quotaRow.getByRole('button', { name: '관리' }));
		expect(onManage.mock.calls[0][0].id).toBe('quota-gpu');
		expect(within(rowFor('public.gpu')).getByText('Public')).toBeTruthy();
		expect(within(rowFor('private.cpu')).getByText('Private')).toBeTruthy();
	});
});
