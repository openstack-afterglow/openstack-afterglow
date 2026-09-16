import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/svelte';
import type { AdminFileStorage } from '$lib/types/fileStorage';

vi.mock('$lib/stores/projectNames', () => ({
	projectNames: {
		subscribe: (run: (value: Map<string, string>) => void) => {
			run(new Map([['project-1', 'Project One']]));
			return () => {};
		},
		load: vi.fn(),
		reset: vi.fn(),
	},
}));

import AdminFileStorageTable from '../AdminFileStorageTable.svelte';

const storage: AdminFileStorage = {
	id: 'share-1',
	name: 'share-one',
	status: 'available',
	size: 20,
	share_proto: 'CEPHFS',
	metadata: { union_type: 'dynamic' },
	project_id: 'project-1',
	created_at: '2026-06-01T00:00:00Z',
	export_locations: ['10.0.0.10:/volumes/share-one'],
};

describe('AdminFileStorageTable', () => {
	it('opens detail from name and action buttons', async () => {
		const onOpen = vi.fn();

		render(AdminFileStorageTable, {
			props: {
				storages: [storage],
				onOpen,
			},
		});

		await fireEvent.click(screen.getByRole('button', { name: 'share-one' }));
		expect(onOpen).toHaveBeenCalledTimes(1);
		expect(onOpen).toHaveBeenLastCalledWith(storage);

		await fireEvent.click(screen.getByRole('button', { name: '상세' }));
		expect(onOpen).toHaveBeenCalledTimes(2);
		expect(onOpen).toHaveBeenLastCalledWith(storage);
	});

	it('highlights the selected storage row', () => {
		render(AdminFileStorageTable, {
			props: {
				storages: [storage],
				selectedId: 'share-1',
				onOpen: vi.fn(),
			},
		});

		const row = screen.getByRole('button', { name: 'share-one' }).closest('tr');
		expect(row?.className).toContain('bg-surface-selected');
	});
});
