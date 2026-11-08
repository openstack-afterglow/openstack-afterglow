<script lang="ts">
	import { intlLocale } from '$lib/i18n/runtime.svelte';
	import { createTableView } from '$lib/utils/tableView.svelte';
	import TableColumnHeader from '$lib/components/ui/TableColumnHeader.svelte';
	import TableViewControls from '$lib/components/ui/TableViewControls.svelte';
	import RegexSearch from '$lib/components/ui/RegexSearch.svelte';
	import ResponsiveTable from '$lib/components/ui/ResponsiveTable.svelte';
	import CompactResourceCard from '$lib/components/ui/CompactResourceCard.svelte';
	import { onMount, onDestroy, untrack } from 'svelte';
	import { get } from 'svelte/store';
	import { auth } from '$lib/stores/auth';
	import { invalidateWorkspaceDisplaySnapshots } from '$lib/stores/workspaceController.svelte';
	import { continueAfterProjectDeletion } from '$lib/utils/projectDeletionContinuation';
	import { ApiError } from '$lib/api/client';
	import { domainIam, type IamSession } from '$lib/api/domainIam';
	import { projectAuthority } from '$lib/api/projectAuthority';
	import type { Project } from '$lib/types/project';
	import { t } from '$lib/i18n/ns/domain-iam';
	import { t as workspaceT } from '$lib/i18n/ns/workspace-selector';
	import { iamErrorMessage } from './iamError';
	import Button from '$lib/components/ui/Button.svelte';
	import Alert from '$lib/components/ui/Alert.svelte';
	import Pill from '$lib/components/ui/Pill.svelte';
	import SlideOver from '$lib/components/ui/SlideOver.svelte';
	import TableShell from '$lib/components/ui/TableShell.svelte';
	import LoadingState from '$lib/components/ui/LoadingState.svelte';
	import AdminProjectDeleteModal from '$lib/components/admin/projects/AdminProjectDeleteModal.svelte';
	import CreateProjectModal from '$lib/components/projects/CreateProjectModal.svelte';
	import IamProjectEdit from './IamProjectEdit.svelte';
	import IamProjectMembers from './IamProjectMembers.svelte';

	let { session, canCreate = true, blocked = false, onDenied, highlightId = null, onCreated }: {
		session: IamSession; canCreate?: boolean; blocked?: boolean; onDenied: () => void;
		// The tutorial delete anchor targets only the project the page just created.
		highlightId?: string | null; onCreated?: (projectId: string) => void;
	} = $props();
	const client = untrack(() => domainIam(session));
	const authority = untrack(() => projectAuthority(session));
	const uid = $props.id();
	let live = true;
	let revision = 0;
	let projects = $state<Project[]>([]);
	let loading = $state(true);
	let error = $state('');
	let showCreate = $state(false);
	let creating = $state(false);
	let panel = $state<{ mode: 'edit' | 'members'; project: Project } | null>(null);
	let deleting = $state<Project | null>(null);

	// The domain's canonical Default project is system-owned: never renamed or deleted here.
	const isDefault = (project: Project) => project.name.trim().toLowerCase() === 'default';
	const actionsDisabled = $derived(blocked || !session.canSubmit());

	function fail(cause: unknown) {
		if (!live || !session.isCurrent()) return;
		error = iamErrorMessage(cause, t('loadFailed'));
		if (cause instanceof ApiError && cause.status === 403) onDenied();
	}
	async function load() {
		const pending = ++revision;
		loading = true; error = '';
		try {
			const result = await client.projects();
			if (!live || !session.isCurrent() || pending !== revision) return;
			projects = result.items;
			if (panel) {
				const fresh = projects.find(row => row.id === panel!.project.id);
				if (fresh) panel = { mode: panel.mode, project: fresh };
				else panel = null;
			}
		} catch (cause) { if (pending === revision) fail(cause); }
		finally { if (live && pending === revision) loading = false; }
	}
	function created(project: { id: string; name: string }) {
		if (!live || !session.isCurrent()) return;
		invalidateWorkspaceDisplaySnapshots();
		onCreated?.(project.id);
		showCreate = false;
		void load();
	}
	function deleted(project: Project) {
		deleting = null;
		if (!live || !session.isCurrent()) return;
		invalidateWorkspaceDisplaySnapshots();
		if (panel?.project.id === project.id) panel = null;
		const state = get(auth);
		if (state.projectId === project.id && state.domainId === session.domainId) void continueAfterProjectDeletion(project.id, session.domainId);
		else void load();
	}
	onMount(() => { void load(); });
	onDestroy(() => { live = false; revision++; projects = []; panel = null; deleting = null; });

	const tableSearchId = `${uid}-search`;
	let tableSearch = $state('');
	const tableView = createTableView<Project>({
		rows: () => projects, locale: () => intlLocale(), search: () => tableSearch,
		searchable: row => [row.name, row.description ?? '', row.id],
		columns: () => [
			{ key: 'name', label: t('name'), value: row => row.name },
			{ key: 'description', label: t('description'), value: row => row.description ?? '' },
			{ key: 'status', label: t('status'), value: row => row.enabled, format: (_, row) => t(row.enabled ? 'enabled' : 'disabled') },
			{ key: 'created', label: t('createdAt'), value: row => row.created_at ?? '', format: (_, row) => row.created_at?.slice(0, 10) ?? '—' }
		]
	});
