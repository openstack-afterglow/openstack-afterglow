<script lang="ts">
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

<section class="volume-status-summary" aria-label="볼륨 상태별 개수">
	<button
		type="button"
		class="status-card status-card-total"
		class:status-card-active={activeStatus === ''}
		aria-pressed={activeStatus === ''}
		onclick={() => onSelect('')}
	>
		<span class="status-card-label">전체</span>
		<span class="status-card-count">{loading ? '…' : (summary?.total ?? 0)}</span>
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
			<span class="status-card-label">{row.status}</span>
			<span class="status-card-count">{loading ? '…' : row.count}</span>
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
