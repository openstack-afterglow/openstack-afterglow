import { sidebarOpen } from '$lib/stores/sidebar';
import { t } from '$lib/i18n/ns/tutorial';
import type { TourStep } from '../tours';
import { selectOwnDomain } from './admin-resources';

// Administration user create/delete tour. The delete anchor exists only on the user this tour just created.
export function adminUserSteps(): TourStep[] {
	return [
		{
			element: '[data-tour="admin-users-create-open"]',
			route: '/admin/users',
			beforeReady: selectOwnDomain,
			prepare: () => sidebarOpen.close(),
			// Create stays disabled until the administrator authority for this page is verified.
			readyElement: '[data-tour="admin-users-create-open"]:not([disabled])',
			waitTimeoutMs: 20000,
			get title() { return t('tours.adminUsers.step1.title'); },
			get description() { return t('tours.adminUsers.step1.description'); },
			advanceOn: 'click',
		},
		{
			// Only the form fields are highlighted; Next appears once submitting would actually send the request.
			element: '[data-tour="admin-users-create-fields"]',
			readyElement: '[data-tour="admin-users-create-submit"]',
			waitTimeoutMs: 600000,
			waitAllowsInput: true,
			get title() { return t('tours.adminUsers.step2.title'); },
			get description() { return t('tours.adminUsers.step2.description'); },
		},
		{
			element: '[data-tour="admin-users-create-submit"]',
			get title() { return t('tours.adminUsers.step3.title'); },
			get description() { return t('tours.adminUsers.step3.description'); },
			advanceOn: 'click',
			showPrevious: true,
		},
		{
			// The dialog stays open with the creation result until it is closed.
			element: '[data-tour="admin-users-create-result"]',
			readyElement: '[data-tour="admin-users-create-close"]',
			waitTimeoutMs: 20000,
			get title() { return t('tours.adminUsers.step4.title'); },
			get description() { return t('tours.adminUsers.step4.description'); },
			advanceOn: 'click',
			advanceElement: '[data-tour="admin-users-create-close"]',
		},
		{
			element: '[data-tour="admin-users-delete"]',
			readyElement: '[data-tour="admin-users-delete"]',
			waitTimeoutMs: 20000,
			get title() { return t('tours.adminUsers.step5.title'); },
			get description() { return t('tours.adminUsers.step5.description'); },
			advanceOn: 'click',
		},
		{
			// The dialog opens after the directory is reread; Delete enables once the full user ID is typed.
			element: '[data-tour="admin-users-delete-fields"]',
			readyElement: '[data-tour="admin-users-delete-confirm"]:not([disabled])',
			waitTimeoutMs: 600000,
			waitAllowsInput: true,
			get title() { return t('tours.adminUsers.step6.title'); },
			get description() { return t('tours.adminUsers.step6.description'); },
		},
		{
			element: '[data-tour="admin-users-delete-confirm"]',
			get title() { return t('tours.adminUsers.step7.title'); },
			get description() { return t('tours.adminUsers.step7.description'); },
			advanceOn: 'click',
			showPrevious: true,
		},
		{
			element: '[data-tour="admin-users-summary"]',
			get title() { return t('tours.adminUsers.step8.title'); },
			get description() { return t('tours.adminUsers.step8.description'); },
		},
	];
}
