<script lang="ts">
	import { useAdminVolumeDetailController } from '$lib/stores/adminVolumeDetailController.svelte';
	import AdminVolumeAttachmentTable from '$lib/components/admin/volumes/id/AdminVolumeAttachmentTable.svelte';

	const s = useAdminVolumeDetailController();
</script>

<AdminVolumeAttachmentTable attachments={s.volume?.attachments ?? []} />
