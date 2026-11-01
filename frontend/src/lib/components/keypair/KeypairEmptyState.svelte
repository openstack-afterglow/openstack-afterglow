<script lang="ts">
 import AssetGlyph from '$lib/components/ui/AssetGlyph.svelte';
	import { t } from '$lib/i18n/ns/images-keys';
	let { onCreate }: { onCreate: () => void } = $props();
</script>

<div class="text-center py-20 text-ink-2">
	<div class="mb-4"><AssetGlyph variant="locked" /></div>
	<p class="text-lg">{t('keypairEmpty.title')}</p>
</div>
