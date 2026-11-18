<script lang="ts">
	import { onMount, tick, untrack, type Snippet } from 'svelte';
	import { SvelteMap, SvelteSet } from 'svelte/reactivity';
	import { page } from '$app/state';
	import { pushState } from '$app/navigation';
	import { derived } from 'svelte/store';
	import { auth, authReady, projectSwitching } from '$lib/stores/auth';
	import { serviceCapabilities } from '$lib/stores/servicePermissions';
	import { api } from '$lib/api/client';
	import type { McpConnection, McpTemplate, McpSettingsPage, McpDomainPage } from '$lib/api/mcpCatalog';
	import { getActiveMockupProfile } from '$lib/mockup/transport';
	import { visibleMcpConnection, mcpConnectionState } from '$lib/api/mcpCatalog';
	import Button from '$lib/components/ui/Button.svelte';
	import Alert from '$lib/components/ui/Alert.svelte';
	import Pill from '$lib/components/ui/Pill.svelte';
	import Field from '$lib/components/ui/Field.svelte';
	import TextInput from '$lib/components/ui/TextInput.svelte';
	import SelectInput from '$lib/components/ui/SelectInput.svelte';
	import LoadingState from '$lib/components/ui/LoadingState.svelte';
	import { intlLocale } from '$lib/i18n/runtime.svelte';
	import ConnectionTabs, { connectionTabs, type ConnectionTab } from './connections/ConnectionTabs.svelte';
	import ConnectionMenu from './connections/ConnectionMenu.svelte';
	import ConnectionName from './connections/ConnectionName.svelte';
	import ConnectionStatus, { type ConnectionState } from './connections/ConnectionStatus.svelte';
	import ConnectionsTable from './connections/ConnectionsTable.svelte';
	import { t } from '$lib/i18n/ns/mcp-gallery';
	import ManagedSandboxToolsPicker from './ManagedSandboxToolsPicker.svelte';
	import { managedSandboxTools, refreshManagedSandboxTools } from '$lib/stores/managedSandboxTools';

	import { t as settingsT } from '$lib/i18n/ns/chat-settings';
	let {
		admin = false, onChanged = async () => {}, remoteForm, approved, cloud, approvedActions,
		adminRows = [], approvedRows = [], adminActions, oauthStatus = {}, inventoryLoading = false, onRemoteClose
	}: {
		admin?: boolean; onChanged?: () => Promise<void>; remoteForm?: Snippet; approved?: Snippet;
		cloud?: { active: boolean; invalid: boolean; toolCount: number };
		approvedActions?: Snippet<[number]>;
		adminRows?: McpConnection[];
		approvedRows?: McpConnection[];
		adminActions?: Snippet<[McpConnection]>;
		oauthStatus?: Record<number, { connected: boolean }>;
		inventoryLoading?: boolean;
		onRemoteClose?: () => void;
	} = $props();
	const id = $props.id();
	const tabParam = 'connections';
	const tabs = (search: URLSearchParams): ConnectionTab => {
		const value = search.get(tabParam);
		return value === 'connected' || value === 'manage' ? value : 'browse';
	};
	let tab = $state(untrack(() => tabs(page.url.searchParams)));
	let preferredScope = $state<'user' | 'domain' | null>(null);
	let queryTimer: ReturnType<typeof setTimeout> | undefined;
	let access = $state<McpTemplate['access'] | ''>('');
	let scopeFilter = $state<McpConnection['scope'] | ''>('');
	const scopeState = { user: 'personal_connected', domain: 'org_connected', global: 'global_connected' } as const;
	const scopes = ['user', 'domain', 'global'] as const;
	const accessModes = ['open', 'oauth', 'credentials', 'configure', 'managed', 'unreachable', 'unavailable'] as const;
	const expanded = new SvelteSet<number | 'cloud'>();
	type Owner = { key: string; token: string; userId: string; projectId: string };
	type Editor = { template?: McpTemplate; row?: McpConnection; scope: 'user' | 'domain' | 'global' };
	let owner = $state.raw<Owner | null>(null);
	let entries = $state<McpTemplate[]>([]);
	let featured = $state<McpTemplate[]>([]);
	let managedEntries = $state<McpTemplate[]>([]);
	let adminEntries = $state<McpTemplate[]>([]);
	let connections = $state<McpConnection[]>([]);
	let domainId = $state<string | null>(null);
	let canManage = $state(false);
	let organizationError = $state(false);
	let loading = $state(false);
	let error = $state('');
	let rowErrors = $state<Record<string, string>>({});
	let busy = $state<Record<string, boolean>>({});
	let query = $state('');
	let appliedQuery = $state('');
	let appliedAccess = $state<McpTemplate['access'] | ''>('');
	let appliedState = $state('');
	let total = $state(0);
	let nextOffset = $state<number | null>(null);
	let editor = $state<Editor | null>(null);
	let label = $state('');
	let editUrl = $state('');
	let published = $state('true');
	let variables = $state<Record<string, string>>({});
	let authMode = $state<'none' | 'oauth' | 'admin'>('none');
	let headers = $state<{ name: string; value: string; fixed: boolean; required: boolean; description?: string }[]>([]);
	let deleteTarget = $state<McpConnection | null>(null);
	let revokeTarget = $state<McpConnection | null>(null);
	let installSummary = $state('');
	let generation = 0;
	let editorGeneration = 0;
	const templates = new SvelteMap<string, McpTemplate>();
	let readController: AbortController | null = null;
	const mutations = new Set<AbortController>();
	const limit = 12;
	const canWrite = $derived(admin ? $auth.isSystemAdmin === true : $serviceCapabilities('lumen-mcp_editor'));
	const canDelete = $derived(admin ? $auth.isSystemAdmin === true : $serviceCapabilities('lumen-resources_admin'));
	type ConnectedRow = { key: number; server: McpConnection; state: ConnectionState; description: string; count?: number }
		| { key: 'cloud'; server: null; state: ConnectionState; description: string; count: number };
	const inventory = $derived(admin ? adminRows : error && owner && !connections.length ? approvedRows : connections);
	let loadedUntil = limit;

	function displayedState(server: McpConnection): ConnectionState {
		if (server.catalog_error || rowErrors[server.id]) return 'error';
		if (admin) return server.is_active ? 'active' : 'inactive';
		if (server.scope === 'global' && !server.template_key && approvedActions) {
			if (server.auth_mode === 'oauth' && (oauthStatus[server.id]?.connected ?? server.auth_connected) !== true) return 'needsAuth';
			if (server.activation_config_version != null && server.activation_is_active && server.activation_config_version !== server.config_version) return 'stale';
			return server.is_active ? 'active' : 'inactive';
		}
		return mcpConnectionState(server);
	}
	const serverRows = $derived.by<ConnectedRow[]>(() => {
		const rows: ConnectedRow[] = inventory.map((server) => ({
			key: server.id,
			server,
			state: displayedState(server),
			description: (server.template_key && templates.get(server.template_key)?.description) || server.connection_label || server.url || '',
			count: server.tool_count ?? server.tools?.length
		}));
		if (cloud) rows.unshift({ key: 'cloud', server: null, state: cloud.invalid ? 'error' : cloud.active ? 'active' : 'inactive', description: settingsT('extensions.catalogue.cloudDescription'), count: cloud.toolCount });
		return rows;
	});
	const connected = $derived.by(() => {
		const needle = appliedQuery.toLocaleLowerCase();
		return serverRows.filter(({ server, description }) => {
			const scope = server?.scope ?? 'user';
			const type = server ? (server.template_key && templates.get(server.template_key)?.access)
				|| (server.auth_mode === 'admin' ? 'credentials' : server.auth_mode === 'oauth' ? 'oauth' : 'open') : 'managed';
			return (!scopeFilter || scope === scopeFilter) && (!access || type === access)
				&& [server?.name ?? 'Afterglow MCP', description, server?.url].some((value) => value?.toLocaleLowerCase().includes(needle));
		});
	});
	const rowsByTemplate = $derived.by(() => {
		const byTemplate = new Map<string, McpConnection[]>();
		for (const row of inventory) {
			if (!row.template_key) continue;
			const matching = byTemplate.get(row.template_key);
			if (matching) matching.push(row);
			else byTemplate.set(row.template_key, [row]);
		}
		return byTemplate;
	});
	const builtinRows = $derived(managedEntries.filter((entry) => !access || access === entry.access));
	const featuredRows = $derived(featured.filter((entry) => entry.access !== 'managed' && (!access || entry.access === access)));

	function browseParams() {
		const params = new URLSearchParams(page.url.searchParams);
		params.set(tabParam, 'browse');
		return params;
	}

	function changeTab(next: ConnectionTab) {
		if (next === tab) return;
		if (tab === 'manage') onRemoteClose?.();
		clearDraft();
		preferredScope = null;
		tab = next;
		const url = new URL(document.location.href);
		url.searchParams.set(tabParam, next);
		pushState(url, page.state);
		applyFilters();
	}

	function addFromBrowse(scope: 'user' | 'domain') {
		changeTab('browse');
		preferredScope = scope;
		void tick().then(() => document.getElementById(`${id}-search`)?.focus());
	}

	function openRemote() {
		changeTab('manage');
		void tick().then(() => document.getElementById(`${id}-remote`)?.querySelector('input')?.focus());
	}

	async function jumpToRow(key: number | 'cloud') {
		changeTab('connected');
		query = ''; access = ''; scopeFilter = '';
		applyFilters();
		expanded.add(key);
		await tick();
		const trigger = document.querySelector<HTMLElement>(`[data-connection-key=\"${id}-${key}\"] button`);
		trigger?.focus();
	}

	function currentState() { return tab === 'connected' && scopeFilter ? scopeState[scopeFilter] : ''; }
	function applyFilters() {
		clearTimeout(queryTimer);
		const search = query.trim(), state = currentState();
		if (search === appliedQuery && access === appliedAccess && state === appliedState) return;
		appliedQuery = search; appliedAccess = access; appliedState = state;
		nextOffset = null;
		loadedUntil = limit;
		if (owner) void load(owner, 0);
	}

	function scheduleSearch() {
		clearTimeout(queryTimer);
		queryTimer = setTimeout(applyFilters, 250);
	}

	function clearDraft() {
		++editorGeneration;
		headers = [];
		variables = {};
		label = '';
		editUrl = '';
		editor = null;
		deleteTarget = null;
		revokeTarget = null;
	}
	export function refresh() { if (owner) void load(owner); }
	function invalidate() {
		readController?.abort();
		for (const controller of mutations) controller.abort();
		mutations.clear();
		++generation;
		templates.clear();
		entries = []; featured = []; managedEntries = []; adminEntries = []; connections = [];
		domainId = null; canManage = false; organizationError = false; error = ''; rowErrors = {}; busy = {};
		loading = false; total = 0; nextOffset = null; query = ''; appliedQuery = '';
		access = ''; appliedAccess = ''; appliedState = ''; scopeFilter = ''; preferredScope = null;
		expanded.clear(); clearTimeout(queryTimer);
		installSummary = ''; clearDraft();
	}
	onMount(() => {
		const stopSandbox = !admin ? managedSandboxTools.subscribe(() => {}) : undefined;
		const unsubscribe = derived([auth, authReady, projectSwitching], ([actor, ready, switching]) => ({ actor, ready, switching })).subscribe(({ actor, ready, switching }) => {
			const key = ready && !switching && actor.token && actor.userId && actor.projectId
				? JSON.stringify([actor.sessionId, actor.userId, actor.identityDomainId, actor.domainId, actor.projectId, admin, actor.isSystemAdmin]) : null;
			if (owner?.key === key) { if (actor.token) owner.token = actor.token; return; }
			invalidate();
			owner = key ? { key, token: actor.token!, userId: actor.userId!, projectId: actor.projectId! } : null;
			if (owner) void load(owner, 0);
		});
		return () => { unsubscribe(); stopSandbox?.(); invalidate(); owner = null; };
	});
	function restoreTab(search = new URLSearchParams(document.location.search)) {
		const next = tabs(search);
		if (next === tab) return;
		if (tab === 'manage') onRemoteClose?.();
		tab = next;
		preferredScope = null;
		clearDraft();
		applyFilters();
	}
	$effect(() => {
		const search = page.url.searchParams;
		untrack(() => restoreTab(search));
	});

	async function load(scope: Owner, start = 0) {
		const ticket = ++generation;
		readController?.abort();
		const controller = new AbortController(); readController = controller;
		const options = { refresh: true, signal: controller.signal };
		loading = true; error = '';
		const search = appliedQuery, type = appliedAccess, state = appliedState;
		try {
			if (admin) {
				const [result, managed] = await Promise.all([
					api.get<{ entries: McpTemplate[] }>('/api/v1/chat/admin/mcp-registry', scope.token, scope.projectId, options),
					api.get<McpSettingsPage>('/api/v1/chat/mcp-settings?access=managed&offset=0&limit=100', scope.token, scope.projectId, options).catch(() => null)
				]);
				if (owner !== scope || ticket !== generation) return;
				const profiles = new Map((managed?.entries ?? []).filter((entry) => entry.access === 'managed').map((entry) => [entry.id, entry]));
				adminEntries = result.entries.map((entry) => entry.access === 'managed' ? { ...entry, managed: profiles.get(entry.id)?.managed ?? null } : entry);
				featured = adminEntries.filter((entry) => entry.featured);
				const needle = search.toLocaleLowerCase();
				managedEntries = adminEntries.filter((entry) => entry.access === 'managed' && [entry.name, entry.description, entry.registry_name].some((value) => value?.toLocaleLowerCase().includes(needle)));
				showAdminPage(start, search, type, start ? limit : loadedUntil);
			} else {
				const fetchPage = (offset: number, size: number) => {
					const params = new URLSearchParams({ offset: String(offset), limit: String(size), ...(search ? { q: search } : {}), ...(type ? { access: type } : {}), ...(state ? { state } : {}) });
					return api.get<McpSettingsPage>(`/api/v1/chat/mcp-settings?${params}`, scope.token, scope.projectId, options);
				};
				const managedParams = new URLSearchParams({ access: 'managed', offset: '0', limit: '100', ...(search ? { q: search } : {}) });
				const target = start ? start + limit : loadedUntil;
				const [page, defaults, rows, managed] = await Promise.all([
					fetchPage(start, Math.min(target - start, 100)),
					api.get<McpSettingsPage>('/api/v1/chat/mcp-settings?featured=true&offset=0&limit=100', scope.token, scope.projectId, options),
					api.get<McpConnection[]>('/api/v1/chat/mcp-servers', scope.token, scope.projectId, options),
					api.get<McpSettingsPage>(`/api/v1/chat/mcp-settings?${managedParams}`, scope.token, scope.projectId, options).catch(() => null)
				]);
				if (owner !== scope || ticket !== generation) return;
				const organization: McpConnection[] = [];
				let organizationUnavailable = page.organization_available === false || !page.domain_id;
				try {
					let next: number | null = 0;
					while (!organizationUnavailable && page.domain_id && next !== null) {
						const response: McpDomainPage = await api.get(`/api/v1/chat/domains/${encodeURIComponent(page.domain_id)}/mcp-connections?offset=${next}&limit=100`, scope.token, scope.projectId, options);
						if (owner !== scope || ticket !== generation) return;
						organization.push(...response.connections);
						if (response.next_offset !== null && response.next_offset <= next) throw new Error('Invalid catalog continuation');
						next = response.next_offset;
					}
				} catch {
					if (owner !== scope || ticket !== generation || controller.signal.aborted) return;
					organizationUnavailable = true;
					organization.length = 0;
				}
				if (owner !== scope || ticket !== generation) return;
				const pageEntries = [...page.entries];
				let next = page.next_offset;
				let last = start;
				while (!start && next !== null && next > last && next < target) {
					last = next;
					const extra = await fetchPage(next, Math.min(target - next, 100));
					if (owner !== scope || ticket !== generation) return;
					pageEntries.push(...extra.entries);
					next = extra.next_offset;
				}
				setPage(pageEntries, start);
				featured = defaults.entries;
				managedEntries = [...new Map([...(managed?.entries ?? []), ...(!search ? defaults.entries : []), ...pageEntries]
					.filter((entry) => entry.access === 'managed').map((entry) => [entry.id, entry])).values()];
				total = page.total; nextOffset = next !== null && next > last ? next : null;
				domainId = page.domain_id; organizationError = organizationUnavailable;
				canManage = !organizationUnavailable && page.can_manage_domain === true;
				if (!canManage && editor?.scope === 'domain') clearDraft();
				for (const entry of [...pageEntries, ...defaults.entries]) templates.set(entry.id, entry);
				connections = [...new Map([...pageEntries.flatMap((entry) => entry.connections ?? []), ...rows, ...organization, ...page.custom_connections]
					.filter((row) => visibleMcpConnection(row, scope.userId, scope.projectId, page.domain_id))
					.map((row) => [row.id, row])).values()];
			}
			if (start) loadedUntil = nextOffset ?? start + limit;
		} catch {
			if (owner === scope && ticket === generation) {
				error = t('loadFailed'); canManage = false;
				if (!start) { entries = []; featured = []; managedEntries = []; connections = []; }
				clearDraft();
			}
		} finally { if (owner === scope && ticket === generation) loading = false; }
	}
	function setPage(rows: McpTemplate[], start: number) {
		entries = start ? [...new Map([...entries, ...rows].map((entry) => [entry.id, entry])).values()] : rows;
	}
	function showAdminPage(start: number, search: string, access: string, size: number) {
		const needle = search.toLocaleLowerCase();
		const rows = adminEntries.filter((entry) => (!access || entry.access === access) && [entry.name, entry.registry_name, entry.description].some((value) => value?.toLocaleLowerCase().includes(needle)));
		total = rows.length; setPage(rows.slice(start, start + size), start); nextOffset = start + size < total ? start + size : null;
	}
	function editable(row: McpConnection) { return row.scope === 'domain' ? canManage && row.owner_domain_id === domainId : row.scope === 'user' && row.owner_user_id === owner?.userId; }
	function rowPath(row: McpConnection) {
		if (row.scope === 'domain') {
			if (!domainId) throw new Error('Organization authority unavailable');
			return `/api/v1/chat/domains/${encodeURIComponent(domainId)}/mcp-connections/${row.id}`;
		}
		return `/api/v1/chat/${row.template_key ? 'mcp-connections' : 'mcp-servers'}/${row.id}`;
	}
	async function action(key: string, work: (scope: Owner, signal: AbortSignal) => Promise<void>, allowed: () => boolean = () => canWrite) {
		if (!owner || busy[key] || !allowed()) return;
		const scope = owner, controller = new AbortController();
		mutations.add(controller); busy[key] = true; rowErrors[key] = '';
		try {
			await work(scope, AbortSignal.any([controller.signal, AbortSignal.timeout(30_000)]));
			if (owner !== scope || controller.signal.aborted || !allowed()) return;
			await load(scope);
			if (owner === scope) await onChanged();
		} catch { if (owner === scope && !controller.signal.aborted) rowErrors[key] = t('actionFailed'); }
		finally { mutations.delete(controller); if (owner === scope) busy[key] = false; }
	}
	function activate(row: McpConnection) {
		void action(String(row.id), async (scope, signal) => {
			const personal = row.scope === 'user';
			const path = personal ? rowPath(row) : row.scope === 'domain' ? `/api/v1/chat/domains/${encodeURIComponent(row.owner_domain_id!)}/mcp-connections/${row.id}/activation` : `/api/v1/chat/mcp-servers/${row.id}/activation`;
			const body = personal ? { is_active: !row.server_is_active } : { is_active: !row.is_active, config_version: row.config_version };
			await api.patch(path, body, scope.token, scope.projectId, { signal });
		});
	}
	function oauth(row: McpConnection, revoke = false) {
		void action(String(row.id), async (scope, signal) => {
			const path = `/api/v1/chat/mcp-servers/${row.id}/oauth`;
			if (revoke) await api.delete(path, scope.token, scope.projectId, { signal });
			else {
				const result = await api.post<{ authorization_url: string }>(`${path}/start`, undefined, scope.token, scope.projectId, { signal });
				if (owner !== scope || signal.aborted || !canWrite || (row.scope === 'domain' && !editable(row))) return;
				const destination = new URL(result.authorization_url, window.location.origin);
				const tutorialReturn = getActiveMockupProfile() !== null && destination.origin === window.location.origin;
				if (destination.protocol !== 'https:' && !tutorialReturn) throw new Error('Unsafe OAuth destination');
				window.location.assign(destination.href);
			}
		}, () => (revoke ? canDelete : canWrite) && (row.scope !== 'domain' || editable(row)));
	}
	function resetHeaders() {
		if (authMode !== 'admin') { headers = []; return; }
		headers = (editor?.template?.header_hints || []).filter((hint) => hint.name).map((hint) => ({
			name: hint.name!, value: '', fixed: true, required: !editor?.row && hint.required === true, description: hint.description
		}));
		if (!editor?.row && !headers.length) headers = [{ name: 'Authorization', value: '', fixed: false, required: true }];
	}
	async function openEditor(template?: McpTemplate, row?: McpConnection, scope: Editor['scope'] = 'user') {
		if (!owner || !canWrite || (row && !editable(row)) || (scope === 'domain' && !canManage)) return;
		clearDraft();
		const currentOwner = owner, ticket = editorGeneration;
		let source = template ?? (row?.template_key ? templates.get(row.template_key) : undefined);
		if (row?.template_key && !source) {
			const controller = new AbortController();
			mutations.add(controller); busy[row.id] = true; rowErrors[row.id] = '';
			try {
				let next: number | null = 0;
				while (next !== null && !source) {
					const page: McpSettingsPage = await api.get(`/api/v1/chat/mcp-settings?offset=${next}&limit=100`, currentOwner.token, currentOwner.projectId, { refresh: true, signal: controller.signal });
					if (owner !== currentOwner || ticket !== editorGeneration || controller.signal.aborted || !canWrite || !editable(row)) return;
					if (row.scope === 'domain' && (page.organization_available === false || page.domain_id !== domainId || page.can_manage_domain !== true)) {
						canManage = false;
						throw new Error('Organization manager authority unavailable');
					}
					for (const entry of page.entries) templates.set(entry.id, entry);
					source = templates.get(row.template_key);
					if (page.next_offset !== null && page.next_offset <= next) throw new Error('Invalid catalog continuation');
					next = page.next_offset;
				}
				if (!source) throw new Error('Template unavailable');
			} catch {
				if (owner === currentOwner && ticket === editorGeneration && !controller.signal.aborted) rowErrors[row.id] = t('actionFailed');
				return;
			} finally {
				mutations.delete(controller);
				if (owner === currentOwner) busy[row.id] = false;
			}
		}
		if (owner !== currentOwner || ticket !== editorGeneration || !canWrite || (row && !editable(row))) return;
		editor = { template: source, row, scope };
		label = row?.name || ''; editUrl = row?.url || '';
		published = row?.server_is_active === false ? 'false' : 'true';
		authMode = row?.auth_mode ?? (source?.access === 'oauth' ? 'oauth' : source?.access === 'credentials' ? 'admin' : 'none');
		variables = Object.fromEntries((row ? [] : source?.variables || []).map((name) => [name, '']));
		resetHeaders();
		const currentEditor = editor;
		void tick().then(() => {
			if (editor === currentEditor && owner === currentOwner) document.getElementById('mcp-connection-label')?.focus();
		});
	}
	function save() {
		if (!editor) return;
		const draft = editor, key = draft.row ? String(draft.row.id) : `template-${draft.template!.id}`;
		if (draft.scope === 'domain' && !canManage) return;
		const secretHeaders = Object.fromEntries((authMode === 'admin' ? headers : []).filter((header) => header.name.trim() && header.value).map((header) => [header.name.trim(), header.value]));
		const body = draft.row
			? { ...(draft.scope === 'domain' ? { name: label.trim(), url: editUrl.trim(), auth_mode: authMode, is_active: published === 'true' } : {}), ...(Object.keys(secretHeaders).length ? { headers: secretHeaders } : {}) }
			: { ...(draft.scope !== 'global' ? { template_id: draft.template!.id } : {}), label: label.trim() || undefined, variables: { ...variables }, auth_mode: authMode, ...(Object.keys(secretHeaders).length ? { headers: secretHeaders } : {}) };
		const path = draft.row ? rowPath(draft.row) : draft.scope === 'global' ? `/api/v1/chat/admin/mcp-registry/${encodeURIComponent(draft.template!.id)}/install` : draft.scope === 'domain' ? `/api/v1/chat/domains/${encodeURIComponent(domainId!)}/mcp-connections` : '/api/v1/chat/mcp-connections';
		clearDraft();
		void action(key, async (scope, signal) => {
			if (draft.row) await api.patch(path, body, scope.token, scope.projectId, { signal });
			else await api.post(path, body, scope.token, scope.projectId, { signal });
		}, () => canWrite && (draft.scope !== 'domain' || canManage));
	}
	function remove(row: McpConnection) {
		deleteTarget = null;
		void action(String(row.id), async (scope, signal) => { await api.delete(rowPath(row), scope.token, scope.projectId, { signal }); }, () => canDelete && editable(row));
	}
	function installFeatured() {
		void action('featured', async (scope, signal) => {
			const result = await api.post<{ counts: Record<string, number> }>('/api/v1/chat/admin/mcp-registry/install-featured', undefined, scope.token, scope.projectId, { signal });
			if (owner === scope && !signal.aborted) installSummary = t('installSummary', { created: result.counts.created ?? 0, existing: result.counts.existing ?? 0, skipped: result.counts.skipped ?? 0, failed: result.counts.failed ?? 0 });
		});
	}
	function reason(code?: string | null) {
		if (code === 'stdio_only') return t('stdioOnly');
		if (code === 'profile_not_in_enabled_sandbox_manifest') return t('profileMissing');
		if (code === 'execution_protocol_v2_unavailable') return t('protocolMissing');
		return t('unavailable');
	}
