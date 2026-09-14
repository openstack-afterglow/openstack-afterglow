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

<div class="settings-workspace">
	<div class="settings-return">
		<Button href="/dashboard/chat" variant="ghost" size="sm" class="min-h-11">채팅으로 돌아가기</Button>
	</div>
	<div class="settings-body">
		<ChatSettings initialSection={data.section} />
	</div>
</div>

<style>
	.settings-workspace {
		width: 100%;
		min-height: 100%;
	}
	.settings-body {
		width: 100%;
	}
	.settings-return {
		width: min(100%, 72rem);
		margin: 0 auto;
		padding: 1rem 1rem 0;
	}
	@media (min-width: 768px) {
		.settings-workspace {
			display: flex;
			height: 100%;
			min-height: 0;
			flex-direction: column;
		}
		.settings-body {
			display: flex;
			min-height: 0;
			flex: 1;
		}
		.settings-body :global(.settings-page) {
			min-height: 0;
			flex: 1;
		}
		.settings-return {
			padding-inline: 1.5rem;
		}
	}
</style>
