<script lang="ts">
	import { untrack } from 'svelte';
	import Alert from '$lib/components/ui/Alert.svelte';
	import { createTableView } from '$lib/utils/tableView.svelte';
	import TableColumnHeader from '$lib/components/ui/TableColumnHeader.svelte';
	import TableViewControls from '$lib/components/ui/TableViewControls.svelte';
	import RegexSearch from '$lib/components/ui/RegexSearch.svelte';
	import PageShell from '$lib/components/ui/PageShell.svelte';
	import LoadingState from '$lib/components/ui/LoadingState.svelte';
	import { page } from '$app/stores';
	import { auth } from '$lib/stores/auth';
	import { api, ApiError } from '$lib/api/client';
	import PageHeader from '$lib/components/ui/PageHeader.svelte';
	import ActivityLogTable from '$lib/components/admin/ActivityLogTable.svelte';

	import type { Project, ProjectMember as Member } from '$lib/types/project';
	import { t } from '$lib/i18n/ns/admin-identity';
	import { intlLocale } from '$lib/i18n/runtime.svelte';
  import ResponsiveTable from '$lib/components/ui/ResponsiveTable.svelte';
  import CompactResourceCard from '$lib/components/ui/CompactResourceCard.svelte';

	let { domainId }: { domainId: string; domainName: string } = $props();

	const projectId = $derived($page.params.id);
	const token = $derived($auth.token ?? undefined);
	const adminProjectId = $derived($auth.projectId ?? undefined);

	let project = $state<Project | null>(null);
	let members = $state<Member[]>([]);
	let loading = $state(true);
	let error = $state('');
	let membersLoading = $state(true);
	let membersError = $state('');
	let loadGeneration = 0;
	let tab = $state<'overview' | 'members' | 'activity'>('overview');
	const readOwner = $derived(JSON.stringify([projectId, domainId, $auth.sessionId, $auth.userId, $auth.identityDomainId, $auth.domainId, adminProjectId, $auth.isSystemAdmin, $auth.isDomainManager, !!token]));
	let previousOwner = '';

	$effect(() => {
		const owner = readOwner;
		const requestProjectId = untrack(() => projectId);
		const requestDomain = untrack(() => domainId);
		const requestToken = token;
		const requestAdminProjectId = adminProjectId;
		const generation = ++loadGeneration;
		let live = true;
		const owns = () => live && generation === loadGeneration && projectId === requestProjectId
			&& domainId === requestDomain && token === requestToken && adminProjectId === requestAdminProjectId;
		if (owner !== previousOwner) {
			previousOwner = owner;
			untrack(() => { project = null; members = []; tab = 'overview'; tableSearch = ''; tableView.reset(); });
		}
		loading = true; membersLoading = true; error = ''; membersError = '';
		if (!requestProjectId || !requestDomain) {
			loading = false; membersLoading = false; error = t('projectDetail.loadFailed');
			return () => { live = false; };
		}
		const path = `/api/v1/admin/projects/${encodeURIComponent(requestProjectId)}`;
		const query = `?domain_id=${encodeURIComponent(requestDomain)}`;
		void (async () => {
			try {
				const value = await api.get<Project>(`${path}${query}`, requestToken, requestAdminProjectId);
				if (!owns()) return;
				if (value.id !== requestProjectId || value.domain_id !== requestDomain) throw new Error('foreign domain');
				project = value;
				loading = false;
				try {
					const value = await api.get<Member[]>(`${path}/members${query}`, requestToken, requestAdminProjectId);
					if (owns()) members = value;
				} catch (memberError) {
					if (owns()) membersError = memberError instanceof ApiError ? memberError.message : t('projectDetail.membersFailed');
				}
			} catch (loadError) {
				if (owns()) {
					error = loadError instanceof ApiError ? loadError.message : t('projectDetail.loadFailed');
					if ((loadError instanceof ApiError && [401, 403, 404].includes(loadError.status)) || (loadError instanceof Error && loadError.message === 'foreign domain')) { project = null; members = []; }
				}
			} finally {
				if (owns()) { loading = false; membersLoading = false; }
			}
		})();
		return () => { live = false; loadGeneration += 1; };
	});
	const tableSearchId = $props.id();
	let tableSearch = $state('');
	const tableView = createTableView<(typeof members)[number]>({ rows: () => members, locale: () => intlLocale(), search: () => tableSearch, columns: () => [{ key: 'user', label: t('projectDetail.user'), value: row => row.user_name }, { key: 'role', label: t('projectDetail.role'), value: row => row.role_name }, { key: 'type', label: t('projectDetail.type'), value: row => row.type === 'group' ? t('projectDetail.groupType') : row.type == null || row.type === 'user' ? t('projectDetail.userType') : row.type }] });
</script>

