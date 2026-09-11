<script lang="ts">
  import StatusChip from '$lib/components/ui/StatusChip.svelte';
  import ActionMenu from '$lib/components/ui/ActionMenu.svelte';
  import SelectionCheckbox from '$lib/components/ui/SelectionCheckbox.svelte';
  import SelectionToolbar from '$lib/components/ui/SelectionToolbar.svelte';
  import type { Network } from '$lib/types/networks';

  let {
    networks,
    defaultNetworkId,
    deleting,
    settingDefault,
    selectedIds,
    selectableIds,
    selectionDisabled,
    onToggleSelect,
    onToggleAll,
    onOpenPanel,
    onSetDefault,
    onDelete,
  }: {
    networks: Network[];
    defaultNetworkId: string | null;
    deleting: string | null;
    settingDefault: string | null;
    selectedIds: ReadonlySet<string>;
    selectableIds: ReadonlySet<string>;
    selectionDisabled: boolean;
    onToggleSelect: (id: string) => void;
    onToggleAll: () => void;
    onOpenPanel: (id: string) => void;
    onSetDefault: (id: string) => void;
    onDelete: (id: string, name: string, isExternal: boolean) => void;
  } = $props();

  let openNetMenu = $state<string | null>(null);
  const selectedCount = $derived([...selectableIds].filter((id) => selectedIds.has(id)).length);
  const allSelected = $derived(selectableIds.size > 0 && selectedCount === selectableIds.size);
  const indeterminate = $derived(selectedCount > 0 && !allSelected);

  $effect(() => {
    const close = () => { openNetMenu = null; };
    document.addEventListener('click', close);
    return () => document.removeEventListener('click', close);
  });
</script>


