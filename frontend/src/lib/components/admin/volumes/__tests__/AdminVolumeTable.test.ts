import { fireEvent, render, screen } from '@testing-library/svelte';
import { describe, expect, it, vi } from 'vitest';
import { writable } from 'svelte/store';

vi.mock('$lib/stores/projectNames', () => ({ projectNames: writable(new Map<string, string>()) }));

import AdminVolumeTable from '../AdminVolumeTable.svelte';

const volumes = [
	{ id: 'vol-1', name: 'first-volume', status: 'available', size: 10, project_id: 'project-1', created_at: '2026-09-01' },
	{ id: 'vol-2', name: 'second-volume', status: 'in-use', size: 20, project_id: 'project-2', created_at: '2026-09-02' },
];

function props(selectedIds: ReadonlySet<string>, onToggleSelect = vi.fn(), onToggleAll = vi.fn()) {
	return {
		volumes,
		selectedVolumeId: null,
		openActionMenu: null,
		copiedProjectId: null,
		selectedIds,
		selectableIds: new Set(volumes.map((volume) => volume.id)),
		selectionDisabled: false,
		onSelect: vi.fn(),
		onToggleSelect,
		onToggleAll,
		onActionMenuOpen: vi.fn(),
		onActionMenuClose: vi.fn(),
		onCopyProjectId: vi.fn(),
		onEdit: vi.fn(),
		onExtend: vi.fn(),
		onTransfer: vi.fn(),
		onReset: vi.fn(),
		onForceDelete: vi.fn(),
		onDelete: vi.fn(),
		onBootFromVolume: vi.fn(),
	};
}

describe('AdminVolumeTable selection', () => {
	it('exposes page select-all and per-row selection with indeterminate state', async () => {
		const onToggleSelect = vi.fn();
		const onToggleAll = vi.fn();
		const view = render(AdminVolumeTable, props(new Set(['vol-1']), onToggleSelect, onToggleAll));

		const selectAll = screen.getByRole('checkbox', { name: '현재 페이지 전체 볼륨 선택' }) as HTMLInputElement;
		expect(selectAll.checked).toBe(false);
		expect(selectAll.indeterminate).toBe(true);
		expect(screen.getByRole('row', { name: /first-volume/ }).getAttribute('data-selected')).toBe('true');

		await fireEvent.click(selectAll);
		await fireEvent.click(screen.getByRole('checkbox', { name: 'first-volume 선택' }));
		expect(onToggleAll).toHaveBeenCalledOnce();
		expect(onToggleSelect).toHaveBeenCalledWith('vol-1');
		view.unmount();
	});
});
