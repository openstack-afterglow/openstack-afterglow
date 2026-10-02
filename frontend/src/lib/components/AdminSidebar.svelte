<script lang="ts">
	import { page } from '$app/stores';
	import { auth } from '$lib/stores/auth';
	import { sidebarOpen } from '$lib/stores/sidebar';
	import ProjectSelector from '$lib/components/ProjectSelector.svelte';
	import { siteConfig } from '$lib/config/site';
	import RingMark from '$lib/components/ui/RingMark.svelte';
	import { palette } from '$lib/stores/palette';
	import { betaFeatures, type BetaFeatures } from '$lib/stores/betaFeatures';
	import { isMockupPathAllowed } from '$lib/mockup/contracts';
	import { adminNavSections, isNavSectionActive } from '$lib/config/nav';
	import { t } from '$lib/i18n/ns/shell';
	import { t as tn } from '$lib/i18n/ns/nav';

	type BetaFeatureKey = keyof BetaFeatures;
	const mockupAdminActive = $derived($page.data.mockup?.active === true && $page.data.mockup.profile === 'admin');

	// 섹션 label은 언어를 따라가는 getter이므로 복사하지 않고 펼침 상태만 prefix로 따로 둔다.
	const openSections = $state<Record<string, boolean>>({});

	$effect(() => {
		const pathname = $page.url.pathname;
		for (const section of adminNavSections) {
			if (isNavSectionActive(section, pathname)) {
				openSections[section.prefix] = true;
			}
		}
	});

	// 페이지 이동 시 모바일 드로어 자동 닫기
	$effect(() => {
		$page.url.pathname;
		sidebarOpen.close();
	});
	function closeMobileSidebar() {
		sidebarOpen.close();
		document.getElementById('app-sidebar-trigger')?.focus();
	}

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

