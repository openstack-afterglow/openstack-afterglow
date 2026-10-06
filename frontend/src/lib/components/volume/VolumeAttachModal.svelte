<script lang="ts">
  import { useVolumeDetailController } from '$lib/stores/volumeDetailController.svelte';
  import Button from '$lib/components/ui/Button.svelte';
  import ActivityIndicator from '$lib/components/ui/ActivityIndicator.svelte';
  import { dialogFocus } from '$lib/utils/dialogFocus';
  import { t } from '$lib/i18n/ns/volume';

  const s = useVolumeDetailController();
</script>

<!-- svelte-ignore a11y_click_events_have_key_events -->
<!-- svelte-ignore a11y_no_static_element_interactions -->
<div
  use:dialogFocus={{ enabled: true, onEscape: () => s.closeAttachModal() }}
  class="fixed inset-0 bg-surface-scrim/60 flex items-center justify-center z-[60]"
  onclick={() => s.closeAttachModal()}
  role="dialog"
  aria-modal="true"
  tabindex="-1"
>
  <div
    class="bg-surface-base border border-line-2 rounded-xl p-6 w-full max-w-sm mx-4 shadow-[var(--shadow-restraint)]"
    onclick={(e) => e.stopPropagation()}
    role="none"
  >
    <h3 class="text-base font-semibold text-ink-0 mb-4">{t('attachModal.title')}</h3>
    <label class="block text-xs text-ink-2 mb-1.5 uppercase tracking-wide">{t('attachModal.instanceLabel')}
      <select
        bind:value={s.attachInstanceId}
        class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-0 text-sm focus:outline-none focus:border-action-warm mt-1.5"
      >
        <option value="">{t('attachModal.instancePlaceholder')}</option>
        {#each s.instances as inst}
          <option value={inst.id}>{t('attachModal.instanceSummary', { name: inst.name || inst.id.slice(0, 8), status: inst.status })}</option>
        {/each}
      </select>
    </label>
    {#if s.attachError}<p class="text-xs text-red-400 mt-2">{s.attachError}</p>{/if}
    <div class="flex justify-end gap-3 mt-5">
      <button onclick={() => s.closeAttachModal()} class="text-sm text-ink-2 hover:text-ink-0 transition-colors">{t('attachModal.cancel')}</button>
      <Button onclick={() => s.attachVolume()} disabled={s.attaching || !s.attachInstanceId}>
        {#if s.attaching}<ActivityIndicator size="xs" tone="ink" />{/if}{s.attaching ? t('attachModal.attaching') : t('attachModal.attach')}
      </Button>
    </div>
  </div>
</div>
