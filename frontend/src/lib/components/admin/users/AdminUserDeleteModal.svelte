<script lang="ts">
  import { onDestroy } from 'svelte';
  import FormModal from '$lib/components/ui/FormModal.svelte';
  import Field from '$lib/components/ui/Field.svelte';
  import TextInput from '$lib/components/ui/TextInput.svelte';
  import Button from '$lib/components/ui/Button.svelte';
  import Alert from '$lib/components/ui/Alert.svelte';
  import type { User } from '$lib/types/common';
  import { t } from '$lib/i18n/ns/admin-identity';
  import { t as tc } from '$lib/i18n/ns/common';

  let { user, domainId, domainName, onDelete, onClose }: {
    user: User;
    domainId: string;
    domainName: string;
    onDelete: (id: string, confirmation: string) => Promise<true | { error: string; rereadRequired: boolean }>;
    onClose: () => void;
  } = $props();
  const componentId = $props.id();
  const confirmationId = `${componentId}-confirmation`;
  let open = $state(true);
  let confirmation = $state('');
  let submitting = $state(false);
  let error = $state('');
  let rereadRequired = $state(false);
  let alive = true;
  let generation = 0;
  const identity = $derived(`${domainId}:${user.domain_id}:${user.id}`);
  onDestroy(() => { alive = false; generation++; });
  $effect(() => {
    // eslint-disable-next-line @typescript-eslint/no-unused-expressions
    identity;
    confirmation = '';
    error = '';
    rereadRequired = false;
    submitting = false;
    generation++;
  });

  async function submit() {
    if (!alive || !open || submitting || rereadRequired || !domainId || user.domain_id !== domainId || confirmation !== user.id) return;
    const request = ++generation;
    const target = identity;
    submitting = true;
    error = '';
    try {
      const result = await onDelete(user.id, confirmation);
      if (!alive || !open || request !== generation || target !== identity) return;
      if (result === true) { open = false; onClose(); }
      else { error = result.error; rereadRequired = result.rereadRequired; }
    } catch {
      if (!alive || !open || request !== generation || target !== identity) return;
      error = t('userDelete.failed');
      rereadRequired = true;
    } finally {
      if (alive && open && request === generation && target === identity) submitting = false;
    }
  }
</script>

<FormModal bind:open title={t('userDelete.title')} {submitting} {onClose}>
  <div class="space-y-4">
    <Alert tone="warning">{t('userDelete.warning')}</Alert>
    <dl class="space-y-3 text-sm">
      <div><dt class="text-ink-2">{t('userTable.name')}</dt><dd class="break-all text-ink-0">{user.name}</dd></div>
      <div><dt class="text-ink-2">{t('userTable.id')}</dt><dd class="break-all font-mono text-ink-0">{user.id}</dd></div>
      <div><dt class="text-ink-2">{t('userDelete.domain')}</dt><dd class="break-all text-ink-0">{domainName}</dd><dd class="break-all font-mono text-ink-1">{domainId}</dd></div>
    </dl>
    {#if error}<Alert>{error}</Alert>{/if}
    {#if rereadRequired}<Alert tone="warning">{t('userDelete.rereadRequired')}</Alert>{/if}
    <form onsubmit={(event) => { event.preventDefault(); void submit(); }}>
      <Field for={confirmationId} label={t('userDelete.confirmId')} help={t('userDelete.confirmHelp')} required>
        <TextInput id={confirmationId} bind:value={confirmation} autocomplete="off" disabled={submitting || rereadRequired} required />
      </Field>
    </form>
  </div>
  {#snippet actions()}
    <Button variant="secondary" disabled={submitting} onclick={() => { open = false; onClose(); }}>{tc(rereadRequired ? 'actions.close' : 'actions.cancel')}</Button>
    {#if !rereadRequired}<Button variant="danger" disabled={submitting || !domainId || user.domain_id !== domainId || confirmation !== user.id} ariaBusy={submitting} onclick={submit}>{submitting ? t('state.deleting') : t('actions.delete')}</Button>{/if}
  {/snippet}
</FormModal>
