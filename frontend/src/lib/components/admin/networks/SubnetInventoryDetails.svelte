<script lang="ts">
	import { t as commonT } from '$lib/i18n/ns/common';
	import { t } from '$lib/i18n/ns/admin-network';
	import { intlLocale } from '$lib/i18n/runtime.svelte';
	import type { AdminSubnetDetail, SubnetPort, SubnetAllocation, SubnetAllocationPool, SubnetDhcpBinding } from '$lib/types/networks';
	import { Alert, Card, EmptyState, Pagination, Pill, SectionHeader, StatTile, TableShell, ToggleGroup } from '$lib/components/ui';
	import ResponsiveTable from '$lib/components/ui/ResponsiveTable.svelte';
	import CompactResourceCard from '$lib/components/ui/CompactResourceCard.svelte';
	import TableColumnHeader from '$lib/components/ui/TableColumnHeader.svelte';
	import TableViewControls from '$lib/components/ui/TableViewControls.svelte';
	import RegexSearch from '$lib/components/ui/RegexSearch.svelte';
	import { createTableView, type TableColumn } from '$lib/utils/tableView.svelte';
	const id = $props.id();
	let poolSearch = $state('');
	let dhcpSearch = $state('');
	let allocationSearch = $state('');
	let portSearch = $state('');
	const poolColumns: TableColumn<SubnetAllocationPool>[] = $derived([
		{ key: 'start', label: t('subnetDetailPage.startIp'), value: (row) => row.start },
		{ key: 'end', label: t('subnetDetailPage.endIp'), value: (row) => row.end },
	]);
	const dhcpColumns: TableColumn<SubnetDhcpBinding>[] = $derived([
		{ key: 'ip', label: t('subnetDetailPage.ipAddress'), filterValues: (row) => row.ip_addresses, value: (row) => row.ip_addresses.join(', ') || null },
		{ key: 'source', label: t('subnetDetailPage.source'), value: (row) => row.source, format: (value) => value === 'agent' ? t('subnetDetailPage.agent') : t('subnetDetailPage.port') },
		{ key: 'host', label: t('subnetDetailPage.host'), value: (row) => row.host },
		{ key: 'binary', label: t('subnetDetailPage.binary'), value: (row) => row.binary },
		{ key: 'zone', label: t('subnetDetailPage.availabilityZone'), value: (row) => row.availability_zone },
		{ key: 'agent', label: t('subnetDetailPage.agentId'), value: (row) => row.agent_id },
		{ key: 'status', label: t('subnetDetailPage.status'), value: (row) => row.alive === null && row.admin_state_up === null ? null : [row.alive === null ? '' : row.alive ? t('subnetDetailPage.healthy') : t('subnetDetailPage.stopped'), row.admin_state_up === null ? '' : row.admin_state_up ? t('subnetDetailPage.up') : t('subnetDetailPage.down')].filter(Boolean).join(' · ') },
		{ key: 'ports', label: t('subnetDetailPage.relatedPorts'), filterValues: (row) => row.port_ids, value: (row) => row.port_ids.join(', ') || null },
	]);
	const allocationColumns: TableColumn<SubnetAllocation>[] = $derived([
		{ key: 'ip', label: t('subnetDetailPage.ipAddress'), value: (row) => row.ip_address },
		{ key: 'port', label: t('subnetDetailPage.portId'), value: (row) => row.port_id },
		{ key: 'name', label: t('subnetDetailPage.portName'), value: (row) => row.port_name },
		{ key: 'attachment', label: t('subnetDetailPage.attachment'), value: (row) => [attachmentKind(row.device_owner), row.device_owner, row.device_name, row.device_id].filter(Boolean).join(' · ') },
		{ key: 'project', label: t('subnetDetailPage.projectId'), value: (row) => row.project_id },
		{ key: 'host', label: `${t('subnetDetailPage.actualNode')} (${t('subnetDetailPage.bindingHost')})`, value: (row) => row.binding_host_id },
	]);
	const portColumns: TableColumn<SubnetPort>[] = $derived([
		{ key: 'id', label: t('subnetDetailPage.portId'), value: (row) => row.id },
		{ key: 'name', label: t('subnetDetailPage.portName'), value: (row) => row.name },
		{ key: 'status', label: t('subnetDetailPage.status'), value: (row) => row.status },
		{ key: 'mac', label: t('subnetDetailPage.macAddress'), value: (row) => row.mac_address },
		{ key: 'ip', label: t('subnetDetailPage.subnetIp'), filterValues: (row) => row.ip_addresses, value: (row) => row.ip_addresses.join(', ') || null },
		{ key: 'attachment', label: t('subnetDetailPage.attachment'), value: (row) => [attachmentKind(row.device_owner), row.device_owner, row.device_name, row.device_id].filter(Boolean).join(' · ') },
		{ key: 'project', label: t('subnetDetailPage.projectId'), value: (row) => row.project_id },
		{ key: 'host', label: `${t('subnetDetailPage.actualNode')} (${t('subnetDetailPage.bindingHost')})`, value: (row) => row.binding_host_id },
	]);
	const poolView = createTableView({ locale: intlLocale, rows: () => subnet.allocation_pools, columns: () => poolColumns, search: () => poolSearch });
	const dhcpView = createTableView({ locale: intlLocale, rows: () => subnet.dhcp_bindings, columns: () => dhcpColumns, search: () => dhcpSearch,
		searchable: (row) => [...row.ip_addresses, ...row.port_ids, row.source, row.host, row.binary, row.availability_zone, row.agent_id, row.alive === null ? null : row.alive ? t('subnetDetailPage.healthy') : t('subnetDetailPage.stopped'), row.admin_state_up === null ? null : row.admin_state_up ? t('subnetDetailPage.up') : t('subnetDetailPage.down')].filter((value) => value != null).map(String) });
	const allocationView = createTableView({ locale: intlLocale, rows: () => subnet.allocations, columns: () => allocationColumns, search: () => allocationSearch,
		searchable: (row) => [row.ip_address, row.port_id, row.port_name, row.device_owner, row.device_id, row.device_name, attachmentKind(row.device_owner), row.project_id, row.binding_host_id].filter((value) => value != null).map(String) });
	const portView = createTableView({ locale: intlLocale, rows: () => subnet.ports, columns: () => portColumns, search: () => portSearch,
		searchable: (row) => [row.id, row.name, row.status, row.mac_address, ...row.ip_addresses, row.device_owner, row.device_id, row.device_name, attachmentKind(row.device_owner), row.project_id, row.binding_host_id].filter((value) => value != null).map(String) });

	let { subnet, showOverview = false }: { subnet: AdminSubnetDetail; showOverview?: boolean } = $props();
	type ResourceTab = 'allocations' | 'ports';
	const RESOURCE_PAGE_SIZE = 20;
	let activeResourceTab = $state<ResourceTab>('allocations');
	let allocationPage = $state(1);
	let portPage = $state(1);
	const resourceTabOptions = $derived([
		{ value: 'allocations', label: t('subnetDetailPage.tabs.allocations', { count: subnet.allocations.length }) },
		{ value: 'ports', label: t('subnetDetailPage.tabs.ports', { count: subnet.ports.length }) },
	]);
	const allocationTotalPages = $derived(Math.max(1, Math.ceil(allocationView.rows.length / RESOURCE_PAGE_SIZE)));
	const portTotalPages = $derived(Math.max(1, Math.ceil(portView.rows.length / RESOURCE_PAGE_SIZE)));
	const currentAllocationPage = $derived(Math.min(allocationPage, allocationTotalPages));
	const currentPortPage = $derived(Math.min(portPage, portTotalPages));
	const visibleAllocations = $derived(allocationView.rows.slice((currentAllocationPage - 1) * RESOURCE_PAGE_SIZE, currentAllocationPage * RESOURCE_PAGE_SIZE));
	const visiblePorts = $derived(portView.rows.slice((currentPortPage - 1) * RESOURCE_PAGE_SIZE, currentPortPage * RESOURCE_PAGE_SIZE));
	$effect(() => { allocationSearch; allocationView.filters; allocationView.sort; allocationPage = 1; });
	$effect(() => { portSearch; portView.filters; portView.sort; portPage = 1; });
	const numberFormat = $derived(new Intl.NumberFormat(intlLocale()));
	function count(value: string): string { return numberFormat.format(BigInt(value)); }
	function selectResourceTab(value: string) { activeResourceTab = value as ResourceTab; }
	// Clamp stored positions too, so a later expansion cannot resurrect a removed page.
	$effect(() => { allocationPage = currentAllocationPage; portPage = currentPortPage; });
	type Attachment = Pick<SubnetPort, 'device_owner' | 'device_id' | 'device_name'>;
	function attachmentKind(owner: string): string {
		if (owner.startsWith('compute:')) return t('subnetDetailPage.attachmentCompute');
		if (owner.startsWith('network:router') || owner === 'network:ha_router_replicated_interface') return t('subnetDetailPage.attachmentRouter');
		if (owner === 'network:dhcp') return t('subnetDetailPage.attachmentDhcp');
		if (owner === 'network:floatingip') return t('subnetDetailPage.attachmentFloatingIp');
		return owner ? t('subnetDetailPage.attachmentOther') : t('subnetDetailPage.attachmentUnattached');
	}
