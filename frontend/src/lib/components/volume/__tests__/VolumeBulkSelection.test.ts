import { fireEvent, render, screen } from '@testing-library/svelte';
import { describe, expect, it, vi } from 'vitest';
import VolumeListTable from '../VolumeListTable.svelte';
import type { Volume } from '$lib/types/volume';

const volumes: Volume[] = [
 { id: 'vol-available', name: 'available-volume', status: 'available', size: 10, volume_type: null, attachments: [] },
 { id: 'vol-attached', name: 'attached-volume', status: 'in-use', size: 20, volume_type: null, attachments: [{ server_id: 'server-1' }] },
];
const props = (onToggleSelect = vi.fn()) => ({ volumes, selectedVolumeId: null, deleting: null, autoBackupConfigs: new Set<string>(), autoBackupToggling: null, openActionMenu: null, selectedIds: new Set<string>(), selectableIds: new Set(['vol-available']), selectionDisabled: false, onToggleSelect, onToggleAll: vi.fn(), onOpenDetail: vi.fn(), onActionMenuOpen: vi.fn(), onActionMenuClose: vi.fn(), onRename: vi.fn(), onBoot: vi.fn(), onExtend: vi.fn(), onBackup: vi.fn(), onSnapshot: vi.fn(), onTransfer: vi.fn(), onForceDelete: vi.fn(), onDelete: vi.fn(), onToggleAutoBackup: vi.fn(), isSystemAdmin: false });

describe('Volume bulk selection', () => {
 it('shows eligible and disabled attached checkboxes', () => { render(VolumeListTable, props()); expect((screen.getByRole('checkbox', { name: 'available-volume 선택' }) as HTMLInputElement).disabled).toBe(false); expect((screen.getByRole('checkbox', { name: 'attached-volume 선택' }) as HTMLInputElement).disabled).toBe(true); });
 it('forwards row selection and renders eligible-only select-all state', async () => {
  const toggle = vi.fn();
  const view = render(VolumeListTable, { ...props(toggle), selectableIds: new Set(['vol-available', 'vol-other']) });
  const selectAll = () => screen.getByRole('checkbox', { name: '전체 선택' }) as HTMLInputElement;
  expect(selectAll().indeterminate).toBe(false);
  await view.rerender({ ...props(toggle), selectableIds: new Set(['vol-available', 'vol-other']), selectedIds: new Set(['vol-available', 'vol-attached']) });
  expect(selectAll().checked).toBe(false);
  expect(selectAll().indeterminate).toBe(true);
  await view.rerender({ ...props(toggle), selectableIds: new Set(['vol-available', 'vol-other']), selectedIds: new Set(['vol-available', 'vol-other', 'vol-attached']) });
  expect(selectAll().checked).toBe(true);
  await fireEvent.click(screen.getByRole('checkbox', { name: 'available-volume 선택' }));
  expect(toggle).toHaveBeenCalledWith('vol-available');
 });
});
