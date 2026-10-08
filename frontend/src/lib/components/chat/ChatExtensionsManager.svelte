<script lang="ts">
	import { auth } from '$lib/stores/auth';
	import { api, ApiError } from '$lib/api/client';
	import { serviceCapabilities } from '$lib/stores/servicePermissions';
	import LumenPermissionNotice from './LumenPermissionNotice.svelte';
	import { confirmDialog } from '$lib/stores/confirm.svelte';
	import { toast } from '$lib/stores/toast';
	import Button from '$lib/components/ui/Button.svelte';
	import Pill from '$lib/components/ui/Pill.svelte';
	import { t } from '$lib/i18n/ns/chat-settings';
	import RichText from '$lib/i18n/RichText.svelte';

	// base: '/api/v1/chat/admin' (관리자 global) 또는 '/api/v1/chat' (사용자 본인)
	// only: 특정 섹션만 렌더('mcp' | 'tools' | 'skills'). 미지정 시 전부.
	let { base, only }: { base: string; only?: 'mcp' | 'tools' | 'skills' } = $props();

	interface McpServer {
		id: number;
		scope: string;
		name: string;
		transport: string;
		url: string | null;
		has_headers?: boolean;
		auth_mode?: 'none' | 'oauth' | 'admin';
		oauth_scopes?: string[];
		has_oauth_client?: boolean;
		has_oauth_client_secret?: boolean;
		load_policy?: 'preloaded' | 'on_demand';
		is_active: boolean;
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
	let connectingOAuthId = $state<number | null>(null);

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



	async function connectOAuth(m: McpServer) {
		if (!canMcp) return;
		connectingOAuthId = m.id;
		try {
			const result = await api.post<{ authorization_url: string }>(
				`${base}/mcp-servers/${m.id}/oauth/start`,
				{},
				token,
				projectId
			);
			if (!result.authorization_url) throw new Error('missing authorization URL');
			window.location.assign(result.authorization_url);
		} catch (e) {
			toast.error(e instanceof ApiError ? e.message : t('extensions.oauth.startFailed'));
		} finally {
			connectingOAuthId = null;
		}
	}

	async function disconnectOAuth(m: McpServer) {
		if (!(await confirmDialog(t('extensions.oauth.disconnectConfirm', { name: m.name })))) return;
		if (!canDelete) return;
		try {
			await api.delete(`${base}/mcp-servers/${m.id}/oauth`, token, projectId);
			await load();
			toast.success(t('extensions.oauth.disconnected'));
		} catch (e) {
			toast.error(e instanceof ApiError ? e.message : t('extensions.oauth.disconnectFailed'));
		}
	}
	let tName = $state('');
	let tDesc = $state('');
	let tMethod = $state('GET');
	let tUrl = $state('');
	let tLoadPolicy = $state<'preloaded' | 'on_demand'>('on_demand');
	let addingTool = $state(false);

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
		try {
			const [ms, ts, ss] = await Promise.all([
				api.get<McpServer[]>(`${base}/mcp-servers`, token, projectId),
				api.get<CustomTool[]>(`${base}/custom-tools`, token, projectId),
				api.get<Skill[]>(`${base}/skills${includePrivate ? '?include_private=true' : ''}`, token, projectId)
			]);
			if (requestToken !== token || requestProject !== projectId || (includePrivate && !canAssets)) return;
			mcps = ms;
			tools = ts;
			skills = ss;
			oauthStatus = isAdmin
				? {}
				: Object.fromEntries(
						await Promise.all(
							ms
								.filter((mcp) => mcp.auth_mode === 'oauth')
								.map(async (mcp) => [
									mcp.id,
									await api.get<McpOAuthStatus>(`${base}/mcp-servers/${mcp.id}/oauth`, token, projectId)
								] as const)
						)
					);
		} catch {
			toast.error(t('extensions.loadFailed'));
		} finally {
			loading = false;
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
		try {
			const headers = parseHeaders(mHeaders);
			const oauthScopes = mOAuthScopes.split(/[\s,]+/).filter(Boolean);
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
								...(mOAuthClientSecret ? { oauth_client_secret: mOAuthClientSecret } : {}),
								load_policy: mLoadPolicy
							}
						: {})
				},
				token,
				projectId
			);
			mName = '';
			mUrl = '';
			mHeaders = '';
			mAuthMode = 'none';
			mOAuthScopes = '';
			mOAuthClientId = '';
			mOAuthClientSecret = '';
			mLoadPolicy = 'on_demand';
			await load();
			toast.success(t('extensions.mcp.added'));
		} catch (e) {
			toast.error(e instanceof ApiError ? e.message : t('extensions.addFailed'));
		} finally {
			addingMcp = false;
		}
	}

	async function addTool() {
		if (!canAssets) return;
		if (!tName.trim() || !tUrl.trim()) {
			toast.error(t('extensions.tools.nameUrlRequired'));
			return;
		}
		addingTool = true;
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
			tName = '';
			tDesc = '';
			tUrl = '';
			await load();
			tLoadPolicy = 'on_demand';
			toast.success(t('extensions.tools.added'));
		} catch (e) {
			toast.error(e instanceof ApiError ? e.message : t('extensions.addFailed'));
		} finally {
			addingTool = false;
		}
	}

	async function removeItem(
		kind: 'mcp-servers' | 'custom-tools' | 'skills',
		id: number,
		name: string
	) {
		const ok = await confirmDialog(
			t('extensions.deleteConfirm', { kind, name }),
			{ confirmLabel: t('extensions.actions.delete') }
		);
		if (!ok) return;
		if (!canDelete) return;
		try {
			await api.delete(`${base}/${kind}/${id}`, token, projectId);
			await load();
		} catch {
			toast.error(t('extensions.deleteFailed', { kind, name }));
		}
	}

	async function toggle(kind: 'mcp-servers' | 'custom-tools' | 'skills', id: number, isActive: boolean) {
		if (!(kind === 'mcp-servers' ? canMcp : canAssets)) return;
		try {
			await api.patch(`${base}/${kind}/${id}`, { is_active: !isActive }, token, projectId);
			await load();
		} catch {
			toast.error(t('extensions.changeFailed'));
		}
	}

	async function setLoadPolicy(
		kind: 'mcp-servers' | 'custom-tools',
		id: number,
		loadPolicy: 'preloaded' | 'on_demand'
	) {
		if (!(kind === 'mcp-servers' ? canMcp : canAssets)) return;
		try {
			await api.patch(`${base}/${kind}/${id}`, { load_policy: loadPolicy }, token, projectId);
			await load();
		} catch {
			toast.error(t('extensions.loadPolicy.changeFailed'));
		}
	}

	$effect(() => {
		if (token) void load();
	});

	const inputCls =
		'w-full rounded-lg border border-[var(--color-line)] bg-[var(--color-surface-base)] px-3 py-2 text-sm text-[var(--color-ink-1)] focus:outline-none focus:border-[var(--color-accent)]';
	const cardCls = 'rounded-lg border border-[var(--color-line)] bg-[var(--color-surface-raised)]';
	const badge = (active: boolean) =>
		`rounded px-1.5 py-0.5 text-xs ${active ? 'bg-[var(--color-state-success)]/15 text-[var(--color-state-success)]' : 'bg-[var(--color-line)] text-[var(--color-ink-3)]'}`;
