<script lang="ts">
  import { onDestroy, untrack } from 'svelte';
  import { get } from 'svelte/store';
  import type { Snippet } from 'svelte';
  import { page } from '$app/state';
  import { goto } from '$app/navigation';
  import { auth, authReady, projectSwitching } from '$lib/stores/auth';
  import { domainsApi } from '$lib/api/domains';
  import type { AdminDomain } from '$lib/api/domains';
  import { ApiError } from '$lib/api/client';
  import PageShell from '$lib/components/ui/PageShell.svelte';
  import SearchSelect from '$lib/components/ui/SearchSelect.svelte';
  import Field from '$lib/components/ui/Field.svelte';
  import Button from '$lib/components/ui/Button.svelte';
  import Alert from '$lib/components/ui/Alert.svelte';
  import { t } from '$lib/i18n/ns/domain-admin';
  let { children, initialDomainId = '' }: { children: Snippet<[string, string]>; initialDomainId?: string } = $props();
  const id = $props.id();
  let domains = $state<AdminDomain[]>([]);
  let loading = $state(true);
  let error = $state('');
  let revision = $state(0);
  let verifiedAuthority = $state('');
  let authorityRevision = $state(0);
  let observedAuthority = '';
  function authorityChanged() {
    const state = get(auth);
    const next = JSON.stringify([state.sessionId, state.userId, state.identityDomainId, state.domainId, state.projectId, state.isDomainManager, state.isSystemAdmin, !!state.token, get(authReady), get(projectSwitching)]);
    if (next === observedAuthority) return;
    observedAuthority = next;
    authorityRevision += 1;
  }
  const unsubscribers = [auth.subscribe(authorityChanged), authReady.subscribe(authorityChanged), projectSwitching.subscribe(authorityChanged)];
  onDestroy(() => { for (const unsubscribe of unsubscribers) unsubscribe(); });
  const selectedId = $derived(page.url.searchParams.get('domain_id') ?? initialDomainId);
  const selected = $derived(domains.find(domain => domain.id === selectedId));
  const authority = $derived(JSON.stringify([authorityRevision, $auth.sessionId, $auth.userId, $auth.identityDomainId, $auth.projectId, $auth.domainId, $auth.isDomainManager, $auth.isSystemAdmin, $authReady, $projectSwitching]));
  $effect(() => {
    const scope = authority;
    revision;
    let alive = true;
    const { token, projectId } = untrack(() => ({ token: $auth.token ?? undefined, projectId: $auth.projectId ?? undefined }));
    untrack(() => { domains = []; loading = true; error = ''; verifiedAuthority = ''; });
    if (!untrack(() => $authReady && !$projectSwitching && $auth.isSystemAdmin) || !token) {
      untrack(() => { loading = false; error = t('scope.denied'); });
      return () => { alive = false; };
    }
    const request = revision > 0 ? domainsApi.list({ token, projectId }, { refresh: true }) : domainsApi.list({ token, projectId });
    request.then(response => {
      if (alive && scope === authority) { domains = response.items; verifiedAuthority = scope; }
    }).catch(reason => {
      if (alive && scope === authority) error = reason instanceof ApiError ? reason.message : t('scope.loadFailed');
    }).finally(() => { if (alive && scope === authority) loading = false; });
    return () => { alive = false; };
  });
  function select(value: string) {
    const url = new URL(page.url);
    url.searchParams.set('domain_id', value);
    void goto(url, { replaceState: true, keepFocus: true, noScroll: true });
  }
</script>

<PageShell>
  <div class="flex flex-wrap items-end gap-3">
    <div class="w-full sm:w-80 min-w-0">
      <Field for={`${id}-domain`} label={t('scope.domain')} help={t('scope.help')}>
        <SearchSelect id={`${id}-domain`} value={selectedId} options={domains.map(domain => ({ value: domain.id, label: domain.name, description: `${domain.id} · ${domain.enabled ? t('state.enabled') : t('state.disabled')}` }))} {loading} disabled={loading || !!error} placeholder={t('scope.choose')} ariaLabel={t('scope.domain')} onchange={select} />
      </Field>
    </div>
    <Button variant="secondary" size="sm" disabled={loading} onclick={() => revision += 1}>{t('actions.refresh')}</Button>
    {#if selectedId}<Button variant="ghost" size="sm" onclick={() => select('')}>{t('scope.clear')}</Button>{/if}
  </div>
  {#if error}<Alert class="mt-3">{error}</Alert>
  {:else if !loading && selectedId && !selected}<Alert class="mt-3">{t('scope.invalid')}</Alert>
  {:else if !loading && !selected}<p class="mt-3 text-sm text-ink-2" role="status">{t('scope.required')}</p>{/if}
</PageShell>
{#if $authReady && !$projectSwitching && $auth.isSystemAdmin && !loading && !error && selected && verifiedAuthority === authority}
  {#key `${authority}:${selected.id}`}
    {@render children(selected.id, selected.name)}
  {/key}
{/if}
