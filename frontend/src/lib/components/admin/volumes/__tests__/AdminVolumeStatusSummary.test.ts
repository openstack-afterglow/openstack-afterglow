import { fireEvent, render, screen } from '@testing-library/svelte';
import { describe, expect, it, vi } from 'vitest';
import type { AdminVolumeStatusSummary as Summary } from '$lib/types/volume';

import AdminVolumeStatusSummary from '../AdminVolumeStatusSummary.svelte';

const mixedSummary: Summary = {
	total: 12,
	statuses: [
		{ status: 'available', count: 5 },
		{ status: 'in-use', count: 3 },
		{ status: 'error', count: 2 },
		{ status: 'maintenance', count: 2 },
		{ status: 'reserved', count: 0 },
	],
};

describe('AdminVolumeStatusSummary', () => {
	it('renders total and positive status counts while hiding zero-count states', () => {
		render(AdminVolumeStatusSummary, {
			props: {
				summary: mixedSummary,
				activeStatus: 'in-use',
				onSelect: vi.fn(),
			},
		});

		expect(screen.getByRole('button', { name: '전체 12' })).toBeTruthy();
		expect(screen.getByRole('button', { name: 'available 5' })).toBeTruthy();
		expect(screen.getByRole('button', { name: 'in-use 3' })).toBeTruthy();
		expect(screen.getByRole('button', { name: 'error 2' })).toBeTruthy();
		expect(screen.getByRole('button', { name: 'maintenance 2' })).toBeTruthy();
		expect(screen.queryByRole('button', { name: 'reserved 0' })).toBeNull();
		expect(screen.queryByRole('button', { name: 'creating 0' })).toBeNull();
	});

	it('calls onSelect with the clicked status and clears the filter from the total card', async () => {
		const onSelect = vi.fn();
		render(AdminVolumeStatusSummary, {
			props: {
				summary: mixedSummary,
				activeStatus: 'available',
				onSelect,
			},
		});

		await fireEvent.click(screen.getByRole('button', { name: 'error 2' }));
		expect(onSelect).toHaveBeenCalledWith('error');

		await fireEvent.click(screen.getByRole('button', { name: '전체 12' }));
		expect(onSelect).toHaveBeenCalledWith('');
		expect(onSelect).toHaveBeenCalledTimes(2);
	});
});
