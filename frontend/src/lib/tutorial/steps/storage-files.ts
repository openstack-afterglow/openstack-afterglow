import { sidebarOpen } from '$lib/stores/sidebar';
import { t } from '$lib/i18n/ns/tutorial';
import type { TourStep } from '../tours';

// Manila file shares and Cinder volume snapshots. Step builders only; registration stays in tours.ts.
// Delete anchors exist only on the item the tour just created (each page records its id from the POST response).
export function volumeSnapshotSteps(): TourStep[] {
	return [
		{
			element: '[data-tour="volume-snapshots-create-open"]',
			route: '/dashboard/volumes/snapshots',
			prepare: () => sidebarOpen.close(),
			get title() { return t('tours.volumeSnapshots.step1.title'); },
			get description() { return t('tours.volumeSnapshots.step1.description'); },
			advanceOn: 'click',
		},
		{
			element: '[data-tour="volume-snapshots-create-form"]',
			get title() { return t('tours.volumeSnapshots.step2.title'); },
			get description() { return t('tours.volumeSnapshots.step2.description'); },
			advanceOn: 'click',
			advanceElement: '[data-tour="volume-snapshots-create-submit"]',
		},
		{
			element: '[data-tour="volume-snapshots-list"]',
			// The delete anchor appears once the snapshot is available or in error; the page re-reads every 15s.
			readyElement: '[data-tour="volume-snapshots-delete"]',
			waitTimeoutMs: 120000,
			// A failed create keeps the dialog open with a NEW error alert: go back to the form instead of waiting.
			// An alert left over from an earlier failed attempt is ignored.
			rewindOnNew: '[role="dialog"] [role="alert"]',
			get title() { return t('tours.volumeSnapshots.step3.title'); },
			get description() { return t('tours.volumeSnapshots.step3.description'); },
		},
		{
			element: '[data-tour="volume-snapshots-delete"]',
			get title() { return t('tours.volumeSnapshots.step4.title'); },
			get description() { return t('tours.volumeSnapshots.step4.description'); },
			advanceOn: 'click',
		},
		{
			element: '[data-tour="confirm-accept"]',
			get title() { return t('tours.volumeSnapshots.step5.title'); },
			get description() { return t('tours.volumeSnapshots.step5.description'); },
			advanceOn: 'click',
		},
		{
			element: '[data-tour="volume-snapshots-list"]',
			get title() { return t('tours.volumeSnapshots.step6.title'); },
			get description() { return t('tours.volumeSnapshots.step6.description'); },
		},
	];
}

// Manila share wizard → close → delete only the share this wizard created.
export function fileStorageSteps(): TourStep[] {
	return [
		{
			element: '[data-tour="file-storage-create-open"]',
			route: '/dashboard/file-storage',
			prepare: () => sidebarOpen.close(),
			get title() { return t('tours.fileStorage.step1.title'); },
			get description() { return t('tours.fileStorage.step1.description'); },
			advanceOn: 'click',
		},
		{
			// The whole wizard dialog stays highlighted so every field remains clickable.
			// Basic and (DHSS NFS) network steps both carry the create-submit anchor on the button that creates.
			element: '[data-tour="file-storage-create-form"]',
			get title() { return t('tours.fileStorage.step2.title'); },
			get description() { return t('tours.fileStorage.step2.description'); },
			advanceOn: 'click',
			advanceElement: '[data-tour="file-storage-create-submit"]',
		},
		{
			// The create call returns only after Manila reports the share available (backend polls up to 300s).
			element: '[data-tour="file-storage-created"]',
			waitTimeoutMs: 330000,
			get title() { return t('tours.fileStorage.step3.title'); },
			get description() { return t('tours.fileStorage.step3.description'); },
			advanceOn: 'click',
			advanceElement: '[data-tour="file-storage-create-done"]',
		},
		{
			// Present only on the card of the share created above, once it is available or in error.
			element: '[data-tour="file-storage-delete"]',
			waitTimeoutMs: 60000,
			get title() { return t('tours.fileStorage.step4.title'); },
			get description() { return t('tours.fileStorage.step4.description'); },
			advanceOn: 'click',
		},
		{
			element: '[data-tour="confirm-accept"]',
			get title() { return t('tours.fileStorage.step5.title'); },
			get description() { return t('tours.fileStorage.step5.description'); },
			advanceOn: 'click',
		},
		{
			element: '[data-tour="file-storage-list"]',
			get title() { return t('tours.fileStorage.step6.title'); },
			get description() { return t('tours.fileStorage.step6.description'); },
		},
	];
}
