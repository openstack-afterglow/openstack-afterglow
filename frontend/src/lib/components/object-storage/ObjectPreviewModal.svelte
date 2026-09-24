<script lang="ts">
	import { useObjectBrowser } from '$lib/stores/objectBrowser.svelte';
	import LoadingSkeleton from '$lib/components/LoadingSkeleton.svelte';
	import { Button, Card, FileIcon, Modal } from '$lib/components/ui';

	const s = useObjectBrowser();
	const label = $derived(s.displayName(s.previewName) || s.previewName);
</script>

<Modal open={s.showPreview} onClose={s.closePreview} ariaLabel={`${label} 미리보기`}>
	<Card surface="modal" padding="none" class="flex max-h-[92vh] w-[min(96vw,72rem)] flex-col">
		<div class="flex items-center gap-3 border-b border-line px-4 py-3">
			<FileIcon name={s.previewName} contentType={s.previewContentType} />
			<h2 class="min-w-0 flex-1 truncate text-sm font-medium text-ink-0" title={s.previewName}>{label}</h2>
			<Button variant="secondary" size="sm" onclick={() => s.downloadObject(s.previewName)}>다운로드</Button>
			<Button variant="ghost" size="icon" ariaLabel="미리보기 닫기" onclick={s.closePreview}>
				<svg class="h-4 w-4" viewBox="0 0 20 20" fill="currentColor">
					<path fill-rule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clip-rule="evenodd"/>
				</svg>
			</Button>
		</div>

		<div class="flex min-h-0 flex-1 items-center justify-center overflow-auto bg-surface-sunken p-4">
			{#if s.loadingPreview}
				<LoadingSkeleton variant="detail" rows={4} />
			{:else if s.previewContentType.startsWith('image/')}
				<img src={s.previewUrl} alt={label} class="max-h-[80vh] max-w-full object-contain" />
			{:else if s.previewContentType === 'application/pdf'}
				<embed src={s.previewUrl} type="application/pdf" class="h-[80vh] w-full rounded" title={label} />
			{:else}
				<pre class="w-full whitespace-pre-wrap break-all text-xs text-ink-1">{s.previewText}</pre>
			{/if}
		</div>
	</Card>
</Modal>
