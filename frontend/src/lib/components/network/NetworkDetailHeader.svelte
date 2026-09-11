<script lang="ts">
	import AutoRefreshControl from '$lib/components/AutoRefreshControl.svelte';
	import { useNetworkDetailController } from '$lib/stores/networkDetailController.svelte';

	interface Props {
		onClose?: () => void;
		ar: { active: boolean; intervalSeconds: number; intervalOptions: number[] };
	}

	let { onClose, ar }: Props = $props();
	const s = useNetworkDetailController();
</script>

<div class="flex items-center justify-between px-5 py-4 border-b border-line flex-shrink-0">
	<h2 class="text-sm font-semibold text-ink-0 truncate">{s.network?.name || ''}</h2>
	<div class="flex items-center gap-2 ml-3 flex-shrink-0">
		<AutoRefreshControl
			bind:active={ar.active}
			bind:intervalSeconds={ar.intervalSeconds}
			intervalOptions={ar.intervalOptions}
			refreshing={s.loading}
			onManualRefresh={() => s.fetchNetwork()}
		/>
		<!-- 닫기 버튼은 SlidePanel 이 제공한다(`[data-slide-panel-close]`) -->
	</div>
</div>
