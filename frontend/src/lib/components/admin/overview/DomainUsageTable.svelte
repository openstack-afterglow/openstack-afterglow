<script lang="ts">
	import { t } from '$lib/i18n/ns/admin-ops';
	import { intlLocale } from '$lib/i18n/runtime.svelte';
	import type { DomainUsage } from '$lib/types/adminOverview';
	import { Alert, CompactResourceCard, ResponsiveTable, TableShell } from '$lib/components/ui';

	let { domains, loading, error = '' }: { domains: DomainUsage[]; loading: boolean; error?: string } = $props();
	const ownerKeys = {
		known: 'overview.domains.known', deleted_project: 'overview.domains.deletedProject',
		unknown_owner: 'overview.domains.unknownOwner', deleted_domain: 'overview.domains.deletedDomain',
	} as const;
	function number(value: number | null): string {
		return value === null ? t('overview.domains.unavailable') : value.toLocaleString(intlLocale());
	}
	function href(domain: DomainUsage, resource: 'instances' | 'volumes'): string | null {
		return domain.domain_id ? `/admin/${resource}?domain_id=${encodeURIComponent(domain.domain_id)}` : null;
	}
</script>

<section class="min-w-0 rounded-lg border border-line bg-surface-base p-5" aria-label={t('overview.domains.title')}>
	<h2 class="mb-2 text-sm font-semibold text-ink-0">{t('overview.domains.title')}</h2>
	<p class="mb-3 text-xs text-ink-2">{t('overview.domains.description')}</p>
	{#if error}<Alert tone="danger">{error}</Alert>{/if}
	{#if loading}
		<div class="space-y-2" role="status" aria-busy="true" aria-label={t('overview.domains.loading')}>
			{#each Array(4) as _}<div class="h-9 motion-skeleton rounded"></div>{/each}
		</div>
	{:else if domains.length > 0}
		{#snippet identity(domain: DomainUsage)}
			<div class="min-w-0 space-y-1">
				<p class="break-words font-medium text-ink-0">{domain.domain_name || t(ownerKeys[domain.owner_status])}</p>
				{#if domain.domain_name && domain.owner_status !== 'known'}<p class="text-xs text-ink-2">{t(ownerKeys[domain.owner_status])}</p>{/if}
				{#if domain.domain_id}<p class="break-all font-mono text-xs text-ink-2">{domain.domain_id}</p>{/if}
				{#if !domain.domain_id && domain.project_ids.length > 0}
					{#each domain.project_ids as id}<p class="break-all font-mono text-xs text-ink-2">{id}</p>{/each}
				{/if}
			</div>
		{/snippet}
		{#snippet links(domain: DomainUsage)}
			{@const instancesHref = href(domain, 'instances')}
			{@const volumesHref = href(domain, 'volumes')}
			{#if instancesHref && volumesHref}
				<div class="flex flex-wrap gap-x-3 gap-y-1">
					<a class="inline-flex min-h-11 items-center text-xs text-warm-text underline" href={instancesHref}>{t('overview.domains.instancesLink')}</a>
					<a class="inline-flex min-h-11 items-center text-xs text-warm-text underline" href={volumesHref}>{t('overview.domains.volumesLink')}</a>
				</div>
			{:else}<p class="text-xs text-ink-2">{t('overview.domains.noDrilldown')}</p>{/if}
		{/snippet}
		{#snippet volumeDetails(domain: DomainUsage)}
			<dl class="space-y-1 text-xs text-ink-2">
				<div><dt>{t('overview.domains.attached')}</dt><dd class="tabular-nums">{number(domain.attached_volumes)} · {number(domain.attached_gb)} GiB</dd></div>
				<div><dt>{t('overview.domains.available')}</dt><dd class="tabular-nums">{number(domain.available_volumes)} · {number(domain.available_gb)} GiB</dd></div>
			</dl>
		{/snippet}
		<ResponsiveTable>
			{#snippet cards()}
				{#each domains as domain (JSON.stringify([domain.owner_status, domain.domain_id, domain.project_ids]))}
					<CompactResourceCard>
						{@render identity(domain)}
						<dl class="flex flex-wrap gap-3 text-xs">
							<div><dt class="text-ink-2">VM</dt><dd>{number(domain.instances)}</dd></div>
							<div><dt class="text-ink-2">vCPU</dt><dd>{number(domain.vcpus)}</dd></div>
							<div><dt class="text-ink-2">{t('overview.domains.volumes')}</dt><dd>{number(domain.volumes)} · {number(domain.volume_gb)} GiB</dd></div>
						</dl>
						{#snippet actions()}{@render links(domain)}{/snippet}
						{#snippet details()}
							<dl class="mb-2 space-y-1 text-xs text-ink-2">
								<div><dt>{t('overview.domains.projects')}</dt><dd>{number(domain.project_count)}</dd></div>
								<div><dt>RAM (GiB)</dt><dd>{number(domain.ram_mb === null ? null : domain.ram_mb / 1024)}</dd></div>
								<div><dt>GPU VM</dt><dd>{number(domain.gpu_instances)}</dd></div>
							</dl>
							{@render volumeDetails(domain)}
						{/snippet}
					</CompactResourceCard>
				{/each}
			{/snippet}
			<TableShell density="compact"><table>
				<thead><tr><th>{t('overview.domains.domain')}</th><th>{t('overview.domains.projects')}</th><th>VM</th><th>vCPU</th><th>RAM (GiB)</th><th>GPU VM</th><th>{t('overview.domains.volumes')}</th><th>{t('overview.domains.capacity')}</th><th>{t('overview.domains.details')}</th></tr></thead>
				<tbody>
					{#each domains as domain (JSON.stringify([domain.owner_status, domain.domain_id, domain.project_ids]))}
						<tr>
							<td>{@render identity(domain)}</td><td class="tabular-nums">{number(domain.project_count)}</td><td class="tabular-nums">{number(domain.instances)}</td><td class="tabular-nums">{number(domain.vcpus)}</td><td class="tabular-nums">{number(domain.ram_mb === null ? null : domain.ram_mb / 1024)}</td><td class="tabular-nums">{number(domain.gpu_instances)}</td><td class="tabular-nums">{number(domain.volumes)}</td><td class="tabular-nums">{number(domain.volume_gb)} GiB</td>
							<td><details><summary class="min-h-11 cursor-pointer text-xs text-ink-2">{t('overview.domains.volumeDetails')}</summary>{@render volumeDetails(domain)}</details>{@render links(domain)}</td>
						</tr>
					{/each}
				</tbody>
			</table></TableShell>
		</ResponsiveTable>
	{:else if !error}<p class="py-6 text-center text-sm text-ink-2">{t('overview.domains.empty')}</p>{/if}
</section>
