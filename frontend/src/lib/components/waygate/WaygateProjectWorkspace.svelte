<script lang="ts">
	import { tick, untrack } from 'svelte';
	import type { WaygateProjectScope } from '$lib/utils/waygateProjectScope';
	import { siteConfig } from '$lib/config/site';
	import { api, ApiError } from '$lib/api/client';
	import { toast } from '$lib/stores/toast';
	import { confirmDialog } from '$lib/stores/confirm.svelte';
	import { createAutoRefresh } from '$lib/utils/autoRefresh.svelte';
	import { downloadBlobAs } from '$lib/utils/downloadBlob';
	import AutoRefreshControl from '$lib/components/AutoRefreshControl.svelte';
	import TutorialStartButton from '$lib/tutorial/TutorialStartButton.svelte';
	import PageHeader from '$lib/components/ui/PageHeader.svelte';
	import LoadingSkeleton from '$lib/components/LoadingSkeleton.svelte';
	import TableShell from '$lib/components/ui/TableShell.svelte';
	import FormModal from '$lib/components/ui/FormModal.svelte';
	import Field from '$lib/components/ui/Field.svelte';
	import TextInput from '$lib/components/ui/TextInput.svelte';
	import SearchSelect from '$lib/components/ui/SearchSelect.svelte';
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
	import ClientSettingsFields from '$lib/components/waygate/ClientSettingsFields.svelte';
	import ClientTraffic from '$lib/components/waygate/ClientTraffic.svelte';
	import { appendClientTraffic, waygateTrafficFreshnessMs, type ClientTrafficHistory } from '$lib/utils/waygateTraffic';
	import { reconcileById, sameJsonValue } from '$lib/utils/reconcileById';
	import {
		emptyWaygateClientDraft,
		WAYGATE_KEEPALIVE_DEFAULT,
		waygateClientCreateBody,
		waygateClientDraft,
		waygateClientUpdateBody,
		waygateServerDraft,
		waygateServerCreateBody,
		waygateServerUpdateBody,
		type WaygateClientDraft,
		type WaygateClientDraftErrors,
	} from '$lib/utils/waygateClientSettings';
	import type { WaygateServer, WaygateClient, WaygateNetworkAttachment } from '$lib/types/waygate';
	import type { Network, NetworkDetail, SubnetDetail } from '$lib/types/networks';
	import { createResourceSelection } from '$lib/utils/resourceSelection.svelte';
	import { executeBulkMutations } from '$lib/utils/bulkActions';

	let { scope, admin = false }: { scope: WaygateProjectScope; admin?: boolean } = $props();
	// The parent keys this entire workspace by scope; credentials never change in place.
	const { token, projectId, isCurrent } = untrack(() => scope);
	const workspaceContext = untrack(() => admin);
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
		if (!isCurrent() || busy) return;
		const ids = [...selection.ids].filter((id) => selectableIds.has(id));
		if (ids.length === 0) return;
		if (!await confirmDialog(`${ids.length}개 Waygate 서버를 삭제하시겠습니까?`) || !isCurrent()) return;
		busy = true;
		try {
			const results = await executeBulkMutations(ids, (id) => {
				if (!isCurrent()) return Promise.reject(new Error('Waygate project changed'));
				return waygateApi.deleteServer(id, token, projectId);
			});
			if (!isCurrent()) return;
			const succeeded = results.filter((result) => result.ok).map((result) => result.id);
			selection.remove(succeeded);
			if (selectedServerId && succeeded.includes(selectedServerId)) closePanel();
			if (succeeded.length > 0) toast.success(`${succeeded.length}개 Waygate 서버 삭제가 시작되었습니다`);
			const failedCount = results.length - succeeded.length;
			if (failedCount > 0) toast.error(`${failedCount}개 Waygate 서버 삭제에 실패했습니다.`);
			await fetchServers(true);
		} finally {
			if (isCurrent()) busy = false;
		}
	}

	// 서버 생성 모달
	let showCreateModal = $state(false);
	let newServerDraft = $state<WaygateClientDraft>(waygateServerDraft());
	let newServerErrors = $state<WaygateClientDraftErrors>({});
	let newServerFields = $state<ReturnType<typeof ClientSettingsFields> | null>(null);
	let creating = $state(false);
	let createError = $state('');
	let showDefaultsModal = $state(false);
	let defaultsDraft = $state<WaygateClientDraft>(waygateServerDraft());
	let defaultsErrors = $state<WaygateClientDraftErrors>({});
	let defaultsFields = $state<ReturnType<typeof ClientSettingsFields> | null>(null);
	let defaultsSaving = $state(false);
	let defaultsError = $state('');

	function openDefaultsModal() {
		if (!captureDetail() || !selectedServer) return;
		defaultsDraft = waygateServerDraft(selectedServer);
		defaultsErrors = {};
		defaultsError = '';
		showDefaultsModal = true;
	}

	async function saveServerDefaults() {
		const detail = captureDetail();
		if (!detail || defaultsSaving) return;
		const parsed = waygateServerUpdateBody(defaultsDraft);
		if (!parsed.ok) {
			defaultsErrors = parsed.errors;
			await tick();
			if (detail.current()) defaultsFields?.focusFirstError();
			return;
		}
		defaultsErrors = {};
		defaultsError = '';
		defaultsSaving = true;
		try {
			const updated = await waygateApi.updateServer(detail.id, parsed.body, token, projectId);
			if (!detail.current()) return;
			serverRequest += 1;
			serverDetailRequest += 1;
			if (!sameJsonValue(selectedServer, updated)) servers = servers.map((server) => server.id === detail.id ? updated : server);
			showDefaultsModal = false;
			toast.success('서버 기본값을 저장했습니다. 상속 중인 클라이언트에 적용됩니다.');
			await fetchClients(detail.id, true);
		} catch (e) {
			if (detail.current()) defaultsError = e instanceof ApiError ? e.message : '서버 기본값 저장 실패';
		} finally {
			if (detail.current()) defaultsSaving = false;
		}
	}

	// 상세 패널
	let selectedServerId = $state<string | null>(null);
	const selectedServer = $derived(servers.find((s) => s.id === selectedServerId) ?? null);

	let serverRequest = 0;
	let serverInFlight: Promise<WaygateServer[]> | null = null;
	async function fetchServers(afterMutation = false) {
		if (!isCurrent()) return;
		while (serverInFlight) {
			if (!afterMutation) return;
			serverRequest += 1;
			await serverInFlight.catch(() => {});
			if (!isCurrent()) return;
		}
		const request = ++serverRequest;
		const pending = waygateApi.listServers(token, projectId);
		serverInFlight = pending;
		try {
			const next = await pending;
			if (!isCurrent() || request !== serverRequest) return;
			servers = reconcileById(servers, next);
			if (selection.count > 0) selection.retain(servers.map((server) => server.id));
			if (selectedServerId && !servers.some((server) => server.id === selectedServerId)) closePanel();
			error = '';
		} catch (e) {
			if (!isCurrent() || request !== serverRequest) return;
			error = e instanceof ApiError ? `조회 실패 (${e.status})` : '서버 오류';
		} finally {
			if (serverInFlight === pending) serverInFlight = null;
			if (isCurrent() && request === serverRequest) loading = false;
		}
	}

	async function forceRefresh() {
		if (!isCurrent()) return;
		refreshing = true;
		try {
			await fetchServers(true);
		} finally {
			if (isCurrent()) refreshing = false;
		}
	}

	const ar = createAutoRefresh(() => selectedServerId ? undefined : fetchServers(), {
		storageKey: workspaceContext ? 'admin-waygate' : 'dashboard-network-waygate',
		defaultActive: true,
		defaultInterval: 15,
		intervalOptions: [10, 15, 30, 60],
		invokeOnMount: false,
	});

	$effect(() => {
		untrack(() => { void fetchServers(); });
	});

	async function createServer() {
		if (!isCurrent() || creating) return;
		const parsed = waygateServerCreateBody(newServerDraft);
		if (!parsed.ok) {
			newServerErrors = parsed.errors;
			await tick();
			if (isCurrent()) newServerFields?.focusFirstError();
			return;
		}
		newServerErrors = {};
		creating = true;
		createError = '';
		try {
			await waygateApi.createServer(parsed.body, token, projectId);
			if (!isCurrent()) return;
			showCreateModal = false;
			newServerDraft = waygateServerDraft();
			toast.success('Waygate 서버 생성이 시작되었습니다');
			await fetchServers(true);
		} catch (e) {
			if (!isCurrent()) return;
			createError = e instanceof ApiError ? e.message : '생성 실패';
		} finally {
			if (isCurrent()) creating = false;
		}
	}

	async function deleteServer(server: WaygateServer) {
		if (!isCurrent()) return;
		if (!(await confirmDialog(`Waygate 서버 "${server.name}"을 삭제하시겠습니까?`)) || !isCurrent()) return;
		try {
			await waygateApi.deleteServer(server.id, token, projectId);
			if (!isCurrent()) return;
			toast.success('Waygate 서버 삭제가 시작되었습니다');
			if (selectedServerId === server.id) closePanel();
			await fetchServers(true);
		} catch (e) {
			if (!isCurrent()) return;
			toast.error('삭제 실패: ' + (e instanceof ApiError ? e.message : String(e)));
		}
	}

	let detailRevision = 0;
	let cancelPeerRound: (() => void) | null = null;
	let serverDetailRequest = 0;
	const serverDetailInFlight = new Map<string, Promise<WaygateServer>>();
	function captureDetail() {
		const id = selectedServerId;
		const revision = detailRevision;
		if (!isCurrent() || !id) return null;
		return { id, current: () => isCurrent() && revision === detailRevision && id === selectedServerId };
	}
	async function fetchSelectedServer(serverId: string, force = false) {
		const detail = captureDetail();
		if (!detail || detail.id !== serverId) return;
		if (serverDetailInFlight.has(serverId)) {
			if (!force) return;
			await serverDetailInFlight.get(serverId)!.catch(() => {});
			if (!detail.current()) return;
		}
		const request = ++serverDetailRequest;
		const pending = waygateApi.getServer(serverId, token, projectId);
		serverDetailInFlight.set(serverId, pending);
		try {
			const server = await pending;
			if (!detail.current() || request !== serverDetailRequest) return;
			serverRequest += 1;
			if (!sameJsonValue(selectedServer, server)) servers = servers.map((item) => item.id === serverId ? server : item);
		} catch (e) {
			if (!detail.current() || request !== serverDetailRequest) return;
			if (e instanceof ApiError && e.status === 404) {
				closePanel();
				await fetchServers(true);
			} else {
				toast.error('서버 상태 조회 실패: ' + (e instanceof ApiError ? e.message : String(e)));
			}
		} finally {
			if (serverDetailInFlight.get(serverId) === pending) serverDetailInFlight.delete(serverId);
		}
	}


	function resetDetail() {
		serverDetailRequest += 1;
		cancelPeerRound?.();
		cancelPeerRound = null;
		networkRequest += 1;
		visibleNetworks = [];
		networksLoading = false;
		detailRevision += 1;
		clientRequest += 1;
		mutatingClientIds = [];
		attachmentRequest += 1;
		clients = [];
		trafficHistories = {};
		clientsError = '';
		clientsLoading = false;
		clientsLoaded = false;
		attachments = [];
		attachmentsError = '';
		attachmentsLoading = false;
		attachmentsLoaded = false;
		showDefaultsModal = false;
		defaultsSaving = false;
		showClientModal = false;
		clientCreating = false;
		editingClient = null;
		clientSaving = false;
		downloadingClientId = null;
		closeQr();
		closeAttachModal();
		availableSubnets = [];
		attachNetworkId = '';
		attachSubnetId = '';
		subnetsLoading = false;
		attaching = false;
		showExportModal = false;
		exportPassphrase = '';
		exporting = false;
		showImportModal = false;
		importPassphrase = '';
		importFile = null;
		importing = false;
	}

	function openPanel(id: string) {
		if (!isCurrent() || !servers.some((server) => server.id === id)) return;
		resetDetail();
		serverRequest += 1;
		selectedServerId = id;
		void fetchSelectedServer(id, true);
		void fetchClients(id, true);
		void fetchAttachments(id, true);
		void fetchNetworks();
	}
	function closePanel() {
		resetDetail();
		selectedServerId = null;
	}

	// ---- 클라이언트(peer) 관리 ----
	let clients = $state<WaygateClient[]>([]);
	let clientsLoading = $state(false);
	let clientsLoaded = $state(false);
	let clientsError = $state('');
	// Real report history for the open server/project only; never shared across scopes.
	let trafficHistories = $state<Record<string, ClientTrafficHistory>>({});
	let trafficNow = $state(Date.now());
	let clientRequest = 0;
	const clientInFlight = new Map<string, Promise<WaygateClient[]>>();

	async function fetchClients(serverId: string, afterMutation = false) {
		const detail = captureDetail();
		if (!detail || serverId !== detail.id) return;
		if (afterMutation) clientRequest += 1;
		if (document.hidden) {
			clientsLoading = false;
			return;
		}
		while (clientInFlight.has(serverId)) {
			if (!afterMutation) return;
			clientRequest += 1;
			await clientInFlight.get(serverId)!.catch(() => {});
			if (!detail.current()) return;
			if (document.hidden) {
				clientsLoading = false;
				return;
			}
		}
		const request = ++clientRequest;
		clientsLoading = !clientsLoaded;
		const pending = waygateApi.listClients(serverId, token, projectId);
		clientInFlight.set(serverId, pending);
		try {
			const next = await pending;
			if (!detail.current() || request !== clientRequest) return;
			const now = Date.now();
			const histories: Record<string, ClientTrafficHistory> = {};
			let historiesChanged = false;
			let enabledCount = 0;
			for (const client of next) {
				if (!client.enabled) continue;
				enabledCount++;
				const previous = trafficHistories[client.id];
				const history = appendClientTraffic(previous, client, now, waygateTrafficFreshnessMs(client.report_interval_seconds, peerAr.intervalSeconds));
				histories[client.id] = history;
				if (history !== previous) historiesChanged = true;
			}
			if (historiesChanged || Object.keys(trafficHistories).length !== enabledCount) {
				trafficHistories = histories;
				trafficNow = now;
			}
			clients = reconcileById(clients, next);
			clientsError = '';
		} catch (e) {
			if (!detail.current() || request !== clientRequest) return;
			clientsError = e instanceof ApiError ? e.message : '클라이언트 조회 실패';
		} finally {
			if (clientInFlight.get(serverId) === pending) clientInFlight.delete(serverId);
			if (detail.current() && request === clientRequest) {
				clientsLoaded = true;
				clientsLoading = false;
			}
		}
	}


	// Stale reports become visibly stale even when auto-refresh is paused.
	$effect(() => {
		if (!selectedServerId) return;
		const timer = setInterval(() => { if (!document.hidden) trafficNow = Date.now(); }, 5000);
		return () => clearInterval(timer);
	});

	// Server/attachment metadata is independent of peers; Neutron names are
	// loaded on panel open, explicit refresh and attachment changes, not each tick.
	const panelAr = createAutoRefresh(
		() => isCurrent() && selectedServerId
			? Promise.all([fetchSelectedServer(selectedServerId), fetchAttachments(selectedServerId)]).then(() => undefined)
			: undefined,
		{
			storageKey: workspaceContext ? 'admin-waygate-detail' : 'dashboard-network-waygate-detail',
			defaultActive: true,
			defaultInterval: 15,
			intervalOptions: [10, 15, 30, 60],
			invokeOnMount: false,
		}
	);

	const peerStorageKey = workspaceContext ? 'admin-waygate-peers' : 'dashboard-network-waygate-peers';
	$effect(() => {
		// Preserve an explicit legacy pause, not the old metadata polling interval.
		const activeKey = `autoRefresh.${peerStorageKey}.active`;
		const legacyKey = `autoRefresh.${workspaceContext ? 'admin-waygate-detail' : 'dashboard-network-waygate-detail'}.active`;
		if (localStorage.getItem(activeKey) === null && localStorage.getItem(legacyKey) === 'false') {
			localStorage.setItem(activeKey, 'false');
		}
	});
	const peerAr = createAutoRefresh(
		() => {
			if (!isCurrent() || !selectedServerId) return;
			const request = fetchClients(selectedServerId);
			let cancel!: () => void;
			const cancelled = new Promise<void>((resolve) => { cancel = resolve; });
			cancelPeerRound = cancel;
			return Promise.race([request, cancelled]).finally(() => {
				if (cancelPeerRound === cancel) cancelPeerRound = null;
			});
		},
		{
			storageKey: peerStorageKey,
			defaultActive: true,
			defaultInterval: 1,
			intervalOptions: [1, 2, 5, 10, 15, 30, 60],
			invokeOnMount: false,
		}
	);

	$effect(() => {
		if (!selectedServerId) return;
		function onVisibility() {
			if (document.hidden) {
				clientRequest += 1;
				clientsLoading = false;
			} else {
				trafficNow = Date.now();
			}
		}
		document.addEventListener('visibilitychange', onVisibility);
		return () => document.removeEventListener('visibilitychange', onVisibility);
	});

	let showClientModal = $state(false);
	let newClientDraft = $state<WaygateClientDraft>(emptyWaygateClientDraft());
	let newClientErrors = $state<WaygateClientDraftErrors>({});
	let newClientFields = $state<ReturnType<typeof ClientSettingsFields> | null>(null);
	let clientCreating = $state(false);
	let clientCreateError = $state('');

	function openClientModal() {
		if (!captureDetail()) return;
		newClientDraft = {
			...emptyWaygateClientDraft(),
			dns: selectedServer?.dns ?? '',
			persistentKeepalive: String(selectedServer?.persistent_keepalive ?? WAYGATE_KEEPALIVE_DEFAULT),
		};
		newClientErrors = {};
		clientCreateError = '';
		showClientModal = true;
	}

	async function createClient() {
		const detail = captureDetail();
		if (!detail || clientCreating) return;
		const parsed = waygateClientCreateBody(newClientDraft);
		clientCreateError = '';
		if (!parsed.ok) {
			newClientErrors = parsed.errors;
			await tick();
			if (detail.current()) newClientFields?.focusFirstError();
			return;
		}
		newClientErrors = {};
		const serverId = detail.id;
		clientCreating = true;
		try {
			const result = await waygateApi.createClient(serverId, parsed.body, token, projectId);
			if (!detail.current()) return;
			showClientModal = false;
			toast.success('Waygate 클라이언트가 발급되었습니다');
			// 발급 직후 응답에 평문 .conf가 포함되어 있으므로 바로 다운로드 제공
			const blob = new Blob([result.tunnel_conf], { type: 'text/plain' });
			downloadBlobAs(blob, `${result.name}.conf`);
			await fetchClients(serverId, true);
		} catch (e) {
			if (!detail.current()) return;
			clientCreateError = e instanceof ApiError ? e.message : '클라이언트 발급 실패';
		} finally {
			if (detail.current()) clientCreating = false;
		}
	}

	let editingClient = $state<WaygateClient | null>(null);
	let editClientDraft = $state<WaygateClientDraft>(emptyWaygateClientDraft());
	let editClientErrors = $state<WaygateClientDraftErrors>({});
	let editClientFields = $state<ReturnType<typeof ClientSettingsFields> | null>(null);
	let clientSaving = $state(false);
	let clientSaveError = $state('');

	function openEditClient(client: WaygateClient) {
		if (!captureDetail()) return;
		editingClient = client;
		editClientDraft = waygateClientDraft(client);
		editClientErrors = {};
		clientSaveError = '';
	}

	async function saveClientSettings() {
		const client = editingClient;
		const detail = captureDetail();
		if (!detail || !client || clientSaving) return;
		const parsed = waygateClientUpdateBody(client, editClientDraft);
		clientSaveError = '';
		if (!parsed.ok) {
			editClientErrors = parsed.errors;
			await tick();
			if (detail.current()) editClientFields?.focusFirstError();
			return;
		}
		editClientErrors = {};
		const serverId = detail.id;
		clientSaving = true;
		try {
			await waygateApi.updateClient(serverId, client.id, parsed.body, token, projectId);
			if (!detail.current()) return;
			editingClient = null;
			toast.success('설정을 저장했습니다. 기기에서 .conf 또는 QR을 다시 가져오세요.');
			await fetchClients(serverId, true);
		} catch (e) {
			if (!detail.current()) return;
			clientSaveError = e instanceof ApiError ? e.message : '클라이언트 설정 저장 실패';
		} finally {
			if (detail.current()) clientSaving = false;
		}
	}

	let mutatingClientIds = $state<string[]>([]);

	async function toggleClient(client: WaygateClient) {
		const detail = captureDetail();
		if (!detail || mutatingClientIds.includes(client.id)) return;
		mutatingClientIds = [...mutatingClientIds, client.id];
		try {
			await waygateApi.updateClient(detail.id, client.id, { enabled: !client.enabled }, token, projectId);
			if (detail.current()) await fetchClients(detail.id, true);
		} catch (e) {
			if (!detail.current()) return;
			toast.error('상태 변경 실패: ' + (e instanceof ApiError ? e.message : String(e)));
		} finally {
			if (detail.current()) mutatingClientIds = mutatingClientIds.filter((id) => id !== client.id);
		}
	}

	async function deleteClient(client: WaygateClient) {
		const detail = captureDetail();
		if (!detail || mutatingClientIds.includes(client.id)) return;
		mutatingClientIds = [...mutatingClientIds, client.id];
		try {
			if (!(await confirmDialog(`클라이언트 "${client.name}"을 삭제하시겠습니까?`)) || !detail.current()) return;
			await waygateApi.deleteClient(detail.id, client.id, token, projectId);
			if (!detail.current()) return;
			toast.success('클라이언트가 삭제되었습니다');
			await fetchClients(detail.id, true);
		} catch (e) {
			if (!detail.current()) return;
			toast.error('삭제 실패: ' + (e instanceof ApiError ? e.message : String(e)));
		} finally {
			if (detail.current()) mutatingClientIds = mutatingClientIds.filter((id) => id !== client.id);
		}
	}

	let downloadingClientId = $state<string | null>(null);

	async function downloadConfig(client: WaygateClient) {
		const detail = captureDetail();
		if (!detail) return;
		downloadingClientId = client.id;
		try {
			const { blob, filename } = await waygateApi.downloadClientConfig(
				detail.id,
				client.id,
				token,
				projectId
			);
			if (!detail.current()) return;
			downloadBlobAs(blob, filename);
		} catch (e) {
			if (!detail.current()) return;
			toast.error('다운로드 실패: ' + (e instanceof ApiError ? e.message : String(e)));
		} finally {
			if (detail.current()) downloadingClientId = null;
		}
	}

	// ---- QR 코드 (프론트 생성 — 백엔드는 .conf 텍스트만 제공) ----
	let qrClient = $state<WaygateClient | null>(null);
	let qrDataUrl = $state('');
	let qrLoading = $state(false);
	let qrError = $state('');
	let qrRequest = 0;

	async function openQr(client: WaygateClient) {
		const detail = captureDetail();
		if (!detail) return;
		const request = ++qrRequest;
		const current = () => detail.current() && request === qrRequest;
		qrClient = client;
		qrDataUrl = '';
		qrError = '';
		qrLoading = true;
		try {
			const text = await waygateApi.getClientConfigText(detail.id, client.id, token, projectId);
			if (!current()) return;
			// qrcode 는 브라우저 전용 — SSR 회피를 위해 동적 import
			const QRCode = (await import('qrcode')).default;
			if (!current()) return;
			const dataUrl = await QRCode.toDataURL(text, { errorCorrectionLevel: 'M', margin: 2, width: 320 });
			if (!current()) return;
			qrDataUrl = dataUrl;
		} catch (e) {
			if (!current()) return;
			qrError = e instanceof ApiError ? e.message : 'QR 생성 실패';
		} finally {
			if (current()) qrLoading = false;
		}
	}

	function closeQr() {
		qrRequest += 1;
		qrLoading = false;
		qrClient = null;
		qrDataUrl = '';
		qrError = '';
	}

	// ---- 네트워크 연결 (Phase 2 — 멀티 NIC + SNAT) ----
	let attachments = $state<WaygateNetworkAttachment[]>([]);
	let attachmentsLoading = $state(false);
	let attachmentsLoaded = $state(false);
	let attachmentsError = $state('');
	let attachmentRequest = 0;
	const attachmentInFlight = new Map<string, Promise<WaygateNetworkAttachment[]>>();
	let showAttachModal = $state(false);
	let visibleNetworks = $state<Network[]>([]);
	const availableNetworks = $derived(visibleNetworks.filter((network) => !network.is_external));
	const networkNames = $derived(new Map(visibleNetworks.map((network) => [network.id, network.name?.trim()])));
	function attachmentNetworkName(networkId: string): string {
		if (!networkNames.has(networkId)) return '네트워크 이름 확인 불가';
		return networkNames.get(networkId) || '이름 없는 네트워크';
	}
	let networksError = $state('');
	let networksInFlight: Promise<Network[]> | null = null;
	let networksLoading = $state(false);
	let availableSubnets = $state<SubnetDetail[]>([]);
	let subnetsLoading = $state(false);
	let attachNetworkId = $state('');
	let attachSubnetId = $state('');
	let attachSubnetRequest = 0;
	let networkRequest = 0;
	let attaching = $state(false);
	let attachError = $state('');
	const networkOptions = $derived(
		availableNetworks.map((network) => ({
			value: network.id,
			label: network.name || network.id,
			description: network.name ? network.id : undefined,
		}))
	);
	const subnetOptions = $derived(
		availableSubnets.map((subnet) => ({
			value: subnet.id,
			label: subnet.name || subnet.cidr,
			description: subnet.name ? subnet.cidr : subnet.id,
		}))
	);

	async function fetchAttachments(serverId: string, afterMutation = false) {
		const detail = captureDetail();
		if (!detail || serverId !== detail.id) return;
		while (attachmentInFlight.has(serverId)) {
			if (!afterMutation) return;
			attachmentRequest += 1;
			await attachmentInFlight.get(serverId)!.catch(() => {});
			if (!detail.current()) return;
		}
		const request = ++attachmentRequest;
		attachmentsLoading = !attachmentsLoaded;
		const pending = waygateApi.listAttachments(serverId, token, projectId);
		attachmentInFlight.set(serverId, pending);
		try {
			const next = await pending;
			if (!detail.current() || request !== attachmentRequest) return;
			attachments = reconcileById(attachments, next);
			attachmentsError = '';
		} catch (e) {
			if (!detail.current() || request !== attachmentRequest) return;
			attachmentsError = e instanceof ApiError ? e.message : '네트워크 연결 조회 실패';
		} finally {
			if (attachmentInFlight.get(serverId) === pending) attachmentInFlight.delete(serverId);
			if (detail.current() && request === attachmentRequest) {
				attachmentsLoaded = true;
				attachmentsLoading = false;
			}
		}
	}

	async function fetchNetworks() {
		const detail = captureDetail();
		if (!detail) return;
		if (networksInFlight) {
			await networksInFlight.catch(() => {});
			if (!detail.current()) return;
		}
		const request = ++networkRequest;
		const current = () => detail.current() && request === networkRequest;
		networksLoading = true;
		const pending = api.get<Network[]>('/api/v1/networks', token, projectId, { refresh: true });
		networksInFlight = pending;
		try {
			const networks = await pending;
			if (!current()) return;
			// Keep the project API's visibility rules, including shared networks.
			visibleNetworks = reconcileById(visibleNetworks, networks);
			networksError = '';
		} catch (e) {
			if (!current()) return;
			networksError = e instanceof ApiError ? e.message : '네트워크 목록 조회 실패';
		} finally {
			if (networksInFlight === pending) networksInFlight = null;
			if (current()) networksLoading = false;
		}
	}

	function openAttachModal() {
		if (!captureDetail()) return;
		showAttachModal = true;
		attachError = '';
		attachNetworkId = '';
		attachSubnetId = '';
		subnetsLoading = false;
		availableSubnets = [];
		attachSubnetRequest += 1;
		void fetchNetworks();
	}

	function closeAttachModal() {
		showAttachModal = false;
		attachError = '';
		attachSubnetRequest += 1;
	}

	async function selectAttachNetwork(networkId: string) {
		const detail = captureDetail();
		if (!detail || !showAttachModal) return;
		attachNetworkId = networkId;
		attachSubnetId = '';
		availableSubnets = [];
		attachError = '';
		subnetsLoading = false;
		const requestId = ++attachSubnetRequest;
		if (!networkId) return;

		subnetsLoading = true;
		try {
			const network = await api.get<NetworkDetail>(`/api/v1/networks/${networkId}`, token, projectId);
			if (!detail.current() || requestId !== attachSubnetRequest || networkId !== attachNetworkId) return;
			availableSubnets = network.subnet_details;
			if (availableSubnets.length === 1) attachSubnetId = availableSubnets[0].id;
		} catch (e) {
			if (!detail.current() || requestId !== attachSubnetRequest || networkId !== attachNetworkId) return;
			attachError = e instanceof ApiError ? e.message : '서브넷 목록 조회 실패';
		} finally {
			if (detail.current() && requestId === attachSubnetRequest) subnetsLoading = false;
		}
	}

	async function submitAttach() {
		const detail = captureDetail();
		if (!detail || !attachNetworkId || !attachSubnetId || subnetsLoading || networksLoading || attaching) return;
		attaching = true;
		attachError = '';
		try {
			await waygateApi.attachNetwork(
				detail.id,
				{ network_id: attachNetworkId, subnet_id: attachSubnetId, nat_mode: 'snat' },
				token,
				projectId
			);
			if (!detail.current()) return;
			closeAttachModal();
			toast.success('네트워크 연결이 시작되었습니다');
			await fetchAttachments(detail.id, true);
			if (detail.current()) await fetchNetworks();
		} catch (e) {
			if (!detail.current()) return;
			attachError = e instanceof ApiError ? e.message : '네트워크 연결 실패';
		} finally {
			if (detail.current()) attaching = false;
		}
	}

	async function detachNetwork(att: WaygateNetworkAttachment) {
		const detail = captureDetail();
		if (!detail) return;
		const name = attachmentNetworkName(att.network_id);
		if (!(await confirmDialog(`네트워크 연결(${name} · ${att.network_id})을 해제하시겠습니까?`)) || !detail.current()) return;
		try {
			await waygateApi.detachNetwork(detail.id, att.id, token, projectId);
			if (!detail.current()) return;
			toast.success('네트워크 연결이 해제되었습니다');
			await fetchAttachments(detail.id, true);
			if (detail.current()) await fetchNetworks();
		} catch (e) {
			if (!detail.current()) return;
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
		const detail = captureDetail();
		if (!detail || !selectedServer || exporting) return;
		const name = selectedServer.name;
		exporting = true;
		exportError = '';
		try {
			const bundle = await waygateApi.exportServer(detail.id, exportPassphrase, token, projectId);
			if (!detail.current()) return;
			const blob = new Blob([JSON.stringify(bundle, null, 2)], { type: 'application/json' });
			downloadBlobAs(blob, `${name}-waygate-export.json`);
			showExportModal = false;
			exportPassphrase = '';
			toast.success('설정을 내보냈습니다');
		} catch (e) {
			if (!detail.current()) return;
			exportError = e instanceof ApiError ? e.message : '내보내기 실패';
		} finally {
			if (detail.current()) exporting = false;
		}
	}

	async function submitImport() {
		const detail = captureDetail();
		if (!detail || !importFile || importing) return;
		const passphrase = importPassphrase;
		importing = true;
		importError = '';
		try {
			const text = await importFile.text();
			if (!detail.current()) return;
			const bundle = JSON.parse(text);
			const result = await waygateApi.importServer(
				detail.id,
				passphrase,
				bundle,
				token,
				projectId
			);
			if (!detail.current()) return;
			showImportModal = false;
			importPassphrase = '';
			importFile = null;
			const skippedMsg = result.skipped.length ? ` (${result.skipped.length}개 건너뜀)` : '';
			toast.success(`${result.imported}개 클라이언트를 가져왔습니다${skippedMsg}`);
			await fetchClients(detail.id, true);
		} catch (e) {
			if (!detail.current()) return;
			if (e instanceof SyntaxError) importError = '번들 JSON 파싱에 실패했습니다';
			else importError = e instanceof ApiError ? e.message : '가져오기 실패';
		} finally {
			if (detail.current()) importing = false;
		}
	}

	function clientStatusLabel(client: WaygateClient): string {
		if (!client.enabled) return 'disabled';
		if (!client.last_reported_at || client.online === null) return '알 수 없음';
		const reportedAt = Date.parse(client.last_reported_at);
		const freshness = waygateTrafficFreshnessMs(client.report_interval_seconds, peerAr.intervalSeconds);
		if (!Number.isFinite(reportedAt) || trafficNow - reportedAt > freshness) return '보고 지연';
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
		<ClientSettingsFields bind:this={newServerFields} bind:draft={newServerDraft} errors={newServerErrors} disabled={creating} mode="server-create" />
		{#if createError}
			<p class="text-sm text-[var(--color-state-danger)]">{createError}</p>
		{/if}
	</div>
</FormModal>

<div class="bulk-selection-page p-4 md:p-8">
	<div data-tour="waygate-header">
	<PageHeader breadcrumb={admin ? 'ADMIN / WAYGATE' : 'NETWORK / WAYGATE'} title={admin ? 'Waygate 관리' : 'Waygate'}>
		{#snippet actions()}
			<TutorialStartButton tour={admin ? 'admin-waygate' : 'waygate'} compactOnMobile />
			<AutoRefreshControl
				bind:active={ar.active}
				bind:intervalSeconds={ar.intervalSeconds}
				intervalOptions={ar.intervalOptions}
				refreshing={refreshing}
				onManualRefresh={forceRefresh}
			/>
			{#if waygateConfigured}
				<Button onclick={() => { newServerDraft = waygateServerDraft(); newServerErrors = {}; showCreateModal = true; createError = ''; }} variant="accent" size="sm">
					+ Waygate 서버 생성
				</Button>
			{/if}
		{/snippet}
	</PageHeader>
	</div>

	{#if !waygateConfigured}
		<Alert tone="warning" class="mb-4">
			관리자가 아직 Waygate 기능을 설정하지 않았습니다. (afterglow.conf [waygate] provider_network_id / image_id 필요)
		</Alert>
	{/if}

	{#if error}
		<Alert tone="danger" class="mb-4">{error}</Alert>
	{/if}

	<div data-tour="waygate-list">
	<div data-tour={!loading && !error ? 'waygate-ready' : undefined}>
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
								onToggle={() => { if (isCurrent()) selection.toggleAll(selectableIds); }}
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
									onclick={() => { if (isCurrent()) selection.toggle(server.id); }}
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
	</div>
</div>
<BulkSelectionOverlay
	count={selection.count}
	ariaLabel="선택한 Waygate 서버 일괄 작업"
	actions={[{ key: 'delete', label: '삭제', tone: 'danger', onAction: bulkDeleteServers }]}
	{busy}
	onClear={() => selection.clear()}
/>

{#if selectedServer}
	<SlidePanel onClose={closePanel} ariaLabel="Waygate 서버 상세" dataTour="waygate-detail" width="w-full md:w-[70vw] max-w-3xl" storageKey="slidePanel.waygate-detail.width">
		<div class="p-6">
			<div class="mb-5 flex flex-wrap items-center justify-between gap-3" role="group" aria-label="서버 및 네트워크 자동 새로고침">
				<!-- 닫기 버튼은 SlidePanel 이 제공한다(`[data-slide-panel-close]`) -->
				<AutoRefreshControl
					bind:active={panelAr.active}
					bind:intervalSeconds={panelAr.intervalSeconds}
					intervalOptions={panelAr.intervalOptions}
					refreshing={attachmentsLoading}
					onManualRefresh={() => { if (selectedServerId) { clientRequest += 1; void Promise.all([panelAr.refresh(), peerAr.refresh(), fetchNetworks()]); } }}
				/>
			</div>

			<div class="flex flex-wrap items-start justify-between gap-3 mb-6">
				<div>
					<h2 class="text-xl font-semibold text-[var(--color-ink-0)]">{selectedServer.name}</h2>
					<div class="mt-1"><StatusChip status={selectedServer.status} /></div>
				</div>
				<div class="flex flex-wrap gap-2">
					<Button onclick={openDefaultsModal} variant="secondary" size="sm">서버 기본값 설정</Button>
					<Button onclick={() => deleteServer(selectedServer)} variant="danger-outline" size="sm">서버 삭제</Button>
				</div>
			</div>

			{#if selectedServer.status_reason}
				<Alert tone="warning" class="mb-4">{selectedServer.status_reason}</Alert>
			{/if}

			<dl class="grid grid-cols-1 gap-3 text-sm mb-8 bg-[var(--color-surface-raised)] border border-[var(--color-line)] rounded-xl p-4 xl:grid-cols-2 xl:gap-x-6">
				<div>
					<dt class="text-xs text-[var(--color-ink-3)] uppercase tracking-wide">엔드포인트</dt>
					<dd class="text-[var(--color-ink-1)] font-mono">{selectedServer.endpoint_ip ?? '-'}:{selectedServer.listen_port}</dd>
				</div>
				<div>
					<dt class="text-xs text-[var(--color-ink-3)] uppercase tracking-wide">터널 CIDR</dt>
					<dd class="text-[var(--color-ink-1)] font-mono">{selectedServer.tunnel_cidr}</dd>
				</div>
				<div>
					<dt class="text-xs text-ink-2">기본 DNS</dt>
					<dd class="text-[var(--color-ink-1)]">{selectedServer.dns ?? '-'}</dd>
				</div>
				<div>
					<dt class="text-xs text-ink-2">기본 Keepalive</dt>
					<dd class="text-ink-1">{(selectedServer.persistent_keepalive ?? WAYGATE_KEEPALIVE_DEFAULT) === 0 ? '비활성화' : `${selectedServer.persistent_keepalive ?? WAYGATE_KEEPALIVE_DEFAULT}초`}</dd>
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
					onclick={openClientModal}
					variant="accent"
					size="sm"
					disabled={selectedServer.status !== 'ACTIVE'}
					title={selectedServer.status !== 'ACTIVE' ? 'Waygate 서버가 ACTIVE 상태여야 클라이언트를 발급할 수 있습니다' : undefined}
				>+ 클라이언트 발급</Button>
			</div>

			<div class="mb-4 flex min-w-0 flex-wrap items-center gap-2 [&_.auto-refresh-control]:min-w-0 [&_.auto-refresh-control]:max-w-full [&_.auto-refresh-control]:flex-wrap [&_.toggle-group]:max-w-full [&_.toggle-group]:flex-wrap" role="group" aria-label="클라이언트 자동 새로고침">
				<span class="text-xs text-ink-2">클라이언트 상태</span>
				<AutoRefreshControl
					bind:active={peerAr.active}
					bind:intervalSeconds={peerAr.intervalSeconds}
					intervalOptions={peerAr.intervalOptions}
					refreshing={clientsLoading}
					onManualRefresh={() => { if (selectedServerId) void fetchClients(selectedServerId, true); }}
				/>
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
				<div class="space-y-3">
					{#each clients as client (client.id)}
						<div class="rounded-xl border border-[var(--color-line)] bg-[var(--color-surface-raised)] p-4">
							<div class="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
								<div class="min-w-0">
									<div class="flex flex-wrap items-center gap-2">
										<span class="font-medium text-[var(--color-ink-0)] break-all">{client.name}</span>
										<StatusChip status={clientStatusLabel(client)} />
									</div>
									<dl class="mt-3 grid grid-cols-1 gap-2 text-xs lg:grid-cols-3">
										<div>
											<dt class="text-[var(--color-ink-3)]">터널 IP</dt>
											<dd class="mt-0.5 font-mono text-[var(--color-ink-1)] break-all">{client.tunnel_ip}</dd>
										</div>
										<div>
											<dt class="break-keep text-[var(--color-ink-3)]">마지막 핸드셰이크</dt>
											<dd class="mt-0.5 break-keep text-[var(--color-ink-1)]">{formatDate(client.last_handshake_at)}</dd>
										</div>
										<div>
											<dt class="break-keep text-[var(--color-ink-3)]">생성일</dt>
											<dd class="mt-0.5 break-keep text-[var(--color-ink-1)]">{formatDate(client.created_at)}</dd>
										</div>
										<div>
											<dt class="text-ink-2">DNS</dt>
											<dd class="mt-0.5 font-mono text-[var(--color-ink-1)] break-all">{client.dns ?? '없음'}{client.inherit_dns ? ' · 서버 기본값' : ''}</dd>
										</div>
										<div>
											<dt class="text-ink-2">MTU · Keepalive</dt>
											<dd class="mt-0.5 text-[var(--color-ink-1)]">{client.mtu ?? '자동'} · {client.persistent_keepalive === 0 ? '비활성화' : `${client.persistent_keepalive}초`}{client.inherit_persistent_keepalive ? ' · 서버 기본값' : ''}</dd>
										</div>
										<div>
											<dt class="text-ink-2">PSK</dt>
											<dd class="mt-0.5 text-[var(--color-ink-1)]">{client.psk_enabled ? '사용 중' : '없음'}</dd>
										</div>
									</dl>
								</div>
								<div class="flex shrink-0 flex-wrap items-center gap-1" role="group" aria-label={`${client.name} 작업`}>
									<Button onclick={() => downloadConfig(client)} disabled={downloadingClientId === client.id} variant="ghost" size="icon" class="!size-11 md:!size-8" ariaLabel={`${client.name} .conf 다운로드`} title={downloadingClientId === client.id ? '다운로드 중...' : `${client.name} .conf 다운로드`}>
										<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 3v12m-5-5 5 5 5-5M5 16v5h14v-5" /></svg>
									</Button>
									<Button onclick={() => openQr(client)} variant="ghost" size="icon" class="!size-11 md:!size-8" ariaLabel={`${client.name} QR`} title={`${client.name} QR`}>
										<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 3h6v6H3zm12 0h6v6h-6zM3 15h6v6H3zm12 0h2v2h-2zm6 0v6h-6m-3-9h3m6 0h-3M12 3v3m0 12v3" /></svg>
									</Button>
									<Button onclick={() => openEditClient(client)} variant="ghost" size="icon" class="!size-11 md:!size-8" ariaLabel={`${client.name} 설정`} title={`${client.name} 설정`}>
										<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 7h16M4 17h16M8 4v6m8 4v6" /></svg>
									</Button>
									<span class="mx-1 h-5 border-l border-line" aria-hidden="true"></span>
									<Button onclick={() => toggleClient(client)} disabled={mutatingClientIds.includes(client.id)} variant="ghost" size="xs" class="min-h-11 md:min-h-8" ariaLabel={`${client.name} ${client.enabled ? '비활성화' : '활성화'}`} title={`${client.name} ${client.enabled ? '비활성화' : '활성화'}`} ariaPressed={client.enabled}>{client.enabled ? '비활성화' : '활성화'}</Button>
									<Button onclick={() => deleteClient(client)} disabled={mutatingClientIds.includes(client.id)} variant="danger-outline" size="xs" class="min-h-11 md:min-h-8" ariaLabel={`${client.name} 삭제`} title={`${client.name} 삭제`}>삭제</Button>
								</div>
							</div>
							<ClientTraffic {client} history={trafficHistories[client.id]} now={trafficNow} pollIntervalSeconds={peerAr.intervalSeconds} />
						</div>
					{/each}
				</div>
			{/if}

			<p class="mt-4 break-keep text-xs text-[var(--color-ink-3)]">
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
				<div class="space-y-3">
					{#each attachments as att (att.id)}
						<div class="rounded-xl border border-[var(--color-line)] bg-[var(--color-surface-raised)] p-4">
							<div class="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
								<dl class="grid min-w-0 flex-1 grid-cols-1 gap-2 text-xs lg:grid-cols-3">
									<div>
										<dt class="text-[var(--color-ink-3)]">네트워크</dt>
										<dd class="mt-0.5 text-[var(--color-ink-1)] break-words">{attachmentNetworkName(att.network_id)}</dd>
										<dd class="mt-0.5 font-mono text-[var(--color-ink-3)] break-all" title={att.network_id}>{att.network_id}</dd>
									</div>
									<div>
										<dt class="text-[var(--color-ink-3)]">CIDR</dt>
										<dd class="mt-0.5 font-mono text-[var(--color-ink-1)] break-all">{att.cidr ?? '-'}</dd>
									</div>
									<div>
										<dt class="text-[var(--color-ink-3)]">NAT</dt>
										<dd class="mt-0.5 text-[var(--color-ink-1)]">{att.nat_mode}</dd>
									</div>
								</dl>
								<div class="flex shrink-0 items-center gap-3">
									<StatusChip status={att.status} />
									<button onclick={() => detachNetwork(att)} class="text-xs text-[var(--color-state-danger)] hover:opacity-80">해제</button>
								</div>
							</div>
						</div>
					{/each}
				</div>
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
			<p class="mt-2 break-keep text-xs text-[var(--color-ink-3)]">
				클라이언트 키는 입력한 패스프레이즈로 암호화되어 번들에 저장됩니다. 다른 Waygate 서버로 이전할 때 같은 패스프레이즈로 가져오세요.
				(서버 키는 이전되지 않으므로 가져온 뒤 클라이언트는 <code>.conf</code> 를 다시 내려받아야 합니다.)
			</p>
		</div>
	</SlidePanel>
{/if}

<FormModal
	bind:open={showDefaultsModal}
	title="서버 기본값 설정"
	submitLabel="저장"
	submitting={defaultsSaving}
	onSubmit={saveServerDefaults}
	onClose={() => { showDefaultsModal = false; defaultsError = ''; }}
>
	<ClientSettingsFields bind:this={defaultsFields} bind:draft={defaultsDraft} errors={defaultsErrors} disabled={defaultsSaving} mode="server-edit" />
	{#if defaultsError}<Alert tone="danger" class="mt-4">{defaultsError}</Alert>{/if}
</FormModal>

<FormModal
	bind:open={showClientModal}
	title="Waygate 클라이언트 발급"
	submitLabel="발급"
	submitting={clientCreating}
	onSubmit={createClient}
	onClose={() => { showClientModal = false; clientCreateError = ''; }}
>
	<ClientSettingsFields bind:this={newClientFields} bind:draft={newClientDraft} defaults={selectedServer ?? undefined} errors={newClientErrors} disabled={clientCreating} mode="issue" />
	{#if clientCreateError}
		<Alert tone="danger" class="mt-4">{clientCreateError}</Alert>
	{/if}
</FormModal>

<FormModal
	open={editingClient !== null}
	title={editingClient ? `${editingClient.name} 설정` : '클라이언트 설정'}
	submitLabel="저장"
	submitting={clientSaving}
	onSubmit={saveClientSettings}
	onClose={() => { editingClient = null; clientSaveError = ''; }}
>
	{#if editingClient}
		<ClientSettingsFields
			bind:this={editClientFields}
			bind:draft={editClientDraft}
			errors={editClientErrors}
			disabled={clientSaving}
			pskEnabled={editingClient.psk_enabled}
			defaults={selectedServer ?? undefined}
		/>
	{/if}
	{#if clientSaveError}
		<Alert tone="danger" class="mt-4">{clientSaveError}</Alert>
	{/if}
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
				<p class="break-keep text-center text-xs text-[var(--color-ink-3)]">
					모바일 WireGuard 앱에서 "QR 코드로 추가"를 선택해 스캔하세요.
				</p>
			</div>
		{/if}
	</Card>
</Modal>

<FormModal
	bind:open={showAttachModal}
	title="네트워크 연결"
	submitting={attaching}
	onClose={closeAttachModal}
>
	<div class="space-y-4">
		<Field label="테넌트 네트워크" required>
			<SearchSelect
				id="waygate-attach-network"
				value={attachNetworkId}
				options={networkOptions}
				placeholder="네트워크 선택"
				searchPlaceholder="이름 또는 ID로 네트워크 검색"
				emptyText="연결 가능한 네트워크가 없습니다"
				loading={networksLoading}
				ariaLabel="연결할 네트워크 선택"
				onchange={selectAttachNetwork}
			/>
		</Field>
		{#if !networksLoading && availableNetworks.length === 0 && !attachError && !networksError}
			<Alert tone="warning">프로젝트에서 사용할 수 있는 내부 네트워크가 없습니다.</Alert>
		{/if}
		<Field label="서브넷" required>
			<SearchSelect
				id="waygate-attach-subnet"
				value={attachSubnetId}
				options={subnetOptions}
				placeholder={attachNetworkId ? '서브넷 선택' : '먼저 네트워크를 선택하세요'}
				searchPlaceholder="이름 또는 CIDR로 서브넷 검색"
				emptyText="연결 가능한 서브넷이 없습니다"
				loading={subnetsLoading}
				disabled={!attachNetworkId || availableSubnets.length === 0}
				ariaLabel="연결할 서브넷 선택"
				onchange={(value) => (attachSubnetId = value)}
			/>
		</Field>
		{#if attachNetworkId && !subnetsLoading && availableSubnets.length === 0 && !attachError}
			<Alert tone="warning">선택한 네트워크에 연결 가능한 서브넷이 없습니다.</Alert>
		{/if}
		<p class="break-keep text-xs text-[var(--color-ink-3)]">
			연결하면 VPN 클라이언트의 <code>.conf</code> AllowedIPs 에 선택한 서브넷 CIDR 이 추가됩니다.
			기존에 발급된 클라이언트는 <code>.conf</code> 를 다시 내려받아야 반영됩니다.
		</p>
		{#if networksError}<Alert tone="danger">{networksError}</Alert>{/if}
		{#if attachError}
			<Alert tone="danger">{attachError}</Alert>
		{/if}
	</div>
	{#snippet actions()}
		<Button onclick={closeAttachModal} variant="secondary" disabled={attaching}>취소</Button>
		<Button
			onclick={submitAttach}
			variant="primary"
			disabled={attaching || networksLoading || subnetsLoading || !attachNetworkId || !attachSubnetId}
		>{attaching ? '처리 중...' : '연결'}</Button>
	{/snippet}
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
