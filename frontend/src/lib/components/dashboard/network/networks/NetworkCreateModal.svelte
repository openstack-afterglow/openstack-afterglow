<script lang="ts">
  import { t } from '$lib/i18n/ns/network-pages';
  import { dialogFocus } from '$lib/utils/dialogFocus';
  import ActivityIndicator from '$lib/components/ui/ActivityIndicator.svelte';

  let {
    open = $bindable(),
    creating,
    error,
    onCreate,
  }: {
    open: boolean;
    creating: boolean;
    error: string;
    onCreate: (body: Record<string, unknown>) => Promise<boolean>;
  } = $props();

  let form = $state({
    name: '',
    addSubnet: false,
    subnetName: '',
    cidr: '10.0.0.0/24',
    gateway: '',
    dhcp: true,
  });

  function close() {
    open = false;
  }

  async function handleCreate() {
    if (!form.name.trim()) return;
    const body: Record<string, unknown> = { name: form.name };
    if (form.addSubnet) {
      body.subnet = {
        name: form.subnetName || `${form.name}-subnet`,
        cidr: form.cidr,
        gateway_ip: form.gateway || null,
        enable_dhcp: form.dhcp,
      };
    }
    const ok = await onCreate(body);
    if (ok) {
      form = { name: '', addSubnet: false, subnetName: '', cidr: '10.0.0.0/24', gateway: '', dhcp: true };
      open = false;
    }
  }
</script>

{#if open}
  <!-- svelte-ignore a11y_click_events_have_key_events -->
  <!-- svelte-ignore a11y_no_static_element_interactions -->
  <div
    use:dialogFocus={{ enabled: true, onEscape: () => close() }}
    class="motion-fade fixed inset-0 bg-surface-scrim/60 flex items-center justify-center z-50"
    onclick={close}
    role="dialog"
    aria-modal="true"
    tabindex="-1"
  >
    <div
      class="motion-pop bg-surface-base border border-line-2 rounded-xl p-6 w-full max-w-md mx-4 shadow-[var(--shadow-restraint)]"
      onclick={(e) => e.stopPropagation()}
      role="none"
    >
      <h2 class="text-lg font-semibold text-ink-0 mb-5">{t('networkCreate.title')}</h2>
      <div class="space-y-4">
        <div>
          <label class="block text-xs text-ink-2 mb-1.5 uppercase tracking-wide">{t('networkCreate.name')}
            <input bind:value={form.name} type="text" placeholder={t('networkCreate.namePlaceholder')} class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-0 text-sm focus:outline-none focus:border-action-warm mt-1.5" />
          </label>
        </div>
        <div class="flex items-center gap-2">
          <input type="checkbox" id="addSubnet" bind:checked={form.addSubnet} class="rounded border-line-2" />
          <label for="addSubnet" class="text-sm text-ink-2">{t('networkCreate.addSubnet')}</label>
        </div>
        {#if form.addSubnet}
          <div>
            <label class="block text-xs text-ink-2 mb-1.5 uppercase tracking-wide">{t('networkCreate.subnetName')}
              <input bind:value={form.subnetName} type="text" placeholder={t('networkCreate.subnetNamePlaceholder')} class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-0 text-sm focus:outline-none focus:border-action-warm mt-1.5" />
            </label>
          </div>
          <div>
            <label class="block text-xs text-ink-2 mb-1.5 uppercase tracking-wide">CIDR
              <input bind:value={form.cidr} type="text" placeholder="10.0.0.0/24" class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-0 text-sm font-mono focus:outline-none focus:border-action-warm mt-1.5" />
            </label>
          </div>
          <div>
            <label class="block text-xs text-ink-2 mb-1.5 uppercase tracking-wide">{t('networkCreate.gateway')}
              <input bind:value={form.gateway} type="text" placeholder="10.0.0.1" class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-0 text-sm font-mono focus:outline-none focus:border-action-warm mt-1.5" />
            </label>
          </div>
          <div class="flex items-center gap-2">
            <input type="checkbox" id="dhcp" bind:checked={form.dhcp} class="rounded border-line-2" />
            <label for="dhcp" class="text-sm text-ink-2">{t('networkCreate.dhcp')}</label>
          </div>
        {/if}
      </div>
      {#if error}<div class="mt-4 text-red-400 text-xs bg-red-900/20 border border-red-800 rounded px-3 py-2">{error}</div>{/if}
      <div class="flex justify-end gap-3 mt-6">
        <button onclick={close} class="px-4 py-2 text-sm text-ink-2 hover:text-ink-0 transition-colors">{t('networkCreate.cancel')}</button>
        <button onclick={handleCreate} disabled={creating} aria-busy={creating} class="inline-flex items-center gap-1.5 px-5 py-2 bg-action-warm hover:bg-action-warm-hover disabled:bg-surface-selected disabled:text-ink-3 text-ink-0 text-sm font-medium rounded-lg transition-colors">{#if creating}<ActivityIndicator size="xs" tone="ink" />{/if}{creating ? t('networkCreate.creating') : t('networkCreate.create')}</button>
      </div>
    </div>
  </div>
{/if}
