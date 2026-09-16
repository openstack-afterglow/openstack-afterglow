<script lang="ts">
	import type { ChatUsage } from '$lib/api/chatTree';
	let { usage }: { usage: ChatUsage } = $props();

	const quotaMax = $derived(usage.quota_max ?? 0);
	const quotaUsed = $derived(usage.quota_used ?? 0);
	const hasQuota = $derived(quotaMax > 0);
	const quotaPct = $derived(hasQuota ? Math.max(0, Math.round((quotaUsed / quotaMax) * 100)) : null);
	const quotaBarPct = $derived(quotaPct === null ? 0 : Math.min(100, quotaPct));
	const quotaTone = $derived(quotaPct !== null && quotaPct >= 90 ? 'danger' : quotaPct !== null && quotaPct >= 70 ? 'warning' : 'ok');

	function fmtPercent(n: number): string {
		return `${Math.max(0, Math.round(n))}%`;
	}
</script>

<div class="usage" title={hasQuota ? `이번 달 월 쿼터 사용률 ${fmtPercent(quotaPct!)}` : '월 쿼터가 설정되지 않았습니다'}>
	<div class="usage-line">
		<span class="usage-label">이번 달 쿼터</span>
		<span class="usage-val">{hasQuota ? `${fmtPercent(quotaPct!)} 사용` : '미설정'}</span>
	</div>
	{#if hasQuota}
		<div class="bar" aria-label="월 쿼터 사용률 {fmtPercent(quotaPct!)}">
			<div class="bar-fill" data-tone={quotaTone} style="width: {quotaBarPct}%"></div>
		</div>
	{/if}
</div>

<style>
	.usage {
		display: flex;
		flex-direction: column;
		align-items: flex-end;
		gap: 0.2rem;
		min-width: 0;
	}
	.usage-line {
		display: inline-flex;
		align-items: center;
		gap: 0.35rem;
		font-size: 0.72rem;
		color: var(--color-ink-2);
		white-space: nowrap;
	}
	.usage-label {
		color: var(--color-ink-2);
	}
	.usage-val {
		font-variant-numeric: tabular-nums;
	}
	.bar {
		width: 8rem;
		height: 0.3rem;
		border-radius: 999px;
		background: var(--color-surface-sunken);
		overflow: hidden;
	}
	.bar-fill {
		height: 100%;
		border-radius: 999px;
		background: var(--color-accent);
		transition: width 0.3s ease;
	}
	.bar-fill[data-tone='warning'] {
		background: var(--color-state-warning);
	}
	.bar-fill[data-tone='danger'] {
		background: var(--color-state-danger);
	}
</style>
