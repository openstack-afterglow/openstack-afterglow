<script lang="ts">
	import NetworkSection from '../NetworkSection.svelte';
	import { createInstanceDetailController, provideInstanceDetailController } from '$lib/stores/instanceDetailController.svelte';
	import type { InstanceDetailController } from '$lib/stores/instanceDetailController.svelte';

	let { source, onReady }: {
		source: { id: string; projectId: string };
		onReady?: (controller: InstanceDetailController) => void;
	} = $props();
	const controller = createInstanceDetailController({
		instanceId: () => source.id,
		effectiveProjectId: () => source.projectId,
		adminMode: () => false,
		onDelete: () => undefined,
	});
	provideInstanceDetailController(controller);
	$effect(() => {
		onReady?.(controller);
		void controller.fetchInstance(source.id);
	});
</script>

<NetworkSection />
