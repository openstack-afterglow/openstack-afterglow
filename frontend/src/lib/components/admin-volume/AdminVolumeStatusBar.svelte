<script lang="ts">
	import { useAdminVolumeDetailController } from '$lib/stores/adminVolumeDetailController.svelte';

	const s = useAdminVolumeDetailController();

	const statusColor: Record<string, string> = {
		available: 'text-green-400',
		creating: 'text-yellow-400',
		error: 'text-red-400',
		in_use: 'text-action-warm',
		deleting: 'text-red-400',
	};
</script>

<div class="flex items-center gap-3">
	<span class="text-lg font-semibold text-ink-0">{s.volume?.name || '-'}</span>
	<span class="px-2 py-0.5 rounded text-xs font-medium {statusColor[s.volume?.status ?? ''] ?? 'text-ink-2'}">{s.volume?.status}</span>
	<span class="text-ink-2 text-sm">{s.volume?.size} GB</span>
</div>
