import { cleanup, fireEvent, render, screen, within } from '@testing-library/svelte';
import { afterEach, describe, expect, it, vi } from 'vitest';
import VolumeListTable from '../VolumeListTable.svelte';
import type { Volume } from '$lib/types/volume';
import { initLocale } from '$lib/i18n/runtime.svelte';
import { t } from '$lib/i18n/ns/volume';

afterEach(() => {
 cleanup();
 initLocale('ko');
});

const volumes: Volume[] = [
 { id: 'vol-available', name: 'available-volume', status: 'available', size: 10, volume_type: null, attachments: [] },
 { id: 'vol-attached', name: 'attached-volume', status: 'in-use', size: 20, volume_type: null, attachments: [{ server_id: 'server-1' }] },
];
const props = (onToggleSelect = vi.fn()) => ({ volumes, selectedVolumeId: null, deleting: null, openActionMenu: null, selectedIds: new Set<string>(), selectableIds: new Set(['vol-available']), selectionDisabled: false, onToggleSelect, onToggleAll: vi.fn(), onOpenDetail: vi.fn(), onActionMenuOpen: vi.fn(), onActionMenuClose: vi.fn(), onRename: vi.fn(), onBoot: vi.fn(), onExtend: vi.fn(), onBackup: vi.fn(), onSnapshot: vi.fn(), onTransfer: vi.fn(), onForceDelete: vi.fn(), onDelete: vi.fn(), isSystemAdmin: false });

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

describe('Volume Auto Backup settings navigation', () => {
 it.each([
  ['ko', '자동 백업 설정'],
  ['en', 'Auto Backup settings'],
 ] as const)('preselects each row volume through desktop and shared menu links in %s', async (locale, label) => {
  initLocale(locale);
  const volume = { ...volumes[0], id: 'vol /한?&=#' };
  const tableProps = { ...props(), volumes: [volume, volumes[1]], selectableIds: new Set([volume.id]) };
  const view = render(VolumeListTable, tableProps);
  const desktopLinks = screen.getAllByRole('link', { name: label });
  expect(desktopLinks).toHaveLength(2);
  expect(desktopLinks[0].getAttribute('href')).toBe('/dashboard/volumes/backups?auto-backup=vol%20%2F%ED%95%9C%3F%26%3D%23');
  expect(desktopLinks[1].getAttribute('href')).toBe('/dashboard/volumes/backups?auto-backup=vol-attached');
  expect(new URL(desktopLinks[0].getAttribute('href')!, 'http://localhost').searchParams.get('auto-backup')).toBe(volume.id);

  await fireEvent.click(screen.getByRole('button', { name: t('listTable.volumeActions', { name: volume.name }) }));
  expect(tableProps.onActionMenuOpen).toHaveBeenCalledWith(volume.id);
  await view.rerender({ ...tableProps, openActionMenu: volume.id });
  const menu = screen.getByRole('group');
  const menuLink = within(menu).getByRole('link', { name: label });
  expect(menuLink.getAttribute('href')).toBe(desktopLinks[0].getAttribute('href'));
  menuLink.addEventListener('click', (event) => event.preventDefault(), { once: true });
  await fireEvent.click(menuLink);
  expect(tableProps.onActionMenuClose).toHaveBeenCalledOnce();
  expect(tableProps.onOpenDetail).not.toHaveBeenCalled();
  expect(tableProps.onBackup).not.toHaveBeenCalled();
  expect(tableProps.onToggleSelect).not.toHaveBeenCalled();
 });
});
