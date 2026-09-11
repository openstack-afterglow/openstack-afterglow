<script lang="ts">
  import type { ShareNetwork } from '$lib/types/securityService';

  let {
    open = $bindable(),
    shareNetworks,
    attaching,
    error,
    selectedNetworkId = $bindable(),
    onAttach,
  }: {
    open: boolean;
    shareNetworks: ShareNetwork[];
    attaching: boolean;
    error: string;
    selectedNetworkId: string;
    onAttach: () => Promise<boolean>;
  } = $props();

  async function handleAttach() {
    const ok = await onAttach();
    if (ok) open = false;
  }
</script>

{#if open}
  <div class="fixed inset-0 bg-surface-scrim/60 flex items-center justify-center z-50"
    onclick={() => { open = false; }}
    role="dialog" aria-modal="true" tabindex="-1"
    onkeydown={(e) => e.key === 'Escape' && (open = false)}>
    <div class="bg-surface-base border border-line-2 rounded-xl p-6 w-full max-w-md mx-4 shadow-[var(--shadow-restraint)]"
      onclick={(e) => e.stopPropagation()} role="none" onkeydown={(e) => e.stopPropagation()}>
      <h2 class="text-lg font-semibold text-ink-0 mb-5">Share Network에 연결</h2>
      <div>
        <label class="block text-xs text-ink-2 mb-1.5 uppercase tracking-wide">Share Network
          <select bind:value={selectedNetworkId}
            class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-0 text-sm focus:outline-none focus:border-action-warm mt-1.5">
            <option value="">Share Network 선택</option>
            {#each shareNetworks as net}
              <option value={net.id}>{net.name || net.id.slice(0, 12)}</option>
            {/each}
          </select>
        </label>
      </div>
      {#if error}
        <div class="mt-4 text-red-400 text-xs bg-red-900/20 border border-red-800 rounded px-3 py-2">{error}</div>
      {/if}
      <div class="flex justify-end gap-3 mt-6">
        <button onclick={() => { open = false; }}
          class="px-4 py-2 text-sm text-ink-2 hover:text-ink-0 transition-colors">취소</button>
        <button onclick={handleAttach} disabled={attaching || !selectedNetworkId}
          class="px-5 py-2 bg-action-warm hover:bg-action-warm-hover disabled:bg-surface-selected disabled:text-ink-3 text-action-on-warm text-sm font-medium rounded-lg transition-colors">
          {attaching ? '연결 중...' : '연결'}
        </button>
      </div>
    </div>
  </div>
{/if}
