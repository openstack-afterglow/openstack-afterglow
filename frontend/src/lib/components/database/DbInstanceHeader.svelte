<script lang="ts">
	import { useDbInstanceDetailController } from '$lib/stores/dbInstanceDetailController.svelte';
	import AutoRefreshControl from '$lib/components/AutoRefreshControl.svelte';

	interface Props {
		onClose?: () => void;
	}

	let { onClose }: Props = $props();

	const s = useDbInstanceDetailController();

	const statusColor: Record<string, string> = {
		ACTIVE: 'text-green-400',
		BUILD: 'text-yellow-400',
		ERROR: 'text-red-400',
		SHUTDOWN: 'text-ink-2',
	};
	const statusLabel: Record<string, string> = { SHUTDOWN: '삭제 중' };
</script>

<div class="flex items-start justify-between">
	<div>
		{#if s.loading && !s.instance}
			<div class="h-7 w-40 bg-surface-sunken rounded animate-pulse mb-1"></div>
		{:else}
			<h1 class="text-xl font-bold text-ink-0">{s.instance?.name ?? ''}</h1>
			<span class="text-xs font-medium {statusColor[s.instance?.status ?? ''] ?? 'text-ink-2'}">
				{statusLabel[s.instance?.status ?? ''] ?? s.instance?.status ?? ''}
			</span>
		{/if}
	</div>
	<div class="flex items-center gap-2 flex-shrink-0">
		<AutoRefreshControl
			bind:active={s.ar.active}
			bind:intervalSeconds={s.ar.intervalSeconds}
			intervalOptions={s.ar.intervalOptions}
			refreshing={s.loading}
			onManualRefresh={() => s.loadAll()}
		/>
		{#if s.instance}
			<button onclick={() => s.deleteInstance()} disabled={s.deleting}
				class="text-red-400 hover:text-red-300 disabled:text-ink-3 text-xs px-2 py-1.5 rounded border border-red-900 hover:border-red-700 transition-colors">
				{s.deleting ? '삭제 중...' : '인스턴스 삭제'}
			</button>
		{/if}
		<!-- 닫기 버튼은 SlidePanel 이 제공한다(`[data-slide-panel-close]`) -->
	</div>
</div>
