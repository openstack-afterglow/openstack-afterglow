<script lang="ts">
	import type { ActiveTab } from '$lib/stores/k3sClusterDetailController.svelte';
	import { useK3sClusterDetailController } from '$lib/stores/k3sClusterDetailController.svelte';
	import Tabs from '$lib/components/ui/Tabs.svelte';

	const s = useK3sClusterDetailController();

	const tabs: { value: ActiveTab; label: string; panelId: string }[] = [
		{ value: 'main', label: '메인', panelId: 'k3s-panel-main' },
		{ value: 'configmaps', label: 'ConfigMap', panelId: 'k3s-panel-configmaps' },
		{ value: 'secrets', label: 'Secret', panelId: 'k3s-panel-secrets' },
		{ value: 'services', label: 'Service', panelId: 'k3s-panel-services' },
		{ value: 'workloads', label: 'Deployment / RS', panelId: 'k3s-panel-workloads' },
		{ value: 'pods', label: 'Pod', panelId: 'k3s-panel-pods' },
		{ value: 'stampede', label: 'Stampede', panelId: 'k3s-panel-stampede' },
	];
</script>

<Tabs
	id="k3s-cluster-tabs"
	value={s.activeTab}
	items={tabs}
	ariaLabel="Kubernetes 리소스"
	onchange={(value) => { s.activeTab = value as ActiveTab; }}
	class="mb-5"
/>
