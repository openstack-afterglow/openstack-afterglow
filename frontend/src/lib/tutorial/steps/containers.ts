import { sidebarOpen } from '$lib/stores/sidebar';
import { t } from '$lib/i18n/ns/tutorial';
import type { TourStep } from '../tours';

// Containers area (Zun). Step builders only; registration stays in tours.ts.
export function containerSteps(): TourStep[] {
	return [
		{
			element: '[data-tour="containers-create-open"]',
			route: '/dashboard/containers/instances',
			prepare: () => sidebarOpen.close(),
			get title() { return t('tours.containers.step1.title'); },
			get description() { return t('tours.containers.step1.description'); },
			advanceOn: 'click',
		},
		{
			element: '[data-tour="containers-create-form"]',
			get title() { return t('tours.containers.step2.title'); },
			get description() { return t('tours.containers.step2.description'); },
			advanceOn: 'click',
			advanceElement: '[data-tour="containers-create-submit"]',
		},
		{
			element: '[data-tour="containers-list"]',
			readyElement: '[data-tour="containers-delete"]',
			waitTimeoutMs: 20000,
			get title() { return t('tours.containers.step3.title'); },
			get description() { return t('tours.containers.step3.description'); },
		},
		{
			element: '[data-tour="containers-delete"]',
			get title() { return t('tours.containers.step4.title'); },
			get description() { return t('tours.containers.step4.description'); },
			advanceOn: 'click',
		},
		{
			element: '[data-tour="confirm-accept"]',
			get title() { return t('tours.containers.step5.title'); },
			get description() { return t('tours.containers.step5.description'); },
			advanceOn: 'click',
		},
		{
			element: '[data-tour="containers-list"]',
			get title() { return t('tours.containers.step6.title'); },
			get description() { return t('tours.containers.step6.description'); },
		},
	];
}
