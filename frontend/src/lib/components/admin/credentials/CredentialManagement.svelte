<script lang="ts">
  import { onMount, untrack } from 'svelte';
  import { get } from 'svelte/store';
  import { auth, authReady, projectSwitching } from '$lib/stores/auth';
  import { createAdminCredentialsController } from '$lib/stores/adminCredentialsController.svelte';
  import PageShell from '$lib/components/ui/PageShell.svelte';
  import PageHeader from '$lib/components/ui/PageHeader.svelte';
  import ResourceToolbar from '$lib/components/ui/ResourceToolbar.svelte';
  import TableShell from '$lib/components/ui/TableShell.svelte';
  import Button from '$lib/components/ui/Button.svelte';
  import Alert from '$lib/components/ui/Alert.svelte';
  import Field from '$lib/components/ui/Field.svelte';
  import TextInput from '$lib/components/ui/TextInput.svelte';
  import TextareaInput from '$lib/components/ui/TextareaInput.svelte';
  import SelectInput from '$lib/components/ui/SelectInput.svelte';
  import Modal from '$lib/components/ui/Modal.svelte';
  import Card from '$lib/components/ui/Card.svelte';
  import { t } from '$lib/i18n/ns/admin-identity';
  import { t as dt } from '$lib/i18n/ns/domain-admin';
  import { intlLocale } from '$lib/i18n/runtime.svelte';
  let { kind, domainId, domainName }: { kind: 'application' | 'user'; domainId: string; domainName: string } = $props();
  // DomainScope remounts this instance; also fence direct prop changes defensively.
  // svelte-ignore state_referenced_locally
  const ctrl = createAdminCredentialsController(kind, domainId);
  const componentId = $props.id();
  const modalTitleId = `${componentId}-credential-title`;
  let search = $state(''), userSearch = $state(''), projectFilter = $state(''), typeFilter = $state(''), expiryFilter = $state('');
  $effect(() => { const id = domainId; untrack(() => ctrl.setScope(id)); search = ''; userSearch = ''; projectFilter = ''; typeFilter = ''; expiryFilter = ''; });
  const title = $derived(t(kind === 'application' ? 'credentials.applicationTitle' : 'credentials.userTitle'));
  const expiryFormatter = $derived(new Intl.DateTimeFormat(intlLocale(), { dateStyle: 'medium', timeStyle: 'short' }));
  function expiryLabel(value: string) {
    const timestamp = Date.parse(value);
    return Number.isFinite(timestamp) ? expiryFormatter.format(timestamp) : value;
  }
  const projects = $derived([...new Set(ctrl.items.flatMap(item => item.project_id ? [item.project_id] : []))].sort());
  const types = $derived([...new Set(ctrl.items.flatMap(item => 'type' in item ? [item.type] : []))].sort());
  const hasFilters = $derived(Boolean(search || projectFilter || typeFilter || expiryFilter));
  const filtered = $derived(ctrl.items.filter(item => {
    if (projectFilter && item.project_id !== projectFilter) return false;
    if (typeFilter && (!('type' in item) || item.type !== typeFilter)) return false;
    if (expiryFilter && 'expires_at' in item) {
      const expires = item.expires_at === null ? null : Date.parse(item.expires_at);
      if (expiryFilter === 'never' && expires !== null) return false;
      if (expiryFilter === 'expired' && (expires === null || !(expires <= Date.now()))) return false;
      if (expiryFilter === 'active' && expires !== null && !(expires > Date.now())) return false;
    }
    return [item.id, item.user_id, item.project_id, 'name' in item ? item.name : item.type, 'description' in item ? item.description : ''].some(value => value?.toLocaleLowerCase().includes(search.toLocaleLowerCase()));
  }));
  const filteredUsers = $derived(ctrl.users.filter(user => user.id === ctrl.selectedUser || `${user.name} ${user.id}`.toLocaleLowerCase().includes(userSearch.toLocaleLowerCase())));
  const modalOpen = $derived(ctrl.mode !== null);
  const modalTitle = $derived(ctrl.mode === 'issued' ? t('credentials.issued') : ctrl.mode === 'delete' ? t('credentials.deleteTitle') : ctrl.mode === 'edit' ? t('credentials.editTitle') : ctrl.mode === 'create' ? t('credentials.createTitle') : t('credentials.detailTitle'));
  onMount(() => {
    const sync = () => {
      const state = get(auth);
      ctrl.setAuthority({ token: state.token ?? undefined, userId: state.userId ?? undefined, projectId: state.projectId ?? undefined, admin: state.isSystemAdmin, ready: get(authReady) && !get(projectSwitching) });
    };
    const subscriptions = [auth.subscribe(sync), authReady.subscribe(sync), projectSwitching.subscribe(sync)];
    return () => { for (const unsubscribe of subscriptions) unsubscribe(); ctrl.dispose(); };
  });
