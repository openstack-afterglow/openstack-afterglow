<script lang="ts">
	import { createInstanceDetailController, provideInstanceDetailController, type InstanceDetailController } from '../instanceDetailController.svelte';
	import InstanceHeader from '$lib/components/instance/InstanceHeader.svelte';
	import RenameModal from '$lib/components/instance/RenameModal.svelte';

	let { source, onReady, onUpdated }: {
		source: { id: string; projectId: string; adminMode: boolean };
		onReady: (controller: InstanceDetailController) => void;
		onUpdated: () => void;
	} = $props();
	const controller = createInstanceDetailController({
		instanceId: () => source.id,
		effectiveProjectId: () => source.projectId,
		adminMode: () => source.adminMode,
		onDelete: () => undefined,
		onUpdated: () => onUpdated(),
	});
	provideInstanceDetailController(controller);
	$effect(() => onReady(controller));
</script>

{#if controller.instance}
	<InstanceHeader adminProjectId={source.adminMode ? source.projectId : null} canMutate={controller.canRename}
		onOpenMigrateModal={() => undefined} onOpenPasswordModal={() => undefined}
		onOpenResizeModal={() => undefined} onOpenEvacuateModal={() => undefined} />
{/if}
{#if controller.renameOpen && controller.canRename}<RenameModal />{/if}
