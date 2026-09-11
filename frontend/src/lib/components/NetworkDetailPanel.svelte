<script lang="ts">
	import { createAutoRefresh } from '$lib/utils/autoRefresh.svelte';
	import { createNetworkDetailController, provideNetworkDetailController } from '$lib/stores/networkDetailController.svelte';
	import NetworkDetailHeader from '$lib/components/network/NetworkDetailHeader.svelte';
	import NetworkBasicInfoSection from '$lib/components/network/NetworkBasicInfoSection.svelte';
	import NetworkSubnetsSection from '$lib/components/network/NetworkSubnetsSection.svelte';
	import NetworkRoutersSection from '$lib/components/network/NetworkRoutersSection.svelte';

	interface Props {
		networkId: string;
		apiBase?: string;
		onClose?: () => void;
		token?: string;
		projectId?: string;
	}

	let { networkId, apiBase = '/api/v1/admin/networks', onClose, token, projectId }: Props = $props();

	const s = createNetworkDetailController({
		networkId: () => networkId,
		apiBase: () => apiBase,
		token: () => token,
		projectId: () => projectId,
		onClose: () => onClose?.(),
	});
	provideNetworkDetailController(s);

	const ar = createAutoRefresh(() => s.fetchNetwork(), {
		storageKey: 'network-detail-panel',
		defaultActive: true,
		defaultInterval: 30,
		intervalOptions: [10, 15, 30, 60],
	});
</script>

<div class="flex flex-col h-full">
	<NetworkDetailHeader {ar} {onClose} />

	<div class="flex-1 overflow-y-auto p-5 space-y-4">
		{#if s.loading}
			<div class="text-ink-3 text-sm">로딩 중...</div>
		{:else if s.error}
			<div class="text-red-400 text-sm">{s.error}</div>
		{:else if s.network}
			<NetworkBasicInfoSection />
			<NetworkSubnetsSection />
			{#if !s.network.is_external}
				<NetworkRoutersSection />
			{/if}
		{/if}
	</div>
</div>
