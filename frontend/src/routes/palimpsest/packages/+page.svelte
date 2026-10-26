<script lang="ts">
  import ResponsiveTable from '$lib/components/ui/ResponsiveTable.svelte';
  import CompactResourceCard from '$lib/components/ui/CompactResourceCard.svelte';
  import { onMount, untrack } from 'svelte';
  import { t } from '$lib/i18n/ns/palimpsest-packages';
  import { intlLocale } from '$lib/i18n/runtime.svelte';
  import { beforeNavigate } from '$app/navigation';
  import { page } from '$app/stores';
  import { derived, get } from 'svelte/store';
  import { auth, authReady, logoutInProgress, projectSwitching } from '$lib/stores/auth';
  import { serviceCapabilities, serviceDenials } from '$lib/stores/servicePermissions';
  import { createPalimpsestPackagesController } from '$lib/stores/palimpsestPackagesController.svelte';
  import type { KeyAction, PackageIdentity, PackageSummary, Platform, PackageKey } from '$lib/api/palimpsestPackages';
  import { samePackageIdentity } from '$lib/api/palimpsestPackages';
  import PageShell from '$lib/components/ui/PageShell.svelte';
  import PageHeader from '$lib/components/ui/PageHeader.svelte';
  import Card from '$lib/components/ui/Card.svelte';
  import TableShell from '$lib/components/ui/TableShell.svelte';
  import Button from '$lib/components/ui/Button.svelte';
  import Alert from '$lib/components/ui/Alert.svelte';
  import Tabs from '$lib/components/ui/Tabs.svelte';
  import Modal from '$lib/components/ui/Modal.svelte';
  import Field from '$lib/components/ui/Field.svelte';
  import TextInput from '$lib/components/ui/TextInput.svelte';
  import ToggleGroup from '$lib/components/ui/ToggleGroup.svelte';
  import SelectionCheckbox from '$lib/components/ui/SelectionCheckbox.svelte';
  import StatusChip from '$lib/components/ui/StatusChip.svelte';
  import ActivityIndicator from '$lib/components/ui/ActivityIndicator.svelte';
  import HubArtifactsPanel from '$lib/components/palimpsest/HubArtifactsPanel.svelte';
  import PalimpsestLocalGuide from '$lib/components/palimpsest/PalimpsestLocalGuide.svelte';
  import AssetSearchPanel from '$lib/components/palimpsest/AssetSearchPanel.svelte';
  import { t as assetText } from '$lib/i18n/ns/palimpsest-assets';
  import type { AssetIdentity } from '$lib/api/palimpsestAssets';

  const selectedIdentity = derived([auth, authReady, projectSwitching, logoutInProgress], ([$auth, ready, switching, loggingOut]): PackageIdentity | null =>
    ready && !switching && !loggingOut && $auth.token && $auth.projectId && $auth.userId
      ? { token: $auth.token, projectId: $auth.projectId, userId: $auth.userId } : null);
  const assetIdentity = $derived<AssetIdentity | null>($auth.token && $auth.projectId && $auth.userId
    ? { token: $auth.token, projectId: $auth.projectId, userId: $auth.userId, sessionId: $auth.sessionId } : null);
  let workspace = $state(get(page).url.searchParams.get('package') ? 'packages' : 'assets');
  const controller = createPalimpsestPackagesController(() => workspace === 'packages' ? get(selectedIdentity) : null, undefined, (leaf) => $serviceCapabilities(leaf), (leaf) => $serviceDenials(leaf));
  let tab = $state('inventory');
  let search = $state('');
  const visibleInventory = $derived.by(() => {
    const query = search.trim().toLowerCase();
    return (controller.inventory ?? []).filter((item) => {
      if (!query) return true;
      const latest = controller.latestVersions[item.package_id]?.version;
      return [item.namespace, item.name, `${item.namespace}/${item.name}`,
        ...item.tags.flatMap((tag) => [tag.tag, tag.digest]), latest?.root_digest ?? '',
        ...[...item.platforms, ...latest?.platforms ?? []].map((platform) => `${platform.os}/${platform.architecture}${platform.variant ? `/${platform.variant}` : ''}`),
      ].some((value) => value.toLowerCase().includes(query));
    });
  });
  let showCreate = $state(false);
  let keyName = $state('');
  let packageNames = $state('');
  let allPackages = $state(false);
  let actions = $state<KeyAction[]>([]);
  let expiryDays = $state('30');
  let formError = $state<Parameters<typeof t>[0] | ''>('');
  let copyMessage = $state<Parameters<typeof t>[0] | ''>('');
  let revokeTarget = $state<PackageKey | null>(null);
  let linkHandled = '';
  let routeLink = '';
  const actionChoices: { value: KeyAction; label: string }[] = $derived([
    { value: 'packages:inventory', label: t('action.packagesInventory') },
    { value: 'packages:read', label: t('action.packagesRead') }, { value: 'packages:write', label: t('action.packagesWrite') },
    { value: 'cache:read', label: t('action.cacheRead') }, { value: 'cache:write', label: t('action.cacheWrite') },
  ]);
  function resetForm() {
    showCreate = false; keyName = ''; packageNames = ''; allPackages = false;
    actions = []; expiryDays = '30'; formError = ''; copyMessage = ''; revokeTarget = null;
  }
  onMount(() => {
    let previous: PackageIdentity | null = null;
    const stop = selectedIdentity.subscribe((identity) => {
      if (!samePackageIdentity(previous, identity)) { resetForm(); linkHandled = ''; tab = 'inventory'; search = ''; }
      previous = identity;
      controller.bindIdentity();
    });
    const leave = () => { resetForm(); controller.discardSecret(); };
    window.addEventListener('pagehide', leave);
    return () => { stop(); window.removeEventListener('pagehide', leave); controller.dispose(); };
  });
  beforeNavigate(() => { resetForm(); controller.discardSecret(); });
  $effect(() => { workspace; $selectedIdentity; untrack(() => controller.bindIdentity()); });
  $effect(() => {
    controller.syncCapabilities();
    if (controller.issueDenied) resetForm();
    if (!controller.canIssue) copyMessage = '';
    if (controller.issued) showCreate = false;
    if (!controller.canRevoke) revokeTarget = null;
    if (controller.canRead && controller.inventory === null && !controller.busy.inventory && !controller.errors.inventory) void controller.loadInventory();
    if (tab === 'keys' && (controller.canIssue || controller.canRevoke) && controller.keys === null && !controller.busy.keys && !controller.errors.keys) void controller.loadKeys();
  });
  $effect(() => {
    const params = $page.url.searchParams;
    const name = params.get('package');
    const key = JSON.stringify([name, params.get('namespace'), params.get('digest')]);
    if (key !== routeLink) {
      routeLink = key; linkHandled = '';
      if (name) { changeWorkspace('packages'); tab = 'inventory'; }
    }
  });
  $effect(() => {
    const context = controller.context;
    const name = $page.url.searchParams.get('package');
    const namespace = $page.url.searchParams.get('namespace') ?? undefined;
    const digest = $page.url.searchParams.get('digest') ?? undefined;
    const key = `${context?.project_id}:${name}:${namespace}:${digest}`;
    if (workspace === 'packages' && tab === 'inventory' && context?.namespace && controller.canRead && name && key !== linkHandled) {
      linkHandled = key;
      void controller.openPackage(name, digest, namespace);
    }
  });
  function changeTab(value: string) {
    controller.discardSecret(); resetForm(); controller.closeDetail(); tab = value;
    if (value === 'keys') void controller.loadKeys();
  }
  function changeWorkspace(value: string) {
    controller.discardSecret(); resetForm(); controller.closeDetail(); workspace = value;
  }
  function platforms(values: Platform[]) { return values.map((item) => `${item.os}/${item.architecture}${item.variant ? `/${item.variant}` : ''}`).join(', ') || t('format.noPlatforms'); }
  function timestamp(value: string | null) { return value ? new Date(value).toLocaleString(intlLocale()) : t('format.noTimestamp'); }
  function size(value: number) { return new Intl.NumberFormat(intlLocale(), { maximumFractionDigits: 1 }).format(value / 1024 / 1024) + ' MiB'; }
  function packageType(value: string) { return value === 'runtime-bundle' ? t('format.runtimeBundle') : t('format.ociImage'); }
  async function copyReference(name: string, digest: string) {
    const context = controller.context;
    if (!context?.namespace || !context.package_authority) { copyMessage = 'copy.noAuthority'; return; }
    await copy(`${context.package_authority}/${context.namespace}/${name}@${digest}`);
  }
  async function copy(value: string, secret = false) {
    const actor = get(selectedIdentity);
    const issued = controller.issued;
    copyMessage = '';
    try {
      await navigator.clipboard.writeText(value);
      if (samePackageIdentity(actor, get(selectedIdentity)) && (!secret || issued === controller.issued)) copyMessage = 'copy.success';
    } catch {
      if (samePackageIdentity(actor, get(selectedIdentity)) && (!secret || issued === controller.issued)) copyMessage = 'copy.failure';
    }
  }
  function toggleAction(action: KeyAction, checked: boolean) {
    if (checked && !controller.canDelegate(action)) return;
    actions = checked ? [...actions, action] : actions.filter((value) => value !== action);
  }
  async function createKey(event: SubmitEvent) {
    event.preventDefault(); formError = '';
    if (!controller.canIssue) return;
    const names = packageNames.split(/[\s,]+/).filter(Boolean);
    const days = Number(expiryDays);
    if (!keyName.trim()) { formError = 'validation.name'; return; }
    if (!Number.isInteger(days) || days < 1 || days > 90) { formError = 'validation.expiry'; return; }
    if (!allPackages && (names.length < 1 || names.length > 32 || new Set(names).size !== names.length || names.some((name) => name.split('/').some((component) => !/^[a-z0-9]+(?:(?:[._]|__|-+)[a-z0-9]+)*$/.test(component)) || `${controller.context?.namespace}/${name}`.length > 255))) {
      formError = 'validation.packages'; return;
    }
    if (!actions.length || !actions.every(controller.canDelegate)) {
      formError = 'validation.actions'; return;
    }
    await controller.issueKey({ name: keyName.trim(), scope: allPackages ? { all_packages: true } : { packages: names }, actions, expires_in_days: days });
    if (controller.issued) showCreate = false;
  }
  function keyStatus(key: PackageKey) { return key.revoked_at ? t('status.revoked') : new Date(key.expires_at).getTime() <= Date.now() ? t('status.expired') : t('status.available'); }
  // Table cells show a recognizable digest prefix; the title, details and copied references keep the exact value.
  function shortDigest(digest: string) { return digest.length > 19 ? `${digest.slice(0, 19)}…` : digest; }
