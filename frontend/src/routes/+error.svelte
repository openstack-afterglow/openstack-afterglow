<script lang="ts">
	import { page } from '$app/stores';
	import { t } from '$lib/i18n/ns/shell';
</script>

<div class="min-h-screen bg-surface-canvas flex items-center justify-center">
	<div class="text-center px-4">
		<h1 class="text-6xl font-bold text-ink-2 mb-4">{$page.status}</h1>
		<p class="text-ink-2 mb-8">
			{$page.status === 404 ? t('error.notFound') : t('error.generic')}
		</p>
		<a href="/" class="text-warm-text hover:text-warm-text-hover text-sm transition-colors">{t('error.home')}</a>
	</div>
</div>
