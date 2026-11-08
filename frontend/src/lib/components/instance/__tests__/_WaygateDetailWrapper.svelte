<script lang="ts">
	import InstanceHeader from '../InstanceHeader.svelte';
	import NetworkSection from '../NetworkSection.svelte';
	import VolumesSection from '../VolumesSection.svelte';
	import StorageAttachmentsSection from '../StorageAttachmentsSection.svelte';
	import { createInstanceDetailController, provideInstanceDetailController } from '$lib/stores/instanceDetailController.svelte';

	let { adminMode = false }: { adminMode?: boolean } = $props();
	const controller = createInstanceDetailController({
		instanceId: () => 'vm',
		effectiveProjectId: () => 'project',
		adminMode: () => adminMode,
		onDelete: () => undefined,
	});
	provideInstanceDetailController(controller);
	$effect(() => { void controller.fetchInstance('vm'); });
</script>

{#if controller.instance}
	<InstanceHeader
		adminProjectId={adminMode ? 'project' : null}
		canMutate={true}
		onOpenMigrateModal={() => undefined}
		onOpenPasswordModal={() => undefined}
		onOpenResizeModal={() => undefined}
		onOpenEvacuateModal={() => undefined}
	/>
	<NetworkSection />
	<VolumesSection />
	<StorageAttachmentsSection />
{/if}
