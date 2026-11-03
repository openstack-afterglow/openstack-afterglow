<script lang="ts">
	import { page } from '$app/state';
	import { goto } from '$app/navigation';
	import { t } from '$lib/i18n/ns/admin-system';
	import { auth } from '$lib/stores/auth';
	import AdminLoginBrandingPanel from '$lib/components/admin/AdminLoginBrandingPanel.svelte';
	import AdminResourcePoliciesPanel from '$lib/components/admin/AdminResourcePoliciesPanel.svelte';
	import AdminEnrollmentPolicyPanel from '$lib/components/admin/AdminEnrollmentPolicyPanel.svelte';
	import AdminEmailSettingsPanel from '$lib/components/admin/AdminEmailSettingsPanel.svelte';
	import { PageHeader, PageShell, Tabs } from '$lib/components/ui';

	const token = $derived($auth.token ?? undefined);
	const projectId = $derived($auth.projectId ?? undefined);
	const destinations = ['branding', 'infrastructure', 'enrollment', 'quotas', 'requests', 'email'] as const;
	type Destination = typeof destinations[number];
	const selected = $derived(destinations.includes(page.url.searchParams.get('tab') as Destination)
		? page.url.searchParams.get('tab') as Destination : 'branding');
	const enrollmentSelected = $derived(selected === 'enrollment' || selected === 'quotas' || selected === 'requests');
	const tabs = $derived(destinations.map(value => ({ value, label: t(`settings.tab.${value}`),
		panelId: value === 'branding' || value === 'infrastructure' || value === 'email' ? `settings-${value}-panel` : 'settings-enrollment-panel' })));
	function selectDestination(value: string) {
		const url = new URL(page.url);
		url.searchParams.set('tab', value);
		void goto(url, { keepFocus: true, noScroll: true });
	}
</script>

<PageShell>
	<PageHeader
		breadcrumb={t('settings.breadcrumb')}
		title={t('settings.title')}
		subtitle={t('settings.subtitle')}
	/>

	<div class="settings-stack">
		<Tabs id="settings-tabs" value={selected} items={tabs} onchange={selectDestination} ariaLabel={t('settings.destinations')} />
		<p class="settings-help">{t('settings.draftHelp')}</p>
		<div id="settings-branding-panel" role="tabpanel" aria-labelledby="settings-tabs-branding" hidden={selected !== 'branding'}>
			<AdminLoginBrandingPanel {token} {projectId} />
		</div>
		<div id="settings-infrastructure-panel" role="tabpanel" aria-labelledby="settings-tabs-infrastructure" hidden={selected !== 'infrastructure'}>
			<AdminResourcePoliciesPanel {token} {projectId} />
		</div>
		<div id="settings-enrollment-panel" role="tabpanel" aria-labelledby={`settings-tabs-${selected}`} hidden={!enrollmentSelected}>
			<AdminEnrollmentPolicyPanel section={selected === 'quotas' ? 'quotas' : selected === 'requests' ? 'requests' : 'policy'} />
		</div>
		<div id="settings-email-panel" role="tabpanel" aria-labelledby="settings-tabs-email" hidden={selected !== 'email'}>
			<AdminEmailSettingsPanel />
		</div>
	</div>
</PageShell>

<style>
	.settings-stack {
		display: grid;
		gap: 1rem;
	}

	.settings-help {
		margin: 0;
		max-width: 65ch;
		font-size: 0.875rem;
		line-height: 1.6;
		color: var(--color-ink-2);
	}
</style>
