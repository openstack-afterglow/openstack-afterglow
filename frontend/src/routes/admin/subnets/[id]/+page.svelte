<script lang="ts">
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
		{ value: 'allocations', label: `할당 IP · ${subnet?.allocations.length ?? 0}` },
		{ value: 'ports', label: `포트 · ${subnet?.ports.length ?? 0}` },
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
				error = err.message || `서브넷 정보를 불러오지 못했습니다 (${err.status})`;
			} else {
				error = (err as Error).message || '서브넷 정보를 불러오지 못했습니다';
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
		breadcrumb="NETWORK / SUBNET DETAIL"
		title={subnet?.name ? `서브넷: ${subnet.name}` : '서브넷 상세'}
		subtitle="서브넷 풀 경계, 할당된 IP, 바인딩 포트, 실제 바인딩 노드 및 DHCP 에이전트 배치 현황을 확인합니다."
	>
		{#snippet actions()}
			<Button
				href={subnet?.network_id ? `/admin/networks/${subnet.network_id}` : '/admin/networks'}
				variant="outline"
				size="sm"
			>
				← 네트워크 상세
			</Button>
			<Button onclick={() => loadSubnet(true)} variant="subtle" size="sm" disabled={loading}>
				새로고침
			</Button>
		{/snippet}
	</PageHeader>

	{#if loading}
		<Card padding="lg">
			<div class="py-12 text-center text-sm text-ink-2">
				서브넷 정보를 불러오는 중...
			</div>
		</Card>
	{:else if error}
		<Alert tone="danger" title="서브넷 조회 실패">
			{error}
		</Alert>
	{:else if subnet}
		<div class="space-y-6">
			<!-- Overview Metadata Card -->
			<Card padding="lg">
				<SectionHeader title="서브넷 요약 정보" class="mb-4" />
				<dl class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-x-6 gap-y-4 text-sm">
					<div>
						<dt class="text-xs text-ink-2 mb-1">서브넷 ID</dt>
						<dd class="font-mono text-ink-0 break-all">{subnet.id}</dd>
					</div>
					<div>
						<dt class="text-xs text-ink-2 mb-1">서브넷 이름</dt>
						<dd class="font-medium text-ink-0">{subnet.name || '(이름 없음)'}</dd>
					</div>
					<div>
						<dt class="text-xs text-ink-2 mb-1">소속 네트워크</dt>
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
						<dt class="text-xs text-ink-2 mb-1">프로젝트 ID</dt>
						<dd class="font-mono text-ink-0 break-all">{subnet.project_id || '-'}</dd>
					</div>
					<div>
						<dt class="text-xs text-ink-2 mb-1">CIDR</dt>
						<dd class="font-mono text-ink-0">{subnet.cidr}</dd>
					</div>
					<div>
						<dt class="text-xs text-ink-2 mb-1">게이트웨이 IP</dt>
						<dd class="font-mono text-ink-0">{subnet.gateway_ip || '-'}</dd>
					</div>
					<div>
						<dt class="text-xs text-ink-2 mb-1">IP 버전</dt>
						<dd class="text-ink-0 font-medium">IPv{subnet.ip_version}</dd>
					</div>
					<div>
						<dt class="text-xs text-ink-2 mb-1">DHCP 활성화</dt>
						<dd>
							<Pill tone={subnet.dhcp_enabled ? 'success' : 'neutral'}>
								{subnet.dhcp_enabled ? '활성' : '비활성'}
							</Pill>
						</dd>
					</div>
				</dl>
			</Card>

			<!-- Summary StatTiles -->
			<div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-3.5">
				<StatTile
					label="CIDR / IP 버전"
					value={subnet.cidr}
					suffix={`IPv${subnet.ip_version}`}
					accent="blue"
				/>
				<StatTile
					label="할당 풀 수"
					value={subnet.allocation_pools.length}
					unit="개"
					accent="cyan"
				/>
				<StatTile
					label="할당된 IP 수"
					value={subnet.allocations.length}
					unit="개"
					accent="violet"
				/>
				<StatTile
					label="사용 중인 포트 수"
					value={subnet.ports.length}
					unit="개"
					accent="emerald"
				/>
			</div>

			<!-- Allocation Pools Section -->
			<Card padding="md">
				<SectionHeader
					title="할당 풀 (Allocation Pools)"
					meta={`총 ${subnet.allocation_pools.length}개`}
					class="mb-3"
				/>
				{#if subnet.allocation_pools.length === 0}
					<EmptyState headline="등록된 할당 풀이 없습니다" description="이 서브넷에 정의된 IP 할당 범위가 없습니다." />
				{:else}
					<TableShell density="compact">
						<table>
							<thead>
								<tr class="text-xs uppercase tracking-wide">
									<th>시작 IP (Start IP)</th>
									<th>종료 IP (End IP)</th>
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
					title="DHCP 배치 및 에이전트"
					meta={`총 ${subnet.dhcp_bindings.length}개`}
					class="mb-3"
				/>
				{#if !subnet.dhcp_agent_data_available}
					<Alert tone="warning" class="mb-3" title="DHCP 에이전트 스케줄러 정보 미제공">
						DHCP 에이전트 스케줄러 데이터를 불러올 수 없습니다. 포트 기반 DHCP 배치 데이터만 표시됩니다.
					</Alert>
				{/if}
				{#if subnet.dhcp_bindings.length === 0}
					<EmptyState headline="DHCP 배치 정보가 없습니다" description="이 서브넷에 등록된 DHCP 에이전트 또는 배치 포트가 없습니다." />
				{:else}
					<TableShell density="compact">
						<table class="subnet-table subnet-table-dhcp">
							<thead>
								<tr class="text-xs uppercase tracking-wide">
									<th>IP 주소</th>
									<th>출처</th>
									<th>호스트 (Host)</th>
									<th>바이너리</th>
									<th>가용구역 (AZ)</th>
									<th>에이전트 ID</th>
									<th>상태</th>
									<th>연관 포트</th>
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
												{binding.source === 'agent' ? '에이전트' : '포트'}
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
															{binding.alive ? '정상' : '중단'}
														</Pill>
													{/if}
													{#if binding.admin_state_up !== null}
														<Pill tone={binding.admin_state_up ? 'info' : 'neutral'}>
															{binding.admin_state_up ? 'UP' : 'DOWN'}
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
						title="서브넷 하위 리소스"
						meta="한 번에 하나의 목록만 표시합니다"
					/>
					<ToggleGroup
						value={activeResourceTab}
						options={resourceTabOptions}
						onchange={selectResourceTab}
						ariaLabel="서브넷 하위 리소스 탭"
						fullWidth
					/>
				</div>

				{#if activeResourceTab === 'allocations'}
					<SectionHeader
						title="할당된 IP (Allocated IPs)"
						meta={`총 ${subnet.allocations.length}개`}
						class="mb-3"
					/>
					{#if subnet.allocations.length === 0}
						<EmptyState headline="할당된 IP가 없습니다" description="이 서브넷에서 현재 고정 IP를 할당받은 포트나 디바이스가 없습니다." />
					{:else}
						<TableShell density="compact">
							<table class="subnet-table subnet-table-allocations">
								<thead>
									<tr class="text-xs uppercase tracking-wide">
										<th>IP 주소</th>
										<th>포트 ID</th>
										<th>디바이스 소유자</th>
										<th>디바이스 ID</th>
										<th>프로젝트 ID</th>
										<th>
											실제 노드
											<span class="block text-xs normal-case text-ink-2 font-normal">Neutron binding host</span>
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
						title="사용 중인 포트 (Ports)"
						meta={`총 ${subnet.ports.length}개`}
						class="mb-3"
					/>
					{#if subnet.ports.length === 0}
						<EmptyState headline="사용 중인 포트가 없습니다" description="이 서브넷에 바인딩된 포트가 없습니다." />
					{:else}
						<TableShell density="compact">
							<table class="subnet-table subnet-table-ports">
								<thead>
									<tr class="text-xs uppercase tracking-wide">
										<th>포트 ID</th>
										<th>포트 이름</th>
										<th>상태</th>
										<th>MAC 주소</th>
										<th>서브넷 IP</th>
										<th>디바이스 소유자</th>
										<th>디바이스 ID</th>
										<th>
											실제 노드
											<span class="block text-xs normal-case text-ink-2 font-normal">Neutron binding host</span>
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
