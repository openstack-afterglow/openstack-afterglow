import { sidebarOpen } from '$lib/stores/sidebar';
import { t } from '$lib/i18n/ns/tutorial';
import type { TourStep } from '../tours';

// Administration object storage create/delete tour. Step builders only; registration stays in tours.ts.
// The delete and result anchors exist only on the bucket the page recorded as just created by this tour.
export function adminObjectStorageSteps(): TourStep[] {
	return [
		{
			element: '[data-tour="admin-object-storage-create-open"]',
			route: '/admin/object-storage',
			prepare: () => sidebarOpen.close(),
			get title() { return t('tours.adminObjectStorage.step1.title'); },
			get description() { return t('tours.adminObjectStorage.step1.description'); },
			advanceOn: 'click',
		},
		{
			element: '[data-tour="admin-object-storage-create-form"]',
			get title() { return t('tours.adminObjectStorage.step2.title'); },
			get description() { return t('tours.adminObjectStorage.step2.description'); },
			advanceOn: 'click',
			advanceElement: '[data-tour="admin-object-storage-create-submit"]',
		},
		{
			element: '[data-tour="admin-object-storage-delete"]',
			readyElement: '[data-tour="admin-object-storage-delete"]',
			waitTimeoutMs: 20000,
			get title() { return t('tours.adminObjectStorage.step3.title'); },
			get description() { return t('tours.adminObjectStorage.step3.description'); },
			advanceOn: 'click',
		},
		{
			element: '[data-tour="confirm-accept"]',
			get title() { return t('tours.adminObjectStorage.step4.title'); },
			get description() { return t('tours.adminObjectStorage.step4.description'); },
			advanceOn: 'click',
		},
		{
			element: '[data-tour="admin-object-storage-deleted"]',
			readyElement: '[data-tour="admin-object-storage-deleted"]',
			waitTimeoutMs: 20000,
			get title() { return t('tours.adminObjectStorage.step5.title'); },
			get description() { return t('tours.adminObjectStorage.step5.description'); },
		},
	];
}
