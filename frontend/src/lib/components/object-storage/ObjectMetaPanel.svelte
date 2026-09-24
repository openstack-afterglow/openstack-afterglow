<script lang="ts">
	import { useObjectBrowser } from '$lib/stores/objectBrowser.svelte';
	import LoadingSkeleton from '$lib/components/LoadingSkeleton.svelte';

	const s = useObjectBrowser();
</script>

{#if s.loadingMeta}
	<div class="w-72 shrink-0 bg-surface-base border border-line rounded-xl p-4">
		<LoadingSkeleton variant="detail" rows={6} />
	</div>
{:else if s.selectedMeta}
	<div class="w-72 shrink-0 bg-surface-base border border-line rounded-xl p-4 text-sm">
		<div class="flex items-center justify-between mb-3">
			<h3 class="text-ink-0 font-medium text-xs">오브젝트 정보</h3>
			<button onclick={() => s.selectedMeta = null} class="text-ink-2 hover:text-ink-2 text-xs">✕</button>
		</div>
		<div class="space-y-2">
			<div>
				<div class="text-ink-2 text-xs">이름</div>
				<div class="text-ink-0 break-all">{s.selectedMeta.name}</div>
			</div>
			<div>
				<div class="text-ink-2 text-xs">크기</div>
				<div class="text-ink-0">{s.selectedMeta.bytes.toLocaleString()} bytes</div>
			</div>
			<div>
				<div class="text-ink-2 text-xs">Content-Type</div>
				<div class="text-ink-0">{s.selectedMeta.content_type || '-'}</div>
			</div>
			<div>
				<div class="text-ink-2 text-xs">ETag (MD5)</div>
				<div class="text-ink-2 font-mono text-xs break-all">{s.selectedMeta.etag || '-'}</div>
			</div>
			{#if s.selectedMeta.sha256}
				<div>
					<div class="text-ink-2 text-xs">SHA-256</div>
					<div class="text-ink-2 font-mono text-xs break-all">{s.selectedMeta.sha256}</div>
				</div>
			{/if}
			{#if s.selectedMeta.detected_content_type}
				<div>
					<div class="text-ink-2 text-xs">검사된 형식</div>
					<div class="text-ink-0 text-xs">{s.selectedMeta.detected_content_type}</div>
				</div>
			{/if}
			<div>
				<div class="text-ink-2 text-xs">수정일</div>
				<div class="text-ink-0">{s.selectedMeta.last_modified ? s.selectedMeta.last_modified.slice(0, 19) : '-'}</div>
			</div>
			{#if s.selectedMeta.content_encoding}
				<div>
					<div class="text-ink-2 text-xs">Content-Encoding</div>
					<div class="text-ink-0">{s.selectedMeta.content_encoding}</div>
				</div>
			{/if}
		</div>
	</div>
{/if}
