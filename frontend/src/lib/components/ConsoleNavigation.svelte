<script lang="ts">
	import { untrack } from 'svelte';
	import type { Snippet } from 'svelte';
	import { page } from '$app/stores';
	import type { NavItem, NavSection } from '$lib/config/nav';
	import { derivePageTitle } from '$lib/config/routes';
	import { siteConfig } from '$lib/config/site';
	import { sidebarExpanded, sidebarOpen } from '$lib/stores/sidebar';
	import { palette } from '$lib/stores/palette';
	import { dialogFocus } from '$lib/utils/dialogFocus';
	import Button from '$lib/components/ui/Button.svelte';

	interface Props {
		rootHref: string;
		rootLabel: string;
		overviewItems: NavItem[];
		sections: NavSection[];
		isItemVisible: (item: NavItem) => boolean;
		isSectionVisible: (section: NavSection) => boolean;
		topActions?: Snippet;
		footer?: Snippet;
	}

	type CurrentContext = { item: NavItem; label: string; icon?: string; items: NavItem[] };
	let { rootHref, rootLabel, overviewItems, sections, isItemVisible, isSectionVisible, topActions, footer }: Props = $props();
	let expanded = $state<Record<string, boolean>>({});
	let previousPath = untrack(() => $page.url.pathname);
	let previousOwner = '';
	const visibleOverview = $derived(overviewItems.filter(isItemVisible));
	const visibleSections = $derived(sections.filter(isSectionVisible).map(section => ({ ...section, items: section.items.filter(isItemVisible) })));

	const current = $derived.by((): CurrentContext | null => {
		const pathname = $page.url.pathname;
		let match: CurrentContext | null = null;
		const consider = (item: NavItem, label: string, items: NavItem[], icon?: string) => {
			if ((pathname === item.href || (item.href !== rootHref && pathname.startsWith(`${item.href}/`))) && (!match || item.href.length > match.item.href.length)) {
				match = { item, label, items, icon };
			}
		};
		for (const item of visibleOverview) consider(item, rootLabel, visibleOverview);
		for (const section of visibleSections) {
			for (const item of section.items) consider(item, section.label, section.items, section.icon);
		}
		return match;
	});
	const hasContext = $derived(current !== null && $page.url.pathname !== rootHref && (current.items !== visibleOverview || !current.item.topLevel));
	$effect(() => {
		document.documentElement.dataset.consoleSidebar = hasContext ? ($sidebarExpanded ? 'expanded' : 'collapsed') : 'hidden';
		return () => { delete document.documentElement.dataset.consoleSidebar; };
	});
	const pageTitle = $derived(current?.item.label ?? derivePageTitle($page.url.pathname));
	const contextItems = $derived(current?.items ?? []);

	$effect(() => {
		const label = current?.label;
		const owner = `${$page.url.pathname}:${label ?? ''}`;
		if (owner !== previousOwner) {
			previousOwner = owner;
			if (label) untrack(() => { expanded[label] = true; });
		}
	});
	$effect(() => {
		const pathname = $page.url.pathname;
		if (pathname !== previousPath) {
			previousPath = pathname;
			sidebarOpen.close();
		}
	});

	function selectPage() {
		sidebarExpanded.open();
		sidebarOpen.close();
	}
	function openSearch() {
		sidebarOpen.close();
		palette.open();
	}
</script>

