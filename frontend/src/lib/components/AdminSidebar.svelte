<script lang="ts">
	import { page } from '$app/stores';
	import { auth } from '$lib/stores/auth';
	import ProjectSelector from '$lib/components/ProjectSelector.svelte';
	import { siteConfig } from '$lib/config/site';
	import { betaFeatures } from '$lib/stores/betaFeatures';
	import type { BetaFeatures } from '$lib/stores/betaFeatures';
	import { isMockupPathAllowed } from '$lib/mockup/contracts';
	import ConsoleNavigation from '$lib/components/ConsoleNavigation.svelte';
	import { adminNavSections, navIcons } from '$lib/config/nav';

	type BetaFeatureKey = keyof BetaFeatures;
	const mockupAdminActive = $derived($page.data.mockup?.active === true && $page.data.mockup.profile === 'admin');

	function isBetaVisible(beta?: BetaFeatureKey): boolean {
		return mockupAdminActive || !beta || Boolean($betaFeatures[beta]);
	}

	function isItemVisible(item: { href: string; beta?: BetaFeatureKey; service?: string | null }): boolean {
		if (mockupAdminActive) return isMockupPathAllowed('admin', item.href);
		if (!isBetaVisible(item.beta)) return false;
		const svcs = $siteConfig.services as Record<string, boolean> | undefined;
		if (!item.service) return true;
		return svcs?.[item.service] ?? false;
	}

	function isSectionVisible(section: { beta?: BetaFeatureKey; service?: string | null; items: { href: string; beta?: BetaFeatureKey; service?: string | null }[] }): boolean {
		if (mockupAdminActive) return section.items.some(item => isItemVisible(item));
		const svcs = $siteConfig.services as Record<string, boolean> | undefined;
		if (!isBetaVisible(section.beta)) return false;
		if (section.service && !(svcs?.[section.service] ?? false)) return false;
		return section.items.some(item => isItemVisible(item));
	}
</script>

{#snippet footer()}
	<div class="lg:hidden">
		<div class="px-4 py-3 text-[13px] font-medium text-ink-1 truncate">{$auth.username}</div>
		<div class="p-3 pt-0 md:hidden">
			<div class="text-[10px] text-ink-2 uppercase tracking-wide px-1 mb-1.5">프로젝트</div>
			<ProjectSelector />
		</div>
		{#if !mockupAdminActive}
			<div class="p-3 pt-0">
				<a
					href="/dashboard"
					aria-label="현재 관리자 모드, 사용자 모드로 전환"
					title="사용자 모드로 전환"
					class="nav-item nav-active flex items-center gap-2 px-3 py-2 rounded-lg text-sm transition-colors"
				>
					<svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 2l8 4v6c0 5-3.5 9-8 10-4.5-1-8-5-8-10V6l8-4z"></path></svg>
					관리자 모드
				</a>
			</div>
		{/if}
	</div>
{/snippet}

<ConsoleNavigation
	rootHref="/admin"
	rootLabel="개요"
	overviewItems={[{ label: '개요', href: '/admin', icon: navIcons.overview, service: null }]}
	sections={adminNavSections}
	{isItemVisible}
	{isSectionVisible}
	{footer}
/>

<style>
	.nav-item {
		color: var(--color-ink-2);
		font-weight: 500;
	}
	.nav-item:hover:not(.nav-active) {
		color: var(--color-ink-0);
		background-color: var(--color-surface-sunken);
	}
	.nav-active {
		background: var(--color-surface-selected);
		color: var(--color-ink-0);
		font-weight: 600;
	}

	@media (pointer: coarse) {
		.nav-item {
			min-height: 2.75rem;
		}
	}
</style>