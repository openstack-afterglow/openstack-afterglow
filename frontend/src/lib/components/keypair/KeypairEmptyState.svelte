<script lang="ts">
	import { t } from '$lib/i18n/ns/images-keys';
	let { onCreate }: { onCreate: () => void } = $props();
</script>

<div class="text-center py-20 text-ink-2">
	<div class="text-5xl mb-4">{t('keypairEmpty.icon')}</div>
	<p class="text-lg">{t('keypairEmpty.title')}</p>
</div>
