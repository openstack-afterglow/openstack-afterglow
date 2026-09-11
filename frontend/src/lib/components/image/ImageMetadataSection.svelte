<script lang="ts">
	import { useImageDetailController } from '$lib/stores/imageDetailController.svelte';
	import { formatIsoDateTime } from '$lib/utils/format';

	const s = useImageDetailController();
</script>

<div class="bg-surface-base border border-line rounded-lg p-5">
	<h3 class="text-xs font-semibold text-ink-2 uppercase tracking-wide mb-3">메타데이터</h3>
	<dl class="grid grid-cols-1 @3xl/panel:grid-cols-2 gap-x-6 gap-y-3">
		<div>
			<dt class="text-xs text-ink-3 mb-0.5">등록일</dt>
			<dd class="text-sm text-ink-2">{formatIsoDateTime(s.image!.created_at)}</dd>
		</div>
		<div>
			<dt class="text-xs text-ink-3 mb-0.5">수정일</dt>
			<dd class="text-sm text-ink-2">{formatIsoDateTime(s.image!.updated_at)}</dd>
		</div>
		{#if s.image!.checksum}
			<div class="col-span-2">
				<dt class="text-xs text-ink-3 mb-0.5">체크섬 (MD5)</dt>
				<dd class="text-xs text-ink-2 font-mono break-all">{s.image!.checksum}</dd>
			</div>
		{/if}
	</dl>
</div>
