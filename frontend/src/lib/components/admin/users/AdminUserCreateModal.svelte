<script lang="ts">
	import LoadingState from '$lib/components/ui/LoadingState.svelte';
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
  import AccountResultDetails from '$lib/components/auth/AccountResultDetails.svelte';
  let { open = $bindable(false), domainId, onCreate }: {
    open: boolean;
    domainId: string;
    onCreate: (form: { name: string; email: string; password: string; enabled: boolean }) => Promise<string | DomainAccountResult>;
  } = $props();
  let form = $state({ name: '', email: '', password: '', enabled: true });
  let formElement = $state<HTMLFormElement>();
  // Enter in a field presses the real Create button, so click guards (tutorial steps) see it like a click.
  let submitHost = $state<HTMLElement>();
  let created = $state<DomainAccountResult | null>(null);
  let creating = $state(false);
  let error = $state('');
  let generation = 0;
  let alive = true;
  onDestroy(() => { alive = false; generation += 1; form.password = ''; });
  $effect(() => {
    if (!open) {
      generation += 1;
      form = { name: '', email: '', password: '', enabled: true };
      created = null;
      error = '';
      creating = false;
    }
  });
  const passwordError = $derived(form.password && form.password.length < 12 ? ta('onboarding.passwordTooShort') : '');
  // Tutorial readiness: the submit anchor exists only once submit() would actually send the request.
  const complete = $derived.by(() => {
    // eslint-disable-next-line @typescript-eslint/no-unused-expressions
    form.email;
    // Browsers accept `a@b`; the tour waits for a dotted domain so Next never appears mid-address.
    return !!form.name.trim() && form.password.length >= 12 && /@[^@\s]+\.[^@\s]{2,}$/.test(form.email) && !!formElement?.checkValidity();
  });
  async function submit() {
    if (creating || created || !domainId || !form.name.trim() || form.password.length < 12 || !formElement?.reportValidity()) return;
    const request = ++generation;
    creating = true;
    error = '';
    const body = { ...form, name: form.name.trim() };
    form.password = '';
    const result = await onCreate(body);
    if (!alive || request !== generation || !open) return;
    creating = false;
    if (typeof result === 'string') error = result;
    else { created = result; form = { name: '', email: '', password: '', enabled: true }; }
  }
</script>

<FormModal bind:open title={t('userCreate.title')} submitting={creating} dataTour={created ? 'admin-users-create-result' : undefined}>
  <div class="space-y-4">
    {#if created}
      <Alert tone="success" title={ta('onboarding.created.title')}>
        <AccountResultDetails result={created} />
      </Alert>
    {:else}
      <Alert tone="info">{t('userCreate.accountSpacesHelp')}</Alert>
      <form bind:this={formElement} class="space-y-4" data-tour="admin-users-create-fields" onsubmit={(event) => { event.preventDefault(); submitHost?.querySelector('button')?.click(); }}>
        {#if error}<Alert>{error}</Alert>{/if}
        <Field for="admin-user-create-name" label={t('userCreate.name')} required><TextInput id="admin-user-create-name" bind:value={form.name} disabled={creating} required /></Field>
        <Field for="admin-user-create-email" label={t('userCreate.email')} required><TextInput id="admin-user-create-email" type="email" bind:value={form.email} disabled={creating} required /></Field>
        <Field for="admin-user-create-password" label={ta('onboarding.password')} help={ta('onboarding.passwordHelp')} error={passwordError} required><TextInput id="admin-user-create-password" type="password" bind:value={form.password} maxlength={1024} ariaInvalid={!!passwordError} disabled={creating} required /></Field>
        <label class="flex items-center gap-3 text-sm text-ink-1 min-h-11"><input type="checkbox" bind:checked={form.enabled} disabled={creating} />{t('userCreate.enabledLabel')}</label>
      </form>
    {/if}
  </div>
  {#snippet actions()}
    <Button variant="secondary" disabled={creating} dataTour={created ? 'admin-users-create-close' : undefined} onclick={() => open = false}>{created ? tc('actions.close') : t('userCreate.cancel')}</Button>
    {#if !created}<span bind:this={submitHost} class="contents"><Button variant="primary" disabled={creating || !domainId || !form.name.trim()} dataTour={complete && !creating ? 'admin-users-create-submit' : undefined} onclick={submit}>{#if creating}<LoadingState variant="control" label="" aria-hidden="true" />{/if}{creating ? t('userCreate.creating') : t('userCreate.create')}</Button></span>{/if}
  {/snippet}
</FormModal>
