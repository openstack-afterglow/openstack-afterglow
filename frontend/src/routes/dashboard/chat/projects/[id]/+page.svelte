<script lang="ts">
	import ChatPanel from '$lib/components/chat/ChatPanel.svelte';

	let { data }: { data: { workspaceId: number } } = $props();
</script>

<div class="app-workspace-height flex min-h-0 min-w-0 w-full flex-col">
	<ChatPanel projectRoute={data.workspaceId} />
</div>
