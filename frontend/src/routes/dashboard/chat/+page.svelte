<script lang="ts">
	import ChatPanel from '$lib/components/chat/ChatPanel.svelte';

	let {
		data
	}: {
		data: { workspaceId: number | null };
	} = $props();
</script>

<div class="app-workspace-height flex min-h-0 min-w-0 w-full flex-col">
	<ChatPanel initialWorkspaceId={data.workspaceId} />
</div>
