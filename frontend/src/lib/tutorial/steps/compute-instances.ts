import { t } from '$lib/i18n/ns/tutorial';
import { createdInstance } from '../createdInstance.svelte';
import type { TourStep } from '../tours';

// Instance detail page delete. Step builders only; registration stays in tours.ts.
// The tour first creates a tut- instance through the VM create wizard steps (passed in by tours.ts,
// whose last step waits for the wizard to close), then deletes only that instance from its detail page.
// Stop/delete anchors exist only on the instance whose id the wizard recorded from its create stream.
const WIZARD_TEXT = [
	['tours.instanceDetailDelete.step1.title', 'tours.instanceDetailDelete.step1.description'],
	['tours.instanceDetailDelete.step2.title', 'tours.instanceDetailDelete.step2.description'],
	['tours.instanceDetailDelete.step3.title', 'tours.instanceDetailDelete.step3.description'],
	['tours.instanceDetailDelete.step4.title', 'tours.instanceDetailDelete.step4.description'],
	['tours.instanceDetailDelete.step5.title', 'tours.instanceDetailDelete.step5.description'],
] as const;

export function instanceDetailDeleteSteps(vmCreate: readonly TourStep[]): TourStep[] {
	const settled = vmCreate.at(-1);
	// Same wizard anchors and settlement as vm-create; only the copy is specific to this tour.
	const wizard = vmCreate.slice(0, WIZARD_TEXT.length).map((step, index): TourStep => {
		const [titleKey, descriptionKey] = WIZARD_TEXT[index];
		return Object.defineProperties({ ...step }, {
			title: { get: () => t(titleKey), enumerable: true },
			description: { get: () => t(descriptionKey), enumerable: true },
		});
	});
	// A fresh run must not target an instance recorded by an earlier wizard deployment.
	const open = wizard[0];
	if (open) {
		const prepare = open.prepare;
		open.prepare = () => {
			createdInstance.id = null;
			return prepare?.();
		};
	}
	return [
		...wizard,
		{
			element: '[data-tour="instance-created-row"]',
			route: '/dashboard/compute/instances',
			// Keep the vm-create settlement: follow wizard corrections and wait until the wizard closes.
			followWizard: settled?.followWizard,
			beforeReady: settled?.beforeReady,
			cancelElement: settled?.cancelElement,
			// A real list can show the new instance only after its next refresh.
			waitTimeoutMs: 120000,
			get title() { return t('tours.instanceDetailDelete.step6.title'); },
			get description() { return t('tours.instanceDetailDelete.step6.description'); },
		},
		{
			element: '[data-tour="instance-detail-stop"]',
			get route() {
				return createdInstance.id
					? `/dashboard/compute/instances/${encodeURIComponent(createdInstance.id)}`
					: '/dashboard/compute/instances';
			},
			// The stop action appears once the new instance reports ACTIVE.
			waitTimeoutMs: 120000,
			get title() { return t('tours.instanceDetailDelete.step7.title'); },
			get description() { return t('tours.instanceDetailDelete.step7.description'); },
			advanceOn: 'click',
		},
		{
			element: '[data-tour="confirm-accept"]',
			get title() { return t('tours.instanceDetailDelete.step8.title'); },
			get description() { return t('tours.instanceDetailDelete.step8.description'); },
			advanceOn: 'click',
		},
		{
			// The detail page offers delete only once the instance is SHUTOFF; Nova stops asynchronously
			// and the detail page's auto-refresh observes the new state.
			element: '[data-tour="instance-detail-delete"]',
			waitTimeoutMs: 120000,
			get title() { return t('tours.instanceDetailDelete.step9.title'); },
			get description() { return t('tours.instanceDetailDelete.step9.description'); },
			advanceOn: 'click',
		},
		{
			element: '[data-tour="confirm-accept"]',
			waitTimeoutMs: 8000,
			get title() { return t('tours.instanceDetailDelete.step10.title'); },
			get description() { return t('tours.instanceDetailDelete.step10.description'); },
			advanceOn: 'click',
		},
		{
			element: '[data-tour="instance-list"]',
			waitTimeoutMs: 20000,
			get title() { return t('tours.instanceDetailDelete.step11.title'); },
			get description() { return t('tours.instanceDetailDelete.step11.description'); },
		},
	];
}
