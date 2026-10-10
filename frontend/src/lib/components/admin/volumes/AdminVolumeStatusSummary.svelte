<script lang="ts" module>
	import { t } from '$lib/i18n/ns/admin-storage';

	const statusKeys: Record<string, Parameters<typeof t>[0]> = {
		available: 'volumeList.status.available',
		'in-use': 'volumeList.status.inUse',
		error: 'volumeList.status.error',
		error_deleting: 'volumeList.status.errorDeleting',
		creating: 'volumeList.status.creating',
		deleting: 'volumeList.status.deleting',
		attaching: 'volumeList.status.attaching',
		detaching: 'volumeList.status.detaching',
		reserved: 'volumeList.status.reserved',
	};

	export function volumeStatusLabel(status: string): string {
		const key = Object.hasOwn(statusKeys, status) ? statusKeys[status] : undefined;
		return key ? t(key) : status;
	}
</script>

<script lang="ts">
	import ActivityIndicator from '$lib/components/ui/ActivityIndicator.svelte';
	import type { AdminVolumeStatusSummary as Summary } from '$lib/types/volume';
	import { getStatusStyle } from '$lib/config/statusColors';

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

	function toneFor(status: string): string {
		return getStatusStyle(status).tone;
	}
</script>

{#if loading}
	<ActivityIndicator size="sm" label={t('volumeList.statusLoading')} class="mb-2" />
{/if}
<section class="volume-status-summary" aria-label={t('volumeList.statusCounts')} aria-busy={loading}>
	<button
		type="button"
		class="status-card status-card-total"
		class:status-card-active={activeStatus === ''}
		aria-pressed={activeStatus === ''}
		onclick={() => onSelect('')}
	>
		<span class="status-card-label">{t('volumeList.all')}</span>
		{#if loading}
			<span class="motion-skeleton h-5 w-8 rounded" aria-hidden="true"></span>
		{:else}
			<span class="status-card-count">{summary?.total ?? 0}</span>
		{/if}
	</button>

	{#each statusRows as row}
		{@const tone = toneFor(row.status)}
		<button
			type="button"
			class="status-card status-card-{tone}"
			class:status-card-active={activeStatus === row.status}
			aria-pressed={activeStatus === row.status}
			data-tour={row.status === 'available' ? 'admin-storage-status-available' : undefined}
			onclick={() => onSelect(row.status)}
		>
			<span class="status-card-label">{volumeStatusLabel(row.status)}</span>
			{#if loading}
				<span class="motion-skeleton h-5 w-8 rounded" aria-hidden="true"></span>
			{:else}
				<span class="status-card-count">{row.count}</span>
			{/if}
		</button>
	{/each}
</section>

<style>
	.volume-status-summary {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(8.5rem, 1fr));
		gap: 0.75rem;
		margin-bottom: 1rem;
	}

	.status-card {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 0.75rem;
		border: 1px solid var(--status-line, var(--color-line));
		border-radius: 0.875rem;
		background: color-mix(in oklab, var(--status-tone, var(--color-surface-raised)) 10%, var(--color-surface-raised));
		padding: 0.875rem 1rem;
		color: var(--color-ink-1);
		text-align: left;
		transition: border-color 0.15s, box-shadow 0.15s, transform 0.15s, background 0.15s;
	}

	.status-card:hover,
	.status-card-active {
		border-color: var(--status-tone, var(--color-accent));
		box-shadow: 0 8px 24px color-mix(in oklab, var(--status-tone, var(--color-accent)) 18%, transparent);
		transform: translateY(-1px);
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
		font-size: 1.25rem;
		font-weight: 700;
		line-height: 1;
		color: var(--status-tone, var(--color-ink-0));
	}

	.status-card-total { --status-tone: var(--color-accent); --status-line: var(--accent-ring); }
	.status-card-success { --status-tone: var(--color-state-success); --status-line: color-mix(in oklab, var(--color-state-success) 30%, transparent); }
	.status-card-warning { --status-tone: var(--color-state-warning); --status-line: color-mix(in oklab, var(--color-state-warning) 30%, transparent); }
	.status-card-danger { --status-tone: var(--color-state-danger); --status-line: color-mix(in oklab, var(--color-state-danger) 30%, transparent); }
	.status-card-info { --status-tone: var(--color-state-info); --status-line: color-mix(in oklab, var(--color-state-info) 30%, transparent); }
	.status-card-neutral { --status-tone: var(--color-state-neutral); --status-line: color-mix(in oklab, var(--color-state-neutral) 30%, transparent); }
</style>
