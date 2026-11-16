<script lang="ts">
	import UsageScheduleSection from '../instance/UsageScheduleSection.svelte';
	import { createInstanceUsageController } from '$lib/stores/instanceUsageController.svelte';

	// Mirrors the instance detail: it owns the controller and renders the section in its dialog.
	let { instanceId, projectId, adminMode = false, canWrite = false, waygateLocked = false, onUpdated }: {
		instanceId: string;
		projectId: string | undefined;
		adminMode?: boolean;
		canWrite?: boolean;
		waygateLocked?: boolean;
		onUpdated?: () => void;
	} = $props();
	const controller = createInstanceUsageController({
		instanceId: () => instanceId, projectId: () => projectId, adminMode: () => adminMode,
		canWrite: () => canWrite, extensionOnly: () => waygateLocked, onUpdated: () => onUpdated?.(),
	});
</script>

<UsageScheduleSection {controller} {canWrite} {waygateLocked} />