</script>

<svelte:head><title>{assetText('heading')} · Palimpsest</title></svelte:head>
<PageShell>
  <PageHeader breadcrumb="Palimpsest" title={assetText('heading')} subtitle={assetText('description')} />
  <div class="space-y-4">
    <Tabs id="palimpsest-workspace-tabs" value={workspace} ariaLabel={t('workspace.label')} items={[{ value: 'assets', label: assetText('heading'), panelId: 'palimpsest-assets' }, { value: 'hub', label: t('workspace.hub'), panelId: 'palimpsest-hub' }, { value: 'packages', label: t('workspace.packages'), panelId: 'palimpsest-native' }, { value: 'local', label: t('workspace.local'), panelId: 'palimpsest-local' }]} onchange={changeWorkspace} />
      <div id="palimpsest-assets" role="tabpanel" aria-labelledby="palimpsest-workspace-tabs-assets" tabindex="0" hidden={workspace !== 'assets'} inert={workspace !== 'assets'}>
        <AssetSearchPanel identity={assetIdentity} onGuide={() => changeWorkspace('local')} />
      </div>
    {#if workspace === 'hub'}
      <div id="palimpsest-hub" role="tabpanel" aria-labelledby="palimpsest-workspace-tabs-hub" tabindex="0">
        <HubArtifactsPanel identity={$selectedIdentity} />
      </div>
    {:else if workspace === 'local'}
      <div id="palimpsest-local" role="tabpanel" aria-labelledby="palimpsest-workspace-tabs-local" tabindex="0">
        <PalimpsestLocalGuide projectId={$selectedIdentity?.projectId} packageAuthority={controller.context?.package_authority} namespace={controller.context?.namespace} />
      </div>
    {:else if workspace === 'packages'}
      <div id="palimpsest-native" role="tabpanel" aria-labelledby="palimpsest-workspace-tabs-packages" tabindex="0" class="space-y-4">
        <div class="flex flex-wrap justify-end gap-2"><Button variant="secondary" disabled={!$selectedIdentity || !!controller.busy.context || !!controller.busy.issue || !!controller.busy.revoke || !!controller.busy.register} onclick={() => { void controller.loadContext(); if (tab === 'keys') void controller.loadKeys(); }}>{t('actions.refresh')}</Button></div>
    {#if controller.errors.context}
      <Alert tone="warning"><p>{t('context.unavailable')}</p><p class="mt-2">{t('context.accessHelp')}</p><p class="mt-2 break-words text-xs">{controller.errors.context}</p></Alert>
    {/if}
    {#if !controller.context}
      {#if controller.errors.context}
        <Button variant="secondary" disabled={!$selectedIdentity || !!controller.busy.context} onclick={() => controller.loadContext()}>{t('actions.retry')}</Button>
      {:else if !$selectedIdentity}<Alert tone="info">{t('context.selectProject')}</Alert>
      {:else}<p class="text-sm text-ink-2" role="status">{t('context.loading')}</p>{/if}
    {:else}
      <Card surface="base">
        <p class="break-words text-sm font-medium">{controller.context.project_name}</p>
        <p class="mt-1 break-all font-mono text-xs text-ink-2">{controller.context.project_id}</p>
        <p class="mt-2 text-sm">{t('context.namespace')} <span class="font-mono">{controller.context.namespace ?? t('context.unregistered')}</span> · {t('context.private')}</p>
        {#if controller.context.namespace && !controller.context.package_authority}<p class="mt-2 text-xs text-ink-2">{t('context.noAuthority')}</p>{/if}
      </Card>
      {#if !controller.context.namespace}
        <Card surface="base">
          <h2 class="text-sm font-semibold">{t('register.heading')}</h2>
          <p class="my-3 text-sm text-ink-2">{t('register.description')}</p>
          {#if controller.canPublish}<Button disabled={!!controller.busy.register} onclick={() => controller.register()}>{controller.busy.register ? t('register.busy') : t('register.action')}</Button>
          {:else}<p class="text-sm text-ink-2">{t('register.denied')}</p>{/if}
          {#if controller.errors.register}<Alert tone="danger" class="mt-3">{controller.errors.register}</Alert>{/if}
        </Card>
      {:else}
        <Tabs id="package-tabs" value={tab} ariaLabel={t('tabs.label')} items={[{ value: 'inventory', label: t('tabs.inventory'), panelId: 'package-inventory' }, { value: 'keys', label: t('tabs.keys'), panelId: 'package-keys' }]} onchange={changeTab} />
        {#if tab === 'inventory'}
          <div id="package-inventory" role="tabpanel" aria-labelledby="package-tabs-inventory" tabindex="0" class="space-y-4">
            {#if controller.errors.inventory}<Alert tone="danger">{controller.errors.inventory}</Alert><Button variant="secondary" onclick={() => controller.loadInventory()}>{t('inventory.retry')}</Button>{/if}
            {#if !controller.canRead}<Alert tone="warning">{t('inventory.denied')}</Alert>
            {:else if controller.busy.inventory && controller.inventory === null}<p class="text-sm text-ink-2" role="status">{t('inventory.loading')}</p>
            {:else if controller.inventory !== null}
              <Field label={t('search.label')} for="native-package-search" help={t('search.scope')}><TextInput id="native-package-search" type="search" bind:value={search} /></Field>
              <p class="text-sm text-ink-2" role="status">{t('search.count', { matched: visibleInventory.length, loaded: controller.inventory.length })}</p>
              {#if controller.inventory.length === 0}<Card surface="base"><p class="text-sm text-ink-2">{t('inventory.empty')}</p></Card>
              {:else if visibleInventory.length === 0}<Card surface="base"><p class="text-sm text-ink-2">{t('search.empty')}</p></Card>
              {:else}
                <ResponsiveTable>{#snippet cards()}{#each visibleInventory as item (item.package_id)}<CompactResourceCard>
                  <h2 class="break-all font-mono text-sm font-medium">{item.namespace}/{item.name}</h2><p class="text-xs text-ink-2">{packageType(item.package_type)} · {t('inventory.versions', { count: item.version_count })}</p>
                  {#if controller.latestVersions[item.package_id]?.version}<p class="text-xs tabular-nums">{size(controller.latestVersions[item.package_id].version!.total_bytes)} · {t('metadata.size')}</p>{:else}<p class="text-xs text-ink-2">{controller.latestVersions[item.package_id] ? t('metadata.unavailable') : t('metadata.loading')}</p>{/if}
                  {#snippet details()}<div class="space-y-1 text-xs">{@render latestMetadata(item)}{#each item.tags as tag}<p class="break-all font-mono">{tag.tag} → {tag.digest}</p>{/each}{#if !item.tags.length}<p>{t('inventory.noTags')}</p>{/if}<p>{platforms(item.platforms)}</p><p class="break-all">{item.latest_pushed_by ?? t('inventory.noPublisher')} · {timestamp(item.latest_pushed_at)}</p><p>{t('context.private')}</p></div>{/snippet}
                  {#snippet actions()}{@render packageActions(item)}{/snippet}
                </CompactResourceCard>{/each}{/snippet}
                <TableShell><table><thead><tr><th scope="col">{t('columns.package')}</th><th scope="col">{t('columns.tags')}</th><th scope="col">{t('columns.platforms')}</th><th scope="col">{t('columns.size')}</th><th scope="col">{t('columns.actions')}</th></tr></thead><tbody>
                  {#each visibleInventory as item (item.package_id)}<tr>
                    <td><span class="font-mono">{item.namespace}/{item.name}</span><p class="mt-1 text-xs text-ink-2">{packageType(item.package_type)} · {t('inventory.versions', { count: item.version_count })}</p></td>
                    <td>{#each item.tags as tag}<p class="font-mono text-xs" title={tag.digest}>{tag.tag} → {shortDigest(tag.digest)}</p>{/each}{#if !item.tags.length}<span class="text-ink-2">{t('inventory.noTags')}</span>{/if}</td>
                    <td class="max-w-56 whitespace-normal">{platforms(item.platforms)}</td><td>{@render latestMetadata(item, true)}<p class="max-w-56 break-all text-xs">{item.latest_pushed_by ?? t('inventory.noPublisher')}</p><p class="text-xs text-ink-2 tabular-nums">{timestamp(item.latest_pushed_at)}</p></td>
                    <td>{@render packageActions(item, true)}</td>
                  </tr>{/each}
                </tbody></table></TableShell></ResponsiveTable>
              {/if}
              {#if controller.nextCursor}<Button variant="secondary" disabled={!!controller.busy.inventory} onclick={() => controller.loadInventory(true)}>{t('inventory.more')}</Button>{/if}
            {/if}
            {#if controller.errors.detail}<Alert tone="danger">{controller.errors.detail}</Alert>{/if}
            {#if controller.busy.detail && !controller.detail}<p class="text-sm text-ink-2" role="status">{t('detail.loading')}</p>{/if}
            {#if controller.errors.download}<Alert tone="danger">{controller.errors.download}</Alert>{/if}
          </div>
        {:else}
          <div id="package-keys" role="tabpanel" aria-labelledby="package-tabs-keys" tabindex="0" class="space-y-4">
            <div class="flex flex-wrap items-center justify-between gap-3"><p class="text-sm text-ink-2">{t('keys.description')}</p><Button disabled={!controller.canIssue || !!controller.busy.issue || !!controller.busy.revoke || !!controller.issued} onclick={() => { resetForm(); showCreate = true; }}>{t('keys.issue')}</Button></div>
            {#if !controller.canIssue}<Alert tone="warning">{t('keys.denied')}</Alert>{/if}
            {#if controller.errors.keys}<Alert tone="danger">{controller.errors.keys}</Alert><Button variant="secondary" onclick={() => controller.loadKeys()}>{t('keys.retry')}</Button>{/if}
            {#if controller.errors.issue}<Alert tone="danger">{controller.errors.issue}</Alert>{/if}
            {#if controller.errors.revoke}<Alert tone="danger">{controller.errors.revoke}</Alert>{/if}
            {#if controller.busy.keys}<p class="text-sm text-ink-2" role="status">{t('keys.loading')}</p>{:else if controller.keys !== null}
              {#if !controller.keys.length}<Card surface="base"><p class="text-sm text-ink-2">{t('keys.empty')}</p></Card>{:else}
                <ResponsiveTable>{#snippet cards()}{#each controller.keys as key (key.key_id)}<CompactResourceCard>
                  <div class="flex flex-wrap items-center justify-between gap-2"><h2 class="text-sm font-medium">{key.name}</h2><StatusChip status={keyStatus(key)} /></div><p class="break-words font-mono text-xs">{key.actions.join(', ')}</p>
                  {#snippet details()}<p class="break-all text-xs font-mono">{t('keys.publicId')}: {key.key_id}</p><p class="break-all text-xs">{t('columns.scope')}: {key.scope.all_packages ? t('keys.allPackages') : key.scope.packages.join(', ')}</p><p class="text-xs text-ink-2">{t('keys.dates', { created: timestamp(key.created_at), expires: timestamp(key.expires_at) })}</p>{/snippet}
                  {#snippet actions()}<Button variant="ghost" size="sm" onclick={() => copy(key.key_id)}>{t('keys.copyId')}</Button><Button variant="danger-outline" disabled={!controller.canRevoke || !!key.revoked_at || !!controller.busy.issue || !!controller.busy.revoke} onclick={() => { revokeTarget = key; }}>{t('actions.revoke')}</Button>{/snippet}
                </CompactResourceCard>{/each}{/snippet}
                <TableShell><table><thead><tr><th scope="col">{t('columns.key')}</th><th scope="col">{t('columns.scope')}</th><th scope="col">{t('columns.permissions')}</th><th scope="col">{t('columns.dates')}</th><th scope="col">{t('columns.actions')}</th></tr></thead><tbody>{#each controller.keys as key (key.key_id)}<tr><td>{key.name}<div class="mt-1"><StatusChip status={keyStatus(key)} /></div></td><td class="max-w-64 break-all">{key.scope.all_packages ? t('keys.allPackages') : key.scope.packages.join(', ')}</td><td class="max-w-56 break-words font-mono text-xs">{key.actions.join(', ')}</td><td class="tabular-nums">{timestamp(key.created_at)}<p class="text-xs text-ink-2">{timestamp(key.expires_at)}</p></td><td>{@render keyRevoke(key)}</td></tr>{/each}</tbody></table></TableShell></ResponsiveTable>
              {/if}
            {/if}
          </div>
        {/if}
      {/if}
    {/if}
    {#if copyMessage}<p role="status" class="text-sm text-ink-2">{t(copyMessage)}</p>{/if}
      </div>
    {/if}
  </div>
</PageShell>

{#snippet packageActions(item: PackageSummary, stacked = false)}
  {@const digest = controller.latestVersions[item.package_id]?.version?.root_digest ?? item.tags[0]?.digest}
  <!-- Table rows stack actions so the max-content table keeps every action visible. -->
  <div class={stacked ? 'flex flex-col items-start gap-2' : 'flex flex-wrap gap-2'}><Button variant="secondary" onclick={() => controller.openPackage(item.name)}>{t('actions.detail')}</Button>{#if digest}<Button variant="ghost" disabled={!controller.context?.package_authority} onclick={() => copyReference(item.name, digest)}>{t('actions.copyReference')}</Button><Button variant="ghost" ariaBusy={!!controller.busy.download} disabled={!controller.canDownload || !!controller.busy.download} onclick={() => controller.download(item.name, digest)}>{#if controller.busy.download}<ActivityIndicator variant="download" label={t('actions.preparingDownload')} />{:else}{t('actions.download')}{/if}</Button>{/if}</div>
{/snippet}
{#snippet latestMetadata(item: PackageSummary, compact = false)}
  {@const latest = controller.latestVersions[item.package_id]}
  {#if latest?.version}
    <p class="text-xs tabular-nums">{size(latest.version.total_bytes)} · {t('metadata.size')}</p>
    <p class="max-w-72 break-all font-mono text-xs text-ink-2" title={latest.version.root_digest}>{t('metadata.digest')} {compact ? shortDigest(latest.version.root_digest) : latest.version.root_digest}</p>
  {:else if !latest}<p class="text-xs text-ink-2" role="status">{t('metadata.loading')}</p>
  {:else}<p class="max-w-72 text-xs text-state-warning-text">{t('metadata.unavailable')} · {latest.error}</p>{/if}
{/snippet}
{#snippet keyRevoke(key: PackageKey)}
  <div class="flex flex-col items-start gap-2">
    <p class="max-w-64 break-all font-mono text-xs select-all"><span class="text-ink-2">{t('keys.publicId')}</span> {key.key_id}</p>
    <Button variant="ghost" size="sm" onclick={() => copy(key.key_id)}>{t('keys.copyId')}</Button>
    <Button variant="danger-outline" disabled={!controller.canRevoke || !!key.revoked_at || !!controller.busy.issue || !!controller.busy.revoke} onclick={() => { revokeTarget = key; }}>{t('actions.revoke')}</Button>
  </div>
{/snippet}

<Modal open={!!controller.detail && controller.canRead} ariaLabel={t('detail.label')} onClose={() => controller.closeDetail()}>
  {#if controller.detail}<Card surface="modal" class="w-full max-w-full md:w-[48rem] space-y-4">
    <div class="flex flex-wrap items-center justify-between gap-3"><h2 class="break-all font-mono text-sm font-semibold">{controller.detail.namespace}/{controller.detail.name}</h2><Button variant="ghost" onclick={() => controller.closeDetail()}>{t('actions.close')}</Button></div>
    {#if copyMessage}<p role="status" class="text-sm text-ink-2">{t(copyMessage)}</p>{/if}
    <p class="text-sm text-ink-2">{packageType(controller.detail.package_type)} · {t('context.private')} · {platforms(controller.detail.platforms)}</p>
    <div class="flex flex-wrap gap-2">{#each controller.detail.tags as tag}<Button variant="secondary" disabled={!!controller.busy.version} onclick={() => controller.resolveTag(tag.tag)}>{t('detail.resolve', { tag: tag.tag })}</Button>{/each}</div>
    <h3 class="text-sm font-semibold">{t('detail.history')}</h3>
    {#if controller.errors.detail}<Alert tone="danger">{controller.errors.detail}</Alert>{/if}
    {#each controller.versions ?? [] as item (item.root_digest)}
      <Card surface="base" padding="sm">
        <p class="break-all font-mono text-xs">{item.root_digest}</p>
        <p class="my-2 text-xs text-ink-2">{size(item.total_bytes)} · {platforms(item.platforms)} · {item.pushed_by} · {timestamp(item.pushed_at)}</p>
        <div class="flex flex-wrap gap-2">
          <Button variant="secondary" disabled={!!controller.busy.version} onclick={() => controller.selectVersion(item.root_digest)}>{t('detail.version')}</Button>
          <Button variant="ghost" disabled={!controller.context?.package_authority} onclick={() => copyReference(item.package, item.root_digest)}>{t('actions.copyReference')}</Button>
          <Button variant="ghost" ariaBusy={!!controller.busy.download} disabled={!controller.canDownload || !!controller.busy.download} onclick={() => controller.download(item.package, item.root_digest)}>{#if controller.busy.download}<ActivityIndicator variant="download" label={t('actions.preparingDownload')} />{:else}{t('actions.download')}{/if}</Button>
        </div>
      </Card>
    {/each}
    {#if controller.versionsCursor}<Button variant="secondary" disabled={!!controller.busy.detail} onclick={() => controller.moreVersions()}>{t('detail.more')}</Button>{/if}
    {#if controller.busy.version}<p role="status" class="text-sm text-ink-2">{t('detail.versionLoading')}</p>{/if}
    {#if controller.errors.version}<Alert tone="danger">{controller.errors.version}</Alert>{/if}
    {#if controller.errors.download}<Alert tone="danger">{controller.errors.download}</Alert>{/if}
    {#if controller.version}<Card surface="base" class="space-y-2 text-sm"><h3 class="font-semibold">{t('detail.selected')}</h3><p class="break-all font-mono text-xs">{controller.version.root_digest}</p><p>{t('detail.mediaType', { type: controller.version.root_media_type })}</p><p>{t('detail.sizes', { verified: size(controller.version.total_bytes), archive: size(controller.version.archive_size_bytes) })}</p><p>{controller.version.pushed_by} · {timestamp(controller.version.pushed_at)}</p><h4 class="font-medium">{t('detail.provenance')}</h4><pre class="max-h-64 overflow-auto whitespace-pre-wrap break-all font-mono text-xs">{JSON.stringify(controller.version.provenance, null, 2)}</pre><h4 class="font-medium">{t('detail.graph')}</h4><pre class="max-h-64 overflow-auto whitespace-pre-wrap break-all font-mono text-xs">{JSON.stringify(controller.version.graph, null, 2)}</pre></Card>{/if}
  </Card>{/if}
</Modal>

<Modal open={showCreate} dismissible={!controller.busy.issue} ariaLabel={t('create.label')} onClose={() => { showCreate = false; controller.discardSecret(); }}>
  <Card surface="modal" class="w-full max-w-full md:w-[32rem]">
    <form onsubmit={createKey} class="space-y-4">
      <h2 class="text-sm font-semibold">{t('create.heading')}</h2>
      <Field label={t('create.name')} for="package-key-name" required><TextInput id="package-key-name" bind:value={keyName} disabled={!controller.canIssue || !!controller.busy.issue} required maxlength={128} /></Field>
      <fieldset class="space-y-2 text-sm"><legend class="mb-2 text-xs font-medium text-ink-1">{t('create.scope')}</legend>
        <ToggleGroup value={allPackages ? 'all' : 'exact'} ariaLabel={t('create.scopeLabel')} fullWidth options={[{value: 'exact', label: t('create.exact'), disabled: !controller.canIssue || !!controller.busy.issue}, {value: 'all', label: t('create.all'), disabled: !controller.canIssue || !!controller.busy.issue}]} onchange={(value) => allPackages = value === 'all'} />
        {#if allPackages}<p class="text-xs text-ink-2">{t('create.allHelp')}</p>{/if}
      </fieldset>
      {#if !allPackages}<Field label={t('create.packages')} for="package-key-packages" help={t('create.packagesHelp')}><TextInput id="package-key-packages" bind:value={packageNames} disabled={!controller.canIssue || !!controller.busy.issue} placeholder="test, team/image" required /></Field>{/if}
      <fieldset class="space-y-2 text-sm"><legend class="mb-2 text-xs font-medium text-ink-1">{t('create.actions')}</legend>
        <p class="text-xs text-ink-2">{t('create.actionsHelp')}</p>
        {#each actionChoices as action}<div class="flex flex-wrap items-center gap-2"><SelectionCheckbox checked={actions.includes(action.value)} disabled={!controller.canIssue || !!controller.busy.issue || !controller.canDelegate(action.value)} ariaLabel={action.label} onclick={() => toggleAction(action.value, !actions.includes(action.value))} />{action.label}<span class="font-mono text-xs text-ink-2">{action.value}</span></div>{/each}
      </fieldset>
      {#if !controller.canPublish && (controller.canRead || controller.canDownload)}<p class="text-xs text-ink-2">{t('create.readOnly')}</p>{/if}
      <Field label={t('create.expiry')} for="package-key-expiry" help={t('create.expiryHelp')}><TextInput id="package-key-expiry" type="number" inputmode="numeric" bind:value={expiryDays} disabled={!controller.canIssue || !!controller.busy.issue} required /></Field>
      {#if formError}<Alert tone="danger">{t(formError)}</Alert>{/if}{#if controller.errors.issue}<Alert tone="danger">{controller.errors.issue}</Alert>{/if}
      <div class="flex flex-wrap justify-end gap-2"><Button variant="secondary" disabled={!!controller.busy.issue} onclick={() => { showCreate = false; controller.discardSecret(); }}>{t('actions.cancel')}</Button><Button type="submit" disabled={!controller.canIssue || !actions.length || !actions.every(controller.canDelegate) || !!controller.busy.issue}>{controller.busy.issue ? t('create.busy') : t('keys.issue')}</Button></div>
    </form>
  </Card>
</Modal>
<Modal open={!!controller.issued} dismissible={false} ariaLabel={t('secret.label')} onClose={() => { controller.discardSecret(); copyMessage = ''; }}>
  {#if controller.issued}<Card surface="modal" class="w-full md:w-[32rem] space-y-4"><h2 class="text-sm font-semibold">{t('secret.heading')}</h2><Alert tone="warning">{t('secret.warning')}</Alert><p class="text-sm">{t('secret.expiry', { name: controller.issued.key.name, expires: timestamp(controller.issued.key.expires_at) })}</p><pre class="select-all whitespace-pre-wrap break-all rounded-md bg-surface-sunken p-3 font-mono text-xs">{controller.issued.secret}</pre>{#if copyMessage}<p role="status" class="text-sm text-ink-2">{t(copyMessage)}</p>{/if}<div class="flex flex-wrap justify-end gap-2"><Button variant="secondary" onclick={() => copy(controller.issued!.secret, true)}>{t('secret.copy')}</Button><Button onclick={() => { controller.discardSecret(); copyMessage = ''; }}>{t('secret.discard')}</Button></div></Card>{/if}
</Modal>
<Modal open={!!revokeTarget && controller.canRevoke} ariaLabel={t('revoke.label')} onClose={() => revokeTarget = null}>
  {#if revokeTarget}<Card surface="modal" class="w-full md:w-[28rem] space-y-4"><h2 class="text-sm font-semibold">{t('revoke.heading')}</h2><p class="text-sm">{t('revoke.confirm', { name: revokeTarget.name })}</p><div class="flex flex-wrap justify-end gap-2"><Button variant="secondary" onclick={() => revokeTarget = null}>{t('actions.cancel')}</Button><Button variant="danger" disabled={!controller.canRevoke || !!controller.busy.revoke} onclick={() => { const key = revokeTarget!; revokeTarget = null; void controller.revokeKey(key); }}>{t('actions.revoke')}</Button></div></Card>{/if}
</Modal>
