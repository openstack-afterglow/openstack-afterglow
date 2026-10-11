<script lang="ts">
	import PageShell from '$lib/components/ui/PageShell.svelte';
	import ChatPanel from '$lib/components/chat/ChatPanel.svelte';
</script>

<PageShell class="app-workspace-height flex min-h-0 flex-col">
	<ChatPanel projectRoute={null} />
</PageShell>
