<script lang="ts">
	let { onCreate }: { onCreate: () => void } = $props();
</script>

<div class="text-center py-20 text-ink-3">
	<div class="text-5xl mb-4">💾</div>
	<p class="text-lg">볼륨이 없습니다</p>
	<button onclick={onCreate} class="text-action-warm hover:text-action-warm-hover text-sm mt-2 inline-block bg-transparent">첫 볼륨을 생성하세요 →</button>
</div>
