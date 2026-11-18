<script module lang="ts">
	export interface ConnectionColumn<Row> {
		key: string;
		label: string;
		cell: import('svelte').Snippet<[Row]>;
	}
</script>

<script lang="ts" generics="Row">
	import type { Snippet } from 'svelte';
	import CompactResourceCard from '$lib/components/ui/CompactResourceCard.svelte';
	import ResponsiveTable from '$lib/components/ui/ResponsiveTable.svelte';
	import TableShell from '$lib/components/ui/TableShell.svelte';
	let { label, rows, keyOf, columns, name, actionsLabel, actions, details, expanded }: {
		label: string; rows: Row[]; keyOf: (row: Row) => string | number;
		columns: ConnectionColumn<Row>[]; name: Snippet<[Row]>;
		actionsLabel: string; actions: Snippet<[Row]>;
		details?: Snippet<[Row]>; expanded?: (row: Row) => boolean;
	} = $props();
</script>

<ResponsiveTable embedded>
	{#snippet children()}
	<TableShell density="compact">
		<table>
			<caption class="sr-only">{label}</caption>
			<thead><tr>
				{#each columns as column (column.key)}<th scope="col">{column.label}</th>{/each}
				<th scope="col" class="action-cell">{actionsLabel}</th>
			</tr></thead>
			{#each rows as row (keyOf(row))}
				<tbody>
					<tr class="connection-row" data-selected={expanded?.(row) || undefined}>
						{#each columns as column (column.key)}
							{#if column.key === 'name'}<th scope="row" class="name-cell">{@render name(row)}</th>
							{:else}<td class:description-cell={column.key === 'description'}>{@render column.cell(row)}</td>{/if}
						{/each}
						<td class="action-cell">{@render actions(row)}</td>
					</tr>
					{#if details && expanded?.(row)}
						<tr class="connection-detail"><td colspan={columns.length + 1}>{@render details(row)}</td></tr>
					{/if}
				</tbody>
			{/each}
		</table>
	</TableShell>
	{/snippet}
	{#snippet cards()}
		{#each rows as row (keyOf(row))}
			<CompactResourceCard class="connection-row" selected={expanded?.(row)}>
				{@render name(row)}
				<dl>
					{#each columns as column (column.key)}
						{#if column.key !== 'name'}
							<div class:wide={column.key === 'description'}><dt>{column.label}</dt><dd>{@render column.cell(row)}</dd></div>
						{/if}
					{/each}
				</dl>
				{#snippet actions()}{@render rowActions(row)}{/snippet}
			</CompactResourceCard>
		{/each}
	{/snippet}
</ResponsiveTable>

{#snippet rowActions(row: Row)}
	{@render actions(row)}
	{#if details && expanded?.(row)}<div class="card-detail">{@render details(row)}</div>{/if}
{/snippet}

<style>
	:global(.table-shell) tbody:not(:last-child) tr:last-child > * { border-bottom: 1px solid var(--color-line); }
	.name-cell { inline-size: 23%; max-inline-size: 15rem; }
	.description-cell { inline-size: 34%; max-inline-size: 17rem; }
	:global(.table-shell) .action-cell { text-align: end; }
	:global(.table-shell) .connection-detail td { padding-block: 0.75rem; background: var(--color-surface-base); }
	.wide { grid-column: 1 / -1; }
	.card-detail { flex: 1 0 100%; min-inline-size: 0; }
</style>
