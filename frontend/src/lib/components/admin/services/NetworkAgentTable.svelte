<script lang="ts">
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

	function aliveLabel(alive: boolean | null): string {
		return alive === true ? 'alive' : alive === false ? 'down' : '미확인';
	}

	const fields: ServiceListField<NetworkAgent>[] = [
		{ key: 'agent_type', label: 'Agent Type', value: (agent) => agent.agent_type, filter: true },
		{ key: 'binary', label: 'Binary', value: (agent) => agent.binary, filter: true },
		{ key: 'host', label: 'Host', value: (agent) => agent.host, filter: true },
		{ key: 'zone', label: 'Zone', value: (agent) => agent.availability_zone, filter: true },
		{ key: 'alive', label: 'Alive', value: (agent) => agent.alive === null ? null : aliveLabel(agent.alive), filter: true },
		{ key: 'admin_state', label: 'Admin State', value: (agent) => agent.admin_state_up ? 'UP' : 'DOWN', filter: true },
		{ key: 'updated', label: 'Updated', value: (agent) => agent.updated_at, sortValue: (agent) => serviceTimestamp(agent.updated_at) },
	];
	const filters = $derived(buildServiceFilters(agents, fields));
	const sortOptions = fields.map(({ key, label }) => ({ key, label }));
	const displayedAgents = $derived(filterAndSortRows(agents, fields, view));
</script>

<ServiceListControls
	bind:view
	{filters}
	{sortOptions}
	total={agents.length}
	count={displayedAgents.length}
	{loading}
	searchPlaceholder="Agent Type, Binary, Host, Zone, Updated 검색"
/>

{#if agents.length === 0}
	{#if loading}
		<LoadingSkeleton variant="table" rows={8} />
	{:else}
		<EmptyState headline={emptyMessage} />
	{/if}
{:else if displayedAgents.length === 0}
	<EmptyState headline="일치하는 네트워크 에이전트가 없습니다" description="필터나 검색어를 조정해 보세요." />
{:else}
	<TableShell density="compact">
		<table aria-label="네트워크 에이전트 목록">
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
						<td><Pill tone={agent.alive === true ? 'success' : agent.alive === false ? 'danger' : 'neutral'} size="xs">{aliveLabel(agent.alive)}</Pill></td>
						<td><Pill tone={agent.admin_state_up ? 'success' : 'danger'} size="xs">{agent.admin_state_up ? 'UP' : 'DOWN'}</Pill></td>
						<td class="tabular-nums text-ink-2">{fmtTime(agent.updated_at)}</td>
					</tr>
				{/each}
			</tbody>
		</table>
	</TableShell>
{/if}
