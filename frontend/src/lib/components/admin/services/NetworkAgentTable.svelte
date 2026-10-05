<script lang="ts">
	import { t } from '$lib/i18n/ns/admin-ops';
	import EmptyState from '$lib/components/ui/EmptyState.svelte';
	import LoadingSkeleton from '$lib/components/LoadingSkeleton.svelte';
	import Pill from '$lib/components/ui/Pill.svelte';
	import TableShell from '$lib/components/ui/TableShell.svelte';
	import type { NetworkAgent } from '$lib/types/adminServices';
	import ServiceListControls from './ServiceListControls.svelte';
	import ServiceSortHeader from './ServiceSortHeader.svelte';
	import { fmtTime } from './serviceColumns.js';
	import {
		buildServiceFilters,
		createServiceListState,
		filterAndSortRows,
		serviceTimestamp,
		type ServiceListField,
		type ServiceListState,
	} from './serviceList';

	let {
		agents,
		loading,
		emptyMessage,
		view = $bindable(createServiceListState()),
	}: {
		agents: NetworkAgent[];
		loading: boolean;
		emptyMessage: string;
		view?: ServiceListState;
	} = $props();

	const fields: ServiceListField<NetworkAgent>[] = $derived([
		{ key: 'agent_type', label: t('services.columns.agentType'), value: (agent) => agent.agent_type, filter: true },
		{ key: 'binary', label: t('services.columns.binary'), value: (agent) => agent.binary, filter: true },
		{ key: 'host', label: t('services.columns.host'), value: (agent) => agent.host, filter: true },
		{ key: 'zone', label: t('services.columns.zone'), value: (agent) => agent.availability_zone, filter: true },
		{ key: 'alive', label: t('services.columns.alive'), value: (agent) => agent.alive === null ? null : agent.alive ? 'alive' : 'down', filter: true },
		{ key: 'admin_state', label: t('services.columns.adminState'), value: (agent) => agent.admin_state_up ? 'UP' : 'DOWN', filter: true },
		{ key: 'updated', label: t('services.columns.updated'), value: (agent) => agent.updated_at, sortValue: (agent) => serviceTimestamp(agent.updated_at) },
	]);
	const filters = $derived(buildServiceFilters(agents, fields));
	const sortOptions = $derived(fields.map(({ key, label }) => ({ key, label })));
	const displayedAgents = $derived(filterAndSortRows(agents, fields, view));
</script>

<ServiceListControls
	bind:view
	{filters}
	{sortOptions}
	total={agents.length}
	count={displayedAgents.length}
	{loading}
	searchPlaceholder={t('services.network.searchPlaceholder')}
/>

{#if agents.length === 0}
	{#if loading}
		<LoadingSkeleton variant="table" rows={8} />
	{:else}
		<EmptyState headline={emptyMessage} />
	{/if}
{:else if displayedAgents.length === 0}
	<EmptyState headline={t('services.network.noMatches')} description={t('services.list.adjustFilters')} />
{:else}
	<TableShell density="compact">
		<table aria-label={t('services.network.listLabel')}>
			<thead>
				<tr>
					{#each fields as field (field.key)}
						<ServiceSortHeader bind:view column={field.key} label={field.label} />
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
{/if}
