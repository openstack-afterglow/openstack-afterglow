<script lang="ts">
	import { provideK3sClusterDetailController, type K3sClusterDetailController } from '$lib/stores/k3sClusterDetailController.svelte';
	import type { TableViewState } from '$lib/utils/tableView.svelte';
	import K3sClusterSecretsCard from '../K3sClusterSecretsCard.svelte';

	let { secrets, namespace = 'default', projectId = 'project-a', clusterId = 'cluster-a', visible = true, onTable } = $props<{
		secrets: { name: string; type: string; data: Record<string, string> }[];
		namespace?: string;
		projectId?: string;
		clusterId?: string;
		visible?: boolean;
		onTable?: (table: { search: string; state: TableViewState }) => void;
	}>();
	const table = $state<{ search: string; state: TableViewState }>({ search: '', state: { sort: null, filters: {} } });
	provideK3sClusterDetailController({
		get secrets() { return secrets; },
		get selectedNamespace() { return namespace; },
		get projectId() { return projectId; },
		get cluster() { return { id: clusterId }; },
		cmActioning: null,
		tableState: () => table,
		loadSecrets: async () => {},
	} as unknown as K3sClusterDetailController);
	$effect(() => { onTable?.(table); });
</script>

{#if visible}<K3sClusterSecretsCard />{/if}
