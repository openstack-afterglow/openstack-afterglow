<script lang="ts">
	import ChatSettings, {
		type ChatSettingsSection
	} from '$lib/components/chat/ChatSettings.svelte';

	let {
		data
	}: {
		data: { section: ChatSettingsSection };
	} = $props();
</script>

<ChatSettings initialSection={data.section} />
