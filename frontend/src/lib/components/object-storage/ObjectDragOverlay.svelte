<script lang="ts">
	import { t } from '$lib/i18n/ns/object-storage';
	import { useObjectBrowser } from '$lib/stores/objectBrowser.svelte';
	import { ActivityIndicator } from '$lib/components/ui';
	const s = useObjectBrowser();
</script>

{#if s.dragActive}
	<div class="motion-fade fixed inset-0 z-50 pointer-events-none flex items-center justify-center bg-surface-scrim/60 backdrop-blur-sm border-4 border-dashed border-accent">
		<div class="motion-pop text-center px-4">
			<ActivityIndicator variant="upload" size="lg" label={t('views.dragOverlay.dropFiles')} />
			<p class="text-ink-0 font-semibold text-xl mt-3">{t('views.dragOverlay.uploadTo', { path: `${s.containerName}${s.prefix ? ` / ${s.prefix}` : ''}` })}</p>
		</div>
	</div>
{/if}
