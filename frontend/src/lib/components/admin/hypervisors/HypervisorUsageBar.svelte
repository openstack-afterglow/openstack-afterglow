<script lang="ts">
	import { usageTone } from '$lib/design/tokens';

	let {
		used,
		total,
		label,
	}: {
		used: number;
		total: number;
		label: string;
	} = $props();

	// 임계값은 usageTone 하나만 따른다. 여기 있던 70/90 은 문서화된 80/95 계약과 어긋났다.
	function usageGrad(u: number, t: number): string {
		if (t === 0) return 'transparent';
		const tone = usageTone(usagePct(u, t));
		return tone === 'danger'
			? 'var(--gradient-usage-danger)'
			: tone === 'warning'
				? 'var(--gradient-usage-warning)'
				: 'var(--gradient-usage)';
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
