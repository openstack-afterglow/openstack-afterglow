import { get } from 'svelte/store';
import { goto } from '$app/navigation';
import { auth } from '$lib/stores/auth';
import { sidebarOpen } from '$lib/stores/sidebar';
import { t } from '$lib/i18n/ns/tutorial';
import type { TourStep } from '../tours';

// Administration create/delete tours. Step builders only; registration stays in tours.ts.
// Every delete anchor exists only on the row the page recorded as just created by this tour.

// Domain-scoped admin pages render only inside a selected domain; default to the administrator's own domain.
export async function selectOwnDomain(): Promise<void> {
	const url = new URL(window.location.href);
	const domainId = get(auth).domainId;
	if (url.searchParams.get('domain_id') || !domainId) return;
	url.searchParams.set('domain_id', domainId);
	await goto(`${url.pathname}${url.search}`, { replaceState: true, keepFocus: true, noScroll: true });
}

export function adminProjectSteps(): TourStep[] {
	return [
		{
			element: '[data-tour="admin-projects-create-open"]',
			route: '/admin/projects',
			beforeReady: selectOwnDomain,
			prepare: () => sidebarOpen.close(),
			waitTimeoutMs: 20000,
			get title() { return t('tours.adminProjects.step1.title'); },
			get description() { return t('tours.adminProjects.step1.description'); },
			advanceOn: 'click',
		},
		{
			element: '[data-tour="admin-projects-create-form"]',
			get title() { return t('tours.adminProjects.step2.title'); },
			get description() { return t('tours.adminProjects.step2.description'); },
			advanceOn: 'click',
			advanceElement: '[data-tour="admin-projects-create-submit"]',
		},
		{
			element: '[data-tour="admin-projects-delete"]',
			readyElement: '[data-tour="admin-projects-delete"]',
			waitTimeoutMs: 20000,
			get title() { return t('tours.adminProjects.step3.title'); },
			get description() { return t('tours.adminProjects.step3.description'); },
			advanceOn: 'click',
		},
		{
			// The danger action stays disabled until the dependent-resource check proves the project empty.
			element: '[data-tour="project-delete-confirm"]',
			readyElement: '[data-tour="project-delete-confirm"]:not([disabled])',
			waitTimeoutMs: 20000,
			get title() { return t('tours.adminProjects.step4.title'); },
			get description() { return t('tours.adminProjects.step4.description'); },
			advanceOn: 'click',
		},
		{
			element: '[data-tour="admin-projects-results"]',
			get title() { return t('tours.adminProjects.step5.title'); },
			get description() { return t('tours.adminProjects.step5.description'); },
		},
	];
}

export function adminFlavorSteps(): TourStep[] {
	return [
		{
			element: '[data-tour="admin-flavors-create-open"]',
			route: '/admin/flavors',
			prepare: () => sidebarOpen.close(),
			readyElement: '[data-tour="admin-flavors-create-open"]:not([disabled])',
			waitTimeoutMs: 20000,
			get title() { return t('tours.adminFlavors.step1.title'); },
			get description() { return t('tours.adminFlavors.step1.description'); },
			advanceOn: 'click',
		},
		{
			element: '[data-tour="admin-flavors-create-form"]',
			get title() { return t('tours.adminFlavors.step2.title'); },
			get description() { return t('tours.adminFlavors.step2.description'); },
			advanceOn: 'click',
			advanceElement: '[data-tour="admin-flavors-create-submit"]',
		},
		{
			element: '[data-tour="admin-flavors-delete"]',
			readyElement: '[data-tour="admin-flavors-delete"]',
			waitTimeoutMs: 20000,
			get title() { return t('tours.adminFlavors.step3.title'); },
			get description() { return t('tours.adminFlavors.step3.description'); },
			advanceOn: 'click',
		},
		{
			element: '[data-tour="confirm-accept"]',
			get title() { return t('tours.adminFlavors.step4.title'); },
			get description() { return t('tours.adminFlavors.step4.description'); },
			advanceOn: 'click',
		},
		{
			element: '[data-tour="admin-flavors-search"]',
			get title() { return t('tours.adminFlavors.step5.title'); },
			get description() { return t('tours.adminFlavors.step5.description'); },
		},
	];
}

