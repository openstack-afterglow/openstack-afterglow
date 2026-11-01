<script lang="ts">
	import { t } from '$lib/i18n/ns/admin-storage';
	import LoadingState from '$lib/components/ui/LoadingState.svelte';
	import type { AdminVolumeStatusSummary as Summary } from '$lib/types/volume';
	import StatusChip from '$lib/components/ui/StatusChip.svelte';
	import { formatNumber } from '$lib/utils/format';

	interface Props {
		summary: Summary | null;
		activeStatus: string;
		onSelect: (status: string) => void;
		loading?: boolean;
	}

	let { summary, activeStatus, onSelect, loading = false }: Props = $props();

	const knownStatuses = ['available', 'in-use', 'error', 'error_deleting', 'creating', 'deleting', 'attaching', 'detaching', 'reserved'];
	const statusCounts = $derived(new Map((summary?.statuses ?? []).map((item) => [item.status, item.count])));
	const statusRows = $derived([
		...knownStatuses
			.map((status) => ({ status, count: statusCounts.get(status) ?? 0 }))
			.filter((item) => item.count > 0),
		...(summary?.statuses ?? [])
			.filter((item) => !knownStatuses.includes(item.status) && item.count > 0)
			.map((item) => ({ status: item.status, count: item.count })),
	]);

</script>

{#if loading}
	<LoadingState variant="inline" label={t('volumeList.statusLoading')} class="mb-2" />
{/if}
<section class="volume-status-summary" aria-label={t('volumeList.statusCounts')} aria-busy={loading}>
	<p class="text-sm text-ink-2" data-testid="admin-volume-inline-capacity">{t('volumeList.summary.provisioned')}: <strong class="font-medium tabular-nums text-ink-0" data-testid="admin-volume-complete-total">{loading || !summary ? '—' : t('volumeList.summary.capacity', { count: formatNumber(summary.total), size: formatNumber(summary.total_gb) })}</strong></p>
	{#if !loading && !summary}<p class="text-sm text-ink-2" role="status">{t('volumeList.summaryUnavailable')}</p>{/if}
	<button
		type="button"
		data-volume-status=""
		class="status-card status-card-total"
		class:status-card-active={activeStatus === ''}
		aria-pressed={activeStatus === ''}
		onclick={() => onSelect('')}
	>
		<span class="status-card-label">{t('volumeList.all')}</span>
		{#if loading}
			<LoadingState variant="control" label="" aria-hidden="true" />
		{:else}
			<span class="status-card-count">{summary?.total ?? '—'}</span>
		{/if}
	</button>

	{#each statusRows as row}
		<button
			type="button"
			data-volume-status={row.status}
			class="status-card"
			class:status-card-active={activeStatus === row.status}
			aria-pressed={activeStatus === row.status}
			data-tour={row.status === 'available' ? 'admin-storage-status-available' : undefined}
			onclick={() => onSelect(row.status)}
		>
			<StatusChip status={row.status} kind="volume" />
			{#if loading}
				<LoadingState variant="control" label="" aria-hidden="true" />
			{:else}
				<span class="status-card-count">{row.count}</span>
			{/if}
		</button>
	{/each}
</section>

<style>
	.volume-status-summary {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 0.5rem;
		margin-bottom: 1rem;
	}
	.status-card {
		display: inline-flex;
		align-items: center;
		justify-content: space-between;
		gap: 0.5rem;
		min-height: 2.25rem;
		border: 1px solid var(--color-line);
		border-radius: var(--radius-md);
		background: var(--color-surface-base);
		padding: 0.375rem 0.75rem;
		color: var(--color-ink-1);
		text-align: left;
	}
	.status-card:hover,
	.status-card-active {
		border-color: var(--color-line-2);
		background: var(--color-surface-sunken);
	}

	.status-card:focus-visible {
		outline: none;
		box-shadow: var(--focus-ring);
	}

	.status-card-label {
		min-width: 0;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
		font-size: 0.8125rem;
		font-weight: 600;
		color: var(--color-ink-1);
	}

	.status-card-count {
		font-size: 0.875rem;
		font-weight: 600;
		font-variant-numeric: tabular-nums;
		line-height: 1.4;
		color: var(--color-ink-0);
	}

	@media (max-width: 1023px) { .status-card { min-height: 2.75rem; } }
</style>
