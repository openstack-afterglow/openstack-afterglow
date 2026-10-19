<script lang="ts">
  import { onDestroy } from 'svelte';
  import FormModal from '$lib/components/ui/FormModal.svelte';
  import Field from '$lib/components/ui/Field.svelte';
  import TextInput from '$lib/components/ui/TextInput.svelte';
  import Button from '$lib/components/ui/Button.svelte';
  import Alert from '$lib/components/ui/Alert.svelte';
  import { t } from '$lib/i18n/ns/admin-identity';
  import { t as tc } from '$lib/i18n/ns/common';
  import { t as ta } from '$lib/i18n/ns/domain-auth';
  import type { DomainAccountResult } from '$lib/types/auth';
  let { open = $bindable(false), domainId, domainName, onCreate }: {
    open: boolean;
    domainId: string;
    domainName: string;
    onCreate: (form: { name: string; email: string; password: string; personal_domain_name: string; enabled: boolean }) => Promise<string | Pick<DomainAccountResult, 'identity_domain_id' | 'identity_domain_name'>>;
  } = $props();
  let form = $state({ name: '', email: '', password: '', personal_domain_name: '', enabled: true });
  let formElement = $state<HTMLFormElement>();
  let created = $state<Pick<DomainAccountResult, 'identity_domain_id' | 'identity_domain_name'> | null>(null);
  let creating = $state(false);
  let error = $state('');
  let generation = 0;
  let alive = true;
  onDestroy(() => { alive = false; generation += 1; form.password = ''; });
  $effect(() => {
    if (!open) {
      generation += 1;
      form = { name: '', email: '', password: '', personal_domain_name: '', enabled: true };
      created = null;
      error = '';
      creating = false;
    }
  });
  const passwordError = $derived(form.password && form.password.length < 12 ? ta('onboarding.passwordTooShort') : '');
  async function submit() {
    if (creating || created || !domainId || !form.name.trim() || !form.personal_domain_name.trim() || form.password.length < 12 || !formElement?.reportValidity()) return;
    const request = ++generation;
    creating = true;
    error = '';
    const body = { ...form, name: form.name.trim(), personal_domain_name: form.personal_domain_name.trim() };
    form.password = '';
    const result = await onCreate(body);
    if (!alive || request !== generation || !open) return;
    creating = false;
    if (typeof result === 'string') error = result;
    else { created = result; form = { name: '', email: '', password: '', personal_domain_name: '', enabled: true }; }
  }
</script>

<FormModal bind:open title={t('userCreate.title')} submitting={creating}>
  <div class="space-y-4">
    <Alert tone="info">{ta('onboarding.joinedDomainHelp', { domain: domainName })}<span class="block font-mono break-all mt-1">{domainId}</span></Alert>
    {#if created}
      <Alert tone="success" title={ta('onboarding.created.title')}>
        <dl class="space-y-2 [overflow-wrap:anywhere]">
          <div><dt>{ta('onboarding.personalDomain')}</dt><dd>{created.identity_domain_name}<code class="block text-xs">{created.identity_domain_id}</code></dd></div>
          <div><dt>{ta('onboarding.joinedDomain')}</dt><dd>{domainName}<code class="block text-xs">{domainId}</code></dd></div>
        </dl>
      </Alert>
    {:else}
      <form bind:this={formElement} class="space-y-4" onsubmit={(event) => { event.preventDefault(); void submit(); }}>
        {#if error}<Alert>{error}</Alert>{/if}
        <Field for="admin-user-create-name" label={t('userCreate.name')} required><TextInput id="admin-user-create-name" bind:value={form.name} disabled={creating} required /></Field>
        <Field for="admin-user-create-domain" label={ta('onboarding.personalDomain')} help={ta('onboarding.personalDomainHelp')} required><TextInput id="admin-user-create-domain" bind:value={form.personal_domain_name} maxlength={64} disabled={creating} required /></Field>
        <Field for="admin-user-create-email" label={t('userCreate.email')} required><TextInput id="admin-user-create-email" type="email" bind:value={form.email} disabled={creating} required /></Field>
        <Field for="admin-user-create-password" label={ta('onboarding.password')} help={ta('onboarding.passwordHelp')} error={passwordError} required><TextInput id="admin-user-create-password" type="password" bind:value={form.password} maxlength={1024} ariaInvalid={!!passwordError} disabled={creating} required /></Field>
        <label class="flex items-center gap-3 text-sm text-ink-1 min-h-11"><input type="checkbox" bind:checked={form.enabled} disabled={creating} />{t('userCreate.enabledLabel')}</label>
      </form>
    {/if}
  </div>
  {#snippet actions()}
    <Button variant="secondary" disabled={creating} onclick={() => open = false}>{created ? tc('actions.close') : t('userCreate.cancel')}</Button>
    {#if !created}<Button variant="primary" disabled={creating || !domainId || !form.name.trim() || !form.personal_domain_name.trim()} onclick={submit}>{creating ? t('userCreate.creating') : t('userCreate.create')}</Button>{/if}
  {/snippet}
</FormModal>