<!-- 오버레이 배경 (모바일만) -->
{#if $sidebarOpen}
	<button
		class="fixed inset-0 z-[var(--z-sidebar)] bg-surface-scrim-soft md:hidden"
		onclick={closeMobileSidebar}
		aria-label={t('menu.close')}
	></button>
{/if}

<aside
	id="app-sidebar"
	class="fixed inset-y-0 left-0 z-[var(--z-sidebar)] flex h-[100dvh] w-[var(--app-sidebar-width)] flex-col overflow-y-auto border-r border-line bg-surface-base transition-transform duration-[var(--motion-duration-panel)] ease-out {$sidebarOpen ? 'translate-x-0' : '-translate-x-full'} md:sticky md:top-0 md:shrink-0 md:translate-x-0 md:transition-none"
	aria-label={t('sidebar.adminNav')}
>
	<!-- 로고 헤더 with Admin badge -->
	<div class="flex h-[var(--app-header-height)] shrink-0 items-center gap-2.5 border-b border-line px-4">
		<RingMark size={24} />
		<a href="/admin" class="text-[15px] font-semibold tracking-tight text-ink-0 transition-colors hover:text-ink-1">
			{$siteConfig.site_name}
		</a>
		<span class="ml-auto rounded-md border border-[var(--admin-tone-ring)] bg-[var(--admin-tone-soft)] px-1.5 py-0.5 text-[10px] font-semibold text-[var(--admin-tone)]">{t('sidebar.adminBadge')}</span>
	</div>

	<!-- 검색 버튼 (1024px 미만에서만 표시) -->
	<div class="px-3 pb-1 pt-2 lg:hidden">
		<button
			onclick={() => palette.open()}
			class="flex w-full items-center gap-2 rounded-md border border-line-2 bg-surface-sunken py-1.5 pl-3 pr-2 text-[13px] text-ink-2 transition-colors hover:bg-surface-selected"
			aria-label={t('search.label')}
		>
			<svg class="size-3.5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-4.35-4.35M17 11A6 6 0 115 11a6 6 0 0112 0z"/></svg>
			<span class="flex-1 text-left">{t('search.placeholder')}</span>
			<kbd class="rounded border border-line px-1.5 py-0.5 font-mono text-[10px]">⌘K</kbd>
		</button>
	</div>

	<nav class="flex-1 min-h-0 overflow-y-auto px-3 py-3 space-y-0.5">
		<!-- 개요 -->
		<a
			href="/admin"
			aria-current={$page.url.pathname === '/admin' ? 'page' : undefined}
			class="nav-item flex h-8 items-center gap-2 rounded-md px-3 text-[13px] transition-colors"
			class:nav-active={$page.url.pathname === '/admin'}
		>
			<svg class="size-4 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z"></path></svg>
			{tn('items.overview')}
		</a>

		<!-- 섹션들 -->
		{#each adminNavSections as section (section.prefix)}
			{#if isSectionVisible(section)}
			<div>
				<button
					onclick={() => (openSections[section.prefix] = !openSections[section.prefix])}
					aria-expanded={openSections[section.prefix] === true}
					class="flex items-center justify-between w-full px-3 py-2 rounded-lg text-sm transition-colors {isNavSectionActive(section, $page.url.pathname) ? 'text-ink-0' : 'text-ink-2 hover:text-ink-0 hover:bg-surface-sunken'}"
				>
					<div class="flex items-center gap-1.5">
						{#if section.icon}
							<svg class="w-3.5 h-3.5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d={section.icon}></path></svg>
						{/if}
						<span>{section.label}</span>
					</div>
					<span class="text-xs text-ink-2" aria-hidden="true">{openSections[section.prefix] ? '▾' : '▸'}</span>
				</button>

				{#if openSections[section.prefix]}
					<div class="ml-3 mt-0.5 space-y-0.5">
						{#each section.items as item}
							{#if isItemVisible(item)}
							<a
								href={item.href}
								aria-current={$page.url.pathname === item.href ? 'page' : undefined}
								class="nav-item nav-sub flex h-8 items-center rounded-md px-3 text-[13px] transition-colors"
								class:nav-active={$page.url.pathname === item.href}
							>
								{item.label}
							</a>
							{/if}
						{/each}
					</div>
				{/if}
			</div>
			{/if}
		{/each}
	</nav>

	<!-- 하단: 사용자 정보 + 현재 관리자 모드 -->
	<div class="border-t border-line shrink-0">
		<!-- 데스크톱: 관리자 정보 -->
		<div class="hidden md:block px-4 py-3">
			<div class="text-[10px] text-ink-2 uppercase tracking-widest font-medium">{t('sidebar.admin')}</div>
			<div class="text-[13px] text-ink-1 font-medium mt-0.5 truncate">{$auth.username}</div>
		</div>

		<!-- 모바일 전용 -->
		<div class="p-3 lg:hidden">
			<div class="text-[10px] text-ink-2 uppercase tracking-wide px-1 mb-1.5">{t('sidebar.project')}</div>
			<ProjectSelector />
		</div>
		{#if !mockupAdminActive}
		<div class="p-3 pt-0 lg:hidden">
			<a
				href="/dashboard"
				aria-label={t('mode.adminCurrent')}
				title={t('mode.switchToUser')}
				class="nav-item nav-active flex items-center gap-2 px-3 py-2 rounded-lg text-sm transition-colors"
			>
				<svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 2l8 4v6c0 5-3.5 9-8 10-4.5-1-8-5-8-10V6l8-4z"></path></svg>
				{t('mode.admin')}
			</a>
		</div>
		{/if}
		<div class="p-3 pt-0 md:hidden border-t border-line">
			<div class="px-3 text-xs text-ink-2">{$auth.username}</div>
		</div>
	</div>
</aside>

<style>
	.nav-item {
		color: var(--color-ink-2);
		font-weight: 500;
	}
	.nav-item:hover:not(.nav-active) {
		color: var(--color-ink-0);
		background-color: var(--color-surface-sunken);
	}
	.nav-sub {
		color: var(--color-ink-2);
	}
	.nav-sub:hover:not(.nav-active) {
		color: var(--color-ink-1);
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