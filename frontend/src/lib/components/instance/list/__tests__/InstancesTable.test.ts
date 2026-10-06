import { fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { describe, expect, it, vi } from 'vitest';
import type { Instance } from '$lib/types/compute';
import InstancesTable from '../InstancesTable.svelte';

const instances: Instance[] = [
	{
		id: 'instance-1', name: 'first-instance', status: 'ACTIVE', image_name: 'Ubuntu', flavor_name: 'small',
		ip_addresses: [], created_at: null, union_libraries: [], union_strategy: null,
	},
	{
		id: 'instance-2', name: 'second-instance', status: 'SHUTOFF', image_name: 'Ubuntu', flavor_name: 'small',
		ip_addresses: [], created_at: null, union_libraries: [], union_strategy: null,
	},
];

function renderTable(overrides: Partial<{
	selectedIds: ReadonlySet<string>;
	selectableIds: ReadonlySet<string>;
	selectionDisabled: boolean;
	onToggleSelect: (id: string) => void;
	onToggleAll: () => void;
	onSelect: (id: string) => void;
	onAction: (kind: 'console' | 'shelve' | 'unshelve' | 'delete', instance: Instance) => Promise<void>;
}> = {}) {
	return render(InstancesTable, {
		instances,
		selectedIds: new Set<string>(),
		selectableIds: new Set(instances.map((instance) => instance.id)),
		selectionDisabled: false,
		onToggleSelect: vi.fn(),
		onToggleAll: vi.fn(),
		onSelect: vi.fn(),
		onAction: async () => {},
		...overrides,
	});
}

describe('InstancesTable selection', () => {
	it('exposes resource columns through native table semantics', () => {
		renderTable();
		expect(screen.getByRole('table', { name: '인스턴스 목록' })).toBeTruthy();
		for (const heading of ['이름', '상태', '이미지 / 플레이버', 'IP', '라이브러리', '전략', '작업']) {
			expect(screen.getByRole('columnheader', { name: heading })).toBeTruthy();
		}
		expect(screen.getAllByRole('row')).toHaveLength(instances.length + 1);
	});

	it('shows selectable row checkboxes and forwards select-all state', async () => {
		const onToggleAll = vi.fn();
		renderTable({ selectedIds: new Set(['instance-1']), onToggleAll });
		const selectAll = screen.getByRole('checkbox', { name: '전체 선택' }) as HTMLInputElement;
		expect(selectAll.indeterminate).toBe(true);
		expect(screen.getByRole('checkbox', { name: 'first-instance 선택' })).toBeTruthy();
		expect(screen.getByRole('checkbox', { name: 'second-instance 선택' })).toBeTruthy();

		await fireEvent.click(selectAll.closest('label')!);
		expect(onToggleAll).toHaveBeenCalledOnce();
	});

	it('keeps selection interaction isolated from instance detail navigation', async () => {
		const onToggleSelect = vi.fn();
		const onSelect = vi.fn();
		renderTable({ onToggleSelect, onSelect });

		await fireEvent.click(screen.getByRole('checkbox', { name: 'first-instance 선택' }).closest('label')!);
		expect(onToggleSelect).toHaveBeenCalledWith('instance-1');
		expect(onSelect).not.toHaveBeenCalled();
	});

	it('shows row-local activity while its closed-menu operation is pending', async () => {
		let resolve!: () => void;
		const onAction = vi.fn(() => new Promise<void>((done) => { resolve = done; }));
		renderTable({ onAction });
		await fireEvent.click(screen.getByRole('button', { name: 'first-instance 인스턴스 작업' }));
		await fireEvent.click(screen.getByRole('button', { name: '콘솔' }));
		expect(screen.getByRole('status').textContent?.trim()).toBe('처리 중...');
		expect(screen.getByRole('status').closest('tr')?.textContent).toContain('first-instance');
		expect(screen.queryByRole('button', { name: '콘솔' })).toBeNull();
		resolve();
		await waitFor(() => expect(screen.queryByRole('status')).toBeNull());
		expect(onAction).toHaveBeenCalledWith('console', instances[0]);
	});
});