</script>

<!-- MCP 서버 -->
{#if !only || only === 'mcp'}
<section class="mb-8">
	<h3 class="mb-1 text-sm font-semibold text-[var(--color-ink-1)]">{t('extensions.mcp.title')}</h3>
	{#if !isAdmin}<LumenPermissionNotice leaf="lumen-mcp_editor" /><LumenPermissionNotice leaf="lumen-resources_admin" />{/if}
	<p class="mb-3 text-xs text-[var(--color-ink-3)]">{t('extensions.mcp.description', { scope: isAdmin ? t('extensions.scope.global') : t('extensions.scope.personal') })}</p>
	<div class="{cardCls} mb-4 p-5">
		<div class="grid grid-cols-1 gap-3 md:grid-cols-3">
			<input class={inputCls} placeholder={t('extensions.mcp.namePlaceholder')} bind:value={mName} />
			<select class={inputCls} bind:value={mTransport}>
				<option value="http">{t('extensions.mcp.transport.http')}</option>
			</select>
			<input class={inputCls} placeholder={t('extensions.mcp.urlPlaceholder')} bind:value={mUrl} />
		</div>
		{#if isAdmin}
			<div class="mt-3">
				<label class="mb-1 block text-xs text-[var(--color-ink-3)]" for="mcp-auth-mode">{t('extensions.mcp.authPolicy')}</label>
				<select id="mcp-auth-mode" class={inputCls} bind:value={mAuthMode}>
					<option value="none">{t('extensions.mcp.auth.public')}</option>
					<option value="oauth">OAuth</option>
					<option value="admin">{t('extensions.mcp.auth.admin')}</option>
				</select>
			</div>
			<div class="mt-3">
				<label class="mb-1 block text-xs text-[var(--color-ink-3)]" for="mcp-load-policy">{t('extensions.loadPolicy.label')}</label>
				<select id="mcp-load-policy" class={inputCls} bind:value={mLoadPolicy}>
					<option value="on_demand">{t('extensions.loadPolicy.onDemand')}</option>
					<option value="preloaded">{t('extensions.loadPolicy.preloaded')}</option>
				</select>
			</div>
			{#if mAuthMode === 'oauth'}
				<div class="mt-3">
					<label class="mb-1 block text-xs text-[var(--color-ink-3)]" for="mcp-oauth-scopes">{t('extensions.mcp.oauthScopes')}</label>
					<input id="mcp-oauth-scopes" class={inputCls} placeholder="read write" bind:value={mOAuthScopes} />
				</div>
				<div class="mt-3 grid grid-cols-1 gap-3 md:grid-cols-2">
					<div>
						<label class="mb-1 block text-xs text-[var(--color-ink-3)]" for="mcp-oauth-client-id">{t('extensions.mcp.oauthClientId')}</label>
						<input id="mcp-oauth-client-id" class={inputCls} autocomplete="off" bind:value={mOAuthClientId} />
					</div>
					<div>
						<label class="mb-1 block text-xs text-[var(--color-ink-3)]" for="mcp-oauth-client-secret">{t('extensions.mcp.oauthClientSecret')}</label>
						<input id="mcp-oauth-client-secret" class={inputCls} type="password" autocomplete="new-password" bind:value={mOAuthClientSecret} />
					</div>
				</div>
			{:else if mAuthMode === 'admin'}
				<div class="mt-3">
					<label class="mb-1 block text-xs text-[var(--color-ink-3)]" for="mcp-headers"><RichText segments={t.rich('extensions.mcp.headers')} /></label>
					<textarea id="mcp-headers" class="{inputCls} font-mono" rows="2" placeholder={'Authorization: Bearer <token>\nX-Api-Key: <key>'} bind:value={mHeaders}></textarea>
				</div>
			{/if}
		{:else}
			<p class="mt-3 text-xs text-[var(--color-ink-3)]">{t('extensions.mcp.authHelp')}</p>
		{/if}
		<div class="mt-3 flex justify-end">
			<Button onclick={addMcp} disabled={addingMcp || !canMcp}>{addingMcp ? t('extensions.actions.adding') : t('extensions.mcp.add')}</Button>
		</div>
	</div>
	{#if loading}
		<div class="motion-skeleton rounded-lg border border-line h-16" role="status" aria-label={t('extensions.mcp.loading')}>
			<span class="sr-only">{t('extensions.mcp.loading')}</span>
		</div>
	{:else if mcps.length === 0}
		<p class="px-1 text-sm text-[var(--color-ink-3)]">{t('extensions.mcp.empty')}</p>
	{:else}
		<div class="space-y-2">
			{#each mcps as m (m.id)}
				<div class={cardCls}>
					<div class="flex items-center justify-between gap-3 px-4 py-3">
						<div class="min-w-0">
							<div class="flex items-center gap-2">
								<span class="truncate text-sm font-medium text-[var(--color-ink-1)]">{m.name}</span>
								<span class={badge(m.is_active)}>{m.is_active ? t('extensions.state.active') : t('extensions.state.inactive')}</span>
								<span class="text-xs text-[var(--color-ink-3)]">{m.transport}</span>
								{#if m.has_headers}<span class="text-xs text-[var(--color-ink-3)]" title={t('extensions.mcp.sharedHeaders')}>🔒</span>{/if}
								{#if m.auth_mode === 'oauth'}
									<span title={t('extensions.mcp.oauthRequired')}><Pill tone="neutral" size="xs">OAuth</Pill></span>
								{/if}
							</div>
							{#if m.url}<div class="mt-0.5 truncate text-xs text-[var(--color-ink-3)]">{m.url}</div>{/if}
						</div>
						<div class="flex shrink-0 items-center gap-3 text-xs">
							{#if !isAdmin && m.auth_mode === 'oauth'}
								{#if oauthStatus[m.id]?.connected}
									<button disabled={!canDelete} class="text-[var(--color-state-success)] hover:opacity-80" onclick={() => disconnectOAuth(m)}>{t('extensions.oauth.connected')}</button>
								{:else}
									<button class="text-[var(--color-accent)] hover:opacity-80" disabled={connectingOAuthId === m.id || !canMcp} onclick={() => connectOAuth(m)}>
										{#if connectingOAuthId === m.id}
											{t('extensions.oauth.preparing')}
										{:else}
											<RichText segments={t.rich('extensions.oauth.connect', { name: m.name })} />
										{/if}
									</button>
								{/if}
							{/if}
							{#if isAdmin}
								<select
									class="rounded border border-[var(--color-line)] bg-[var(--color-surface-sunken)] px-1 py-0.5 text-xs text-[var(--color-ink-2)]"
									aria-label={t('extensions.loadPolicy.ariaLabel', { name: m.name })}
									value={m.load_policy ?? 'on_demand'}
									onchange={(event) =>
										void setLoadPolicy(
											'mcp-servers',
											m.id,
											(event.currentTarget as HTMLSelectElement).value as 'preloaded' | 'on_demand'
										)}
								>
									<option value="on_demand">{t('extensions.loadPolicy.onDemandShort')}</option>
									<option value="preloaded">{t('extensions.loadPolicy.preloadedShort')}</option>
								</select>
							{/if}
							<button disabled={!canMcp} class="text-[var(--color-ink-2)] hover:text-[var(--color-ink-0)]" onclick={() => toggle('mcp-servers', m.id, m.is_active)}>{m.is_active ? t('extensions.actions.deactivate') : t('extensions.actions.activate')}</button>
							<button disabled={!canDelete} class="text-[var(--color-state-danger)] hover:opacity-80" onclick={() => removeItem('mcp-servers', m.id, m.name)}>{t('extensions.actions.delete')}</button>
						</div>
					</div>
				</div>
			{/each}
		</div>
	{/if}
</section>
{/if}

<!-- 커스텀 HTTP 툴 -->
{#if !only || only === 'tools'}
<section>
	<h3 class="mb-1 text-sm font-semibold text-[var(--color-ink-1)]">{t('extensions.tools.title')}</h3>
	{#if !isAdmin}<LumenPermissionNotice leaf="lumen-assets_editor" /><LumenPermissionNotice leaf="lumen-resources_admin" />{/if}
	<p class="mb-3 text-xs text-[var(--color-ink-3)]">{t('extensions.tools.description', { scope: isAdmin ? t('extensions.scope.global') : t('extensions.scope.personal') })}</p>
	<div class="{cardCls} mb-4 p-5">
		<div class="grid grid-cols-1 gap-3 md:grid-cols-2">
			<input class={inputCls} placeholder={t('extensions.tools.namePlaceholder')} bind:value={tName} />
			<input class={inputCls} placeholder={t('extensions.tools.descriptionPlaceholder')} bind:value={tDesc} />
			<select class={inputCls} bind:value={tMethod}>
				<option value="GET">GET</option>
				<option value="POST">POST</option>
			</select>
			<input class={inputCls} placeholder="URL" bind:value={tUrl} />
		</div>
		{#if isAdmin}
			<div class="mt-3">
				<label class="mb-1 block text-xs text-[var(--color-ink-3)]" for="tool-load-policy">{t('extensions.loadPolicy.label')}</label>
				<select id="tool-load-policy" class={inputCls} bind:value={tLoadPolicy}>
					<option value="on_demand">{t('extensions.loadPolicy.onDemand')}</option>
					<option value="preloaded">{t('extensions.loadPolicy.preloaded')}</option>
				</select>
			</div>
		{/if}
		<div class="mt-3 flex justify-end">
			<Button onclick={addTool} disabled={addingTool || !canAssets}>{addingTool ? t('extensions.actions.adding') : t('extensions.tools.add')}</Button>
		</div>
	</div>
	{#if loading}
		<div class="motion-skeleton rounded-lg border border-line h-16" role="status" aria-label={t('extensions.tools.loading')}>
			<span class="sr-only">{t('extensions.tools.loading')}</span>
		</div>
	{:else if tools.length === 0}
		<p class="px-1 text-sm text-[var(--color-ink-3)]">{t('extensions.tools.empty')}</p>
	{:else}
		<div class="space-y-2">
			{#each tools as tool (tool.id)}
				<div class="{cardCls} flex items-center justify-between gap-3 px-4 py-3">
					<div class="min-w-0">
						<div class="flex items-center gap-2">
							<span class="truncate text-sm font-medium text-[var(--color-ink-1)]">{tool.name}</span>
							<span class={badge(tool.is_active)}>{tool.is_active ? t('extensions.state.active') : t('extensions.state.inactive')}</span>
							<span class="text-xs text-[var(--color-ink-3)]">{tool.method}</span>
						</div>
						<div class="mt-0.5 truncate text-xs text-[var(--color-ink-3)]">{tool.description} · {tool.url}</div>
					</div>
					<div class="flex shrink-0 items-center gap-3 text-xs">
						{#if isAdmin}
							<select
								class="rounded border border-[var(--color-line)] bg-[var(--color-surface-sunken)] px-1 py-0.5 text-xs text-[var(--color-ink-2)]"
								aria-label={t('extensions.loadPolicy.ariaLabel', { name: tool.name })}
								value={tool.load_policy ?? 'on_demand'}
								onchange={(event) =>
									void setLoadPolicy(
										'custom-tools',
										tool.id,
										(event.currentTarget as HTMLSelectElement).value as 'preloaded' | 'on_demand'
									)}
							>
								<option value="on_demand">{t('extensions.loadPolicy.onDemandShort')}</option>
								<option value="preloaded">{t('extensions.loadPolicy.preloadedShort')}</option>
							</select>
						{/if}
						<button disabled={!canAssets} class="text-[var(--color-ink-2)] hover:text-[var(--color-ink-0)]" onclick={() => toggle('custom-tools', tool.id, tool.is_active)}>{tool.is_active ? t('extensions.actions.deactivate') : t('extensions.actions.activate')}</button>
						<button disabled={!canDelete} class="text-[var(--color-state-danger)] hover:opacity-80" onclick={() => removeItem('custom-tools', tool.id, tool.name)}>{t('extensions.actions.delete')}</button>
					</div>
				</div>
			{/each}
		</div>
	{/if}
</section>
{/if}

<!-- 스킬 (선택 시 채팅 지침으로 주입) -->
{#if !only || only === 'skills'}
<section class="mt-8">
	<h3 class="mb-1 text-sm font-semibold text-[var(--color-ink-1)]">{t('extensions.skills.title')}</h3>
	{#if !isAdmin}<LumenPermissionNotice leaf="lumen-assets_editor" /><LumenPermissionNotice leaf="lumen-resources_admin" />{/if}
	<p class="mb-3 text-xs text-[var(--color-ink-3)]">{t('extensions.skills.description', { scope: isAdmin ? t('extensions.scope.global') : t('extensions.scope.personal') })}</p>
	<div class="{cardCls} mb-4 p-5">
		<div class="grid grid-cols-1 gap-3 md:grid-cols-2">
			<input class={inputCls} placeholder={t('extensions.skills.namePlaceholder')} bind:value={sName} />
			<input class={inputCls} placeholder={t('extensions.skills.descriptionPlaceholder')} bind:value={sDesc} />
		</div>
		<div class="mt-3">
			<label class="mb-1 block text-xs text-[var(--color-ink-3)]" for="skill-instructions">
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
			<Button onclick={addSkill} disabled={addingSkill || !canAssets}>{addingSkill ? t('extensions.actions.adding') : t('extensions.skills.add')}</Button>
		</div>
	</div>
	{#if loading}
		<div class="motion-skeleton rounded-lg border border-line h-16" role="status" aria-label={t('extensions.skills.loading')}>
			<span class="sr-only">{t('extensions.skills.loading')}</span>
		</div>
	{:else if skills.length === 0}
		<p class="px-1 text-sm text-[var(--color-ink-3)]">{t('extensions.skills.empty')}</p>
	{:else}
		<div class="space-y-2">
			{#each skills as s (s.id)}
				<div class="{cardCls} flex items-center justify-between gap-3 px-4 py-3">
					<div class="min-w-0">
						<div class="flex items-center gap-2">
							<span class="truncate text-sm font-medium text-[var(--color-ink-1)]">{s.name}</span>
							<span class={badge(s.is_active)}>{s.is_active ? t('extensions.state.active') : t('extensions.state.inactive')}</span>
						</div>
						{#if s.description}<div class="mt-0.5 truncate text-xs text-[var(--color-ink-3)]">{s.description}</div>{/if}
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
