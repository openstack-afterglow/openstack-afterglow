import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const media = vi.hoisted(() => {
	const events = new EventTarget();
	const query = {
		matches: true,
		media: '(min-width: 1024px)',
		onchange: null,
		addEventListener: events.addEventListener.bind(events),
		removeEventListener: events.removeEventListener.bind(events),
		dispatchEvent: events.dispatchEvent.bind(events),
		addListener: () => undefined,
		removeListener: () => undefined,
	};
	vi.stubGlobal('matchMedia', () => query);
	return query;
});

import VolumeListTable from '../VolumeListTable.svelte';
import SnapshotListTable from '../SnapshotListTable.svelte';
import VolumeBackupListTable from '../backups/VolumeBackupListTable.svelte';
import VolumeSnapshotsTable from '../snapshots/VolumeSnapshotsTable.svelte';
import type { Volume, VolumeBackup, VolumeSnapshot } from '$lib/types/volume';
import { initLocale } from '$lib/i18n/runtime.svelte';
import { t } from '$lib/i18n/ns/volume';

beforeEach(() => { media.matches = true; initLocale('ko'); });
afterEach(() => { cleanup(); initLocale('ko'); });

async function setDesktop(desktop: boolean, cardCount: number) {
	media.matches = desktop;
	media.dispatchEvent(new Event('change'));
	await waitFor(() => expect(screen.queryAllByRole('article')).toHaveLength(desktop ? 0 : cardCount));
}

const volumes: Volume[] = [
	{ id: 'volume-a', name: 'Volume A', status: 'available', size: 10, volume_type: null, attachments: [], bootable: true },
	{ id: 'volume-b', name: 'Volume B', status: 'in-use', size: 20, volume_type: 'fast', attachments: [{ server_id: 'server-a' }] },
];
const snapshot: VolumeSnapshot = {
	id: 'snapshot-a', name: 'Snapshot A', status: 'available', volume_id: 'source-volume-a', size: 10,
	description: 'Secondary snapshot description', created_at: '2026-10-20T03:00:00Z',
};
const backup: VolumeBackup = {
	id: 'backup-a', name: 'Backup A', status: 'available', volume_id: 'source-volume-a', size: 10,
	description: null, created_at: null, is_incremental: false, has_dependent_backups: false,
};

function selection(id: string) {
	return {
		selectedIds: new Set([id]), selectableIds: new Set([id]), selectionDisabled: false,
		onToggleSelect: vi.fn(), onToggleAll: vi.fn(),
	};
}

function volumeProps() {
	return {
		volumes, selectedVolumeId: 'volume-a', deleting: null, openActionMenu: null,
		...selection('volume-a'), isSystemAdmin: false,
		onOpenDetail: vi.fn(), onActionMenuOpen: vi.fn(), onActionMenuClose: vi.fn(),
		onRename: vi.fn(), onBoot: vi.fn(), onExtend: vi.fn(), onBackup: vi.fn(), onSnapshot: vi.fn(),
		onTransfer: vi.fn(), onForceDelete: vi.fn(), onDelete: vi.fn(),
	};
}

