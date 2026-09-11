<script lang="ts">
	import { useImageDetailController } from '$lib/stores/imageDetailController.svelte';

	const s = useImageDetailController();
</script>

<div class="bg-surface-base border border-line rounded-lg p-5">
	<h3 class="text-xs font-semibold text-ink-2 uppercase tracking-wide mb-3">기본 정보</h3>
	<dl class="grid grid-cols-1 @3xl/panel:grid-cols-2 gap-x-6 gap-y-3">
		<div class="col-span-2">
			<dt class="text-xs text-ink-3 mb-0.5">ID</dt>
			<dd class="text-xs text-ink-2 font-mono break-all">{s.image!.id}</dd>
		</div>
		<div>
			<dt class="text-xs text-ink-3 mb-0.5">OS 배포판</dt>
			<dd class="text-sm text-ink-2">{s.image!.os_distro ?? '-'}</dd>
		</div>
		<div>
			<dt class="text-xs text-ink-3 mb-0.5">디스크 포맷</dt>
			<dd class="text-sm text-ink-2">{s.image!.disk_format ?? '-'}</dd>
		</div>
		<div>
			<dt class="text-xs text-ink-3 mb-0.5">컨테이너 포맷</dt>
			<dd class="text-sm text-ink-2">{s.image!.container_format ?? '-'}</dd>
		</div>
		<div>
			<dt class="text-xs text-ink-3 mb-0.5">보호됨</dt>
			<dd class="text-sm text-ink-2">{s.image!.protected ? '예' : '아니요'}</dd>
		</div>
		{#if s.image!.tags.length > 0}
			<div class="col-span-2">
				<dt class="text-xs text-ink-3 mb-0.5">태그</dt>
				<dd class="text-sm text-ink-2">{s.image!.tags.join(', ')}</dd>
			</div>
		{/if}
		{#if s.isAdmin}
			<div class="col-span-2">
				<dt class="text-xs text-ink-3 mb-0.5">소유자 (Project ID)</dt>
				<dd class="text-xs text-ink-2 font-mono break-all">{s.image!.owner ?? '-'}</dd>
			</div>
		{/if}
		{#if s.image!.os_hash_algo}
			<div class="col-span-2">
				<dt class="text-xs text-ink-3 mb-0.5">해시 ({s.image!.os_hash_algo})</dt>
				<dd class="text-xs text-ink-2 font-mono break-all">{s.image!.os_hash_value ?? '-'}</dd>
			</div>
		{/if}
		{#if s.isAdmin && s.image!.direct_url}
			<div class="col-span-2">
				<dt class="text-xs text-ink-3 mb-0.5">저장 위치</dt>
				<dd class="text-xs text-ink-2 font-mono break-all">{s.image!.direct_url}</dd>
			</div>
		{/if}
	</dl>
</div>
