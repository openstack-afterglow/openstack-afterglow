<script lang="ts">
	import { t } from '$lib/i18n/ns/admin-network';
	import ActivityIndicator from '$lib/components/ui/ActivityIndicator.svelte';
	import { page } from '$app/stores';
	import { auth } from '$lib/stores/auth';
	import { api, ApiError } from '$lib/api/client';
	import type { AdminSubnetDetail } from '$lib/types/networks';
	import {
		Alert,
		Button,
		Card,
		EmptyState,
		PageHeader,
		PageShell,
		Pagination,
		Pill,
		SectionHeader,
		StatTile,
		TableShell,
		ToggleGroup,
	} from '$lib/components/ui';

	let loading = $state(true);
	let error = $state<string | null>(null);
	let subnet = $state<AdminSubnetDetail | null>(null);

	const subnetId = $derived($page.params.id);
	const token = $derived($auth.token ?? undefined);
	const projectId = $derived($auth.projectId ?? undefined);

	type ResourceTab = 'allocations' | 'ports';
	const RESOURCE_PAGE_SIZE = 20;

	let activeResourceTab = $state<ResourceTab>('allocations');
	let allocationPage = $state(1);
	let portPage = $state(1);

	const resourceTabOptions = $derived([
		{ value: 'allocations', label: t('subnetDetailPage.tabs.allocations', { count: subnet?.allocations.length ?? 0 }) },
		{ value: 'ports', label: t('subnetDetailPage.tabs.ports', { count: subnet?.ports.length ?? 0 }) },
	]);
	const allocationTotalPages = $derived(
		Math.max(1, Math.ceil((subnet?.allocations.length ?? 0) / RESOURCE_PAGE_SIZE)),
	);
	const portTotalPages = $derived(
		Math.max(1, Math.ceil((subnet?.ports.length ?? 0) / RESOURCE_PAGE_SIZE)),
	);
	const visibleAllocations = $derived(
		subnet?.allocations.slice(
			(allocationPage - 1) * RESOURCE_PAGE_SIZE,
			allocationPage * RESOURCE_PAGE_SIZE,
		) ?? [],
	);
	const visiblePorts = $derived(
		subnet?.ports.slice(
			(portPage - 1) * RESOURCE_PAGE_SIZE,
			portPage * RESOURCE_PAGE_SIZE,
		) ?? [],
	);

	function selectResourceTab(value: string) {
		activeResourceTab = value as ResourceTab;
	}

	async function loadSubnet(forceRefresh = false) {
		if (!subnetId || !token) return;
		loading = true;
		error = null;
		try {
			const path = `/api/v1/admin/subnets/${subnetId}`;
			const detail = forceRefresh
				? await api.get<AdminSubnetDetail>(path, token, projectId, { refresh: true })
				: await api.get<AdminSubnetDetail>(path, token, projectId);
			subnet = detail;
			allocationPage = 1;
			portPage = 1;
		} catch (err) {
			if (err instanceof ApiError) {
				error = err.message || t('subnetDetailPage.loadFailedStatus', { status: err.status });
			} else {
				error = (err as Error).message || t('subnetDetailPage.loadFailed');
			}
		} finally {
			loading = false;
		}
	}

	$effect(() => {
		if (!subnetId || !$auth.token) return;
		void loadSubnet();
	});
</script>

