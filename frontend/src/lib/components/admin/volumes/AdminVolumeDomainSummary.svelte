<script lang="ts">
	import { t } from '$lib/i18n/ns/admin-storage';
	import type { AdminVolumeStatusSummary, AdminVolumeDomainSummary } from '$lib/types/volume';
	import { formatNumber } from '$lib/utils/format';
	import Card from '$lib/components/ui/Card.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import ResponsiveTable from '$lib/components/ui/ResponsiveTable.svelte';
	import CompactResourceCard from '$lib/components/ui/CompactResourceCard.svelte';
	import TableShell from '$lib/components/ui/TableShell.svelte';

	let { summary, loading, scoped, onDomain }: {
		summary: AdminVolumeStatusSummary | null; loading: boolean; scoped: boolean;
		onDomain: (domainId: string) => void;
	} = $props();
	function ownerLabel(row: AdminVolumeDomainSummary): string {
		if (row.owner_status === 'known') return row.domain_name || row.domain_id || t('volumeList.owner.unknown_owner');
		return t(`volumeList.owner.${row.owner_status}`);
	}
	function ownerKey(row: AdminVolumeDomainSummary): string {
		return JSON.stringify([row.owner_status, row.domain_id, row.project_ids]);
	}
	function capacity(count: number | undefined, size: number | undefined): string {
		return count === undefined || size === undefined ? '—' : t('volumeList.summary.capacity', { count: formatNumber(count), size: formatNumber(size) });
	}
</script>

<section class="mb-4 space-y-3" aria-label={t('volumeList.summary.domains')} aria-busy={loading} data-testid="admin-volume-domain-summary">
	<Card>
		<h2 class="text-sm font-medium text-ink-0">{t(scoped ? 'volumeList.summary.scoped' : 'volumeList.summary.global')}</h2>
		<p class="mt-1 text-xs text-ink-2">{t('volumeList.summary.complete')}</p>
		<dl class="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-3">
			<div><dt class="text-xs text-ink-2">{t('volumeList.all')}</dt><dd class="text-sm tabular-nums text-ink-0" data-testid="admin-volume-complete-total">{loading ? '—' : capacity(summary?.total, summary?.total_gb)}</dd></div>
			<div><dt class="text-xs text-ink-2">{t('volumeList.summary.attached')}</dt><dd class="text-sm tabular-nums text-ink-0">{loading ? '—' : capacity(summary?.attached_count, summary?.attached_gb)}</dd></div>
			<div><dt class="text-xs text-ink-2">{t('volumeList.status.available')}</dt><dd class="text-sm tabular-nums text-ink-0">{loading ? '—' : capacity(summary?.available_count, summary?.available_gb)}</dd></div>
		</dl>
	</Card>
	{#if !loading && summary}
		<ResponsiveTable>
			{#snippet cards()}
				{#each summary.domains as row (ownerKey(row))}
					<CompactResourceCard>
						<h3 class="break-all text-sm font-medium text-ink-0">{ownerLabel(row)}</h3>
						{#if !row.domain_id && row.project_ids.length}<p class="break-all font-mono text-xs text-ink-2">{row.project_ids.join(', ')}</p>{/if}
						<dl class="space-y-1 text-xs text-ink-2">
							<div><dt>{t('volumeList.all')}</dt><dd>{capacity(row.volumes, row.volume_gb)}</dd></div>
							<div><dt>{t('volumeList.summary.attached')}</dt><dd>{capacity(row.attached_volumes, row.attached_gb)}</dd></div>
							<div><dt>{t('volumeList.status.available')}</dt><dd>{capacity(row.available_volumes, row.available_gb)}</dd></div>
						</dl>
						{#snippet actions()}{#if row.owner_status === 'known' && row.domain_id}<Button variant="outline" size="sm" onclick={() => onDomain(row.domain_id!)}>{t('volumeList.summary.drilldown', { name: ownerLabel(row) })}</Button>{/if}{/snippet}
						{#snippet details()}<div class="space-y-1 break-all font-mono text-xs text-ink-2"><p>{row.domain_id ?? '—'}</p>{#each row.project_ids as projectId}<p>{projectId}</p>{/each}</div>{/snippet}
					</CompactResourceCard>
				{/each}
			{/snippet}
			<TableShell density="compact">
			<table class="w-full text-left text-xs">
				<thead><tr class="border-b border-line text-ink-2"><th class="p-3">{t('volumeList.column.domain')}</th><th class="p-3">{t('volumeList.all')}</th><th class="p-3">{t('volumeList.summary.attached')}</th><th class="p-3">{t('volumeList.status.available')}</th><th class="p-3">{t('volumeList.column.actions')}</th></tr></thead>
				<tbody>{#each summary.domains as row (ownerKey(row))}<tr class="border-b border-line"><td class="p-3 text-ink-0"><span title={row.domain_id ?? undefined}>{ownerLabel(row)}</span>{#if !row.domain_id && row.project_ids.length}<p class="font-mono text-xs text-ink-2">{row.project_ids.join(', ')}</p>{/if}</td><td class="p-3 tabular-nums">{capacity(row.volumes, row.volume_gb)}</td><td class="p-3 tabular-nums">{capacity(row.attached_volumes, row.attached_gb)}</td><td class="p-3 tabular-nums">{capacity(row.available_volumes, row.available_gb)}</td><td class="p-3">{#if row.owner_status === 'known' && row.domain_id}<Button variant="outline" size="sm" onclick={() => onDomain(row.domain_id!)}>{t('volumeList.summary.drilldown', { name: ownerLabel(row) })}</Button>{/if}</td></tr>{/each}</tbody>
			</table>
			</TableShell>
		</ResponsiveTable>
	{/if}
	<p class="text-xs tabular-nums text-ink-2" role="status" data-testid="admin-volume-filtered-total">{t('volumeList.summary.filtered')}: {loading ? '—' : capacity(summary?.filtered_total, summary?.filtered_gb)}</p>
</section>
