<script lang="ts">
	import { t } from '$lib/i18n/ns/drover';
	import type { ActiveTab } from '$lib/stores/k3sClusterDetailController.svelte';
	import { useK3sClusterDetailController } from '$lib/stores/k3sClusterDetailController.svelte';
	import Tabs from '$lib/components/ui/Tabs.svelte';
	import { k3sPermissions } from '$lib/stores/k3sPermissions';

	const s = useK3sClusterDetailController();

	const tabs: { value: ActiveTab; label: string; panelId: string }[] = [
		{ value: 'main', get label() { return t('overview.tabs.main'); }, panelId: 'k3s-panel-main' },
		{ value: 'configmaps', get label() { return t('overview.tabs.configmaps'); }, panelId: 'k3s-panel-configmaps' },
		{ value: 'secrets', get label() { return t('overview.tabs.secrets'); }, panelId: 'k3s-panel-secrets' },
		{ value: 'services', get label() { return t('overview.tabs.services'); }, panelId: 'k3s-panel-services' },
		{ value: 'workloads', get label() { return t('overview.tabs.workloads'); }, panelId: 'k3s-panel-workloads' },
		{ value: 'pods', get label() { return t('overview.tabs.pods'); }, panelId: 'k3s-panel-pods' },
		{ value: 'stampede', get label() { return t('overview.tabs.stampede'); }, panelId: 'k3s-panel-stampede' },
	];
</script>

<Tabs
	id="k3s-cluster-tabs"
	value={s.activeTab}
	items={tabs.filter((tab) => (tab.value !== 'secrets' && tab.value !== 'configmaps') || $k3sPermissions.workloads)}
	ariaLabel={t('overview.tabs.resources')}
	onchange={(value) => { s.activeTab = value as ActiveTab; }}
	class="mb-5"
/>
