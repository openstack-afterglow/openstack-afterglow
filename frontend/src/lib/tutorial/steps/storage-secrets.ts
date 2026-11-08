import { sidebarOpen } from '$lib/stores/sidebar';
import { t } from '$lib/i18n/ns/tutorial';
import type { TourStep } from '../tours';

// Key Manager secrets and volume backups. Step builders only; registration stays in tours.ts.
// Delete anchors exist only on the row the tour just created (the page records its id from the POST response).
export function secretSteps(): TourStep[] {
	return [
		{
			element: '[data-tour="secrets-create-open"]',
			route: '/dashboard/secrets',
			prepare: () => sidebarOpen.close(),
			get title() { return t('tours.secrets.step1.title'); },
			get description() { return t('tours.secrets.step1.description'); },
			advanceOn: 'click',
		},
		{
			element: '[data-tour="secrets-create-form"]',
			get title() { return t('tours.secrets.step2.title'); },
			get description() { return t('tours.secrets.step2.description'); },
			advanceOn: 'click',
			advanceElement: '[data-tour="secrets-create-submit"]',
		},
		{
			element: '[data-tour="secrets-list"]',
			readyElement: '[data-tour="secrets-delete"]',
			waitTimeoutMs: 20000,
			get title() { return t('tours.secrets.step3.title'); },
			get description() { return t('tours.secrets.step3.description'); },
		},
		{
			element: '[data-tour="secrets-delete"]',
			get title() { return t('tours.secrets.step4.title'); },
			get description() { return t('tours.secrets.step4.description'); },
			advanceOn: 'click',
		},
		{
			element: '[data-tour="confirm-accept"]',
			get title() { return t('tours.secrets.step5.title'); },
			get description() { return t('tours.secrets.step5.description'); },
			advanceOn: 'click',
		},
		{
			element: '[data-tour="secrets-list"]',
			get title() { return t('tours.secrets.step6.title'); },
			get description() { return t('tours.secrets.step6.description'); },
		},
	];
}

export function volumeBackupSteps(): TourStep[] {
	return [
		{
			element: '[data-tour="volume-backups-create-open"]',
			route: '/dashboard/volumes/backups',
			prepare: () => sidebarOpen.close(),
			get title() { return t('tours.volumeBackups.step1.title'); },
			get description() { return t('tours.volumeBackups.step1.description'); },
			advanceOn: 'click',
		},
		{
			element: '[data-tour="volume-backups-create-form"]',
			get title() { return t('tours.volumeBackups.step2.title'); },
			get description() { return t('tours.volumeBackups.step2.description'); },
			advanceOn: 'click',
			advanceElement: '[data-tour="volume-backups-create-submit"]',
		},
		{
			element: '[data-tour="volume-backups-list"]',
			// The delete anchor appears only once the backup is available; real Cinder backups take minutes and the page re-reads every 15s.
			readyElement: '[data-tour="volume-backups-delete"]',
			waitTimeoutMs: 300000,
			get title() { return t('tours.volumeBackups.step3.title'); },
			get description() { return t('tours.volumeBackups.step3.description'); },
		},
		{
			element: '[data-tour="volume-backups-delete"]',
			get title() { return t('tours.volumeBackups.step4.title'); },
			get description() { return t('tours.volumeBackups.step4.description'); },
			advanceOn: 'click',
		},
		{
			element: '[data-tour="confirm-accept"]',
			get title() { return t('tours.volumeBackups.step5.title'); },
			get description() { return t('tours.volumeBackups.step5.description'); },
			advanceOn: 'click',
		},
		{
			element: '[data-tour="volume-backups-list"]',
			get title() { return t('tours.volumeBackups.step6.title'); },
			get description() { return t('tours.volumeBackups.step6.description'); },
		},
	];
}
