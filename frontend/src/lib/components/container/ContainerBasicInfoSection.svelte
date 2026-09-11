<script lang="ts">
	import { useContainerDetailController } from '$lib/stores/containerDetailController.svelte';

	const s = useContainerDetailController();
</script>

<div class="bg-surface-base border border-line rounded-xl p-4">
	<h3 class="text-xs text-ink-3 uppercase tracking-wide mb-3">기본 정보</h3>
	<dl class="space-y-2 text-xs">
		<div class="flex justify-between gap-4">
			<dt class="text-ink-2 flex-shrink-0">이미지</dt>
			<dd class="text-ink-2 font-mono text-right break-all">{s.container?.image ?? '-'}</dd>
		</div>
		{#if s.container?.command}
			<div class="flex justify-between gap-4">
				<dt class="text-ink-2 flex-shrink-0">명령</dt>
				<dd class="text-ink-2 font-mono text-right break-all">{s.container.command}</dd>
			</div>
		{/if}
		<div class="flex justify-between">
			<dt class="text-ink-2">CPU</dt>
			<dd class="text-ink-2">{s.container?.cpu ?? '-'}</dd>
		</div>
		<div class="flex justify-between">
			<dt class="text-ink-2">메모리</dt>
			<dd class="text-ink-2">{s.container?.memory ? `${s.container.memory} MB` : '-'}</dd>
		</div>
		<div class="flex justify-between">
			<dt class="text-ink-2">호스트</dt>
			<dd class="text-ink-2 font-mono">{s.container?.host ?? '-'}</dd>
		</div>
		<div class="flex justify-between">
			<dt class="text-ink-2">생성일</dt>
			<dd class="text-ink-2">{s.container?.created_at?.slice(0, 19).replace('T', ' ') ?? '-'}</dd>
		</div>
		{#if s.container?.status_reason}
			<div class="flex justify-between gap-4">
				<dt class="text-ink-2 flex-shrink-0">상태 메시지</dt>
				<dd class="text-ink-2 text-right break-all">{s.container.status_reason}</dd>
			</div>
		{/if}
	</dl>
</div>
