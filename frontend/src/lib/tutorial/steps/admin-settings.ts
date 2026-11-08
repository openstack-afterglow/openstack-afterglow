import { goto } from '$app/navigation';
import { sidebarOpen } from '$lib/stores/sidebar';
import { t } from '$lib/i18n/ns/tutorial';
import type { TourStep } from '../tours';

type SettingsTab = 'branding' | 'infrastructure' | 'enrollment' | 'quotas' | 'requests' | 'email';

// Read-only guide for /admin/settings. It only highlights the tab strip and the page help text, so no
// save, reset, upload, approve, reject or test-send control is ever highlighted, and the only clicks are
// tab switches, which never write anything. Registration stays in tours.ts.

// Selecting a tab only changes the `?tab=` query, exactly as clicking it does; used so Previous restores the panel.
function openTab(tab: SettingsTab): () => Promise<void> {
	return async () => {
		const url = new URL(window.location.href);
		if ((url.searchParams.get('tab') ?? 'branding') === tab) return;
		url.searchParams.set('tab', tab);
		await goto(`${url.pathname}${url.search}`, { replaceState: true, keepFocus: true, noScroll: true });
	};
}

const TABS = '[data-tour="admin-settings-tabs"]';
const tab = (name: SettingsTab) => `[data-tour="admin-settings-tab-${name}"]`;

function tabStep(name: SettingsTab, next: SettingsTab, title: () => string, description: () => string): TourStep {
	return {
		element: TABS,
		beforeReady: openTab(name),
		readyElement: tab(name),
		waitTimeoutMs: 20000,
		get title() { return title(); },
		get description() { return description(); },
		advanceOn: 'click',
		advanceElement: tab(next),
		showPrevious: true,
	};
}

export function adminSettingsSteps(): TourStep[] {
	return [
		{
			element: TABS,
			route: '/admin/settings',
			beforeReady: openTab('branding'),
			prepare: () => sidebarOpen.close(),
			readyElement: tab('branding'),
			waitTimeoutMs: 20000,
			get title() { return t('tours.adminSettings.step1.title'); },
			get description() { return t('tours.adminSettings.step1.description'); },
		},
		tabStep('branding', 'infrastructure', () => t('tours.adminSettings.step2.title'), () => t('tours.adminSettings.step2.description')),
		tabStep('infrastructure', 'enrollment', () => t('tours.adminSettings.step3.title'), () => t('tours.adminSettings.step3.description')),
		tabStep('enrollment', 'quotas', () => t('tours.adminSettings.step4.title'), () => t('tours.adminSettings.step4.description')),
		tabStep('quotas', 'requests', () => t('tours.adminSettings.step5.title'), () => t('tours.adminSettings.step5.description')),
		tabStep('requests', 'email', () => t('tours.adminSettings.step6.title'), () => t('tours.adminSettings.step6.description')),
		{
			element: TABS,
			beforeReady: openTab('email'),
			readyElement: tab('email'),
			waitTimeoutMs: 20000,
			get title() { return t('tours.adminSettings.step7.title'); },
			get description() { return t('tours.adminSettings.step7.description'); },
		},
		{
			element: '[data-tour="admin-settings-help"]',
			get title() { return t('tours.adminSettings.step8.title'); },
			get description() { return t('tours.adminSettings.step8.description'); },
		},
	];
}
