import { sidebarOpen } from '$lib/stores/sidebar';
import { t } from '$lib/i18n/ns/tutorial';
import type { TourStep } from '../tours';

// Storage-area tours. Each file exports step builders only; registration stays in tours.ts.
export function bucketSteps(): TourStep[] {
	return [
		{
			element: '[data-tour="object-storage-create-open"]',
			route: '/dashboard/object-storage/buckets',
			prepare: () => sidebarOpen.close(),
			get title() { return t('tours.buckets.step1.title'); },
			get description() { return t('tours.buckets.step1.description'); },
			advanceOn: 'click',
		},
		{
			element: '[data-tour="object-storage-create-form"]',
			get title() { return t('tours.buckets.step2.title'); },
			get description() { return t('tours.buckets.step2.description'); },
			advanceOn: 'click',
			advanceElement: '[data-tour="object-storage-create-submit"]',
		},
		{
			element: '[data-tour="object-storage-list"]',
			readyElement: '[data-tour="object-storage-delete"]',
			waitTimeoutMs: 20000,
			get title() { return t('tours.buckets.step3.title'); },
			get description() { return t('tours.buckets.step3.description'); },
		},
		{
			element: '[data-tour="object-storage-delete"]',
			get title() { return t('tours.buckets.step4.title'); },
			get description() { return t('tours.buckets.step4.description'); },
			advanceOn: 'click',
		},
		{
			element: '[data-tour="confirm-accept"]',
			get title() { return t('tours.buckets.step5.title'); },
			get description() { return t('tours.buckets.step5.description'); },
			advanceOn: 'click',
		},
		{
			element: '[data-tour="object-storage-trash"]',
			get title() { return t('tours.buckets.step6.title'); },
			get description() { return t('tours.buckets.step6.description'); },
		},
	];
}
