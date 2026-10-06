<script lang="ts">
  import { t } from '$lib/i18n/ns/file-storage';
  import type { ShareNetwork } from '$lib/types/securityService';
  import { dialogFocus } from '$lib/utils/dialogFocus';
  import ActivityIndicator from '$lib/components/ui/ActivityIndicator.svelte';

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
  <!-- svelte-ignore a11y_click_events_have_key_events -->
  <!-- svelte-ignore a11y_no_static_element_interactions -->
  <div
		use:dialogFocus={{ enabled: true, onEscape: () => (open = false) }} class="fixed inset-0 bg-surface-scrim/60 flex items-center justify-center z-50"
    onclick={() => { open = false; }}
    role="dialog" aria-modal="true" tabindex="-1"
>
    <div class="bg-surface-base border border-line-2 rounded-xl p-6 w-full max-w-md mx-4 shadow-[var(--shadow-restraint)]"
      onclick={(e) => e.stopPropagation()} role="none">
      <h2 class="text-lg font-semibold text-ink-0 mb-5">{t('securityAttach.title')}</h2>
      <div>
        <label class="block text-xs text-ink-2 mb-1.5 uppercase tracking-wide">{t('securityAttach.networkLabel')}
          <select bind:value={selectedNetworkId}
            class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-0 text-sm focus:outline-none focus:border-action-warm mt-1.5">
            <option value="">{t('securityAttach.selectNetwork')}</option>
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
          class="px-4 py-2 text-sm text-ink-2 hover:text-ink-0 transition-colors">{t('securityAttach.cancel')}</button>
        <button onclick={handleAttach} disabled={attaching || !selectedNetworkId}
          class="inline-flex items-center gap-1.5 px-5 py-2 bg-action-warm hover:bg-action-warm-hover disabled:bg-surface-selected disabled:text-ink-3 text-action-on-warm text-sm font-medium rounded-lg transition-colors">
          {#if attaching}<ActivityIndicator size="xs" tone="ink" />{/if}{attaching ? t('securityAttach.attaching') : t('securityAttach.attach')}
        </button>
      </div>
    </div>
  </div>
{/if}
