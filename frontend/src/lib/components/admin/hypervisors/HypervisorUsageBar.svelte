<script lang="ts">
	let {
		used,
		total,
		label,
	}: {
		used: number;
		total: number;
		label: string;
	} = $props();

	function usageGrad(u: number, t: number): string {
		if (t === 0) return '#374151';
		const pct = (u / t) * 100;
		if (pct >= 90) return 'var(--gradient-usage-danger)';
		if (pct >= 70) return 'var(--gradient-usage-warning)';
		return 'var(--gradient-usage)';
	}

	function usagePct(u: number, t: number): number {
		if (t === 0) return 0;
		return Math.min(100, Math.round((u / t) * 100));
	}
</script>

<div class="flex items-center gap-2">
	<div class="w-14 bg-surface-sunken rounded-full h-1.5 flex-shrink-0">
		<div class="h-1.5 rounded-full transition-all" style="width: {usagePct(used, total)}%; background: {usageGrad(used, total)}"></div>
	</div>
	<span class="text-ink-2 text-xs">{label}</span>
</div>
