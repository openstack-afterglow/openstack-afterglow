<script lang="ts">
 import AssetGlyph from '$lib/components/ui/AssetGlyph.svelte';
	import { t } from '$lib/i18n/ns/file-storage';
	let { onCreate }: { onCreate: () => void } = $props();
</script>

<div class="text-center py-20 text-ink-2">
	<div class="mb-4"><AssetGlyph variant="empty" /></div>
	<p class="text-lg">{t('snapshotEmpty.title')}</p>
	<button onclick={onCreate} class="text-warm-text hover:text-warm-text-hover text-sm mt-2 inline-block">
		{t('snapshotEmpty.create')}
	</button>
</div>
