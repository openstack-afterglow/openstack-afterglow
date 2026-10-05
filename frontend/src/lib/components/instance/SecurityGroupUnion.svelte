<script lang="ts">
	import Button from '$lib/components/ui/Button.svelte';
	import TableShell from '$lib/components/ui/TableShell.svelte';
	import { t } from '$lib/i18n/ns/instance';
	import { buildSecurityGroupUnion } from '$lib/utils/securityGroupUnion';
	import type { SecurityGroupUnionGroup, SecurityGroupUnionRow } from '$lib/utils/securityGroupUnion';

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

	function toggleInbound() { inboundOpen = !inboundOpen; }
	function toggleOutbound() { outboundOpen = !outboundOpen; }
</script>

{#snippet directionTable(rows: SecurityGroupUnionRow[], direction: 'ingress' | 'egress', remoteHeading: string, expanded: boolean, onToggle: () => void)}
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
			<TableShell density="compact" class="min-w-0 max-w-full">
				<table aria-label={t('securityGroupUnion.rulesLabel', { direction })}>
					<thead>
						<tr>
							<th scope="col">{t('securityGroupUnion.column.ipVersion')}</th>
							<th scope="col">{t('securityGroupUnion.column.protocol')}</th>
							<th scope="col">{t('securityGroupUnion.column.portIcmp')}</th>
							<th scope="col">{remoteHeading}</th>
						</tr>
					</thead>
					<tbody>
						{#each rows as row (row.key)}
							<tr>
								<td>{row.ethertype}</td>
								<td>{row.protocolLabel}</td>
								<td>{row.portLabel}</td>
								<td title={row.remote.kind === 'group' ? row.remote.value : undefined}>{row.remoteLabel}</td>
							</tr>
						{:else}
							<tr><td colspan="4" class="text-ink-2">{t('securityGroupUnion.emptyDirection', { direction })}</td></tr>
						{/each}
					</tbody>
				</table>
			</TableShell>
		{/if}
	</div>
{/snippet}

<section aria-label={t('securityGroupUnion.title')} class="mt-3 min-w-0 max-w-full space-y-3">
	<h3 class="text-xs font-semibold text-ink-1">{t('securityGroupUnion.title')}</h3>
	<p class="text-xs leading-relaxed text-ink-2 break-words">
		{t('securityGroupUnion.description')}
	</p>

	{#if loading}
		<p role="status" class="text-xs text-ink-2">{t('securityGroupUnion.loading')}</p>
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
	{:else if union.rows.length === 0}
		<p class="text-xs leading-relaxed text-ink-2">{t('securityGroupUnion.noRules')}</p>
	{:else}
		{@render directionTable(inbound, 'ingress', t('securityGroupUnion.column.source'), inboundOpen, toggleInbound)}
		{@render directionTable(outbound, 'egress', t('securityGroupUnion.column.destination'), outboundOpen, toggleOutbound)}
	{/if}
</section>
