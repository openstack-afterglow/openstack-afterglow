<script lang="ts">
	import LoadingSkeleton from '$lib/components/LoadingSkeleton.svelte';
	import type { ServiceColumn } from './serviceColumns.js';
	import { fmtTime } from './serviceColumns.js';

	interface Service {
		id: string;
		binary: string;
		host: string;
		status: string;
		state: string;
		zone: string;
		updated_at: string | null;
		disabled_reason: string | null;
	}

	let {
		services,
		columns,
		loading,
		emptyMessage,
	}: {
		services: Service[];
		columns: ServiceColumn[];
		loading: boolean;
		emptyMessage: string;
	} = $props();
</script>

{#if loading}
	<LoadingSkeleton variant="table" rows={8} />
{:else if services.length === 0}
	<div class="text-ink-3 text-sm py-8 text-center">{emptyMessage}</div>
{:else}
	<div class="overflow-x-auto">
		<table class="w-full text-sm">
			<thead>
				<tr class="border-b border-line text-ink-2 text-xs uppercase tracking-wide">
					{#each columns as col, i}
						<th class="text-left py-2 {i < columns.length - 1 ? 'pr-4' : ''}">{col.label}</th>
					{/each}
				</tr>
			</thead>
			<tbody>
				{#each services as s (s.id || s.binary + s.host)}
					<tr class="border-b border-line/50 text-xs hover:bg-surface-sunken/30">
						{#each columns as col, i}
							<td class="py-2 {i < columns.length - 1 ? 'pr-4' : ''}">
								{#if col.type === 'binary'}
									<span class="text-ink-0 font-mono">{s.binary}</span>
								{:else if col.type === 'host'}
									<span class="text-ink-2">{s.host}</span>
								{:else if col.type === 'zone'}
									<span class="text-ink-2">{s.zone}</span>
								{:else if col.type === 'status'}
									<span class="px-1.5 py-0.5 rounded text-xs font-medium {(col.mode === 'strict' ? s.status === 'enabled' : s.status === 'enabled' || s.status === 'up') ? 'bg-green-900/30 text-green-400' : 'bg-red-900/30 text-red-400'}">{s.status}</span>
								{:else if col.type === 'state'}
									<span class="px-1.5 py-0.5 rounded text-xs font-medium {s.state === 'up' ? 'bg-green-900/30 text-green-400' : 'bg-red-900/30 text-red-400'}">{s.state}</span>
								{:else if col.type === 'disabledReason'}
									<span class="text-ink-3">{s.disabled_reason || '-'}</span>
								{:else if col.type === 'updated'}
									<span class="text-ink-3">{fmtTime(s.updated_at)}</span>
								{/if}
							</td>
						{/each}
					</tr>
				{/each}
			</tbody>
		</table>
	</div>
{/if}
