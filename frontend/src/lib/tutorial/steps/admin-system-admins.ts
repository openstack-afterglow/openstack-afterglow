import { sidebarOpen } from '$lib/stores/sidebar';
import { t } from '$lib/i18n/ns/tutorial';
import type { TourStep } from '../tours';

// Read-only guide for /admin/system-admins. Granting or revoking system authority is a platform-wide change, and
// the grant API gives no atomic proof of who created an assignment, so this tour never advances on a click. The
// highlighted blocks can contain live Add and Revoke buttons (revoke POSTs at once), so every step is `readOnly`:
// the engine swallows any click or keyboard activation inside the highlight. Registration stays in tours.ts.
export function adminSystemAdminSteps(): TourStep[] {
	return [
		{
			element: '[data-tour="admin-system-admins-add"]',
			route: '/admin/system-admins',
			prepare: () => sidebarOpen.close(),
			readyElement: '[data-tour="admin-system-admins-list"]',
			waitTimeoutMs: 20000,
			readOnly: true,
			get title() { return t('tours.adminSystemAdmins.step1.title'); },
			get description() { return t('tours.adminSystemAdmins.step1.description'); },
		},
		{
			element: '[data-tour="admin-system-admins-policy"]',
			readOnly: true,
			skipIf: () => document.querySelector('[data-tour="admin-system-admins-policy"]') === null,
			get title() { return t('tours.adminSystemAdmins.step2.title'); },
			get description() { return t('tours.adminSystemAdmins.step2.description'); },
		},
		{
			element: '[data-tour="admin-system-admins-list"]',
			readOnly: true,
			get title() { return t('tours.adminSystemAdmins.step3.title'); },
			get description() { return t('tours.adminSystemAdmins.step3.description'); },
		},
	];
}
