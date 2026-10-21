import { writable } from 'svelte/store';
import { fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { Instance } from '$lib/types/compute';
import InstancesTable from '../InstancesTable.svelte';
import { t } from '$lib/i18n/ns/instance';

vi.mock('$lib/stores/auth', () => ({ canWrite: writable(true) }));

const media = vi.hoisted(() => {
	const events = new EventTarget();
	const query = {
		matches: true, media: '(min-width: 1024px)', onchange: null,
		addEventListener: events.addEventListener.bind(events),
		removeEventListener: events.removeEventListener.bind(events),
		dispatchEvent: events.dispatchEvent.bind(events),
		addListener: () => undefined, removeListener: () => undefined,
	};
	vi.stubGlobal('matchMedia', () => query);
	return query;
});
beforeEach(() => { media.matches = true; });

async function setDesktop(desktop: boolean) {
	media.matches = desktop;
	media.dispatchEvent(new Event('change'));
	await waitFor(() => expect(screen.queryByRole('table') !== null).toBe(desktop));
}

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
	instances: Instance[];
	selectedIds: ReadonlySet<string>;
	selectableIds: ReadonlySet<string>;
	selectionDisabled: boolean;
	onToggleSelect: (id: string) => void;
	onToggleAll: () => void;
	onSelect: (id: string) => void;
	onAction: (kind: 'console' | 'shelve' | 'unshelve' | 'delete' | 'start' | 'stop', instance: Instance) => Promise<void>;
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

	it('changes an open menu from ACTIVE stop/console to grouped SHUTOFF actions', async () => {
		const { rerender } = renderTable({ instances: [instances[0]] });
		await fireEvent.click(screen.getByRole('button', { name: t('rowActions.instanceActions', { name: instances[0].name }) }));
		expect(screen.getByRole('button', { name: t('rowActions.console') })).toBeTruthy();
		expect(screen.getByRole('button', { name: t('list.stop') })).toBeTruthy();
		expect(screen.queryByRole('button', { name: t('rowActions.shelve') })).toBeNull();
		expect(screen.queryByRole('button', { name: t('rowActions.delete') })).toBeNull();
		await rerender({ instances: [{ ...instances[0], status: 'SHUTOFF' }] });
		expect(screen.getByRole('button', { name: t('list.start') })).toBeTruthy();
		expect(screen.getByRole('button', { name: t('rowActions.shelve') })).toBeTruthy();
		expect(screen.getByRole('button', { name: t('rowActions.delete') })).toBeTruthy();
		expect(screen.queryByRole('button', { name: t('rowActions.console') })).toBeNull();
		expect(screen.queryByRole('button', { name: t('list.stop') })).toBeNull();
		await rerender({ instances: [{ ...instances[0], status: 'ACTIVE' }] });
		expect(screen.queryByRole('button', { name: t('rowActions.shelve') })).toBeNull();
		expect(screen.queryByRole('button', { name: t('rowActions.delete') })).toBeNull();
	});

	it.each(['SHELVED', 'SHELVED_OFFLOADED'])('preserves %s restore without delete/archive', async (status) => {
		renderTable({ instances: [{ ...instances[0], status }] });
		await fireEvent.click(screen.getByRole('button', { name: t('rowActions.instanceActions', { name: instances[0].name }) }));
		expect(screen.getByRole('button', { name: t('rowActions.unshelve') })).toBeTruthy();
		expect(screen.queryByRole('button', { name: t('rowActions.shelve') })).toBeNull();
		expect(screen.queryByRole('button', { name: t('rowActions.delete') })).toBeNull();
	});

	it.each(['BUILD', 'ERROR', 'VERIFY_RESIZE', 'shutoff', ''])('rejects %s as stopped action eligibility', async (status) => {
		renderTable({ instances: [{ ...instances[0], status }] });
		await fireEvent.click(screen.getByRole('button', { name: t('rowActions.instanceActions', { name: instances[0].name }) }));
		expect(screen.queryByRole('button', { name: t('list.start') })).toBeNull();
		expect(screen.queryByRole('button', { name: t('rowActions.shelve') })).toBeNull();
		expect(screen.queryByRole('button', { name: t('rowActions.delete') })).toBeNull();
	});

	it('retains selection, unavailable rows and one action menu per compact resource', async () => {
		const onSelect = vi.fn();
		const onToggleAll = vi.fn();
		renderTable({ selectedIds: new Set(['instance-1']), selectableIds: new Set(['instance-1']), onSelect, onToggleAll });
		await setDesktop(false);
		expect(screen.getAllByRole('article')).toHaveLength(2);
		expect((screen.getByRole('checkbox', { name: 'first-instance 선택' }) as HTMLInputElement).checked).toBe(true);
		expect((screen.getByRole('checkbox', { name: 'second-instance 선택' }) as HTMLInputElement).disabled).toBe(true);
		expect(screen.getAllByRole('button', { name: 'first-instance 인스턴스 작업' })).toHaveLength(1);
		await fireEvent.click(screen.getByRole('checkbox', { name: '전체 선택' }).closest('label')!);
		expect(onToggleAll).toHaveBeenCalledOnce();
		await fireEvent.click(screen.getByRole('button', { name: 'first-instance' }));
		expect(onSelect).toHaveBeenCalledWith('instance-1');
		await setDesktop(true);
		expect(screen.queryByRole('article')).toBeNull();
		expect((screen.getByRole('checkbox', { name: 'first-instance 선택' }) as HTMLInputElement).checked).toBe(true);
	});

	it('keeps pending row actions disabled through a viewport transition', async () => {
		let resolve!: () => void;
		const onAction = vi.fn(() => new Promise<void>((done) => { resolve = done; }));
		renderTable({ onAction });
		await fireEvent.click(screen.getByRole('button', { name: 'first-instance 인스턴스 작업' }));
		await fireEvent.click(screen.getByRole('button', { name: '콘솔' }));
		await setDesktop(false);
		expect(screen.getByRole('status').closest('article')?.textContent).toContain('first-instance');
		await fireEvent.click(screen.getByRole('button', { name: 'first-instance 인스턴스 작업' }));
		expect((screen.getByRole('button', { name: '콘솔' }) as HTMLButtonElement).disabled).toBe(true);
		expect(onAction).toHaveBeenCalledOnce();
		resolve();
		await waitFor(() => expect(screen.queryByRole('status')).toBeNull());
	});
});
