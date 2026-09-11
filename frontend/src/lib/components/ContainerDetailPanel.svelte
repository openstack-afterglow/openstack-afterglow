<script lang="ts">
	import { auth } from '$lib/stores/auth';
	import { createAutoRefresh } from '$lib/utils/autoRefresh.svelte';
	import { createContainerDetailController, provideContainerDetailController } from '$lib/stores/containerDetailController.svelte';
	import ContainerDetailHeader from '$lib/components/container/ContainerDetailHeader.svelte';
	import ContainerActionsBar from '$lib/components/container/ContainerActionsBar.svelte';
	import ContainerBasicInfoSection from '$lib/components/container/ContainerBasicInfoSection.svelte';
	import ContainerNetworkSection from '$lib/components/container/ContainerNetworkSection.svelte';
	import ContainerLogsSection from '$lib/components/container/ContainerLogsSection.svelte';

	interface Props {
		containerId: string;
		onClose?: () => void;
		adminMode?: boolean;
		onRefresh?: () => void;
	}

	let { containerId, onClose, adminMode = false, onRefresh }: Props = $props();

	const s = createContainerDetailController({
		containerId: () => containerId,
		adminMode: () => adminMode,
		token: () => $auth.token ?? undefined,
		projectId: () => $auth.projectId ?? undefined,
		onClose: () => onClose?.(),
		onRefresh: () => onRefresh?.(),
	});
	provideContainerDetailController(s);

	const ar = createAutoRefresh(() => s.fetchContainer(), {
		storageKey: 'container-detail-panel',
		defaultActive: true,
		defaultInterval: 10,
		intervalOptions: [10, 15, 30, 60],
	});

	$effect(() => {
		if (containerId) s.fetchContainer();
	});
</script>

<div class="flex flex-col h-full">
	<ContainerDetailHeader {ar} {onClose} {containerId} />

	<div class="flex-1 overflow-y-auto p-5 space-y-4">
		{#if s.loading}
			<div class="text-ink-3 text-sm">로딩 중...</div>
		{:else if s.error}
			<div class="text-red-400 text-sm">{s.error}</div>
		{:else if s.container}
			<ContainerActionsBar />
			<ContainerBasicInfoSection />
			<ContainerNetworkSection />
			<ContainerLogsSection />
		{/if}
	</div>
</div>