</script>

<PageShell>
  <PageHeader title={title} breadcrumb={t('credentials.identity')} subtitle={`${domainName} · ${domainId}`}>
    {#snippet actions()}
      <Button variant="primary" disabled={!ctrl.canCreate} onclick={() => ctrl.open('create')}>{t('actions.create')}</Button>
      <Button variant="secondary" disabled={!ctrl.allowed || ctrl.loading} onclick={ctrl.load}>{t('credentials.refresh')}</Button>
    {/snippet}
  </PageHeader>
  <Alert tone="info" class="mb-4">{t(kind === 'application' ? 'credentials.applicationNotice' : 'credentials.userNotice')}</Alert>
  <ResourceToolbar label={t('credentials.filters')} class="mb-4">
    <TextInput type="search" bind:value={search} ariaLabel={t('credentials.search')} placeholder={t('credentials.search')} />
    <TextInput type="search" bind:value={userSearch} ariaLabel={t('credentials.userSearch')} placeholder={t('credentials.userSearch')} />
    <SelectInput value={ctrl.selectedUser} ariaLabel={t('credentials.user')} onchange={(event) => ctrl.selectUser((event.currentTarget as HTMLSelectElement).value)}>
      <option value="">{kind === 'user' ? t('credentials.allUsers') : dt('credentials.chooseUser')}</option>
      {#each filteredUsers as user (user.id)}<option value={user.id}>{user.name} · {user.id}</option>{/each}
    </SelectInput>
    <SelectInput bind:value={projectFilter} ariaLabel={t('credentials.project')}>
      <option value="">{dt('credentials.allProjects')}</option>
      {#each projects as project}<option value={project}>{project}</option>{/each}
    </SelectInput>
    {#if kind === 'user'}
      <SelectInput bind:value={typeFilter} ariaLabel={t('credentials.type')}>
        <option value="">{dt('credentials.allTypes')}</option>
        {#each types as type}<option value={type}>{type}</option>{/each}
      </SelectInput>
    {:else}
      <SelectInput bind:value={expiryFilter} ariaLabel={t('credentials.expiry')}>
        <option value="">{dt('credentials.allExpiries')}</option>
        <option value="expired">{dt('credentials.expired')}</option>
        <option value="active">{dt('credentials.active')}</option>
        <option value="never">{dt('credentials.neverExpires')}</option>
      </SelectInput>
    {/if}
  </ResourceToolbar>
  {#if ctrl.directoryLoading}<p class="text-sm text-ink-2 mb-3" role="status">{t('credentials.directoryLoading')}</p>{/if}
  {#if ctrl.directoryError}<Alert class="mb-3">{ctrl.directoryError}<Button variant="ghost" size="sm" onclick={ctrl.loadUsers}>{t('credentials.retryDirectory')}</Button></Alert>{/if}
  {#if ctrl.error}<Alert class="mb-4">{ctrl.error}</Alert>{/if}
  {#if ctrl.loading}<p role="status" class="text-sm text-ink-2">{t('state.loading')}</p>
  {:else if ctrl.allowed && !ctrl.error && kind === 'application' && !ctrl.selectedUser && !ctrl.directoryLoading && !ctrl.directoryError}<p class="text-sm text-ink-2 py-8 text-center">{dt('credentials.chooseUser')}</p>
  {:else if !ctrl.error && !ctrl.directoryLoading && !ctrl.directoryError && ctrl.allowed && filtered.length === 0}<p class="text-sm text-ink-2 py-8 text-center">{hasFilters ? t('credentials.noMatches') : t('credentials.empty')}</p>
  {:else if ctrl.allowed && filtered.length}
    <TableShell><table>
      <thead><tr><th>{t(kind === 'application' ? 'form.name' : 'credentials.type')}</th><th>{t('credentials.id')}</th><th>{t('credentials.project')}</th><th>{t('credentials.user')}</th>{#if kind === 'application'}<th>{t('credentials.expiry')}</th>{/if}<th>{t('credentials.actions')}</th></tr></thead>
      <tbody>{#each filtered as item (item.id)}<tr>
        <td>{'name' in item ? item.name : item.type}</td><td class="font-mono">{item.id}</td><td>{item.project_id ?? t('credentials.none')}</td><td>{item.user_id}</td>
        {#if 'expires_at' in item}<td>{#if item.expires_at}<time datetime={item.expires_at} title={item.expires_at}>{expiryLabel(item.expires_at)}</time>{:else}{dt('credentials.neverExpires')}{/if}</td>{/if}
        <td><div class="flex gap-2"><Button variant="ghost" size="sm" onclick={() => ctrl.open('detail', item)}>{t('credentials.details')}</Button><Button variant="danger" size="sm" onclick={() => ctrl.open('delete', item)}>{t('actions.delete')}</Button></div></td>
      </tr>{/each}</tbody>
    </table></TableShell>
  {/if}
</PageShell>

<Modal open={modalOpen} labelledBy={modalTitleId} onClose={ctrl.close} dismissible={!ctrl.busy && ctrl.mode !== 'issued'}>
  <Card surface="modal" padding="lg" class="w-[28rem] max-w-full">
  <h2 id={modalTitleId} class="text-lg font-semibold text-ink-0 mb-5">{modalTitle}</h2>
  <div class="space-y-4">
    {#if ctrl.busy}<p role="status" class="text-sm text-ink-2">{t('state.loading')}</p>{/if}
    {#if ctrl.modalError}<Alert>{ctrl.modalError}</Alert>{/if}
    {#if ctrl.mode === 'issued' && ctrl.issued}
      <Alert tone="warning">{t('credentials.onceOnly')}</Alert>
      <Field label={t('credentials.id')}><p class="font-mono break-all">{ctrl.issued.id}</p></Field>
      <Field label={t('credentials.secret')}><p class="font-mono break-all select-all">{ctrl.issued.secret}</p></Field>
    {:else if ctrl.mode === 'delete'}
      <Alert tone="warning">{t('credentials.deleteWarning', { id: ctrl.detail?.id ?? '' })}</Alert>
    {:else if ctrl.mode === 'create' || ctrl.mode === 'edit'}
      {#if kind === 'application'}
        <p class="text-sm text-ink-2 break-all">{t('credentials.creationScope', { user: ctrl.context?.user_id ?? '', project: ctrl.context?.project_id ?? '' })}</p>
        <Field label={t('form.name')}><TextInput bind:value={ctrl.draft.name} ariaLabel={t('form.name')} disabled={ctrl.busy} /></Field>
        <Field label={t('form.description')}><TextareaInput bind:value={ctrl.draft.description} ariaLabel={t('form.description')} disabled={ctrl.busy} /></Field>
        <Field label={t('credentials.expiry')} help={t('credentials.optionalExpiry')}><input type="datetime-local" bind:value={ctrl.draft.expires_at} aria-label={t('credentials.expiry')} disabled={ctrl.busy} class="w-full rounded-md border border-line-2 bg-surface-sunken px-3 py-2 text-sm text-ink-0" /></Field>
        <fieldset class="space-y-2"><legend class="text-sm text-ink-1 mb-2">{t('credentials.roles')}</legend>
          {#each ctrl.context?.roles ?? [] as role (role.id)}<label class="flex items-center gap-2 text-sm min-h-11"><input type="checkbox" value={role.id} bind:group={ctrl.draft.role_ids} disabled={ctrl.busy} />{role.name || role.id}</label>{/each}
        </fieldset>
      {:else}
        <Field label={t('credentials.user')}><SelectInput bind:value={ctrl.draft.user_id} ariaLabel={t('credentials.user')} disabled={ctrl.busy}><option value="">{dt('credentials.chooseUser')}</option>{#each ctrl.users as user (user.id)}<option value={user.id}>{user.name} · {user.id}</option>{/each}</SelectInput></Field>
        <Field label={t('credentials.project')} help={t('credentials.projectHelp')}><TextInput bind:value={ctrl.draft.project_id} ariaLabel={t('credentials.project')} disabled={ctrl.busy} /></Field>
        <Field label={t('credentials.type')} help={t('credentials.typeHelp')}><TextInput bind:value={ctrl.draft.type} ariaLabel={t('credentials.type')} disabled={ctrl.busy} /></Field>
        <Field label={t('credentials.blob')} help={t('credentials.blobHelp')}><TextareaInput rows={8} bind:value={ctrl.draft.blob} ariaLabel={t('credentials.blob')} disabled={ctrl.busy} /></Field>
      {/if}
    {:else if ctrl.mode === 'detail' && ctrl.detail}
      <dl class="space-y-3 text-sm break-all">
        <div><dt class="text-ink-2">{t('credentials.id')}</dt><dd class="font-mono">{ctrl.detail.id}</dd></div>
        <div><dt class="text-ink-2">{t('credentials.user')}</dt><dd>{ctrl.detail.user_id}</dd></div>
        <div><dt class="text-ink-2">{t('credentials.project')}</dt><dd>{ctrl.detail.project_id ?? t('credentials.none')}</dd></div>
        {#if 'roles' in ctrl.detail}
          <div><dt class="text-ink-2">{t('form.name')}</dt><dd>{ctrl.detail.name}</dd></div>
          <div><dt class="text-ink-2">{t('form.description')}</dt><dd>{ctrl.detail.description}</dd></div>
          <div><dt class="text-ink-2">{t('credentials.roles')}</dt><dd>{ctrl.detail.roles.map(role => role.name || role.id).join(', ')}</dd></div>
          <div><dt class="text-ink-2">{t('credentials.expiry')}</dt><dd>{#if ctrl.detail.expires_at}<time datetime={ctrl.detail.expires_at} title={ctrl.detail.expires_at}>{expiryLabel(ctrl.detail.expires_at)}</time>{:else}{dt('credentials.neverExpires')}{/if}</dd></div>
          <div><dt class="text-ink-2">{t('credentials.restricted')}</dt><dd>{ctrl.detail.unrestricted ? t('credentials.no') : t('credentials.yes')}</dd></div>
        {:else}
          <div><dt class="text-ink-2">{t('credentials.type')}</dt><dd>{ctrl.detail.type}</dd></div>
          {#if ctrl.detail.blob !== undefined}<Alert tone="warning">{t('credentials.sensitive')}</Alert><pre class="whitespace-pre-wrap break-all font-mono">{ctrl.detail.blob}</pre>{/if}
        {/if}
      </dl>
    {/if}
  </div>
  <div class="flex flex-wrap justify-end gap-3 mt-6">
    <Button variant="secondary" onclick={ctrl.close}>{t('credentials.close')}</Button>
    {#if ctrl.mode === 'create' || ctrl.mode === 'edit' || ctrl.mode === 'delete'}
      <Button variant={ctrl.mode === 'delete' ? 'danger' : 'primary'} disabled={ctrl.busy || (kind === 'application' && ctrl.mode === 'create' && !ctrl.context)} onclick={ctrl.submit}>{ctrl.mode === 'delete' ? t('actions.delete') : t('actions.save')}</Button>
    {:else if ctrl.mode === 'detail' && kind === 'user'}
      <Button variant="secondary" disabled={ctrl.busy} onclick={() => ctrl.reveal()}>{t('credentials.reveal')}</Button>
      <Button variant="primary" disabled={ctrl.busy} onclick={() => ctrl.reveal(true)}>{t('credentials.editSensitive')}</Button>
    {/if}
  </div>
  </Card>
</Modal>
