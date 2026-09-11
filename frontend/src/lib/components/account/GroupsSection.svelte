<script lang="ts">
  import { auth } from '$lib/stores/auth';
  import { api, ApiError } from '$lib/api/client';

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

  async function load() {
    loading = true;
    error = '';
    noPermission = false;
    try {
      groups = await api.get<Group[]>('/api/v1/auth/groups', token);
      if (groups.length === 0) noPermission = true;
    } catch (e) {
      error = e instanceof ApiError ? e.message : '조회 실패';
    } finally {
      loading = false;
    }
  }

  $effect(() => {
    if ($auth.token) load();
  });
</script>

<div class="bg-surface-base border border-line rounded-xl p-5">
  <h3 class="text-sm font-semibold text-ink-0 mb-4">소속 그룹</h3>

  {#if error}
    <div class="text-red-400 text-xs">{error}</div>
  {:else if loading}
    <div class="space-y-2">
      {#each [1, 2] as _}
        <div class="h-8 bg-surface-sunken rounded animate-pulse"></div>
      {/each}
    </div>
  {:else if noPermission}
    <div class="text-ink-3 text-xs text-center py-4">그룹 조회 권한이 없거나 소속 그룹이 없습니다</div>
  {:else}
    <div class="space-y-2">
      {#each groups as grp (grp.id)}
        <div class="flex items-center gap-3 px-3 py-2.5 bg-surface-sunken/50 rounded-lg">
          <div class="w-7 h-7 rounded-md bg-indigo-500/15 border border-indigo-500/30 text-indigo-400 flex items-center justify-center shrink-0">
            <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0z" />
            </svg>
          </div>
          <div class="flex-1 min-w-0">
            <div class="text-sm text-ink-0 font-medium truncate">{grp.name}</div>
            {#if grp.description}
              <div class="text-[11px] text-ink-3 truncate">{grp.description}</div>
            {/if}
          </div>
        </div>
      {/each}
    </div>
  {/if}
</div>
