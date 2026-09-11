<script lang="ts">
	import type { HTMLAttributes } from 'svelte/elements';

	interface Props extends HTMLAttributes<HTMLDivElement> {
		/** Number of skeleton rows to display */
		rows?: number;
		/** Type of skeleton to show */
		variant?: 'table' | 'card' | 'list' | 'detail';
	}

	let { rows = 5, variant = 'table', ...restProps }: Props = $props();
</script>

{#if variant === 'table'}
	<div class="overflow-x-auto" {...restProps}>
		<table class="w-full text-sm">
			<thead>
				<tr class="border-b border-line text-ink-2 text-xs uppercase tracking-wide">
					<th class="text-left py-3 pr-6"><div class="h-3 w-20 bg-surface-sunken rounded animate-pulse"></div></th>
					<th class="text-left py-3 pr-6"><div class="h-3 w-12 bg-surface-sunken rounded animate-pulse"></div></th>
					<th class="text-left py-3 pr-6"><div class="h-3 w-16 bg-surface-sunken rounded animate-pulse"></div></th>
					<th class="text-left py-3 pr-6"><div class="h-3 w-12 bg-surface-sunken rounded animate-pulse"></div></th>
					<th class="text-left py-3 pr-6"><div class="h-3 w-24 bg-surface-sunken rounded animate-pulse"></div></th>
					<th class="text-left py-3 pr-6"><div class="h-3 w-12 bg-surface-sunken rounded animate-pulse"></div></th>
					<th class="text-right py-3"><div class="h-3 w-16 bg-surface-sunken rounded animate-pulse ml-auto"></div></th>
				</tr>
			</thead>
			<tbody>
				{#each Array(rows) as _, i}
					<tr class="border-b border-line/50">
						<td class="py-3 pr-6"><div class="h-4 w-32 bg-surface-sunken rounded animate-pulse"></div></td>
						<td class="py-3 pr-6"><div class="h-5 w-14 bg-surface-sunken rounded animate-pulse"></div></td>
						<td class="py-3 pr-6"><div class="h-4 w-24 bg-surface-sunken rounded animate-pulse"></div></td>
						<td class="py-3 pr-6"><div class="h-4 w-28 bg-surface-sunken rounded animate-pulse font-mono"></div></td>
						<td class="py-3 pr-6"><div class="flex gap-1"><div class="h-5 w-16 bg-surface-sunken rounded animate-pulse"></div><div class="h-5 w-20 bg-surface-sunken rounded animate-pulse"></div></div></td>
						<td class="py-3 pr-6"><div class="h-4 w-16 bg-surface-sunken rounded animate-pulse"></div></td>
						<td class="py-3"><div class="flex justify-end gap-2"><div class="h-6 w-12 bg-surface-sunken rounded animate-pulse"></div><div class="h-6 w-12 bg-surface-sunken rounded animate-pulse"></div></div></td>
					</tr>
				{/each}
			</tbody>
		</table>
	</div>
{:else if variant === 'card'}
	<div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4" {...restProps}>
		{#each Array(rows) as _, i}
			<div class="bg-surface-base rounded-xl border border-line p-4">
				<div class="h-5 w-3/4 bg-surface-sunken rounded animate-pulse mb-3"></div>
				<div class="h-4 w-1/2 bg-surface-sunken rounded animate-pulse mb-2"></div>
				<div class="h-4 w-2/3 bg-surface-sunken rounded animate-pulse mb-4"></div>
				<div class="flex gap-2">
					<div class="h-8 w-20 bg-surface-sunken rounded animate-pulse"></div>
					<div class="h-8 w-20 bg-surface-sunken rounded animate-pulse"></div>
				</div>
			</div>
		{/each}
	</div>
{:else if variant === 'list'}
	<div class="space-y-3" {...restProps}>
		{#each Array(rows) as _, i}
			<div class="flex items-center gap-4 p-3 bg-surface-base rounded-lg border border-line">
				<div class="h-10 w-10 bg-surface-sunken rounded animate-pulse shrink-0"></div>
				<div class="flex-1">
					<div class="h-4 w-1/3 bg-surface-sunken rounded animate-pulse mb-2"></div>
					<div class="h-3 w-1/2 bg-surface-sunken rounded animate-pulse"></div>
				</div>
				<div class="h-6 w-16 bg-surface-sunken rounded animate-pulse"></div>
			</div>
		{/each}
	</div>
{:else if variant === 'detail'}
	<div class="space-y-4" {...restProps}>
		<div class="bg-surface-base border border-line rounded-lg p-6">
			<div class="h-4 w-24 bg-surface-sunken rounded animate-pulse mb-4"></div>
			<div class="grid grid-cols-2 gap-x-8 gap-y-4">
				{#each Array(rows) as _, i}
					<div>
						<div class="h-3 w-16 bg-surface-sunken rounded animate-pulse mb-1.5"></div>
						<div class="h-4 w-32 bg-surface-sunken rounded animate-pulse"></div>
					</div>
				{/each}
			</div>
		</div>
	</div>
{/if}