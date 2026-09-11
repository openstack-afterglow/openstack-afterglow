<script lang="ts">
	import { useImageDetailController } from '$lib/stores/imageDetailController.svelte';
	import { visibilityBadge, visibilityLabel } from '$lib/utils/format';

	interface Props {
		onClose?: () => void;
	}
	let { onClose }: Props = $props();

	const s = useImageDetailController();
</script>

<div class="flex items-start justify-between px-6 py-4 border-b border-[var(--color-line)] shrink-0">
	<div class="min-w-0 pr-4">
		{#if s.image}
			<h2 class="text-lg font-bold text-ink-0 truncate">{s.image.name}</h2>
			<div class="text-xs text-[var(--color-ink-3)] font-mono mt-1">repository: {s.image.repository ?? s.image.name} · tag: {s.image.tag ?? 'latest'}</div>
			<div class="flex items-center gap-2 mt-1.5 flex-wrap">
				<span class="px-2 py-0.5 rounded text-xs font-medium {s.image.status === 'active' ? 'text-[var(--color-state-success)] bg-[var(--color-state-success)]/15' : 'text-[var(--color-ink-2)] bg-[var(--color-surface-sunken)]'}">
					{s.image.status}
				</span>
				<span class="px-2 py-0.5 rounded text-xs font-medium {visibilityBadge(s.image.visibility)}">
					{visibilityLabel(s.image.visibility)}
				</span>
				{#if s.image.protected}
					<span class="px-2 py-0.5 rounded text-xs font-medium text-[var(--color-state-warning)] bg-[var(--color-state-warning)]/15">보호됨</span>
				{/if}
			</div>
		{:else if s.loading}
			<div class="h-6 w-48 bg-[var(--color-surface-sunken)] rounded animate-pulse"></div>
		{/if}
	</div>
	<!-- 닫기 버튼은 SlidePanel 이 제공한다(`[data-slide-panel-close]`) -->
</div>