{#if hasContext}
	<div class="hidden w-[var(--app-sidebar-offset)] shrink-0 md:block" aria-hidden="true"></div>
	<aside id="app-service-sidebar" aria-label="페이지 메뉴" class="fixed bottom-0 left-0 top-[var(--app-header-height)] z-[var(--z-sidebar)] hidden w-[var(--app-sidebar-offset)] flex-col border-r border-line bg-surface-base md:flex">
		<div class="flex min-h-16 shrink-0 items-center gap-2 py-2" class:px-4={$sidebarExpanded} class:justify-center={!$sidebarExpanded}>
			{#if $sidebarExpanded}
				{#if current?.icon}<svg class="size-5 shrink-0 text-ink-2" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d={current.icon} /></svg>{/if}
				<div class="min-w-0 flex-1">
					{#if current && current.label !== pageTitle}<p class="truncate text-xs text-ink-2">{current.label}</p>{/if}
					<h2 class="truncate text-[0.9375rem] font-semibold text-ink-0" title={pageTitle}>{pageTitle}</h2>
				</div>
			{/if}
			<button id="app-service-sidebar-toggle" type="button" onclick={sidebarExpanded.toggle} aria-expanded={$sidebarExpanded} aria-controls="app-service-navigation" aria-label={$sidebarExpanded ? '서비스 메뉴 접기' : '서비스 메뉴 펼치기'} title={$sidebarExpanded ? '서비스 메뉴 접기' : '서비스 메뉴 펼치기'} class="flex size-11 shrink-0 items-center justify-center rounded-md text-ink-2 transition-colors hover:bg-surface-sunken hover:text-ink-0 focus-visible:outline-none focus-visible:shadow-[var(--focus-ring)]">
				<svg class="size-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d={$sidebarExpanded ? 'M9 4v16M14 8l-4 4 4 4M4 4h16v16H4z' : 'M9 4v16M12 8l4 4-4 4M4 4h16v16H4z'} /></svg>
			</button>
		</div>
		{#if $sidebarExpanded && topActions && !$sidebarOpen}<div class="px-3 pb-3">{@render topActions()}</div>{/if}
		<nav id="app-service-navigation" aria-label="현재 서비스" class="min-h-0 flex-1 space-y-0.5 overflow-y-auto pb-4 pt-1" class:px-3={$sidebarExpanded} class:overflow-x-hidden={!$sidebarExpanded}>
			{#each contextItems as item (item.href)}
				<a href={item.href} title={item.label} aria-current={current?.item.href === item.href ? 'page' : undefined} class="nav-item service-nav-item gap-3" class:nav-active={current?.item.href === item.href} class:nav-compact={!$sidebarExpanded}>
					<svg class="size-4 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d={item.icon} /></svg>
					<span class:sr-only={!$sidebarExpanded} class:truncate={$sidebarExpanded}>{item.label}</span>
				</a>
			{/each}
		</nav>
		{#if $sidebarExpanded && footer}<div class="shrink-0 border-t border-line">{@render footer()}</div>{/if}
	</aside>
{/if}

{#if $sidebarOpen}
	<div use:dialogFocus={{ enabled: true, onEscape: () => sidebarOpen.close(), initialFocus: '#app-navigation-close' }} role="dialog" aria-modal="true" aria-label="전체 메뉴" tabindex="-1" class="fixed inset-0 z-[var(--z-modal)]">
		<button type="button" onclick={() => sidebarOpen.close()} tabindex="-1" aria-hidden="true" data-navigation-backdrop class="absolute inset-0 cursor-default bg-surface-scrim-soft"></button>
		<aside id="app-navigation-menu" aria-label={rootHref === '/admin' ? '관리자 탐색' : '사용자 탐색'} class="relative flex h-[100dvh] w-[min(var(--app-sidebar-width),100vw)] flex-col bg-surface-base shadow-[var(--shadow-restraint)]">
			<div class="flex h-[var(--app-header-height)] shrink-0 items-center gap-2 border-b border-line px-3 sm:gap-3 md:px-6">
				<button id="app-navigation-close" type="button" onclick={() => sidebarOpen.close()} aria-label="전체 메뉴 닫기" class="-ml-2 flex size-11 shrink-0 items-center justify-center rounded-md text-ink-2 transition-colors hover:bg-surface-sunken hover:text-ink-0 focus-visible:outline-none focus-visible:shadow-[var(--focus-ring)] lg:size-8">
					<svg class="size-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="m6 6 12 12M6 18 18 6" /></svg>
				</button>
				<a href={rootHref} onclick={selectPage} class="flex min-w-0 items-center gap-2.5 text-[15px] font-semibold tracking-tight text-ink-0 transition-colors hover:text-ink-1" title={$siteConfig.site_name}>
					<img src="/afterglow-symbol.svg" alt="" width="24" height="24" class="shrink-0" />
					<span class="max-w-36 truncate">{$siteConfig.site_name}</span>
				</a>
			</div>
			<div class="min-h-0 flex-1 overflow-y-auto px-3 py-3">
				<div class="mb-3 lg:hidden">
					<Button variant="secondary" onclick={openSearch} class="w-full" ariaLabel="검색 (⌘K)">
						<svg class="size-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="m21 21-4.35-4.35M17 11a6 6 0 1 1-12 0 6 6 0 0 1 12 0" /></svg>
						리소스 검색
					</Button>
				</div>
				{#if topActions}<div class="mb-3">{@render topActions()}</div>{/if}
				<nav aria-label="모든 서비스" class="space-y-0.5">
					{#each visibleOverview as item (item.href)}
						<a href={item.href} onclick={selectPage} aria-current={current?.item.href === item.href ? 'page' : undefined} class="nav-item" class:nav-active={current?.item.href === item.href}>{item.label}</a>
					{/each}
					{#each visibleSections as section (section.label)}
						{#if section.items.length === 1 && section.items[0].topLevel}
							<a href={section.items[0].href} onclick={selectPage} aria-current={current?.item.href === section.items[0].href ? 'page' : undefined} class="nav-item gap-2" class:nav-active={current?.item.href === section.items[0].href}>
								<svg class="size-4 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d={section.icon} /></svg>
								{section.items[0].label}
							</a>
						{:else}
							<div>
								<button type="button" onclick={() => expanded[section.label] = !expanded[section.label]} aria-expanded={!!expanded[section.label]} class="nav-item w-full justify-between gap-2 text-left">
									<span class="flex min-w-0 items-center gap-2">
										<svg class="size-4 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d={section.icon} /></svg>
										<span class="truncate">{section.label}</span>
									</span>
									<svg class="size-3.5 shrink-0 transition-transform" class:rotate-90={!!expanded[section.label]} fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="m9 5 7 7-7 7" /></svg>
								</button>
								{#if expanded[section.label]}
									<div class="ml-4 space-y-0.5">
										{#each section.items as item (item.href)}
											<a href={item.href} onclick={selectPage} aria-current={current?.item.href === item.href ? 'page' : undefined} class="nav-item" class:nav-active={current?.item.href === item.href}>{item.label}</a>
										{/each}
									</div>
								{/if}
							</div>
						{/if}
					{/each}
				</nav>
			</div>
			{#if footer}<div class="shrink-0 border-t border-line">{@render footer()}</div>{/if}
		</aside>
	</div>
{/if}

<style>
	.nav-item {
		display: flex;
		min-height: 2rem;
		align-items: center;
		border-radius: var(--radius-md);
		padding: 0.375rem 0.75rem;
		color: var(--color-ink-2);
		font-size: 0.8125rem;
		font-weight: 500;
		transition: color var(--motion-duration-fast), background-color var(--motion-duration-fast);
	}
	.nav-item:hover:not(.nav-active) {
		color: var(--color-ink-0);
		background: var(--color-surface-sunken);
	}
	.nav-item:focus-visible {
		outline: none;
		box-shadow: var(--focus-ring);
	}
	.nav-active {
		color: var(--color-ink-0);
		background: var(--color-surface-selected);
		font-weight: 600;
	}
	.service-nav-item {
		min-height: 2.75rem;
	}
	.nav-compact {
		width: 2.75rem;
		margin-inline: auto;
		justify-content: center;
		padding: 0.375rem;
	}
	@media (pointer: coarse) {
		.nav-item, #app-navigation-close {
			min-height: 2.75rem;
		}
	}
</style>
