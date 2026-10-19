<script lang="ts">
  import { untrack } from 'svelte';
  import { auth } from '$lib/stores/auth';
  import { domainsApi } from '$lib/api/domains';
  import type { DomainManagers } from '$lib/api/domains';
  import { ApiError } from '$lib/api/client';
  import Alert from '$lib/components/ui/Alert.svelte';
  import Button from '$lib/components/ui/Button.svelte';
  import Field from '$lib/components/ui/Field.svelte';
  import SelectInput from '$lib/components/ui/SelectInput.svelte';
  import { t } from '$lib/i18n/ns/domain-admin';
  let { userId, domainId, onChanged }: { userId: string; domainId: string; onChanged?: () => void } = $props();
  const id = $props.id();
  let data = $state<DomainManagers | null>(null);
  let error = $state('');
  let loading = $state(true);
  let busy = $state(false);
  let roleId = $state('');
  let revision = $state(0);
  let generation = 0;
  const authority = $derived(JSON.stringify([userId, domainId, $auth.token, $auth.projectId, $auth.isSystemAdmin]));
  const grants = $derived(data?.items.filter(item => item.user_id === userId) ?? []);
  $effect(() => {
    const scope = authority;
    revision;
    const request = ++generation;
    const token = $auth.token ?? undefined;
    const projectId = $auth.projectId ?? undefined;
    const selectedDomain = domainId;
    let alive = true;
    untrack(() => { data = null; error = ''; roleId = ''; loading = true; busy = false; });
    if (!$auth.isSystemAdmin) {
      untrack(() => { loading = false; error = t('scope.denied'); });
      return () => { alive = false; generation += 1; };
    }
    domainsApi.managers(selectedDomain, { token, projectId }).then(response => {
      if (alive && request === generation && scope === authority) data = response;
    }).catch(reason => {
      if (alive && request === generation && scope === authority) error = reason instanceof ApiError ? reason.message : t('managers.failed');
    }).finally(() => { if (alive && request === generation && scope === authority) loading = false; });
    return () => { alive = false; generation += 1; };
  });
  async function change(role: string, remove: boolean) {
    if (!data || busy || loading || !$auth.isSystemAdmin || !data.roles.some(item => item.id === role && (remove || item.grantable))) return;
    const request = generation;
    const scope = authority;
    const token = $auth.token ?? undefined;
    const projectId = $auth.projectId ?? undefined;
    busy = true;
    error = '';
    try {
      if (remove) await domainsApi.revokeManager(domainId, userId, role, { token, projectId });
      else await domainsApi.grantManager(domainId, userId, role, { token, projectId });
      if (request !== generation || scope !== authority) return;
      onChanged?.();
      revision += 1;
    } catch (reason) {
      if (request === generation && scope === authority) error = reason instanceof ApiError ? reason.message : t('managers.failed');
    } finally { if (request === generation && scope === authority) busy = false; }
  }
</script>

<section aria-labelledby={`${id}-title`} class="mt-5 pt-4 border-t border-line min-w-0">
  <h3 id={`${id}-title`} class="text-sm font-medium text-ink-0 mb-2">{t('managers.title')}</h3>
  <p class="text-xs text-ink-2 mb-3">{t('managers.help')}</p>
  {#if error}<Alert class="mb-3">{error}</Alert>{/if}
  {#if loading}<p class="text-sm text-ink-2" role="status">{t('state.loading')}</p>
  {:else if data}
    {#if grants.length}
      <ul class="space-y-2 mb-3">{#each grants as grant (grant.role_id)}<li class="flex flex-wrap items-center justify-between gap-3 text-sm text-ink-1"><span>{grant.role_name}</span><Button variant="danger-outline" size="sm" disabled={busy} onclick={() => change(grant.role_id, true)}>{t('managers.revoke')} · {grant.role_name}</Button></li>{/each}</ul>
    {:else}<p class="text-xs text-ink-2 mb-3">{t('managers.empty')}</p>{/if}
    <div class="flex flex-wrap items-end gap-3">
      <div class="min-w-0 flex-1"><Field for={`${id}-role`} label={t('managers.role')}><SelectInput id={`${id}-role`} bind:value={roleId} disabled={busy}><option value="">{t('managers.role')}</option>{#each data.roles.filter(role => role.grantable && !grants.some(grant => grant.role_id === role.id)) as role (role.id)}<option value={role.id}>{role.name}</option>{/each}</SelectInput></Field></div>
      <Button variant="secondary" disabled={busy || !roleId} onclick={() => change(roleId, false)}>{t('managers.grant')}</Button>
    </div>
  {/if}
  <Button variant="ghost" size="sm" class="mt-3" disabled={loading || busy} onclick={() => revision += 1}>{t('actions.refresh')}</Button>
</section>
