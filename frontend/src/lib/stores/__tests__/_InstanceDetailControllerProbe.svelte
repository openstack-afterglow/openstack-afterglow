<script lang="ts">
	import { createInstanceDetailController } from '../instanceDetailController.svelte';

	let {
		source,
		onReady,
	}: {
		source: { id: string; projectId: string; adminMode?: boolean };
		onReady: (controller: ReturnType<typeof createInstanceDetailController>) => void;
	} = $props();

	const controller = createInstanceDetailController({
		instanceId: () => source.id,
		effectiveProjectId: () => source.projectId,
		adminMode: () => source.adminMode ?? false,
		onDelete: () => undefined,
	});

	$effect(() => {
		onReady(controller);
	});
</script>

<div data-testid="detail-loading">{controller.loading ? 'loading' : 'ready'}</div>
<div data-testid="detail-instance">{controller.instance?.name ?? ''}</div>
<div data-testid="detail-network-count">{controller.availableNetworks.length}</div>
<div data-testid="detail-floating-count">{controller.floatingIps.length}</div>
<div data-testid="detail-volume-count">{controller.availableVolumes.length}</div>