export function adminNetworkLifecycleSteps(): TourStep[] {
	return [
		{
			element: '[data-tour="admin-networks-create-open"]',
			route: '/admin/networks',
			prepare: () => sidebarOpen.close(),
			get title() { return t('tours.adminNetworks.step1.title'); },
			get description() { return t('tours.adminNetworks.step1.description'); },
			advanceOn: 'click',
		},
		{
			element: '[data-tour="admin-networks-create-form"]',
			get title() { return t('tours.adminNetworks.step2.title'); },
			get description() { return t('tours.adminNetworks.step2.description'); },
			advanceOn: 'click',
			advanceElement: '[data-tour="admin-networks-create-submit"]',
		},
		{
			element: '[data-tour="admin-networks-actions"]',
			readyElement: '[data-tour="admin-networks-actions"]',
			waitTimeoutMs: 20000,
			get title() { return t('tours.adminNetworks.step3.title'); },
			get description() { return t('tours.adminNetworks.step3.description'); },
			advanceOn: 'click',
		},
		{
			element: '[data-tour="admin-networks-delete"]',
			get title() { return t('tours.adminNetworks.step4.title'); },
			get description() { return t('tours.adminNetworks.step4.description'); },
			advanceOn: 'click',
		},
		{
			element: '[data-tour="admin-networks-delete-confirm"]',
			get title() { return t('tours.adminNetworks.step5.title'); },
			get description() { return t('tours.adminNetworks.step5.description'); },
			advanceOn: 'click',
		},
		{
			element: '[data-tour="admin-networks-results"]',
			get title() { return t('tours.adminNetworks.step6.title'); },
			get description() { return t('tours.adminNetworks.step6.description'); },
		},
	];
}

export function adminRouterSteps(): TourStep[] {
	return [
		{
			element: '[data-tour="admin-routers-create-open"]',
			route: '/admin/routers',
			prepare: () => sidebarOpen.close(),
			get title() { return t('tours.adminRouters.step1.title'); },
			get description() { return t('tours.adminRouters.step1.description'); },
			advanceOn: 'click',
		},
		{
			element: '[data-tour="admin-routers-create-form"]',
			get title() { return t('tours.adminRouters.step2.title'); },
			get description() { return t('tours.adminRouters.step2.description'); },
			advanceOn: 'click',
			advanceElement: '[data-tour="admin-routers-create-submit"]',
		},
		{
			element: '[data-tour="admin-routers-delete"]',
			readyElement: '[data-tour="admin-routers-delete"]',
			waitTimeoutMs: 20000,
			get title() { return t('tours.adminRouters.step3.title'); },
			get description() { return t('tours.adminRouters.step3.description'); },
			advanceOn: 'click',
		},
		{
			element: '[data-tour="admin-routers-delete-confirm"]',
			get title() { return t('tours.adminRouters.step4.title'); },
			get description() { return t('tours.adminRouters.step4.description'); },
			advanceOn: 'click',
		},
		{
			element: '[data-tour="admin-routers-summary"]',
			get title() { return t('tours.adminRouters.step5.title'); },
			get description() { return t('tours.adminRouters.step5.description'); },
		},
	];
}

export function adminFloatingIpSteps(): TourStep[] {
	return [
		{
			element: '[data-tour="admin-floating-ips-create-open"]',
			route: '/admin/floating-ips',
			prepare: () => sidebarOpen.close(),
			get title() { return t('tours.adminFloatingIps.step1.title'); },
			get description() { return t('tours.adminFloatingIps.step1.description'); },
			advanceOn: 'click',
		},
		{
			element: '[data-tour="admin-floating-ips-create-form"]',
			get title() { return t('tours.adminFloatingIps.step2.title'); },
			get description() { return t('tours.adminFloatingIps.step2.description'); },
			advanceOn: 'click',
			advanceElement: '[data-tour="admin-floating-ips-create-submit"]',
		},
		{
			element: '[data-tour="admin-floating-ips-delete"]',
			readyElement: '[data-tour="admin-floating-ips-delete"]',
			waitTimeoutMs: 20000,
			get title() { return t('tours.adminFloatingIps.step3.title'); },
			get description() { return t('tours.adminFloatingIps.step3.description'); },
			advanceOn: 'click',
		},
		{
			element: '[data-tour="admin-floating-ips-delete-confirm"]',
			get title() { return t('tours.adminFloatingIps.step4.title'); },
			get description() { return t('tours.adminFloatingIps.step4.description'); },
			advanceOn: 'click',
		},
		{
			element: '[data-tour="admin-floating-ips-summary"]',
			get title() { return t('tours.adminFloatingIps.step5.title'); },
			get description() { return t('tours.adminFloatingIps.step5.description'); },
		},
	];
}
