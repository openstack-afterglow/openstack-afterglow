import { sidebarOpen } from '$lib/stores/sidebar';
import { t } from '$lib/i18n/ns/tutorial';
import type { TourStep } from '../tours';

// Administration port create/delete tour. Step builders only; registration stays in tours.ts.
// The delete anchor exists only on the row of the port this page just created.
export function adminPortSteps(): TourStep[] {
	return [
		{
			element: '[data-tour="admin-ports-create-open"]',
			route: '/admin/ports',
			prepare: () => sidebarOpen.close(),
			get title() { return t('tours.adminPorts.step1.title'); },
			get description() { return t('tours.adminPorts.step1.description'); },
			advanceOn: 'click',
		},
		{
			// The whole form (with the owner project picker and fixed IP) can exceed a tablet viewport, so
			// only the network and name fields are highlighted; the remaining fields keep their defaults.
			element: '[data-tour="admin-ports-create-fields"]',
			// Next appears once a network is chosen (the submit enables); the fields stay typeable meanwhile.
			readyElement: '[data-tour="admin-ports-create-submit"]:not([disabled])',
			waitTimeoutMs: 600000,
			waitAllowsInput: true,
			get title() { return t('tours.adminPorts.step2.title'); },
			get description() { return t('tours.adminPorts.step2.description'); },
		},
		{
			element: '[data-tour="admin-ports-create-submit"]',
			// The submit is enabled here: step 2 only continues after a network was chosen.
			get title() { return t('tours.adminPorts.step3.title'); },
			get description() { return t('tours.adminPorts.step3.description'); },
			advanceOn: 'click',
			showPrevious: true,
		},
		{
			element: '[data-tour="admin-ports-delete"]',
			readyElement: '[data-tour="admin-ports-delete"]',
			waitTimeoutMs: 20000,
			get title() { return t('tours.adminPorts.step4.title'); },
			get description() { return t('tours.adminPorts.step4.description'); },
			advanceOn: 'click',
		},
		{
			element: '[data-tour="admin-ports-delete-confirm"]',
			get title() { return t('tours.adminPorts.step5.title'); },
			get description() { return t('tours.adminPorts.step5.description'); },
			advanceOn: 'click',
		},
		{
			element: '[data-tour="admin-ports-summary"]',
			get title() { return t('tours.adminPorts.step6.title'); },
			get description() { return t('tours.adminPorts.step6.description'); },
		},
	];
}
