<script lang="ts">
  import { untrack } from 'svelte';
  import { useK3sClusterDetailController } from '$lib/stores/k3sClusterDetailController.svelte';

  const s = useK3sClusterDetailController();

  // vmId → label 매핑
  const nodeOptions = $derived((() => {
    const c = s.cluster;
    if (!c) return [];
    const opts: { vmId: string; label: string }[] = [];
    if (c.server_vm_id) {
      opts.push({ vmId: c.server_vm_id, label: `server (${c.server_vm_id.slice(0, 8)})` });
    }
    c.agent_vm_ids.forEach((id, i) => {
      opts.push({ vmId: id, label: `agent-${i + 1} (${id.slice(0, 8)})` });
    });
    return opts;
  })());

  let selectedVmId = $state('');
  let selectedNetId = $state('');
  let showAttachForm = $state(false);
  let loadingIfaces = $state(false);
  let ifaceError = $state('');
  let attachError = $state('');

  // 첫 번째 노드 자동 선택
  $effect(() => {
    if (nodeOptions.length > 0 && !selectedVmId) {
      selectedVmId = nodeOptions[0].vmId;
    }
  });

  // 노드 선택 시 인터페이스 로드
  $effect(() => {
    const vmId = selectedVmId;
    if (!vmId) return;
    if (s.interfaces[vmId]) return; // 이미 로드됨
    loadingIfaces = true;
    ifaceError = '';
    untrack(() => s.loadInterfaces([vmId]))
      .catch(() => { ifaceError = '인터페이스 로드 실패'; })
      .finally(() => { loadingIfaces = false; });
  });

  // 네트워크 목록 로드 (폼 열릴 때)
  $effect(() => {
    if (showAttachForm) {
      untrack(() => s.loadNetworks());
    }
  });

  const currentIfaces = $derived(selectedVmId ? (s.interfaces[selectedVmId] ?? null) : null);
  const availableNetworks = $derived(s.networks.filter((net) => !(currentIfaces ?? []).some((iface) => iface.net_id === net.id)));

  async function handleAttach() {
    if (!selectedVmId || !selectedNetId) return;
    attachError = '';
    try {
      await s.attachInterface(selectedVmId, selectedNetId);
      showAttachForm = false;
      selectedNetId = '';
    } catch (e) {
      attachError = e instanceof Error ? e.message : '연결 실패';
    }
  }

  async function handleDetach(vmId: string, portId: string) {
    attachError = '';
    try {
      await s.detachInterface(vmId, portId);
    } catch (e) {
      attachError = e instanceof Error ? e.message : '해제 실패';
    }
  }
</script>

<div class="bg-surface-base border border-line rounded-xl p-4 mt-3">
  <div class="flex items-center justify-between mb-3">
    <h3 class="text-xs text-ink-3 uppercase tracking-wide">노드 네트워크</h3>
    {#if s.isActive}
      <button
        onclick={() => { showAttachForm = !showAttachForm; selectedNetId = ''; attachError = ''; }}
        class="text-xs text-action-warm hover:text-action-warm-hover transition-colors"
      >
        {showAttachForm ? '닫기' : '+ 네트워크 연결'}
      </button>
    {/if}
  </div>

  {#if nodeOptions.length === 0}
    <p class="text-sm text-ink-3">노드 정보 없음</p>
  {:else}
    <!-- 노드 선택 -->
    <div class="mb-3">
      <select
        bind:value={selectedVmId}
        class="w-full bg-surface-sunken border border-line-2 text-ink-1 text-xs rounded px-2 py-1.5 focus:outline-none focus:border-action-warm"
      >
        {#each nodeOptions as opt}
          <option value={opt.vmId}>{opt.label}</option>
        {/each}
      </select>
    </div>

    <!-- 인터페이스 목록 -->
    {#if loadingIfaces}
      <div class="text-xs text-ink-3 py-2">로드 중...</div>
    {:else if ifaceError}
      <div class="text-xs text-red-400 py-2">{ifaceError}</div>
    {:else if currentIfaces === null}
      <div class="text-xs text-ink-3 py-2">로드 중...</div>
    {:else if currentIfaces.length === 0}
      <div class="text-xs text-ink-3 py-2">인터페이스 없음</div>
    {:else}
      <div class="space-y-2">
        {#each currentIfaces as iface}
          {@const detachingKey = `${selectedVmId}:${iface.port_id}`}
          <div class="bg-surface-sunken/50 rounded-lg p-3 flex items-start justify-between gap-3">
            <div class="min-w-0">
              <div class="flex items-center gap-2 mb-1">
                <span class="text-xs px-1.5 py-0.5 rounded {iface.node_role === 'server' ? 'bg-purple-900/40 text-purple-400 border border-purple-800' : 'bg-surface-selected/40 text-action-warm border border-action-warm'}">
                  {iface.node_role}
                </span>
                {#if iface.is_primary}
                  <span class="text-xs text-ink-3">기본 인터페이스</span>
                {/if}
              </div>
              <div class="text-xs text-ink-3 mb-0.5">포트</div>
              <div class="text-xs text-ink-2 font-mono truncate">{iface.port_id}</div>
              <div class="text-xs text-ink-3 mt-1 mb-0.5">네트워크</div>
              <div class="text-xs text-ink-2 font-mono truncate">{iface.net_id}</div>
              {#if iface.fixed_ips.length > 0}
                <div class="text-xs text-ink-3 mt-1 mb-0.5">IP</div>
                <div class="flex flex-wrap gap-1">
                  {#each iface.fixed_ips as fip}
                    <span class="text-xs font-mono text-ink-2 bg-surface-selected px-1.5 py-0.5 rounded">{fip.ip_address}</span>
                  {/each}
                </div>
              {/if}
            </div>
            <button
              onclick={() => handleDetach(selectedVmId, iface.port_id)}
              disabled={iface.is_primary || s.interfaceActioning === detachingKey}
              title={iface.is_primary ? '기본 인터페이스는 제거할 수 없습니다' : '인터페이스 제거'}
              class="shrink-0 text-xs text-orange-400 hover:text-orange-300 px-2 py-1 border border-orange-900 hover:border-orange-700 rounded transition-colors disabled:text-ink-3 disabled:border-line-2 disabled:cursor-not-allowed"
            >
              {s.interfaceActioning === detachingKey ? '제거 중...' : '제거'}
            </button>
          </div>
        {/each}
      </div>
    {/if}

    {#if attachError}
      <p class="text-xs text-red-400 mt-2">{attachError}</p>
    {/if}

    {#if showAttachForm && s.isActive}
      <div class="mt-3 bg-surface-sunken rounded-lg p-3">
        <p class="text-xs text-ink-2 mb-2">연결할 네트워크 선택</p>
        <div class="flex gap-2">
          <select
            bind:value={selectedNetId}
            class="flex-1 bg-surface-selected border border-line-2 text-ink-1 text-xs rounded px-2 py-1.5 focus:outline-none focus:border-action-warm"
          >
            <option value="">네트워크 선택...</option>
            {#each availableNetworks as net}
              <option value={net.id}>{net.name || net.id.slice(0, 12)}</option>
            {/each}
          </select>
          <button
            onclick={handleAttach}
            disabled={!selectedNetId || !!s.interfaceActioning}
            class="text-xs text-action-warm hover:text-action-warm-hover px-3 py-1.5 border border-action-warm hover:border-action-warm rounded transition-colors disabled:text-ink-3 disabled:border-line-2"
          >
            {s.interfaceActioning === selectedVmId ? '추가 중...' : '추가'}
          </button>
        </div>
      </div>
    {/if}
  {/if}
</div>
