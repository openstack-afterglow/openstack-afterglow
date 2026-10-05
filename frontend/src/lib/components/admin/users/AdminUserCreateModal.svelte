<script lang="ts">
    import { dialogFocus } from '$lib/utils/dialogFocus';
  import { t } from '$lib/i18n/ns/admin-identity';

  let {
    open = $bindable(),
    onCreate,
  }: {
    open: boolean;
    onCreate: (form: { name: string; email: string; password: string; enabled: boolean }) => Promise<string | true>;
  } = $props();

  let form = $state({ name: '', email: '', password: '', enabled: true });
  let creating = $state(false);
  let error = $state('');

  $effect(() => {
    if (!open) {
      form = { name: '', email: '', password: '', enabled: true };
      error = '';
      creating = false;
    }
  });

  async function submit() {
    creating = true;
    error = '';
    const result = await onCreate({ ...form });
    creating = false;
    if (result === true) {
      open = false;
    } else {
      error = result;
    }
  }
</script>

{#if open}
  <!-- svelte-ignore a11y_click_events_have_key_events -->
  <!-- svelte-ignore a11y_no_static_element_interactions -->
  <div
    use:dialogFocus={{ enabled: true, onEscape: () => (open = false) }}
    class="fixed inset-0 bg-surface-scrim/60 flex items-center justify-center z-50"
    onclick={(event) => { if (event.target === event.currentTarget) (() => { open = false; })(); }}
    role="dialog" aria-modal="true"
    tabindex="-1"
  >
    <div class="bg-surface-base border border-line-2 rounded-xl p-6 w-full max-w-md mx-4 shadow-[var(--shadow-restraint)]">
      <h2 class="text-lg font-semibold text-ink-0 mb-5">{t('userCreate.title')}</h2>
      {#if error}<div class="bg-red-900/40 border border-red-700 text-red-300 rounded-lg px-4 py-3 text-sm mb-4">{error}</div>{/if}
      <div class="space-y-4">
        <div><label class="block text-xs text-ink-2 mb-1.5 uppercase tracking-wide" for="field-adminusercreatemodal-47">{t('userCreate.name')}</label><input id="field-adminusercreatemodal-47" bind:value={form.name} type="text" class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-0 text-sm focus:outline-none focus:border-action-warm" /></div>
        <div><label class="block text-xs text-ink-2 mb-1.5 uppercase tracking-wide" for="field-adminusercreatemodal-48">{t('userCreate.email')}</label><input id="field-adminusercreatemodal-48" bind:value={form.email} type="email" class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-0 text-sm focus:outline-none focus:border-action-warm" /></div>
        <div><label class="block text-xs text-ink-2 mb-1.5 uppercase tracking-wide" for="field-adminusercreatemodal-49">{t('userCreate.password')}</label><input id="field-adminusercreatemodal-49" bind:value={form.password} type="password" class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-0 text-sm focus:outline-none focus:border-action-warm" /></div>
        <div class="flex items-center gap-3">
          <button type="button" role="switch" aria-label={t('userCreate.enabledLabel')} aria-checked={form.enabled} onclick={() => form.enabled = !form.enabled} class="relative w-11 h-6 rounded-full transition-colors {form.enabled ? 'bg-action-warm' : 'bg-surface-selected'}">
            <span class="absolute top-0.5 left-0.5 w-5 h-5 bg-surface-base rounded-full transition-transform {form.enabled ? 'translate-x-5' : ''}"></span>
          </button>
          <span class="text-sm text-ink-2">{form.enabled ? t('userCreate.enabled') : t('userCreate.disabled')}</span>
        </div>
      </div>
      <div class="flex justify-end gap-3 mt-6">
        <button onclick={() => { open = false; }} class="px-4 py-2 bg-surface-selected hover:bg-surface-selected text-ink-0 text-sm font-medium rounded-lg">{t('userCreate.cancel')}</button>
        <button onclick={submit} disabled={creating || !form.name} class="px-4 py-2 bg-action-warm hover:bg-action-warm-hover text-ink-0 text-sm font-medium rounded-lg disabled:opacity-30">{creating ? t('userCreate.creating') : t('userCreate.create')}</button>
      </div>
    </div>
  </div>
{/if}
