<script lang="ts">
	import type { FileStorage } from '$lib/types/fileStorage';

	let { fileStorage }: { fileStorage: FileStorage } = $props();
</script>

<div class="bg-surface-base border border-line rounded-lg p-6 mb-4">
	<h2 class="text-sm font-semibold text-ink-2 uppercase tracking-wide mb-4">기본 정보</h2>
	<dl class="grid grid-cols-2 gap-x-8 gap-y-3">
		<div>
			<dt class="text-xs text-ink-3 mb-0.5">ID</dt>
			<dd class="text-sm text-ink-2 font-mono">{fileStorage.id}</dd>
		</div>
		<div>
			<dt class="text-xs text-ink-3 mb-0.5">크기</dt>
			<dd class="text-sm text-ink-2">{fileStorage.size} GB</dd>
		</div>
		{#if fileStorage.library_name}
			<div>
				<dt class="text-xs text-ink-3 mb-0.5">라이브러리</dt>
				<dd class="text-sm text-ink-2">{fileStorage.library_name}</dd>
			</div>
			<div>
				<dt class="text-xs text-ink-3 mb-0.5">버전</dt>
				<dd class="text-sm text-ink-2">{fileStorage.library_version ?? '-'}</dd>
			</div>
			{#if fileStorage.built_at}
				<div class="col-span-2">
					<dt class="text-xs text-ink-3 mb-0.5">빌드 일시</dt>
					<dd class="text-sm text-ink-2">{fileStorage.built_at}</dd>
				</div>
			{/if}
		{/if}
	</dl>
</div>
