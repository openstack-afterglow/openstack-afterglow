<script lang="ts">
  import { goto } from '$app/navigation';
  import { page } from '$app/stores';
  import { palette } from '$lib/stores/palette';
  import { auth } from '$lib/stores/auth';
  import { fuzzyMatch, loadResourceSearchEntries, resourceSearchIcons as ICONS } from '$lib/utils/resourceSearch';
  import { allNavItems } from '$lib/config/nav';
  import { canManageDomain, isAdmin } from '$lib/stores/auth';
  import { canManageOrganizationProjects } from '$lib/stores/projectManagement';
  import { betaFeatures, type BetaFeatures } from '$lib/stores/betaFeatures';
  import { siteConfig } from '$lib/config/site';
  import { isMockupPathAllowed } from '$lib/mockup/contracts';
  import { dialogFocus } from '$lib/utils/dialogFocus';
  import { t } from '$lib/i18n/ns/shell';

  interface PaletteItem {
    id: string;
    label: string;
    sublabel?: string;
    type: 'route' | 'instance' | 'volume' | 'image' | 'network' | 'router';
    href: string;
    icon?: string;
  }

  const MOCKUP_BETA_FEATURES: BetaFeatures = {
    keyManager: true,
    volumeSnapshots: true,
    fileStorageSnapshots: true,
    fileStorageShareNetworks: true,
    fileStorageSecurityServices: true,
  };

  let query = $state('');
  let selectedIdx = $state(0);
  let inputEl = $state<HTMLInputElement | null>(null);
  let indexedAt = $state(0);
  let resourceItems = $state<PaletteItem[]>([]);
  const listboxId = 'command-palette-results';
  const mockupAdminActive = $derived($page.data.mockup?.active === true && $page.data.mockup.profile === 'admin');
  const administratorSurface = $derived($page.url.pathname === '/admin' || $page.url.pathname.startsWith('/admin/'));
  const paletteBetaFeatures = $derived(mockupAdminActive ? MOCKUP_BETA_FEATURES : $betaFeatures);

  // 비활성 서비스 route는 sidebar와 동일하게 command palette에서도 숨긴다.
  const navItems = $derived(allNavItems($isAdmin && administratorSurface, paletteBetaFeatures, { domainManager: $canManageDomain, projectManagement: $canManageOrganizationProjects })
    .filter((item) => !item.service || (($siteConfig.services as Record<string, boolean>)[item.service] ?? false))
    .filter((item) => !mockupAdminActive || isMockupPathAllowed('admin', item.href))
    .map((item) => ({
      id: `route:${item.href}`,
      label: item.label,
      sublabel: item.section,
      type: 'route' as const,
      href: item.href,
      icon: ICONS.route,
    })));

  async function loadResources() {
    if (mockupAdminActive) {
      resourceItems = [];
      return;
    }
    const now = Date.now();
    if (now - indexedAt < 60_000) return;
    indexedAt = now;
    const token = $auth.token ?? undefined;
    const project = $auth.projectId ?? undefined;

    try {
      const entries = await loadResourceSearchEntries(token, project);
      resourceItems = entries.map((entry) => ({ id: entry.id, label: entry.name, sublabel: t(`palette.kind.${entry.kind}`), type: entry.kind, href: entry.href, icon: ICONS[entry.kind] }));
    } catch {
      // index load failure is non-fatal
    }
  }

  function resultId(item: PaletteItem): string {
    return `command-palette-result-${item.id.replace(/[^a-zA-Z0-9_-]/g, '-')}`;
  }

  const results = $derived.by(() => {
    const q = query.trim();
    const all = [...navItems, ...resourceItems];
    if (!q) return navItems.slice(0, 8);
    return all.filter((item) => fuzzyMatch(q, item.label) || fuzzyMatch(q, item.sublabel ?? '')).slice(0, 12);
  });

  $effect(() => {
    selectedIdx = 0;
  });

  $effect(() => {
    if ($palette) {
      query = '';
      setTimeout(() => inputEl?.focus(), 10);
      loadResources();
    }
  });

  function navigate(href: string) {
    palette.close();
    goto(href);
  }

  function onKeydown(e: KeyboardEvent) {
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      selectedIdx = Math.min(selectedIdx + 1, results.length - 1);
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      selectedIdx = Math.max(selectedIdx - 1, 0);
    } else if (e.key === 'Enter') {
      e.preventDefault();
      const item = results[selectedIdx];
      if (item) navigate(item.href);
    } else if (e.key === 'Escape') {
      palette.close();
    }
  }
