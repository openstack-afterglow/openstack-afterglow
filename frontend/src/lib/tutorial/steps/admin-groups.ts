import { sidebarOpen } from '$lib/stores/sidebar';
import { t } from '$lib/i18n/ns/tutorial';
import type { TourStep } from '../tours';
import { selectOwnDomain } from './admin-resources';

// Administration identity group create/delete tour. Step builders only; registration stays in tours.ts.
// The delete anchor exists only on the group this page just created.
export function adminGroupSteps(): TourStep[] {
	return [
		{
			element: '[data-tour="admin-groups-create-open"]',
			route: '/admin/groups',
			beforeReady: selectOwnDomain,
			prepare: () => sidebarOpen.close(),
			waitTimeoutMs: 20000,
			get title() { return t('tours.adminGroups.step1.title'); },
			get description() { return t('tours.adminGroups.step1.description'); },
			advanceOn: 'click',
		},
		{
			// Name and optional description stay typeable; Next appears once a name enables the submit.
			element: '[data-tour="admin-groups-create-fields"]',
			readyElement: '[data-tour="admin-groups-create-submit"]:not([disabled])',
			waitTimeoutMs: 600000,
			waitAllowsInput: true,
			get title() { return t('tours.adminGroups.step2.title'); },
			get description() { return t('tours.adminGroups.step2.description'); },
		},
		{
			element: '[data-tour="admin-groups-create-submit"]',
			// The submit is enabled here: step 2 only continues after a name was entered.
			get title() { return t('tours.adminGroups.step3.title'); },
			get description() { return t('tours.adminGroups.step3.description'); },
			advanceOn: 'click',
			showPrevious: true,
		},
		{
			element: '[data-tour="admin-groups-delete"]',
			readyElement: '[data-tour="admin-groups-delete"]',
			waitTimeoutMs: 20000,
			get title() { return t('tours.adminGroups.step4.title'); },
			get description() { return t('tours.adminGroups.step4.description'); },
			advanceOn: 'click',
		},
		{
			element: '[data-tour="admin-groups-delete-confirm"]',
			get title() { return t('tours.adminGroups.step5.title'); },
			get description() { return t('tours.adminGroups.step5.description'); },
			advanceOn: 'click',
		},
		{
			element: '[data-tour="admin-groups-results"]',
			// Settles after the created group is deleted and the list reload finished.
			readyElement: '[data-tour="admin-groups-results"][data-tour-settled="true"]',
			waitTimeoutMs: 20000,
			get title() { return t('tours.adminGroups.step6.title'); },
			get description() { return t('tours.adminGroups.step6.description'); },
		},
	];
}