<div class="bg-surface-base border border-line rounded-lg p-5">
  <div class="text-ink-0 text-[15px] font-semibold mb-3.5">네트워크</div>
  <div class="bg-[#0B1220] border border-line rounded-lg overflow-hidden">
    <!-- Header -->
    <div class="grid grid-cols-[1fr_0px_auto_0px_0px_0px_0px] sm:grid-cols-[1.4fr_1fr_100px_80px_80px_100px_56px] px-4 py-2.5 border-b border-line text-[11px] uppercase tracking-wider text-ink-3 font-medium">
      <div class="flex items-center">
        <SelectionToolbar
          label="네트워크"
          ariaLabel="네트워크 전체 선택"
          checked={allSelected}
          indeterminate={indeterminate}
          selectedCount={selectedCount}
          disabled={selectionDisabled || selectableIds.size === 0}
          onToggle={onToggleAll}
        />
      </div>
      <div class="hidden sm:block">CIDR</div>
      <div>유형</div>
      <div class="hidden sm:block">서브넷</div>
      <div class="hidden sm:block">MTU</div>
      <div class="hidden sm:block">상태</div>
      <div class="hidden sm:block"></div>
    </div>
    <!-- Rows -->
    {#each networks as net (net.id)}
      <div
        class="resource-selection-surface grid grid-cols-[1fr_0px_auto_0px_0px_0px_0px] sm:grid-cols-[1.4fr_1fr_100px_80px_80px_100px_56px] px-4 py-3 text-[13px] items-center border-b border-line transition-colors last:border-b-0"
        data-selected={selectedIds.has(net.id)}
      >
        <!-- 이름 -->
        <div class="flex items-center gap-2.5 min-w-0">
          <SelectionCheckbox
            checked={selectedIds.has(net.id)}
            disabled={selectionDisabled || !selectableIds.has(net.id)}
            unavailable={!selectableIds.has(net.id)}
            title={!selectableIds.has(net.id) ? '외부 네트워크는 선택할 수 없습니다' : undefined}
            ariaLabel={`${net.name || net.id.slice(0, 12)} 선택`}
            onclick={() => onToggleSelect(net.id)}
          />
          <button
            type="button"
            onclick={() => onOpenPanel(net.id)}
            class="flex items-center gap-2.5 min-w-0 w-full text-left text-ink-0 hover:text-action-warm-hover transition-colors cursor-pointer"
          >
            <div class="shrink-0 w-7 h-7 rounded-md bg-violet-500/15 border border-violet-500/30 flex items-center justify-center">
              <svg class="w-3.5 h-3.5 text-violet-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3.055 11H5a2 2 0 012 2v1a2 2 0 002 2 2 2 0 012 2v2.945M8 3.935V5.5A2.5 2.5 0 0010.5 8h.5a2 2 0 012 2 2 2 0 104 0 2 2 0 012-2h1.064M15 20.488V18a2 2 0 012-2h3.064M21 12a9 9 0 11-18 0z" />
              </svg>
            </div>
            <div class="min-w-0 flex-1">
              <div class="flex items-center gap-1.5">
                <span class="font-medium truncate">{net.name || net.id.slice(0, 12)}</span>
                {#if net.id === defaultNetworkId}
                  <span class="text-[10px] px-1.5 py-0.5 rounded bg-surface-selected/40 border border-action-warm/60 text-action-warm shrink-0">기본</span>
                {/if}
              </div>
              <div class="text-[11px] text-ink-3 font-mono truncate">{net.id.slice(0, 8)}…</div>
            </div>
          </button>
        </div>
        <!-- CIDR -->
        <div
          class="hidden sm:block text-ink-2 font-mono text-[12px] truncate"
          title={net.cidrs && net.cidrs.length > 0 ? net.cidrs.join(', ') : undefined}
        >
          {net.cidrs && net.cidrs.length > 0 ? net.cidrs.join(', ') : '—'}
        </div>
        <!-- 유형 badge -->
        <div>
          {#if net.is_external}
            <span class="text-[11px] px-2 py-0.5 rounded-md bg-surface-selected/25 border border-action-warm text-action-warm">외부</span>
          {:else if net.is_shared}
            <span class="text-[11px] px-2 py-0.5 rounded-md bg-teal-500/15 border border-teal-500/30 text-teal-400">공유</span>
          {:else}
            <span class="text-[11px] px-2 py-0.5 rounded-md bg-surface-sunken border border-line-2 text-ink-2">내부</span>
          {/if}
        </div>
        <!-- 서브넷 -->
        <div class="hidden sm:block text-ink-2 text-[12px]">{net.subnets.length}개</div>
        <!-- MTU -->
        <div class="hidden sm:block text-ink-3 font-mono text-[12px]">—</div>
        <!-- 상태 -->
        <div class="hidden sm:block"><StatusChip status={net.status} /></div>
        <!-- 액션 -->
        <div class="hidden sm:flex items-center justify-end" role="none">
          {#if !net.is_external}
            <ActionMenu
              open={openNetMenu === net.id}
              ariaLabel={`${net.name || net.id} 네트워크 작업`}
              onopen={() => { openNetMenu = net.id; }}
              onclose={() => { openNetMenu = null; }}
            >
              {#if net.id !== defaultNetworkId}
                <button
                  onclick={() => { openNetMenu = null; onSetDefault(net.id); }}
                  disabled={settingDefault === net.id}
                  class="w-full text-left px-3 py-1.5 text-xs text-action-warm hover:bg-surface-sunken hover:text-action-warm-hover disabled:text-ink-3"
                >{settingDefault === net.id ? '설정 중...' : '기본 네트워크로 설정'}</button>
              {/if}
              <div class="border-t border-line my-1"></div>
              <button
                onclick={() => { openNetMenu = null; onDelete(net.id, net.name, net.is_external); }}
                disabled={deleting === net.id}
                class="w-full text-left px-3 py-1.5 text-xs text-red-400 hover:bg-surface-sunken hover:text-red-300 disabled:text-ink-3"
              >{deleting === net.id ? '삭제 중...' : '삭제'}</button>
            </ActionMenu>
          {/if}
        </div>
      </div>
    {/each}
  </div>
</div>
