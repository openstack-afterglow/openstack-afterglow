<script lang="ts">
  import ActivityIndicator from '$lib/components/ui/ActivityIndicator.svelte';
  import type { PortInfo } from '$lib/types/networks';
  import { dialogFocus } from '$lib/utils/dialogFocus';
  import { t } from '$lib/i18n/ns/admin-network';
  import RichText from '$lib/i18n/RichText.svelte';

  let {
    port = $bindable<PortInfo | null>(),
    onConfirm,
  }: {
    port: PortInfo | null;
    onConfirm: (id: string) => Promise<string | true>;
  } = $props();

  let deleting = $state(false);
  let error = $state('');

  $effect(() => {
    if (port) {
      error = '';
      deleting = false;
    }
  });

  async function submit() {
    if (!port) return;
    deleting = true;
    error = '';
    const result = await onConfirm(port.id);
    deleting = false;
    if (result === true) {
      port = null;
    } else {
      error = result;
    }
  }
</script>

{#snippet portText(text: string)}<span class="text-ink-0 font-mono">{text}</span>{/snippet}

{#if port}
  <!-- svelte-ignore a11y_click_events_have_key_events -->
  <!-- svelte-ignore a11y_no_static_element_interactions -->
  <div
    use:dialogFocus={{ enabled: true, onEscape: () => (port = null) }}
    class="fixed inset-0 bg-surface-scrim/60 flex items-center justify-center z-50"
    onclick={(event) => { if (event.target === event.currentTarget) (() => { port = null; })(); }}
    role="dialog" aria-modal="true"
    tabindex="-1"
  >
    <div class="bg-surface-base border border-line-2 rounded-xl p-6 w-full max-w-sm mx-4 shadow-[var(--shadow-restraint)]">
      <h2 class="text-lg font-semibold text-ink-0 mb-3">{t('portDeleteModal.title')}</h2>
      <p class="text-sm text-ink-2 mb-4"><RichText segments={t.rich('portDeleteModal.body', { id: port.id.slice(0, 8) })} tags={{ port: portText }} /></p>
      {#if error}<div class="bg-red-900/40 border border-red-700 text-red-300 rounded-lg px-4 py-3 text-sm mb-4">{error}</div>{/if}
      <div class="flex justify-end gap-3">
        <button onclick={() => { port = null; }} class="px-4 py-2 bg-surface-selected hover:bg-surface-selected text-ink-0 text-sm font-medium rounded-lg">{t('portDeleteModal.cancel')}</button>
        <button aria-busy={deleting} onclick={submit} disabled={deleting} class="px-4 py-2 bg-[var(--color-state-danger)]/10 hover:bg-[var(--color-state-danger)]/20 text-[var(--color-state-danger-text)] text-sm font-medium rounded-lg disabled:opacity-30">{#if deleting}<span class="inline-flex items-center gap-2" role="status"><ActivityIndicator size="xs" />{t('portDeleteModal.deleting')}</span>{:else}{t('portDeleteModal.delete')}{/if}</button>
      </div>
    </div>
  </div>
{/if}
