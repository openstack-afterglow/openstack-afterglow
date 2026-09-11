<script lang="ts">
	import { useAdminVolumeDetailController } from '$lib/stores/adminVolumeDetailController.svelte';

	const s = useAdminVolumeDetailController();
</script>

<div class="bg-surface-base border border-line rounded-xl p-4">
	<h3 class="text-xs text-ink-3 uppercase tracking-wide mb-3">연결 정보</h3>
	<div class="space-y-2">
		{#each s.volume?.attachments ?? [] as att}
			<div class="text-xs space-y-1">
				<div class="text-ink-2 font-mono">{att.server_id?.slice(0, 8)}...</div>
				<div class="text-ink-3">{att.device}</div>
			</div>
		{/each}
	</div>
</div>
