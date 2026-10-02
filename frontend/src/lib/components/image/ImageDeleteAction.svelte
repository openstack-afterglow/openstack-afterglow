<script lang="ts">
	import { t } from '$lib/i18n/ns/images-keys';
	import { useImageDetailController } from '$lib/stores/imageDetailController.svelte';

	const s = useImageDetailController();
</script>

<div class="pt-2 pb-4">
	<button
		onclick={() => s.deleteImage()}
		disabled={s.deleting}
		class="w-full py-2 text-sm text-red-400 hover:text-red-300 disabled:text-ink-3 border border-red-900 hover:border-red-700 disabled:border-line-2 rounded-lg transition-colors"
	>
		{s.deleting ? t('deleteAction.deleting') : t('deleteAction.delete')}
	</button>
</div>
