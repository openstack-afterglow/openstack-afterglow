<script lang="ts">
	import { tick, untrack } from 'svelte';
	import { t } from '$lib/i18n/ns/waygate';
	import { intlLocale } from '$lib/i18n/runtime.svelte';
	import RichText from '$lib/i18n/RichText.svelte';
	import type { WaygateProjectScope } from '$lib/utils/waygateProjectScope';
	import { siteConfig } from '$lib/config/site';
	import { api, ApiError } from '$lib/api/client';
	import { toast } from '$lib/stores/toast';
	import { auth } from '$lib/stores/auth';
	import { serviceCapabilities } from '$lib/stores/servicePermissions';
	import { confirmDialog } from '$lib/stores/confirm.svelte';
	import { createAutoRefresh } from '$lib/utils/autoRefresh.svelte';
	import { downloadBlobAs } from '$lib/utils/downloadBlob';
	import AutoRefreshControl from '$lib/components/AutoRefreshControl.svelte';
	import TutorialStartButton from '$lib/tutorial/TutorialStartButton.svelte';
	import PageHeader from '$lib/components/ui/PageHeader.svelte';
	import ActivityIndicator from '$lib/components/ui/ActivityIndicator.svelte';
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
	// Exact effective Waygate leaves from the current-project permission response;
	// pending, failed or switching permissions deny every gated action.
	const can = $derived({
		createGateway: $serviceCapabilities('waygate-gateways_editor'),
		deleteGateway: $serviceCapabilities('waygate-gateways_admin'),
		editClients: $serviceCapabilities('waygate-clients_editor'),
		revokeClients: $serviceCapabilities('waygate-clients_admin'),
		route: $serviceCapabilities('waygate-routing_admin'),
		connect: $serviceCapabilities('waygate-connect_user'),
	});
	// Export/import bundle client credentials together with gateway routing.
	const canBackup = $derived(can.revokeClients && can.route);
	const userId = $derived($auth.userId?.trim() || null);

	/** Download/QR always require connect permission and the caller's enabled profile. */
	function canAccessConfig(client: WaygateClient): boolean {
		return can.connect && client.enabled && userId !== null && client.owner_user_id === userId;
	}
	function ownerLabel(client: WaygateClient): string {
		if (!client.owner_user_id) return t('project.client.ownerUnassigned');
		return client.owner_user_id === userId ? t('project.client.ownerSelf') : client.owner_user_id;
	}

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

	$effect(() => {
		if (!can.deleteGateway) untrack(() => selection.clear());
	});

	async function bulkDeleteServers() {
		if (!isCurrent() || busy || !can.deleteGateway) return;
		const ids = [...selection.ids].filter((id) => selectableIds.has(id));
		if (ids.length === 0) return;
		if (!await confirmDialog(t('project.confirm.bulkDelete', { count: ids.length })) || !isCurrent() || !can.deleteGateway) return;
		busy = true;
		try {
			const results = await executeBulkMutations(ids, (id) => {
				if (!isCurrent()) return Promise.reject(new Error(t('project.error.projectChanged')));
				if (!can.deleteGateway) return Promise.reject(new Error(t('project.permission.denied')));
				return waygateApi.deleteServer(id, token, projectId);
			});
			if (!isCurrent()) return;
			const succeeded = results.filter((result) => result.ok).map((result) => result.id);
			selection.remove(succeeded);
			if (selectedServerId && succeeded.includes(selectedServerId)) closePanel();
			if (succeeded.length > 0) toast.success(t('project.toast.bulkDeleteStarted', { count: succeeded.length }));
			const failedCount = results.length - succeeded.length;
			if (failedCount > 0) toast.error(t('project.toast.bulkDeleteFailed', { count: failedCount }));
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

	function openCreateServer() {
		if (!isCurrent() || !can.createGateway) return;
		newServerDraft = waygateServerDraft();
		newServerErrors = {};
		createError = '';
		showCreateModal = true;
	}

	function openDefaultsModal() {
		if (!captureDetail() || !selectedServer || !can.createGateway) return;
		defaultsDraft = waygateServerDraft(selectedServer);
		defaultsErrors = {};
		defaultsError = '';
		showDefaultsModal = true;
	}

	async function saveServerDefaults() {
		const detail = captureDetail();
		if (!detail || defaultsSaving) return;
		if (!can.createGateway) {
			defaultsError = t('project.permission.denied');
			return;
		}
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
			toast.success(t('project.toast.defaultsSaved'));
			await fetchClients(detail.id, true);
		} catch (e) {
			if (detail.current()) defaultsError = e instanceof ApiError ? e.message : t('project.error.defaultsSave');
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
			error = e instanceof ApiError ? t('project.error.fetchStatus', { status: e.status }) : t('project.error.server');
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
		if (!can.createGateway) {
			createError = t('project.permission.denied');
			return;
		}
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
			toast.success(t('project.toast.serverCreateStarted'));
			await fetchServers(true);
		} catch (e) {
			if (!isCurrent()) return;
			createError = e instanceof ApiError ? e.message : t('project.error.create');
		} finally {
			if (isCurrent()) creating = false;
		}
	}

	async function deleteServer(server: WaygateServer) {
		if (!isCurrent() || !can.deleteGateway) return;
		if (!(await confirmDialog(t('project.confirm.serverDelete', { name: server.name }))) || !isCurrent() || !can.deleteGateway) return;
		try {
			await waygateApi.deleteServer(server.id, token, projectId);
			if (!isCurrent()) return;
			toast.success(t('project.toast.serverDeleteStarted'));
			if (selectedServerId === server.id) closePanel();
			await fetchServers(true);
		} catch (e) {
			if (!isCurrent()) return;
			toast.error(t('project.error.delete', { error: e instanceof ApiError ? e.message : String(e) }));
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
				toast.error(t('project.error.serverStatus', { error: e instanceof ApiError ? e.message : String(e) }));
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
		newClientOwner = '';
		editingClient = null;
		editClientOwner = '';
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
		exportNotice = '';
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
			clientsError = e instanceof ApiError ? e.message : t('project.error.clientsLoad');
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
	// Owner user ID controls which connect-only user may download the profile; blank = unassigned.
	let newClientOwner = $state('');

	function openClientModal() {
		if (!captureDetail() || !can.editClients) return;
		newClientDraft = {
			...emptyWaygateClientDraft(),
			dns: selectedServer?.dns ?? '',
			persistentKeepalive: String(selectedServer?.persistent_keepalive ?? WAYGATE_KEEPALIVE_DEFAULT),
		};
		newClientOwner = userId ?? '';
		newClientErrors = {};
		clientCreateError = '';
		showClientModal = true;
	}

	async function createClient() {
		const detail = captureDetail();
		if (!detail || clientCreating) return;
		if (!can.editClients) {
			clientCreateError = t('project.permission.denied');
			return;
		}
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
			const result = await waygateApi.createClient(serverId, { ...parsed.body, owner_user_id: newClientOwner.trim() || null }, token, projectId);
			if (!detail.current()) return;
			showClientModal = false;
			// Another owner's issuance response intentionally omits plaintext credentials.
			if (result.tunnel_conf && canAccessConfig(result)) {
				toast.success(t('project.toast.clientIssued'));
				const blob = new Blob([result.tunnel_conf], { type: 'text/plain' });
				downloadBlobAs(blob, `${result.name}.conf`);
			} else {
				toast.success(t('project.toast.clientIssuedNoProfile'));
			}
			await fetchClients(serverId, true);
		} catch (e) {
			if (!detail.current()) return;
			clientCreateError = e instanceof ApiError ? e.message : t('project.error.clientIssue');
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
	let editClientOwner = $state('');

	function openEditClient(client: WaygateClient) {
		if (!captureDetail() || !can.editClients) return;
		editingClient = client;
		editClientDraft = waygateClientDraft(client);
		editClientOwner = client.owner_user_id ?? '';
		editClientErrors = {};
		clientSaveError = '';
	}

	async function saveClientSettings() {
		const client = editingClient;
		const detail = captureDetail();
		if (!detail || !client || clientSaving) return;
		if (!can.editClients) {
			clientSaveError = t('project.permission.denied');
			return;
		}
		const parsed = waygateClientUpdateBody(client, editClientDraft);
		clientSaveError = '';
		if (!parsed.ok) {
			editClientErrors = parsed.errors;
			await tick();
			if (detail.current()) editClientFields?.focusFirstError();
			return;
		}
		editClientErrors = {};
		const owner = editClientOwner.trim();
		// Ownership is immutable once assigned; clearing is never a valid PATCH.
		const body = client.owner_user_id == null && owner ? { ...parsed.body, owner_user_id: owner } : parsed.body;
		const serverId = detail.id;
		clientSaving = true;
		try {
			await waygateApi.updateClient(serverId, client.id, body, token, projectId);
			if (!detail.current()) return;
			editingClient = null;
			toast.success(t('project.toast.clientSaved'));
			await fetchClients(serverId, true);
		} catch (e) {
			if (!detail.current()) return;
			clientSaveError = e instanceof ApiError ? e.message : t('project.error.clientSave');
		} finally {
			if (detail.current()) clientSaving = false;
		}
	}

	let mutatingClientIds = $state<string[]>([]);

	async function toggleClient(client: WaygateClient) {
		const detail = captureDetail();
		if (!detail || mutatingClientIds.includes(client.id) || !can.revokeClients) return;
		mutatingClientIds = [...mutatingClientIds, client.id];
		try {
			await waygateApi.updateClient(detail.id, client.id, { enabled: !client.enabled }, token, projectId);
			if (detail.current()) await fetchClients(detail.id, true);
		} catch (e) {
			if (!detail.current()) return;
			toast.error(t('project.error.clientToggle', { error: e instanceof ApiError ? e.message : String(e) }));
		} finally {
			if (detail.current()) mutatingClientIds = mutatingClientIds.filter((id) => id !== client.id);
		}
	}

	async function deleteClient(client: WaygateClient) {
		const detail = captureDetail();
		if (!detail || mutatingClientIds.includes(client.id) || !can.revokeClients) return;
		mutatingClientIds = [...mutatingClientIds, client.id];
		try {
			if (!(await confirmDialog(t('project.confirm.clientDelete', { name: client.name }))) || !detail.current() || !can.revokeClients) return;
			await waygateApi.deleteClient(detail.id, client.id, token, projectId);
			if (!detail.current()) return;
			toast.success(t('project.toast.clientDeleted'));
			await fetchClients(detail.id, true);
		} catch (e) {
			if (!detail.current()) return;
			toast.error(t('project.error.delete', { error: e instanceof ApiError ? e.message : String(e) }));
		} finally {
			if (detail.current()) mutatingClientIds = mutatingClientIds.filter((id) => id !== client.id);
		}
	}

	let downloadingClientId = $state<string | null>(null);

	function canAccessCurrentConfig(id: string): boolean {
		const client = clients.find((item) => item.id === id);
		return !!client && canAccessConfig(client);
	}

	async function downloadConfig(client: WaygateClient) {
		const detail = captureDetail();
		if (!detail || !canAccessConfig(client)) return;
		downloadingClientId = client.id;
		try {
			const { blob, filename } = await waygateApi.downloadClientConfig(
				detail.id,
				client.id,
				token,
				projectId
			);
			if (!detail.current() || !canAccessCurrentConfig(client.id)) return;
			downloadBlobAs(blob, filename);
		} catch (e) {
			if (!detail.current()) return;
			toast.error(t('project.error.download', { error: e instanceof ApiError ? e.message : String(e) }));
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
		if (!detail || !canAccessConfig(client)) return;
		const request = ++qrRequest;
		const current = () => detail.current() && request === qrRequest && canAccessCurrentConfig(client.id);
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
			qrError = e instanceof ApiError ? e.message : t('project.error.qr');
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

	$effect(() => {
		if (qrClient && !canAccessCurrentConfig(qrClient.id)) untrack(closeQr);
	});

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
		if (!networkNames.has(networkId)) return t('project.network.nameUnavailable');
		return networkNames.get(networkId) || t('project.network.unnamed');
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
			attachmentsError = e instanceof ApiError ? e.message : t('project.error.attachmentsLoad');
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
			networksError = e instanceof ApiError ? e.message : t('project.error.networksLoad');
		} finally {
			if (networksInFlight === pending) networksInFlight = null;
			if (current()) networksLoading = false;
		}
	}

	function openAttachModal() {
		if (!captureDetail() || !can.route) return;
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
			attachError = e instanceof ApiError ? e.message : t('project.error.subnetsLoad');
		} finally {
			if (detail.current() && requestId === attachSubnetRequest) subnetsLoading = false;
		}
	}

	async function submitAttach() {
		const detail = captureDetail();
		if (!detail || !attachNetworkId || !attachSubnetId || subnetsLoading || networksLoading || attaching) return;
		if (!can.route) {
			attachError = t('project.permission.denied');
			return;
		}
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
			toast.success(t('project.toast.networkAttachStarted'));
			await fetchAttachments(detail.id, true);
			if (detail.current()) await fetchNetworks();
		} catch (e) {
			if (!detail.current()) return;
			attachError = e instanceof ApiError ? e.message : t('project.error.attach');
		} finally {
			if (detail.current()) attaching = false;
		}
	}

	async function detachNetwork(att: WaygateNetworkAttachment) {
		const detail = captureDetail();
		if (!detail || !can.route) return;
		const name = attachmentNetworkName(att.network_id);
		if (!(await confirmDialog(t('project.confirm.networkDetach', { name, id: att.network_id }))) || !detail.current() || !can.route) return;
		try {
			await waygateApi.detachNetwork(detail.id, att.id, token, projectId);
			if (!detail.current()) return;
			toast.success(t('project.toast.networkDetached'));
			await fetchAttachments(detail.id, true);
			if (detail.current()) await fetchNetworks();
		} catch (e) {
			if (!detail.current()) return;
			toast.error(t('project.error.detach', { error: e instanceof ApiError ? e.message : String(e) }));
		}
	}

	// ---- 백업 / 마이그레이션 (Phase 3) ----
	let showExportModal = $state(false);
	let exportPassphrase = $state('');
	let exporting = $state(false);
	let exportError = $state('');
	let exportNotice = $state('');

	let showImportModal = $state(false);
	let importPassphrase = $state('');
	let importFile = $state<File | null>(null);
	let importing = $state(false);
	let importError = $state('');

	function openExportModal() {
		if (!captureDetail() || !canBackup) return;
		exportError = '';
		showExportModal = true;
	}

	function openImportModal() {
		if (!captureDetail() || !canBackup) return;
		importError = '';
		showImportModal = true;
	}

	async function submitExport() {
		const detail = captureDetail();
		if (!detail || !selectedServer || exporting) return;
		if (!canBackup) {
			exportError = t('project.permission.denied');
			return;
		}
		const name = selectedServer.name;
		exporting = true;
		exportError = '';
		try {
			const bundle = await waygateApi.exportServer(detail.id, exportPassphrase, token, projectId);
			if (!detail.current() || !canBackup) return;
			const blob = new Blob([JSON.stringify(bundle, null, 2)], { type: 'application/json' });
			downloadBlobAs(blob, `${name}-waygate-export.json`);
			showExportModal = false;
			exportPassphrase = '';
			exportNotice = t('project.backup.exportSubsetResult', { count: bundle.excluded_assigned_client_count });
			toast.success(t('project.toast.exported'));
		} catch (e) {
			if (!detail.current()) return;
			exportError = e instanceof ApiError ? e.message : t('project.error.export');
		} finally {
			if (detail.current()) exporting = false;
		}
	}

	async function submitImport() {
		const detail = captureDetail();
		if (!detail || !importFile || importing) return;
		if (!canBackup) {
			importError = t('project.permission.denied');
			return;
		}
		const passphrase = importPassphrase;
		importing = true;
		importError = '';
		try {
			const text = await importFile.text();
			if (!detail.current()) return;
			if (!canBackup) {
				importError = t('project.permission.denied');
				return;
			}
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
			toast.success(result.skipped.length
				? t('project.toast.importedSkipped', { count: result.imported, skipped: result.skipped.length })
				: t('project.toast.imported', { count: result.imported }));
			await fetchClients(detail.id, true);
		} catch (e) {
			if (!detail.current()) return;
			if (e instanceof SyntaxError) importError = t('project.error.bundleParse');
			else importError = e instanceof ApiError ? e.message : t('project.error.import');
		} finally {
			if (detail.current()) importing = false;
		}
	}

	function clientStatusLabel(client: WaygateClient): string {
		if (!client.enabled) return t('project.status.disabled');
		if (!client.last_reported_at || client.online === null) return t('project.status.unknown');
		const reportedAt = Date.parse(client.last_reported_at);
		const freshness = waygateTrafficFreshnessMs(client.report_interval_seconds, peerAr.intervalSeconds);
		if (!Number.isFinite(reportedAt) || trafficNow - reportedAt > freshness) return t('project.status.delayed');
		return client.online ? t('project.status.online') : t('project.status.offline');
	}

	function formatDate(iso: string | null): string {
		if (!iso) return '-';
		try {
			return new Date(iso).toLocaleString(intlLocale());
		} catch {
			return iso;
		}
	}
</script>

<FormModal
	bind:open={showCreateModal}
	title={t('project.server.createTitle')}
	submitLabel={t('project.actions.create')}
	submitting={creating}
	onSubmit={can.createGateway ? createServer : undefined}
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
	<PageHeader breadcrumb={admin ? t('project.header.adminBreadcrumb') : t('project.header.networkBreadcrumb')} title={admin ? t('project.header.adminTitle') : 'Waygate'}>
		{#snippet actions()}
			<TutorialStartButton tour={admin ? 'admin-waygate' : 'waygate'} compactOnMobile />
			<AutoRefreshControl
				bind:active={ar.active}
				bind:intervalSeconds={ar.intervalSeconds}
				intervalOptions={ar.intervalOptions}
				refreshing={refreshing}
				onManualRefresh={forceRefresh}
			/>
			{#if waygateConfigured && can.createGateway}
				<Button onclick={openCreateServer} variant="accent" size="sm">
					{t('project.actions.createServer')}
				</Button>
			{/if}
		{/snippet}
	</PageHeader>
	</div>

	{#if !waygateConfigured}
		<Alert tone="warning" class="mb-4">
			{t('project.configuration.required')}
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
			<div class="text-5xl mb-4">{t('project.empty.icon')}</div>
			<div class="text-lg">{t('project.empty.servers')}</div>
			<p class="text-sm text-[var(--color-ink-3)] mt-2">{t('project.empty.serversHelp')}</p>
		</div>
	{:else}
		<TableShell>
			<table>
				<thead>
					<tr>
						<th>
							{#if can.deleteGateway}
							<SelectionToolbar
								label={t('project.server.label')}
								ariaLabel={t('project.selection.all')}
								checked={allSelected}
								indeterminate={indeterminate}
								selectedCount={selectedCount}
								disabled={busy || selectableIds.size === 0}
								onToggle={() => { if (isCurrent() && can.deleteGateway) selection.toggleAll(selectableIds); }}
							/>
							{:else}
								{t('project.server.label')}
								{/if}
						</th>
						<th>{t('project.table.status')}</th>
						<th>{t('project.server.endpoint')}</th>
						<th>{t('project.server.tunnelCidr')}</th>
						<th>{t('project.server.peerCount')}</th>
						<th>{t('project.details.createdAt')}</th>
						<th></th>
					</tr>
				</thead>
				<tbody class="motion-stagger">
					{#each servers as server (server.id)}
						<tr class="resource-selection-surface cursor-pointer" data-selected={selection.has(server.id)} onclick={() => openPanel(server.id)}>
							<td class="text-[var(--color-ink-0)]">
								{#if can.deleteGateway}
								<SelectionCheckbox
									checked={selection.has(server.id)}
									disabled={busy}
									ariaLabel={t('project.selection.server', { name: server.name })}
									onclick={() => { if (isCurrent() && can.deleteGateway) selection.toggle(server.id); }}
								/>
								{/if}
								<span class="ml-2">{server.name}</span>
							</td>
							<td><StatusChip status={server.status} /></td>
							<td class="text-[var(--color-ink-2)] text-xs font-mono">{server.endpoint_ip ?? '-'}</td>
							<td class="text-[var(--color-ink-2)] text-xs font-mono">{server.tunnel_cidr}</td>
							<td class="text-[var(--color-ink-2)] text-xs">{server.peer_count ?? '-'}</td>
							<td class="text-[var(--color-ink-2)] text-xs">{formatDate(server.created_at)}</td>
							<td>
								{#if can.deleteGateway}
								<button
									onclick={(e) => { e.stopPropagation(); deleteServer(server); }}
									class="text-xs text-[var(--color-state-danger)] hover:opacity-80"
								>{t('project.actions.delete')}</button>
								{/if}
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
{#if can.deleteGateway}
<BulkSelectionOverlay
	count={selection.count}
	ariaLabel={t('project.selection.bulkActions')}
	actions={[{ key: 'delete', label: t('project.actions.delete'), tone: 'danger', onAction: bulkDeleteServers }]}
	{busy}
	onClear={() => selection.clear()}
/>
{/if}

{#if selectedServer}
	<SlidePanel onClose={closePanel} ariaLabel={t('project.server.details')} dataTour="waygate-detail" width="w-full md:w-[70vw] max-w-3xl" storageKey="slidePanel.waygate-detail.width">
		<div class="p-6">
			<div class="mb-5 flex flex-wrap items-center justify-between gap-3" role="group" aria-label={t('project.refresh.serverNetworks')}>
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
					{#if can.createGateway}
					<Button onclick={openDefaultsModal} variant="secondary" size="sm">{t('project.server.defaults')}</Button>
					{/if}
					{#if can.deleteGateway}
					<Button onclick={() => deleteServer(selectedServer)} variant="danger-outline" size="sm">{t('project.actions.deleteServer')}</Button>
					{/if}
				</div>
			</div>

			{#if selectedServer.status_reason}
				<Alert tone="warning" class="mb-4">{selectedServer.status_reason}</Alert>
			{/if}

			<dl class="grid grid-cols-1 gap-3 text-sm mb-8 bg-[var(--color-surface-raised)] border border-[var(--color-line)] rounded-xl p-4 xl:grid-cols-2 xl:gap-x-6">
				<div>
					<dt class="text-xs text-[var(--color-ink-3)] uppercase tracking-wide">{t('project.server.endpoint')}</dt>
					<dd class="text-[var(--color-ink-1)] font-mono">{selectedServer.endpoint_ip ?? '-'}:{selectedServer.listen_port}</dd>
				</div>
				<div>
					<dt class="text-xs text-[var(--color-ink-3)] uppercase tracking-wide">{t('project.server.tunnelCidr')}</dt>
					<dd class="text-[var(--color-ink-1)] font-mono">{selectedServer.tunnel_cidr}</dd>
				</div>
				<div>
					<dt class="text-xs text-ink-2">{t('project.server.defaultDns')}</dt>
					<dd class="text-[var(--color-ink-1)]">{selectedServer.dns ?? '-'}</dd>
				</div>
				<div>
					<dt class="text-xs text-ink-2">{t('project.server.defaultKeepalive')}</dt>
					<dd class="text-ink-1">{(selectedServer.persistent_keepalive ?? WAYGATE_KEEPALIVE_DEFAULT) === 0 ? t('project.state.disabled') : t('project.duration.seconds', { seconds: selectedServer.persistent_keepalive ?? WAYGATE_KEEPALIVE_DEFAULT })}</dd>
				</div>
				<div>
					<dt class="text-xs text-[var(--color-ink-3)] uppercase tracking-wide">{t('project.server.publicKey')}</dt>
					<dd class="text-[var(--color-ink-1)] font-mono text-xs break-all">{selectedServer.server_public_key ?? t('project.server.waitingAgent')}</dd>
				</div>
				<div>
					<dt class="text-xs text-[var(--color-ink-3)] uppercase tracking-wide">{t('project.server.lastReport')}</dt>
					<dd class="text-[var(--color-ink-1)]">{formatDate(selectedServer.last_status_reported_at)}</dd>
				</div>
				<div>
					<dt class="text-xs text-[var(--color-ink-3)] uppercase tracking-wide">{t('project.server.peerCount')}</dt>
					<dd class="text-[var(--color-ink-1)]">{selectedServer.peer_count ?? '-'}</dd>
				</div>
			</dl>

			<div class="flex items-center justify-between mb-3">
				<h3 class="text-sm font-medium text-[var(--color-ink-1)]">{t('project.client.heading')}</h3>
				{#if can.editClients}
				<Button
					onclick={openClientModal}
					variant="accent"
					size="sm"
					disabled={selectedServer.status !== 'ACTIVE'}
					title={selectedServer.status !== 'ACTIVE' ? t('project.client.requiresActive') : undefined}
				>{t('project.actions.issueClient')}</Button>
				{/if}
			</div>

			<div class="mb-4 flex min-w-0 flex-wrap items-center gap-2 [&_.auto-refresh-control]:min-w-0 [&_.auto-refresh-control]:max-w-full [&_.auto-refresh-control]:flex-wrap [&_.toggle-group]:max-w-full [&_.toggle-group]:flex-wrap" role="group" aria-label={t('project.refresh.clients')}>
				<span class="text-xs text-ink-2">{t('project.client.status')}</span>
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
					<div class="text-sm">{t('project.empty.clients')}</div>
				</div>
			{:else}
				<div class="motion-stagger space-y-3">
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
											<dt class="text-[var(--color-ink-3)]">{t('project.client.tunnelIp')}</dt>
											<dd class="mt-0.5 font-mono text-[var(--color-ink-1)] break-all">{client.tunnel_ip}</dd>
										</div>
										<div>
											<dt class="break-keep text-[var(--color-ink-3)]">{t('project.client.lastHandshake')}</dt>
											<dd class="mt-0.5 break-keep text-[var(--color-ink-1)]">{formatDate(client.last_handshake_at)}</dd>
										</div>
										<div>
											<dt class="break-keep text-[var(--color-ink-3)]">{t('project.details.createdAt')}</dt>
											<dd class="mt-0.5 break-keep text-[var(--color-ink-1)]">{formatDate(client.created_at)}</dd>
										</div>
										<div>
											<dt class="text-ink-2">{t('project.client.dnsLabel')}</dt>
											<dd class="mt-0.5 font-mono text-[var(--color-ink-1)] break-all">{t('project.client.dnsValue', { dns: client.dns ?? t('project.state.none'), inherit: client.inherit_dns })}</dd>
										</div>
										<div>
											<dt class="text-ink-2">{t('project.client.mtuKeepaliveLabel')}</dt>
											<dd class="mt-0.5 text-[var(--color-ink-1)]">{t('project.client.mtuKeepaliveValue', { mtu: client.mtu ?? t('project.state.auto'), keepalive: client.persistent_keepalive === 0 ? t('project.state.disabled') : t('project.duration.seconds', { seconds: client.persistent_keepalive }), inherit: client.inherit_persistent_keepalive })}</dd>
										</div>
										<div>
											<dt class="text-ink-2">{t('project.client.pskLabel')}</dt>
											<dd class="mt-0.5 text-[var(--color-ink-1)]">{client.psk_enabled ? t('project.state.inUse') : t('project.state.none')}</dd>
										</div>
										<div>
											<dt class="text-ink-2">{t('project.client.owner')}</dt>
											<dd class="mt-0.5 break-all text-ink-1">{ownerLabel(client)}</dd>
										</div>
									</dl>
								</div>
								<div class="flex shrink-0 flex-wrap items-center gap-1" role="group" aria-label={t('project.client.actions', { name: client.name })}>
									{#if canAccessConfig(client)}
									<Button onclick={() => downloadConfig(client)} disabled={downloadingClientId === client.id} ariaBusy={downloadingClientId === client.id} variant="ghost" size="icon" class="!size-11 md:!size-8" ariaLabel={t('project.client.downloadConfig', { name: client.name })} title={downloadingClientId === client.id ? t('project.client.downloading') : t('project.client.downloadConfig', { name: client.name })}>
										{#if downloadingClientId === client.id}
											<ActivityIndicator variant="download" size="md" />
										{:else}
											<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 3v12m-5-5 5 5 5-5M5 16v5h14v-5" /></svg>
										{/if}
									</Button>
									<Button onclick={() => openQr(client)} variant="ghost" size="icon" class="!size-11 md:!size-8" ariaLabel={t('project.client.qr', { name: client.name })} title={t('project.client.qr', { name: client.name })}>
										<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 3h6v6H3zm12 0h6v6h-6zM3 15h6v6H3zm12 0h2v2h-2zm6 0v6h-6m-3-9h3m6 0h-3M12 3v3m0 12v3" /></svg>
									</Button>
									{/if}
									{#if can.editClients}
									<Button onclick={() => openEditClient(client)} variant="ghost" size="icon" class="!size-11 md:!size-8" ariaLabel={t('project.client.namedSettings', { name: client.name })} title={t('project.client.namedSettings', { name: client.name })}>
										<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 7h16M4 17h16M8 4v6m8 4v6" /></svg>
									</Button>
									{/if}
									{#if can.revokeClients}
									<span class="mx-1 h-5 border-l border-line" aria-hidden="true"></span>
									{/if}
									{#if can.revokeClients}
									<Button onclick={() => toggleClient(client)} disabled={mutatingClientIds.includes(client.id)} variant="ghost" size="xs" class="min-h-11 md:min-h-8" ariaLabel={client.enabled ? t('project.client.disable', { name: client.name }) : t('project.client.enable', { name: client.name })} title={client.enabled ? t('project.client.disable', { name: client.name }) : t('project.client.enable', { name: client.name })} ariaPressed={client.enabled}>{client.enabled ? t('project.actions.disable') : t('project.actions.enable')}</Button>
									{/if}
									{#if can.revokeClients}
									<Button onclick={() => deleteClient(client)} disabled={mutatingClientIds.includes(client.id)} variant="danger-outline" size="xs" class="min-h-11 md:min-h-8" ariaLabel={t('project.client.delete', { name: client.name })} title={t('project.client.delete', { name: client.name })}>{t('project.actions.delete')}</Button>
									{/if}
								</div>
							</div>
							<ClientTraffic {client} history={trafficHistories[client.id]} now={trafficNow} pollIntervalSeconds={peerAr.intervalSeconds} />
						</div>
					{/each}
				</div>
			{/if}

			<p class="mt-4 break-keep text-xs text-[var(--color-ink-3)]">
				<RichText segments={t.rich('project.client.configHelp')} />
			</p>

			<div class="flex items-center justify-between mb-3 mt-8">
				<h3 class="text-sm font-medium text-[var(--color-ink-1)]">{t('project.network.attachedHeading')}</h3>
				{#if can.route}
				<Button
					onclick={openAttachModal}
					variant="secondary"
					size="sm"
					disabled={selectedServer.status !== 'ACTIVE'}
					title={selectedServer.status !== 'ACTIVE' ? t('project.network.requiresActive') : undefined}
				>{t('project.actions.attachNetwork')}</Button>
				{/if}
			</div>

			{#if attachmentsError}
				<Alert tone="danger" class="mb-4">{attachmentsError}</Alert>
			{/if}

			{#if attachmentsLoading && attachments.length === 0}
				<LoadingSkeleton variant="table" rows={2} />
			{:else if attachments.length === 0}
				<div class="text-center py-8 text-[var(--color-ink-3)] bg-[var(--color-surface-raised)] border border-[var(--color-line)] rounded-xl text-sm">
					{t('project.empty.networks')}
				</div>
			{:else}
				<div class="motion-stagger space-y-3">
					{#each attachments as att (att.id)}
						<div class="rounded-xl border border-[var(--color-line)] bg-[var(--color-surface-raised)] p-4">
							<div class="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
								<dl class="grid min-w-0 flex-1 grid-cols-1 gap-2 text-xs lg:grid-cols-3">
									<div>
										<dt class="text-[var(--color-ink-3)]">{t('project.network.label')}</dt>
										<dd class="mt-0.5 text-[var(--color-ink-1)] break-words">{attachmentNetworkName(att.network_id)}</dd>
										<dd class="mt-0.5 font-mono text-[var(--color-ink-3)] break-all" title={att.network_id}>{att.network_id}</dd>
									</div>
									<div>
										<dt class="text-[var(--color-ink-3)]">{t('project.network.cidrLabel')}</dt>
										<dd class="mt-0.5 font-mono text-[var(--color-ink-1)] break-all">{att.cidr ?? '-'}</dd>
									</div>
									<div>
										<dt class="text-[var(--color-ink-3)]">{t('project.network.natLabel')}</dt>
										<dd class="mt-0.5 text-[var(--color-ink-1)]">{att.nat_mode}</dd>
									</div>
								</dl>
								<div class="flex shrink-0 items-center gap-3">
									<StatusChip status={att.status} />
									{#if can.route}
									<button onclick={() => detachNetwork(att)} class="text-xs text-[var(--color-state-danger)] hover:opacity-80">{t('project.actions.detach')}</button>
									{/if}
								</div>
							</div>
						</div>
					{/each}
				</div>
			{/if}

			{#if canBackup}
			<div class="flex items-center justify-between mb-3 mt-8">
				<h3 class="text-sm font-medium text-[var(--color-ink-1)]">{t('project.backup.heading')}</h3>
			</div>
			<div class="flex gap-2">
				<Button onclick={openExportModal} variant="secondary" size="sm">{t('project.backup.exportSettings')}</Button>
				<Button
					onclick={openImportModal}
					variant="secondary"
					size="sm"
					disabled={selectedServer.status !== 'ACTIVE'}
					title={selectedServer.status !== 'ACTIVE' ? t('project.backup.requiresActive') : undefined}
				>{t('project.actions.import')}</Button>
			</div>
			<p class="mt-2 break-keep text-xs text-[var(--color-ink-3)]">
				<RichText segments={t.rich('project.backup.help')} />
			</p>
			{#if exportNotice}<Alert tone="info">{exportNotice}</Alert>{/if}
			{/if}
		</div>
	</SlidePanel>
{/if}

<FormModal
	bind:open={showDefaultsModal}
	title={t('project.server.defaults')}
	submitLabel={t('project.actions.save')}
	submitting={defaultsSaving}
	onSubmit={can.createGateway ? saveServerDefaults : undefined}
	onClose={() => { showDefaultsModal = false; defaultsError = ''; }}
>
	<ClientSettingsFields bind:this={defaultsFields} bind:draft={defaultsDraft} errors={defaultsErrors} disabled={defaultsSaving} mode="server-edit" />
	{#if defaultsError}<Alert tone="danger" class="mt-4">{defaultsError}</Alert>{/if}
</FormModal>

<FormModal
	bind:open={showClientModal}
	title={t('project.client.issueTitle')}
	submitLabel={t('project.actions.issue')}
	submitting={clientCreating}
	onSubmit={can.editClients ? createClient : undefined}
	onClose={() => { showClientModal = false; clientCreateError = ''; }}
>
	<ClientSettingsFields bind:this={newClientFields} bind:draft={newClientDraft} defaults={selectedServer ?? undefined} errors={newClientErrors} disabled={clientCreating} mode="issue" />
	<div class="mt-4 space-y-2">
		<Field label={t('project.client.owner')} for="waygate-new-owner" help={t('project.client.ownerHelp')}>
			<TextInput id="waygate-new-owner" bind:value={newClientOwner} disabled={clientCreating || !can.editClients} />
		</Field>
		<Button variant="ghost" size="sm" disabled={!userId || clientCreating || !can.editClients} onclick={() => { if (can.editClients) newClientOwner = userId ?? ''; }}>{t('project.client.assignSelf')}</Button>
	</div>
	{#if clientCreateError}
		<Alert tone="danger" class="mt-4">{clientCreateError}</Alert>
	{/if}
</FormModal>

<FormModal
	open={editingClient !== null}
	title={editingClient ? t('project.client.namedSettings', { name: editingClient.name }) : t('project.client.settings')}
	submitLabel={t('project.actions.save')}
	submitting={clientSaving}
	onSubmit={can.editClients ? saveClientSettings : undefined}
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
		<div class="mt-4 space-y-2">
			<Field label={t('project.client.owner')} for="waygate-edit-owner" help={t('project.client.ownerHelp')}>
				<TextInput id="waygate-edit-owner" bind:value={editClientOwner} disabled={clientSaving || !can.editClients || editingClient.owner_user_id != null} />
			</Field>
			{#if editingClient.owner_user_id == null}
				<Button variant="ghost" size="sm" disabled={!userId || clientSaving || !can.editClients} onclick={() => { if (can.editClients && editingClient?.owner_user_id == null) editClientOwner = userId ?? ''; }}>{t('project.client.assignSelf')}</Button>
			{/if}
		</div>
	{/if}
	{#if clientSaveError}
		<Alert tone="danger" class="mt-4">{clientSaveError}</Alert>
	{/if}
</FormModal>

<Modal open={qrClient !== null} onClose={closeQr} ariaLabel={t('project.qr.dialog')}>
	<Card surface="modal" padding="lg" class="w-[min(100%-2rem,22rem)] mx-4">
		<div class="flex items-center justify-between mb-4">
			<h2 class="text-sm font-medium text-[var(--color-ink-0)]">
				{t('project.qr.title', { name: qrClient?.name })}
			</h2>
			<button onclick={closeQr} class="text-[var(--color-ink-2)] hover:text-[var(--color-ink-0)] text-sm">{t('project.actions.closeSymbol')}</button>
		</div>
		{#if qrLoading}
			<div class="flex justify-center py-16"><ActivityIndicator label={t('project.qr.loading')} /></div>
		{:else if qrError}
			<Alert tone="danger">{qrError}</Alert>
		{:else if qrDataUrl}
			<div class="flex flex-col items-center gap-3">
				<img src={qrDataUrl} alt={t('project.qr.alt')} width="288" height="288" class="rounded-lg bg-surface-base p-2" />
				<p class="break-keep text-center text-xs text-[var(--color-ink-3)]">
					{t('project.qr.help')}
				</p>
			</div>
		{/if}
	</Card>
</Modal>

<FormModal
	bind:open={showAttachModal}
	title={t('project.network.attachTitle')}
	submitting={attaching}
	onClose={closeAttachModal}
>
	<div class="space-y-4">
		<Field label={t('project.network.tenant')} required>
			<SearchSelect
				id="waygate-attach-network"
				value={attachNetworkId}
				options={networkOptions}
				placeholder={t('project.network.select')}
				searchPlaceholder={t('project.network.search')}
				emptyText={t('project.network.noneAvailable')}
				loading={networksLoading}
				ariaLabel={t('project.network.selectAttach')}
				onchange={selectAttachNetwork}
			/>
		</Field>
		{#if !networksLoading && availableNetworks.length === 0 && !attachError && !networksError}
			<Alert tone="warning">{t('project.network.noInternal')}</Alert>
		{/if}
		<Field label={t('project.subnet.label')} required>
			<SearchSelect
				id="waygate-attach-subnet"
				value={attachSubnetId}
				options={subnetOptions}
				placeholder={attachNetworkId ? t('project.subnet.select') : t('project.subnet.selectNetworkFirst')}
				searchPlaceholder={t('project.subnet.search')}
				emptyText={t('project.subnet.noneAvailable')}
				loading={subnetsLoading}
				disabled={!attachNetworkId || availableSubnets.length === 0}
				ariaLabel={t('project.subnet.selectAttach')}
				onchange={(value) => (attachSubnetId = value)}
			/>
		</Field>
		{#if attachNetworkId && !subnetsLoading && availableSubnets.length === 0 && !attachError}
			<Alert tone="warning">{t('project.subnet.noAttachable')}</Alert>
		{/if}
		<p class="break-keep text-xs text-[var(--color-ink-3)]">
			<RichText segments={t.rich('project.network.attachHelp')} />
		</p>
		{#if networksError}<Alert tone="danger">{networksError}</Alert>{/if}
		{#if attachError}
			<Alert tone="danger">{attachError}</Alert>
		{/if}
	</div>
	{#snippet actions()}
		<Button onclick={closeAttachModal} variant="secondary" disabled={attaching}>{t('project.actions.cancel')}</Button>
		<Button
			onclick={submitAttach}
			variant="primary"
			disabled={!can.route || attaching || networksLoading || subnetsLoading || !attachNetworkId || !attachSubnetId}
			ariaBusy={attaching}
		>{attaching ? t('project.actions.processing') : t('project.actions.attach')}</Button>
	{/snippet}
</FormModal>

<FormModal
	bind:open={showExportModal}
	title={t('project.backup.exportSettings')}
	submitLabel={t('project.actions.export')}
	submitting={exporting}
	onSubmit={canBackup ? submitExport : undefined}
	onClose={() => { showExportModal = false; exportError = ''; }}
>
	<div class="space-y-4">
		<Field label={t('project.backup.passphrase')} help={t('project.backup.exportHelp')} required>
			<TextInput bind:value={exportPassphrase} type="password" placeholder={t('project.backup.passphrasePlaceholder')} />
		</Field>
		{#if exportError}
			<p class="text-sm text-[var(--color-state-danger)]">{exportError}</p>
		{/if}
	</div>
</FormModal>

<FormModal
	bind:open={showImportModal}
	title={t('project.backup.importSettings')}
	submitLabel={t('project.actions.import')}
	submitting={importing}
	onSubmit={canBackup ? submitImport : undefined}
	onClose={() => { showImportModal = false; importError = ''; importFile = null; }}
>
	<div class="space-y-4">
		<Field label={t('project.backup.bundleFile')} required>
			<input
				type="file"
				accept="application/json,.json"
				class="text-sm text-[var(--color-ink-1)]"
				onchange={(e) => { importFile = (e.currentTarget as HTMLInputElement).files?.[0] ?? null; }}
			/>
		</Field>
		<Field label={t('project.backup.passphrase')} help={t('project.backup.importHelp')} required>
			<TextInput bind:value={importPassphrase} type="password" />
		</Field>
		{#if importError}
			<p class="text-sm text-[var(--color-state-danger)]">{importError}</p>
		{/if}
	</div>
</FormModal>
