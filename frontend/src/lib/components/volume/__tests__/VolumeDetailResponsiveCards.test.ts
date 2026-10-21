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
const detail = vi.hoisted(() => ({
	volume: {
		id: 'detail-volume', name: 'Detail Volume', status: 'in-use', size: 10, volume_type: 'fast', bootable: true,
		attachments: [{ server_id: 'attached-server', device: '/dev/vdb' }],
	},
	snapshots: [{ id: 'detail-snapshot', name: 'Detail Snapshot', status: 'available', size: 10 }],
	attachmentName: vi.fn(() => ({ state: 'resolved', name: 'Attached VM' })),
	showSnapshotForm: false, snapshotName: '', snapshotDesc: '', snapshotError: '', creatingSnapshot: false,
	deletingSnapshot: null as string | null,
	deleteSnapshot: vi.fn(), cancelSnapshot: vi.fn(), createSnapshot: vi.fn(),
}));
vi.mock('$lib/stores/volumeDetailController.svelte', () => ({
	useVolumeDetailController: () => detail,
	attachmentServerId: (attachment: Record<string, unknown>) => typeof attachment.server_id === 'string' ? attachment.server_id : '',
	statusColor: { available: 'text-state-success-text' },
}));

import VolumeInfoCard from '../VolumeInfoCard.svelte';
import VolumeAttachmentsList from '../VolumeAttachmentsList.svelte';
import VolumeSnapshotsSection from '../VolumeSnapshotsSection.svelte';
import { initLocale } from '$lib/i18n/runtime.svelte';
import { t } from '$lib/i18n/ns/volume';

beforeEach(() => {
	media.matches = true;
	initLocale('ko');
	vi.clearAllMocks();
	detail.attachmentName.mockReturnValue({ state: 'resolved', name: 'Attached VM' });
	detail.deletingSnapshot = null;
});
afterEach(() => { cleanup(); initLocale('ko'); });

async function setDesktop(desktop: boolean) {
	media.matches = desktop;
	media.dispatchEvent(new Event('change'));
	await waitFor(() => expect(screen.queryAllByRole('article')).toHaveLength(desktop ? 0 : 1));
}

describe('compact volume detail resources', () => {
	it('keeps identity and core specifications above secondary immutable metadata', async () => {
		const view = render(VolumeInfoCard);
		await setDesktop(false);
		expect(screen.getByText('Detail Volume')).toBeTruthy();
		expect(screen.getByText('fast')).toBeTruthy();
		const disclosure = view.container.querySelector('details');
		expect(disclosure?.open).toBe(false);
		expect(disclosure?.textContent).toContain('detail-volume');
		expect(disclosure?.textContent).toContain(t('infoCard.bootable'));
		await setDesktop(true);
		expect(screen.getAllByText('Detail Volume')).toHaveLength(1);
	});

	it('keeps resolved attachment navigation and device while deferring the server UUID', async () => {
		const view = render(VolumeAttachmentsList);
		await setDesktop(false);
		expect(screen.getByRole('link', { name: 'Attached VM' }).getAttribute('href')).toBe('/dashboard/instances/attached-server');
		expect(screen.getByText('/dev/vdb')).toBeTruthy();
		const disclosure = view.container.querySelector('details');
		expect(disclosure?.open).toBe(false);
		expect(disclosure?.textContent).toContain('attached-server');
		await setDesktop(true);
		expect(screen.getAllByRole('link', { name: 'Attached VM' })).toHaveLength(1);
	});

	it('keeps snapshot deletion callbacks and busy disabling in the compact detail list', async () => {
		render(VolumeSnapshotsSection);
		await setDesktop(false);
		expect(screen.getAllByText('Detail Snapshot')).toHaveLength(1);
		await fireEvent.click(screen.getByRole('button', { name: t('snapshotsSection.delete') }));
		expect(detail.deleteSnapshot).toHaveBeenCalledExactlyOnceWith('detail-snapshot', 'Detail Snapshot');
		await setDesktop(true);
		expect(screen.getAllByRole('button', { name: t('snapshotsSection.delete') })).toHaveLength(1);
		cleanup();
		detail.deletingSnapshot = 'detail-snapshot';
		render(VolumeSnapshotsSection);
		await setDesktop(false);
		expect((screen.getByRole('button', { name: t('snapshotListTable.deleting') }) as HTMLButtonElement).disabled).toBe(true);
		expect(detail.deleteSnapshot).toHaveBeenCalledTimes(1);
	});
});