</script>

<div class="space-y-4">
	<div class="flex flex-wrap justify-end gap-2">
		<Button variant="secondary" disabled={loading} onclick={load}>{t('refresh')}</Button>
		{#if canCreate}<Button variant="accent" disabled={actionsDisabled || creating} onclick={() => { showCreate = true; }} dataTour="iam-projects-create-open">{workspaceT('newProject')}</Button>{/if}
	</div>
	{#if loading}<LoadingState variant={projects.length ? 'inline' : 'surface'} label={t('loading')} />{/if}
	{#if error}<Alert tone="danger">{error}</Alert>{/if}
	{#if !loading && !error && !projects.length}<Alert tone="info">{t('emptyProjects')}</Alert>{/if}
	<RegexSearch id={tableSearchId} bind:value={tableSearch} /><TableViewControls view={tableView} />
	<div data-tour="iam-projects-list">
	<ResponsiveTable>
		{#snippet cards()}
			{#each tableView.rows as project (project.id)}<CompactResourceCard>
				<div class="flex flex-wrap items-center justify-between gap-2"><h3 class="min-w-0 break-words text-sm font-medium">{project.name}</h3><Pill tone={project.enabled ? 'success' : 'danger'}>{project.enabled ? t('enabled') : t('disabled')}</Pill></div>
				<p class="line-clamp-2 text-sm text-ink-2">{project.description || '—'}</p>
				{#if isDefault(project)}<p class="text-xs text-ink-2">{t('defaultProtected')}</p>{/if}
				{#snippet actions()}
					<Button variant="secondary" size="sm" disabled={actionsDisabled || isDefault(project)} onclick={() => { panel = { mode: 'edit', project }; }}>{t('projectEdit')}</Button>
					<Button variant="secondary" size="sm" disabled={actionsDisabled} onclick={() => { panel = { mode: 'members', project }; }}>{t('projectMembers')}</Button>
					<Button variant="danger-outline" size="sm" disabled={actionsDisabled || isDefault(project)} onclick={() => { deleting = project; }} dataTour={project.id === highlightId ? 'iam-projects-delete' : undefined}>{t('projectRemove')}</Button>
				{/snippet}
			</CompactResourceCard>{/each}
		{/snippet}
		<TableShell><table>
			<thead><tr><TableColumnHeader view={tableView} columnKey="name" /><TableColumnHeader view={tableView} columnKey="description" /><TableColumnHeader view={tableView} columnKey="status" /><TableColumnHeader view={tableView} columnKey="created" /><th>{t('actions')}</th></tr></thead>
			<tbody>
				{#each tableView.rows as project (project.id)}<tr>
					<td><span class="font-medium">{project.name}</span>{#if isDefault(project)}<span class="block text-xs text-ink-2">{t('defaultProtected')}</span>{/if}</td>
					<td class="max-w-80 whitespace-normal [overflow-wrap:anywhere]">{project.description || '—'}</td>
					<td><Pill tone={project.enabled ? 'success' : 'danger'}>{project.enabled ? t('enabled') : t('disabled')}</Pill></td>
					<td>{project.created_at?.slice(0, 10) ?? '—'}</td>
					<td><div class="flex flex-wrap gap-2">
						<Button variant="secondary" size="sm" disabled={actionsDisabled || isDefault(project)} onclick={() => { panel = { mode: 'edit', project }; }}>{t('projectEdit')}</Button>
						<Button variant="secondary" size="sm" disabled={actionsDisabled} onclick={() => { panel = { mode: 'members', project }; }}>{t('projectMembers')}</Button>
						<Button variant="danger-outline" size="sm" disabled={actionsDisabled || isDefault(project)} onclick={() => { deleting = project; }} dataTour={project.id === highlightId ? 'iam-projects-delete' : undefined}>{t('projectRemove')}</Button>
					</div></td>
				</tr>{/each}
				{#if !loading && !error && !projects.length}<tr><td colspan="5">{t('emptyProjects')}</td></tr>{/if}
			</tbody>
		</table></TableShell>
	</ResponsiveTable>
	</div>
</div>

{#if panel}
	{#key `${panel.mode}:${panel.project.id}`}
		<SlideOver open={true} title={t(panel.mode === 'edit' ? 'editProjectTitle' : 'membersTitle', { project: panel.project.name })} subtitle={panel.project.id} onClose={() => { panel = null; }}>
			{#if panel.mode === 'edit'}
				<IamProjectEdit {session} project={panel.project} {blocked} {onDenied} onSaved={() => { invalidateWorkspaceDisplaySnapshots(); void load(); }} />
			{:else}
				<IamProjectMembers {session} project={panel.project} {blocked} {onDenied} />
			{/if}
		</SlideOver>
	{/key}
{/if}
{#if deleting}<AdminProjectDeleteModal project={deleting} domainId={session.domainId} {session} onClose={() => { deleting = null; }} onSuccess={() => deleted(deleting!)} />{/if}
{#if showCreate && canCreate}<CreateProjectModal domainId={session.domainId} domainName="" bind:submitting={creating} submitDisabled={actionsDisabled} onCreate={authority.create} onClose={() => { showCreate = false; }} onSuccess={created} />{/if}
