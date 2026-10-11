<script lang="ts">
	import PageShell from '$lib/components/ui/PageShell.svelte';
	import ChatPanel from '$lib/components/chat/ChatPanel.svelte';

	let { data }: { data: { workspaceId: number } } = $props();
</script>

<PageShell class="app-workspace-height flex min-h-0 flex-col">
	<ChatPanel projectRoute={data.workspaceId} />
</PageShell>
