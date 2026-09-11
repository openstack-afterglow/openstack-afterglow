<script lang="ts">
	import StatusChip from '$lib/components/ui/StatusChip.svelte';
	import type { VolumeItem } from '$lib/types/userDashboard';

	interface Props {
		volumes: (VolumeItem & { project: string })[];
	}

	let { volumes }: Props = $props();

	const PREVIEW_LIMIT = 5;
</script>

<div class="bg-surface-base border border-line rounded-lg p-5">
	<div class="flex items-center gap-2.5 mb-3.5">
		<div class="w-10 h-10 rounded-lg bg-cyan-500/15 border border-cyan-500/30 text-cyan-400 flex items-center justify-center shrink-0">
			<svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
				<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4m0 5c0 2.21-3.582 4-8 4s-8-1.79-8-4" />
			</svg>
		</div>
		<div class="text-ink-0 font-semibold text-sm">블록 볼륨</div>
		<span class="ml-auto text-xs text-ink-3">{volumes.length}개</span>
	</div>
	<div class="flex flex-col">
		{#each volumes.slice(0, PREVIEW_LIMIT) as vol (vol.id)}
			<div class="flex items-center gap-3 py-2.5 border-b border-line last:border-b-0">
				<div class="flex-1 min-w-0">
					<div class="text-ink-0 text-[13px] font-medium truncate">{vol.name || vol.id.slice(0, 8)}</div>
					<div class="text-[11px] text-ink-3 mt-0.5 font-mono truncate">{vol.size} GB · {vol.volume_type || '—'}</div>
				</div>
				<StatusChip status={vol.status} />
			</div>
		{/each}
		{#if volumes.length === 0}
			<div class="text-ink-3 text-xs py-3 text-center">없음</div>
		{:else if volumes.length > PREVIEW_LIMIT}
			<a href="/dashboard/volumes" class="block text-center text-[11px] text-cyan-400 hover:text-cyan-300 transition-colors pt-2.5">
				+{volumes.length - PREVIEW_LIMIT}개 더 보기 →
			</a>
		{/if}
	</div>
</div>