</script>

{#if $palette}
  <div
    use:dialogFocus={{ enabled: true, onEscape: () => palette.close(), initialFocus: '#command-palette-input' }}
    class="fixed inset-0 z-[var(--z-command)]"
    role="dialog"
    aria-modal="true"
    aria-label={t('palette.label')}
    tabindex="-1"
  >
    <button
      type="button"
      class="motion-fade material-scrim absolute inset-0 cursor-default bg-surface-scrim"
      onclick={() => palette.close()}
      aria-label={t('palette.close')}
    ></button>
    <div class="fixed left-1/2 top-[20vh] z-[calc(var(--z-command)+1)] w-full max-w-xl -translate-x-1/2 px-4">
      <div class="motion-pop palette-panel overflow-hidden rounded-xl border border-line-2 shadow-[var(--shadow-restraint)]">
        <div class="flex items-center gap-3 border-b border-line px-4 py-3">
          <svg class="size-4 shrink-0 text-ink-2" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-4.35-4.35M17 11A6 6 0 115 11a6 6 0 0112 0z"/>
          </svg>
          <input
            id="command-palette-input"
            bind:this={inputEl}
            bind:value={query}
            onkeydown={onKeydown}
            type="text"
            role="combobox"
            aria-label={t('palette.searchLabel')}
            aria-autocomplete="list"
            aria-controls={listboxId}
            aria-expanded="true"
            aria-activedescendant={results[selectedIdx] ? resultId(results[selectedIdx]) : undefined}
            placeholder={t('palette.searchPlaceholder')}
            autocomplete="off"
            class="flex-1 bg-transparent text-[14px] text-ink-0 placeholder-ink-3 outline-none"
          />
          <kbd class="rounded border border-line px-1.5 py-0.5 font-mono text-[10px] text-ink-2">ESC</kbd>
        </div>

        <p class="sr-only" aria-live="polite">{results.length > 0 ? t('palette.resultCount', { count: results.length }) : t('palette.noResultsLive')}</p>
        {#if results.length > 0}
          <ul id={listboxId} role="listbox" aria-label={t('palette.results')} class="max-h-80 overflow-y-auto py-1">
            {#each results as item, i}
              <li role="presentation">
                <button
                  id={resultId(item)}
                  role="option"
                  aria-selected={i === selectedIdx}
                  onclick={() => navigate(item.href)}
                  class="palette-item flex w-full items-center gap-3 px-4 py-2.5 text-left transition-colors"
                  class:palette-item-selected={i === selectedIdx}
                  onmouseenter={() => selectedIdx = i}
                >
                  <span class="palette-icon flex size-7 shrink-0 items-center justify-center rounded-md">
                    <svg class="size-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d={item.icon ?? ICONS.route}/>
                    </svg>
                  </span>
                  <span class="min-w-0 flex-1">
                    <span class="block truncate text-[13px] font-medium text-ink-0">{item.label}</span>
                    {#if item.sublabel}
                      <span class="block truncate text-xs text-ink-2">{item.sublabel}</span>
                    {/if}
                  </span>
                  <kbd class="text-[10px] text-ink-2 opacity-0 group-hover:opacity-100">↵</kbd>
                </button>
              </li>
            {/each}
          </ul>
        {:else}
          <div id={listboxId} role="listbox" aria-label={t('palette.results')} class="px-4 py-6 text-center text-sm text-ink-2">{t('palette.noResults')}</div>
        {/if}
      </div>
    </div>
  </div>
{/if}

<svelte:window
  onkeydown={(e) => {
    if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
      e.preventDefault();
      if ($palette) palette.close(); else palette.open();
    }
  }}
/>

<style>
  .palette-panel {
    background: var(--color-surface-raised);
  }
  .palette-item:hover,
  .palette-item-selected {
    background: var(--color-surface-selected);
  }
  .palette-icon {
    background: var(--color-surface-sunken);
    color: var(--color-ink-2);
  }
  .palette-item-selected .palette-icon {
    background: var(--color-surface-selected);
    color: var(--color-ink-0);
  }
</style>
