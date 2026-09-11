<script lang="ts">
  import { api, ApiError } from '$lib/api/client';
  import type { ShareNeutronNetwork, ShareSubnet } from '$lib/types/shareNetwork';

  let {
    open = $bindable(),
    creating,
    token,
    projectId,
    onCreate,
  }: {
    open: boolean;
    creating: boolean;
    token: string | undefined;
    projectId: string | undefined;
    onCreate: (form: { name: string; description: string; neutron_net_id: string; neutron_subnet_id: string }) => Promise<boolean>;
  } = $props();

  let neutronNetworks = $state<ShareNeutronNetwork[]>([]);
  let subnets = $state<ShareSubnet[]>([]);
  let loadingSubnets = $state(false);
  let createError = $state('');
  let form = $state({ name: '', description: '', neutron_net_id: '', neutron_subnet_id: '' });

  $effect(() => {
    if (open) {
      form = { name: '', description: '', neutron_net_id: '', neutron_subnet_id: '' };
      subnets = [];
      createError = '';
      api.get<ShareNeutronNetwork[]>('/api/v1/networks', token, projectId).then(
        (data) => { neutronNetworks = data; },
        () => { neutronNetworks = []; }
      );
    }
  });

  async function onNetworkChange() {
    form.neutron_subnet_id = '';
    subnets = [];
    if (!form.neutron_net_id) return;
    loadingSubnets = true;
    try {
      const detail = await api.get<{ id: string; subnet_details: ShareSubnet[] }>(
        `/api/v1/networks/${form.neutron_net_id}`, token, projectId
      );
      subnets = detail.subnet_details ?? [];
    } catch {
      subnets = [];
    } finally {
      loadingSubnets = false;
    }
  }

  async function handleCreate() {
    if (!form.name.trim() || !form.neutron_net_id || !form.neutron_subnet_id) return;
    createError = '';
    try {
      const success = await onCreate(form);
      if (success) open = false;
    } catch (e) {
      createError = e instanceof ApiError ? e.message : '생성 실패';
    }
  }
</script>

{#if open}
  <div class="fixed inset-0 bg-surface-scrim/60 flex items-center justify-center z-50"
    onclick={() => { open = false; createError = ''; }}
    role="dialog" aria-modal="true" tabindex="-1"
    onkeydown={(e) => e.key === 'Escape' && (open = false)}>
    <div class="bg-surface-base border border-line-2 rounded-xl p-6 w-full max-w-lg mx-4 shadow-[var(--shadow-restraint)]"
      onclick={(e) => e.stopPropagation()} role="none" onkeydown={(e) => e.stopPropagation()}>
      <h2 class="text-lg font-semibold text-ink-0 mb-5">Share 네트워크 생성</h2>
      <div class="space-y-4">
        <div>
          <label class="block text-xs text-ink-2 mb-1.5 uppercase tracking-wide">이름 *
            <input bind:value={form.name} type="text" placeholder="my-share-network"
              class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-0 text-sm focus:outline-none focus:border-action-warm mt-1.5" />
          </label>
        </div>
        <div>
          <label class="block text-xs text-ink-2 mb-1.5 uppercase tracking-wide">설명 (선택)
            <input bind:value={form.description} type="text" placeholder="설명"
              class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-0 text-sm focus:outline-none focus:border-action-warm mt-1.5" />
          </label>
        </div>
        <div>
          <label class="block text-xs text-ink-2 mb-1.5 uppercase tracking-wide">Neutron 네트워크 *
            <select bind:value={form.neutron_net_id} onchange={onNetworkChange}
              class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-0 text-sm focus:outline-none focus:border-action-warm mt-1.5">
              <option value="">네트워크 선택</option>
              {#each neutronNetworks as net}
                <option value={net.id}>{net.name || net.id.slice(0, 12)} ({net.status})</option>
              {/each}
            </select>
          </label>
        </div>
        <div>
          <label class="block text-xs text-ink-2 mb-1.5 uppercase tracking-wide">서브넷 *
            {#if loadingSubnets}
              <div class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-3 text-sm mt-1.5">로딩 중...</div>
            {:else}
              <select bind:value={form.neutron_subnet_id}
                disabled={subnets.length === 0}
                class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-0 text-sm focus:outline-none focus:border-action-warm mt-1.5 disabled:text-ink-3">
                <option value="">{subnets.length === 0 ? '네트워크를 먼저 선택하세요' : '서브넷 선택'}</option>
                {#each subnets as subnet}
                  <option value={subnet.id}>{subnet.name || subnet.id.slice(0, 12)} {subnet.cidr ? `(${subnet.cidr})` : ''}</option>
                {/each}
              </select>
            {/if}
          </label>
        </div>
      </div>
      {#if createError}
        <div class="mt-4 text-red-400 text-xs bg-red-900/20 border border-red-800 rounded px-3 py-2">{createError}</div>
      {/if}
      <div class="flex justify-end gap-3 mt-6">
        <button onclick={() => { open = false; createError = ''; }}
          class="px-4 py-2 text-sm text-ink-2 hover:text-ink-0 transition-colors">취소</button>
        <button onclick={handleCreate} disabled={creating || !form.name.trim() || !form.neutron_net_id || !form.neutron_subnet_id}
          class="px-5 py-2 bg-action-warm hover:bg-action-warm-hover disabled:bg-surface-selected disabled:text-ink-3 text-action-on-warm text-sm font-medium rounded-lg transition-colors">
          {creating ? '생성 중...' : '생성'}
        </button>
      </div>
    </div>
  </div>
{/if}
