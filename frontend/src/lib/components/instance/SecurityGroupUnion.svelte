<script lang="ts">
	import Button from '$lib/components/ui/Button.svelte';
	import TableShell from '$lib/components/ui/TableShell.svelte';
	import { t } from '$lib/i18n/ns/instance';
	import { buildSecurityGroupUnion } from '$lib/utils/securityGroupUnion';
	import type { SecurityGroupUnionGroup, SecurityGroupUnionRow } from '$lib/utils/securityGroupUnion';
	import LoadingState from '$lib/components/ui/LoadingState.svelte';
	import { CompactResourceCard, ResponsiveTable } from '$lib/components/ui';
	import { createTableView, type TableColumn } from '$lib/utils/tableView.svelte';
	import TableColumnHeader from '$lib/components/ui/TableColumnHeader.svelte';
	import TableViewControls from '$lib/components/ui/TableViewControls.svelte';
	import { t as tc } from '$lib/i18n/ns/common';

	interface Props {
		groupIds: readonly string[];
		groups: readonly SecurityGroupUnionGroup[];
		loading?: boolean;
		error?: string;
	}

	let { groupIds, groups, loading = false, error = '' }: Props = $props();
	let union = $derived(buildSecurityGroupUnion(groups, groupIds));
	let inbound = $derived(union.rows.filter((row) => row.direction === 'ingress'));
	let outbound = $derived(union.rows.filter((row) => row.direction === 'egress'));
	let inboundOpen = $state(false);
	let outboundOpen = $state(false);
	const columns = (direction: 'ingress' | 'egress'): TableColumn<SecurityGroupUnionRow>[] => [
		{ key: 'version', label: t('securityGroupUnion.column.ipVersion'), value: row => row.ethertype },
		{ key: 'protocol', label: t('securityGroupUnion.column.protocol'), value: row => row.protocol ?? 'any', format: (_value, row) => row.protocolLabel },
		{ key: 'port', label: t('securityGroupUnion.column.portIcmp'), value: row => `${row.portRangeMin ?? 'any'}:${row.portRangeMax ?? 'any'}`, format: (_value, row) => row.portLabel },
		{ key: 'remote', label: t(direction === 'ingress' ? 'securityGroupUnion.column.source' : 'securityGroupUnion.column.destination'), value: row => `${row.remote.kind}:${row.remote.value}`, format: (_value, row) => row.remoteLabel },
	];
	const inboundView = createTableView({ rows: () => inbound, columns: () => columns('ingress') });
	const outboundView = createTableView({ rows: () => outbound, columns: () => columns('egress') });

	function toggleInbound() { inboundOpen = !inboundOpen; }
	function toggleOutbound() { outboundOpen = !outboundOpen; }
</script>

