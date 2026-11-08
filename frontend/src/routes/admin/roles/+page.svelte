<script lang="ts">
	import { onMount } from 'svelte';
	import { derived, get } from 'svelte/store';
	import { auth, authReady, projectSwitching } from '$lib/stores/auth';
	import type { AuthState } from '$lib/stores/auth';
	import { api, ApiError } from '$lib/api/client';
	import PageShell from '$lib/components/ui/PageShell.svelte';
	import PageHeader from '$lib/components/ui/PageHeader.svelte';
	import Card from '$lib/components/ui/Card.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import TextInput from '$lib/components/ui/TextInput.svelte';
	import ToggleGroup from '$lib/components/ui/ToggleGroup.svelte';
	import TableShell from '$lib/components/ui/TableShell.svelte';
	import ResponsiveTable from '$lib/components/ui/ResponsiveTable.svelte';
	import CompactResourceCard from '$lib/components/ui/CompactResourceCard.svelte';
	import RegexSearch from '$lib/components/ui/RegexSearch.svelte';
	import TableColumnHeader from '$lib/components/ui/TableColumnHeader.svelte';
	import TableViewControls from '$lib/components/ui/TableViewControls.svelte';
	import { createTableView } from '$lib/utils/tableView.svelte';
	import Alert from '$lib/components/ui/Alert.svelte';
	import EmptyState from '$lib/components/ui/EmptyState.svelte';
	import FormModal from '$lib/components/ui/FormModal.svelte';
	import Field from '$lib/components/ui/Field.svelte';
	import LoadingState from '$lib/components/ui/LoadingState.svelte';
	import AutoRefreshControl from '$lib/components/AutoRefreshControl.svelte';
	import { createAutoRefresh } from '$lib/utils/autoRefresh.svelte';
	import RoleBadges from '$lib/components/admin/roles/RoleBadges.svelte';
	import RoleTree from '$lib/components/admin/roles/RoleTree.svelte';
	import RoleDetailPanel from '$lib/components/admin/roles/RoleDetailPanel.svelte';
	import RoleMetadataModal from '$lib/components/admin/roles/RoleMetadataModal.svelte';
	import TutorialStartButton from '$lib/tutorial/TutorialStartButton.svelte';
	import { buildRoleGraph, deleteDisabledReason, edgeDisabledReason, roleColumns } from '$lib/components/admin/roles/catalog';
	import type { ManagedRole, RoleMetadata } from '$lib/components/admin/roles/types';
	import { t } from '$lib/i18n/ns/admin-identity';
	import { t as tc } from '$lib/i18n/ns/common';
	import { confirmDialog } from '$lib/stores/confirm.svelte';
	import { isNativeRole } from '$lib/components/admin/roles/naming';
	import { isRetiredRole } from '$lib/utils/roleCatalog';
	import { sessionScopeKey } from '$lib/utils/authSession';
	import { createPrivateViewScope } from '$lib/utils/privateViewScope';
	import { intlLocale } from '$lib/i18n/runtime.svelte';
	const privateScope = createPrivateViewScope();
	type RolePreset = { name: string; description: string; area: string; grade: string; parent: string | null };
	type PresetPreview = { roles: RolePreset[]; implications: { prior: string; implied: string }[]; retired_implications: { prior: string; implied: string }[]; project_roles: RolePreset[] };
	let preset = $state<PresetPreview | null>(null);
	let presetLoading = $state(false);
	let presetVersion = 0;
	let presetQuery = $state('');
	const presetRoleView = createTableView<RolePreset>({
		rows: () => preset ? [...preset.project_roles, ...preset.roles].filter((item) => !isRetiredRole(item)) : [],
		search: () => presetQuery,
		locale: intlLocale,
		columns: () => [
			{ key: 'name', label: t('form.name'), value: (item) => item.name },
			{ key: 'description', label: t('form.description'), value: (item) => item.description },
		],
	});
	type PresetEdge = { prior: string; implied: string };
	const edgeColumns = () => [
		{ key: 'prior', label: t('roleDetail.directParentsLabel'), value: (edge: PresetEdge) => edge.prior },
		{ key: 'implied', label: t('roleDetail.directChildrenLabel'), value: (edge: PresetEdge) => edge.implied },
	];
	const presetEdgeView = createTableView<PresetEdge>({
		rows: () => preset?.implications.filter((edge) => !isRetiredRole({ name: edge.prior }) && !isRetiredRole({ name: edge.implied })) ?? [],
		search: () => presetQuery, columns: edgeColumns, locale: intlLocale,
	});
	const retiredEdgeView = createTableView<PresetEdge>({
		rows: () => preset?.retired_implications ?? [],
		search: () => presetQuery, columns: edgeColumns, locale: intlLocale,
	});

	function identityKey(state: AuthState, verified: boolean, switching: boolean, revision: number): string | null {
		return verified && !switching && state.isSystemAdmin === true && state.token
			? JSON.stringify([sessionScopeKey(state), revision]) : null;
	}
	const scope = $derived(identityKey($auth, $authReady, $projectSwitching, $privateScope));
	const authorization = derived([auth, authReady, projectSwitching, privateScope], ([state, verified, switching, revision]) => identityKey(state, verified, switching, revision));
	let loadedScope = $state<string | null>(null);
	let roles = $state<ManagedRole[]>([]);
	let loading = $state(false);
	let refreshing = $state(false);
	let fresh = $state(false);
	let loadError = $state('');
	let actionError = $state('');
	let notice = $state('');
	let busy = $state(false);
	let query = $state('');
	const roleView = createTableView<ManagedRole>({ rows: () => roles, columns: roleColumns, search: () => query, locale: intlLocale });
	let view = $state('list');
	let selectedId = $state<string | null>(null);
	let editor = $state<'create' | 'edit' | null>(null);
	let editId = $state<string | null>(null);
	let deleteId = $state<string | null>(null);
	let confirmation = $state('');
	// The role this page just created. Only its row, detail delete control and delete dialog carry the
	// tutorial anchors, so a tour never targets native, retired or pre-existing roles.
	let createdRoleId = $state<string | null>(null);
	let mounted = false;
	let requestVersion = 0;
	let operationVersion = 0;
	let controller: AbortController | null = null;
	const selected = $derived(roles.find((role) => role.id === selectedId) ?? null);
	const editRole = $derived(roles.find((role) => role.id === editId) ?? null);
	const deleteRole = $derived(roles.find((role) => role.id === deleteId) ?? null);
	const filtered = $derived(roleView.rows);
	const canMutate = $derived(fresh && !busy && !loading && !refreshing);

	function isCurrent(key: string | null): boolean {
		return mounted && key !== null && key === loadedScope && key === identityKey(get(auth), get(authReady), get(projectSwitching), get(privateScope));
	}
	function message(error: unknown): string {
		return error instanceof ApiError || error instanceof Error ? error.message : t('rolePage.requestFailed');
	}

	async function load(force = false): Promise<boolean> {
		const key = loadedScope;
		if (!isCurrent(key) || (busy && !force)) return false;
		const state = get(auth);
		const version = ++requestVersion;
		controller?.abort();
		const request = new AbortController();
		controller = request;
		loading = roles.length === 0;
		refreshing = !loading;
		loadError = '';
		try {
			const result = await api.get<ManagedRole[]>('/api/v1/admin/roles', state.token ?? undefined, state.projectId ?? undefined, { refresh: true, signal: request.signal });
			if (!isCurrent(key) || version !== requestVersion) return false;
			roles = result;
			fresh = true;
			if (selectedId && !result.some((role) => role.id === selectedId)) selectedId = null;
			if (editor === 'edit' && !result.some((role) => role.id === editId)) { editor = null; editId = null; }
			if (deleteId && !result.some((role) => role.id === deleteId)) deleteId = null;
			return true;
		} catch (error) {
			if (!isCurrent(key) || version !== requestVersion) return false;
			fresh = false;
			loadError = t('rolePage.loadFailed', { error: message(error) });
			return false;
		} finally {
			if (isCurrent(key) && version === requestVersion) { loading = false; refreshing = false; controller = null; }
		}
	}

	const ar = createAutoRefresh(async () => { await load(); }, {
		storageKey: 'admin-roles', invokeOnMount: false, defaultActive: true,
		defaultInterval: 60, intervalOptions: [30, 60]
	});

	onMount(() => {
		mounted = true;
		const unsubscribe = authorization.subscribe((key) => {
			if (key === loadedScope) return;
			++requestVersion;
			++operationVersion;
			controller?.abort(); controller = null;
			loadedScope = key;
			query = ''; roleView.reset();
			roles = []; fresh = false; loading = false; refreshing = false; busy = false;
			selectedId = null; editor = null; editId = null; deleteId = null; confirmation = ''; createdRoleId = null;
			preset = null; presetLoading = false; ++presetVersion;
			loadError = ''; actionError = ''; notice = '';
			presetQuery = ''; presetRoleView.reset(); presetEdgeView.reset(); retiredEdgeView.reset();
			if (key) void load();
		});
		return () => { mounted = false; ++requestVersion; ++operationVersion; controller?.abort(); unsubscribe(); };
	});

	function selectRole(role: ManagedRole) { selectedId = role.id; actionError = ''; }
	function openEditor(role: ManagedRole | null) {
		if (!canMutate || (role && isRetiredRole(role))) return;
		editId = role?.id ?? null; editor = role ? 'edit' : 'create'; actionError = '';
	}

	async function mutate<T>(request: (token: string, projectId?: string) => Promise<T>, success: string, after: (result: T) => void) {
		const key = loadedScope;
		if (!canMutate || !isCurrent(key)) return;
		const state = get(auth);
		const operation = ++operationVersion;
		++requestVersion; controller?.abort(); controller = null;
		busy = true; actionError = ''; notice = '';
		try {
			const result = await request(state.token!, state.projectId ?? undefined);
			if (!isCurrent(key) || operation !== operationVersion) return;
			fresh = false;
			after(result);
			notice = success;
			await load(true);
		} catch (error) {
			if (!isCurrent(key) || operation !== operationVersion) return;
			actionError = message(error);
			// Conflicts or transport failures can leave the old graph out of date.
			await load(true);
		} finally {
			if (isCurrent(key) && operation === operationVersion) busy = false;
		}
	}
	async function saveMetadata(metadata: RoleMetadata) {
		if (editor === 'edit' && editRole && !isRetiredRole(editRole)) {
			const role = editRole;
			const body = { description: metadata.description, ...(!role.protected && !isNativeRole(role.name) && metadata.name !== undefined ? { name: metadata.name } : {}) };
			await mutate((token, project) => api.patch<ManagedRole>(`/api/v1/admin/roles/${encodeURIComponent(role.id)}`, body, token, project), t('rolePage.saved'), () => { editor = null; editId = null; });
		} else if (editor === 'create' && metadata.name) {
			await mutate((token, project) => api.post<ManagedRole>('/api/v1/admin/roles', metadata, token, project), t('rolePage.created'), (role) => { editor = null; createdRoleId = role.id; });
		}
	}
	async function toggleEdge(candidate: ManagedRole) {
		if (!selected || !canMutate) return;
		const prior = selected;
		if (edgeDisabledReason(buildRoleGraph(roles), prior, candidate)) return;
		const removing = prior.implied_role_ids.includes(candidate.id);
		const path = `/api/v1/admin/roles/${encodeURIComponent(prior.id)}/implies/${encodeURIComponent(candidate.id)}`;
		await mutate((token, project) => removing ? api.delete(path, token, project) : api.put(path, {}, token, project), removing ? t('rolePage.edgeRemoved') : t('rolePage.edgeAdded'), () => {});
	}
	function confirmDelete() {
		if (!deleteRole || deleteDisabledReason(deleteRole) || confirmation !== deleteRole.name) return;
		const role = deleteRole;
		void mutate((token, project) => api.delete(`/api/v1/admin/roles/${encodeURIComponent(role.id)}`, token, project), t('rolePage.deleted'), () => { deleteId = null; selectedId = null; confirmation = ''; if (createdRoleId === role.id) createdRoleId = null; });
	}
	async function previewPresets() {
		const key = loadedScope;
		if (!isCurrent(key) || !canMutate || presetLoading) return;
		const version = ++presetVersion;
		presetQuery = ''; presetRoleView.reset(); presetEdgeView.reset(); retiredEdgeView.reset();
		presetLoading = true; actionError = '';
		const state = get(auth);
		try {
			const result = await api.get<PresetPreview>('/api/v1/admin/roles/presets', state.token!, state.projectId ?? undefined, { refresh: true });
			if (isCurrent(key) && version === presetVersion) preset = result;
		} catch (error) {
			if (isCurrent(key) && version === presetVersion) actionError = message(error);
		} finally {
			if (isCurrent(key) && version === presetVersion) presetLoading = false;
		}
	}
	async function applyPresets() {
		const key = loadedScope;
		const version = presetVersion;
		if (!preset || !canMutate || !isCurrent(key)) return;
		const confirmed = await confirmDialog(t('rolePresets.confirm'), { confirmLabel: t('rolePresets.apply'), confirmVariant: 'primary' });
		if (!confirmed || !isCurrent(key) || version !== presetVersion || !preset) return;
		await mutate((token, project) => api.post('/api/v1/admin/roles/presets/apply', {}, token, project), t('rolePresets.applied'), () => { preset = null; view = 'tree'; });
	}
