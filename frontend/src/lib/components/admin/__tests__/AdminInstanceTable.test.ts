import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/svelte';
import type { AdminInstance } from '$lib/types/adminInstance';
import { t } from '$lib/i18n/ns/admin-compute';
import { t as instanceT } from '$lib/i18n/ns/instance';

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

import AdminInstanceTable from '../instances/AdminInstanceTable.svelte';

describe('AdminInstanceTable', () => {
	it('keeps content interactive while refreshing', async () => {
		const instance: AdminInstance = {
			id: 'inst-1',
			name: 'vm-one',
			status: 'ACTIVE',
			project_id: 'project-1',
			user_id: 'user-1',
			flavor: 'm1.small',
			host: 'host-1',
			created_at: '2026-06-01T00:00:00Z',
		};
		const onOpen = vi.fn();

		const { container } = render(AdminInstanceTable, {
			props: {
				refreshing: true,
				instances: [instance],
				markerStack: [],
				nextMarker: null,
				selectedIds: new Set<string>(),
				onOpen,
				onPrev: vi.fn(),
				onNext: vi.fn(),
				onToggleSelect: vi.fn(),
				onToggleAll: vi.fn(),
			},
		});

		expect(container.querySelector('.opacity-60')).toBeNull();
		expect(container.querySelector('.pointer-events-none')).toBeNull();

		await fireEvent.click(screen.getByRole('button', { name: 'vm-one' }));
		expect(onOpen).toHaveBeenCalledTimes(1);
		expect(onOpen).toHaveBeenCalledWith(instance);
	});

	it('preserves ERROR recovery across state transitions without live destructive actions', async () => {
		const instance: AdminInstance = {
			id: 'inst-1', name: 'vm-one', status: 'ACTIVE', project_id: 'project-1',
			user_id: 'user-1', flavor: 'small', host: 'host-1', created_at: null,
		};
		const { rerender } = render(AdminInstanceTable, {
			instances: [instance], markerStack: [], nextMarker: null, refreshing: false,
			selectedIds: new Set<string>(), onOpen: vi.fn(), onPrev: vi.fn(), onNext: vi.fn(),
			onRecover: vi.fn(), onToggleSelect: vi.fn(), onToggleAll: vi.fn(),
		});
		expect(screen.queryByRole('button', { name: t('instances.table.recover') })).toBeNull();
		expect(screen.queryByRole('button', { name: instanceT('rowActions.delete') })).toBeNull();
		expect(screen.queryByRole('button', { name: instanceT('rowActions.shelve') })).toBeNull();
		await rerender({ instances: [{ ...instance, status: 'ERROR', fault: 'Host unavailable' }] });
		expect(screen.getByRole('button', { name: t('instances.table.recover') })).toBeTruthy();
		expect(screen.getByRole('button', { name: t('instances.table.reason') })).toBeTruthy();
		await rerender({ instances: [{ ...instance, status: 'ACTIVE' }] });
		expect(screen.queryByRole('button', { name: t('instances.table.recover') })).toBeNull();
		expect(screen.queryByRole('button', { name: instanceT('rowActions.delete') })).toBeNull();
		expect(screen.queryByRole('button', { name: instanceT('rowActions.shelve') })).toBeNull();
	});
});