{#snippet directionTable(view: typeof inboundView, direction: 'ingress' | 'egress', remoteHeading: string, expanded: boolean, onToggle: () => void)}
	<div class="min-w-0 max-w-full space-y-2">
		<h4>
			<Button variant="ghost" size="sm" class="w-full min-h-11" ariaExpanded={expanded} ariaLabel={t(expanded ? 'securityGroupUnion.collapseRules' : 'securityGroupUnion.expandRules', { direction })} onclick={onToggle}>
				<span class="flex w-full items-center justify-between gap-2">
					<span class="text-ink-1">{t(direction === 'ingress' ? 'securityGroupUnion.direction.ingress' : 'securityGroupUnion.direction.egress')}</span>
					<span class="flex items-center gap-1 text-ink-2">
						<span>{t(expanded ? 'securityGroupUnion.collapse' : 'securityGroupUnion.expand')}</span>
						<svg class="size-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
							<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d={expanded ? 'M19 15l-7-7-7 7' : 'M5 9l7 7 7-7'} />
						</svg>
					</span>
				</span>
			</Button>
		</h4>
		{#if expanded}
			<TableViewControls {view} />
			<ResponsiveTable>
				{#snippet cards()}
					{#each view.rows as row (row.key)}
						{#snippet remoteDetails()}<p class="break-all font-mono text-xs">{row.remote.kind === 'group' ? row.remote.value : row.remoteLabel}</p>{/snippet}
						<CompactResourceCard details={row.remote.kind === 'group' ? remoteDetails : undefined}>
							<h5 class="text-sm font-medium">{row.protocolLabel} · {row.portLabel}</h5>
							<dl class="space-y-1 text-xs"><div><dt class="text-ink-2">{t('securityGroupUnion.column.ipVersion')}</dt><dd>{row.ethertype}</dd></div><div><dt class="text-ink-2">{remoteHeading}</dt><dd class="break-all">{row.remoteLabel}</dd></div></dl>
						</CompactResourceCard>
					{:else}<p class="col-span-full text-xs text-ink-2">{(direction === 'ingress' ? inbound : outbound).length ? tc('table.noMatches') : t('securityGroupUnion.emptyDirection', { direction })}</p>{/each}
				{/snippet}
			<TableShell density="compact" class="motion-fade min-w-0 max-w-full">
				<table aria-label={t('securityGroupUnion.rulesLabel', { direction })}>
					<thead>
						<tr>
							<TableColumnHeader {view} columnKey="version" />
							<TableColumnHeader {view} columnKey="protocol" />
							<TableColumnHeader {view} columnKey="port" />
							<TableColumnHeader {view} columnKey="remote" />
						</tr>
					</thead>
					<tbody>
						{#each view.rows as row (row.key)}
							<tr>
								<td>{row.ethertype}</td>
								<td>{row.protocolLabel}</td>
								<td>{row.portLabel}</td>
								<td title={row.remote.kind === 'group' ? row.remote.value : undefined}>{row.remoteLabel}</td>
							</tr>
						{:else}
							<tr><td colspan="4" class="text-ink-2">{(direction === 'ingress' ? inbound : outbound).length ? tc('table.noMatches') : t('securityGroupUnion.emptyDirection', { direction })}</td></tr>
						{/each}
					</tbody>
				</table>
			</TableShell>
			</ResponsiveTable>
		{/if}
	</div>
{/snippet}

<section aria-label={t('securityGroupUnion.title')} class="mt-3 min-w-0 max-w-full space-y-3">
	<h3 class="text-xs font-semibold text-ink-1">{t('securityGroupUnion.title')}</h3>
	<p class="text-xs leading-relaxed text-ink-2 break-words">
		{t('securityGroupUnion.description')}
	</p>

	{#if loading}
		<LoadingState variant="section" label={t('securityGroupUnion.loading')} />
	{:else if error}
		<p role="alert" class="text-xs leading-relaxed text-state-danger-text break-words">
			{t('securityGroupUnion.error', { error })}
		</p>
	{:else if groupIds.length === 0}
		<p class="text-xs leading-relaxed text-ink-2">{t('securityGroupUnion.noGroups')}</p>
	{:else if union.missingGroupIds.length > 0}
		<div role="alert" class="min-w-0 space-y-1 text-xs leading-relaxed text-state-warning-text">
			<p>{t('securityGroupUnion.missingGroups')}</p>
			<ul class="space-y-1">
				{#each union.missingGroupIds as id (id)}
					<li class="font-mono break-all">{id}</li>
				{/each}
			</ul>
		</div>
	{:else if union.rows.length === 0 && !inboundView.sort && !outboundView.sort && !Object.keys(inboundView.filters).length && !Object.keys(outboundView.filters).length}
		<p class="text-xs leading-relaxed text-ink-2">{t('securityGroupUnion.noRules')}</p>
	{:else}
		{@render directionTable(inboundView, 'ingress', t('securityGroupUnion.column.source'), inboundOpen, toggleInbound)}
		{@render directionTable(outboundView, 'egress', t('securityGroupUnion.column.destination'), outboundOpen, toggleOutbound)}
	{/if}
</section>
