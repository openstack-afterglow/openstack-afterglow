import { sidebarOpen } from '$lib/stores/sidebar';
import { t } from '$lib/i18n/ns/tutorial';
import type { TourStep } from '../tours';

// Administration domain create/disable tour. Step builders only; registration stays in tours.ts.
// Afterglow has no domain deletion, so the tour ends by disabling the domain it created. The edit,
// enabled and status anchors exist only for the domain this page just created.
export function adminDomainSteps(): TourStep[] {
	return [
		{
			element: '[data-tour="admin-domains-create-open"]',
			route: '/admin/domains',
			prepare: () => sidebarOpen.close(),
			// Create stays disabled until the domain list has loaded.
			readyElement: '[data-tour="admin-domains-create-open"]:not([disabled])',
			waitTimeoutMs: 20000,
			get title() { return t('tours.adminDomains.step1.title'); },
			get description() { return t('tours.adminDomains.step1.description'); },
			advanceOn: 'click',
		},
		{
			element: '[data-tour="admin-domains-create-name"]',
			// Next appears once a name is entered (Save enables); the field stays typeable meanwhile.
			readyElement: '[data-tour="admin-domains-create-submit"]:not([disabled])',
			waitTimeoutMs: 600000,
			waitAllowsInput: true,
			get title() { return t('tours.adminDomains.step2.title'); },
			get description() { return t('tours.adminDomains.step2.description'); },
		},
		{
			element: '[data-tour="admin-domains-create-submit"]',
			get title() { return t('tours.adminDomains.step3.title'); },
			get description() { return t('tours.adminDomains.step3.description'); },
			advanceOn: 'click',
			showPrevious: true,
		},
		{
			element: '[data-tour="admin-domains-edit"]',
			readyElement: '[data-tour="admin-domains-edit"]',
			waitTimeoutMs: 20000,
			get title() { return t('tours.adminDomains.step4.title'); },
			get description() { return t('tours.adminDomains.step4.description'); },
			advanceOn: 'click',
		},
		{
			// Next appears once Enabled is cleared; the checkbox stays usable meanwhile.
			element: '[data-tour="admin-domains-enabled"]',
			readyElement: '[data-tour="admin-domains-enabled"] input:not(:checked)',
			waitTimeoutMs: 600000,
			waitAllowsInput: true,
			get title() { return t('tours.adminDomains.step5.title'); },
			get description() { return t('tours.adminDomains.step5.description'); },
		},
		{
			element: '[data-tour="admin-domains-disable-submit"]',
			get title() { return t('tours.adminDomains.step6.title'); },
			get description() { return t('tours.adminDomains.step6.description'); },
			advanceOn: 'click',
			showPrevious: true,
		},
		{
			element: '[data-tour="admin-domains-disabled"]',
			readyElement: '[data-tour="admin-domains-disabled"]',
			waitTimeoutMs: 20000,
			get title() { return t('tours.adminDomains.step7.title'); },
			get description() { return t('tours.adminDomains.step7.description'); },
		},
	];
}
