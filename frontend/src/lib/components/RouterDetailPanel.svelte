<script lang="ts">
	import { auth } from '$lib/stores/auth';
	import { createAutoRefresh } from '$lib/utils/autoRefresh.svelte';
	import { createRouterDetailController, provideRouterDetailController } from '$lib/stores/routerDetailController.svelte';
	import RouterDetailHeader from '$lib/components/router/RouterDetailHeader.svelte';
	import RouterInfoSection from '$lib/components/router/RouterInfoSection.svelte';
	import RouterGatewaySection from '$lib/components/router/RouterGatewaySection.svelte';
	import RouterInterfacesSection from '$lib/components/router/RouterInterfacesSection.svelte';

	interface Props {
		routerId: string;
		onClose?: () => void;
		onDeleted?: () => void;
	}

	let { routerId, onClose, onDeleted }: Props = $props();

	const s = createRouterDetailController({
		routerId: () => routerId,
		token: () => $auth.token ?? undefined,
		projectId: () => $auth.projectId ?? undefined,
		onDeleted: () => onDeleted?.(),
		onClose: () => onClose?.(),
	});
	provideRouterDetailController(s);

	const ar = createAutoRefresh(() => s.fetchRouter(), {
		storageKey: 'router-detail-panel',
		defaultActive: true,
		defaultInterval: 30,
		intervalOptions: [10, 15, 30, 60],
	});

	$effect(() => {
		if (routerId && $auth.projectId) {
			s.fetchRouter();
			s.fetchNetworks();
		}
	});
</script>

<div class="p-6 text-ink-1">
	<RouterDetailHeader {ar} {onClose} {routerId} />

	{#if s.loading}
		<div class="text-ink-3 text-sm">불러오는 중...</div>
	{:else if s.error}
		<div class="bg-red-900/40 border border-red-700 text-red-300 rounded-lg px-4 py-3 text-sm">{s.error}</div>
	{:else if s.router}
		<RouterInfoSection />
		<RouterGatewaySection />
		<RouterInterfacesSection />
	{/if}
</div>
