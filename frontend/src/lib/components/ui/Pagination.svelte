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
	} = $props();
</script>

<div class="pagination">
	<Button disabled={!hasPrev} onclick={onPrev} variant="subtle" size="sm">{t('pagination.previous')}</Button>
	<div class="pagination-meta">
		{#if total != null && pageSize != null}
			<span>{t('pagination.range', { total, start: (page - 1) * pageSize + 1, end: Math.min(page * pageSize, total) })}{note ? ' ' + note : ''}</span>
		{:else if note}
			<span>{note}</span>
		{/if}
		<span class="pagination-page">{totalPages != null ? `${page} / ${totalPages}` : t('pagination.page', { page })}</span>
	</div>
	<Button disabled={!hasNext} onclick={onNext} onintent={hasNext ? onintent : undefined} variant="subtle" size="sm">{t('pagination.next')}</Button>
</div>

<style>
	.pagination {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 1rem;
		margin-top: 0.75rem;
		font-size: 0.75rem;
		color: var(--color-ink-2);
	}
	.pagination-meta {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		min-width: 0;
	}
	.pagination-page {
		font-weight: 500;
		color: var(--color-ink-2);
	}
</style>
