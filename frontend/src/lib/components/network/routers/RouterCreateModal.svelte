<script lang="ts">
  import type { Network } from '$lib/types/networks';

  let {
    open = $bindable(),
    externalNetworks,
    onCreate,
  }: {
    open: boolean;
    externalNetworks: Network[];
    onCreate: (form: { name: string; external_network_id: string }) => Promise<string | true>;
  } = $props();

  let form = $state({ name: '', external_network_id: '' });
  let creating = $state(false);
  let error = $state('');

  $effect(() => {
    if (!open) {
      form = { name: '', external_network_id: '' };
      error = '';
      creating = false;
    }
  });

  async function submit() {
    if (!form.name.trim()) return;
    creating = true;
    error = '';
    const result = await onCreate({ ...form });
    creating = false;
    if (result === true) open = false;
    else error = result;
  }
</script>

{#if open}
  <div class="fixed inset-0 bg-surface-scrim/60 flex items-center justify-center z-50" onclick={() => { open = false; }} role="dialog" aria-modal="true" tabindex="-1" onkeydown={(e) => e.key === 'Escape' && (open = false)}>
    <div class="bg-surface-base border border-line-2 rounded-xl p-6 w-full max-w-md mx-4 shadow-[var(--shadow-restraint)]" onclick={(e) => e.stopPropagation()} role="none" onkeydown={(e) => e.stopPropagation()}>
      <h2 class="text-lg font-semibold text-ink-0 mb-5">라우터 생성</h2>
      <div class="space-y-4">
        <div>
          <label class="block text-xs text-ink-2 mb-1.5 uppercase tracking-wide">이름
            <input bind:value={form.name} type="text" placeholder="my-router" class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-0 text-sm focus:outline-none focus:border-action-warm mt-1.5" />
          </label>
        </div>
        <div>
          <label class="block text-xs text-ink-2 mb-1.5 uppercase tracking-wide">외부 네트워크 (선택)
            <select bind:value={form.external_network_id} class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-0 text-sm focus:outline-none focus:border-action-warm mt-1.5">
              <option value="">외부 게이트웨이 없음</option>
              {#each externalNetworks as net}
                <option value={net.id}>{net.name || net.id.slice(0, 12)}</option>
              {/each}
            </select>
          </label>
        </div>
      </div>
      {#if error}<div class="mt-4 text-red-400 text-xs bg-red-900/20 border border-red-800 rounded px-3 py-2">{error}</div>{/if}
      <div class="flex justify-end gap-3 mt-6">
        <button onclick={() => { open = false; }} class="px-4 py-2 text-sm text-ink-2 hover:text-ink-0 transition-colors">취소</button>
        <button onclick={submit} disabled={creating} class="px-5 py-2 bg-action-warm hover:bg-action-warm-hover disabled:bg-surface-selected disabled:text-ink-3 text-ink-0 text-sm font-medium rounded-lg transition-colors">{creating ? '생성 중...' : '생성'}</button>
      </div>
    </div>
  </div>
{/if}
