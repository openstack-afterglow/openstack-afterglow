<script lang="ts">
	import VolumesSection from '../VolumesSection.svelte';
	import { provideInstanceDetailController } from '$lib/stores/instanceDetailController.svelte';
	import type { InstanceDetailController } from '$lib/stores/instanceDetailController.svelte';
	let { source, refresh }: { source: InstanceDetailController; refresh: InstanceDetailController['fetchInstance'] } = $props();
	provideInstanceDetailController({
		get instance() { return source.instance; },
		get instanceId() { return source.instanceId; },
		get effectiveProjectId() { return source.effectiveProjectId; },
		get adminMode() { return source.adminMode; },
		get volumes() { return source.volumes; },
		get availableVolumes() { return source.availableVolumes; },
		get actioning() { return source.actioning; },
		fetchInstance: (...args: Parameters<InstanceDetailController['fetchInstance']>) => refresh(...args),
	} as InstanceDetailController);
</script>

<VolumesSection />
