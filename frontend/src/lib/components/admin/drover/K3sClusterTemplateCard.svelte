<script lang="ts">
	import type { K3sClusterTemplate } from '$lib/types/k3s';

	let {
		template,
		onEdit,
		onDelete,
	}: {
		template: K3sClusterTemplate;
		onEdit: (t: K3sClusterTemplate) => void;
		onDelete: (t: K3sClusterTemplate) => void;
	} = $props();
</script>

<div class="bg-surface-base border border-line-2 rounded-xl p-4 flex flex-col gap-3">
	<div class="flex items-start justify-between gap-2">
		<div class="min-w-0">
			<div class="flex items-center gap-2">
				<span class="font-semibold text-ink-0 text-sm truncate">{template.name}</span>
				{#if !template.public_visible}
					<span class="px-1.5 py-0.5 bg-surface-selected text-ink-2 text-xs rounded">비공개</span>
				{/if}
			</div>
			{#if template.description}
				<p class="text-xs text-ink-2 mt-0.5 truncate">{template.description}</p>
			{/if}
		</div>
		<div class="flex gap-1 shrink-0">
			<button
				onclick={() => onEdit(template)}
				class="px-2 py-1 text-xs text-ink-2 hover:text-ink-0 bg-surface-sunken hover:bg-surface-selected rounded"
			>수정</button>
			<button
				onclick={() => onDelete(template)}
				class="px-2 py-1 text-xs text-red-400 hover:text-red-300 bg-surface-sunken hover:bg-surface-selected rounded"
			>삭제</button>
		</div>
	</div>

	<div class="grid grid-cols-2 gap-2 text-xs">
		<div class="text-ink-3">k3s 버전</div>
		<div class="text-ink-2 font-mono">{template.k3s_version ?? '설정값'}</div>
		<div class="text-ink-3">에이전트 수</div>
		<div class="text-ink-2">{template.default_node_count}대</div>
		<div class="text-ink-3">OS</div>
		<div class="text-ink-2">{template.os_type}</div>
		<div class="text-ink-3">플러그인</div>
		<div class="text-ink-2">
			{#if Object.keys(template.plugins_enabled).length === 0}
				없음
			{:else}
				{Object.entries(template.plugins_enabled).filter(([, v]) => v).map(([k]) => k).join(', ') || '없음'}
			{/if}
		</div>
	</div>
</div>
