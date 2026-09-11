<script lang="ts">
	import AutoRefreshControl from '$lib/components/AutoRefreshControl.svelte';
	import { useFileStorageDetailController } from '$lib/stores/fileStorageDetailController.svelte';

	interface Props {
		onClose?: () => void;
		ar: { active: boolean; intervalSeconds: number; intervalOptions: number[] };
		onManualRefresh: () => Promise<void>;
	}

	let { onClose, ar, onManualRefresh }: Props = $props();
	const s = useFileStorageDetailController();
</script>

<div class="flex items-center justify-between mb-4">
	<!-- 닫기 버튼은 SlidePanel 이 제공한다(`[data-slide-panel-close]`). 이 패널은 SlidePanel 안에서만 쓰인다. -->
	<AutoRefreshControl
		bind:active={ar.active}
		bind:intervalSeconds={ar.intervalSeconds}
		intervalOptions={ar.intervalOptions}
		refreshing={s.loading}
		onManualRefresh={onManualRefresh}
	/>
</div>
