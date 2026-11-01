<script lang="ts">
	import Button from './Button.svelte';
	import { t } from '$lib/i18n/ns/common';

	let {
		page,
		totalPages = null,
		hasPrev,
		hasNext,
		onPrev,
		onNext,
		onintent,
		total = null,
		pageSize = null,
		note = null,
		class: className = '',
	}: {
		page: number;
		totalPages?: number | null;
		hasPrev: boolean;
		hasNext: boolean;
		onPrev: () => void;
		onNext: () => void;
		onintent?: () => void;
		total?: number | null;
		pageSize?: number | null;
		note?: string | null;
		class?: string;
	} = $props();
</script>

<div class="pagination {className}">
	<Button disabled={!hasPrev} onclick={onPrev} variant="subtle" size="sm" class="justify-self-start">{t('pagination.previous')}</Button>
	<div class="pagination-meta">
		{#if total != null && pageSize != null}
			<span>{t('pagination.range', { total, start: (page - 1) * pageSize + 1, end: Math.min(page * pageSize, total) })}{note ? ' ' + note : ''}</span>
		{:else if note}
			<span>{note}</span>
		{/if}
		<span class="pagination-page">{totalPages != null ? `${page} / ${totalPages}` : t('pagination.page', { page })}</span>
	</div>
	<Button disabled={!hasNext} onclick={onNext} onintent={hasNext ? onintent : undefined} variant="subtle" size="sm" class="justify-self-end">{t('pagination.next')}</Button>
</div>

<style>
	.pagination {
		display: grid;
		grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
		align-items: center;
		gap: 0.5rem 1rem;
		min-width: 0;
		max-width: 100%;
		margin-top: 0.75rem;
		font-size: var(--type-support);
		font-variant-numeric: tabular-nums;
		color: var(--color-ink-2);
	}
	.pagination-meta {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		justify-content: center;
		gap: 0.25rem 0.5rem;
		grid-column: 1 / -1;
		grid-row: 1;
		min-width: 0;
		text-align: center;
	}
	.pagination-page {
		font-weight: 500;
		color: var(--color-ink-2);
		white-space: nowrap;
		flex-shrink: 0;
	}
	@media (min-width: 768px) {
		.pagination { grid-template-columns: auto minmax(0, 1fr) auto; }
		.pagination-meta { grid-column: auto; grid-row: auto; }
	}
</style>
