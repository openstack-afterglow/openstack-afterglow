<script lang="ts">
	import ChatPanel from '$lib/components/chat/ChatPanel.svelte';

	let {
		data
	}: {
		data: { workspaceId: number | null };
	} = $props();
</script>

<ChatPanel initialWorkspaceId={data.workspaceId} />
