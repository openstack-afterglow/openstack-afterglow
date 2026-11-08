import { sidebarOpen } from '$lib/stores/sidebar';
import { t } from '$lib/i18n/ns/tutorial';
import type { TourStep } from '../tours';

// Identity area (domain project console). Step builders only; registration stays in tours.ts.
export function iamProjectSteps(): TourStep[] {
	return [
		{
			element: '[data-tour="iam-projects-create-open"]',
			route: '/dashboard/iam/projects',
			prepare: () => sidebarOpen.close(),
			waitTimeoutMs: 20000,
			get title() { return t('tours.iamProjects.step1.title'); },
			get description() { return t('tours.iamProjects.step1.description'); },
			advanceOn: 'click',
		},
		{
			element: '[data-tour="project-create-form"]',
			get title() { return t('tours.iamProjects.step2.title'); },
			get description() { return t('tours.iamProjects.step2.description'); },
			advanceOn: 'click',
			advanceElement: '[data-tour="project-create-submit"]',
		},
		{
			element: '[data-tour="iam-projects-list"]',
			readyElement: '[data-tour="iam-projects-delete"]',
			waitTimeoutMs: 20000,
			get title() { return t('tours.iamProjects.step3.title'); },
			get description() { return t('tours.iamProjects.step3.description'); },
		},
		{
			element: '[data-tour="iam-projects-delete"]',
			get title() { return t('tours.iamProjects.step4.title'); },
			get description() { return t('tours.iamProjects.step4.description'); },
			advanceOn: 'click',
		},
		{
			// The danger action stays disabled until the dependent-resource check proves the project empty.
			element: '[data-tour="project-delete-confirm"]',
			readyElement: '[data-tour="project-delete-confirm"]:not([disabled])',
			waitTimeoutMs: 20000,
			get title() { return t('tours.iamProjects.step5.title'); },
			get description() { return t('tours.iamProjects.step5.description'); },
			advanceOn: 'click',
		},
		{
			element: '[data-tour="iam-projects-list"]',
			get title() { return t('tours.iamProjects.step6.title'); },
			get description() { return t('tours.iamProjects.step6.description'); },
		},
	];
}
