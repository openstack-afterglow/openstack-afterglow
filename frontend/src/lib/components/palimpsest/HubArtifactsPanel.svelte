<script lang="ts">
  import { onMount, untrack } from 'svelte';
  import type { PackageIdentity } from '$lib/api/palimpsestPackages';
  import type { HubFilters } from '$lib/api/palimpsestHub';
  import { MAX_HUB_DOWNLOAD_BYTES, hubDownloadCommand, sameHubIdentity } from '$lib/api/palimpsestHub';
  import { createPalimpsestHubController } from '$lib/stores/palimpsestHubController.svelte';
  import { projectPermissions, serviceCapabilities } from '$lib/stores/servicePermissions';
  import { intlLocale } from '$lib/i18n/runtime.svelte';
  import { t } from '$lib/i18n/ns/palimpsest-hub';
  import Card from '$lib/components/ui/Card.svelte';
  import Button from '$lib/components/ui/Button.svelte';
  import Alert from '$lib/components/ui/Alert.svelte';
  import Field from '$lib/components/ui/Field.svelte';
  import TextInput from '$lib/components/ui/TextInput.svelte';
  import SelectInput from '$lib/components/ui/SelectInput.svelte';
  import TableShell from '$lib/components/ui/TableShell.svelte';
  import StatusChip from '$lib/components/ui/StatusChip.svelte';

  let { identity }: { identity: PackageIdentity | null } = $props();
  const hub = createPalimpsestHubController(() => identity);
  let name = $state(''), prefix = $state(''), kind = $state(''), arch = $state(''), diskFormat = $state('');
  let autoRefresh = $state(false);
  let copyNotice = $state<'copied' | 'copyFailed' | null>(null);
  let visible = $state(true);
  const permissionReady = $derived(!!$projectPermissions.permissions && !$projectPermissions.loading && !$projectPermissions.error);
  const verifiedActor = $derived(permissionReady ? hub.me : null);
  const anyBusy = $derived(Object.values(hub.busy).some(Boolean));
  const cli = $derived.by(() => {
    if (!hub.detail) return '';
    try { return hubDownloadCommand(hub.detail); } catch { return ''; }
  });
  const urls = new Set<string>();

  $effect(() => {
    identity?.token; identity?.projectId; identity?.userId;
    untrack(() => { copyNotice = null; hub.bindIdentity(); });
  });
  $effect(() => {
    $projectPermissions; $serviceCapabilities;
    untrack(() => hub.syncCapabilities());
  });
  onMount(() => {
    const updateVisibility = () => { visible = !document.hidden; };
    updateVisibility();
    document.addEventListener('visibilitychange', updateVisibility);
    const timer = setInterval(() => {
      if (autoRefresh && visible) void hub.refresh(true);
    }, 30_000);
    return () => {
      clearInterval(timer); document.removeEventListener('visibilitychange', updateVisibility);
      hub.dispose();
      for (const url of urls) URL.revokeObjectURL(url);
    };
  });
  function timestamp(value: string | number | null | undefined) {
    if (value === null || value === undefined || value === '') return t('unknown');
    // Hub DATETIME rows serialize UTC without an offset; epochs and explicit offsets already identify an instant.
    const instant = typeof value === 'string' && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?$/.test(value) ? `${value}Z` : value;
    const date = new Date(instant);
    return Number.isNaN(date.getTime()) ? t('unknown') : date.toLocaleString(intlLocale());
  }
  function bytes(value: number | null | undefined) {
    if (value === null || value === undefined || !Number.isFinite(value) || value < 0) return t('unknown');
    if (value < 1024) return `${value.toLocaleString(intlLocale())} B`;
    const unit = value >= 1024 ** 3 ? 3 : value >= 1024 ** 2 ? 2 : 1;
    return `${(value / 1024 ** unit).toLocaleString(intlLocale(), { maximumFractionDigits: 1 })} ${['B', 'KiB', 'MiB', 'GiB'][unit]}`;
  }
  async function search(clear = false) {
    if (clear) { name = ''; prefix = ''; kind = ''; arch = ''; diskFormat = ''; }
    const filters: HubFilters = {};
    if (name.trim()) filters.name = name.trim();
    if (prefix.trim()) filters.digest_prefix = prefix.trim();
    if (kind === 'cloud-image' || kind === 'squashfs') filters.kind = kind;
    if (arch === 'x86_64' || arch === 'aarch64') filters.arch = arch;
    if (diskFormat === 'raw' || diskFormat === 'qcow2' || diskFormat === 'vmdk' || diskFormat === 'vdi' || diskFormat === 'vhd' || diskFormat === 'vhdx') filters.disk_format = diskFormat;
    copyNotice = null;
    await hub.setFilters(filters);
  }
  async function copyDigest() {
    const actor = identity ? { ...identity } : null;
    const digest = hub.detail?.blob_digest;
    if (!digest || !hub.canInventory) return;
    try {
      await navigator.clipboard.writeText(digest);
      if (sameHubIdentity(actor, identity) && hub.detail?.blob_digest === digest) copyNotice = 'copied';
    } catch {
      if (sameHubIdentity(actor, identity) && hub.detail?.blob_digest === digest) copyNotice = 'copyFailed';
    }
  }
  async function saveDownload() {
    const actor = identity ? { ...identity } : null;
    const layer = hub.detail;
    if (!layer || !hub.canDownload) return;
    const blob = await hub.download();
    if (!blob || !sameHubIdentity(actor, identity) || !hub.canDownload || hub.detail?.blob_digest !== layer.blob_digest) return;
    const url = URL.createObjectURL(blob); urls.add(url);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = `${layer.blob_digest.slice(7)}.${layer.kind === 'squashfs' ? 'squashfs' : layer.disk_format || 'blob'}`;
    anchor.click();
    setTimeout(() => { URL.revokeObjectURL(url); urls.delete(url); }, 1000);
  }
