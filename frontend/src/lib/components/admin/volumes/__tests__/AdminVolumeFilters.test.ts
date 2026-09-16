import { render, screen } from '@testing-library/svelte';
import { describe, expect, it, vi } from 'vitest';
import { writable } from 'svelte/store';

vi.mock('$lib/stores/projectNames', () => ({ projectNames: writable(new Map<string, string>()) }));

import AdminVolumeFilters from '../AdminVolumeFilters.svelte';

describe('AdminVolumeFilters status options', () => {
	it('renders only the positive-count options supplied by the status summary', () => {
		render(AdminVolumeFilters, {
			props: {
				projectFilter: '',
				projectSearchText: '',
				statusFilter: '',
				nameSearch: '',
				statusOptions: ['available', 'in-use'],
				onChange: vi.fn(),
			},
		});

		expect(screen.getByRole('option', { name: '모든 상태' })).toBeTruthy();
		expect(screen.getByRole('option', { name: 'available' })).toBeTruthy();
		expect(screen.getByRole('option', { name: 'in-use' })).toBeTruthy();
		expect(screen.queryByRole('option', { name: 'error' })).toBeNull();
	});
});
