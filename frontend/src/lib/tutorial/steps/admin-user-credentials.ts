import { sidebarOpen } from '$lib/stores/sidebar';
import { t } from '$lib/i18n/ns/tutorial';
import type { TourStep } from '../tours';
import { selectOwnDomain } from './admin-resources';

// Administration user credential create/delete tour. Step builders only; registration stays in tours.ts.
// The delete anchor exists only on the credential this page just created.
export function adminUserCredentialSteps(): TourStep[] {
	return [
		{
			// Creation stays disabled until the domain directory proves the signed-in administrator.
			element: '[data-tour="admin-user-credentials-scope"]',
			route: '/admin/user-credentials',
			beforeReady: selectOwnDomain,
			prepare: () => sidebarOpen.close(),
			readyElement: '[data-tour="admin-user-credentials-create-open"]:not([disabled])',
			waitTimeoutMs: 20000,
			get title() { return t('tours.adminUserCredentials.step1.title'); },
			get description() { return t('tours.adminUserCredentials.step1.description'); },
			advanceOn: 'click',
			advanceElement: '[data-tour="admin-user-credentials-create-open"]',
		},
		{
			// Highlight the form fields inside the modal; inputs stay interactive.
			element: '[data-tour="admin-user-credentials-form"]',
			readyElement: '[data-tour="admin-user-credentials-submit"]',
			waitTimeoutMs: 600000,
			waitAllowsInput: true,
			popoverSide: 'top',
			get title() { return t('tours.adminUserCredentials.step2.title'); },
			get description() { return t('tours.adminUserCredentials.step2.description'); },
			advanceOn: 'click',
			advanceElement: '[data-tour="admin-user-credentials-submit"]',
		},
		{
			// Anchored only to the row of this attempt's verified create result (controller clears it per attempt).
			// A new error alert in the still-open form means the POST failed: rewind instead of waiting.
			element: '[data-tour="admin-user-credentials-delete"]',
			readyElement: '[data-tour="admin-user-credentials-delete"]',
			rewindOnNew: '[data-tour="admin-user-credentials-form"] [role="alert"]',
			waitTimeoutMs: 20000,
			get title() { return t('tours.adminUserCredentials.step3.title'); },
			get description() { return t('tours.adminUserCredentials.step3.description'); },
			advanceOn: 'click',
		},
		{
			// Confirmation modal warning: permanently removes the credential.
			element: '[data-tour="admin-user-credentials-delete-confirm"]',
			readyElement: '[data-tour="admin-user-credentials-delete-confirm"]:not([disabled])',
			waitTimeoutMs: 20000,
			get title() { return t('tours.adminUserCredentials.step4.title'); },
			get description() { return t('tours.adminUserCredentials.step4.description'); },
			advanceOn: 'click',
			showPrevious: true,
		},
		{
			// Settled credentials inventory list view.
			element: '[data-tour="admin-user-credentials-list"]',
			get title() { return t('tours.adminUserCredentials.step5.title'); },
			get description() { return t('tours.adminUserCredentials.step5.description'); },
		},
	];
}
