<script lang="ts">
	import { t } from '$lib/i18n/ns/chat-settings';
	import { PageShell } from '$lib/components/ui';
	import ChatExtensionsManager from '$lib/components/chat/ChatExtensionsManager.svelte';
</script>

<PageShell class="space-y-4">
	<div class="flex flex-wrap items-center justify-between gap-3">
		<div class="min-w-0">
			<h1 class="text-2xl font-semibold text-ink-0">{t('toolsPage.title')}</h1>
			<p class="mt-1 text-sm text-ink-2">{t('toolsPage.description')}</p>
		</div>
		<a href="/dashboard/chat" class="shrink-0 text-sm text-[var(--color-ink-2)] transition-colors hover:text-[var(--color-ink-1)]">{t('toolsPage.backToChat')}</a>
	</div>
	<ChatExtensionsManager base="/api/v1/chat" />
</PageShell>
