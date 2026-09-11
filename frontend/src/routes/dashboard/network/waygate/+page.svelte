<script lang="ts">
	import { untrack } from 'svelte';
	import { auth } from '$lib/stores/auth';
	import { siteConfig } from '$lib/config/site';
	import { api, ApiError } from '$lib/api/client';
	import { toast } from '$lib/stores/toast';
	import { confirmDialog } from '$lib/stores/confirm.svelte';
	import { createAutoRefresh } from '$lib/utils/autoRefresh.svelte';
	import { downloadBlobAs } from '$lib/utils/downloadBlob';
	import AutoRefreshControl from '$lib/components/AutoRefreshControl.svelte';
	import PageHeader from '$lib/components/ui/PageHeader.svelte';
	import LoadingSkeleton from '$lib/components/LoadingSkeleton.svelte';
	import TableShell from '$lib/components/ui/TableShell.svelte';
	import FormModal from '$lib/components/ui/FormModal.svelte';
	import Field from '$lib/components/ui/Field.svelte';
	import TextInput from '$lib/components/ui/TextInput.svelte';
	import SelectInput from '$lib/components/ui/SelectInput.svelte';
	import StatusChip from '$lib/components/ui/StatusChip.svelte';
	import SlidePanel from '$lib/components/SlidePanel.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import Alert from '$lib/components/ui/Alert.svelte';
	import Modal from '$lib/components/ui/Modal.svelte';
	import Card from '$lib/components/ui/Card.svelte';
	import BulkSelectionOverlay from '$lib/components/ui/BulkSelectionOverlay.svelte';
	import SelectionCheckbox from '$lib/components/ui/SelectionCheckbox.svelte';
	import SelectionToolbar from '$lib/components/ui/SelectionToolbar.svelte';
	import * as waygateApi from '$lib/api/waygate';
	import type { WaygateServer, WaygateClient, WaygateNetworkAttachment } from '$lib/types/waygate';
	import { createResourceSelection } from '$lib/utils/resourceSelection.svelte';
	import { executeBulkMutations } from '$lib/utils/bulkActions';

	const token = $derived($auth.token ?? undefined);
	const projectId = $derived($auth.projectId ?? undefined);
	const waygateConfigured = $derived($siteConfig.services?.waygate ?? false);

	let servers = $state<WaygateServer[]>([]);
	let loading = $state(true);
	let refreshing = $state(false);
	let error = $state('');
	let selection = createResourceSelection();
	let busy = $state(false);
	let selectableIds = $derived(new Set(servers.map((server) => server.id)));
	let selectedCount = $derived([...selectableIds].filter((id) => selection.ids.has(id)).length);
	let allSelected = $derived(selectableIds.size > 0 && selectedCount === selectableIds.size);
	let indeterminate = $derived(selectedCount > 0 && !allSelected);

	async function bulkDeleteServers() {
		const ids = [...selection.ids];
		if (ids.length === 0) return;
		if (!await confirmDialog(`${ids.length}개 Waygate 서버를 삭제하시겠습니까?`)) return;
		const tokenSnapshot = token;
		const projectSnapshot = projectId;
		busy = true;
		try {
			const results = await executeBulkMutations(ids, (id) => waygateApi.deleteServer(id, tokenSnapshot, projectSnapshot));
			const succeeded = results.filter((result) => result.ok).map((result) => result.id);
			if (projectSnapshot === projectId) selection.remove(succeeded);
			if (succeeded.length > 0) toast.success(`${succeeded.length}개 Waygate 서버 삭제가 시작되었습니다`);
			const failedCount = results.length - succeeded.length;
			if (failedCount > 0) toast.error(`${failedCount}개 Waygate 서버 삭제에 실패했습니다.`);
			if (projectSnapshot === projectId) await fetchServers();
		} finally {
			busy = false;
		}
	}

	// 서버 생성 모달
	let showCreateModal = $state(false);
	let newServerName = $state('');
	let creating = $state(false);
	let createError = $state('');

	// 상세 패널
	let selectedServerId = $state<string | null>(null);
	const selectedServer = $derived(servers.find((s) => s.id === selectedServerId) ?? null);

	async function fetchServers(opts?: { refresh?: boolean }) {
		try {
			servers = await waygateApi.listServers(token, projectId);
			if (selection.count > 0) selection.retain(servers.map((server) => server.id));
			error = '';
		} catch (e) {
			error = e instanceof ApiError ? `조회 실패 (${e.status})` : '서버 오류';
		} finally {
			loading = false;
		}
	}

	async function forceRefresh() {
		refreshing = true;
		try {
			await fetchServers({ refresh: true });
		} finally {
			refreshing = false;
		}
	}

	const ar = createAutoRefresh(() => fetchServers(), {
		storageKey: 'dashboard-network-waygate',
		defaultActive: true,
		defaultInterval: 15,
		intervalOptions: [10, 15, 30, 60],
		invokeOnMount: false,
	});

	$effect(() => {
		const pid = $auth.projectId;
		if (!pid) return;
		untrack(() => {
			selection.clear();
			loading = true;
			void fetchServers();
		});
	});

	async function createServer() {
		creating = true;
		createError = '';
		try {
			await waygateApi.createServer(newServerName.trim(), token, projectId);
			showCreateModal = false;
			newServerName = '';
			toast.success('Waygate 서버 생성이 시작되었습니다');
			await fetchServers();
		} catch (e) {
			createError = e instanceof ApiError ? e.message : '생성 실패';
		} finally {
			creating = false;
		}
	}

	async function deleteServer(server: WaygateServer) {
		if (!(await confirmDialog(`Waygate 서버 "${server.name}"을 삭제하시겠습니까?`))) return;
		try {
			await waygateApi.deleteServer(server.id, token, projectId);
			toast.success('Waygate 서버 삭제가 시작되었습니다');
			if (selectedServerId === server.id) selectedServerId = null;
			await fetchServers();
		} catch (e) {
			toast.error('삭제 실패: ' + (e instanceof ApiError ? e.message : String(e)));
		}
	}

	function openPanel(id: string) {
		selectedServerId = id;
	}
	function closePanel() {
		selectedServerId = null;
	}

	// ---- 클라이언트(peer) 관리 ----
	let clients = $state<WaygateClient[]>([]);
	let clientsLoading = $state(false);
	let clientsError = $state('');

	async function fetchClients(serverId: string) {
		clientsLoading = true;
		try {
			clients = await waygateApi.listClients(serverId, token, projectId);
			clientsError = '';
		} catch (e) {
			clientsError = e instanceof ApiError ? e.message : '클라이언트 조회 실패';
		} finally {
			clientsLoading = false;
		}
	}

	$effect(() => {
		const id = selectedServerId;
		if (!id) {
			clients = [];
			attachments = [];
			return;
		}
		untrack(() => {
			fetchClients(id);
			fetchAttachments(id);
		});
	});

	// 상세 패널이 열려있는 동안 서버 상태 + 클라이언트 상태를 함께 갱신
	const panelAr = createAutoRefresh(
		() => {
			if (!selectedServerId) return;
			fetchServers();
			fetchClients(selectedServerId);
		},
		{
			storageKey: 'dashboard-network-waygate-detail',
			defaultActive: true,
			defaultInterval: 15,
			intervalOptions: [10, 15, 30, 60],
			invokeOnMount: false,
		}
	);

	let showClientModal = $state(false);
	let newClientName = $state('');
	let clientCreating = $state(false);
	let clientCreateError = $state('');

	async function createClient() {
		if (!selectedServerId) return;
		clientCreating = true;
		clientCreateError = '';
		try {
			const result = await waygateApi.createClient(
				selectedServerId,
				{ name: newClientName.trim() },
				token,
				projectId
			);
			showClientModal = false;
			newClientName = '';
			toast.success('Waygate 클라이언트가 발급되었습니다');
			// 발급 직후 응답에 평문 .conf가 포함되어 있으므로 바로 다운로드 제공
			const blob = new Blob([result.tunnel_conf], { type: 'text/plain' });
			downloadBlobAs(blob, `${result.name}.conf`);
			await fetchClients(selectedServerId);
		} catch (e) {
			clientCreateError = e instanceof ApiError ? e.message : '클라이언트 발급 실패';
		} finally {
			clientCreating = false;
		}
	}

	async function toggleClient(client: WaygateClient) {
		if (!selectedServerId) return;
		try {
			await waygateApi.updateClient(
				selectedServerId,
				client.id,
				{ enabled: !client.enabled },
				token,
				projectId
			);
			await fetchClients(selectedServerId);
		} catch (e) {
			toast.error('상태 변경 실패: ' + (e instanceof ApiError ? e.message : String(e)));
		}
	}

	async function deleteClient(client: WaygateClient) {
		if (!selectedServerId) return;
		if (!(await confirmDialog(`클라이언트 "${client.name}"을 삭제하시겠습니까?`))) return;
		try {
			await waygateApi.deleteClient(selectedServerId, client.id, token, projectId);
			toast.success('클라이언트가 삭제되었습니다');
			await fetchClients(selectedServerId);
		} catch (e) {
			toast.error('삭제 실패: ' + (e instanceof ApiError ? e.message : String(e)));
		}
	}

	let downloadingClientId = $state<string | null>(null);

	async function downloadConfig(client: WaygateClient) {
		if (!selectedServerId) return;
		downloadingClientId = client.id;
		try {
			const { blob, filename } = await waygateApi.downloadClientConfig(
				selectedServerId,
				client.id,
				token,
				projectId
			);
			downloadBlobAs(blob, filename);
		} catch (e) {
			toast.error('다운로드 실패: ' + (e instanceof ApiError ? e.message : String(e)));
		} finally {
			downloadingClientId = null;
		}
	}

	// ---- QR 코드 (프론트 생성 — 백엔드는 .conf 텍스트만 제공) ----
	let qrClient = $state<WaygateClient | null>(null);
	let qrDataUrl = $state('');
	let qrLoading = $state(false);
	let qrError = $state('');

	async function openQr(client: WaygateClient) {
		if (!selectedServerId) return;
		qrClient = client;
		qrDataUrl = '';
		qrError = '';
		qrLoading = true;
		try {
			const text = await waygateApi.getClientConfigText(selectedServerId, client.id, token, projectId);
			// qrcode 는 브라우저 전용 — SSR 회피를 위해 동적 import
			const QRCode = (await import('qrcode')).default;
			qrDataUrl = await QRCode.toDataURL(text, { errorCorrectionLevel: 'M', margin: 2, width: 320 });
		} catch (e) {
			qrError = e instanceof ApiError ? e.message : 'QR 생성 실패';
		} finally {
			qrLoading = false;
		}
	}

	function closeQr() {
		qrClient = null;
		qrDataUrl = '';
		qrError = '';
	}

	// ---- 네트워크 연결 (Phase 2 — 멀티 NIC + SNAT) ----
	let attachments = $state<WaygateNetworkAttachment[]>([]);
	let attachmentsLoading = $state(false);
	let attachmentsError = $state('');
	let showAttachModal = $state(false);
	let availableNetworks = $state<{ id: string; name: string }[]>([]);
	let attachNetworkId = $state('');
	let attaching = $state(false);
	let attachError = $state('');

	async function fetchAttachments(serverId: string) {
		attachmentsLoading = true;
		try {
			attachments = await waygateApi.listAttachments(serverId, token, projectId);
			attachmentsError = '';
		} catch (e) {
			attachmentsError = e instanceof ApiError ? e.message : '네트워크 연결 조회 실패';
		} finally {
			attachmentsLoading = false;
		}
	}

	async function openAttachModal() {
		showAttachModal = true;
		attachError = '';
		attachNetworkId = '';
		try {
			availableNetworks = await api.get<{ id: string; name: string }[]>('/api/v1/networks', token, projectId);
		} catch {
			availableNetworks = [];
		}
	}

	async function submitAttach() {
		if (!selectedServerId || !attachNetworkId) return;
		attaching = true;
		attachError = '';
		try {
			await waygateApi.attachNetwork(selectedServerId, { network_id: attachNetworkId }, token, projectId);
			showAttachModal = false;
			toast.success('네트워크 연결이 시작되었습니다');
			await fetchAttachments(selectedServerId);
		} catch (e) {
			attachError = e instanceof ApiError ? e.message : '네트워크 연결 실패';
		} finally {
			attaching = false;
		}
	}

	async function detachNetwork(att: WaygateNetworkAttachment) {
		if (!selectedServerId) return;
		if (!(await confirmDialog(`네트워크 연결(${att.cidr ?? att.network_id})을 해제하시겠습니까?`))) return;
		try {
			await waygateApi.detachNetwork(selectedServerId, att.id, token, projectId);
			toast.success('네트워크 연결이 해제되었습니다');
			await fetchAttachments(selectedServerId);
		} catch (e) {
			toast.error('해제 실패: ' + (e instanceof ApiError ? e.message : String(e)));
		}
	}

	// ---- 백업 / 마이그레이션 (Phase 3) ----
	let showExportModal = $state(false);
	let exportPassphrase = $state('');
	let exporting = $state(false);
	let exportError = $state('');

	let showImportModal = $state(false);
	let importPassphrase = $state('');
	let importFile = $state<File | null>(null);
	let importing = $state(false);
	let importError = $state('');

	async function submitExport() {
		if (!selectedServerId || !selectedServer) return;
		exporting = true;
		exportError = '';
		try {
			const bundle = await waygateApi.exportServer(selectedServerId, exportPassphrase, token, projectId);
			const blob = new Blob([JSON.stringify(bundle, null, 2)], { type: 'application/json' });
			downloadBlobAs(blob, `${selectedServer.name}-waygate-export.json`);
			showExportModal = false;
			exportPassphrase = '';
			toast.success('설정을 내보냈습니다');
		} catch (e) {
			exportError = e instanceof ApiError ? e.message : '내보내기 실패';
		} finally {
			exporting = false;
		}
	}

	async function submitImport() {
		if (!selectedServerId || !importFile) return;
		importing = true;
		importError = '';
		try {
			const text = await importFile.text();
			const bundle = JSON.parse(text);
			const result = await waygateApi.importServer(
				selectedServerId,
				importPassphrase,
				bundle,
				token,
				projectId
			);
			showImportModal = false;
			importPassphrase = '';
			importFile = null;
			const skippedMsg = result.skipped.length ? ` (${result.skipped.length}개 건너뜀)` : '';
			toast.success(`${result.imported}개 클라이언트를 가져왔습니다${skippedMsg}`);
			await fetchClients(selectedServerId);
		} catch (e) {
			if (e instanceof SyntaxError) importError = '번들 JSON 파싱에 실패했습니다';
			else importError = e instanceof ApiError ? e.message : '가져오기 실패';
		} finally {
			importing = false;
		}
	}

	function clientStatusLabel(client: WaygateClient): string {
		if (!client.enabled) return 'disabled';
		return client.online ? 'ONLINE' : 'OFFLINE';
	}

	function formatDate(iso: string | null): string {
		if (!iso) return '-';
		try {
			return new Date(iso).toLocaleString('ko');
		} catch {
			return iso;
		}
	}
