import { sidebarOpen } from '$lib/stores/sidebar';
import { t } from '$lib/i18n/ns/tutorial';
import type { TourStep } from '../tours';

// Administration custom role create/delete tour. Step builders only; registration stays in tours.ts.
// The row, detail delete and delete dialog anchors exist only for the role this page just created,
// so native (core), retired and pre-existing roles are never targeted.
export function adminRoleSteps(): TourStep[] {
	return [
		{
			element: '[data-tour="admin-roles-create-open"]',
			route: '/admin/roles',
			prepare: () => sidebarOpen.close(),
			// Create stays disabled until the role catalog has loaded.
			readyElement: '[data-tour="admin-roles-create-open"]:not([disabled])',
			waitTimeoutMs: 20000,
			get title() { return t('tours.adminRoles.step1.title'); },
			get description() { return t('tours.adminRoles.step1.description'); },
			advanceOn: 'click',
		},
		{
			// Area, grade and the composed name preview; description and domain keep their defaults.
			element: '[data-tour="admin-roles-create-name"]',
			// Next appears once area and grade form a valid name (the submit enables); the fields stay typeable meanwhile.
			readyElement: '[data-tour="admin-roles-create-submit"]:not([disabled])',
			waitTimeoutMs: 600000,
			waitAllowsInput: true,
			get title() { return t('tours.adminRoles.step2.title'); },
			get description() { return t('tours.adminRoles.step2.description'); },
		},
		{
			element: '[data-tour="admin-roles-create-submit"]',
			get title() { return t('tours.adminRoles.step3.title'); },
			get description() { return t('tours.adminRoles.step3.description'); },
			advanceOn: 'click',
			showPrevious: true,
		},
		{
			element: '[data-tour="admin-roles-created"]',
			readyElement: '[data-tour="admin-roles-created"]',
			waitTimeoutMs: 20000,
			get title() { return t('tours.adminRoles.step4.title'); },
			get description() { return t('tours.adminRoles.step4.description'); },
			advanceOn: 'click',
		},
		{
			element: '[data-tour="admin-roles-delete"]',
			// Delete stays disabled while the catalog refreshes after the create.
			readyElement: '[data-tour="admin-roles-delete"]:not([disabled])',
			waitTimeoutMs: 20000,
			get title() { return t('tours.adminRoles.step5.title'); },
			get description() { return t('tours.adminRoles.step5.description'); },
			advanceOn: 'click',
		},
		{
			// The real dialog requires the exact role name before its Delete enables.
			element: '[data-tour="admin-roles-delete-name"]',
			readyElement: '[data-tour="admin-roles-delete-confirm"]:not([disabled])',
			waitTimeoutMs: 600000,
			waitAllowsInput: true,
			get title() { return t('tours.adminRoles.step6.title'); },
			get description() { return t('tours.adminRoles.step6.description'); },
		},
		{
			element: '[data-tour="admin-roles-delete-confirm"]',
			get title() { return t('tours.adminRoles.step7.title'); },
			get description() { return t('tours.adminRoles.step7.description'); },
			advanceOn: 'click',
			showPrevious: true,
		},
		{
			element: '[data-tour="admin-roles-summary"]',
			get title() { return t('tours.adminRoles.step8.title'); },
			get description() { return t('tours.adminRoles.step8.description'); },
		},
	];
}
