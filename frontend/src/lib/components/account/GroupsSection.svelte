<script lang="ts">
  import { t } from '$lib/i18n/ns/account';
  import { t as tc } from '$lib/i18n/ns/common';
  import { intlLocale } from '$lib/i18n/runtime.svelte';
  import { auth } from '$lib/stores/auth';
  import { api, ApiError } from '$lib/api/client';
  import LoadingState from '$lib/components/ui/LoadingState.svelte';
  import RegexSearch from '$lib/components/ui/RegexSearch.svelte';
  import TableViewControls from '$lib/components/ui/TableViewControls.svelte';
  import { createTableView } from '$lib/utils/tableView.svelte';
  import { onDestroy } from 'svelte';
  import { sessionScopeKey } from '$lib/utils/authSession';

  interface Group {
    id: string;
    name: string;
    description: string | null;
    domain_id: string | null;
  }

  const token = $derived($auth.token ?? undefined);

  let groups = $state<Group[]>([]);
  let loading = $state(true);
  let error = $state('');
  let noPermission = $state(false);
  const uid = $props.id();
  let search = $state('');
  const view = createTableView<Group>({
    locale: () => intlLocale(),
    rows: () => groups,
    search: () => search,
    columns: () => [
      { key: 'name', label: t('keypairs.name'), value: row => row.name },
      { key: 'id', label: 'ID', value: row => row.id },
      { key: 'description', label: t('profile.description'), value: row => row.description },
    ],
  });
  let viewOwner = '';
  const unsubscribeView = auth.subscribe(state => {
    const next = sessionScopeKey(state);
    if (viewOwner !== next) { viewOwner = next; search = ''; view.reset(); }
  });
  onDestroy(unsubscribeView);

  async function load() {
    loading = true;
    error = '';
    noPermission = false;
    try {
      groups = await api.get<Group[]>('/api/v1/auth/groups', token);
      if (groups.length === 0) noPermission = true;
    } catch (e) {
      error = e instanceof ApiError ? e.message : t('groups.loadFailed');
    } finally {
      loading = false;
    }
  }

  $effect(() => {
    if ($auth.token) load();
  });
</script>

<div class="motion-fade bg-surface-base border border-line rounded-xl p-5">
  <h3 class="text-sm font-semibold text-ink-0 mb-4">{t('groups.title')}</h3>
  <RegexSearch id={`${uid}-search`} bind:value={search} />
  <TableViewControls {view} class="" />

  {#if error}
    <div class="text-red-400 text-xs">{error}</div>
  {:else if loading}
    <LoadingState variant="section" label={tc('state.loading')}  />
  {:else if noPermission}
    <div class="text-ink-2 text-xs text-center py-4">{t('groups.empty')}</div>
  {:else if view.rows.length === 0}
    <p role="status" class="py-4 text-sm text-ink-2">{tc('table.noMatches')}</p>
  {:else}
    <div class="space-y-2">
      {#each view.rows as grp (grp.id)}
        <div class="flex items-center gap-3 px-3 py-2.5 bg-surface-sunken/50 rounded-lg">
          <div class="w-7 h-7 rounded-md bg-indigo-500/15 border border-indigo-500/30 text-indigo-400 flex items-center justify-center shrink-0">
            <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0z" />
            </svg>
          </div>
          <div class="flex-1 min-w-0">
            <div class="text-sm text-ink-0 font-medium truncate">{grp.name}</div>
            {#if grp.description}
              <div class="text-xs text-ink-2 truncate">{grp.description}</div>
            {/if}
          </div>
        </div>
      {/each}
    </div>
  {/if}
</div>