</script>

<FormModal
	bind:open={showCreateModal}
	title="Waygate 서버 생성"
	submitLabel="생성"
	submitting={creating}
	onSubmit={createServer}
	onClose={() => { showCreateModal = false; createError = ''; }}
>
	<div class="space-y-4">
		<Field label="이름" help="비워두면 자동으로 생성됩니다">
			<TextInput bind:value={newServerName} placeholder="waygate-gateway" />
		</Field>
		{#if createError}
			<p class="text-sm text-[var(--color-state-danger)]">{createError}</p>
		{/if}
	</div>
</FormModal>

<div class="bulk-selection-page p-4 md:p-8">
	<PageHeader breadcrumb="NETWORK / WAYGATE" title="Waygate">
		{#snippet actions()}
			<AutoRefreshControl
				bind:active={ar.active}
				bind:intervalSeconds={ar.intervalSeconds}
				intervalOptions={ar.intervalOptions}
				refreshing={refreshing}
				onManualRefresh={forceRefresh}
			/>
			{#if waygateConfigured}
				<Button onclick={() => { showCreateModal = true; createError = ''; }} variant="accent" size="sm">
					+ Waygate 서버 생성
				</Button>
			{/if}
		{/snippet}
	</PageHeader>

	{#if !waygateConfigured}
		<Alert tone="warning" class="mb-4">
			관리자가 아직 Waygate 기능을 설정하지 않았습니다. (afterglow.conf [waygate] provider_network_id / image_id 필요)
		</Alert>
	{/if}

	{#if error}
		<Alert tone="danger" class="mb-4">{error}</Alert>
	{/if}

	{#if loading}
		<LoadingSkeleton variant="table" rows={5} />
	{:else if servers.length === 0}
		<div class="text-center py-20 text-[var(--color-ink-3)]">
			<div class="text-5xl mb-4">🔐</div>
			<div class="text-lg">Waygate 서버가 없습니다</div>
			<p class="text-sm text-[var(--color-ink-3)] mt-2">테넌트 네트워크로부터 안전한 Waygate 연결을 생성하세요.</p>
		</div>
	{:else}
		<TableShell>
			<table>
				<thead>
					<tr>
						<th>
							<SelectionToolbar
								label="Waygate 서버"
								ariaLabel="Waygate 서버 전체 선택"
								checked={allSelected}
								indeterminate={indeterminate}
								selectedCount={selectedCount}
								disabled={busy || selectableIds.size === 0}
								onToggle={() => selection.toggleAll(selectableIds)}
							/>
						</th>
						<th>상태</th>
						<th>엔드포인트</th>
						<th>터널 CIDR</th>
						<th>피어 수</th>
						<th>생성일</th>
						<th></th>
					</tr>
				</thead>
				<tbody>
					{#each servers as server (server.id)}
						<tr class="resource-selection-surface cursor-pointer" data-selected={selection.has(server.id)} onclick={() => openPanel(server.id)}>
							<td class="text-[var(--color-ink-0)]">
								<SelectionCheckbox
									checked={selection.has(server.id)}
									disabled={busy}
									ariaLabel={`${server.name} 선택`}
									onclick={() => selection.toggle(server.id)}
								/>
								<span class="ml-2">{server.name}</span>
							</td>
							<td><StatusChip status={server.status} /></td>
							<td class="text-[var(--color-ink-2)] text-xs font-mono">{server.endpoint_ip ?? '-'}</td>
							<td class="text-[var(--color-ink-2)] text-xs font-mono">{server.tunnel_cidr}</td>
							<td class="text-[var(--color-ink-2)] text-xs">{server.peer_count ?? '-'}</td>
							<td class="text-[var(--color-ink-2)] text-xs">{formatDate(server.created_at)}</td>
							<td>
								<button
									onclick={(e) => { e.stopPropagation(); deleteServer(server); }}
									class="text-xs text-[var(--color-state-danger)] hover:opacity-80"
								>삭제</button>
							</td>
						</tr>
					{/each}
				</tbody>
			</table>
		</TableShell>
	{/if}
</div>
<BulkSelectionOverlay
	count={selection.count}
	ariaLabel="선택한 Waygate 서버 일괄 작업"
	actions={[{ key: 'delete', label: '삭제', tone: 'danger', onAction: bulkDeleteServers }]}
	{busy}
	onClear={() => selection.clear()}
/>

{#if selectedServer}
	<SlidePanel onClose={closePanel} ariaLabel="Waygate 서버 상세" width="w-full md:w-[70vw] max-w-3xl" storageKey="slidePanel.waygate-detail.width">
		<div class="p-6">
			<div class="mb-5 flex items-center justify-between">
				<!-- 닫기 버튼은 SlidePanel 이 제공한다(`[data-slide-panel-close]`) -->
				<AutoRefreshControl
					bind:active={panelAr.active}
					bind:intervalSeconds={panelAr.intervalSeconds}
					intervalOptions={panelAr.intervalOptions}
					refreshing={clientsLoading}
					onManualRefresh={() => { fetchServers(); if (selectedServerId) fetchClients(selectedServerId); }}
				/>
			</div>

			<div class="flex items-start justify-between mb-6">
				<div>
					<h2 class="text-xl font-semibold text-[var(--color-ink-0)]">{selectedServer.name}</h2>
					<div class="mt-1"><StatusChip status={selectedServer.status} /></div>
				</div>
				<Button onclick={() => deleteServer(selectedServer)} variant="danger-outline" size="sm">서버 삭제</Button>
			</div>

			{#if selectedServer.status_reason}
				<Alert tone="warning" class="mb-4">{selectedServer.status_reason}</Alert>
			{/if}

			<dl class="grid grid-cols-2 gap-x-6 gap-y-3 text-sm mb-8 bg-[var(--color-surface-raised)] border border-[var(--color-line)] rounded-xl p-4">
				<div>
					<dt class="text-xs text-[var(--color-ink-3)] uppercase tracking-wide">엔드포인트</dt>
					<dd class="text-[var(--color-ink-1)] font-mono">{selectedServer.endpoint_ip ?? '-'}:{selectedServer.listen_port}</dd>
				</div>
				<div>
					<dt class="text-xs text-[var(--color-ink-3)] uppercase tracking-wide">터널 CIDR</dt>
					<dd class="text-[var(--color-ink-1)] font-mono">{selectedServer.tunnel_cidr}</dd>
				</div>
				<div>
					<dt class="text-xs text-[var(--color-ink-3)] uppercase tracking-wide">DNS</dt>
					<dd class="text-[var(--color-ink-1)]">{selectedServer.dns ?? '-'}</dd>
				</div>
				<div>
					<dt class="text-xs text-[var(--color-ink-3)] uppercase tracking-wide">서버 공개키</dt>
					<dd class="text-[var(--color-ink-1)] font-mono text-xs break-all">{selectedServer.server_public_key ?? '(에이전트 등록 대기 중)'}</dd>
				</div>
				<div>
					<dt class="text-xs text-[var(--color-ink-3)] uppercase tracking-wide">마지막 상태 보고</dt>
					<dd class="text-[var(--color-ink-1)]">{formatDate(selectedServer.last_status_reported_at)}</dd>
				</div>
				<div>
					<dt class="text-xs text-[var(--color-ink-3)] uppercase tracking-wide">피어 수</dt>
					<dd class="text-[var(--color-ink-1)]">{selectedServer.peer_count ?? '-'}</dd>
				</div>
			</dl>

			<div class="flex items-center justify-between mb-3">
				<h3 class="text-sm font-medium text-[var(--color-ink-1)]">클라이언트</h3>
				<Button
					onclick={() => { showClientModal = true; clientCreateError = ''; }}
					variant="accent"
					size="sm"
					disabled={selectedServer.status !== 'ACTIVE'}
					title={selectedServer.status !== 'ACTIVE' ? 'Waygate 서버가 ACTIVE 상태여야 클라이언트를 발급할 수 있습니다' : undefined}
				>+ 클라이언트 발급</Button>
			</div>

			{#if clientsError}
				<Alert tone="danger" class="mb-4">{clientsError}</Alert>
			{/if}

			{#if clientsLoading && clients.length === 0}
				<LoadingSkeleton variant="table" rows={3} />
			{:else if clients.length === 0}
				<div class="text-center py-10 text-[var(--color-ink-3)] bg-[var(--color-surface-raised)] border border-[var(--color-line)] rounded-xl">
					<div class="text-sm">발급된 클라이언트가 없습니다</div>
				</div>
			{:else}
				<TableShell>
					<table>
						<thead>
							<tr>
								<th>이름</th>
								<th>터널 IP</th>
								<th>상태</th>
								<th>마지막 핸드셰이크</th>
								<th>생성일</th>
								<th></th>
							</tr>
						</thead>
						<tbody>
							{#each clients as client (client.id)}
								<tr>
									<td class="text-[var(--color-ink-0)]">{client.name}</td>
									<td class="text-[var(--color-ink-2)] text-xs font-mono">{client.tunnel_ip}</td>
									<td><StatusChip status={clientStatusLabel(client)} /></td>
									<td class="text-[var(--color-ink-2)] text-xs">{formatDate(client.last_handshake_at)}</td>
									<td class="text-[var(--color-ink-2)] text-xs">{formatDate(client.created_at)}</td>
									<td>
										<div class="flex gap-2 justify-end">
											<button
												onclick={() => downloadConfig(client)}
												disabled={downloadingClientId === client.id}
												class="text-xs text-[var(--color-accent)] hover:opacity-80 disabled:opacity-50"
											>{downloadingClientId === client.id ? '다운로드 중...' : '.conf 다운로드'}</button>
											<button
												onclick={() => openQr(client)}
												class="text-xs text-[var(--color-accent)] hover:opacity-80"
											>QR</button>
											<button onclick={() => toggleClient(client)} class="text-xs text-[var(--color-ink-2)] hover:text-[var(--color-ink-0)]">
												{client.enabled ? '비활성화' : '활성화'}
											</button>
											<button onclick={() => deleteClient(client)} class="text-xs text-[var(--color-state-danger)] hover:opacity-80">삭제</button>
										</div>
									</td>
								</tr>
							{/each}
						</tbody>
					</table>
				</TableShell>
			{/if}

			<p class="text-xs text-[var(--color-ink-3)] mt-4">
				<code>.conf</code> 파일을 다운로드하거나, <strong>QR</strong> 버튼으로 모바일 WireGuard 앱에서 바로 스캔해 등록할 수 있습니다.
			</p>

			<div class="flex items-center justify-between mb-3 mt-8">
				<h3 class="text-sm font-medium text-[var(--color-ink-1)]">연결된 네트워크</h3>
				<Button
					onclick={openAttachModal}
					variant="secondary"
					size="sm"
					disabled={selectedServer.status !== 'ACTIVE'}
					title={selectedServer.status !== 'ACTIVE' ? 'Waygate 서버가 ACTIVE 상태여야 네트워크를 연결할 수 있습니다' : undefined}
				>+ 네트워크 연결</Button>
			</div>

			{#if attachmentsError}
				<Alert tone="danger" class="mb-4">{attachmentsError}</Alert>
			{/if}

			{#if attachmentsLoading && attachments.length === 0}
				<LoadingSkeleton variant="table" rows={2} />
			{:else if attachments.length === 0}
				<div class="text-center py-8 text-[var(--color-ink-3)] bg-[var(--color-surface-raised)] border border-[var(--color-line)] rounded-xl text-sm">
					연결된 테넌트 네트워크가 없습니다. 연결하면 VPN 클라이언트가 그 네트워크 내부로 접근할 수 있습니다.
				</div>
			{:else}
				<TableShell>
					<table>
						<thead>
							<tr>
								<th>네트워크</th>
								<th>CIDR</th>
								<th>NAT</th>
								<th>상태</th>
								<th></th>
							</tr>
						</thead>
						<tbody>
							{#each attachments as att (att.id)}
								<tr>
									<td class="text-[var(--color-ink-2)] text-xs font-mono">{att.network_id}</td>
									<td class="text-[var(--color-ink-2)] text-xs font-mono">{att.cidr ?? '-'}</td>
									<td class="text-[var(--color-ink-2)] text-xs">{att.nat_mode}</td>
									<td><StatusChip status={att.status} /></td>
									<td>
										<button onclick={() => detachNetwork(att)} class="text-xs text-[var(--color-state-danger)] hover:opacity-80">해제</button>
									</td>
								</tr>
							{/each}
						</tbody>
					</table>
				</TableShell>
			{/if}

			<div class="flex items-center justify-between mb-3 mt-8">
				<h3 class="text-sm font-medium text-[var(--color-ink-1)]">백업 / 마이그레이션</h3>
			</div>
			<div class="flex gap-2">
				<Button onclick={() => { showExportModal = true; exportError = ''; }} variant="secondary" size="sm">설정 내보내기</Button>
				<Button
					onclick={() => { showImportModal = true; importError = ''; }}
					variant="secondary"
					size="sm"
					disabled={selectedServer.status !== 'ACTIVE'}
					title={selectedServer.status !== 'ACTIVE' ? 'Waygate 서버가 ACTIVE 상태여야 가져올 수 있습니다' : undefined}
				>가져오기</Button>
			</div>
			<p class="text-xs text-[var(--color-ink-3)] mt-2">
				클라이언트 키는 입력한 패스프레이즈로 암호화되어 번들에 저장됩니다. 다른 Waygate 서버로 이전할 때 같은 패스프레이즈로 가져오세요.
				(서버 키는 이전되지 않으므로 가져온 뒤 클라이언트는 <code>.conf</code> 를 다시 내려받아야 합니다.)
			</p>
		</div>
	</SlidePanel>
{/if}

<FormModal
	bind:open={showClientModal}
	title="Waygate 클라이언트 발급"
	submitLabel="발급"
	submitting={clientCreating}
	onSubmit={createClient}
	onClose={() => { showClientModal = false; clientCreateError = ''; }}
>
	<div class="space-y-4">
		<Field label="이름" required>
			<TextInput bind:value={newClientName} placeholder="my-laptop" />
		</Field>
		{#if clientCreateError}
			<p class="text-sm text-[var(--color-state-danger)]">{clientCreateError}</p>
		{/if}
	</div>
</FormModal>

<Modal open={qrClient !== null} onClose={closeQr} ariaLabel="Waygate 클라이언트 QR 코드">
	<Card surface="modal" padding="lg" class="w-[min(100%-2rem,22rem)] mx-4">
		<div class="flex items-center justify-between mb-4">
			<h2 class="text-sm font-medium text-[var(--color-ink-0)]">
				{qrClient?.name} — QR 코드
			</h2>
			<button onclick={closeQr} class="text-[var(--color-ink-2)] hover:text-[var(--color-ink-0)] text-sm">✕</button>
		</div>
		{#if qrLoading}
			<div class="py-16 text-center text-sm text-[var(--color-ink-3)]">QR 생성 중...</div>
		{:else if qrError}
			<Alert tone="danger">{qrError}</Alert>
		{:else if qrDataUrl}
			<div class="flex flex-col items-center gap-3">
				<img src={qrDataUrl} alt="WireGuard 설정 QR 코드" width="288" height="288" class="rounded-lg bg-surface-base p-2" />
				<p class="text-xs text-[var(--color-ink-3)] text-center">
					모바일 WireGuard 앱에서 "QR 코드로 추가"를 선택해 스캔하세요.
				</p>
			</div>
		{/if}
	</Card>
</Modal>

<FormModal
	bind:open={showAttachModal}
	title="네트워크 연결"
	submitLabel="연결"
	submitting={attaching}
	onSubmit={submitAttach}
	onClose={() => { showAttachModal = false; attachError = ''; }}
>
	<div class="space-y-4">
		<Field label="테넌트 네트워크" required>
			{#if availableNetworks.length === 0}
				<p class="text-xs text-[var(--color-ink-3)]">사용 가능한 네트워크가 없거나 조회에 실패했습니다.</p>
			{:else}
				<SelectInput bind:value={attachNetworkId} ariaLabel="연결할 네트워크 선택">
					<option value="" disabled>네트워크 선택</option>
					{#each availableNetworks as net (net.id)}
						<option value={net.id}>{net.name} ({net.id.slice(0, 8)})</option>
					{/each}
				</SelectInput>
			{/if}
		</Field>
		<p class="text-xs text-[var(--color-ink-3)]">
			연결하면 VPN 클라이언트의 <code>.conf</code> AllowedIPs 에 이 네트워크 CIDR 이 추가됩니다.
			기존에 발급된 클라이언트는 <code>.conf</code> 를 다시 내려받아야 반영됩니다.
		</p>
		{#if attachError}
			<p class="text-sm text-[var(--color-state-danger)]">{attachError}</p>
		{/if}
	</div>
</FormModal>

<FormModal
	bind:open={showExportModal}
	title="설정 내보내기"
	submitLabel="내보내기"
	submitting={exporting}
	onSubmit={submitExport}
	onClose={() => { showExportModal = false; exportError = ''; }}
>
	<div class="space-y-4">
		<Field label="패스프레이즈" help="클라이언트 키를 암호화합니다 (8자 이상). 가져올 때 동일하게 입력해야 합니다." required>
			<TextInput bind:value={exportPassphrase} type="password" placeholder="8자 이상" />
		</Field>
		{#if exportError}
			<p class="text-sm text-[var(--color-state-danger)]">{exportError}</p>
		{/if}
	</div>
</FormModal>

<FormModal
	bind:open={showImportModal}
	title="설정 가져오기"
	submitLabel="가져오기"
	submitting={importing}
	onSubmit={submitImport}
	onClose={() => { showImportModal = false; importError = ''; importFile = null; }}
>
	<div class="space-y-4">
		<Field label="번들 파일 (.json)" required>
			<input
				type="file"
				accept="application/json,.json"
				class="text-sm text-[var(--color-ink-1)]"
				onchange={(e) => { importFile = (e.currentTarget as HTMLInputElement).files?.[0] ?? null; }}
			/>
		</Field>
		<Field label="패스프레이즈" help="내보낼 때 사용한 패스프레이즈" required>
			<TextInput bind:value={importPassphrase} type="password" />
		</Field>
		{#if importError}
			<p class="text-sm text-[var(--color-state-danger)]">{importError}</p>
		{/if}
	</div>
</FormModal>
