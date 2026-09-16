<script lang="ts">
	import { useAdminVolumeDetailController } from '$lib/stores/adminVolumeDetailController.svelte';

	interface Props {
		onClose?: () => void;
	}

	let { onClose }: Props = $props();

	const s = useAdminVolumeDetailController();
</script>

<div class="flex items-center justify-between px-5 py-4 border-b border-line flex-shrink-0">
	<h2 class="text-sm font-semibold text-ink-0 truncate">{s.volume?.name || 'Volume'}</h2>
</div>
