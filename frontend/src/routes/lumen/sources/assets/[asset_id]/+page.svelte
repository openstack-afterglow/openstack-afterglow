<script lang="ts">
	import { page } from '$app/stores';
	import ChatSourcePage from '$lib/components/chat/ChatSourcePage.svelte';
</script>

<ChatSourcePage assetId={$page.params.asset_id} />
