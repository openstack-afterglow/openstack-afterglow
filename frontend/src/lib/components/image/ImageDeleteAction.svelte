<script lang="ts">
	import { useImageDetailController } from '$lib/stores/imageDetailController.svelte';

	const s = useImageDetailController();
</script>

<div class="pt-2 pb-4">
	<button
		onclick={() => s.deleteImage()}
		disabled={s.deleting}
		class="w-full py-2 text-sm text-red-400 hover:text-red-300 disabled:text-ink-3 border border-red-900 hover:border-red-700 disabled:border-line-2 rounded-lg transition-colors"
	>
		{s.deleting ? '삭제 중...' : '이미지 삭제'}
	</button>
</div>
