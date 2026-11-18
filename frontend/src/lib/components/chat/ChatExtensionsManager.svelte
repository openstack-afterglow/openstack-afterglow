<script lang="ts">
	import LoadingState from '$lib/components/ui/LoadingState.svelte';
	import { onMount, untrack } from 'svelte';
	import { derived } from 'svelte/store';
	import { auth, authReady, projectSwitching } from '$lib/stores/auth';
	import { api, ApiError } from '$lib/api/client';
	import { serviceCapabilities } from '$lib/stores/servicePermissions';
	import LumenPermissionNotice from './LumenPermissionNotice.svelte';
	import ChatMcpCatalogue, { type ApprovedMcpWorkspace } from './ChatMcpCatalogue.svelte';
	import ChatMcpGallery from './ChatMcpGallery.svelte';
	import type { McpConnection } from '$lib/api/mcpCatalog';
	import ConnectionStatus from './connections/ConnectionStatus.svelte';
	import ConnectionName from './connections/ConnectionName.svelte';
	import ConnectionsTable from './connections/ConnectionsTable.svelte';
	import Field from '$lib/components/ui/Field.svelte';
	import FormModal from '$lib/components/ui/FormModal.svelte';
	import TextInput from '$lib/components/ui/TextInput.svelte';
	import SelectInput from '$lib/components/ui/SelectInput.svelte';
	import { t as galleryT } from '$lib/i18n/ns/mcp-gallery';
	import { confirmDialog } from '$lib/stores/confirm.svelte';
	import { toast } from '$lib/stores/toast';
	import Button from '$lib/components/ui/Button.svelte';
	import Pill from '$lib/components/ui/Pill.svelte';
	import { t } from '$lib/i18n/ns/chat-settings';
	import RichText from '$lib/i18n/RichText.svelte';

	// base: '/api/v1/chat/admin' (관리자 global) 또는 '/api/v1/chat' (사용자 본인)
	// only: 특정 섹션만 렌더('mcp' | 'tools' | 'skills'). 미지정 시 전부.
	let { base, only }: { base: string; only?: 'mcp' | 'tools' | 'skills' } = $props();

	interface McpServer extends McpConnection {
		oauth_scopes?: string[];
		has_oauth_client?: boolean;
		has_oauth_client_secret?: boolean;
		load_policy?: 'preloaded' | 'on_demand';
		activation_config_version?: number | null;
	}
	interface McpOAuthStatus {
		required: boolean;
		connected: boolean;
		expires_at: string | null;
	}
	interface CustomTool {
		id: number;
		scope: string;
		name: string;
		description: string;
		method: string;
		url: string;
		load_policy?: 'preloaded' | 'on_demand';
		is_active: boolean;
	}
	interface Skill {
		id: number;
		scope: string;
		name: string;
		description: string | null;
		instructions: string;
		is_active: boolean;
	}

	const token = $derived($auth.token ?? undefined);
	const projectId = $derived($auth.projectId ?? undefined);

	let mcps = $state<McpServer[]>([]);
	let tools = $state<CustomTool[]>([]);
	let skills = $state<Skill[]>([]);
	let loading = $state(true);
	let catalogLoaded = $state(false);
	let loadGeneration = 0;
	let gallery: { refresh: () => void } | undefined = $state();
	const id = $props.id();
	const approvedServers = $derived(mcps.filter((mcp) => mcp.scope === 'global' && !mcp.template_key));

	const isAdmin = $derived(base.includes('/admin'));
	const canMcp = $derived(isAdmin ? $auth.isSystemAdmin === true : $serviceCapabilities('lumen-mcp_editor'));
	const canAssets = $derived(isAdmin ? $auth.isSystemAdmin === true : $serviceCapabilities('lumen-assets_editor'));
	const canDelete = $derived(isAdmin ? $auth.isSystemAdmin === true : $serviceCapabilities('lumen-resources_admin'));

	let mName = $state('');
	let mTransport = $state('http');
	let mUrl = $state('');
	let mHeaders = $state(''); // admin-only `Header-Name: value` lines → dict
	let mAuthMode = $state<'none' | 'oauth' | 'admin'>('none');
	let mOAuthScopes = $state('');
	let mOAuthClientId = $state('');
	let mOAuthClientSecret = $state('');
	let mLoadPolicy = $state<'preloaded' | 'on_demand'>('on_demand');
	let addingMcp = $state(false);

	let oauthStatus = $state<Record<number, McpOAuthStatus>>({});
	let mcpRequest: AbortController | null = null;

	/** 'Header-Name: value' 형식 줄들을 dict 로 파싱. 빈 줄/':' 없는 줄 무시. */
	function parseHeaders(text: string): Record<string, string> {
		const out: Record<string, string> = {};
		for (const line of text.split('\n')) {
			const idx = line.indexOf(':');
			if (idx <= 0) continue;
			const k = line.slice(0, idx).trim();
			const v = line.slice(idx + 1).trim();
			if (k && v) out[k] = v;
		}
		return out;
	}

	let tName = $state('');
	let tDesc = $state('');
	let tMethod = $state('GET');
	let tUrl = $state('');
	let tLoadPolicy = $state<'preloaded' | 'on_demand'>('on_demand');
	let addingTool = $state(false);
	let toolDialog = $state(false);
	let toolForm = $state<HTMLFormElement>();
	let toolQuery = $state('');
	let ownerGeneration = 0;
	const filteredTools = $derived.by(() => {
		const needle = toolQuery.trim().toLocaleLowerCase();
		return tools.filter((tool) => [tool.name, tool.method, tool.description, tool.url].some((value) => value?.toLocaleLowerCase().includes(needle)));
	});

	function closeToolDialog() {
		toolDialog = false;
		tName = ''; tDesc = ''; tMethod = 'GET'; tUrl = ''; tLoadPolicy = 'on_demand';
	}

	function clearRemoteSecrets() {
		mHeaders = '';
		mOAuthClientSecret = '';
	}

	let sName = $state('');
	let sDesc = $state('');
	let sInstructions = $state('');
	let addingSkill = $state(false);

	async function load() {
		if (!token) return;
		const requestToken = token;
		const requestProject = projectId;
		const includePrivate = !isAdmin && canAssets;
		loading = true;
		const generation = ++loadGeneration;
		try {
			const [ms, ts, ss] = await Promise.all([
				api.get<McpServer[]>(`${base}/mcp-servers`, token, projectId),
				api.get<CustomTool[]>(`${base}/custom-tools`, token, projectId),
				api.get<Skill[]>(`${base}/skills${includePrivate ? '?include_private=true' : ''}`, token, projectId)
			]);
			if (generation !== loadGeneration || requestToken !== token || requestProject !== projectId || (includePrivate && !canAssets)) return;
			mcps = ms;
			tools = ts;
			skills = ss;
			const statuses = isAdmin
				? {}
				: Object.fromEntries(
						await Promise.all(
							ms
								.filter((mcp) => mcp.scope === 'global' && !mcp.template_key && mcp.auth_mode === 'oauth')
								.map(async (mcp) => [
									mcp.id,
									await api.get<McpOAuthStatus>(`${base}/mcp-servers/${mcp.id}/oauth`, requestToken, requestProject)
								] as const)
						)
					);
			if (generation === loadGeneration && requestToken === token && requestProject === projectId) {
				oauthStatus = statuses;
				catalogLoaded = true;
			}
		} catch {
			if (generation === loadGeneration) toast.error(t('extensions.loadFailed'));
		} finally {
			if (generation === loadGeneration) loading = false;
		}
	}

	async function addSkill() {
		if (!canAssets) return;
		if (!sName.trim() || !sInstructions.trim()) {
			toast.error(t('extensions.skills.nameInstructionsRequired'));
			return;
		}
		addingSkill = true;
		try {
			await api.post(
				`${base}/skills`,
				{ name: sName.trim(), description: sDesc.trim() || null, instructions: sInstructions.trim() },
				token,
				projectId
			);
			sName = '';
			sDesc = '';
			sInstructions = '';
			await load();
			toast.success(t('extensions.skills.added'));
		} catch (e) {
			toast.error(e instanceof ApiError ? e.message : t('extensions.addFailed'));
		} finally {
			addingSkill = false;
		}
	}

	async function addMcp() {
		if (!canMcp) return;
		if (!mName.trim()) {
			toast.error(t('extensions.mcp.nameRequired'));
			return;
		}
		if (!mUrl.trim()) {
			toast.error(t('extensions.mcp.urlRequired'));
			return;
		}
		addingMcp = true;
		const request = new AbortController();
		mcpRequest = request;
		const requestToken = token, requestProject = projectId;
		try {
			const headers = parseHeaders(mHeaders);
			const oauthScopes = mOAuthScopes.split(/[\s,]+/).filter(Boolean);
			const oauthClientSecret = mOAuthClientSecret;
			mHeaders = '';
			mOAuthClientSecret = '';
			await api.post(
				`${base}/mcp-servers`,
				{
					name: mName.trim(),
					transport: mTransport,
					url: mUrl.trim(),
					...(isAdmin
						? {
								auth_mode: mAuthMode,
								...(Object.keys(headers).length ? { headers } : {}),
								...(oauthScopes.length ? { oauth_scopes: oauthScopes } : {}),
								...(mOAuthClientId.trim() ? { oauth_client_id: mOAuthClientId.trim() } : {}),
								...(oauthClientSecret ? { oauth_client_secret: oauthClientSecret } : {}),
								load_policy: mLoadPolicy
							}
						: {})
				},
				requestToken,
				requestProject,
				{ signal: request.signal }
			);
			if (request.signal.aborted || mcpRequest !== request) return;
			mName = '';
			mUrl = '';
			mHeaders = '';
			mAuthMode = 'none';
			mOAuthScopes = '';
			mOAuthClientId = '';
			mOAuthClientSecret = '';
			mLoadPolicy = 'on_demand';
			await load();
			if (request.signal.aborted || mcpRequest !== request) return;
			gallery?.refresh();
			toast.success(t('extensions.mcp.added'));
		} catch (e) {
			if (!request.signal.aborted) toast.error(t('extensions.addFailed'));
		} finally {
			if (mcpRequest === request) { addingMcp = false; mcpRequest = null; }
		}
	}

	async function addTool() {
		if (!canAssets || addingTool) return;
		if (!tName.trim() || !tUrl.trim()) {
			toast.error(t('extensions.tools.nameUrlRequired'));
			return;
		}
		addingTool = true;
		const owner = ownerGeneration;
		try {
			await api.post(
				`${base}/custom-tools`,
				{
					name: tName.trim(),
					description: tDesc.trim() || tName.trim(),
					method: tMethod,
					url: tUrl.trim(),
					...(isAdmin ? { load_policy: tLoadPolicy } : {})
				},
				token,
				projectId
			);
			if (owner !== ownerGeneration) return;
			closeToolDialog();
			await load();
			if (owner === ownerGeneration) toast.success(t('extensions.tools.added'));
		} catch (e) {
			if (owner === ownerGeneration) toast.error(e instanceof ApiError ? e.message : t('extensions.addFailed'));
		} finally {
			if (owner === ownerGeneration) addingTool = false;
		}
	}

	async function removeItem(
		kind: 'mcp-servers' | 'custom-tools' | 'skills',
		id: number,
		name: string
	) {
		const owner = ownerGeneration;
		const ok = await confirmDialog(
			t('extensions.deleteConfirm', { kind, name }),
			{ confirmLabel: t('extensions.actions.delete') }
		);
		if (!ok || !canDelete || owner !== ownerGeneration) return;
		try {
			await api.delete(`${base}/${kind}/${id}`, token, projectId);
			if (owner === ownerGeneration) await load();
		} catch {
			if (owner === ownerGeneration) toast.error(t('extensions.deleteFailed', { kind, name }));
		}
	}

	async function toggle(kind: 'mcp-servers' | 'custom-tools' | 'skills', id: number, isActive: boolean) {
		if (!(kind === 'mcp-servers' ? canMcp : canAssets)) return;
		const owner = ownerGeneration;
		try {
			await api.patch(`${base}/${kind}/${id}`, { is_active: !isActive }, token, projectId);
			if (owner === ownerGeneration) await load();
		} catch {
			if (owner === ownerGeneration) toast.error(t('extensions.changeFailed'));
		}
	}

	async function setLoadPolicy(
		kind: 'mcp-servers' | 'custom-tools',
		id: number,
		loadPolicy: 'preloaded' | 'on_demand'
	) {
		if (!(kind === 'mcp-servers' ? canMcp : canAssets)) return;
		const owner = ownerGeneration;
		try {
			await api.patch(`${base}/${kind}/${id}`, { load_policy: loadPolicy }, token, projectId);
			if (owner === ownerGeneration) await load();
		} catch {
			if (owner === ownerGeneration) toast.error(t('extensions.loadPolicy.changeFailed'));
		}
	}

	onMount(() => {
		const unsubscribe = derived([auth, authReady, projectSwitching], ([actor, ready, switching]) =>
			ready && !switching && actor.token && actor.projectId && actor.userId
				? `${actor.token}\u0000${actor.userId}\u0000${actor.projectId}\u0000${actor.domainId}` : null
		).subscribe(() => {
			++loadGeneration;
			++ownerGeneration;
			closeToolDialog(); addingTool = false; toolQuery = '';
			mcpRequest?.abort();
			mcpRequest = null;
			addingMcp = false;
			mHeaders = '';
			mOAuthClientSecret = '';
			mName = ''; mUrl = ''; mOAuthClientId = ''; mOAuthScopes = ''; mAuthMode = 'none'; mLoadPolicy = 'on_demand';
			mcps = [];
			tools = [];
			skills = [];
			oauthStatus = {};
			catalogLoaded = false;
		});
		return () => { unsubscribe(); ++ownerGeneration; mcpRequest?.abort(); clearRemoteSecrets(); };
	});
	$effect(() => {
		void [token, projectId, $auth.userId, $auth.domainId, canAssets];
		if (token && $authReady && !$projectSwitching) untrack(() => void load());
	});

	const inputCls =
		'w-full rounded-lg border border-[var(--color-line)] bg-[var(--color-surface-base)] px-3 py-2 text-sm text-[var(--color-ink-1)] focus:outline-none focus:border-[var(--color-accent)]';
	const badge = (active: boolean) =>
		`rounded px-1.5 py-0.5 text-xs ${active ? 'bg-[var(--color-state-success)]/15 text-[var(--color-state-success)]' : 'bg-[var(--color-line)] text-[var(--color-ink-2)]'}`;
