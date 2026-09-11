<script lang="ts">
	import { formatNumber } from '$lib/utils/format';
	import type { Overview } from '$lib/types/adminOverview';

	let { overview }: { overview: Overview } = $props();
</script>

<div class="flex flex-col gap-px overflow-hidden rounded-lg border border-line bg-line">
	<a href="/admin/containers" class="flex items-center gap-3 bg-surface-base p-4 transition-colors hover:bg-surface-selected">
		<div class="flex size-8 shrink-0 items-center justify-center text-action-warm">
			<svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4"/></svg>
		</div>
		<div>
			<div class="text-xs font-medium tracking-tight text-ink-2">컨테이너</div>
			<div class="text-[28px] font-bold text-ink-0 leading-none">{formatNumber(overview.containers_count ?? 0)}</div>
		</div>
	</a>
	<a href="/admin/file-storage" class="flex items-center gap-3 bg-surface-base p-4 transition-colors hover:bg-surface-selected">
		<div class="flex size-8 shrink-0 items-center justify-center text-teal-400">
			<svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z"/></svg>
		</div>
		<div>
			<div class="text-xs font-medium tracking-tight text-ink-2">파일 스토리지</div>
			<div class="text-[28px] font-bold text-ink-0 leading-none">{formatNumber(overview.file_storage_count ?? 0)}</div>
		</div>
	</a>
	<a href="/admin/database-instances" class="flex items-center gap-3 bg-surface-base p-4 transition-colors hover:bg-surface-selected">
		<div class="flex size-8 shrink-0 items-center justify-center text-cyan-400">
			<svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 7c0-1.657 3.582-3 8-3s8 1.343 8 3M4 7v5c0 1.657 3.582 3 8 3s8-1.343 8-3V7M4 7c0 1.657 3.582 3 8 3s8-1.343 8-3M4 12v5c0 1.657 3.582 3 8 3s8-1.343 8-3v-5"/></svg>
		</div>
		<div>
			<div class="text-xs font-medium tracking-tight text-ink-2">Database</div>
			<div class="text-[28px] font-bold text-ink-0 leading-none">{formatNumber(overview.database_instances_count ?? 0)}</div>
		</div>
	</a>
	<a href="/admin/object-storage" class="flex items-center gap-3 bg-surface-base p-4 transition-colors hover:bg-surface-selected">
		<div class="flex size-8 shrink-0 items-center justify-center text-indigo-400">
			<svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 15a4 4 0 004 4h9a5 5 0 10-.1-9.999 5.002 5.002 0 10-9.78 2.096A4.001 4.001 0 003 15z"/></svg>
		</div>
		<div>
			<div class="text-xs font-medium tracking-tight text-ink-2">Object Storage</div>
			<div class="text-[28px] font-bold text-ink-0 leading-none">{formatNumber(overview.object_storage_containers_count ?? 0)}</div>
		</div>
	</a>
</div>
