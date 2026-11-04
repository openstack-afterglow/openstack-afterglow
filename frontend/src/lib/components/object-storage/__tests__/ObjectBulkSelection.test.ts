vi.mock('$lib/api/client', () => ({
	api: {
		withExperience() { return this; },
		get: vi.fn(async (path: string) => path.includes('/trash') ? [] : [{ name: 'alpha', count: 1, bytes: 1, content_type: 'text/plain', last_modified: '', etag: '' }, { name: 'beta', count: 1, bytes: 1, content_type: 'text/plain', last_modified: '', etag: '' }]),
		post: vi.fn(async (path: string) => path.includes('bulk-delete') ? { deleted: ['alpha'], failed: [{ name: 'beta', error: 'blocked' }] } : {}),
		delete: vi.fn(async () => {}),
		downloadBlob: vi.fn(),
	},
	ApiError: class ApiError extends Error {},
	getBaseUrl: () => '',
}));
vi.mock('$lib/stores/confirm.svelte', () => ({ confirmDialog: vi.fn(async () => true) }));
import { fireEvent, render, screen } from '@testing-library/svelte';
import { describe, expect, it, vi } from 'vitest';
import BucketCardGrid from '../BucketCardGrid.svelte';
import ObjectTreeSelectionHarness from './ObjectTreeSelectionHarness.svelte';
import type { SwiftContainer } from '$lib/types/objectStorage';

const containers: SwiftContainer[] = [
	{ name: 'alpha', count: 2, bytes: 1024 },
	{ name: 'beta', count: 0, bytes: 0 },
];

describe('Object bulk selection', () => {
	it('renders visible card checkboxes and isolates selection from detail/delete actions', async () => {
		const onToggleSelect = vi.fn();
		const onDelete = vi.fn(async () => {});
		render(BucketCardGrid, {
			containers,
			deleting: null,
			refreshing: false,
			selectedIds: new Set(['alpha']),
			onToggleSelect,
			onDelete,
		});

		expect((screen.getByRole('checkbox', { name: 'alpha 선택' }) as HTMLInputElement).checked).toBe(true);
		expect((screen.getByRole('checkbox', { name: 'beta 선택' }) as HTMLInputElement).checked).toBe(false);
		await fireEvent.click(screen.getByRole('checkbox', { name: 'alpha 선택' }).closest('label')!);
		expect(onToggleSelect).toHaveBeenCalledWith('alpha');
		expect(onDelete).not.toHaveBeenCalled();
		await fireEvent.click(screen.getAllByRole('button', { name: '삭제' })[0]);
		expect(onDelete).toHaveBeenCalledWith('alpha');
	});

	it('forwards disabled state while a batch is running', () => {
		render(BucketCardGrid, {
			containers,
			deleting: null,
			refreshing: false,
			selectedIds: new Set<string>(),
			selectionDisabled: true,
			onToggleSelect: vi.fn(),
			onDelete: vi.fn(async () => {}),
		});
		expect((screen.getByRole('checkbox', { name: 'alpha 선택' }) as HTMLInputElement).disabled).toBe(true);
		expect((screen.getByRole('checkbox', { name: 'beta 선택' }) as HTMLInputElement).disabled).toBe(true);
	});

	it('derives object-tree select-all from visible rows and replaces hidden selections', async () => {
		render(ObjectTreeSelectionHarness, { initialSelected: ['beta'], filterText: 'alpha' });

		const selectAll = await screen.findByRole('checkbox', { name: '표시된 오브젝트 전체 선택' });
		expect((selectAll as HTMLInputElement).checked).toBe(false);
		expect((selectAll as HTMLInputElement).indeterminate).toBe(false);
		expect(screen.getByTestId('selected-names').textContent).toBe('beta');

		await fireEvent.click(selectAll.closest('label')!);
		expect((selectAll as HTMLInputElement).checked).toBe(true);
		expect(screen.getByTestId('selected-names').textContent).toBe('alpha');
	});
});
