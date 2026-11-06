<script lang="ts">
	import LoadingState from '$lib/components/ui/LoadingState.svelte';
  import { onDestroy, untrack } from 'svelte';
  import { auth, authReady, projectSwitching } from '$lib/stores/auth';
  import { domainsApi } from '$lib/api/domains';
  import type { AdminDomain, DomainDraft } from '$lib/api/domains';
  import { ApiError } from '$lib/api/client';
  import PageShell from '$lib/components/ui/PageShell.svelte';
  import PageHeader from '$lib/components/ui/PageHeader.svelte';
  import TableShell from '$lib/components/ui/TableShell.svelte';
  import FormModal from '$lib/components/ui/FormModal.svelte';
  import Field from '$lib/components/ui/Field.svelte';
  import TextInput from '$lib/components/ui/TextInput.svelte';
  import TextareaInput from '$lib/components/ui/TextareaInput.svelte';
  import Button from '$lib/components/ui/Button.svelte';
  import Alert from '$lib/components/ui/Alert.svelte';
  import Pill from '$lib/components/ui/Pill.svelte';
  import { t } from '$lib/i18n/ns/domain-admin';
  import ResponsiveTable from '$lib/components/ui/ResponsiveTable.svelte';
  import CompactResourceCard from '$lib/components/ui/CompactResourceCard.svelte';
  import RegexSearch from '$lib/components/ui/RegexSearch.svelte';
  import TableColumnHeader from '$lib/components/ui/TableColumnHeader.svelte';
  import TableViewControls from '$lib/components/ui/TableViewControls.svelte';
  import { createTableView } from '$lib/utils/tableView.svelte';
  import { t as tc } from '$lib/i18n/ns/common';
  import { sessionScopeKey } from '$lib/utils/authSession';
  import { createPrivateViewScope } from '$lib/utils/privateViewScope';
  import { intlLocale } from '$lib/i18n/runtime.svelte';
  const privateScope = createPrivateViewScope();
  let readinessRevision = $state(0);
  const stopReadiness = authReady.subscribe((ready) => {
    // Preserve the loss edge even if verification returns before runes flush.
    if (!ready) readinessRevision += 1;
  });
  onDestroy(stopReadiness);
  let items = $state<AdminDomain[]>([]);
  let loading = $state(true);
  let error = $state('');
  let modalError = $state('');
  let open = $state(false);
  let editing = $state<string | null>(null);
  let saving = $state(false);
  let draft = $state<DomainDraft>({ name: '', description: '', enabled: true });
  let revision = $state(0);
  let generation = 0;
  let query = $state('');
  let viewOwner: string | undefined;
  const domainView = createTableView<AdminDomain>({
    rows: () => items,
    search: () => query,
    locale: intlLocale,
    columns: () => [
      { key: 'name', label: t('form.name'), value: (domain) => domain.name },
      { key: 'id', label: t('form.id'), value: (domain) => domain.id },
      { key: 'status', label: t('form.status'), value: (domain) => domain.enabled, format: (value) => value ? t('state.enabled') : t('state.disabled') },
      { key: 'description', label: t('form.description'), value: (domain) => domain.description },
    ],
  });
  const owner = $derived(JSON.stringify([sessionScopeKey($auth), $privateScope, readinessRevision, $authReady, $auth.isSystemAdmin, $projectSwitching, !!$auth.token]));
  const authority = $derived(JSON.stringify([$auth.token, owner]));
  const reserved = $derived(items.some(domain => domain.id === editing && (domain.kind === 'account' || domain.kind === 'personal')));
  $effect(() => {
    const scope = authority;
    revision;
    const request = ++generation;
    const token = $auth.token ?? undefined;
    const projectId = $auth.projectId ?? undefined;
    let alive = true;
    untrack(() => {
      if (viewOwner !== owner) {
        viewOwner = owner;
        items = []; query = ''; domainView.reset();
        open = false; saving = false; draft = { name: '', description: '', enabled: true };
      }
      error = ''; loading = true;
    });
    if (!$authReady || !$auth.isSystemAdmin || $projectSwitching || !token) {
      untrack(() => { loading = false; error = t('scope.denied'); });
      return () => { alive = false; };
    }
    domainsApi.list({ token, projectId }).then(response => {
      if (alive && request === generation && scope === authority) items = response.items;
    }).catch(reason => {
      if (alive && request === generation && scope === authority) error = reason instanceof ApiError ? reason.message : t('scope.loadFailed');
    }).finally(() => { if (alive && request === generation && scope === authority) loading = false; });
    return () => { alive = false; };
  });
  function show(domain?: AdminDomain) {
    editing = domain?.id ?? null;
    draft = { name: domain?.name ?? '', description: domain?.description ?? '', enabled: domain?.enabled ?? true };
    modalError = '';
    open = true;
  }
  async function save() {
    if (saving || !draft.name.trim() || !$auth.isSystemAdmin) return;
    // Inventory reads may restart on renewal; an admitted write belongs to the
    // logical owner until it settles, not to a particular list request/token.
    const scope = owner;
    const body = { ...draft, name: draft.name.trim() };
    const access = { token: $auth.token ?? undefined, projectId: $auth.projectId ?? undefined };
    saving = true;
    modalError = '';
    try {
      if (editing) await domainsApi.update(editing, body, access);
      else await domainsApi.create(body, access);
      if (scope !== owner) return;
      open = false;
      revision += 1;
    } catch (reason) {
      if (scope === owner) modalError = reason instanceof ApiError ? reason.message : t('inventory.failed');
    } finally { if (scope === owner) saving = false; }
  }