</script>

<svelte:window onpopstate={() => restoreTab()} />

<section class="gallery" aria-labelledby={`${id}-title`}>
	<header class="workspace-header">
		<div><h2 id={`${id}-title`}>{t('workspace.title')}</h2><p>{t('workspace.description')}</p></div>
		{#if admin}
			{#if remoteForm}<Button size="sm" disabled={!canWrite} onclick={openRemote}>{t('workspace.remote')}</Button>{/if}
		{:else}
			<ConnectionMenu label={t('workspace.add')} primary disabled={!canWrite}
				items={[
					{ label: t('connectPersonal'), run: () => addFromBrowse('user') },
					...(canManage ? [{ label: t('connectOrganization'), run: () => addFromBrowse('domain') }] : []),
					...(remoteForm ? [{ label: t('workspace.remote'), run: openRemote }] : [])
				]} />
		{/if}
	</header>
	<div class="workspace-navigation">
		<ConnectionTabs selected={tab} count={connected.length} {id} onchange={changeTab} />
		<Button variant="ghost" size="sm" class="workspace-refresh" ariaLabel={t('refresh')} title={t('refresh')} disabled={loading || !owner} onclick={() => { refresh(); if (!admin) void refreshManagedSandboxTools(); }}>
			<svg aria-hidden="true" viewBox="0 0 20 20" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M16 8a6.5 6.5 0 1 0 .15 3.25M16 4v4h-4"/></svg>
			<span class="refresh-label">{t('refresh')}</span>
		</Button>
	</div>
	{#if error}<Alert tone="danger">{error}</Alert>{/if}
	{#if rowErrors.featured}<Alert tone="danger">{rowErrors.featured}</Alert>{/if}
	{#if installSummary}<Alert tone="info">{installSummary}</Alert>{/if}
	{#if loading}<LoadingState variant="inline" label={t('loading')} />{/if}
	{#if owner && organizationError}
		<section aria-label={t('organization')}>
			<Alert tone="warning" flat>{connections.some((row) => row.scope === 'domain') ? t('organizationManagementUnavailable') : t('organizationUnavailable')}</Alert>
		</section>
	{/if}

	{#each connectionTabs as panel (panel)}
		<div role="tabpanel" id={`${id}-panel-${panel}`} aria-labelledby={`${id}-tab-${panel}`} hidden={tab !== panel}>
			{#if tab === panel}{@render panelBody()}{/if}
		</div>
	{/each}
</section>

{#snippet panelBody()}
	<div class="tab-content">

	{#if tab !== 'manage'}
		<search aria-label={t('search')} class="search-tools">
			<div class="search-input">
				<TextInput id={`${id}-search`} type="search" ariaLabel={t('search')} placeholder={t('search')} bind:value={query} maxlength={100} oninput={scheduleSearch}
					onkeydown={(event) => { if (event.key === 'Enter' && !event.isComposing) { event.preventDefault(); applyFilters(); } }} />
			</div>
			<SelectInput ariaLabel={t('workspace.allTypes')} value={access} onchange={(event) => { access = (event.currentTarget as HTMLSelectElement).value as typeof access; applyFilters(); }}>
				<option value="">{t('workspace.allTypes')}</option>
				{#each accessModes as mode}<option value={mode}>{t(`workspace.access.${mode}`)}</option>{/each}
			</SelectInput>
			{#if tab === 'connected' && !admin}
				<SelectInput ariaLabel={t('workspace.allScopes')} value={scopeFilter} onchange={(event) => { scopeFilter = (event.currentTarget as HTMLSelectElement).value as typeof scopeFilter; applyFilters(); }}>
					<option value="">{t('workspace.allScopes')}</option>
					{#each scopes as scope}<option value={scope}>{t(`workspace.scope.${scope}`)}</option>{/each}
				</SelectInput>
			{/if}
		</search>
	{/if}

	{#if editor}
		<form class="editor" aria-labelledby="mcp-editor-title" method="post" onsubmit={(event) => { event.preventDefault(); save(); }}>
			<h3 id="mcp-editor-title">{editor.row ? t('editTitle', { name: editor.row.name }) : t('connectTitle', { name: editor.template!.name })}</h3>
			<p>{editor.scope === 'domain' ? t('sharedWarning') : editor.scope === 'global' ? t('globalWarning') : t('personalHelp')}</p>
			<p>{t('schemaHelp')}</p>
			<Field label={editor.row ? settingsT('extensions.mcp.namePlaceholder') : t('label')} for="mcp-connection-label"><TextInput id="mcp-connection-label" bind:value={label} maxlength={100} required={!!editor.row && editor.scope === 'domain'} /></Field>
			{#if editor.row && editor.scope === 'domain'}<Field label={t('url')} for="mcp-connection-url"><TextInput id="mcp-connection-url" type="url" bind:value={editUrl} required /></Field>{/if}
			{#each editor.row ? [] : editor.template?.variables || [] as variable}<Field label={t('variable', { name: variable })} for={`mcp-variable-${variable}`}><TextInput id={`mcp-variable-${variable}`} bind:value={variables[variable]} required autocomplete="off" /></Field>{/each}
			{#if editor.template?.access === 'configure' || (editor.row && editor.scope === 'domain')}<Field label={t('authMode')} for="mcp-connection-auth"><SelectInput id="mcp-connection-auth" bind:value={authMode} onchange={resetHeaders}><option value="none">{t('public')}</option><option value="oauth">OAuth</option><option value="admin">{t('credentials')}</option></SelectInput></Field>{/if}
			{#if editor.row && editor.scope === 'domain'}<Field label={t('publication')} for="mcp-publication"><SelectInput id="mcp-publication" bind:value={published}><option value="true">{t('published')}</option><option value="false">{t('unpublished')}</option></SelectInput></Field>{/if}
			{#if authMode === 'admin'}
				<fieldset><legend>{t('headers')}</legend><p>{t('secretHelp')}</p>
					{#each headers as header, index}<div class="header-fields" class:declared-header={header.fixed}>
						{#if !header.fixed}<Field label={t('headerName')} for={`mcp-header-name-${index}`}><TextInput id={`mcp-header-name-${index}`} bind:value={header.name} required autocomplete="off" /></Field>{/if}
						<Field label={header.fixed ? header.name : t('headerValue')} for={`mcp-header-value-${index}`} help={header.description}><TextInput id={`mcp-header-value-${index}`} type="password" bind:value={header.value} required={header.required} autocomplete="new-password" /></Field>
						{#if !header.fixed}<Button variant="subtle" size="sm" onclick={() => headers = headers.filter((_, position) => position !== index)}>{t('removeHeader')}</Button>{/if}
					</div>{/each}
					{#if !editor.template?.header_hints.some((hint) => !!hint.name)}<Button variant="secondary" size="sm" onclick={() => headers = [...headers, { name: '', value: '', fixed: false, required: true }]}>{t('addHeader')}</Button>{/if}
				</fieldset>
			{/if}
			<div class="actions"><Button variant="secondary" onclick={clearDraft}>{t('cancel')}</Button><Button type="submit">{t('save')}</Button></div>
		</form>
	{/if}
	{#if tab === 'browse'}
		{#if preferredScope}<p class="scope-choice" role="status">{t(preferredScope === 'domain' ? 'connectOrganization' : 'connectPersonal')}</p>{/if}
		{#if !error && (featuredRows.length || admin)}
			<section class="catalog-section">
				<header><h3>{t('featured')}</h3>{#if admin}<Button size="sm" variant="outline" disabled={!canWrite || busy.featured} onclick={installFeatured}>{t('installFeatured')}</Button>{/if}</header>
				<div class="template-grid">{#each featuredRows as entry (entry.id)}{@render templateRow(entry)}{/each}</div>
			</section>
		{/if}
		{#if !error && builtinRows.length}
			<section class="catalog-section">
				<header><h3>{t('builtIn')}</h3></header>
				<div class="template-grid">{#each builtinRows as entry (entry.id)}{@render templateRow(entry)}{/each}</div>
			</section>
		{/if}
		<section class="catalog-section">
			<header><h3>{t('browse')} <span class="count">({total.toLocaleString(intlLocale())})</span></h3></header>
			{#if !loading && !error && !entries.length}<p class="empty">{t('emptySearch')}</p>{/if}
			<div class="template-grid">{#each entries.filter((entry) => entry.access !== 'managed') as entry (entry.id)}{@render templateRow(entry)}{/each}</div>
			{#if nextOffset !== null}
				<div class="more"><Button variant="outline" size="sm" disabled={loading} onclick={() => owner && nextOffset !== null && void load(owner, nextOffset)}>{t('workspace.more')}</Button></div>
			{/if}
		</section>
	{:else if tab === 'connected'}
		{#if connected.length}
			<ConnectionsTable label={t('workspace.connected')} rows={connected} keyOf={(row) => row.key}
				columns={[
					{ key: 'status', label: t('workspace.status'), cell: connectionStatus },
					{ key: 'name', label: t('workspace.name'), cell: connectionName },
					{ key: 'scope', label: t('workspace.scopeLabel'), cell: connectionScope },
					{ key: 'description', label: t('workspace.details'), cell: connectionDescription },
					{ key: 'count', label: t('workspace.tools'), cell: connectionCount }
				]}
				name={connectionName} actionsLabel={t('workspace.manage')} actions={manageRow}
				expanded={(row) => expanded.has(row.key)} details={rowDetails} />
		{:else if inventoryLoading && !loading}
			<LoadingState variant="inline" label={settingsT('extensions.mcp.loading')} />
		{:else if !loading && !error && !(organizationError && scopeFilter === 'domain')}
			<div class="empty">
				<p>{t(appliedQuery || access || scopeFilter ? 'emptySearch' : 'emptyConnections')}</p>
				<Button variant="link" size="sm" href={`${page.url.pathname}?${browseParams()}`} onclick={(event) => { if (event.button === 0 && !event.metaKey && !event.ctrlKey && !event.shiftKey && !event.altKey) { event.preventDefault(); changeTab('browse'); void tick().then(() => document.getElementById(`${id}-tab-browse`)?.focus()); } }}>{t('workspace.browse')}</Button>
			</div>
		{/if}
	{:else}
		<div id={`${id}-remote`}>{@render remoteForm?.()}</div>
		{@render approved?.()}
		{#if !admin}
			<ManagedSandboxToolsPicker summaryOnly />
			{#if domainId && !organizationError}
				<section class="scope-note">
					<h3>{t('organization')}</h3>
					<p>{t('domain')}: <code>{domainId}</code></p>
					<p>{canManage ? t('managerHelp') : t('memberHelp')}</p>
				</section>
			{/if}
		{/if}
	{/if}
	</div>
{/snippet}

{#snippet templateRow(entry: McpTemplate)}
	{@const matching = preferredScope ? undefined : rowsByTemplate.get(entry.id)?.[0]}
	{@const unavailable = entry.access === 'unreachable' || entry.access === 'unavailable'}
	{@const blocked = !canWrite || loading || !!busy[`template-${entry.id}`]}
	<article class="template" aria-label={entry.name}>
		<div class="template-line">
			<details>
				<summary aria-label={`${entry.name} · ${t('workspace.details')}`}>
					<ConnectionName name={entry.name} identity={entry.id} description={entry.description}>
						{#snippet badge()}<Pill tone="neutral" size="xs">{t(entry.access === 'managed' ? 'builtIn' : `workspace.access.${entry.access}`)}</Pill>{/snippet}
					</ConnectionName>
					<svg aria-hidden="true" viewBox="0 0 16 16" width="12" height="12" fill="none" stroke="currentColor" stroke-width="1.5"><path d="m6 4 4 4-4 4"/></svg>
				</summary>
				<div class="template-meta">
					<p class="endpoint">{entry.registry_name}</p>
					{#if entry.description}<p>{entry.description}</p>{/if}
					{#if entry.access === 'managed' && admin && entry.managed?.tools.length}<p>{entry.managed.tools.join(', ')}</p>
					{:else if !unavailable && entry.access !== 'managed'}<p>{t(entry.access === 'oauth' ? 'oauthHelp' : entry.access === 'credentials' ? 'credentialsHelp' : entry.access === 'configure' ? 'configureHelp' : 'publicHelp')}</p>{/if}
				</div>
			</details>
			{#if unavailable}
				<p class="unavailable">{reason(entry.unavailable_reason)}</p>
			{:else if entry.access !== 'managed'}
				{#if matching}
					<Button variant="outline" size="sm" onclick={() => jumpToRow(matching.id)}>{t('workspace.manage')}</Button>
				{:else if canManage && !preferredScope && !admin}
					<ConnectionMenu label={t('workspace.connect')} disabled={blocked} items={[
						{ label: t('connectPersonal'), run: () => void openEditor(entry, undefined, 'user') },
						{ label: t('connectOrganization'), run: () => void openEditor(entry, undefined, 'domain') }
					]} />
				{:else}
					<Button variant="outline" size="sm" disabled={blocked || (preferredScope === 'domain' && !canManage)}
						onclick={() => openEditor(entry, undefined, admin ? 'global' : preferredScope ?? 'user')}>{t(admin ? 'install' : 'workspace.connect')}</Button>
				{/if}
			{/if}
		</div>
		{#if entry.access === 'managed'}
			<p>{entry.managed ? entry.managed.available ? t('managedAvailable') : reason(entry.managed.reason) : t('managedUnknown')}</p>
			{#if !admin && (entry.managed?.profile || entry.managed_profile)}
				<ManagedSandboxToolsPicker profileId={entry.managed?.profile || entry.managed_profile || undefined} showReadiness={false} />
			{/if}
		{/if}
		{#if rowErrors[`template-${entry.id}`]}<Alert tone="danger" flat>{rowErrors[`template-${entry.id}`]}</Alert>{/if}
	</article>
{/snippet}

{#snippet connectionStatus(row: ConnectedRow)}
	<ConnectionStatus state={row.state} label={t(row.state === 'error' ? 'workspace.error' : row.state)} />
{/snippet}
{#snippet connectionName(row: ConnectedRow)}
	<ConnectionName name={row.server?.name ?? 'Afterglow MCP'} identity={row.server?.template_key ?? row.server?.name ?? 'Afterglow MCP'} />
{/snippet}
{#snippet connectionScope(row: ConnectedRow)}
	<Pill tone="neutral" size="xs">{t(`workspace.scope.${row.server?.scope ?? 'user'}`)}</Pill>
{/snippet}
{#snippet connectionDescription(row: ConnectedRow)}
	<span class="single-line" title={row.description}>{row.description || '—'}</span>
{/snippet}
{#snippet connectionCount(row: ConnectedRow)}
	{row.count?.toLocaleString(intlLocale()) ?? '—'}
{/snippet}

{#snippet manageRow(row: ConnectedRow)}
	<span data-connection-key={`${id}-${row.key}`}>
		<Button variant="outline" size="sm" ariaExpanded={expanded.has(row.key)} ariaLabel={`${t('workspace.manage')} ${row.server?.name ?? 'Afterglow MCP'}`}
			onclick={() => expanded.has(row.key) ? expanded.delete(row.key) : expanded.add(row.key)}>{t('workspace.manage')}</Button>
	</span>
{/snippet}

{#snippet rowDetails(item: ConnectedRow)}
	<div class="detail-body">
		{#if item.server}
			{@const row = item.server}
			<div class="metadata">
				{#if row.config_version != null}<span>{t('revision', { version: row.config_version })}</span>{/if}
				{#if row.has_headers != null || row.auth_mode === 'admin'}<span>{t(row.has_headers ? 'headersSaved' : 'workspace.headersMissing')}</span>{/if}
				{#if row.transport}<span>{row.transport}</span>{/if}
			</div>
			{#if row.url}<p class="endpoint">{row.url}</p>{/if}
			{#if row.catalog_error}<p>{t('catalogError')}</p>{/if}
			{#if row.tools?.length}
				<div><h3>{t('tools', { count: row.tool_count ?? row.tools.length })}</h3><p>{t('schemaHelp')}</p>
					<ul>{#each row.tools as tool}<li><strong>{tool.name}</strong>{tool.description ? ` — ${tool.description}` : ''}</li>{/each}</ul>
				</div>
			{/if}
			{#if admin}
				{@render adminActions?.(row)}
			{:else if row.scope === 'global' && !row.template_key && approvedActions}
				{@render approvedActions(row.id)}
			{:else}
				<div class="actions">
					<Button variant="secondary" size="sm" disabled={!!busy[row.id] || !canWrite || (row.scope !== 'user' && !row.server_is_active) || !row.config_version} onclick={() => activate(row)}>{(row.scope === 'user' ? row.server_is_active : row.is_active) ? t('deactivate') : t('activate')}</Button>
					{#if row.auth_mode === 'oauth' && (row.scope !== 'domain' || editable(row))}
						<Button variant="outline" size="sm" disabled={!!busy[row.id] || !canWrite} onclick={() => oauth(row)}>{row.auth_connected ? t('reconnect') : t('connectOAuth')}</Button>
						{#if row.auth_connected}<Button variant="subtle" size="sm" disabled={!!busy[row.id] || !canDelete} onclick={() => revokeTarget = row}>{t('revokeOAuth')}</Button>{/if}
					{/if}
					{#if editable(row)}
						{#if row.scope === 'domain' || (row.template_key && row.auth_mode === 'admin')}
							<Button variant="subtle" size="sm" disabled={!!busy[row.id] || !canWrite} onclick={() => openEditor(undefined, row, row.scope)}>{t('edit')}</Button>
						{/if}
						<Button variant="danger-outline" size="sm" disabled={!!busy[row.id] || !canDelete} onclick={() => deleteTarget = row}>{t('delete')}</Button>
					{/if}
				</div>
			{/if}
			{#if rowErrors[row.id]}<Alert tone="danger" flat>{rowErrors[row.id]}</Alert>{/if}
			{#if deleteTarget?.id === row.id}
				<Alert tone="warning" flat>{t('deleteConfirm', { name: row.name })}</Alert>
				<div class="actions"><Button variant="secondary" size="sm" onclick={() => deleteTarget = null}>{t('cancel')}</Button><Button variant="danger" size="sm" onclick={() => remove(row)}>{t('delete')}</Button></div>
			{/if}
			{#if revokeTarget?.id === row.id}
				<Alert tone="warning" flat>{t('revokeConfirm', { name: row.name })}</Alert>
				<div class="actions"><Button variant="secondary" size="sm" onclick={() => revokeTarget = null}>{t('cancel')}</Button><Button variant="danger" size="sm" onclick={() => { revokeTarget = null; oauth(row, true); }}>{t('revokeOAuth')}</Button></div>
			{/if}
		{:else}
			{@render approved?.()}
		{/if}
	</div>
{/snippet}

<style>
	.gallery { display: grid; gap: 1rem; min-width: 0; color: var(--color-ink-1); }
	h2, h3 { margin: 0; font-weight: 600; color: var(--color-ink-0); }
	h2 { font-size: 1.25rem; }
	h3 { font-size: var(--type-body); }
	p { margin: 0.25rem 0 0; font-size: var(--type-support); color: var(--color-ink-2); overflow-wrap: anywhere; }
	.workspace-header, .workspace-navigation, .catalog-section > header { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 0.5rem 1rem; }
	.workspace-header > div:first-child { flex: 1 1 17rem; min-width: 0; }
	.workspace-header p { max-inline-size: 68ch; }
	.search-tools { display: flex; flex-wrap: wrap; gap: 0.5rem; }
	.search-tools :global(.select-input) { flex: 0 1 auto; inline-size: auto; max-inline-size: 100%; }
	.search-input { flex: 1 1 14rem; min-inline-size: 0; }
	.tab-content { display: grid; gap: 1.375rem; min-inline-size: 0; }
	.catalog-section { display: grid; gap: 0.5rem; }
	.template-grid { display: grid; gap: 0 1.125rem; grid-template-columns: repeat(auto-fit, minmax(min(100%, max(17rem, calc((100% - 1.125rem) / 2))), 1fr)); }
	.template { min-width: 0; border-block-start: 1px solid var(--color-line); padding-block: 0.625rem; }
	.template-line { display: flex; align-items: flex-start; gap: 0.625rem; }
	.template-line > :global(button), .template-line > :global(.menu-group) { margin-inline-start: auto; }
	.unavailable { flex: 0 1 9rem; min-inline-size: 0; text-align: end; }
	.template details { flex: 1 1 0; min-inline-size: 0; font-size: var(--type-support); color: var(--color-ink-2); }
	.template summary { display: flex; min-block-size: var(--control-height); align-items: center; justify-content: space-between; gap: 0.375rem; cursor: pointer; }
	.template summary::-webkit-details-marker { display: none; }
	.template summary :global(.name) { flex: 1; }
	.template summary svg { flex: none; }
	.template details[open] summary svg { rotate: 90deg; }
	.template-meta { margin-inline-start: 2.625rem; }
	.template summary:focus-visible { outline: 2px solid var(--color-accent); outline-offset: 2px; }
	.single-line { display: block; overflow: hidden; white-space: nowrap; text-overflow: ellipsis; color: var(--color-ink-2); }
	.actions, .metadata { display: flex; flex-wrap: wrap; align-items: center; gap: 0.5rem; }
	.metadata { font-size: var(--type-support); color: var(--color-ink-2); }
	.endpoint { overflow-wrap: anywhere; font-size: var(--type-identifier); }
	.detail-body { display: grid; gap: 0.625rem; width: 100%; text-align: start; overflow-wrap: anywhere; }
	.detail-body ul { margin: 0.375rem 0; padding-inline-start: 1.25rem; font-size: var(--type-support); list-style: disc; }
	.scope-note { border-block-start: 1px solid var(--color-line); padding-block-start: 0.875rem; }
	.scope-choice { border-block-end: 1px solid var(--color-line); padding-block-end: 0.5rem; }
	.more { display: flex; justify-content: center; margin-block-start: 0.375rem; }
	.empty { display: grid; justify-items: start; gap: 0.375rem; border-block: 1px solid var(--color-line); padding-block: 1rem; }
	.count { color: var(--color-ink-2); font-weight: 400; font-variant-numeric: tabular-nums; }
	.editor { display: grid; gap: 0.75rem; border-block: 1px solid var(--color-line); padding-block: 1rem; }
	fieldset { display: grid; gap: 0.75rem; min-width: 0; border: 0; padding: 0; }
	legend { font-size: var(--type-body); font-weight: 500; }
	.header-fields { display: grid; gap: 0.75rem; align-items: end; }
	@media (min-width: 768px) { .header-fields:not(.declared-header) { grid-template-columns: minmax(0, 1fr) minmax(0, 1fr) auto; } }
	@media (max-width: 767px), (pointer: coarse) { .template summary { min-block-size: var(--control-touch-height); align-content: center; } }
	@media (max-width: 767px) {
		.template-grid { grid-template-columns: minmax(0, 1fr); }
		.workspace-navigation { flex-wrap: nowrap; gap: 0.375rem; }
		.workspace-navigation :global(.workspace-refresh) { min-inline-size: var(--control-touch-height); }
		.refresh-label { display: none; }
		.search-input { flex-basis: 100%; }
		.search-tools :global(.select-input) { flex: 1 1 8rem; min-inline-size: 0; }
	}
</style>