<PageShell max="7xl">
	<PageHeader
		breadcrumb={t('subnetDetailPage.breadcrumb')}
		title={subnet?.name ? t('subnetDetailPage.namedTitle', { name: subnet.name }) : t('subnetDetailPage.title')}
		subtitle={t('subnetDetailPage.subtitle')}
	>
		{#snippet actions()}
			<Button
				href={subnet?.network_id ? `/admin/networks/${subnet.network_id}` : '/admin/networks'}
				variant="outline"
				size="sm"
			>
				{t('subnetDetailPage.networkDetail')}
			</Button>
			<Button onclick={() => loadSubnet(true)} variant="subtle" size="sm" disabled={loading}>
				{t('subnetDetailPage.refresh')}
			</Button>
		{/snippet}
	</PageHeader>

	{#if loading}
		<Card padding="lg">
			<div class="py-12 text-center text-sm text-ink-2">
				<ActivityIndicator label={t('subnetDetailPage.loading')} />
			</div>
		</Card>
	{:else if error}
		<Alert tone="danger" title={t('subnetDetailPage.loadFailedTitle')}>
			{error}
		</Alert>
	{:else if subnet}
		<div class="space-y-6">
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

			<!-- Summary StatTiles -->
			<div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-3.5">
				<StatTile
					label={t('subnetDetailPage.cidrVersion')}
					value={subnet.cidr}
					suffix={`IPv${subnet.ip_version}`}
					accent="blue"
				/>
				<StatTile
					label={t('subnetDetailPage.poolCount')}
					value={subnet.allocation_pools.length}
					unit={subnet.allocation_pools.length === 1 ? t('subnetDetailPage.singleCountUnit') : t('subnetDetailPage.countUnit')}
					accent="cyan"
				/>
				<StatTile
					label={t('subnetDetailPage.allocatedIpCount')}
					value={subnet.allocations.length}
					unit={subnet.allocations.length === 1 ? t('subnetDetailPage.singleCountUnit') : t('subnetDetailPage.countUnit')}
					accent="violet"
				/>
				<StatTile
					label={t('subnetDetailPage.usedPortCount')}
					value={subnet.ports.length}
					unit={subnet.ports.length === 1 ? t('subnetDetailPage.singleCountUnit') : t('subnetDetailPage.countUnit')}
					accent="emerald"
				/>
			</div>

			<!-- Allocation Pools Section -->
			<Card padding="md">
				<SectionHeader
					title={t('subnetDetailPage.pools')}
					meta={t('subnetDetailPage.totalCount', { count: subnet.allocation_pools.length })}
					class="mb-3"
				/>
				{#if subnet.allocation_pools.length === 0}
					<EmptyState headline={t('subnetDetailPage.poolsEmpty')} description={t('subnetDetailPage.poolsEmptyDescription')} />
				{:else}
					<TableShell density="compact">
						<table>
							<thead>
								<tr class="text-xs uppercase tracking-wide">
									<th>{t('subnetDetailPage.startIp')}</th>
									<th>{t('subnetDetailPage.endIp')}</th>
								</tr>
							</thead>
							<tbody>
								{#each subnet.allocation_pools as pool}
									<tr>
										<td class="font-mono text-sm">{pool.start}</td>
										<td class="font-mono text-sm">{pool.end}</td>
									</tr>
								{/each}
							</tbody>
						</table>
					</TableShell>
				{/if}
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
				{#if subnet.dhcp_bindings.length === 0}
					<EmptyState headline={t('subnetDetailPage.dhcpEmpty')} description={t('subnetDetailPage.dhcpEmptyDescription')} />
				{:else}
					<TableShell density="compact">
						<table class="subnet-table subnet-table-dhcp">
							<thead>
								<tr class="text-xs uppercase tracking-wide">
									<th>{t('subnetDetailPage.ipAddress')}</th>
									<th>{t('subnetDetailPage.source')}</th>
									<th>{t('subnetDetailPage.host')}</th>
									<th>{t('subnetDetailPage.binary')}</th>
									<th>{t('subnetDetailPage.availabilityZone')}</th>
									<th>{t('subnetDetailPage.agentId')}</th>
									<th>{t('subnetDetailPage.status')}</th>
									<th>{t('subnetDetailPage.relatedPorts')}</th>
								</tr>
							</thead>
							<tbody>
								{#each subnet.dhcp_bindings as binding}
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
				{/if}
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
					{#if subnet.allocations.length === 0}
						<EmptyState headline={t('subnetDetailPage.allocationsEmpty')} description={t('subnetDetailPage.allocationsEmptyDescription')} />
					{:else}
						<TableShell density="compact">
							<table class="subnet-table subnet-table-allocations">
								<thead>
									<tr class="text-xs uppercase tracking-wide">
										<th>{t('subnetDetailPage.ipAddress')}</th>
										<th>{t('subnetDetailPage.portId')}</th>
										<th>{t('subnetDetailPage.deviceOwner')}</th>
										<th>{t('subnetDetailPage.deviceId')}</th>
										<th>{t('subnetDetailPage.projectId')}</th>
										<th>
											{t('subnetDetailPage.actualNode')}
											<span class="block text-xs normal-case text-ink-2 font-normal">{t('subnetDetailPage.bindingHost')}</span>
										</th>
									</tr>
								</thead>
								<tbody>
									{#each visibleAllocations as alloc}
										<tr>
											<td class="font-mono text-sm font-semibold text-ink-0">{alloc.ip_address}</td>
											<td class="font-mono text-xs whitespace-nowrap">{alloc.port_id || '-'}</td>
											<td class="text-xs text-ink-1">{alloc.device_owner || '-'}</td>
											<td class="font-mono text-xs whitespace-nowrap">{alloc.device_id || '-'}</td>
											<td class="font-mono text-xs whitespace-nowrap">{alloc.project_id || '-'}</td>
											<td class="font-mono text-xs font-medium text-ink-0">{alloc.binding_host_id || '-'}</td>
										</tr>
									{/each}
								</tbody>
							</table>
						</TableShell>
						<Pagination
							page={allocationPage}
							totalPages={allocationTotalPages}
							hasPrev={allocationPage > 1}
							hasNext={allocationPage < allocationTotalPages}
							onPrev={() => (allocationPage = Math.max(1, allocationPage - 1))}
							onNext={() => (allocationPage = Math.min(allocationTotalPages, allocationPage + 1))}
							total={subnet.allocations.length}
							pageSize={RESOURCE_PAGE_SIZE}
						/>
					{/if}
				{:else}
					<SectionHeader
						title={t('subnetDetailPage.ports')}
						meta={t('subnetDetailPage.totalCount', { count: subnet.ports.length })}
						class="mb-3"
					/>
					{#if subnet.ports.length === 0}
						<EmptyState headline={t('subnetDetailPage.portsEmpty')} description={t('subnetDetailPage.portsEmptyDescription')} />
					{:else}
						<TableShell density="compact">
							<table class="subnet-table subnet-table-ports">
								<thead>
									<tr class="text-xs uppercase tracking-wide">
										<th>{t('subnetDetailPage.portId')}</th>
										<th>{t('subnetDetailPage.portName')}</th>
										<th>{t('subnetDetailPage.status')}</th>
										<th>{t('subnetDetailPage.macAddress')}</th>
										<th>{t('subnetDetailPage.subnetIp')}</th>
										<th>{t('subnetDetailPage.deviceOwner')}</th>
										<th>{t('subnetDetailPage.deviceId')}</th>
										<th>
											{t('subnetDetailPage.actualNode')}
											<span class="block text-xs normal-case text-ink-2 font-normal">{t('subnetDetailPage.bindingHost')}</span>
										</th>
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
											<td class="text-xs text-ink-1">{port.device_owner || '-'}</td>
											<td class="font-mono text-xs whitespace-nowrap">{port.device_id || '-'}</td>
											<td class="font-mono text-xs font-medium text-ink-0">{port.binding_host_id || '-'}</td>
										</tr>
									{/each}
								</tbody>
							</table>
						</TableShell>
						<Pagination
							page={portPage}
							totalPages={portTotalPages}
							hasPrev={portPage > 1}
							hasNext={portPage < portTotalPages}
							onPrev={() => (portPage = Math.max(1, portPage - 1))}
							onNext={() => (portPage = Math.min(portTotalPages, portPage + 1))}
							total={subnet.ports.length}
							pageSize={RESOURCE_PAGE_SIZE}
						/>
					{/if}
				{/if}
			</Card>
		</div>
	{/if}
</PageShell>

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
