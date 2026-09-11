<script lang="ts">
	import LoadingSkeleton from '$lib/components/LoadingSkeleton.svelte';
	import { fmtTime } from './serviceColumns.js';

	interface NetworkAgent {
		id: string;
		binary: string;
		host: string;
		agent_type: string;
		availability_zone: string | null;
		alive: boolean | null;
		admin_state_up: boolean;
		updated_at: string | null;
	}

	let {
		agents,
		loading,
		emptyMessage,
	}: {
		agents: NetworkAgent[];
		loading: boolean;
		emptyMessage: string;
	} = $props();
</script>

{#if loading}
	<LoadingSkeleton variant="table" rows={8} />
{:else if agents.length === 0}
	<div class="text-ink-3 text-sm py-8 text-center">{emptyMessage}</div>
{:else}
	<div class="overflow-x-auto">
		<table class="w-full text-sm">
			<thead>
				<tr class="border-b border-line text-ink-2 text-xs uppercase tracking-wide">
					<th class="text-left py-2 pr-4">Agent Type</th>
					<th class="text-left py-2 pr-4">Binary</th>
					<th class="text-left py-2 pr-4">Host</th>
					<th class="text-left py-2 pr-4">Zone</th>
					<th class="text-left py-2 pr-4">Alive</th>
					<th class="text-left py-2 pr-4">Admin State</th>
					<th class="text-left py-2">Updated</th>
				</tr>
			</thead>
			<tbody>
				{#each agents as a (a.id)}
					<tr class="border-b border-line/50 text-xs hover:bg-surface-sunken/30">
						<td class="py-2 pr-4 text-ink-0">{a.agent_type}</td>
						<td class="py-2 pr-4 text-ink-2 font-mono">{a.binary}</td>
						<td class="py-2 pr-4 text-ink-2">{a.host}</td>
						<td class="py-2 pr-4 text-ink-2">{a.availability_zone || '-'}</td>
						<td class="py-2 pr-4"><span class="px-1.5 py-0.5 rounded text-xs font-medium {a.alive ? 'bg-green-900/30 text-green-400' : 'bg-red-900/30 text-red-400'}">{a.alive ? 'alive' : 'down'}</span></td>
						<td class="py-2 pr-4"><span class="px-1.5 py-0.5 rounded text-xs font-medium {a.admin_state_up ? 'bg-green-900/30 text-green-400' : 'bg-red-900/30 text-red-400'}">{a.admin_state_up ? 'UP' : 'DOWN'}</span></td>
						<td class="py-2 text-ink-3">{fmtTime(a.updated_at)}</td>
					</tr>
				{/each}
			</tbody>
		</table>
	</div>
{/if}
