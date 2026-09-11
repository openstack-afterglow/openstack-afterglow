<script lang="ts">
	import PageHeader from '$lib/components/ui/PageHeader.svelte';
	import AutoRefreshControl from '$lib/components/AutoRefreshControl.svelte';
	import TutorialStartButton from '$lib/tutorial/TutorialStartButton.svelte';
	import type { AutoRefreshController } from '$lib/utils/autoRefresh.svelte';

	let {
		showDeleted = $bindable(),
		ar,
		refreshing,
		onForceRefresh,
		onOpenCreate,
		onOpenCreateIntent,
		onToggleDeleted,
	}: {
		showDeleted: boolean;
		ar: AutoRefreshController;
		refreshing: boolean;
		onForceRefresh: () => void;
		onOpenCreate: () => void;
		onOpenCreateIntent?: () => void;
		onToggleDeleted: () => void;
	} = $props();
</script>

<PageHeader breadcrumb="CONTAINERS / K3S" title="Drover 클러스터">
	{#snippet actions()}
		<TutorialStartButton tour="drover" />
		<button
			onclick={onToggleDeleted}
			class="hidden sm:inline-flex text-xs px-3 py-1.5 rounded border transition-colors {showDeleted
				? 'border-line-2 text-ink-2 bg-surface-sunken'
				: 'border-line-2 text-ink-3 hover:border-line-2 hover:text-ink-2'}"
		>
			{showDeleted ? '삭제 이력 숨기기' : '삭제 이력 보기'}
		</button>
		<AutoRefreshControl
			bind:active={ar.active}
			bind:intervalSeconds={ar.intervalSeconds}
			intervalOptions={ar.intervalOptions}
			{refreshing}
			onManualRefresh={onForceRefresh}
		/>
		<button
			data-tour="drover-create-open"
			onclick={onOpenCreate}
			onpointerenter={onOpenCreateIntent}
			onfocus={onOpenCreateIntent}
			class="bg-surface-selected hover:bg-surface-selected text-ink-0 text-sm font-medium px-4 py-2 rounded-lg transition-colors"
		>
			+ 클러스터 생성
		</button>
	{/snippet}
</PageHeader>
