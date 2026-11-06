import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/svelte';
import DbBackupsTable from '../DbBackupsTable.svelte';
import type { DbBackup, DbInstance } from '$lib/types/database';
import { createTableView } from '$lib/utils/tableView.svelte';
import { dbBackupColumns } from '$lib/utils/databaseTableColumns';

const backups: DbBackup[] = [
  {
    id: 'backup-1', name: 'daily-backup', status: 'COMPLETED', size: 10,
    created_at: '2026-01-01T00:00:00Z',
  },
  {
    id: 'backup-2', name: 'building-backup', status: 'BUILDING', size: 20,
    created_at: '2026-01-02T00:00:00Z',
  },
];

describe('DbBackupsTable selection', () => {
  it('renders row checkboxes and disables them plus row actions while busy', () => {
    const { container } = render(DbBackupsTable, {
      backups,
      view: createTableView({ rows: () => backups, columns: () => dbBackupColumns([]) }),
      instances: [],
      selectedIds: new Set(['backup-1']),
      selectableIds: new Set(backups.map((backup) => backup.id)),
      selectionDisabled: true,
      onToggleSelect: vi.fn(),
      onToggleAll: vi.fn(),
      onRestore: vi.fn(),
      onDelete: vi.fn(),
    });
    expect(screen.getByLabelText('daily-backup 선택')).toBeTruthy();
    expect(screen.getByLabelText('building-backup 선택')).toBeTruthy();
    expect((container.querySelector('input[aria-label="daily-backup 선택"]') as HTMLInputElement).disabled).toBe(true);
    expect(screen.getAllByRole('button', { name: '복원' }).every((button) => (button as HTMLButtonElement).disabled)).toBe(true);
    expect(screen.getAllByRole('button', { name: '삭제' }).every((button) => (button as HTMLButtonElement).disabled)).toBe(true);
    expect(screen.getByText('1개 선택됨')).toBeTruthy();
  });

  it('reports indeterminate state and invokes callbacks without navigating', async () => {
    const onToggleAll = vi.fn();
    const onToggleSelect = vi.fn();
    const onRestore = vi.fn();
    const onDelete = vi.fn();
    const { container } = render(DbBackupsTable, {
      backups,
      view: createTableView({ rows: () => backups, columns: () => dbBackupColumns([]) }),
      instances: [],
      selectedIds: new Set(['backup-1']),
      selectableIds: new Set(backups.map((backup) => backup.id)),
      onToggleSelect,
      onToggleAll,
      onRestore,
      onDelete,
    });
    const header = container.querySelector('input[aria-label="전체 백업 선택"]') as HTMLInputElement;
    expect(header.indeterminate).toBe(true);
    await fireEvent.click(header);
    expect(onToggleAll).toHaveBeenCalledTimes(1);
    await fireEvent.click(screen.getByLabelText('building-backup 선택'));
    expect(onToggleSelect).toHaveBeenCalledWith('backup-2');
    await fireEvent.click(screen.getAllByRole('button', { name: '복원' })[0]);
    expect(onRestore).toHaveBeenCalledWith(backups[0]);
    await fireEvent.click(screen.getAllByRole('button', { name: '삭제' })[0]);
    expect(onDelete).toHaveBeenCalledWith('backup-1', 'daily-backup', false);
  });
});

describe('database backup column values', () => {
  it('sorts sources by visible name and groups timestamps into the displayed date facet', () => {
    const sourceInstances: DbInstance[] = [
      { id: 'source-z', name: 'alpha', status: 'ACTIVE', datastore: {}, flavor_id: 'small', size: 10, created_at: '2026-01-01T00:00:00Z' },
      { id: 'source-a', name: 'zulu', status: 'ACTIVE', datastore: {}, flavor_id: 'small', size: 10, created_at: '2026-01-01T00:00:00Z' },
    ];
    const rows: DbBackup[] = [
      { ...backups[0], id: 'zulu-backup', instance_id: 'source-a', created_at: '2026-01-01T10:00:00Z' },
      { ...backups[1], id: 'alpha-backup', instance_id: 'source-z', created_at: '2026-01-01T12:00:00Z' },
    ];
    const view = createTableView({ rows: () => rows, columns: () => dbBackupColumns(sourceInstances) });
    view.toggleSort('source');
    expect(view.rows.map((row) => row.id)).toEqual(['alpha-backup', 'zulu-backup']);
    expect(view.options('created')).toEqual([{ value: '2026-01-01', label: '2026-01-01', count: 2 }]);
    view.setFilter('created', ['2026-01-01']);
    expect(view.rows).toHaveLength(2);
  });
});
