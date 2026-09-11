<script lang="ts">
	import { page } from '$app/stores';
</script>

<div class="min-h-screen bg-surface-canvas flex items-center justify-center">
	<div class="text-center px-4">
		<h1 class="text-6xl font-bold text-ink-3 mb-4">{$page.status}</h1>
		<p class="text-ink-2 mb-8">
			{$page.status === 404 ? '페이지를 찾을 수 없습니다' : '오류가 발생했습니다'}
		</p>
		<a href="/" class="text-action-warm hover:text-action-warm-hover text-sm transition-colors">홈으로 돌아가기</a>
	</div>
</div>
