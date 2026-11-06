import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/svelte';
import type { AdminInstance } from '$lib/types/adminInstance';
import { t } from '$lib/i18n/ns/admin-compute';
import { t as instanceT } from '$lib/i18n/ns/instance';


import AdminInstanceTable from '../instances/AdminInstanceTable.svelte';
import { createTableView } from '$lib/utils/tableView.svelte';
const view = () => createTableView<AdminInstance>({ rows: () => [], columns: () => [{ key: 'name', label: t('instances.table.name'), value: row => row.name }] });

describe('AdminInstanceTable', () => {
	it('opens the selected resource from its name', async () => {
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

		render(AdminInstanceTable, {
			props: {
				instances: [instance],
				view: view(),
				selectedIds: new Set<string>(),
				onOpen,
				onToggleSelect: vi.fn(),
				onToggleAll: vi.fn(),
			},
		});

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
			instances: [instance],
			view: view(),
			selectedIds: new Set<string>(), onOpen: vi.fn(),
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

	it('uses row-native owner names and preserves deleted or unknown ownership states', () => {
		const base = { id: 'one', name: 'vm-one', status: 'ACTIVE', project_id: 'p-one', user_id: null, flavor: 'small', host: 'host', created_at: null };
		render(AdminInstanceTable, {
			view: view(),
			instances: [
				{ ...base, project_name: 'Research', domain_id: 'd-one', domain_name: 'Science', owner_status: 'known' },
				{ ...base, id: 'two', project_id: 'p-two', project_name: 'Research', domain_id: 'd-two', domain_name: 'Engineering', owner_status: 'known' },
				{ ...base, id: 'three', project_id: 'deleted', owner_status: 'deleted_project' },
				{ ...base, id: 'four', project_id: null, owner_status: 'unknown_owner' },
			],
			selectedIds: new Set<string>(), onOpen: vi.fn(), onToggleSelect: vi.fn(), onToggleAll: vi.fn(),
		});
		expect(screen.getAllByText('Research')).toHaveLength(2);
		expect(screen.getByText(`${t('instances.table.domain')}: Science`)).toBeTruthy();
		expect(screen.getByText(`${t('instances.table.domain')}: Engineering`)).toBeTruthy();
		expect(screen.getByText(t('instances.table.deletedProject'))).toBeTruthy();
		expect(screen.getByText(t('instances.table.unknownOwner'))).toBeTruthy();
	});
});
