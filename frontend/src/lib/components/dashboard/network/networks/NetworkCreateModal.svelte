<script lang="ts">
	import LoadingState from '$lib/components/ui/LoadingState.svelte';
  import { t } from '$lib/i18n/ns/network-pages';
  import { dialogFocus } from '$lib/utils/dialogFocus';
  import { Alert, Button, Field, TextInput } from '$lib/components/ui';

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
      data-tour="networks-create-form"
      class="motion-pop bg-surface-base border border-line-2 rounded-xl p-6 w-full max-w-md mx-4 shadow-[var(--shadow-restraint)]"
      onclick={(e) => e.stopPropagation()}
      role="none"
    >
      <h2 class="text-lg font-semibold text-ink-0 mb-5">{t('networkCreate.title')}</h2>
      <div class="space-y-4">
        <Field label={t('networkCreate.name')} for="network-create-name"><TextInput id="network-create-name" bind:value={form.name} disabled={creating} placeholder={t('networkCreate.namePlaceholder')} /></Field>
        <div class="flex items-center gap-2">
          <input type="checkbox" id="addSubnet" bind:checked={form.addSubnet} class="rounded border-line-2" />
          <label for="addSubnet" class="text-sm text-ink-2">{t('networkCreate.addSubnet')}</label>
        </div>
        {#if form.addSubnet}
          <Field label={t('networkCreate.subnetName')} for="network-create-subnet-name"><TextInput id="network-create-subnet-name" bind:value={form.subnetName} disabled={creating} placeholder={t('networkCreate.subnetNamePlaceholder')} /></Field>
          <Field label="CIDR" for="network-create-cidr"><TextInput id="network-create-cidr" bind:value={form.cidr} disabled={creating} placeholder="10.0.0.0/24" class="font-mono" /></Field>
          <Field label={t('networkCreate.gateway')} for="network-create-gateway"><TextInput id="network-create-gateway" bind:value={form.gateway} disabled={creating} placeholder="10.0.0.1" class="font-mono" /></Field>
          <div class="flex items-center gap-2">
            <input type="checkbox" id="dhcp" bind:checked={form.dhcp} class="rounded border-line-2" />
            <label for="dhcp" class="text-sm text-ink-2">{t('networkCreate.dhcp')}</label>
          </div>
        {/if}
      </div>
      {#if error}<Alert tone="danger" class="mt-4">{error}</Alert>{/if}
      <div class="flex justify-end gap-3 mt-6">
        <Button variant="secondary" onclick={close} disabled={creating}>{t('networkCreate.cancel')}</Button>
        <Button variant="primary" onclick={handleCreate} disabled={creating || !form.name.trim()} ariaBusy={creating} dataTour="networks-create-submit">{#if creating}<LoadingState variant="control" label="" />{/if}{creating ? t('networkCreate.creating') : t('networkCreate.create')}</Button>
      </div>
    </div>
  </div>
{/if}
