import { sidebarOpen } from '$lib/stores/sidebar';
import { t } from '$lib/i18n/ns/tutorial';
import type { TourStep } from '../tours';

// Administration announcement send/delete tour. Step builders only; registration stays in tours.ts.
// The delete anchor exists only on the announcement this page just created.
export function adminAnnouncementSteps(): TourStep[] {
	return [
		{
			element: '[data-tour="admin-announcements-form"]',
			route: '/admin/announcements',
			prepare: () => sidebarOpen.close(),
			get title() { return t('tours.adminAnnouncements.step1.title'); },
			get description() { return t('tours.adminAnnouncements.step1.description'); },
		},
		{
			element: '[data-tour="admin-announcements-audience"]',
			get title() { return t('tours.adminAnnouncements.step2.title'); },
			get description() { return t('tours.adminAnnouncements.step2.description'); },
		},
		{
			element: '[data-tour="admin-announcements-submit"]',
			get title() { return t('tours.adminAnnouncements.step3.title'); },
			get description() { return t('tours.adminAnnouncements.step3.description'); },
			advanceOn: 'click',
		},
		{
			// Appears once the send request settles and the history reloads; a rejected send rewinds to step 3.
			element: '[data-tour="admin-announcements-delete"]',
			waitTimeoutMs: 10000,
			get title() { return t('tours.adminAnnouncements.step4.title'); },
			get description() { return t('tours.adminAnnouncements.step4.description'); },
			advanceOn: 'click',
		},
		{
			element: '[data-tour="confirm-accept"]',
			get title() { return t('tours.adminAnnouncements.step5.title'); },
			get description() { return t('tours.adminAnnouncements.step5.description'); },
			advanceOn: 'click',
		},
		{
			element: '[data-tour="admin-announcements-history"]',
			get title() { return t('tours.adminAnnouncements.step6.title'); },
			get description() { return t('tours.adminAnnouncements.step6.description'); },
		},
	];
}
