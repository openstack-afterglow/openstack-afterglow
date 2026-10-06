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
	import Alert from '$lib/components/ui/Alert.svelte';
	import EmptyState from '$lib/components/ui/EmptyState.svelte';
	import FormModal from '$lib/components/ui/FormModal.svelte';
	import Field from '$lib/components/ui/Field.svelte';
	import LoadingSkeleton from '$lib/components/LoadingSkeleton.svelte';
	import AutoRefreshControl from '$lib/components/AutoRefreshControl.svelte';
	import { createAutoRefresh } from '$lib/utils/autoRefresh.svelte';
	import RoleBadges from '$lib/components/admin/roles/RoleBadges.svelte';
	import RoleTree from '$lib/components/admin/roles/RoleTree.svelte';
	import RoleDetailPanel from '$lib/components/admin/roles/RoleDetailPanel.svelte';
	import RoleMetadataModal from '$lib/components/admin/roles/RoleMetadataModal.svelte';
	import { buildRoleGraph, deleteDisabledReason, edgeDisabledReason, matchesRole, sortRoles } from '$lib/components/admin/roles/catalog';
	import type { ManagedRole, RoleMetadata, RoleSort, SortDirection } from '$lib/components/admin/roles/types';
	import { t } from '$lib/i18n/ns/admin-identity';

	function identityKey(state: AuthState, verified: boolean, switching: boolean): string | null {
		return verified && !switching && state.isSystemAdmin === true && state.token
			? JSON.stringify([state.token, state.userId, state.projectId]) : null;
	}
	const scope = $derived(identityKey($auth, $authReady, $projectSwitching));
	const authorization = derived([auth, authReady, projectSwitching], ([state, verified, switching]) => identityKey(state, verified, switching));
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
	let sort = $state<RoleSort>('name');
	let direction = $state<SortDirection>('asc');
	let view = $state('list');
	let selectedId = $state<string | null>(null);
	let editor = $state<'create' | 'edit' | null>(null);
	let editId = $state<string | null>(null);
	let deleteId = $state<string | null>(null);
	let confirmation = $state('');
	let mounted = false;
	let requestVersion = 0;
	let operationVersion = 0;
	let controller: AbortController | null = null;
	const selected = $derived(roles.find((role) => role.id === selectedId) ?? null);
	const editRole = $derived(roles.find((role) => role.id === editId) ?? null);
	const deleteRole = $derived(roles.find((role) => role.id === deleteId) ?? null);
	const filtered = $derived(sortRoles(roles.filter((role) => matchesRole(role, query)), sort, direction));
	const canMutate = $derived(fresh && !busy && !loading && !refreshing);

	function isCurrent(key: string | null): boolean {
		return mounted && key !== null && key === loadedScope && key === identityKey(get(auth), get(authReady), get(projectSwitching));
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
			roles = []; fresh = false; loading = false; refreshing = false; busy = false;
			selectedId = null; editor = null; editId = null; deleteId = null; confirmation = '';
			loadError = ''; actionError = ''; notice = '';
			if (key) void load();
		});
		return () => { mounted = false; ++requestVersion; ++operationVersion; controller?.abort(); unsubscribe(); };
	});

	function chooseSort(key: RoleSort) {
		if (sort === key) direction = direction === 'asc' ? 'desc' : 'asc';
		else { sort = key; direction = 'asc'; }
	}
	function ariaSort(key: RoleSort): 'ascending' | 'descending' | 'none' {
		return sort !== key ? 'none' : direction === 'asc' ? 'ascending' : 'descending';
	}
	function sortLabel(key: RoleSort): string { return sort === key ? direction === 'asc' ? ' ↑' : ' ↓' : ''; }
	function selectRole(role: ManagedRole) { selectedId = role.id; actionError = ''; }
	function openEditor(role: ManagedRole | null) {
		if (!canMutate) return;
		editId = role?.id ?? null; editor = role ? 'edit' : 'create'; actionError = '';
	}

	async function mutate(request: (token: string, projectId?: string) => Promise<unknown>, success: string, after: () => void) {
		const key = loadedScope;
		if (!canMutate || !isCurrent(key)) return;
		const state = get(auth);
		const operation = ++operationVersion;
		++requestVersion; controller?.abort(); controller = null;
		busy = true; actionError = ''; notice = '';
		try {
			await request(state.token!, state.projectId ?? undefined);
			if (!isCurrent(key) || operation !== operationVersion) return;
			fresh = false;
			after();
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
		if (editor === 'edit' && editRole) {
			const role = editRole;
			const body = role.protected ? { description: metadata.description } : { name: metadata.name, description: metadata.description };
			await mutate((token, project) => api.patch<ManagedRole>(`/api/v1/admin/roles/${encodeURIComponent(role.id)}`, body, token, project), t('rolePage.saved'), () => { editor = null; editId = null; });
		} else if (editor === 'create') {
			await mutate((token, project) => api.post<ManagedRole>('/api/v1/admin/roles', metadata, token, project), t('rolePage.created'), () => { editor = null; });
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
		void mutate((token, project) => api.delete(`/api/v1/admin/roles/${encodeURIComponent(role.id)}`, token, project), t('rolePage.deleted'), () => { deleteId = null; selectedId = null; confirmation = ''; });
	}
</script>

{#if scope && scope === loadedScope}
	<PageShell class="min-w-0">
		<PageHeader breadcrumb={t('rolePage.breadcrumb')} title={t('rolePage.title')}>
			{#snippet actions()}
				<AutoRefreshControl bind:active={ar.active} bind:intervalSeconds={ar.intervalSeconds} intervalOptions={ar.intervalOptions} refreshing={loading || refreshing || busy} onManualRefresh={() => { void load(); }} />
				<Button disabled={!canMutate} onclick={() => openEditor(null)}>{t('rolePage.create')}</Button>
			{/snippet}
		</PageHeader>
		<div class="space-y-4 min-w-0">
			<Card surface="base" padding="md" class="min-w-0">
				<div class="flex min-w-0 flex-col gap-3 md:flex-row md:flex-wrap md:items-center">
					<div class="min-w-0 flex-1"><TextInput type="search" bind:value={query} ariaLabel={t('rolePage.searchLabel')} placeholder={t('rolePage.searchPlaceholder')} /></div>
					<ToggleGroup value={view} options={[{ value: 'list', label: t('rolePage.viewList') }, { value: 'tree', label: t('rolePage.viewTree') }]} onchange={(value) => { view = value; }} ariaLabel={t('rolePage.viewLabel')} />
				</div>
				<div class="mt-3 flex flex-wrap items-center gap-2 text-xs text-ink-2">
					<span>{t('rolePage.sort')}</span>
					{#each [{ key: 'name', label: t('form.name') }, { key: 'id', label: 'ID' }, { key: 'inheritance', label: t('rolePage.sortInheritance') }] as option}
						<Button variant="subtle" size="sm" ariaPressed={sort === option.key} ariaLabel={t('rolePage.sortButtonLabel', { label: option.label, indicator: sortLabel(option.key as RoleSort) })} onclick={() => chooseSort(option.key as RoleSort)}>{option.label}{sortLabel(option.key as RoleSort)}</Button>
					{/each}
					<span aria-live="polite">{t('rolePage.count', { shown: filtered.length, total: roles.length })}</span>
				</div>
			</Card>
			{#if loadError}<Alert tone="danger">{loadError} {roles.length ? t('rolePage.previousListShown') : ''} <Button variant="secondary" size="sm" disabled={busy} onclick={() => { void load(); }}>{t('rolePage.retry')}</Button></Alert>{/if}
			{#if actionError && !editor && !deleteId && !selected}<Alert tone="danger">{actionError}</Alert>{/if}
			{#if notice}<Alert tone="success">{notice}</Alert>{/if}
			{#if refreshing}<p role="status" class="text-xs text-ink-2">{t('rolePage.refreshing')}</p>{/if}
			{#if loading}<LoadingSkeleton variant="table" rows={5} />
			{:else if roles.length === 0 && !loadError}<EmptyState headline={t('rolePage.empty')} description={t('rolePage.emptyDescription')} />
			{:else if filtered.length === 0 && roles.length > 0}<EmptyState headline={t('rolePage.noResults')} description={t('rolePage.noResultsDescription')}>{#snippet cta()}<Button variant="secondary" onclick={() => { query = ''; }}>{t('rolePage.clearSearch')}</Button>{/snippet}</EmptyState>
			{:else if view === 'tree'}<RoleTree {roles} {query} {sort} {direction} onSelect={selectRole} />
			{:else if roles.length > 0}
				<div class="space-y-3 md:hidden">
					{#each filtered as role (role.id)}
						<Card surface="base" padding="md">
							<Button variant="link" class="max-w-full !whitespace-normal [overflow-wrap:anywhere] !text-left" ariaLabel={t('rolePage.detailLabel', { name: role.name })} onclick={() => selectRole(role)}>{role.name}</Button>
							<RoleBadges {role} />
							<p class="mt-2 text-xs font-mono text-ink-2 [overflow-wrap:anywhere]">{role.id}</p>
							<p class="mt-2 text-sm text-ink-1 line-clamp-2 [overflow-wrap:anywhere]">{role.description || t('rolePage.noDescription')}</p>
							<p class="mt-2 text-xs text-ink-2">{t('rolePage.cardCounts', { direct: role.implied_role_ids.length, inherited: role.inherited_role_ids.length, parents: role.parent_role_ids.length })}</p>
						</Card>
					{/each}
				</div>
				<div class="hidden min-w-0 md:block"><TableShell class="max-w-full">
					<table aria-label={t('projectAccess.roleListLabel')}>
						<thead><tr>
							<th aria-sort={ariaSort('name')}><Button variant="ghost" size="sm" onclick={() => chooseSort('name')}>{t('form.name')}{sortLabel('name')}</Button></th>
							<th aria-sort={ariaSort('id')}><Button variant="ghost" size="sm" onclick={() => chooseSort('id')}>ID{sortLabel('id')}</Button></th>
							<th>{t('rolePage.columns.kind')}</th><th>{t('rolePage.columns.directChildren')}</th>
							<th aria-sort={ariaSort('inheritance')}><Button variant="ghost" size="sm" onclick={() => chooseSort('inheritance')}>{t('rolePage.columns.inherited')}{sortLabel('inheritance')}</Button></th><th>{t('rolePage.columns.directParents')}</th>
						</tr></thead>
						<tbody>{#each filtered as role (role.id)}<tr data-selected={selectedId === role.id}>
							<td><Button variant="link" class="max-w-64 truncate" ariaLabel={t('rolePage.detailLabel', { name: role.name })} title={role.name} onclick={() => selectRole(role)}>{role.name}</Button></td>
							<td class="font-mono text-ink-2" title={role.id}>{role.id.slice(0, 12)}</td><td><RoleBadges {role} /></td>
							<td>{role.implied_role_ids.length}</td><td>{role.inherited_role_ids.length}</td><td>{role.parent_role_ids.length}</td>
						</tr>{/each}</tbody>
					</table>
				</TableShell></div>
			{/if}
		</div>
	</PageShell>
	{#if selected}
		{@const currentRole = selected}
		<RoleDetailPanel role={currentRole} {roles} busy={busy || refreshing || loading} stale={!fresh} error={actionError} onClose={() => { selectedId = null; actionError = ''; }} onEdit={() => openEditor(currentRole)} onDelete={() => { if (canMutate) { deleteId = currentRole.id; confirmation = ''; actionError = ''; } }} onToggle={toggleEdge} onSelect={selectRole} />
	{/if}
	{#if editor}
		{#key `${editor}:${editId}`}<RoleMetadataModal role={editor === 'edit' ? editRole : null} {busy} disabled={!canMutate} error={actionError || loadError} onClose={() => { if (!busy) { editor = null; actionError = ''; } }} onSave={saveMetadata} />{/key}
	{/if}
	{#if deleteRole}
		<FormModal open={true} title={t('rolePage.delete.title')} submitting={busy} onClose={() => { if (!busy) { deleteId = null; actionError = ''; confirmation = ''; } }}>
			<div class="space-y-4">
				<p class="text-sm text-ink-1 [overflow-wrap:anywhere]">{t('rolePage.delete.body', { name: deleteRole.name })}</p>
				<p class="font-mono text-xs text-ink-2 [overflow-wrap:anywhere]">{deleteRole.id}</p>
				<Alert tone="warning">{t('rolePage.delete.warning')}</Alert>
				{#if actionError || loadError}<Alert tone="danger">{actionError || loadError}</Alert>{/if}
				{#if deleteDisabledReason(deleteRole)}<Alert tone="warning">{deleteDisabledReason(deleteRole)}</Alert>{/if}
				<Field label={t('rolePage.delete.confirmLabel')} for="role-delete-name" help={t('rolePage.delete.confirmHelp')}><TextInput id="role-delete-name" bind:value={confirmation} disabled={!canMutate} /></Field>
			</div>
			{#snippet actions()}
				<Button variant="secondary" disabled={busy} onclick={() => { deleteId = null; confirmation = ''; actionError = ''; }}>{t('rolePage.delete.cancel')}</Button>
				<Button variant="danger" ariaBusy={busy} disabled={!canMutate || confirmation !== deleteRole.name || !!deleteDisabledReason(deleteRole)} onclick={confirmDelete}>{t('rolePage.delete.submit')}</Button>
			{/snippet}
		</FormModal>
	{/if}
{:else}
	<PageShell><EmptyState headline={t('rolePage.unauthorized.title')} description={t('rolePage.unauthorized.description')} /></PageShell>
{/if}
