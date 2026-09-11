<script lang="ts">
	import { useContainerDetailController } from '$lib/stores/containerDetailController.svelte';

	const s = useContainerDetailController();

	const statusColor: Record<string, string> = {
		Running:  'text-green-400 bg-green-900/30',
		Stopped:  'text-ink-2 bg-surface-sunken',
		Created:  'text-action-warm bg-surface-selected/30',
		Error:    'text-red-400 bg-red-900/30',
		Deleting: 'text-orange-400 bg-orange-900/30',
	};
</script>

<div class="flex items-center justify-between">
	<span class="px-2 py-0.5 rounded text-xs font-medium {statusColor[s.container?.status ?? ''] ?? 'text-ink-2 bg-surface-sunken'}">
		{s.container?.status}
	</span>
	<div class="flex items-center gap-2">
		{#if s.container?.status === 'Running'}
			<button onclick={() => s.handleAction('stop')} disabled={s.actioning}
				class="px-3 py-1 text-xs text-orange-400 border border-orange-800 hover:bg-orange-900/30 rounded-lg transition-colors disabled:opacity-40">
				중지
			</button>
		{:else if s.container?.status === 'Stopped' || s.container?.status === 'Created'}
			<button onclick={() => s.handleAction('start')} disabled={s.actioning}
				class="px-3 py-1 text-xs text-green-400 border border-green-800 hover:bg-green-900/30 rounded-lg transition-colors disabled:opacity-40">
				시작
			</button>
		{/if}
		<button onclick={s.handleDelete} disabled={s.actioning}
			class="px-3 py-1 text-xs text-red-400 border border-red-800 hover:bg-red-900/30 rounded-lg transition-colors disabled:opacity-40">
			삭제
		</button>
	</div>
</div>

{#if s.actionError}
	<div class="text-red-400 text-xs">{s.actionError}</div>
{/if}
