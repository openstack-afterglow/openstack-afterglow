import { sidebarOpen } from '$lib/stores/sidebar';
import { t } from '$lib/i18n/ns/tutorial';
import type { TourStep } from '../tours';

// Network area: Octavia load balancers and Neutron routers. Step builders only; registration stays in tours.ts.

// Create lives on /new and redirects to the new item's detail page; delete happens there.
export function loadBalancerSteps(): TourStep[] {
	return [
		{
			element: '[data-tour="load-balancers-create-open"]',
			route: '/dashboard/network/loadbalancers',
			prepare: () => sidebarOpen.close(),
			get title() { return t('tours.loadBalancers.step1.title'); },
			get description() { return t('tours.loadBalancers.step1.description'); },
			advanceOn: 'click',
		},
		{
			element: '[data-tour="load-balancers-create-form"]',
			waitTimeoutMs: 8000,
			get title() { return t('tours.loadBalancers.step2.title'); },
			get description() { return t('tours.loadBalancers.step2.description'); },
			advanceOn: 'click',
			advanceElement: '[data-tour="load-balancers-create-submit"]',
		},
		{
			element: '[data-tour="load-balancers-detail"]',
			// A real Octavia load balancer accepts deletes only once provisioning finishes (15s auto-refresh).
			readyElement: '[data-tour="load-balancers-delete"]',
			waitTimeoutMs: 300000,
			get title() { return t('tours.loadBalancers.step3.title'); },
			get description() { return t('tours.loadBalancers.step3.description'); },
		},
		{
			element: '[data-tour="load-balancers-delete"]',
			get title() { return t('tours.loadBalancers.step4.title'); },
			get description() { return t('tours.loadBalancers.step4.description'); },
			advanceOn: 'click',
		},
		{
			element: '[data-tour="confirm-accept"]',
			get title() { return t('tours.loadBalancers.step5.title'); },
			get description() { return t('tours.loadBalancers.step5.description'); },
			advanceOn: 'click',
		},
		{
			element: '[data-tour="load-balancers-list-section"]',
			waitTimeoutMs: 8000,
			get title() { return t('tours.loadBalancers.step6.title'); },
			get description() { return t('tours.loadBalancers.step6.description'); },
		},
	];
}

// Delete lives in the router detail panel, opened from the created router's card.
export function routerSteps(): TourStep[] {
	return [
		{
			element: '[data-tour="routers-create-open"]',
			route: '/dashboard/network/routers',
			prepare: () => sidebarOpen.close(),
			get title() { return t('tours.routers.step1.title'); },
			get description() { return t('tours.routers.step1.description'); },
			advanceOn: 'click',
		},
		{
			element: '[data-tour="routers-create-form"]',
			get title() { return t('tours.routers.step2.title'); },
			get description() { return t('tours.routers.step2.description'); },
			advanceOn: 'click',
			advanceElement: '[data-tour="routers-create-submit"]',
		},
		{
			element: '[data-tour="routers-open-created"]',
			waitTimeoutMs: 20000,
			get title() { return t('tours.routers.step3.title'); },
			get description() { return t('tours.routers.step3.description'); },
			advanceOn: 'click',
		},
		{
			element: '[data-tour="routers-delete"]',
			waitTimeoutMs: 8000,
			get title() { return t('tours.routers.step4.title'); },
			get description() { return t('tours.routers.step4.description'); },
			advanceOn: 'click',
		},
		{
			element: '[data-tour="confirm-accept"]',
			get title() { return t('tours.routers.step5.title'); },
			get description() { return t('tours.routers.step5.description'); },
			advanceOn: 'click',
		},
		{
			element: '[data-tour="routers-list-section"]',
			get title() { return t('tours.routers.step6.title'); },
			get description() { return t('tours.routers.step6.description'); },
		},
	];
}
