<script lang="ts">
	import AutoRefreshControl from '$lib/components/AutoRefreshControl.svelte';
	import { goto } from '$app/navigation';
	import { useRouterDetailController } from '$lib/stores/routerDetailController.svelte';

	interface Props {
		onClose?: () => void;
		routerId: string;
		ar: { active: boolean; intervalSeconds: number; intervalOptions: number[] };
	}

	let { onClose, routerId, ar }: Props = $props();
	const s = useRouterDetailController();
</script>

<div class="flex items-center justify-between mb-6 border-b border-line pb-4">
	<h2 class="text-xl font-bold text-ink-0">라우터 상세</h2>
	<div class="flex items-center gap-2">
		<AutoRefreshControl
			bind:active={ar.active}
			bind:intervalSeconds={ar.intervalSeconds}
			intervalOptions={ar.intervalOptions}
			refreshing={s.loading}
			onManualRefresh={() => s.fetchRouter()}
		/>
		<button
			onclick={() => goto(`/dashboard/network/routers/${routerId}`)}
			class="text-xs text-ink-2 hover:text-action-warm-hover px-2 py-1 rounded border border-line-2 hover:border-action-warm transition-colors"
		>전체 보기 →</button>
	</div>
</div>