</script>

{#snippet attachment(device: Attachment)}
	<div class="space-y-1">
		<Pill tone="neutral">{attachmentKind(device.device_owner)}</Pill>
		<div class="font-mono text-xs text-ink-2">{device.device_owner || '-'}</div>
		{#if device.device_owner.startsWith('compute:') && device.device_id}
			<a href="/admin/instances" class="text-accent hover:underline">{device.device_name || device.device_id}</a>
		{:else if device.device_name}
			<div class="font-medium">{device.device_name}</div>
		{/if}
		{#if device.device_id && (!device.device_owner.startsWith('compute:') || device.device_name)}
			<div class="font-mono text-xs">{device.device_id}</div>
		{/if}
	</div>
{/snippet}

<div class="min-w-0 space-y-6">
{#if showOverview}
			<!-- Overview Metadata Card -->
			<Card padding="lg">
				<SectionHeader title={t('subnetDetailPage.overview')} class="mb-4" />
				<dl class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-x-6 gap-y-4 text-sm">
					<div>
						<dt class="text-xs text-ink-2 mb-1">{t('subnetDetailPage.subnetId')}</dt>
						<dd class="font-mono text-ink-0 break-all">{subnet.id}</dd>
					</div>
					<div>
						<dt class="text-xs text-ink-2 mb-1">{t('subnetDetailPage.subnetName')}</dt>
						<dd class="font-medium text-ink-0">{subnet.name || t('subnetDetailPage.unnamed')}</dd>
					</div>
					<div>
						<dt class="text-xs text-ink-2 mb-1">{t('subnetDetailPage.network')}</dt>
						<dd class="text-ink-0">
							{#if subnet.network_id}
								<a
									href="/admin/networks/{subnet.network_id}"
									class="text-accent hover:underline font-medium"
								>
									{subnet.network_name || subnet.network_id}
								</a>
							{:else}
								-
							{/if}
						</dd>
					</div>
					<div>
						<dt class="text-xs text-ink-2 mb-1">{t('subnetDetailPage.projectId')}</dt>
						<dd class="font-mono text-ink-0 break-all">{subnet.project_id || '-'}</dd>
					</div>
					<div>
						<dt class="text-xs text-ink-2 mb-1">CIDR</dt>
						<dd class="font-mono text-ink-0">{subnet.cidr}</dd>
					</div>
					<div>
						<dt class="text-xs text-ink-2 mb-1">{t('subnetDetailPage.gatewayIp')}</dt>
						<dd class="font-mono text-ink-0">{subnet.gateway_ip || '-'}</dd>
					</div>
					<div>
						<dt class="text-xs text-ink-2 mb-1">{t('subnetDetailPage.ipVersion')}</dt>
						<dd class="text-ink-0 font-medium">IPv{subnet.ip_version}</dd>
					</div>
					<div>
						<dt class="text-xs text-ink-2 mb-1">{t('subnetDetailPage.dhcpEnabled')}</dt>
						<dd>
							<Pill tone={subnet.dhcp_enabled ? 'success' : 'neutral'}>
								{subnet.dhcp_enabled ? t('subnetDetailPage.enabled') : t('subnetDetailPage.disabled')}
							</Pill>
						</dd>
					</div>
				</dl>
			</Card>
{/if}

	<Card padding="md">
		<SectionHeader title={t('subnetDetailPage.usage')} class="mb-3" />
		<div class="grid min-w-0 grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-3">
			<StatTile label={t('subnetDetailPage.totalPoolIps')} value={count(subnet.ip_usage.total_pool_ips)} class="min-w-0 [&_.stat-value]:break-all" />
			<StatTile label={t('subnetDetailPage.allocatedPoolIps')} value={count(subnet.ip_usage.allocated_pool_ips)} accent="violet" />
			<StatTile label={t('subnetDetailPage.reservedPoolIps')} value={count(subnet.ip_usage.reserved_pool_ips)} accent="amber" />
			<StatTile label={t('subnetDetailPage.availablePoolIps')} value={subnet.ip_usage.available_pool_ips === null ? t('subnetDetailPage.remainingUnavailable') : count(subnet.ip_usage.available_pool_ips)} accent="emerald" class="min-w-0 [&_.stat-value]:break-all" />
			<StatTile label={t('subnetDetailPage.totalAllocatedIps')} value={count(subnet.ip_usage.allocated_ips)} accent="cyan" />
			<StatTile label={t('subnetDetailPage.outsidePoolIps')} value={count(subnet.ip_usage.outside_pool_ips)} accent="rose" />
		</div>
		{#if subnet.ip_usage.available_pool_ips === null}
			<p class="mt-3 text-sm text-ink-2">{t('subnetDetailPage.autoIpv6Explanation', { mode: subnet.ip_usage.allocation_mode })}</p>
		{/if}
		<p class="mt-3 text-sm text-ink-2">{t('subnetDetailPage.measurementCaveat')}</p>
	</Card>
	{#if !subnet.device_names_available}
		<Alert tone="warning" title={t('subnetDetailPage.namesUnavailable')}>{t('subnetDetailPage.namesUnavailableDescription')}</Alert>
	{/if}
			<!-- Allocation Pools Section -->
			<Card padding="md">
				<SectionHeader
					title={t('subnetDetailPage.pools')}
					meta={t('subnetDetailPage.totalCount', { count: subnet.allocation_pools.length })}
					class="mb-3"
				/>
				<RegexSearch id="{id}-pool-search" bind:value={poolSearch} />
				<TableViewControls view={poolView} />
	{#if subnet.allocation_pools.length > 0 && poolView.rows.length === 0}<p class="my-3 text-sm text-ink-2">{commonT('table.noMatches')}</p>{/if}
				{#if subnet.allocation_pools.length === 0}
					<EmptyState headline={t('subnetDetailPage.poolsEmpty')} description={t('subnetDetailPage.poolsEmptyDescription')} />
				{/if}
					<ResponsiveTable>
						{#snippet cards()}
							{#each poolView.rows as pool}
								<CompactResourceCard><p class="break-all font-mono text-xs text-ink-0">{t('subnetDetailPage.startIp')}: {pool.start}</p><p class="break-all font-mono text-xs text-ink-2">{t('subnetDetailPage.endIp')}: {pool.end}</p></CompactResourceCard>
							{/each}
						{/snippet}
					<TableShell density="compact">
						<table>
							<thead>
								<tr class="text-xs uppercase tracking-wide">
									{#each poolColumns as column (column.key)}<TableColumnHeader view={poolView} columnKey={column.key} />{/each}
								</tr>
							</thead>
							<tbody>
								{#each poolView.rows as pool}
									<tr>
										<td class="font-mono text-sm">{pool.start}</td>
										<td class="font-mono text-sm">{pool.end}</td>
									</tr>
								{/each}
							</tbody>
						</table>
					</TableShell>
					</ResponsiveTable>
			</Card>

			<!-- DHCP Placement & Agent Section -->
			<Card padding="md">
				<SectionHeader
					title={t('subnetDetailPage.dhcpPlacement')}
					meta={t('subnetDetailPage.totalCount', { count: subnet.dhcp_bindings.length })}
					class="mb-3"
				/>
				{#if !subnet.dhcp_agent_data_available}
					<Alert tone="warning" class="mb-3" title={t('subnetDetailPage.schedulerUnavailable')}>
						{t('subnetDetailPage.schedulerUnavailableDescription')}
					</Alert>
				{/if}
				<RegexSearch id="{id}-dhcp-search" bind:value={dhcpSearch} />
				<TableViewControls view={dhcpView} />
	{#if subnet.dhcp_bindings.length > 0 && dhcpView.rows.length === 0}<p class="my-3 text-sm text-ink-2">{commonT('table.noMatches')}</p>{/if}
				{#if subnet.dhcp_bindings.length === 0}
					<EmptyState headline={t('subnetDetailPage.dhcpEmpty')} description={t('subnetDetailPage.dhcpEmptyDescription')} />
				{/if}
					<ResponsiveTable>
						{#snippet cards()}
							{#each dhcpView.rows as binding}
								<CompactResourceCard>
									<div class="flex flex-wrap items-start justify-between gap-2"><h3 class="break-all font-mono text-sm text-ink-0">{binding.host || binding.ip_addresses[0] || '-'}</h3>{#if binding.alive !== null}<Pill tone={binding.alive ? 'success' : 'danger'}>{binding.alive ? t('subnetDetailPage.healthy') : t('subnetDetailPage.stopped')}</Pill>{/if}{#if binding.admin_state_up !== null}<Pill tone={binding.admin_state_up ? 'info' : 'neutral'}>{binding.admin_state_up ? t('subnetDetailPage.up') : t('subnetDetailPage.down')}</Pill>{/if}</div>
									<div class="space-y-1 break-all text-xs text-ink-2"><p>{t('subnetDetailPage.ipAddress')}: {binding.ip_addresses[0] ?? '-'}{binding.ip_addresses.length > 1 ? ` (+${binding.ip_addresses.length - 1})` : ''}</p><p>{t('subnetDetailPage.source')}: {binding.source === 'agent' ? t('subnetDetailPage.agent') : t('subnetDetailPage.port')}</p><p>{t('subnetDetailPage.availabilityZone')}: {binding.availability_zone || '-'}</p></div>
									{#snippet details()}<div class="space-y-2 break-all text-xs text-ink-2"><p>{t('subnetDetailPage.binary')}: {binding.binary || '-'}</p><p>{t('subnetDetailPage.agentId')}: {binding.agent_id || '-'}</p><p>{t('subnetDetailPage.relatedPorts')}: {binding.port_ids.join(', ') || '-'}</p><p>{binding.ip_addresses.join(', ') || '-'}</p></div>{/snippet}
								</CompactResourceCard>
							{/each}
						{/snippet}
					<TableShell density="compact">
						<table class="subnet-table subnet-table-dhcp">
							<thead>
								<tr class="text-xs uppercase tracking-wide">
									{#each dhcpColumns as column (column.key)}<TableColumnHeader view={dhcpView} columnKey={column.key} />{/each}
								</tr>
							</thead>
							<tbody>
								{#each dhcpView.rows as binding}
									<tr>
										<td class="font-mono text-sm">
											{binding.ip_addresses.length > 0 ? binding.ip_addresses.join(', ') : '-'}
										</td>
										<td>
											<Pill tone={binding.source === 'agent' ? 'info' : 'neutral'}>
												{binding.source === 'agent' ? t('subnetDetailPage.agent') : t('subnetDetailPage.port')}
											</Pill>
										</td>
										<td class="font-mono text-sm">{binding.host || '-'}</td>
										<td class="font-mono text-xs text-ink-2">{binding.binary || '-'}</td>
										<td class="text-xs">{binding.availability_zone || '-'}</td>
										<td class="font-mono text-xs whitespace-nowrap">{binding.agent_id || '-'}</td>
										<td>
											{#if binding.alive !== null || binding.admin_state_up !== null}
												<div class="flex items-center gap-1.5">
													{#if binding.alive !== null}
														<Pill tone={binding.alive ? 'success' : 'danger'}>
															{binding.alive ? t('subnetDetailPage.healthy') : t('subnetDetailPage.stopped')}
														</Pill>
													{/if}
													{#if binding.admin_state_up !== null}
														<Pill tone={binding.admin_state_up ? 'info' : 'neutral'}>
															{binding.admin_state_up ? t('subnetDetailPage.up') : t('subnetDetailPage.down')}
														</Pill>
													{/if}
												</div>
											{:else}
												<span class="text-ink-2">-</span>
											{/if}
										</td>
										<td class="font-mono text-xs whitespace-nowrap">
											{binding.port_ids.length > 0 ? binding.port_ids.join(', ') : '-'}
										</td>
									</tr>
								{/each}
							</tbody>
						</table>
					</TableShell>
					</ResponsiveTable>
			</Card>

			<Card padding="md">
				<div class="mb-4 space-y-3">
					<SectionHeader
						title={t('subnetDetailPage.resources')}
						meta={t('subnetDetailPage.resourcesMeta')}
					/>
					<ToggleGroup
						value={activeResourceTab}
						options={resourceTabOptions}
						onchange={selectResourceTab}
						ariaLabel={t('subnetDetailPage.resourcesTabs')}
						fullWidth
					/>
				</div>

				{#if activeResourceTab === 'allocations'}
					<SectionHeader
						title={t('subnetDetailPage.allocations')}
						meta={t('subnetDetailPage.totalCount', { count: subnet.allocations.length })}
						class="mb-3"
					/>
					<RegexSearch id="{id}-allocation-search" bind:value={allocationSearch} />
					<TableViewControls view={allocationView} />
	{#if subnet.allocations.length > 0 && allocationView.rows.length === 0}<p class="my-3 text-sm text-ink-2">{commonT('table.noMatches')}</p>{/if}
					{#if subnet.allocations.length === 0}
						<EmptyState headline={t('subnetDetailPage.allocationsEmpty')} description={t('subnetDetailPage.allocationsEmptyDescription')} />
					{/if}
						<ResponsiveTable>
							{#snippet cards()}
								{#each visibleAllocations as alloc}
									<CompactResourceCard>
										<h3 class="break-all font-mono text-sm text-ink-0">{alloc.ip_address}</h3><div class="space-y-1 break-all text-xs text-ink-2"><p>{t('subnetDetailPage.portName')}: {alloc.port_name || '-'}</p><p>{t('subnetDetailPage.attachment')}: {attachmentKind(alloc.device_owner)}</p><p>{t('subnetDetailPage.actualNode')}: {alloc.binding_host_id || '-'}</p></div>
										{#snippet details()}<div class="space-y-2 break-all text-xs text-ink-2"><p>{t('subnetDetailPage.portId')}: {alloc.port_id || '-'}</p><p>{t('subnetDetailPage.projectId')}: {alloc.project_id || '-'}</p>{@render attachment(alloc)}</div>{/snippet}
									</CompactResourceCard>
								{/each}
							{/snippet}
						<TableShell density="compact">
							<table class="subnet-table subnet-table-allocations">
								<thead>
									<tr class="text-xs uppercase tracking-wide">
										{#each allocationColumns as column (column.key)}<TableColumnHeader view={allocationView} columnKey={column.key} />{/each}
									</tr>
								</thead>
								<tbody>
									{#each visibleAllocations as alloc}
										<tr>
											<td class="font-mono text-sm font-semibold text-ink-0">{alloc.ip_address}</td>
											<td class="font-mono text-xs whitespace-nowrap">{alloc.port_id || '-'}</td>
											<td>{alloc.port_name || '-'}</td>
											<td>{@render attachment(alloc)}</td>
											<td class="font-mono text-xs whitespace-nowrap">{alloc.project_id || '-'}</td>
											<td class="font-mono text-xs font-medium text-ink-0">{alloc.binding_host_id || '-'}</td>
										</tr>
									{/each}
								</tbody>
							</table>
						</TableShell>
						</ResponsiveTable>
						<Pagination
							page={currentAllocationPage}
							totalPages={allocationTotalPages}
							hasPrev={currentAllocationPage > 1}
							hasNext={currentAllocationPage < allocationTotalPages}
							onPrev={() => (allocationPage = Math.max(1, currentAllocationPage - 1))}
							onNext={() => (allocationPage = Math.min(allocationTotalPages, currentAllocationPage + 1))}
							total={allocationView.rows.length}
							pageSize={RESOURCE_PAGE_SIZE}
						/>
				{:else}
					<SectionHeader
						title={t('subnetDetailPage.ports')}
						meta={t('subnetDetailPage.totalCount', { count: subnet.ports.length })}
						class="mb-3"
					/>
					<RegexSearch id="{id}-port-search" bind:value={portSearch} />
					<TableViewControls view={portView} />
	{#if subnet.ports.length > 0 && portView.rows.length === 0}<p class="my-3 text-sm text-ink-2">{commonT('table.noMatches')}</p>{/if}
					{#if subnet.ports.length === 0}
						<EmptyState headline={t('subnetDetailPage.portsEmpty')} description={t('subnetDetailPage.portsEmptyDescription')} />
					{/if}
						<ResponsiveTable>
							{#snippet cards()}
								{#each visiblePorts as port (port.id)}
									<CompactResourceCard>
										<div class="flex items-start justify-between gap-2"><h3 class="break-all font-medium text-ink-0">{port.name || port.id.slice(0, 12)}</h3><Pill tone={port.status === 'ACTIVE' ? 'success' : port.status === 'DOWN' ? 'danger' : 'neutral'}>{port.status}</Pill></div><div class="space-y-1 break-all text-xs text-ink-2"><p>{t('subnetDetailPage.subnetIp')}: {port.ip_addresses[0] ?? '-'}{port.ip_addresses.length > 1 ? ` (+${port.ip_addresses.length - 1})` : ''}</p><p>{t('subnetDetailPage.attachment')}: {attachmentKind(port.device_owner)}</p><p>{t('subnetDetailPage.actualNode')}: {port.binding_host_id || '-'}</p></div>
										{#snippet details()}<div class="space-y-2 break-all text-xs text-ink-2"><p class="font-mono">{port.id}</p><p>{t('subnetDetailPage.macAddress')}: {port.mac_address}</p><p>{t('subnetDetailPage.projectId')}: {port.project_id || '-'}</p><p>{port.ip_addresses.join(', ') || '-'}</p>{@render attachment(port)}</div>{/snippet}
									</CompactResourceCard>
								{/each}
							{/snippet}
						<TableShell density="compact">
							<table class="subnet-table subnet-table-ports">
								<thead>
									<tr class="text-xs uppercase tracking-wide">
										{#each portColumns as column (column.key)}<TableColumnHeader view={portView} columnKey={column.key} />{/each}
									</tr>
								</thead>
								<tbody>
									{#each visiblePorts as port}
										<tr>
											<td class="font-mono text-xs whitespace-nowrap">{port.id}</td>
											<td class="text-sm font-medium">{port.name || '-'}</td>
											<td>
												<Pill tone={port.status === 'ACTIVE' ? 'success' : port.status === 'DOWN' ? 'danger' : 'neutral'}>
													{port.status}
												</Pill>
											</td>
											<td class="font-mono text-xs">{port.mac_address}</td>
											<td class="font-mono text-xs">{port.ip_addresses.length > 0 ? port.ip_addresses.join(', ') : '-'}</td>
											<td>{@render attachment(port)}</td>
											<td class="font-mono text-xs">{port.project_id || '-'}</td>
											<td class="font-mono text-xs font-medium text-ink-0">{port.binding_host_id || '-'}</td>
										</tr>
									{/each}
								</tbody>
							</table>
						</TableShell>
						</ResponsiveTable>
						<Pagination
							page={currentPortPage}
							totalPages={portTotalPages}
							hasPrev={currentPortPage > 1}
							hasNext={currentPortPage < portTotalPages}
							onPrev={() => (portPage = Math.max(1, currentPortPage - 1))}
							onNext={() => (portPage = Math.min(portTotalPages, currentPortPage + 1))}
							total={portView.rows.length}
							pageSize={RESOURCE_PAGE_SIZE}
						/>
				{/if}
			</Card>
</div>

<style>
	.subnet-table :global(th) {
		white-space: nowrap;
	}

	.subnet-table-dhcp {
		min-width: 64rem;
	}

	.subnet-table-allocations {
		min-width: 58rem;
	}

	.subnet-table-ports {
		min-width: 72rem;
	}
</style>
