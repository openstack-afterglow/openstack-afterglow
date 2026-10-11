<script lang="ts">
	import PageShell from '$lib/components/ui/PageShell.svelte';
	import { t } from '$lib/i18n/ns/chat-settings';
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

<PageShell class="min-h-full md:flex md:h-full md:min-h-0 md:flex-col">
	<div class="shrink-0">
		<Button href="/dashboard/chat" variant="ghost" size="sm" class="min-h-11">{t('settingsPage.backToChat')}</Button>
	</div>
	<div class="settings-body">
		<ChatSettings initialSection={data.section} />
	</div>
</PageShell>

<style>
	.settings-body {
		width: 100%;
	}
	@media (min-width: 768px) {
		.settings-body {
			display: flex;
			min-height: 0;
			flex: 1;
		}
		.settings-body :global(.settings-page) {
			min-height: 0;
			flex: 1;
		}
	}
</style>