describe('compact volume resource behavior', () => {
	it('keeps eligible selection, detail navigation, menu actions and settings links across viewport changes', async () => {
		const props = volumeProps();
		const view = render(VolumeListTable, props);
		await setDesktop(false, 2);
		const selected = () => screen.getByRole('checkbox', { name: t('listTable.selectVolume', { name: 'Volume A' }) }) as HTMLInputElement;
		expect(selected().checked).toBe(true);
		expect((screen.getByRole('checkbox', { name: t('listTable.selectVolume', { name: 'Volume B' }) }) as HTMLInputElement).disabled).toBe(true);
		const selectAll = screen.getByRole('checkbox', { name: t('listTable.selectAll') }) as HTMLInputElement;
		expect(selectAll.checked).toBe(true);
		await fireEvent.click(selectAll);
		expect(props.onToggleAll).toHaveBeenCalledOnce();
		await fireEvent.click(selected());
		expect(props.onToggleSelect).toHaveBeenCalledExactlyOnceWith('volume-a');
		await fireEvent.click(screen.getByRole('button', { name: 'Volume A' }));
		expect(props.onOpenDetail).toHaveBeenCalledExactlyOnceWith('volume-a');
		const settings = screen.getAllByRole('link', { name: t('autoPolicy.settings') });
		expect(settings).toHaveLength(2);
		expect(settings[0].getAttribute('href')).toBe('/dashboard/volumes/backups?auto-backup=volume-a');
		await fireEvent.click(screen.getByRole('button', { name: t('listTable.volumeActions', { name: 'Volume A' }) }));
		expect(props.onActionMenuOpen).toHaveBeenCalledExactlyOnceWith('volume-a');
		await view.rerender({ ...props, openActionMenu: 'volume-a' });
		await fireEvent.click(screen.getByRole('button', { name: t('operationItems.rename') }));
		expect(props.onRename).toHaveBeenCalledExactlyOnceWith(volumes[0]);
		await view.rerender(props);
		await setDesktop(true, 2);
		expect(selected().checked).toBe(true);
		expect(screen.getAllByRole('checkbox')).toHaveLength(3);
		expect(props.onToggleSelect).toHaveBeenCalledTimes(1);
	});

	it('keeps snapshot list menu callbacks and deleting state in cards', async () => {
		const props = {
			snapshots: [snapshot], deleting: null, openSnapshotActionMenu: null, ...selection(snapshot.id),
			onActionMenuOpen: vi.fn(), onActionMenuClose: vi.fn(), onDelete: vi.fn(),
		};
		const view = render(SnapshotListTable, props);
		await setDesktop(false, 1);
		expect((screen.getByRole('checkbox', { name: t('snapshotListTable.selectSnapshot', { name: snapshot.name }) }) as HTMLInputElement).checked).toBe(true);
		await fireEvent.click(screen.getByRole('checkbox', { name: t('snapshotListTable.selectAll') }));
		expect(props.onToggleAll).toHaveBeenCalledOnce();
		await fireEvent.click(screen.getByRole('button', { name: t('snapshotListTable.snapshotActions', { name: snapshot.name }) }));
		expect(props.onActionMenuOpen).toHaveBeenCalledExactlyOnceWith(snapshot.id);
		await view.rerender({ ...props, openSnapshotActionMenu: snapshot.id });
		await fireEvent.click(screen.getByRole('button', { name: t('snapshotListTable.delete') }));
		expect(props.onDelete).toHaveBeenCalledExactlyOnceWith(snapshot.id, snapshot.name);
		await view.rerender({ ...props, openSnapshotActionMenu: snapshot.id, deleting: snapshot.id });
		expect((screen.getByRole('button', { name: t('snapshotListTable.deleting') }) as HTMLButtonElement).disabled).toBe(true);
		await setDesktop(true, 1);
		expect(screen.getAllByRole('checkbox')).toHaveLength(2);
		expect(props.onDelete).toHaveBeenCalledTimes(1);
	});

	it('keeps backup restore/delete, select-all and missing-date metadata available', async () => {
		const props = {
			backups: [backup], deletingId: null, ...selection(backup.id),
			onRestore: vi.fn(), onDelete: vi.fn().mockResolvedValue(undefined),
		};
		const view = render(VolumeBackupListTable, props);
		await setDesktop(false, 1);
		expect(screen.queryByRole('table')).toBeNull();
		await fireEvent.click(screen.getByRole('checkbox', { name: t('backupListTable.selectBackup', { name: backup.name }) }));
		expect(props.onToggleSelect).toHaveBeenCalledExactlyOnceWith(backup.id);
		await fireEvent.click(screen.getByRole('checkbox', { name: t('backupListTable.selectAll') }));
		expect(props.onToggleAll).toHaveBeenCalledOnce();
		await fireEvent.click(screen.getByRole('button', { name: t('backupListTable.restore') }));
		expect(props.onRestore).toHaveBeenCalledExactlyOnceWith(backup);
		await fireEvent.click(screen.getByRole('button', { name: t('backupListTable.delete') }));
		expect(props.onDelete).toHaveBeenCalledExactlyOnceWith(backup.id, backup.name);
		const details = view.container.querySelector('details');
		expect(details?.open).toBe(false);
		expect(details?.textContent).toContain(t('backupListTable.missingValue'));
		await view.rerender({ ...props, deletingId: backup.id, selectionDisabled: true });
		expect((screen.getByRole('button', { name: t('backupListTable.deleting') }) as HTMLButtonElement).disabled).toBe(true);
		expect((screen.getByRole('checkbox', { name: t('backupListTable.selectAll') }) as HTMLInputElement).disabled).toBe(true);
		await setDesktop(true, 1);
		expect(screen.getByRole('table')).toBeTruthy();
		expect(screen.getAllByRole('checkbox')).toHaveLength(2);
		expect(props.onDelete).toHaveBeenCalledTimes(1);
	});

	it('keeps full snapshot metadata in disclosure while preserving row deletion and selection', async () => {
		const props = {
			snapshots: [snapshot], deleting: null, ...selection(snapshot.id), onDelete: vi.fn().mockResolvedValue(undefined),
		};
		const view = render(VolumeSnapshotsTable, props);
		await setDesktop(false, 1);
		expect(screen.queryByRole('table')).toBeNull();
		const details = view.container.querySelector('details');
		expect(details?.open).toBe(false);
		expect(details?.textContent).toContain(snapshot.description);
		expect(details?.textContent).toContain(snapshot.volume_id);
		await fireEvent.click(screen.getByRole('checkbox', { name: t('snapshotsTable.selectSnapshot', { name: snapshot.name }) }));
		expect(props.onToggleSelect).toHaveBeenCalledExactlyOnceWith(snapshot.id);
		await fireEvent.click(screen.getByRole('checkbox', { name: t('snapshotsTable.selectAll') }));
		expect(props.onToggleAll).toHaveBeenCalledOnce();
		await fireEvent.click(screen.getByRole('button', { name: t('snapshotsTable.delete') }));
		expect(props.onDelete).toHaveBeenCalledExactlyOnceWith(snapshot.id, snapshot.name);
		await view.rerender({ ...props, deleting: snapshot.id });
		expect((screen.getByRole('button', { name: t('snapshotsTable.deleting') }) as HTMLButtonElement).disabled).toBe(true);
		await setDesktop(true, 1);
		expect(screen.getByRole('table')).toBeTruthy();
		expect(screen.getAllByRole('checkbox')).toHaveLength(2);
		expect(props.onDelete).toHaveBeenCalledTimes(1);
	});
});
