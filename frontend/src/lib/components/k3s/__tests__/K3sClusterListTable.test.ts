import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/svelte';
import K3sClusterListTable from '../K3sClusterListTable.svelte';
import type { Cluster } from '$lib/types/cluster';
import { createTableView } from '$lib/utils/tableView.svelte';
const clusterView = () => createTableView<Cluster>({ rows: () => clusters, columns: () => [{ key: 'name', label: 'Name', value: row => row.name }] });

const clusters: Cluster[] = [
  {
    id: 'cluster-1', name: 'first-cluster', status: 'CREATE_COMPLETE', status_reason: null,
    cluster_template_id: 'template-1', master_count: 1, node_count: 2, api_address: null,
    coe_version: null, keypair: null, create_timeout: null, created_at: '2026-01-01T00:00:00Z',
    updated_at: null, stack_id: null,
  },
  {
    id: 'cluster-2', name: 'second-cluster', status: 'CREATE_IN_PROGRESS', status_reason: null,
    cluster_template_id: 'template-1', master_count: 1, node_count: 1, api_address: null,
    coe_version: null, keypair: null, create_timeout: null, created_at: '2026-01-02T00:00:00Z',
    updated_at: null, stack_id: null,
  },
];

function renderTable(overrides: Partial<{
  selectedIds: ReadonlySet<string>;
  selectableIds: ReadonlySet<string>;
  selectionDisabled: boolean;
  onToggleSelect: (id: string) => void;
  onToggleAll: () => void;
}> = {}) {
  return render(K3sClusterListTable, {
    clusters,
    view: clusterView(),
    deleting: null,
    onNavigate: vi.fn(),
    onDelete: vi.fn(),
    selectedIds: new Set<string>(),
    selectableIds: new Set(clusters.map((cluster) => cluster.id)),
    selectionDisabled: false,
    onToggleSelect: vi.fn(),
    onToggleAll: vi.fn(),
    ...overrides,
  });
}

describe('K3sClusterListTable selection', () => {
  it('renders visible row checkboxes and disables unavailable rows', () => {
    const { container } = renderTable({ selectableIds: new Set(['cluster-1']) });
    expect(screen.getByLabelText('first-cluster 선택')).toBeTruthy();
    expect(screen.getByLabelText('second-cluster 선택')).toBeTruthy();
    expect((container.querySelector('input[aria-label="second-cluster 선택"]') as HTMLInputElement).disabled).toBe(true);
  });

  it('reports an indeterminate header and invokes the select-all callback', async () => {
    const onToggleAll = vi.fn();
    const { container } = renderTable({ selectedIds: new Set(['cluster-1']), onToggleAll });
    const header = container.querySelector('input[aria-label="전체 클러스터 선택"]') as HTMLInputElement;
    expect(header.indeterminate).toBe(true);
    await fireEvent.click(header);
    expect(onToggleAll).toHaveBeenCalledTimes(1);
  });

  it('keeps checkbox activation isolated from detail navigation', async () => {
    const onNavigate = vi.fn();
    const onToggleSelect = vi.fn();
    render(K3sClusterListTable, {
      clusters,
    view: clusterView(),
      deleting: null,
      selectedIds: new Set<string>(),
      selectableIds: new Set(clusters.map((cluster) => cluster.id)),
      selectionDisabled: false,
      onToggleSelect,
      onToggleAll: vi.fn(),
      onNavigate,
      onDelete: vi.fn(),
    });
    await fireEvent.click(screen.getByLabelText('first-cluster 선택'));
    expect(onToggleSelect).toHaveBeenCalledWith('cluster-1');
    expect(onNavigate).not.toHaveBeenCalled();
  });
});
