import { sidebarOpen } from '$lib/stores/sidebar';
import { t } from '$lib/i18n/ns/tutorial';
import type { TourStep } from '../tours';

// Trove database instances and Magnum container clusters. Step builders only; registration stays in tours.ts.
// Delete anchors exist only on the row the tour just created (each page records the id from the POST response).
export function databaseInstanceSteps(): TourStep[] {
	return [
		{
			element: '[data-tour="database-instances-create-open"]',
			route: '/dashboard/database/instances',
			prepare: () => sidebarOpen.close(),
			get title() { return t('tours.databaseInstances.step1.title'); },
			get description() { return t('tours.databaseInstances.step1.description'); },
			advanceOn: 'click',
		},
		{
			// Highlight the whole form so the name field stays clickable; the submit click advances.
			element: '[data-tour="database-instances-create-form"]',
			readyElement: '[data-tour="database-instances-create-details"]',
			waitTimeoutMs: 20000,
			popoverSide: 'top',
			get title() { return t('tours.databaseInstances.step2.title'); },
			get description() { return t('tours.databaseInstances.step2.description'); },
			advanceOn: 'click',
			advanceElement: '[data-tour="database-instances-create-submit"]',
		},
		{
			element: '[data-tour="database-instances-list"]',
			readyElement: '[data-tour="database-instances-delete"]',
			waitTimeoutMs: 20000,
			get title() { return t('tours.databaseInstances.step3.title'); },
			get description() { return t('tours.databaseInstances.step3.description'); },
		},
		{
			element: '[data-tour="database-instances-delete"]',
			get title() { return t('tours.databaseInstances.step4.title'); },
			get description() { return t('tours.databaseInstances.step4.description'); },
			advanceOn: 'click',
		},
		{
			element: '[data-tour="confirm-accept"]',
			get title() { return t('tours.databaseInstances.step5.title'); },
			get description() { return t('tours.databaseInstances.step5.description'); },
			advanceOn: 'click',
		},
		{
			element: '[data-tour="database-instances-list"]',
			get title() { return t('tours.databaseInstances.step6.title'); },
			get description() { return t('tours.databaseInstances.step6.description'); },
		},
	];
}

export function containerClusterSteps(): TourStep[] {
	return [
		{
			element: '[data-tour="containers-clusters-create-open"]',
			route: '/dashboard/containers/clusters',
			prepare: () => sidebarOpen.close(),
			get title() { return t('tours.containersClusters.step1.title'); },
			get description() { return t('tours.containersClusters.step1.description'); },
			advanceOn: 'click',
		},
		{
			element: '[data-tour="containers-clusters-create-form"]',
			readyElement: '[data-tour="containers-clusters-create-template"]',
			waitTimeoutMs: 20000,
			get title() { return t('tours.containersClusters.step2.title'); },
			get description() { return t('tours.containersClusters.step2.description'); },
			advanceOn: 'click',
			advanceElement: '[data-tour="containers-clusters-create-submit"]',
		},
		{
			element: '[data-tour="containers-clusters-list"]',
			readyElement: '[data-tour="containers-clusters-delete"]',
			waitTimeoutMs: 20000,
			get title() { return t('tours.containersClusters.step3.title'); },
			get description() { return t('tours.containersClusters.step3.description'); },
		},
		{
			element: '[data-tour="containers-clusters-delete"]',
			get title() { return t('tours.containersClusters.step4.title'); },
			get description() { return t('tours.containersClusters.step4.description'); },
			advanceOn: 'click',
		},
		{
			element: '[data-tour="confirm-accept"]',
			get title() { return t('tours.containersClusters.step5.title'); },
			get description() { return t('tours.containersClusters.step5.description'); },
			advanceOn: 'click',
		},
		{
			element: '[data-tour="containers-clusters-list"]',
			get title() { return t('tours.containersClusters.step6.title'); },
			get description() { return t('tours.containersClusters.step6.description'); },
		},
	];
}
