<script lang="ts">
	import { useNetworkDetailController } from '$lib/stores/networkDetailController.svelte';

	const s = useNetworkDetailController();
</script>

<div class="bg-surface-base border border-line rounded-xl p-4">
	<h3 class="text-xs text-ink-3 uppercase tracking-wide mb-3">기본 정보</h3>
	<dl class="space-y-2 text-xs">
		<div class="flex justify-between">
			<dt class="text-ink-2">ID</dt>
			<dd class="text-ink-2 font-mono text-xs break-all">{s.network!.id}</dd>
		</div>
		<div class="flex justify-between">
			<dt class="text-ink-2">상태</dt>
			<dd class="{s.network!.status === 'ACTIVE' ? 'text-green-400' : 'text-ink-2'}">{s.network!.status}</dd>
		</div>
		<div class="flex justify-between">
			<dt class="text-ink-2">유형</dt>
			<dd class="flex gap-1">
				{#if s.network!.is_external}<span class="px-1.5 py-0.5 bg-orange-900/30 text-orange-300 rounded text-xs">외부</span>{/if}
				{#if s.network!.is_shared}<span class="px-1.5 py-0.5 bg-surface-selected/30 text-action-warm rounded text-xs">공유</span>{/if}
				{#if !s.network!.is_external && !s.network!.is_shared}<span class="text-ink-3">내부</span>{/if}
			</dd>
		</div>
	</dl>
</div>
