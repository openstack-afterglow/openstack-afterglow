<script lang="ts">
	import { onMount, tick } from 'svelte';
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
	import Pagination from '$lib/components/ui/Pagination.svelte';
	import { t } from '$lib/i18n/ns/mcp-gallery';

	import { t as settingsT } from '$lib/i18n/ns/chat-settings';
	let { admin = false, onChanged = async () => {} }: { admin?: boolean; onChanged?: () => Promise<void> } = $props();
	type Owner = { key: string; token: string; userId: string; projectId: string };
	type Editor = { template?: McpTemplate; row?: McpConnection; scope: 'user' | 'domain' | 'global' };
	let owner = $state.raw<Owner | null>(null);
	let entries = $state<McpTemplate[]>([]);
	let featured = $state<McpTemplate[]>([]);
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
	let offset = $state(0);
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
	const templates = new Map<string, McpTemplate>();
	let readController: AbortController | null = null;
	const mutations = new Set<AbortController>();
	const limit = 12;
	const canWrite = $derived(admin ? $auth.isSystemAdmin === true : $serviceCapabilities('lumen-mcp_editor'));
	const canDelete = $derived(admin ? $auth.isSystemAdmin === true : $serviceCapabilities('lumen-resources_admin'));
	const lists = $derived([
		{ scope: 'user', title: t('personal') },
		{ scope: 'domain', title: t('organization') },
		{ scope: 'global', title: t('global') }
	]);

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
		entries = []; featured = []; adminEntries = []; connections = [];
		domainId = null; canManage = false; organizationError = false; error = ''; rowErrors = {}; busy = {};
		loading = false; total = 0; offset = 0; nextOffset = null; query = ''; appliedQuery = '';
		installSummary = ''; clearDraft();
	}
	onMount(() => {
		const unsubscribe = derived([auth, authReady, projectSwitching], ([actor, ready, switching]) => ({ actor, ready, switching })).subscribe(({ actor, ready, switching }) => {
			const key = ready && !switching && actor.token && actor.userId && actor.projectId
				? JSON.stringify([actor.sessionId, actor.userId, actor.identityDomainId, actor.domainId, actor.projectId, admin, actor.isSystemAdmin]) : null;
			if (owner?.key === key) { if (actor.token) owner.token = actor.token; return; }
			invalidate();
			owner = key ? { key, token: actor.token!, userId: actor.userId!, projectId: actor.projectId! } : null;
			if (owner) void load(owner, 0, '');
		});
		return () => { unsubscribe(); invalidate(); owner = null; };
	});

	async function load(scope: Owner, start = offset, search = appliedQuery) {
		const ticket = ++generation;
		readController?.abort();
		const controller = new AbortController(); readController = controller;
		const options = { refresh: true, signal: controller.signal };
		loading = true; error = '';
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
				showAdminPage(start, search);
			} else {
				const params = new URLSearchParams({ offset: String(start), limit: String(limit), ...(search ? { q: search } : {}) });
				const [page, defaults, rows] = await Promise.all([
					api.get<McpSettingsPage>(`/api/v1/chat/mcp-settings?${params}`, scope.token, scope.projectId, options),
					api.get<McpSettingsPage>('/api/v1/chat/mcp-settings?featured=true&offset=0&limit=100', scope.token, scope.projectId, options),
					api.get<McpConnection[]>('/api/v1/chat/mcp-servers', scope.token, scope.projectId, options)
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
				entries = page.entries; featured = defaults.entries; total = page.total; nextOffset = page.next_offset;
				domainId = page.domain_id; organizationError = organizationUnavailable;
				canManage = !organizationUnavailable && page.can_manage_domain === true;
				if (!canManage && editor?.scope === 'domain') clearDraft();
				for (const entry of [...page.entries, ...defaults.entries]) templates.set(entry.id, entry);
				connections = [...new Map([...rows, ...organization, ...page.custom_connections]
					.filter((row) => (!organizationUnavailable || row.scope !== 'domain') && visibleMcpConnection(row, scope.userId, scope.projectId, page.domain_id) && (row.scope !== 'global' || !!row.template_key))
					.map((row) => [row.id, row])).values()];
			}
			offset = start; appliedQuery = search;
		} catch {
			if (owner === scope && ticket === generation) { error = t('loadFailed'); canManage = false; entries = []; featured = []; connections = []; clearDraft(); }
		} finally { if (owner === scope && ticket === generation) loading = false; }
	}
	function showAdminPage(start: number, search: string) {
		const needle = search.toLocaleLowerCase();
		const rows = adminEntries.filter((entry) => [entry.name, entry.registry_name, entry.description].some((value) => value?.toLocaleLowerCase().includes(needle)));
		total = rows.length; entries = rows.slice(start, start + limit); nextOffset = start + limit < total ? start + limit : null;
	}
	function browse(start: number, search = appliedQuery) { if (owner) void load(owner, start, search); }
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
			const path = personal ? rowPath(row) : row.scope === 'domain' ? `${rowPath(row)}/activation` : `/api/v1/chat/mcp-servers/${row.id}/activation`;
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

