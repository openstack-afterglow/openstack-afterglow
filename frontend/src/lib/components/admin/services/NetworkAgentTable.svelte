<script lang="ts">
	import { intlLocale } from '$lib/i18n/runtime.svelte';
	import { t } from '$lib/i18n/ns/admin-ops';
	import EmptyState from '$lib/components/ui/EmptyState.svelte';
	import LoadingState from '$lib/components/ui/LoadingState.svelte';
	import Pill from '$lib/components/ui/Pill.svelte';
	import TableShell from '$lib/components/ui/TableShell.svelte';
	import ResponsiveTable from '$lib/components/ui/ResponsiveTable.svelte';
	import CompactResourceCard from '$lib/components/ui/CompactResourceCard.svelte';
	import type { NetworkAgent } from '$lib/types/adminServices';
	import TableColumnHeader from '$lib/components/ui/TableColumnHeader.svelte';
	import TableViewControls from '$lib/components/ui/TableViewControls.svelte';
	import RegexSearch from '$lib/components/ui/RegexSearch.svelte';
	import { createTableView, type TableColumn } from '$lib/utils/tableView.svelte';
	import { fmtTime } from './serviceColumns.js';
	import { serviceTimestamp } from './serviceList';
	const id = $props.id();

	let {
		agents,
		loading,
		emptyMessage,
		search = $bindable(''),
	}: {
		agents: NetworkAgent[];
		loading: boolean;
		emptyMessage: string;
		search?: string;
	} = $props();

	const fields: TableColumn<NetworkAgent>[] = $derived([
		{ key: 'agent_type', label: t('services.columns.agentType'), value: (agent) => agent.agent_type },
		{ key: 'binary', label: t('services.columns.binary'), value: (agent) => agent.binary },
		{ key: 'host', label: t('services.columns.host'), value: (agent) => agent.host },
		{ key: 'zone', label: t('services.columns.zone'), value: (agent) => agent.availability_zone },
		{ key: 'alive', label: t('services.columns.alive'), value: (agent) => agent.alive, format: (value) => value === null ? t('services.state.unknown') : value ? t('services.state.alive') : t('services.state.down') },
		{ key: 'admin_state', label: t('services.columns.adminState'), value: (agent) => agent.admin_state_up, format: (value) => value ? t('services.state.adminUp') : t('services.state.adminDown') },
		{ key: 'updated', label: t('services.columns.updated'), value: (agent) => serviceTimestamp(agent.updated_at), format: (_value, agent) => fmtTime(agent.updated_at) },
	]);
	const view = createTableView({ locale: intlLocale, rows: () => agents, columns: () => fields, search: () => search,
		searchable: (agent) => [agent.agent_type, agent.binary, agent.host, agent.availability_zone, agent.updated_at, agent.alive === null ? t('services.state.unknown') : agent.alive ? t('services.state.alive') : t('services.state.down'), agent.admin_state_up ? t('services.state.adminUp') : t('services.state.adminDown')].filter((value) => value != null).map(String) });
	const displayedAgents = $derived(view.rows);
</script>

<RegexSearch id="{id}-search" bind:value={search} placeholder={t('services.network.searchPlaceholder')} />
<TableViewControls {view} />

{#if agents.length === 0}
	{#if loading}
		<LoadingState variant="section" />
	{:else}
		<EmptyState headline={emptyMessage} />
	{/if}
{:else if displayedAgents.length === 0}
	<EmptyState headline={t('services.network.noMatches')} description={t('services.list.adjustFilters')} />
{/if}
	<ResponsiveTable>
		{#snippet cards()}
			{#each displayedAgents as agent (agent.id)}
				<CompactResourceCard>
					<div class="flex flex-wrap items-start justify-between gap-2">
						<h3 class="min-w-0 break-words text-sm font-medium text-ink-0">{agent.agent_type}</h3>
						<div class="flex flex-wrap gap-1">
							<Pill tone={agent.alive === true ? 'success' : agent.alive === false ? 'danger' : 'neutral'} size="xs">{agent.alive === true ? t('services.state.alive') : agent.alive === false ? t('services.state.down') : t('services.state.unknown')}</Pill>
							<Pill tone={agent.admin_state_up ? 'success' : 'danger'} size="xs">{agent.admin_state_up ? t('services.state.adminUp') : t('services.state.adminDown')}</Pill>
						</div>
					</div>
					<dl class="grid gap-1 text-xs text-ink-2">
						<div class="flex flex-wrap justify-between gap-2"><dt>{t('services.columns.host')}</dt><dd class="break-all">{agent.host}</dd></div>
						<div class="flex flex-wrap justify-between gap-2"><dt>{t('services.columns.zone')}</dt><dd class="break-all">{agent.availability_zone || '-'}</dd></div>
					</dl>
					{#snippet details()}
						<dl class="grid gap-2 text-xs text-ink-2">
							<div><dt>{t('services.columns.binary')}</dt><dd class="break-all font-mono">{agent.binary}</dd></div>
							<div><dt>{t('services.columns.updated')}</dt><dd class="tabular-nums">{fmtTime(agent.updated_at)}</dd></div>
						</dl>
					{/snippet}
				</CompactResourceCard>
			{/each}
		{/snippet}
	<TableShell density="compact">
		<table aria-label={t('services.network.listLabel')}>
			<thead>
				<tr>
					{#each fields as field (field.key)}
						<TableColumnHeader {view} columnKey={field.key} />
					{/each}
				</tr>
			</thead>
			<tbody>
				{#each displayedAgents as agent (agent.id)}
					<tr>
						<td class="text-ink-0">{agent.agent_type}</td>
						<td class="font-mono text-ink-2">{agent.binary}</td>
						<td class="text-ink-2">{agent.host}</td>
						<td class="text-ink-2">{agent.availability_zone || '-'}</td>
						<td><Pill tone={agent.alive === true ? 'success' : agent.alive === false ? 'danger' : 'neutral'} size="xs">{agent.alive === true ? t('services.state.alive') : agent.alive === false ? t('services.state.down') : t('services.state.unknown')}</Pill></td>
						<td><Pill tone={agent.admin_state_up ? 'success' : 'danger'} size="xs">{agent.admin_state_up ? t('services.state.adminUp') : t('services.state.adminDown')}</Pill></td>
						<td class="tabular-nums text-ink-2">{fmtTime(agent.updated_at)}</td>
					</tr>
				{/each}
			</tbody>
		</table>
	</TableShell>
	</ResponsiveTable>
