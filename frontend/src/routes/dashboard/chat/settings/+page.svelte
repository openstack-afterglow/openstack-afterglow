<script lang="ts">
	import ChatSettings, {
		type ChatSettingsSection
	} from '$lib/components/chat/ChatSettings.svelte';
	import Button from '$lib/components/ui/Button.svelte';

	let {
		data
	}: {
		data: { section: ChatSettingsSection };
	} = $props();
</script>

<div class="settings-return">
	<Button href="/dashboard/chat" variant="ghost" size="sm" class="min-h-11">채팅으로 돌아가기</Button>
</div>
<ChatSettings initialSection={data.section} />

<style>
	.settings-return {
		width: min(100%, 72rem);
		margin: 0 auto;
		padding: 1rem 1rem 0;
	}
	@media (min-width: 768px) {
		.settings-return {
			padding-inline: 1.5rem;
		}
	}
</style>