</script>

<section class="space-y-4 min-w-0" aria-label={t('heading')}>
  <Card surface="base">
    <div class="flex flex-wrap items-start justify-between gap-4">
      <div class="min-w-0 space-y-2">
        <h2 class="text-sm font-semibold text-ink-0">{t('heading')}</h2>
        <p class="text-sm text-ink-2">{t('description')}</p>
        {#if verifiedActor}<p class="text-xs text-ink-2 break-all">{verifiedActor.project_name} · <code>{verifiedActor.project_id}</code> · <code>{verifiedActor.user_id}</code></p>{/if}
      </div>
      <Button variant="secondary" size="sm" disabled={!identity || !permissionReady || anyBusy} onclick={() => hub.refresh(visible)}>{t('refresh')}</Button>
    </div>
    <label class="mt-4 flex items-center gap-2 text-xs text-ink-2">
      <input type="checkbox" bind:checked={autoRefresh} disabled={!identity || !permissionReady} />{t('autoRefresh')}
    </label>
  </Card>
  {#if !identity}
    <Alert tone="info">{t('noIdentity')}</Alert>
  {:else if $projectPermissions.error}
    <Alert>{t('permissions.error')} {$projectPermissions.error}</Alert>
  {:else if !permissionReady}
    <Alert tone="info">{t('permissions.pending')}</Alert>
  {:else if hub.errors.me}
    <Alert>{hub.errors.me}</Alert>
    <Button variant="secondary" size="sm" disabled={anyBusy} onclick={() => hub.refresh(visible)}>{t('retry')}</Button>
  {:else if hub.busy.me || !hub.me}
    <p role="status" class="text-sm text-ink-2">{t('loading')}</p>
  {:else}
    <section class="space-y-3 min-w-0" aria-label={t('inventory')}>
      <h3 class="text-sm font-semibold">{t('inventory')}</h3>
      {#if !hub.canInventory}
        <Alert tone="warning">{t('denied')}</Alert>
      {:else}
        <Card surface="base">
          <form onsubmit={(event) => { event.preventDefault(); void search(); }} class="space-y-3">
            <div class="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-5">
              <Field label={t('filter.name')} for="hub-name"><TextInput id="hub-name" bind:value={name} maxlength={128} /></Field>
              <Field label={t('filter.digest')} for="hub-prefix"><TextInput id="hub-prefix" bind:value={prefix} maxlength={71} /></Field>
              <Field label={t('filter.kind')} for="hub-kind"><SelectInput id="hub-kind" bind:value={kind}><option value="">{t('filter.all')}</option><option value="cloud-image">cloud-image</option><option value="squashfs">squashfs</option></SelectInput></Field>
              <Field label={t('filter.arch')} for="hub-arch"><SelectInput id="hub-arch" bind:value={arch}><option value="">{t('filter.all')}</option><option value="x86_64">x86_64</option><option value="aarch64">aarch64</option></SelectInput></Field>
              <Field label={t('filter.format')} for="hub-format"><SelectInput id="hub-format" bind:value={diskFormat}><option value="">{t('filter.all')}</option>{#each ['raw', 'qcow2', 'vmdk', 'vdi', 'vhd', 'vhdx'] as format}<option value={format}>{format}</option>{/each}</SelectInput></Field>
            </div>
            <p class="text-xs text-ink-2">{t('filter.help')}</p>
            <div class="flex flex-wrap gap-2"><Button type="submit" variant="secondary" size="sm">{t('filter.apply')}</Button><Button variant="ghost" size="sm" onclick={() => search(true)}>{t('filter.clear')}</Button></div>
          </form>
        </Card>
        <p class="text-xs text-ink-2">{hub.observed.inventory ? t('observed', { time: timestamp(hub.observed.inventory) }) : t('neverObserved')}</p>
        {#if hub.errors.inventory}<Alert>{hub.errors.inventory}</Alert><Button variant="secondary" size="sm" disabled={hub.busy.inventory} onclick={() => hub.loadInventory()}>{t('retry')}</Button>{/if}
        {#if hub.busy.inventory}<p role="status" class="text-sm text-ink-2">{t('loading')}</p>{/if}
        {#if hub.inventory}
          <p class="text-xs text-ink-2">{t('page', { start: hub.offset, count: hub.inventory.length })}</p>
          {#if hub.inventory.length === 0}<Alert tone="neutral">{t('empty')}</Alert>{:else}
            <TableShell><table><thead><tr><th>{t('name')}</th><th>{t('filter.kind')}</th><th>{t('filter.arch')}</th><th>{t('size')}</th><th>{t('digest')}</th><th>{t('details')}</th></tr></thead><tbody>
              {#each hub.inventory as row (row.blob_digest)}<tr data-selected={hub.selected === row.blob_digest}><td>{row.name}</td><td><code>{row.kind}</code></td><td><code>{row.arch ?? '—'}</code></td><td>{bytes(row.size_bytes)}</td><td><code title={row.blob_digest}>{row.blob_digest.slice(0, 19)}…</code></td><td><Button variant="secondary" size="sm" onclick={() => { copyNotice = null; void hub.openDetail(row.blob_digest); }}>{t('details')}</Button></td></tr>{/each}
            </tbody></table></TableShell>
          {/if}
        {/if}
        <div class="flex flex-wrap gap-2"><Button variant="secondary" size="sm" disabled={hub.offset === 0 || hub.busy.inventory} onclick={() => hub.page(-1)}>{t('previous')}</Button><Button variant="secondary" size="sm" disabled={!hub.hasNext || hub.busy.inventory} onclick={() => hub.page(1)}>{t('next')}</Button></div>
        {#if hub.selected}
          <Card surface="base">
            <div class="flex flex-wrap items-center justify-between gap-2"><h3 class="text-sm font-semibold">{t('details')}</h3><Button variant="ghost" size="sm" onclick={() => hub.closeDetail()}>{t('close')}</Button></div>
            {#if hub.busy.detail}<p role="status" class="mt-3 text-sm text-ink-2">{t('loading')}</p>{/if}
            {#if hub.errors.detail}<Alert class="mt-3">{hub.errors.detail}</Alert><Button variant="secondary" size="sm" onclick={() => hub.openDetail(hub.selected!)}>{t('retry')}</Button>{/if}
            {#if hub.detail}
              {@const item = hub.detail}
              <div class="space-y-3 mt-3">
                <h4 class="text-sm font-semibold break-all">{item.name}</h4>
                <code class="block text-xs break-all select-all">{item.blob_digest}</code>
                <div class="flex flex-wrap gap-2"><Button variant="secondary" size="sm" onclick={copyDigest}>{t('copy')}</Button><Button variant="secondary" size="sm" disabled={!hub.canDownload || hub.busy.download || item.size_bytes > MAX_HUB_DOWNLOAD_BYTES} onclick={saveDownload}>{hub.busy.download ? t('download.busy') : t('download')}</Button></div>
                {#if copyNotice}<p role="status" class="text-xs text-ink-2">{t(copyNotice)}</p>{/if}
                {#if !hub.canDownload}<Alert tone="warning">{t('denied')}</Alert>{/if}
                {#if hub.errors.download}<Alert>{hub.errors.download}</Alert>{/if}
                <p class="text-xs text-ink-2">{t('download.limit')}</p>
                {#if cli}<pre class="overflow-x-auto text-xs select-all">{cli}</pre>{:else}<Alert tone="warning">{t('error.unsupported')}</Alert>{/if}
                <Alert tone={item.chain_complete ? 'info' : 'warning'}>{item.chain_complete ? t('chain.complete') : t('chain.incomplete')}</Alert>
                <dl class="grid grid-cols-1 gap-3 text-xs md:grid-cols-2">
                  {#each ['kind', 'media_type', 'disk_format', 'arch', 'os_variant', 'ubuntu_base', 'python_version', 'project_id', 'created_by', 'parent_digest', 'base_image_digest', 'config_digest', 'chain_id'] as key}
                    <div class="min-w-0"><dt class="text-ink-2"><code>{key}</code></dt><dd class="break-all"><code>{String(item[key as keyof typeof item] ?? t('unknown'))}</code></dd></div>
                  {/each}
                  <div><dt class="text-ink-2">{t('size')}</dt><dd>{bytes(item.size_bytes)}</dd></div><div><dt class="text-ink-2">{t('jobs.created')}</dt><dd>{timestamp(item.created_at)}</dd></div><div><dt class="text-ink-2"><code>is_published</code></dt><dd>{item.is_published ? t('published') : t('private')}</dd></div>
                </dl>
                <h4 class="text-xs font-semibold">{t('chain.ancestors')}</h4>
                {#if item.ancestors.length}<ol class="space-y-2 text-xs">{#each item.ancestors as digest}<li class="break-all"><code>{digest}</code></li>{/each}</ol>{:else}<p class="text-xs text-ink-2">{t('chain.none')}</p>{/if}
                <details><summary class="text-xs cursor-pointer">{t('config')}</summary><pre class="mt-2 max-h-80 overflow-auto whitespace-pre-wrap break-all text-xs">{JSON.stringify(item.config_json, null, 2)}</pre></details>
              </div>
            {/if}
          </Card>
        {/if}
      {/if}
    </section>
    <div class="grid grid-cols-1 gap-4 lg:grid-cols-2">
      <Card surface="base">
        <section class="space-y-3" aria-label={t('builds')}>
          <div class="flex flex-wrap items-center justify-between gap-2"><h3 class="text-sm font-semibold">{t('builds')}</h3><Button variant="ghost" size="sm" disabled={!hub.canBuilds || hub.busy.builds} onclick={() => hub.loadBuilds()}>{t('refresh')}</Button></div>
          <p class="text-xs text-ink-2">{hub.observed.builds ? t('observed', { time: timestamp(hub.observed.builds) }) : t('neverObserved')}</p>
          {#if !hub.canBuilds}<Alert tone="warning">{t('denied')}</Alert>{:else}
            {#if hub.errors.builds}<Alert>{hub.errors.builds}</Alert>{/if}
            {#if hub.busy.builds}<p role="status" class="text-sm text-ink-2">{t('loading')}</p>{/if}
            {#if hub.builds?.length === 0}<p class="text-xs text-ink-2">{t('jobs.empty')}</p>{/if}
            {#if hub.builds}<ul class="space-y-3">{#each hub.builds as job (job.id)}<li class="border-t border-line pt-3 space-y-2">
              <div class="flex flex-wrap justify-between gap-2"><span class="text-sm break-all">{job.name}</span><StatusChip status={job.status} /></div>
              <p class="text-xs text-ink-2">{t('jobs.noMetrics')}</p>
              <details><summary class="text-xs cursor-pointer"><code>{job.id}</code></summary><dl class="mt-2 space-y-2 text-xs"><div><dt>{t('jobs.created')}</dt><dd>{timestamp(job.created_at)}</dd></div><div><dt>{t('jobs.started')}</dt><dd>{timestamp(job.started_at)}</dd></div><div><dt>{t('jobs.completed')}</dt><dd>{timestamp(job.completed_at)}</dd></div><div><dt><code>output_size_bytes</code></dt><dd>{bytes(job.output_size_bytes)}</dd></div><div><dt><code>output_digest</code></dt><dd class="break-all"><code>{job.output_digest ?? t('unknown')}</code></dd></div><div><dt>{t('jobs.error')}</dt><dd class="break-all">{job.error_code ?? t('unknown')}</dd></div></dl></details>
            </li>{/each}</ul>{/if}
          {/if}
        </section>
      </Card>
      <Card surface="base">
        <section class="space-y-3" aria-label={t('exports')}>
          <div class="flex flex-wrap items-center justify-between gap-2"><h3 class="text-sm font-semibold">{t('exports')}</h3><Button variant="ghost" size="sm" disabled={!hub.canInventory || hub.busy.exports} onclick={() => hub.loadExports()}>{t('refresh')}</Button></div>
          <p class="text-xs text-ink-2">{hub.observed.exports ? t('observed', { time: timestamp(hub.observed.exports) }) : t('neverObserved')}</p>
          {#if !hub.canInventory}<Alert tone="warning">{t('denied')}</Alert>{:else}
            {#if hub.errors.exports}<Alert>{hub.errors.exports}</Alert>{/if}
            {#if hub.busy.exports}<p role="status" class="text-sm text-ink-2">{t('loading')}</p>{/if}
            {#if hub.exports?.length === 0}<p class="text-xs text-ink-2">{t('jobs.empty')}</p>{/if}
            {#if hub.exports}<ul class="space-y-3">{#each hub.exports as job (job.id)}<li class="border-t border-line pt-3 space-y-2">
              <div class="flex flex-wrap justify-between gap-2"><span class="text-sm break-all">{job.source_name}</span><StatusChip status={job.status} /></div>
              <p class="text-xs text-ink-2">{Number.isFinite(job.progress_pct) && job.progress_pct >= 0 && job.progress_pct <= 100 ? `${job.progress_pct.toLocaleString(intlLocale())}%` : t('jobs.noMetrics')}</p>
              <details><summary class="text-xs cursor-pointer"><code>{job.id}</code></summary><dl class="mt-2 space-y-2 text-xs"><div><dt>{t('jobs.created')}</dt><dd>{timestamp(job.created_at)}</dd></div><div><dt>{t('jobs.started')}</dt><dd>{timestamp(job.started_at)}</dd></div><div><dt>{t('jobs.completed')}</dt><dd>{timestamp(job.completed_at)}</dd></div><div><dt><code>target_disk_format</code></dt><dd><code>{job.target_disk_format}</code></dd></div><div><dt>{t('size')}</dt><dd>{bytes(job.size_bytes)}</dd></div><div><dt><code>blob_digest</code></dt><dd class="break-all"><code>{job.blob_digest ?? t('unknown')}</code></dd></div><div><dt>{t('jobs.error')}</dt><dd class="break-all">{job.error_code ?? t('unknown')}{#if job.error_message} · {job.error_message}{/if}</dd></div></dl></details>
            </li>{/each}</ul>{/if}
          {/if}
        </section>
      </Card>
    </div>
  {/if}
</section>
