<script lang="ts">
	import { t } from '$lib/i18n/ns/network-resources';
	import { createAutoRefresh } from '$lib/utils/autoRefresh.svelte';
	import { createNetworkDetailController, provideNetworkDetailController } from '$lib/stores/networkDetailController.svelte';
	import NetworkDetailHeader from '$lib/components/network/NetworkDetailHeader.svelte';
	import NetworkBasicInfoSection from '$lib/components/network/NetworkBasicInfoSection.svelte';
	import NetworkSubnetsSection from '$lib/components/network/NetworkSubnetsSection.svelte';
	import NetworkRoutersSection from '$lib/components/network/NetworkRoutersSection.svelte';
	import ActivityIndicator from '$lib/components/ui/ActivityIndicator.svelte';

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

	<!-- loading은 네트워크가 바뀔 때만 켜지므로(자동 새로고침은 유지) 섹션 진입은 최초 도착에서만 재생된다. -->
	<div class="motion-stagger flex-1 overflow-y-auto p-5 space-y-4">
		{#if s.loading}
			<ActivityIndicator label={t('network.state.loading')} />
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