</script>

{#if !isAdmin}
	<LumenPermissionNotice leaves={only === 'mcp'
		? ['lumen-tools_user', 'lumen-mcp_editor', 'lumen-resources_admin']
		: only
			? ['lumen-assets_editor', 'lumen-resources_admin']
			: ['lumen-mcp_editor', 'lumen-assets_editor', 'lumen-resources_admin']} />
{/if}

<!-- MCP 서버 -->
{#if !only || only === 'mcp'}
	{#if isAdmin}
		{@render mcpWorkspace()}
	{:else}
		<ChatMcpCatalogue servers={approvedServers} loading={loading && !catalogLoaded} {oauthStatus} onChanged={async () => { await load(); gallery?.refresh(); }}>
			{#snippet children(workspace)}{@render mcpWorkspace(workspace)}{/snippet}
		</ChatMcpCatalogue>
	{/if}
{/if}

{#snippet mcpWorkspace(workspace?: ApprovedMcpWorkspace)}
	<ChatMcpGallery bind:this={gallery} admin={isAdmin} onChanged={load} {remoteForm} onRemoteClose={clearRemoteSecrets}
		approved={workspace?.approval} cloud={workspace?.cloud} approvedActions={workspace?.remoteActions}
		adminRows={isAdmin ? mcps : []} approvedRows={approvedServers} {adminActions} {oauthStatus} inventoryLoading={loading && !catalogLoaded} />
{/snippet}

{#snippet remoteForm()}
	<h3 class="mb-1 text-sm font-semibold text-[var(--color-ink-1)]">{t('extensions.mcp.title')}</h3>
	<form class="extension-form" method="post" aria-label={t('extensions.mcp.title')} onsubmit={(event) => { event.preventDefault(); void addMcp(); }}>
		<p class="section-copy">{t('extensions.mcp.description', { scope: isAdmin ? t('extensions.scope.global') : t('extensions.scope.personal') })}</p>
		<div class="extension-fields">
			<Field label={t('extensions.mcp.namePlaceholder')} for={`${id}-mcp-name`}><TextInput id={`${id}-mcp-name`} placeholder={t('extensions.mcp.namePlaceholder')} bind:value={mName} required /></Field>
			<Field label="URL" for={`${id}-mcp-url`}><TextInput id={`${id}-mcp-url`} placeholder={t('extensions.mcp.urlPlaceholder')} bind:value={mUrl} required /></Field>
			<Field label={t('extensions.workspace.transport')} for={`${id}-mcp-transport`}>
				<SelectInput id={`${id}-mcp-transport`} bind:value={mTransport}><option value="http">{t('extensions.mcp.transport.http')}</option></SelectInput>
			</Field>
		</div>
		{#if isAdmin}
			<div class="mt-3">
				<label class="mb-1 block text-xs text-[var(--color-ink-2)]" for="mcp-auth-mode">{t('extensions.mcp.authPolicy')}</label>
				<select id="mcp-auth-mode" class={inputCls} bind:value={mAuthMode}>
					<option value="none">{t('extensions.mcp.auth.public')}</option>
					<option value="oauth">OAuth</option>
					<option value="admin">{t('extensions.mcp.auth.admin')}</option>
				</select>
			</div>
			<div class="mt-3">
				<label class="mb-1 block text-xs text-[var(--color-ink-2)]" for="mcp-load-policy">{t('extensions.loadPolicy.label')}</label>
				<select id="mcp-load-policy" class={inputCls} bind:value={mLoadPolicy}>
					<option value="on_demand">{t('extensions.loadPolicy.onDemand')}</option>
					<option value="preloaded">{t('extensions.loadPolicy.preloaded')}</option>
				</select>
			</div>
			{#if mAuthMode === 'oauth'}
				<div class="mt-3">
					<label class="mb-1 block text-xs text-[var(--color-ink-2)]" for="mcp-oauth-scopes">{t('extensions.mcp.oauthScopes')}</label>
					<input id="mcp-oauth-scopes" class={inputCls} placeholder="read write" bind:value={mOAuthScopes} />
				</div>
				<div class="mt-3 grid grid-cols-1 gap-3 md:grid-cols-2">
					<div>
						<label class="mb-1 block text-xs text-[var(--color-ink-2)]" for="mcp-oauth-client-id">{t('extensions.mcp.oauthClientId')}</label>
						<input id="mcp-oauth-client-id" class={inputCls} autocomplete="off" bind:value={mOAuthClientId} />
					</div>
					<div>
						<label class="mb-1 block text-xs text-[var(--color-ink-2)]" for="mcp-oauth-client-secret">{t('extensions.mcp.oauthClientSecret')}</label>
						<input id="mcp-oauth-client-secret" class={inputCls} type="password" autocomplete="new-password" bind:value={mOAuthClientSecret} />
					</div>
				</div>
			{:else if mAuthMode === 'admin'}
				<div class="mt-3">
					<label class="mb-1 block text-xs text-[var(--color-ink-2)]" for="mcp-headers"><RichText segments={t.rich('extensions.mcp.headers')} /></label>
					<textarea id="mcp-headers" class="{inputCls} font-mono" rows="2" placeholder={'Authorization: Bearer <token>\nX-Api-Key: <key>'} bind:value={mHeaders}></textarea>
				</div>
			{/if}
		{:else}
			<p class="mt-3 text-xs text-[var(--color-ink-2)]">{t('extensions.mcp.authHelp')}</p>
		{/if}
		<div class="mt-3 flex justify-end">
			<Button type="submit" disabled={addingMcp || !canMcp}>{#if addingMcp}<LoadingState variant="control" label={t('extensions.actions.adding')} />{:else}{t('extensions.mcp.add')}{/if}</Button>
		</div>
	</form>
{/snippet}

{#snippet adminActions(m: McpConnection)}
	{#if m.auth_mode === 'oauth'}
		<span title={t('extensions.mcp.oauthRequired')}><Pill tone="neutral" size="xs">OAuth</Pill></span>
	{/if}
	<div class="tool-actions">
		{@render loadPolicy('mcp-servers', m.id, m.name, mcps.find((server) => server.id === m.id)?.load_policy, canMcp)}
		<Button variant="outline" size="sm" disabled={!canMcp} onclick={() => toggle('mcp-servers', m.id, m.is_active)}>{m.is_active ? t('extensions.actions.deactivate') : t('extensions.actions.activate')}</Button>
		<Button variant="danger-outline" size="sm" disabled={!canDelete} onclick={() => removeItem('mcp-servers', m.id, m.name)}>{t('extensions.actions.delete')}</Button>
	</div>
{/snippet}

<!-- 커스텀 HTTP 툴 -->
{#if !only || only === 'tools'}
<section class="tools-workspace" aria-labelledby={`${id}-tools-title`}>
	<header>
		<h2 id={`${id}-tools-title`}>{t('extensions.tools.title')}</h2>
		<p class="section-copy">{t('extensions.tools.description', { scope: isAdmin ? t('extensions.scope.global') : t('extensions.scope.personal') })}</p>
	</header>
	<div class="tools-toolbar">
		<search><TextInput type="search" ariaLabel={t('extensions.workspace.searchTools')} placeholder={t('extensions.workspace.searchTools')} bind:value={toolQuery} /></search>
		<Button size="sm" disabled={!canAssets} onclick={() => toolDialog = true}>
			<svg aria-hidden="true" viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M8 3v10M3 8h10"/></svg>
			{t('extensions.workspace.addTool')}
		</Button>
	</div>
	{#if loading && catalogLoaded}<LoadingState variant="inline" label={t('extensions.tools.loading')} />{/if}
	{#if loading && !catalogLoaded}
		<LoadingState label={t('extensions.tools.loading')} />
	{:else if !filteredTools.length}
		<p class="tool-empty section-copy">{tools.length ? galleryT('emptySearch') : t('extensions.tools.empty')}</p>
	{:else}
		<ConnectionsTable label={t('extensions.tools.title')} rows={filteredTools} keyOf={(tool) => tool.id}
			columns={[
				{ key: 'status', label: galleryT('workspace.status'), cell: toolStatus },
				{ key: 'method', label: t('extensions.workspace.method'), cell: toolMethod },
				{ key: 'name', label: galleryT('workspace.name'), cell: toolName },
				{ key: 'description', label: galleryT('workspace.details'), cell: toolDetails },
				...(isAdmin ? [{ key: 'policy', label: t('extensions.loadPolicy.label'), cell: toolPolicy }] : [])
			]} name={toolName} actionsLabel={t('extensions.workspace.actions')} actions={toolActions} />
	{/if}
</section>

<FormModal bind:open={toolDialog} title={t('extensions.workspace.addTool')} submitting={addingTool}
	onClose={closeToolDialog} onSubmit={() => toolForm?.requestSubmit()} submitLabel={t('extensions.workspace.addTool')}>
	<form class="extension-form" aria-label={t('extensions.workspace.addTool')} method="post" bind:this={toolForm} onsubmit={(event) => { event.preventDefault(); void addTool(); }}>
		<Field label={t('extensions.tools.namePlaceholder')} for={`${id}-tool-name`}><TextInput id={`${id}-tool-name`} bind:value={tName} required /></Field>
		<Field label={t('extensions.tools.descriptionPlaceholder')} for={`${id}-tool-description`}><TextInput id={`${id}-tool-description`} bind:value={tDesc} /></Field>
		<Field label={t('extensions.workspace.method')} for={`${id}-tool-method`}>
			<SelectInput id={`${id}-tool-method`} bind:value={tMethod}><option value="GET">GET</option><option value="POST">POST</option></SelectInput>
		</Field>
		<Field label="URL" for={`${id}-tool-url`}><TextInput id={`${id}-tool-url`} bind:value={tUrl} required /></Field>
		{#if isAdmin}
			<Field label={t('extensions.loadPolicy.label')} for={`${id}-tool-policy`}>
				<SelectInput id={`${id}-tool-policy`} bind:value={tLoadPolicy}>
					<option value="on_demand">{t('extensions.loadPolicy.onDemand')}</option>
					<option value="preloaded">{t('extensions.loadPolicy.preloaded')}</option>
				</SelectInput>
			</Field>
		{/if}
		<button type="submit" hidden>{t('extensions.workspace.addTool')}</button>
	</form>
</FormModal>
{/if}

{#snippet toolStatus(tool: CustomTool)}
	<ConnectionStatus state={tool.is_active ? 'active' : 'inactive'} label={t(tool.is_active ? 'extensions.state.active' : 'extensions.state.inactive')} />
{/snippet}
{#snippet toolMethod(tool: CustomTool)}<Pill tone="neutral" size="xs">{tool.method}</Pill>{/snippet}
{#snippet toolName(tool: CustomTool)}<ConnectionName name={tool.name} />{/snippet}
{#snippet toolDetails(tool: CustomTool)}
	<div class="tool-details">
		{#if tool.description}<span>{tool.description}</span>{/if}
		<span>{tool.url}</span>
	</div>
{/snippet}
{#snippet toolPolicy(tool: CustomTool)}{@render loadPolicy('custom-tools', tool.id, tool.name, tool.load_policy, canAssets)}{/snippet}
{#snippet toolActions(tool: CustomTool)}
	<div class="tool-actions">
		<Button variant="outline" size="sm" disabled={!canAssets} onclick={() => toggle('custom-tools', tool.id, tool.is_active)}>{tool.is_active ? t('extensions.actions.deactivate') : t('extensions.actions.activate')}</Button>
		<Button variant="danger-outline" size="sm" disabled={!canDelete} onclick={() => removeItem('custom-tools', tool.id, tool.name)}>{t('extensions.actions.delete')}</Button>
	</div>
{/snippet}
{#snippet loadPolicy(kind: 'mcp-servers' | 'custom-tools', targetId: number, name: string, policy: 'preloaded' | 'on_demand' | undefined, allowed: boolean)}
	<SelectInput ariaLabel={t('extensions.loadPolicy.ariaLabel', { name })} value={policy ?? 'on_demand'} disabled={!allowed}
		onchange={(event) => void setLoadPolicy(kind, targetId, (event.currentTarget as HTMLSelectElement).value as 'preloaded' | 'on_demand')}>
		<option value="on_demand">{t('extensions.loadPolicy.onDemandShort')}</option>
		<option value="preloaded">{t('extensions.loadPolicy.preloadedShort')}</option>
	</SelectInput>
{/snippet}

<!-- 스킬 (선택 시 채팅 지침으로 주입) -->
{#if !only || only === 'skills'}
<section class="mt-8">
	<h2 class="mb-1 text-sm font-semibold text-[var(--color-ink-1)]">{t('extensions.skills.title')}</h2>
	<p class="mb-3 text-xs text-[var(--color-ink-2)]">{t('extensions.skills.description', { scope: isAdmin ? t('extensions.scope.global') : t('extensions.scope.personal') })}</p>
	<div class="mb-4 border-b border-[var(--color-line)] pb-4">
		<div class="grid grid-cols-1 gap-3 md:grid-cols-2">
			<input class={inputCls} placeholder={t('extensions.skills.namePlaceholder')} bind:value={sName} />
			<input class={inputCls} placeholder={t('extensions.skills.descriptionPlaceholder')} bind:value={sDesc} />
		</div>
		<div class="mt-3">
			<label class="mb-1 block text-xs text-[var(--color-ink-2)]" for="skill-instructions">
				{t('extensions.skills.instructionsLabel')}
			</label>
			<textarea
				id="skill-instructions"
				class={inputCls}
				rows="5"
				placeholder={t('extensions.skills.instructionsPlaceholder')}
				bind:value={sInstructions}
			></textarea>
		</div>
		<div class="mt-3 flex justify-end">
			<Button onclick={addSkill} disabled={addingSkill || !canAssets}>{#if addingSkill}<LoadingState variant="control" label={t('extensions.actions.adding')} />{:else}{t('extensions.skills.add')}{/if}</Button>
		</div>
	</div>
	{#if loading && catalogLoaded}<LoadingState variant="inline" label={t('extensions.skills.loading')} />{/if}
	{#if loading && !catalogLoaded}
		<LoadingState label={t('extensions.skills.loading')} />
	{:else if skills.length === 0}
		<p class="px-1 text-sm text-[var(--color-ink-2)]">{t('extensions.skills.empty')}</p>
	{:else}
		<div class="divide-y divide-[var(--color-line)]">
			{#each skills as s (s.id)}
				<div class="flex flex-wrap items-center justify-between gap-3 py-3">
					<div class="min-w-0">
						<div class="flex items-center gap-2">
							<span class="truncate text-sm font-medium text-[var(--color-ink-1)]">{s.name}</span>
							<span class={badge(s.is_active)}>{s.is_active ? t('extensions.state.active') : t('extensions.state.inactive')}</span>
						</div>
						{#if s.description}<div class="mt-0.5 truncate text-xs text-[var(--color-ink-2)]">{s.description}</div>{/if}
					</div>
					<div class="flex shrink-0 items-center gap-3 text-xs">
						<button disabled={!canAssets} class="text-[var(--color-ink-2)] hover:text-[var(--color-ink-0)]" onclick={() => toggle('skills', s.id, s.is_active)}>{s.is_active ? t('extensions.actions.deactivate') : t('extensions.actions.activate')}</button>
						<button disabled={!canDelete} class="text-[var(--color-state-danger)] hover:opacity-80" onclick={() => removeItem('skills', s.id, s.name)}>{t('extensions.actions.delete')}</button>
					</div>
				</div>
			{/each}
		</div>
	{/if}
</section>
{/if}

<style>
	.tools-workspace { display: grid; gap: 1rem; min-width: 0; }
	.tools-workspace h2 { margin: 0; font-size: 1.25rem; font-weight: 600; color: var(--color-ink-0); }
	.section-copy { margin: 0.25rem 0 0; font-size: var(--type-support); color: var(--color-ink-2); }
	.tools-toolbar, .tool-actions { display: flex; flex-wrap: wrap; align-items: center; justify-content: flex-end; gap: 0.5rem; }
	.tools-toolbar search { flex: 1 1 12rem; }
	.tool-actions :global(.select-input) { inline-size: auto; max-inline-size: 100%; }
	.tool-details { display: grid; color: var(--color-ink-2); font-size: var(--type-support); overflow-wrap: anywhere; }
	.tool-empty { border-block: 1px solid var(--color-line); padding-block: 0.875rem; }
	.extension-form { display: grid; gap: 0.75rem; }
	.extension-fields { display: grid; gap: 0.75rem; grid-template-columns: repeat(auto-fit, minmax(min(100%, 12rem), 1fr)); }
</style>