</script>

{#if scope && scope === loadedScope}
	<PageShell class="min-w-0">
		<PageHeader breadcrumb={t('rolePage.breadcrumb')} title={t('rolePage.title')}>
			{#snippet actions()}
				<TutorialStartButton tour="admin-roles" compactOnMobile />
				<AutoRefreshControl bind:active={ar.active} bind:intervalSeconds={ar.intervalSeconds} intervalOptions={ar.intervalOptions} refreshing={loading || refreshing || busy} onManualRefresh={() => { void load(); }} />
				<Button disabled={!canMutate} dataTour="admin-roles-create-open" onclick={() => openEditor(null)}>{t('rolePage.create')}</Button>
				<Button variant="secondary" disabled={!canMutate || presetLoading} onclick={previewPresets}>{t('rolePresets.preview')}</Button>
			{/snippet}
		</PageHeader>
		<div class="space-y-4 min-w-0">
			<Card surface="base" padding="md" class="min-w-0">
				<div class="flex min-w-0 flex-col gap-3 md:flex-row md:flex-wrap md:items-center">
					<div class="min-w-0 flex-1"><RegexSearch id="admin-role-search" bind:value={query} label={t('rolePage.searchLabel')} /></div>
					<ToggleGroup value={view} options={[{ value: 'list', label: t('rolePage.viewList') }, { value: 'tree', label: t('rolePage.viewTree') }]} onchange={(value) => { view = value; }} ariaLabel={t('rolePage.viewLabel')} />
				</div>
				<div class="mt-3 flex flex-wrap items-center gap-2 text-xs text-ink-2" data-tour="admin-roles-summary">
					<span aria-live="polite">{t('rolePage.count', { shown: filtered.length, total: roles.length })}</span>
				</div>
			</Card>
			<TableViewControls view={roleView} class={view === 'tree' ? '' : 'lg:hidden'} />
			<p class="text-xs text-ink-2">{tc('table.loadedScope')}</p>
			{#if loadError}<Alert tone="danger">{loadError} {roles.length ? t('rolePage.previousListShown') : ''} <Button variant="secondary" size="sm" disabled={busy} onclick={() => { void load(); }}>{t('rolePage.retry')}</Button></Alert>{/if}
			{#if actionError && !editor && !deleteId && !selected}<Alert tone="danger">{actionError}</Alert>{/if}
			{#if notice}<Alert tone="success">{notice}</Alert>{/if}
			{#if refreshing}<LoadingState variant="inline" label={t('rolePage.refreshing')} />{/if}
			{#if loading}<LoadingState variant="surface" />
			{:else if roles.length === 0 && !loadError}<EmptyState headline={t('rolePage.empty')} description={t('rolePage.emptyDescription')} />
			{:else if view === 'tree'}
				{#if filtered.length === 0 && roles.length > 0}<EmptyState headline={t('rolePage.noResults')} description={t('rolePage.noResultsDescription')}>{#snippet cta()}<Button variant="secondary" onclick={() => { query = ''; roleView.reset(); }}>{t('rolePage.clearSearch')}</Button>{/snippet}</EmptyState>{/if}
				<RoleTree {roles} view={roleView} onSelect={selectRole} tourRoleId={createdRoleId} />
			{:else if roles.length > 0}
				<ResponsiveTable>
					{#snippet cards()}
						{#if filtered.length === 0}<p class="text-sm text-ink-2">{tc('table.noMatches')}</p>{/if}
						{#each filtered as role (role.id)}
							<CompactResourceCard selected={selectedId === role.id}>
								<div class="flex min-w-0 flex-wrap items-start justify-between gap-2">
									<Button variant="link" class="min-h-11 max-w-full !whitespace-normal [overflow-wrap:anywhere] !text-left" ariaLabel={t('rolePage.detailLabel', { name: role.name })} dataTour={role.id === createdRoleId ? 'admin-roles-created' : undefined} onclick={() => selectRole(role)}>{role.name}</Button>
									<RoleBadges {role} />
								</div>
								<dl>
									<div><dt>{t('rolePage.columns.directChildren')}</dt><dd>{role.implied_role_ids.length}</dd></div>
									<div><dt>{t('rolePage.columns.inherited')}</dt><dd>{role.inherited_role_ids.length}</dd></div>
									<div><dt>{t('rolePage.columns.directParents')}</dt><dd>{role.parent_role_ids.length}</dd></div>
								</dl>
								{#snippet details()}
									<dl><div><dt>ID</dt><dd class="font-mono">{role.id}</dd></div></dl>
									<p class="mt-2">{role.description || t('rolePage.noDescription')}</p>
								{/snippet}
							</CompactResourceCard>
						{/each}
					{/snippet}
					<TableShell class="max-w-full">
					<table aria-label={t('projectAccess.roleListLabel')}>
						<thead><tr>
							{#each roleView.columns as column (column.key)}<TableColumnHeader view={roleView} columnKey={column.key} />{/each}
						</tr></thead>
						<tbody>{#each filtered as role (role.id)}<tr data-selected={selectedId === role.id}>
							<td><Button variant="link" class="max-w-64 truncate" ariaLabel={t('rolePage.detailLabel', { name: role.name })} title={role.name} dataTour={role.id === createdRoleId ? 'admin-roles-created' : undefined} onclick={() => selectRole(role)}>{role.name}</Button></td>
							<td class="font-mono text-ink-2" title={role.id}>{role.id.slice(0, 12)}</td><td><RoleBadges {role} /></td>
							<td>{role.implied_role_ids.length}</td><td>{role.inherited_role_ids.length}</td><td>{role.parent_role_ids.length}</td>
							<td class="max-w-64 whitespace-pre-wrap break-words">{role.description || t('rolePage.noDescription')}</td>
							<td class="font-mono break-all">{role.domain_id ?? t('roleDetail.global')}</td>
						</tr>{:else}<tr><td colspan={roleView.columns.length}>{tc('table.noMatches')}</td></tr>{/each}</tbody>
					</table>
					</TableShell>
				</ResponsiveTable>
			{/if}
		</div>
	</PageShell>
	{#if selected}
		{@const currentRole = selected}
		<RoleDetailPanel role={currentRole} {roles} busy={busy || refreshing || loading} stale={!fresh} error={actionError} tourDelete={currentRole.id === createdRoleId} onClose={() => { selectedId = null; actionError = ''; }} onEdit={() => openEditor(currentRole)} onDelete={() => { if (canMutate) { deleteId = currentRole.id; confirmation = ''; actionError = ''; } }} onToggle={toggleEdge} onSelect={selectRole} />
	{/if}
	{#if editor}
		{#key `${editor}:${editId}`}<RoleMetadataModal role={editor === 'edit' ? editRole : null} {busy} disabled={!canMutate} error={actionError || loadError} onClose={() => { if (!busy) { editor = null; actionError = ''; } }} onSave={saveMetadata} />{/key}
	{/if}
	{#if preset}
		<FormModal open={true} title={t('rolePresets.preview')} submitting={busy} onClose={() => { if (!busy) { preset = null; ++presetVersion; } }}>
			<div class="space-y-4 min-w-0">
				<Alert tone="info">{t('rolePresets.previewHelp')}</Alert>
				{#if actionError || loadError}<Alert tone="danger">{actionError || loadError}</Alert>{/if}
				<RegexSearch id="role-preset-search" bind:value={presetQuery} label={tc('table.search')} />
				<TableViewControls view={presetRoleView} class="" />
				<ul class="space-y-2 text-sm">{#each presetRoleView.rows as item (item.name)}<li class="[overflow-wrap:anywhere]"><code>{item.name}</code><span class="text-ink-2"> — {item.description}</span></li>{:else}<li class="text-ink-2">{tc('table.noMatches')}</li>{/each}</ul>
				<h3 class="text-sm font-semibold">{t('rolePresets.directImplications')}</h3>
				<TableViewControls view={presetEdgeView} class="" />
				<ul class="space-y-1 text-xs font-mono text-ink-2">{#each presetEdgeView.rows as edge (`${edge.prior}:${edge.implied}`)}<li class="[overflow-wrap:anywhere]">{edge.prior} → {edge.implied}</li>{:else}<li>{tc('table.noMatches')}</li>{/each}</ul>
				<h3 class="text-sm font-semibold">{t('rolePresets.retiredImplications')}</h3>
				<TableViewControls view={retiredEdgeView} class="" />
				<ul class="space-y-1 text-xs font-mono text-ink-2">{#each retiredEdgeView.rows as edge (`${edge.prior}:${edge.implied}`)}<li class="[overflow-wrap:anywhere]">{edge.prior} → {edge.implied}</li>{:else}<li>{tc('table.noMatches')}</li>{/each}</ul>
			</div>
			{#snippet actions()}
				<Button variant="secondary" disabled={busy} onclick={() => { preset = null; ++presetVersion; }}>{tc('actions.cancel')}</Button>
				<Button variant="primary" disabled={!canMutate} ariaBusy={busy} onclick={applyPresets}>{t('rolePresets.apply')}</Button>
			{/snippet}
		</FormModal>
	{/if}
	{#if deleteRole}
		<FormModal open={true} title={t('rolePage.delete.title')} submitting={busy} onClose={() => { if (!busy) { deleteId = null; actionError = ''; confirmation = ''; } }}>
			<div class="space-y-4">
				<p class="text-sm text-ink-1 [overflow-wrap:anywhere]">{t('rolePage.delete.body', { name: deleteRole.name })}</p>
				<p class="font-mono text-xs text-ink-2 [overflow-wrap:anywhere]">{deleteRole.id}</p>
				<Alert tone="warning">{t('rolePage.delete.warning')}</Alert>
				{#if actionError || loadError}<Alert tone="danger">{actionError || loadError}</Alert>{/if}
				{#if deleteDisabledReason(deleteRole)}<Alert tone="warning">{deleteDisabledReason(deleteRole)}</Alert>{/if}
				<div data-tour={deleteRole.id === createdRoleId ? 'admin-roles-delete-name' : undefined}><Field label={t('rolePage.delete.confirmLabel')} for="role-delete-name" help={t('rolePage.delete.confirmHelp')}><TextInput id="role-delete-name" bind:value={confirmation} disabled={!canMutate} /></Field></div>
			</div>
			{#snippet actions()}
				<Button variant="secondary" disabled={busy} onclick={() => { deleteId = null; confirmation = ''; actionError = ''; }}>{t('rolePage.delete.cancel')}</Button>
				<Button variant="danger" ariaBusy={busy} disabled={!canMutate || confirmation !== deleteRole.name || !!deleteDisabledReason(deleteRole)} dataTour={deleteRole.id === createdRoleId ? 'admin-roles-delete-confirm' : undefined} onclick={confirmDelete}>{t('rolePage.delete.submit')}</Button>
			{/snippet}
		</FormModal>
	{/if}
{:else}
	<PageShell><EmptyState headline={t('rolePage.unauthorized.title')} description={t('rolePage.unauthorized.description')} /></PageShell>
{/if}