<section class="gallery" aria-labelledby="mcp-gallery-title">
	<header class="toolbar">
		<div><h3 id="mcp-gallery-title">{t('title')}</h3><p>{t('description')}</p></div>
		<div class="actions"><Button variant="secondary" size="sm" disabled={loading || !owner} onclick={() => owner && load(owner)}>{t('refresh')}</Button>{#if admin}<Button size="sm" disabled={!canWrite || busy.featured} onclick={installFeatured}>{t('installFeatured')}</Button>{/if}</div>
	</header>
	{#if error}<Alert tone="danger">{error}</Alert>{/if}
	{#if rowErrors.featured}<Alert tone="danger">{rowErrors.featured}</Alert>{/if}
	{#if installSummary}<Alert tone="info">{installSummary}</Alert>{/if}
	{#if loading}<LoadingState variant="inline" label={t('loading')} />{/if}
	{#if !error && featured.length}
		<h4>{t('featured')}</h4>
		<div class="featured-grid">{#each featured as entry (entry.id)}{@render templateCard(entry)}{/each}</div>
	{/if}
	{#if !admin && !error && owner}
		{#if domainId && !organizationError}<div class="scope-note"><span>{t('domain')}: <code>{domainId}</code></span><span>{canManage ? t('managerHelp') : t('memberHelp')}</span></div>{/if}
		{#each lists as list}
			<section class="connections" aria-label={list.title}>
				<h4>{list.title}</h4>
				{#if list.scope === 'domain' && organizationError}<Alert tone="warning" flat>{t('organizationUnavailable')}</Alert>{/if}
				{#each connections.filter((row) => row.scope === list.scope) as row (row.id)}
					{@const state = mcpConnectionState(row)}
					<div class="connection-row">
						<div class="row-copy"><strong>{row.name}</strong>{#if row.connection_label}<p>{row.connection_label}</p>{/if}<div class="metadata"><Pill tone={state === 'active' ? 'success' : state === 'stale' || state === 'needsAuth' ? 'warning' : 'neutral'} size="xs">{t(state)}</Pill><span>{t('revision', { version: row.config_version })}</span>{#if row.has_headers}<span>{t('headersSaved')}</span>{/if}</div>{#if row.url}<p class="endpoint">{row.url}</p>{/if}{#if row.catalog_error}<p>{t('catalogError')}</p>{/if}</div>
						{#if row.tools?.length}<details class="row-error"><summary>{t('tools', { count: row.tool_count ?? row.tools.length })}</summary><p>{t('schemaHelp')}</p>{#each row.tools as tool}<p><strong>{tool.name}</strong>{tool.description ? ` — ${tool.description}` : ''}</p>{/each}</details>{/if}
						<div class="actions">
							<Button variant="secondary" size="sm" disabled={!!busy[row.id] || !canWrite || (row.scope !== 'user' && !row.server_is_active) || !row.config_version} onclick={() => activate(row)}>{(row.scope === 'user' ? row.server_is_active : row.is_active) ? t('deactivate') : t('activate')}</Button>
							{#if row.auth_mode === 'oauth' && (row.scope !== 'domain' || editable(row))}<Button variant="outline" size="sm" disabled={!!busy[row.id] || !canWrite} onclick={() => oauth(row)}>{row.auth_connected ? t('reconnect') : t('connectOAuth')}</Button>{#if row.auth_connected}<Button variant="subtle" size="sm" disabled={!!busy[row.id] || !canDelete} onclick={() => revokeTarget = row}>{t('revokeOAuth')}</Button>{/if}{/if}
							{#if editable(row)}{#if row.scope === 'domain' || (row.template_key && row.auth_mode === 'admin')}<Button variant="subtle" size="sm" disabled={!!busy[row.id] || !canWrite} onclick={() => openEditor(undefined, row, row.scope)}>{t('edit')}</Button>{/if}<Button variant="danger" size="sm" disabled={!!busy[row.id] || !canDelete} onclick={() => deleteTarget = row}>{t('delete')}</Button>{/if}
						</div>
						{#if rowErrors[row.id]}<div class="row-error"><Alert tone="danger" flat>{rowErrors[row.id]}</Alert></div>{/if}
						{#if deleteTarget?.id === row.id}<div class="row-error"><Alert tone="warning" flat>{t('deleteConfirm', { name: row.name })}</Alert><div class="actions"><Button variant="secondary" size="sm" onclick={() => deleteTarget = null}>{t('cancel')}</Button><Button variant="danger" size="sm" onclick={() => remove(row)}>{t('delete')}</Button></div></div>{/if}
						{#if revokeTarget?.id === row.id}<div class="row-error"><Alert tone="warning" flat>{t('revokeConfirm', { name: row.name })}</Alert><div class="actions"><Button variant="secondary" size="sm" onclick={() => revokeTarget = null}>{t('cancel')}</Button><Button variant="danger" size="sm" onclick={() => { revokeTarget = null; oauth(row, true); }}>{t('revokeOAuth')}</Button></div></div>{/if}
					</div>
				{:else}{#if !loading && !(list.scope === 'domain' && organizationError)}<p>{t('emptyConnections')}</p>{/if}{/each}
			</section>
		{/each}
	{/if}
	{#if editor}
		<form class="editor" aria-labelledby="mcp-editor-title" method="post" onsubmit={(event) => { event.preventDefault(); save(); }}>
			<h4 id="mcp-editor-title">{editor.row ? t('editTitle', { name: editor.row.name }) : t('connectTitle', { name: editor.template!.name })}</h4>
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
	<search><form class="search-form" method="get" aria-label={t('browse')} onsubmit={(event) => { event.preventDefault(); browse(0, query.trim()); }}><Field label={t('search')} for="mcp-gallery-search"><TextInput id="mcp-gallery-search" type="search" bind:value={query} maxlength={100} /></Field><Button type="submit" variant="secondary" disabled={loading || !owner}>{t('searchAction')}</Button></form></search>
	<h4>{t('browse')} <span class="count">{total}</span></h4>
	{#if !loading && !error && !entries.length}<p>{t('emptySearch')}</p>{/if}
	<div class="catalog-list">{#each entries as entry (entry.id)}{@render templateCard(entry)}{/each}</div>
	{#if total > 0}<Pagination page={Math.floor(offset / limit) + 1} totalPages={Math.ceil(total / limit)} total={total} pageSize={limit} hasPrev={offset > 0 && !loading} hasNext={nextOffset !== null && !loading} onPrev={() => browse(Math.max(0, offset - limit))} onNext={() => nextOffset !== null && browse(nextOffset)} />{/if}
</section>

{#snippet templateCard(entry: McpTemplate)}
	<article class="template" aria-label={entry.name}>
		<div class="row-copy"><div class="template-heading"><strong>{entry.name}</strong>{#if entry.access === 'managed'}<Pill tone="neutral" size="xs">{t('builtIn')}</Pill>{/if}</div><p>{entry.description}</p><p class="registry-name">{entry.registry_name}</p>
			{#if entry.access === 'managed'}<p>{entry.managed ? entry.managed.available ? t('managedAvailable') : reason(entry.managed.reason) : t('managedUnknown')}</p>{#if entry.managed?.tools.length}<p>{entry.managed.tools.join(', ')}</p>{/if}
			{:else if entry.access === 'unavailable' || entry.access === 'unreachable'}<p>{reason(entry.unavailable_reason)}</p>{:else}<p>{entry.access === 'oauth' ? t('oauthHelp') : entry.access === 'credentials' ? t('credentialsHelp') : entry.access === 'configure' ? t('configureHelp') : t('publicHelp')}</p>{/if}
		</div>
		{#if !['managed', 'unavailable', 'unreachable'].includes(entry.access)}<div class="actions"><Button variant="outline" size="sm" disabled={!canWrite || loading || !!busy[`template-${entry.id}`]} onclick={() => openEditor(entry, undefined, admin ? 'global' : 'user')}>{admin ? t('install') : t('connectPersonal')}</Button>{#if !admin && canManage}<Button variant="secondary" size="sm" disabled={!canWrite || loading || !!busy[`template-${entry.id}`]} onclick={() => openEditor(entry, undefined, 'domain')}>{t('connectOrganization')}</Button>{/if}</div>{/if}
		{#if rowErrors[`template-${entry.id}`]}<Alert tone="danger" flat>{rowErrors[`template-${entry.id}`]}</Alert>{/if}
	</article>
{/snippet}

<style>
	.gallery { display: grid; gap: 1rem; min-width: 0; margin-block-end: 2rem; color: var(--color-ink-1); }
	h3, h4 { margin: 0; font-size: var(--type-body); font-weight: 600; color: var(--color-ink-0); }
	p { margin: 0.35rem 0 0; font-size: var(--type-support); color: var(--color-ink-2); overflow-wrap: anywhere; }
	.toolbar, .connection-row { display: flex; flex-wrap: wrap; justify-content: space-between; align-items: flex-start; gap: 0.75rem 1.5rem; }
	.toolbar > div:first-child, .row-copy { min-width: 0; flex: 1 1 16rem; }
	.actions, .metadata, .template-heading { display: flex; flex-wrap: wrap; align-items: center; gap: 0.5rem; }
	.metadata { margin-block-start: 0.4rem; font-size: var(--type-support); color: var(--color-ink-2); }
	.featured-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 18rem), 1fr)); gap: 0.75rem; }
	.featured-grid .template { border: 1px solid var(--color-line); border-radius: var(--radius-lg); padding: 1rem; background: var(--color-surface-base); }
	.template { display: flex; flex-direction: column; gap: 0.75rem; padding-block: 1rem; min-width: 0; }
	.catalog-list .template + .template, .connection-row { border-block-start: 1px solid var(--color-line); }
	.catalog-list .template .row-copy { flex: auto; }
	.featured-grid .row-copy { flex: 1; }
	.registry-name, .endpoint { overflow-wrap: anywhere; font-size: var(--type-identifier); }
	.scope-note { display: grid; gap: 0.4rem; padding-block: 0.75rem; font-size: var(--type-support); color: var(--color-ink-2); overflow-wrap: anywhere; }
	.connections { display: grid; gap: 0.75rem; min-width: 0; }
	.connection-row { padding-block: 0.875rem; }
	.row-error { flex-basis: 100%; min-width: 0; }
	.editor { display: grid; gap: 1rem; border-block: 1px solid var(--color-line); padding-block: 1.25rem; }
	fieldset { display: grid; gap: 0.75rem; min-width: 0; border: 0; padding: 0; }
	legend { font-size: var(--type-body); font-weight: 500; }
	.header-fields { display: grid; gap: 0.75rem; align-items: end; }
	.search-form { display: flex; flex-wrap: wrap; align-items: end; gap: 0.75rem; }
	.search-form :global(.field) { flex: 1 1 16rem; }
	.count { color: var(--color-ink-2); font-weight: 400; font-variant-numeric: tabular-nums; }
	@media (min-width: 768px) { .header-fields { grid-template-columns: minmax(0, 1fr) minmax(0, 1fr) auto; } .catalog-list .template { flex-direction: row; align-items: center; flex-wrap: wrap; } .catalog-list .template .row-copy { flex: 1 1 20rem; } }
	.header-fields.declared-header { grid-template-columns: minmax(0, 1fr); }
</style>
