<script lang="ts">
	import { page } from '$app/stores';
	import ChatSourcePage from '$lib/components/chat/ChatSourcePage.svelte';
</script>

<ChatSourcePage runId={$page.params.run_id} citationId={$page.params.citation_id} />
