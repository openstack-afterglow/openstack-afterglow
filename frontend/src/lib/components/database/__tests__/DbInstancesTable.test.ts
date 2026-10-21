import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import DbInstancesTable from '../DbInstancesTable.svelte';
import type { DbInstance } from '$lib/types/database';

const media = vi.hoisted(() => {
  const events = new EventTarget();
  const query = { matches: true, media: '(min-width: 1024px)', onchange: null, addEventListener: events.addEventListener.bind(events), removeEventListener: events.removeEventListener.bind(events), dispatchEvent: events.dispatchEvent.bind(events), addListener: () => undefined, removeListener: () => undefined };
  vi.stubGlobal('matchMedia', () => query);
  return query;
});
beforeEach(() => { media.matches = true; media.dispatchEvent(new Event('change')); });

const instances: DbInstance[] = [
  {
    id: 'db-1', name: 'primary-db', status: 'ACTIVE', datastore: { type: 'mysql', version: '8.0' },
    flavor_id: 'flavor-1', size: 20, created_at: '2026-01-01T00:00:00Z',
  },
  {
    id: 'db-2', name: 'replica-db', status: 'BUILD', datastore: { type: 'postgresql', version: '15' },
    flavor_id: 'flavor-2', size: 40, created_at: '2026-01-02T00:00:00Z',
  },
];

function renderTable(overrides: Partial<{
  selectedIds: ReadonlySet<string>;
  selectableIds: ReadonlySet<string>;
  selectionDisabled: boolean;
  onToggleSelect: (id: string) => void;
  onToggleAll: () => void;
}> = {}) {
  return render(DbInstancesTable, {
    instances,
    refreshing: false,
    restarting: null,
    deleting: null,
    onOpen: vi.fn(),
    onRestart: vi.fn(),
    onDelete: vi.fn(),
    selectedIds: new Set<string>(),
    selectableIds: new Set(instances.map((instance) => instance.id)),
    selectionDisabled: false,
    onToggleSelect: vi.fn(),
    onToggleAll: vi.fn(),
    ...overrides,
  });
}

describe('DbInstancesTable selection', () => {
  it('renders visible checkboxes and disables a non-selectable instance', () => {
    const { container } = renderTable({ selectableIds: new Set(['db-1']) });
    expect(screen.getByLabelText('primary-db 선택')).toBeTruthy();
    expect(screen.getByLabelText('replica-db 선택')).toBeTruthy();
    expect((container.querySelector('input[aria-label="replica-db 선택"]') as HTMLInputElement).disabled).toBe(true);
  });

  it('reports indeterminate state and invokes select-all', async () => {
    const onToggleAll = vi.fn();
    const { container } = renderTable({ selectedIds: new Set(['db-1']), onToggleAll });
    const header = container.querySelector('input[aria-label="전체 DB 인스턴스 선택"]') as HTMLInputElement;
    expect(header.indeterminate).toBe(true);
    await fireEvent.click(header);
    expect(onToggleAll).toHaveBeenCalledTimes(1);
  });

  it('does not navigate when a row checkbox is activated', async () => {
    const onOpen = vi.fn();
    const onToggleSelect = vi.fn();
    render(DbInstancesTable, {
      instances,
      refreshing: false,
      restarting: null,
      deleting: null,
      selectedIds: new Set<string>(),
      selectableIds: new Set(instances.map((instance) => instance.id)),
      selectionDisabled: false,
      onToggleSelect,
      onToggleAll: vi.fn(),
      onOpen,
      onRestart: vi.fn(),
      onDelete: vi.fn(),
    });
    await fireEvent.click(screen.getByLabelText('primary-db 선택'));
    expect(onToggleSelect).toHaveBeenCalledWith('db-1');
    expect(onOpen).not.toHaveBeenCalled();
  });
  it('keeps selection, navigation and action guards in tablet cards and restores desktop rows', async () => {
    const onOpen = vi.fn();
    const onRestart = vi.fn();
    const onToggleSelect = vi.fn();
    render(DbInstancesTable, { instances, refreshing: false, restarting: 'db-1', deleting: null, selectedIds: new Set(['db-1']), selectableIds: new Set(['db-1']), onToggleSelect, onToggleAll: vi.fn(), onOpen, onRestart, onDelete: vi.fn() });
    media.matches = false;
    media.dispatchEvent(new Event('change'));
    await waitFor(() => expect(screen.queryByRole('table')).toBeNull());
    expect(screen.getAllByRole('article')).toHaveLength(2);
    expect((screen.getByLabelText('primary-db 선택') as HTMLInputElement).checked).toBe(true);
    expect((screen.getByLabelText('replica-db 선택') as HTMLInputElement).disabled).toBe(true);
    await fireEvent.click(screen.getByLabelText('primary-db 선택'));
    expect(onToggleSelect).toHaveBeenCalledWith('db-1');
    expect(onOpen).not.toHaveBeenCalled();
    await fireEvent.click(screen.getByRole('button', { name: 'primary-db' }));
    expect(onOpen).toHaveBeenCalledWith('db-1');
    expect((screen.getByRole('button', { name: /재시작 중/ }) as HTMLButtonElement).disabled).toBe(true);
    expect(onRestart).not.toHaveBeenCalled();
    media.matches = true;
    media.dispatchEvent(new Event('change'));
    await waitFor(() => expect(screen.getByRole('table')).toBeTruthy());
    expect((screen.getByLabelText('primary-db 선택') as HTMLInputElement).checked).toBe(true);
    expect(screen.queryByRole('article')).toBeNull();
  });
});
