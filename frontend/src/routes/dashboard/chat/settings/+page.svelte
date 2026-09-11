<script lang="ts">
	import ChatPanel from '$lib/components/chat/ChatPanel.svelte';
	import type { ChatSettingsSection } from '$lib/components/chat/ChatSettingsOverlay.svelte';

	let {
		data
	}: {
		data: { section: ChatSettingsSection };
	} = $props();
</script>

<ChatPanel initialSettingsSection={data.section} />
