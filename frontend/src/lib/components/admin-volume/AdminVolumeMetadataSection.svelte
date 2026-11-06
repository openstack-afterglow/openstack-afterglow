<script lang="ts">
	import { useAdminVolumeDetailController } from '$lib/stores/adminVolumeDetailController.svelte';
	import AdminVolumeMetadataCard from '$lib/components/admin/volumes/id/AdminVolumeMetadataCard.svelte';

	const s = useAdminVolumeDetailController();
</script>

<AdminVolumeMetadataCard metadata={s.volume?.metadata ?? {}} />
