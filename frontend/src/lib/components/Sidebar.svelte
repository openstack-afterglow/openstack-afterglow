<script lang="ts">
	import { t } from '$lib/i18n/ns/shell';
	import { t as tn } from '$lib/i18n/ns/nav';
	import { page } from '$app/stores';
	import { auth, isAdmin } from '$lib/stores/auth';
	import ConsoleNavigation from '$lib/components/ConsoleNavigation.svelte';
	import ProjectSelector from '$lib/components/ProjectSelector.svelte';
	import { siteConfig } from '$lib/config/site';
	import { openWizard } from '$lib/stores/wizard';
	import Button from '$lib/components/ui/Button.svelte';
	import { betaFeatures } from '$lib/stores/betaFeatures';
	import type { BetaFeatures } from '$lib/stores/betaFeatures';
	import { documentationNavItem, navIcons, userNavSections } from '$lib/config/nav';
	import type { NavItem, NavSection } from '$lib/config/nav';
	import { isMockupPathAllowed } from '$lib/mockup/contracts';

	const mockupProfile = $derived($page.data.mockup?.active ? $page.data.mockup.profile : null);

	type BetaFeatureKey = keyof BetaFeatures;
	const overviewItems: NavItem[] = $derived([
		{ label: tn('items.overview'), labelKey: 'items.overview', href: '/dashboard', icon: navIcons.overview, service: null },
		{ label: tn('items.usage'), labelKey: 'items.usage', href: '/dashboard/usage', icon: navIcons.chart, service: null },
		{ label: tn('items.usageReport'), labelKey: 'items.usageReport', href: '/dashboard/usage-report', icon: navIcons.document, service: null },
		{ label: tn('items.activity'), labelKey: 'items.activity', href: '/dashboard/activity', icon: navIcons.activity, service: null },
		{ label: tn('items.topology'), labelKey: 'items.topology', href: '/dashboard/network/topology', icon: navIcons.network, service: null, topLevel: true },
		documentationNavItem,
	]);

	function isBetaVisible(beta?: BetaFeatureKey): boolean {
		return !beta || Boolean($betaFeatures[beta]);
	}

	function isSectionServiceVisible(section: { service?: string | null }): boolean {
		const svcs = $siteConfig.services as Record<string, boolean> | undefined;
		if (!section.service) return true;
		if (section.service === 'manila') return svcs?.manila ?? false;
		if (section.service === 'containers') return (svcs?.magnum ?? false) || (svcs?.zun ?? false) || (svcs?.k3s ?? false);
		// AI 채팅은 services.chat([services] chat = true + [chat] base_url 설정)일 때만 노출
		if (section.service === 'chat') return svcs?.chat ?? false;
		return svcs?.[section.service] ?? false;
	}

	function isSectionVisible(section: NavSection): boolean {
		if (!isBetaVisible(section.beta)) return false;
		if (!isSectionServiceVisible(section)) return false;
		return section.items.some(item => isItemVisible(item));
	}

	function isItemVisible(item: NavItem): boolean {
		if (mockupProfile && !isMockupPathAllowed(mockupProfile, item.href)) return false;
		if (!isBetaVisible(item.beta)) return false;
		const svcs = $siteConfig.services as Record<string, boolean> | undefined;
		if (!item.service) return true;
		if (item.service === 'magnum') return svcs?.magnum ?? false;
		if (item.service === 'zun') return svcs?.zun ?? false;
		if (item.service === 'k3s') return svcs?.k3s ?? false;
		if (item.service === 'waygate') return svcs?.waygate ?? false;
		if (item.service === 'chat') return svcs?.chat ?? false;
		return true;
	}
</script>

<ConsoleNavigation
	rootHref="/dashboard"
	rootLabel={tn('sections.dashboard')}
	{overviewItems}
	sections={userNavSections}
	{isSectionVisible}
	{isItemVisible}
>
	{#snippet topActions()}
		<div data-tour="vm-create-open">
			<Button variant="secondary" onclick={() => openWizard()} class="w-full">
				<svg class="size-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 5v14M5 12h14"/></svg>
				{t('sidebar.createVm')}
			</Button>
		</div>
	{/snippet}

	{#snippet footer()}
		<div class="p-3 md:hidden">
			<div class="text-[10px] text-ink-2 uppercase tracking-wide px-1 mb-1.5">{t('sidebar.project')}</div>
			<ProjectSelector />
		</div>

		<div class="hidden lg:block px-4 py-3">
			<div class="text-[10px] text-ink-2 uppercase tracking-widest font-medium">{t('sidebar.project')}</div>
			<div class="text-[13px] text-ink-1 font-medium mt-0.5 truncate">{$auth.projectName ?? '—'}</div>
		</div>

		{#if $isAdmin}
			<div class="px-3 pb-3 lg:hidden">
				<a
					href="/admin"
					aria-label={t('mode.userCurrent')}
					title={t('mode.switchToAdmin')}
					class="flex items-center gap-2 px-3 py-2 rounded-lg text-sm transition-colors duration-[var(--motion-duration-fast)] ease-[var(--motion-ease-standard)] text-ink-2 hover:text-ink-0 hover:bg-surface-sunken"
				>
					<svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z"/></svg>
					{t('mode.user')}
				</a>
			</div>
		{/if}

		<div class="p-3 pt-0 md:hidden border-t border-line">
			<div class="px-3 text-xs text-ink-2">{$auth.username}</div>
		</div>
	{/snippet}
</ConsoleNavigation>
