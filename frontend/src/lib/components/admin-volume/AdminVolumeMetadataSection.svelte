<script lang="ts">
	import { useAdminVolumeDetailController } from '$lib/stores/adminVolumeDetailController.svelte';

	const s = useAdminVolumeDetailController();
</script>

<div class="bg-surface-base border border-line rounded-xl p-4">
	<h3 class="text-xs text-ink-3 uppercase tracking-wide mb-3">메타데이터</h3>
	<dl class="space-y-1.5 text-xs">
		{#each Object.entries(s.volume?.metadata ?? {}) as [k, v]}
			<div class="flex gap-2">
				<dt class="text-ink-3 min-w-24">{k}</dt>
				<dd class="text-ink-2 break-all">{v}</dd>
			</div>
		{/each}
	</dl>
</div>
