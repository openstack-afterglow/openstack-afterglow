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
	import ExperienceSupportCode from '$lib/components/ui/ExperienceSupportCode.svelte';
	import { t } from '$lib/i18n/ns/nav';
	import { auth } from '$lib/stores/auth';
	import TextInput from '$lib/components/ui/TextInput.svelte';
	import { emptyNavigationPreferences, navigationPreferenceKey, readNavigationPreferences, saveNavigationPreferences, type NavigationPreferences } from '$lib/stores/navigationPreferences';
	import { adminInventoryScope } from '$lib/stores/adminInventoryScope';
	import { t as ts } from '$lib/i18n/ns/shell';
	import { mobileViewport } from '$lib/utils/mobileViewport';
	import { fuzzyMatch, loadResourceSearchEntries, resourceSearchIcons, type ResourceSearchEntry } from '$lib/utils/resourceSearch';

	interface Props {
		rootHref: string;
		rootLabel: string;
		overviewItems: NavItem[];
		sections: NavSection[];
		isItemVisible: (item: NavItem) => boolean;
		isSectionVisible: (section: NavSection) => boolean;
		footer?: Snippet;
	}

	type CurrentContext = { item: NavItem; key: string; label: string; icon?: string; items: NavItem[] };
	let { rootHref, rootLabel, overviewItems, sections, isItemVisible, isSectionVisible, footer }: Props = $props();
	let expanded = $state<Record<string, boolean>>({});
	let previousPath = untrack(() => $page.url.pathname);
	const visibleOverview = $derived(overviewItems.filter(isItemVisible));
	const visibleSections = $derived(sections.filter(isSectionVisible).map(section => ({ ...section, items: section.items.filter(isItemVisible) })));
	let serviceQuery = $state('');
	let allServicesExpanded = $state(true);
	let preferences = $state<NavigationPreferences>(emptyNavigationPreferences());
	let preferenceOwner = $state('');
	const preferenceKey = $derived($auth.userId && $auth.identityDomainId
		? navigationPreferenceKey($auth.identityDomainId, $auth.userId, rootHref === '/admin' ? 'admin' : 'user') : '');
	const serviceDestinations = $derived(visibleSections.flatMap(section => section.items).filter(item => !visibleOverview.some(hub => hub.href === item.href)));
	const catalogSections = $derived(visibleSections.map(section => ({ ...section, items: section.items.filter(item => !visibleOverview.some(hub => hub.href === item.href)) })).filter(section => section.items.length));
	const matchedDestinations = $derived(serviceDestinations.filter(item => `${item.label} ${visibleSections.find(section => section.items.some(row => row.href === item.href))?.label ?? ''}`.toLocaleLowerCase().includes(serviceQuery.trim().toLocaleLowerCase())));
	const pinned = $derived(preferenceOwner === preferenceKey ? preferences.pinned.flatMap(href => serviceDestinations.find(item => item.href === href) ?? []) : []);
	const scopeLabel = $derived(rootHref === '/admin' ? ($adminInventoryScope.projectId || $adminInventoryScope.domainId ? t('scope.filtered', { id: $adminInventoryScope.projectId || $adminInventoryScope.domainId }) : t('scope.allProjects')) : t('scope.currentProject', { name: $auth.projectName || '—' }));

	// Mobile (<768px) drawer: one search over project resources and every menu destination, Hub + Services body.
	const mobile = $derived(mobileViewport.current);
	const mockupAdminActive = $derived($page.data.mockup?.active === true && $page.data.mockup.profile === 'admin');
	const mobileHub = $derived(visibleOverview.filter(item => !item.mobileHidden));
	const searchTerm = $derived(serviceQuery.trim());
	const mobileServiceMatches = $derived(searchTerm ? [...visibleOverview, ...serviceDestinations].filter(item => `${item.label} ${visibleSections.find(section => section.items.some(row => row.href === item.href))?.label ?? rootLabel}`.toLocaleLowerCase().includes(searchTerm.toLocaleLowerCase())) : []);
	let resourceEntries = $state<ResourceSearchEntry[]>([]);
	let resourceLoading = $state(false);
	let resourceIndexKey = '';
	let resourceIndexedAt = 0;
	let resourceRequest = 0;
	const resourceMatches = $derived(searchTerm ? resourceEntries.filter(entry => fuzzyMatch(searchTerm, entry.name) || fuzzyMatch(searchTerm, ts(`palette.kind.${entry.kind}`))).slice(0, 8) : []);
	$effect(() => {
		if (!mobile || !$sidebarOpen || !searchTerm) return;
		const key = `${$auth.userId ?? ''}|${$auth.projectId ?? ''}`;
		untrack(() => void loadResources(key));
	});
	async function loadResources(key: string) {
		if (mockupAdminActive) {
			resourceEntries = [];
			return;
		}
		if (key === resourceIndexKey && Date.now() - resourceIndexedAt < 60_000) return;
		if (key !== resourceIndexKey) resourceEntries = [];
		resourceIndexKey = key;
		resourceIndexedAt = Date.now();
		const request = ++resourceRequest;
		resourceLoading = true;
		try {
			const entries = await loadResourceSearchEntries($auth.token ?? undefined, $auth.projectId ?? undefined);
			if (request === resourceRequest) resourceEntries = entries;
		} catch {
			// A failed resource index leaves menu destinations searchable.
		} finally {
			if (request === resourceRequest) resourceLoading = false;
		}
	}
	function selectFirstResult(event: KeyboardEvent) {
		if (event.key !== 'Enter') return;
		const first = document.querySelector<HTMLAnchorElement>('#console-navigation-results a[href]');
		if (!first) return;
		event.preventDefault();
		first.click();
	}
	$effect(() => {
		const key = preferenceKey;
		untrack(() => {
			if (preferenceOwner !== key) {
				preferenceOwner = key;
				preferences = key ? readNavigationPreferences(key) : emptyNavigationPreferences();
				serviceQuery = '';
				allServicesExpanded = true;
				expanded = {};
			}
		});
	});
	function togglePinned(href: string) {
		if (!preferenceKey || preferenceOwner !== preferenceKey || !serviceDestinations.some(item => item.href === href)) return;
		const paths = preferences.pinned.includes(href) ? preferences.pinned.filter(path => path !== href) : [...preferences.pinned, href].slice(-20);
		preferences = { ...preferences, pinned: paths };
		saveNavigationPreferences(preferenceKey, preferences);
	}

	const current = $derived.by((): CurrentContext | null => {
		const pathname = $page.url.pathname;
		let match: CurrentContext | null = null;
		const consider = (item: NavItem, key: string, label: string, items: NavItem[], icon?: string) => {
			if ((pathname === item.href || (item.href !== rootHref && pathname.startsWith(`${item.href}/`))) && (!match || item.href.length > match.item.href.length)) {
				match = { item, key, label, items, icon };
			}
		};
		for (const item of visibleOverview) consider(item, rootHref, rootLabel, visibleOverview);
		for (const section of visibleSections) {
			for (const item of section.items) consider(item, section.prefix, section.label, section.items, section.icon);
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
		if (!$sidebarOpen) untrack(() => {
			serviceQuery = '';
			allServicesExpanded = true;
			expanded = {};
		});
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
		serviceQuery = '';
	}
	function openSearch() {
		sidebarOpen.close();
		palette.open();
	}
</script>

{#if hasContext}
	<div class="hidden w-[var(--app-sidebar-offset)] shrink-0 md:block" aria-hidden="true"></div>
	<aside id="app-service-sidebar" aria-label={t('accessibility.pageMenu')} class="fixed bottom-0 left-0 top-[var(--app-header-height)] z-[var(--z-sidebar)] hidden w-[var(--app-sidebar-offset)] flex-col border-r border-line bg-surface-base md:flex">
		<div class="flex min-h-16 shrink-0 items-center gap-2 py-2" class:px-4={$sidebarExpanded} class:justify-center={!$sidebarExpanded}>
			{#if $sidebarExpanded}
				{#if current?.icon}<svg class="size-5 shrink-0 text-ink-2" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d={current.icon} /></svg>{/if}
				<div class="min-w-0 flex-1">
					{#if current && current.label !== pageTitle}<p class="truncate text-xs text-ink-2">{current.label}</p>{/if}
					<h2 class="truncate text-[0.9375rem] font-semibold text-ink-0" title={pageTitle}>{pageTitle}</h2>
				</div>
			{/if}
			<button id="app-service-sidebar-toggle" type="button" onclick={sidebarExpanded.toggle} aria-expanded={$sidebarExpanded} aria-controls="app-service-navigation" aria-label={$sidebarExpanded ? t('accessibility.collapseServiceMenu') : t('accessibility.expandServiceMenu')} title={$sidebarExpanded ? t('accessibility.collapseServiceMenu') : t('accessibility.expandServiceMenu')} class="flex size-11 shrink-0 items-center justify-center rounded-md text-ink-2 transition-colors hover:bg-surface-sunken hover:text-ink-0 focus-visible:outline-none focus-visible:shadow-[var(--focus-ring)]">
				<svg class="size-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d={$sidebarExpanded ? 'M9 4v16M14 8l-4 4 4 4M4 4h16v16H4z' : 'M9 4v16M12 8l4 4-4 4M4 4h16v16H4z'} /></svg>
			</button>
		</div>
		<div class="mb-2 shrink-0 border-b border-line pb-2" class:px-3={$sidebarExpanded}>
			<button type="button" onclick={sidebarOpen.open} aria-haspopup="dialog" aria-controls="app-navigation-menu" aria-expanded={$sidebarOpen} title={t('accessibility.allServices')} class="nav-item service-nav-item w-full gap-3 text-left" class:nav-compact={!$sidebarExpanded}>
				<svg class="size-4 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.8" d="m10 6-6 6 6 6M4 12h16" /></svg>
				<span class:sr-only={!$sidebarExpanded}>{t('accessibility.allServices')}</span>
			</button>
		</div>
		<nav id="app-service-navigation" aria-label={t('accessibility.currentService')} class="min-h-0 flex-1 space-y-0.5 overflow-y-auto pb-4 pt-1" class:px-3={$sidebarExpanded} class:overflow-x-hidden={!$sidebarExpanded}>
			{#each contextItems as item (item.href)}
				<a href={item.href} title={item.label} aria-current={current?.item.href === item.href ? 'page' : undefined} class="nav-item service-nav-item gap-3" class:nav-active={current?.item.href === item.href} class:nav-compact={!$sidebarExpanded}>
					<svg class="size-4 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d={item.icon} /></svg>
					<span class:sr-only={!$sidebarExpanded} class:truncate={$sidebarExpanded}>{item.label}</span>
				</a>
			{/each}
		</nav>
		{#if $sidebarExpanded}
			<div class="min-h-0 max-h-[40%] shrink-0 overflow-y-auto border-t border-line">
				<ExperienceSupportCode />
				{#if footer}{@render footer()}{/if}
			</div>
		{/if}
	</aside>
{/if}

{#if $sidebarOpen}
	<div use:dialogFocus={{ enabled: true, onEscape: () => sidebarOpen.close(), initialFocus: '#app-navigation-close' }} role="dialog" aria-modal="true" aria-label={t('accessibility.allMenu')} tabindex="-1" class="fixed inset-0 z-[var(--z-modal)]">
		<div onclick={() => sidebarOpen.close()} aria-hidden="true" data-navigation-backdrop class="motion-fade absolute inset-0 cursor-default bg-surface-scrim-soft"></div>
		{#if mobile}
		<aside id="app-navigation-menu" aria-label={rootHref === '/admin' ? t('accessibility.adminNavigation') : t('accessibility.userNavigation')} data-navigation-layout="mobile" class="motion-enter relative flex h-[100dvh] w-full flex-col bg-surface-base">
			<div class="flex h-[var(--app-header-height)] shrink-0 items-center justify-between gap-2 border-b border-line px-3">
				<a href={rootHref} onclick={selectPage} class="flex min-w-0 items-center gap-2.5 text-[15px] font-semibold tracking-tight text-ink-0 transition-colors hover:text-ink-1" title={$siteConfig.site_name}>
					<img src="/afterglow-symbol.svg" alt="" width="24" height="24" class="shrink-0" />
					<span class="min-w-0 truncate">{$siteConfig.site_name}</span>
				</a>
				<button id="app-navigation-close" type="button" onclick={() => sidebarOpen.close()} aria-label={t('accessibility.closeAllMenu')} title={t('accessibility.closeAllMenu')} class="-mr-1 flex size-11 shrink-0 items-center justify-center rounded-md border border-line text-ink-1 transition-colors hover:bg-surface-sunken hover:text-ink-0 focus-visible:outline-none focus-visible:shadow-[var(--focus-ring)]">
					<svg class="size-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="m6 6 12 12M6 18 18 6" /></svg>
				</button>
			</div>
			<div class="shrink-0 border-b border-line px-3 py-3">
				<label for="console-navigation-search" class="sr-only">{t('actions.searchAll')}</label>
				<TextInput id="console-navigation-search" type="search" bind:value={serviceQuery} placeholder={t('actions.searchAll')} autocomplete="off" onkeydown={selectFirstResult} class="w-full" />
			</div>
			<div class="min-h-0 flex-1 overflow-y-auto px-3 py-3">
				{#if searchTerm}
					<div id="console-navigation-results">
						<p class="sr-only" aria-live="polite">{t('search.resultCount', { count: resourceMatches.length + mobileServiceMatches.length })}</p>
						<section aria-label={t('search.resources')} class="space-y-0.5">
							<h2 class="px-3 pb-1 text-xs font-medium text-ink-2">{t('search.resources')}</h2>
							{#each resourceMatches as entry (`${entry.kind}:${entry.id}`)}
								<a href={entry.href} onclick={selectPage} class="nav-item min-w-0 gap-2">
									<svg class="size-4 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.8" d={resourceSearchIcons[entry.kind]} /></svg>
									<span class="min-w-0 flex-1 truncate">{entry.name}</span>
									<span class="shrink-0 text-xs font-normal text-ink-2">{ts(`palette.kind.${entry.kind}`)}</span>
								</a>
							{/each}
							{#if resourceMatches.length === 0}<p class="px-3 py-2 text-sm text-ink-2">{resourceLoading ? t('search.loadingResources') : t('search.noResources')}</p>{/if}
						</section>
						<nav aria-label={t('sections.services')} class="mt-4 space-y-0.5">
							<h2 class="px-3 pb-1 text-xs font-medium text-ink-2">{t('sections.services')}</h2>
							{#each mobileServiceMatches as item (item.href)}{@render destinationRow(item, !visibleOverview.some(hub => hub.href === item.href))}{/each}
							{#if mobileServiceMatches.length === 0}<p class="px-3 py-2 text-sm text-ink-2">{t('search.noServices')}</p>{/if}
						</nav>
					</div>
				{:else}
					<nav aria-label={t('sections.hub')} class="space-y-0.5">
						<h2 class="px-3 pb-1 text-xs font-medium text-ink-2">{t('sections.hub')}</h2>
						{#each mobileHub as item (item.href)}{@render destinationRow(item, false)}{/each}
						{#each pinned as item (item.href)}{@render destinationRow(item)}{/each}
					</nav>
					<section aria-labelledby="console-mobile-services-heading" class="mt-4">
						<h2 id="console-mobile-services-heading" class="px-3 pb-1 text-xs font-medium text-ink-2">{t('sections.services')}</h2>
						{@render serviceCatalog()}
					</section>
				{/if}
				<div data-navigation-bottom class="-mx-3 mt-4 border-t border-line">
					<p class="break-words px-4 pt-3 text-xs text-ink-2">{scopeLabel}</p>
					{#if footer}{@render footer()}{/if}
					<ExperienceSupportCode />
					<p class="px-4 pb-3 text-xs text-ink-2">{$siteConfig.site_name === 'Afterglow' ? 'Afterglow' : `${$siteConfig.site_name} · Powered by Afterglow`}</p>
				</div>
			</div>
		</aside>
		{:else}
		<aside id="app-navigation-menu" aria-label={rootHref === '/admin' ? t('accessibility.adminNavigation') : t('accessibility.userNavigation')} class="motion-enter relative flex h-[100dvh] w-[min(var(--app-sidebar-width),100vw)] flex-col bg-surface-base shadow-[var(--shadow-restraint)]">
			<div class="flex h-[var(--app-header-height)] shrink-0 items-center gap-2 border-b border-line px-3 sm:gap-3 md:px-6">
				<button id="app-navigation-close" type="button" onclick={() => sidebarOpen.close()} aria-label={t('accessibility.closeAllMenu')} class="-ml-2 flex size-11 shrink-0 items-center justify-center rounded-md text-ink-2 transition-colors hover:bg-surface-sunken hover:text-ink-0 focus-visible:outline-none focus-visible:shadow-[var(--focus-ring)] lg:size-9">
					<svg class="size-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="m6 6 12 12M6 18 18 6" /></svg>
				</button>
				<a href={rootHref} onclick={selectPage} class="flex min-w-0 items-center gap-2.5 text-[15px] font-semibold tracking-tight text-ink-0 transition-colors hover:text-ink-1" title={$siteConfig.site_name}>
					<img src="/afterglow-symbol.svg" alt="" width="24" height="24" class="shrink-0" />
					<span class="max-w-36 truncate">{$siteConfig.site_name}</span>
				</a>
			</div>
			<div class="flex min-h-0 flex-1 flex-col">
			<div data-navigation-shortcuts class="min-h-0 max-h-[60%] shrink-0 overflow-y-auto border-b border-line px-3 py-3">
				<nav aria-label={t('sections.hub')} class="space-y-0.5">
					<h2 class="px-3 pb-1 text-xs font-medium text-ink-2">{t('sections.hub')}</h2>
					{#each visibleOverview as item (item.href)}{@render destinationRow(item, false)}{/each}
				</nav>
				{#if pinned.length}
					<section class="mt-3 space-y-0.5" aria-label={t('sections.favorites')}>
						<h2 class="px-3 pb-1 text-xs font-medium text-ink-2">{t('sections.favorites')}</h2>
						{#each pinned as item (item.href)}{@render destinationRow(item)}{/each}
					</section>
				{/if}
			</div>
			<div class="min-h-0 flex-1 overflow-y-auto px-3 py-3">
				<div class="mb-3 lg:hidden">
					<Button variant="secondary" onclick={openSearch} class="w-full" ariaLabel={t('accessibility.search')}>
						<svg class="size-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="m21 21-4.35-4.35M17 11a6 6 0 1 1-12 0 6 6 0 0 1 12 0" /></svg>
						{t('actions.searchResources')}
					</Button>
				</div>
				<label for="console-service-search" class="mb-1 block text-xs text-ink-2">{t('actions.searchServices')}</label>
				<TextInput id="console-service-search" type="search" bind:value={serviceQuery} class="mb-3 w-full" />
				<p class="mb-3 break-words text-xs text-ink-2">{scopeLabel}</p>
				{#if serviceQuery.trim()}
					<nav aria-label={t('actions.searchServices')} class="mb-3 space-y-0.5">
						{#each matchedDestinations as item (item.href)}{@render destinationRow(item)}{/each}
						{#if matchedDestinations.length === 0}<p class="px-3 py-2 text-sm text-ink-2">{t('search.noMatches')}</p>{/if}
					</nav>
				{:else}
				<button type="button" onclick={() => allServicesExpanded = !allServicesExpanded} aria-expanded={allServicesExpanded} aria-controls="console-service-catalog" class="nav-item w-full justify-between gap-2 text-left">
					<span>{t('accessibility.allServices')}</span>
					<svg class="nav-chevron size-3.5 shrink-0" class:rotate-90={allServicesExpanded} fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="m9 5 7 7-7 7" /></svg>
				</button>
				{#if allServicesExpanded}
				{@render serviceCatalog()}
				{/if}
				{/if}
			</div>
			</div>
			<p class="shrink-0 px-6 pb-3 text-xs text-ink-2">{$siteConfig.site_name === 'Afterglow' ? 'Afterglow' : `${$siteConfig.site_name} · Powered by Afterglow`}</p>
			<div class="min-h-0 max-h-[35%] shrink-0 overflow-y-auto border-t border-line">
				<ExperienceSupportCode />
				{#if footer}{@render footer()}{/if}
			</div>
		</aside>
		{/if}
	</div>
{/if}

{#snippet serviceCatalog()}
	<nav id="console-service-catalog" aria-label={t('accessibility.allServices')} class="mt-1 space-y-0.5">
		{#each catalogSections as section (section.prefix)}
			{#if section.items.length === 1 && section.items[0].topLevel}
				{@render destinationRow(section.items[0])}
			{:else}
				<div>
					<button type="button" onclick={() => expanded[section.prefix] = !expanded[section.prefix]} aria-expanded={!!expanded[section.prefix]} class="nav-item w-full justify-between gap-2 text-left">
						<span class="flex min-w-0 items-center gap-2">
							<svg class="size-4 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d={section.icon} /></svg>
							<span class="truncate">{section.label}</span>
						</span>
						<svg class="nav-chevron size-3.5 shrink-0" class:rotate-90={!!expanded[section.prefix]} fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="m9 5 7 7-7 7" /></svg>
					</button>
					{#if expanded[section.prefix]}
						<div class="motion-fade ml-4 space-y-0.5">
							{#each section.items as item (item.href)}
								{@render destinationRow(item)}
							{/each}
						</div>
					{/if}
				</div>
			{/if}
		{/each}
	</nav>
{/snippet}

{#snippet destinationRow(item: NavItem, pinnable = true)}
	<div class="flex min-w-0 items-center gap-1">
		<a href={item.href} onclick={selectPage} aria-current={current?.item.href === item.href ? 'page' : undefined} class="nav-item min-w-0 flex-1 gap-2" class:nav-active={current?.item.href === item.href}>
			<svg class="size-4 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.8" d={item.icon} /></svg><span class="min-w-0 break-words">{item.label}</span>
		</a>
		{#if pinnable && preferenceKey}<Button variant="ghost" size="icon" class="shrink-0" ariaPressed={preferences.pinned.includes(item.href)} ariaLabel={t(preferences.pinned.includes(item.href) ? 'actions.unpin' : 'actions.pin', { name: item.label })} onclick={() => togglePinned(item.href)}>
			<svg class="size-3.5" fill={preferences.pinned.includes(item.href) ? 'currentColor' : 'none'} stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true"><path stroke-linejoin="round" stroke-width="1.8" d="m12 3 2.8 5.7 6.2.9-4.5 4.4 1.1 6.2-5.6-3-5.6 3 1.1-6.2L3 9.6l6.2-.9L12 3Z" /></svg>
		</Button>{/if}
	</div>
{/snippet}

<style>
	.nav-item {
		display: flex;
		min-height: 2.25rem;
		align-items: center;
		border-radius: var(--radius-md);
		padding: 0.375rem 0.75rem;
		color: var(--color-ink-2);
		font-size: 0.8125rem;
		font-weight: 500;
		transition: color var(--motion-duration-fast) var(--motion-ease-standard), background-color var(--motion-duration-fast) var(--motion-ease-standard);
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
	.nav-chevron {
		transition: transform var(--motion-duration-fast) var(--motion-ease-standard);
	}
	@media (max-width: 767px), (pointer: coarse) {
		.nav-item, #app-navigation-close {
			min-height: 2.75rem;
		}
		#app-navigation-close {
			min-width: 2.75rem;
		}
	}
</style>
