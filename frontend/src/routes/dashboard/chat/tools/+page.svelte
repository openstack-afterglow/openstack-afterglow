<script lang="ts">
	import { t } from '$lib/i18n/ns/chat-settings';
	import { SectionHeader } from '$lib/components/ui';
	import ChatExtensionsManager from '$lib/components/chat/ChatExtensionsManager.svelte';
</script>

<div class="space-y-4 p-4 md:p-8 max-w-4xl">
	<div class="flex items-center justify-between gap-3">
		<SectionHeader title={t('toolsPage.title')} meta={t('toolsPage.description')} />
		<a href="/dashboard/chat" class="shrink-0 text-sm text-[var(--color-ink-3)] transition-colors hover:text-[var(--color-ink-1)]">{t('toolsPage.backToChat')}</a>
	</div>
	<ChatExtensionsManager base="/api/v1/chat" />
</div>
