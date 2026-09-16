<script lang="ts">
	import type { RouterDetail } from '$lib/types/router';
	import type { AutoRefreshController } from '$lib/utils/autoRefresh.svelte';
	import AutoRefreshControl from '$lib/components/AutoRefreshControl.svelte';
	import StatusChip from '$lib/components/ui/StatusChip.svelte';
	import Button from '$lib/components/ui/Button.svelte';

	let {
		router,
		saving,
		ar,
		canManage = false,
		onManualRefresh,
		onDelete,
		onBack,
	}: {
		router: RouterDetail;
		saving: boolean;
		ar: AutoRefreshController;
		canManage?: boolean;
		onManualRefresh: () => void;
		onDelete: () => Promise<void>;
		onBack: () => void;
	} = $props();
</script>

<button onclick={onBack} class="text-sm text-ink-2 hover:text-ink-1 mb-6 inline-flex items-center gap-1">
	← 라우터 목록
</button>

<div class="flex items-start justify-between mb-8">
	<div>
		<h1 class="text-2xl font-bold text-ink-0">{router.name || router.id.slice(0, 12)}</h1>
		<div class="flex items-center gap-3 mt-2">
			<StatusChip status={router.status} />
			<span class="text-xs text-ink-2 font-mono">{router.id}</span>
		</div>
	</div>
	<div class="flex items-center gap-2">
		<AutoRefreshControl
			bind:active={ar.active}
			bind:intervalSeconds={ar.intervalSeconds}
			intervalOptions={ar.intervalOptions}
			refreshing={saving}
			onManualRefresh={onManualRefresh}
		/>
		{#if canManage}
			<Button variant="danger-outline" size="sm" disabled={saving} onclick={onDelete}>삭제</Button>
		{/if}
	</div>
</div>
