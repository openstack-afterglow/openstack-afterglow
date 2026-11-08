import { sidebarOpen } from '$lib/stores/sidebar';
import { t } from '$lib/i18n/ns/tutorial';
import type { TourStep } from '../tours';

// Trove database backups. Step builders only; registration stays in tours.ts.
// Backups are created and deleted in the instance detail panel opened from the instances list.
// Delete anchors exist only on the backup the panel just created (recorded from the POST response).
export function databaseBackupSteps(): TourStep[] {
	return [
		{
			element: '[data-tour="database-backups-instance-open"]',
			route: '/dashboard/database/instances',
			prepare: () => sidebarOpen.close(),
			waitTimeoutMs: 20000,
			get title() { return t('tours.databaseBackups.step1.title'); },
			get description() { return t('tours.databaseBackups.step1.description'); },
			advanceOn: 'click',
		},
		{
			element: '[data-tour="database-backups-create-open"]',
			readyElement: '[data-tour="database-backups-create-open"]',
			waitTimeoutMs: 20000,
			get title() { return t('tours.databaseBackups.step2.title'); },
			get description() { return t('tours.databaseBackups.step2.description'); },
			advanceOn: 'click',
		},
		{
			element: '[data-tour="database-backups-create-form"]',
			get title() { return t('tours.databaseBackups.step3.title'); },
			get description() { return t('tours.databaseBackups.step3.description'); },
			advanceOn: 'click',
			advanceElement: '[data-tour="database-backups-create-submit"]',
		},
		{
			element: '[data-tour="database-backups-created"]',
			// Trove deletes a backup only once it settles; the panel re-reads every 15s.
			readyElement: '[data-tour="database-backups-delete"]',
			waitTimeoutMs: 120000,
			get title() { return t('tours.databaseBackups.step4.title'); },
			get description() { return t('tours.databaseBackups.step4.description'); },
		},
		{
			element: '[data-tour="database-backups-delete"]',
			get title() { return t('tours.databaseBackups.step5.title'); },
			get description() { return t('tours.databaseBackups.step5.description'); },
			advanceOn: 'click',
		},
		{
			element: '[data-tour="confirm-accept"]',
			get title() { return t('tours.databaseBackups.step6.title'); },
			get description() { return t('tours.databaseBackups.step6.description'); },
			advanceOn: 'click',
		},
		{
			element: '[data-tour="database-backups-list"]',
			get title() { return t('tours.databaseBackups.step7.title'); },
			get description() { return t('tours.databaseBackups.step7.description'); },
		},
	];
}