{#if loading && !project}
	<PageShell>
		<LoadingState variant="surface" />
	</PageShell>
{:else if error && !project}
	<PageShell class="text-state-danger-text text-sm">{error}</PageShell>
{:else if project}
	<PageShell class="flex flex-col gap-6">
		{#if error}<Alert tone="danger">{error}</Alert>{/if}
		{#if loading}<LoadingState variant="inline" label={t('state.loading')} />{/if}
		<PageHeader breadcrumb={t('projectDetail.breadcrumb')} title={project.name} subtitle={t('projectDetail.subtitle')}>
			{#snippet actions()}
				<a href={`/admin/projects?domain_id=${encodeURIComponent(domainId)}`} class="text-sm text-ink-2 hover:text-ink-0 transition-colors">{t('projectDetail.back')}</a>
			{/snippet}
		</PageHeader>

		<!-- 탭 -->
		<div class="flex gap-1 border-b border-line">
			{#each [['overview', 'projectDetail.overviewTab'], ['members', 'projectDetail.membersTab'], ['activity', 'projectDetail.activityTab']] as [key, labelKey]}
				<button
					onclick={() => tab = key as typeof tab}
					class="px-4 py-2 text-sm font-medium transition-colors border-b-2 -mb-px {tab === key ? 'text-warm-text border-action-warm' : 'text-ink-2 border-transparent hover:text-ink-0'}"
				>
					{t(labelKey as 'projectDetail.overviewTab' | 'projectDetail.membersTab' | 'projectDetail.activityTab')}
				</button>
			{/each}
		</div>

		<!-- 개요 탭 -->
		{#if tab === 'overview'}
			<div class="bg-surface-base border border-line rounded-lg p-5 space-y-4">
				<dl class="grid grid-cols-1 sm:grid-cols-2 gap-4">
					<div>
						<dt class="text-xs text-ink-2 uppercase tracking-wide mb-1">{t('projectDetail.projectId')}</dt>
						<dd class="font-mono text-sm text-ink-2">{project.id}</dd>
					</div>
					<div>
						<dt class="text-xs text-ink-2 uppercase tracking-wide mb-1">{t('form.name')}</dt>
						<dd class="text-sm text-ink-0">{project.name}</dd>
					</div>
					<div>
						<dt class="text-xs text-ink-2 uppercase tracking-wide mb-1">{t('form.description')}</dt>
						<dd class="text-sm text-ink-2">{project.description || '—'}</dd>
					</div>
					<div>
						<dt class="text-xs text-ink-2 uppercase tracking-wide mb-1">{t('projectDetail.status')}</dt>
						<dd>
							<span class="inline-flex items-center gap-1.5 text-xs px-2 py-0.5 rounded-full font-medium {project.enabled ? 'bg-state-success/10 text-state-success-text' : 'bg-surface-sunken text-ink-2'}">
								{project.enabled ? t('state.enabled') : t('state.disabled')}
							</span>
						</dd>
					</div>
					{#if project.created_at}
						<div>
							<dt class="text-xs text-ink-2 uppercase tracking-wide mb-1">{t('projectDetail.createdAt')}</dt>
							<dd class="text-sm text-ink-2">{new Date(project.created_at).toLocaleString(intlLocale())}</dd>
						</div>
					{/if}
					{#if project.domain_id}
						<div>
							<dt class="text-xs text-ink-2 uppercase tracking-wide mb-1">{t('projectDetail.domainId')}</dt>
							<dd class="font-mono text-sm text-ink-2">{project.domain_id}</dd>
						</div>
					{/if}
				</dl>
			</div>
		{/if}

		<!-- 멤버 탭 -->
		{#if tab === 'members'}
			<div class="bg-surface-base border border-line rounded-lg overflow-hidden">
				{#if membersLoading}
					<div class="text-ink-2 text-sm py-8 text-center"><LoadingState variant="section" label={t('projectDetail.membersLoading')} /></div>
				{:else if membersError}
					<div class="text-[var(--color-state-danger)] text-sm py-8 text-center">{membersError}</div>
				{:else}
          <RegexSearch id={tableSearchId} bind:value={tableSearch} /><TableViewControls view={tableView} />
<ResponsiveTable>
            {#snippet cards()}
              {#each tableView.rows as m (m.user_id + m.role_id)}
                <CompactResourceCard>
                  <strong class="break-words text-sm">{m.user_name}</strong>
                  <dl class="space-y-1 text-xs"><div><dt class="text-ink-2">{t('projectDetail.role')}</dt><dd>{m.role_name}</dd></div><div><dt class="text-ink-2">{t('projectDetail.type')}</dt><dd>{m.type === 'group' ? t('projectDetail.groupType') : m.type == null || m.type === 'user' ? t('projectDetail.userType') : m.type}</dd></div></dl>
                </CompactResourceCard>
              {/each}
            {/snippet}
					<table class="w-full text-sm">
						<thead class="bg-surface-base/60 text-ink-2 text-xs uppercase tracking-wide">
							<tr>
<TableColumnHeader view={tableView} columnKey="user" />
<TableColumnHeader view={tableView} columnKey="role" />
<TableColumnHeader view={tableView} columnKey="type" />
							</tr>
						</thead>
						<tbody class="divide-y divide-line">
							{#each tableView.rows as m (m.user_id + m.role_id)}
								<tr class="hover:bg-surface-sunken/40">
									<td class="px-4 py-3 text-ink-0">{m.user_name}</td>
									<td class="px-4 py-3 text-ink-2">{m.role_name}</td>
									<td class="px-4 py-3 text-ink-2">{m.type === 'group' ? t('projectDetail.groupType') : m.type == null || m.type === 'user' ? t('projectDetail.userType') : m.type}</td>
								</tr>
							{/each}
						</tbody>
					</table>
          </ResponsiveTable>
				{/if}
			</div>
		{/if}

		<!-- 활동 탭 -->
		{#if tab === 'activity'}
			<ActivityLogTable
				endpoint={`/api/v1/admin/projects/${encodeURIComponent(project.id)}/activity?domain_id=${encodeURIComponent(domainId)}`}
				storageKey="admin-project-activity"
				showUser
			/>
		{/if}
	</PageShell>
{/if}