</script>

<PageShell>
  <PageHeader title={t('inventory.title')} breadcrumb={t('inventory.breadcrumb')}>
    {#snippet actions()}
      <Button variant="primary" disabled={loading || !!error} onclick={() => show()}>{t('inventory.create')}</Button>
      <Button variant="secondary" disabled={loading} onclick={() => revision += 1}>{t('actions.refresh')}</Button>
    {/snippet}
  </PageHeader>
  <p class="text-sm text-ink-2 mb-4">{t('inventory.description')}</p>
  <RegexSearch id="admin-domain-search" bind:value={query} label={tc('table.search')} />
  <TableViewControls view={domainView} />
  <p class="mb-3 text-xs text-ink-2">{tc('table.loadedScope')}</p>
  {#if error}<Alert>{error}</Alert>
  {:else if loading}<LoadingState variant="surface" label={t('state.loading')} />
  {:else if items.length === 0}<p class="text-sm text-ink-2">{t('inventory.empty')}</p>
  {:else}
    <ResponsiveTable>
      {#snippet cards()}
        {#if domainView.rows.length === 0}<p class="text-sm text-ink-2">{tc('table.noMatches')}</p>{/if}
        {#each domainView.rows as domain (domain.id)}
          <CompactResourceCard>
            <div class="flex flex-wrap items-center justify-between gap-2"><strong class="break-words text-sm">{domain.name}</strong><Pill>{domain.enabled ? t('state.enabled') : t('state.disabled')}</Pill></div>
            {#snippet actions()}<Button size="sm" variant="secondary" onclick={() => show(domain)}>{t('actions.edit')}</Button><Button size="sm" variant="link" href={`/admin/domains/${encodeURIComponent(domain.id)}?domain_id=${encodeURIComponent(domain.id)}`}>{t('actions.inspect')}</Button>{/snippet}
            {#snippet details()}<dl class="text-xs"><dt class="text-ink-2">{t('form.id')}</dt><dd class="break-all font-mono">{domain.id}</dd><dt class="text-ink-2">{t('form.description')}</dt><dd class="whitespace-pre-wrap break-words">{domain.description || '-'}</dd></dl>{/snippet}
          </CompactResourceCard>
        {/each}
      {/snippet}
    <TableShell><table>
      <thead><tr>
        {#each domainView.columns as column (column.key)}<TableColumnHeader view={domainView} columnKey={column.key} />{/each}
        <th>{t('actions.inspect')}</th>
      </tr></thead>
      <tbody>{#each domainView.rows as domain (domain.id)}<tr>
        <td>{domain.name}</td><td class="font-mono">{domain.id}</td>
        <td><Pill>{domain.enabled ? t('state.enabled') : t('state.disabled')}</Pill></td>
        <td class="max-w-64 whitespace-pre-wrap break-words">{domain.description || '-'}</td>
        <td><div class="flex flex-wrap gap-2"><Button size="sm" variant="secondary" onclick={() => show(domain)}>{t('actions.edit')}</Button><Button size="sm" variant="link" href={`/admin/domains/${encodeURIComponent(domain.id)}?domain_id=${encodeURIComponent(domain.id)}`}>{t('actions.inspect')}</Button></div></td>
      </tr>{:else}<tr><td colspan={domainView.columns.length + 1}>{tc('table.noMatches')}</td></tr>{/each}</tbody>
    </table></TableShell>
    </ResponsiveTable>
  {/if}
</PageShell>
<FormModal bind:open title={editing ? t('inventory.edit') : t('inventory.create')} submitting={saving}>
  <div class="space-y-4">
    {#if modalError}<Alert>{modalError}</Alert>{/if}
    <Field for="domain-name" label={t('form.name')} help={t('form.nameRequired')}><TextInput id="domain-name" bind:value={draft.name} disabled={saving || reserved} /></Field>
    <Field for="domain-description" label={t('form.description')}><TextareaInput id="domain-description" bind:value={draft.description} disabled={saving} /></Field>
    <label class="flex items-center gap-3 text-sm text-ink-1 min-h-11"><input type="checkbox" bind:checked={draft.enabled} disabled={saving || reserved} />{t('form.enabled')}</label>
  </div>
  {#snippet actions()}
    <Button variant="secondary" disabled={saving} onclick={() => open = false}>{t('actions.cancel')}</Button>
    <Button variant="primary" disabled={saving || !draft.name.trim()} onclick={save}>{t('actions.save')}</Button>
  {/snippet}
</FormModal>
