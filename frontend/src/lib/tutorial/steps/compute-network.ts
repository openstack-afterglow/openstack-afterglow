import { sidebarOpen } from '$lib/stores/sidebar';
import { t } from '$lib/i18n/ns/tutorial';
import type { TourStep } from '../tours';

// Compute and network resource tours. Step builders only; registration stays in tours.ts.
// Every delete anchor exists only on the row the page recorded as just created by this tour.
export function keypairSteps(): TourStep[] {
	return [
		{
			element: '[data-tour="keypairs-create-open"]',
			route: '/dashboard/compute/keypairs',
			prepare: () => sidebarOpen.close(),
			get title() { return t('tours.keypairs.step1.title'); },
			get description() { return t('tours.keypairs.step1.description'); },
			advanceOn: 'click',
		},
		{
			element: '[data-tour="keypairs-create-form"]',
			get title() { return t('tours.keypairs.step2.title'); },
			get description() { return t('tours.keypairs.step2.description'); },
			advanceOn: 'click',
			advanceElement: '[data-tour="keypairs-create-submit"]',
		},
		{
			// Nova returns a private key only for generated keys; an imported public key closes the modal instead.
			element: '[data-tour="keypairs-private-key"]',
			skipReadyElement: '[data-tour="keypairs-private-key"], [data-tour="keypairs-delete"]',
			skipIf: () => !document.querySelector('[data-tour="keypairs-private-key"]'),
			waitTimeoutMs: 20000,
			get title() { return t('tours.keypairs.step3.title'); },
			get description() { return t('tours.keypairs.step3.description'); },
			advanceOn: 'click',
			advanceElement: '[data-tour="keypairs-private-key-confirm"]',
		},
		{
			element: '[data-tour="keypairs-delete"]',
			readyElement: '[data-tour="keypairs-delete"]',
			waitTimeoutMs: 20000,
			get title() { return t('tours.keypairs.step4.title'); },
			get description() { return t('tours.keypairs.step4.description'); },
			advanceOn: 'click',
		},
		{
			element: '[data-tour="confirm-accept"]',
			get title() { return t('tours.keypairs.step5.title'); },
			get description() { return t('tours.keypairs.step5.description'); },
			advanceOn: 'click',
		},
		{
			element: '[data-tour="keypairs-list"]',
			get title() { return t('tours.keypairs.step6.title'); },
			get description() { return t('tours.keypairs.step6.description'); },
		},
	];
}

export function floatingIpSteps(): TourStep[] {
	return [
		{
			element: '[data-tour="floating-ips-allocate-open"]',
			route: '/dashboard/network/floating-ips',
			prepare: () => sidebarOpen.close(),
			get title() { return t('tours.floatingIps.step1.title'); },
			get description() { return t('tours.floatingIps.step1.description'); },
			advanceOn: 'click',
		},
		{
			element: '[data-tour="floating-ips-allocate-form"]',
			get title() { return t('tours.floatingIps.step2.title'); },
			get description() { return t('tours.floatingIps.step2.description'); },
			advanceOn: 'click',
			advanceElement: '[data-tour="floating-ips-allocate-submit"]',
		},
		{
			element: '[data-tour="floating-ips-list"]',
			readyElement: '[data-tour="floating-ips-release"]',
			waitTimeoutMs: 20000,
			get title() { return t('tours.floatingIps.step3.title'); },
			get description() { return t('tours.floatingIps.step3.description'); },
		},
		{
			element: '[data-tour="floating-ips-release"]',
			get title() { return t('tours.floatingIps.step4.title'); },
			get description() { return t('tours.floatingIps.step4.description'); },
			advanceOn: 'click',
		},
		{
			element: '[data-tour="confirm-accept"]',
			get title() { return t('tours.floatingIps.step5.title'); },
			get description() { return t('tours.floatingIps.step5.description'); },
			advanceOn: 'click',
		},
		{
			element: '[data-tour="floating-ips-list"]',
			get title() { return t('tours.floatingIps.step6.title'); },
			get description() { return t('tours.floatingIps.step6.description'); },
		},
	];
}

export function securityGroupSteps(): TourStep[] {
	return [
		{
			element: '[data-tour="security-groups-create-open"]',
			route: '/dashboard/network/security-groups',
			prepare: () => sidebarOpen.close(),
			get title() { return t('tours.securityGroups.step1.title'); },
			get description() { return t('tours.securityGroups.step1.description'); },
			advanceOn: 'click',
		},
		{
			element: '[data-tour="security-groups-create-form"]',
			get title() { return t('tours.securityGroups.step2.title'); },
			get description() { return t('tours.securityGroups.step2.description'); },
			advanceOn: 'click',
			advanceElement: '[data-tour="security-groups-create-submit"]',
		},
		{
			element: '[data-tour="security-groups-select"]',
			readyElement: '[data-tour="security-groups-select"]',
			waitTimeoutMs: 20000,
			get title() { return t('tours.securityGroups.step3.title'); },
			get description() { return t('tours.securityGroups.step3.description'); },
			advanceOn: 'click',
		},
		{
			element: '[data-tour="security-groups-delete"]',
			get title() { return t('tours.securityGroups.step4.title'); },
			get description() { return t('tours.securityGroups.step4.description'); },
			advanceOn: 'click',
		},
		{
			element: '[data-tour="confirm-accept"]',
			get title() { return t('tours.securityGroups.step5.title'); },
			get description() { return t('tours.securityGroups.step5.description'); },
			advanceOn: 'click',
		},
		{
			element: '[data-tour="security-groups-list"]',
			get title() { return t('tours.securityGroups.step6.title'); },
			get description() { return t('tours.securityGroups.step6.description'); },
		},
	];
}

export function networkSteps(): TourStep[] {
	return [
		{
			element: '[data-tour="networks-create-open"]',
			route: '/dashboard/network/networks',
			prepare: () => sidebarOpen.close(),
			get title() { return t('tours.networks.step1.title'); },
			get description() { return t('tours.networks.step1.description'); },
			advanceOn: 'click',
		},
		{
			// Highlight the whole form so the name field stays clickable; the create click advances.
			element: '[data-tour="networks-create-form"]',
			get title() { return t('tours.networks.step2.title'); },
			get description() { return t('tours.networks.step2.description'); },
			advanceOn: 'click',
			advanceElement: '[data-tour="networks-create-submit"]',
		},
		{
			element: '[data-tour="networks-actions"]',
			readyElement: '[data-tour="networks-actions"]',
			waitTimeoutMs: 20000,
			get title() { return t('tours.networks.step3.title'); },
			get description() { return t('tours.networks.step3.description'); },
			advanceOn: 'click',
		},
		{
			element: '[data-tour="networks-delete"]',
			get title() { return t('tours.networks.step4.title'); },
			get description() { return t('tours.networks.step4.description'); },
			advanceOn: 'click',
		},
		{
			element: '[data-tour="confirm-accept"]',
			get title() { return t('tours.networks.step5.title'); },
			get description() { return t('tours.networks.step5.description'); },
			advanceOn: 'click',
		},
		{
			element: '[data-tour="networks-list"]',
			get title() { return t('tours.networks.step6.title'); },
			get description() { return t('tours.networks.step6.description'); },
		},
	];
}
