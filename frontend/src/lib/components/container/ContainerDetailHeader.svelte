<script lang="ts">
	import AutoRefreshControl from '$lib/components/AutoRefreshControl.svelte';
	import { useContainerDetailController } from '$lib/stores/containerDetailController.svelte';
	import type { AutoRefreshController } from '$lib/utils/autoRefresh.svelte';

	interface Props {
		containerId: string;
		onClose?: () => void;
		ar: AutoRefreshController;
	}

	let { containerId, onClose, ar }: Props = $props();

	const s = useContainerDetailController();
</script>

<div class="flex items-center justify-between px-5 py-4 border-b border-line flex-shrink-0">
	<div>
		<h2 class="text-sm font-semibold text-ink-0 truncate">{s.container?.name ?? containerId.slice(0, 12)}</h2>
		<p class="text-xs text-ink-2 mt-0.5 font-mono">{containerId}</p>
	</div>
	<div class="flex items-center gap-2 ml-3 flex-shrink-0">
		<AutoRefreshControl
			bind:active={ar.active}
			bind:intervalSeconds={ar.intervalSeconds}
			intervalOptions={ar.intervalOptions}
			refreshing={s.loading}
			onManualRefresh={ar.refresh}
		/>
	</div>
</div>
