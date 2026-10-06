<script lang="ts">
	import ActivityIndicator from '$lib/components/ui/ActivityIndicator.svelte';
	import { page } from '$app/stores';
	import { auth } from '$lib/stores/auth';
	import { api, ApiError } from '$lib/api/client';
	import LoadingSkeleton from '$lib/components/LoadingSkeleton.svelte';
	import PageHeader from '$lib/components/ui/PageHeader.svelte';
	import ActivityLogTable from '$lib/components/admin/ActivityLogTable.svelte';

	import type { Project, ProjectMember as Member } from '$lib/types/project';
	import { t } from '$lib/i18n/ns/admin-identity';
	import { intlLocale } from '$lib/i18n/runtime.svelte';

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

	$effect(() => {
		const requestProjectId = projectId;
		const requestToken = token;
		const requestAdminProjectId = adminProjectId;
		if (!requestProjectId) return;
		const generation = ++loadGeneration;
		loading = true;
		membersLoading = true;
		error = '';
		membersError = '';
		const projectPromise = api.get<Project>(
			`/api/v1/admin/projects/${requestProjectId}`,
			requestToken,
			requestAdminProjectId,
		);
		const membersPromise = api.get<Member[]>(
			`/api/v1/admin/projects/${requestProjectId}/members`,
			requestToken,
			requestAdminProjectId,
		).then((value) => {
			if (generation === loadGeneration && projectId === requestProjectId) members = value;
		}).catch((memberError) => {
			if (generation === loadGeneration && projectId === requestProjectId) {
				members = [];
				membersError = memberError instanceof ApiError ? memberError.message : t('projectDetail.membersFailed');
			}
		}).finally(() => {
			if (generation === loadGeneration && projectId === requestProjectId) membersLoading = false;
		});
		void projectPromise.then((value) => {
			if (generation !== loadGeneration || projectId !== requestProjectId) return;
			project = value;
			error = '';
		}).catch((loadError) => {
			if (generation === loadGeneration && projectId === requestProjectId) {
				project = null;
				error = loadError instanceof ApiError ? loadError.message : t('projectDetail.loadFailed');
			}
		}).finally(() => {
			if (generation === loadGeneration && projectId === requestProjectId) loading = false;
		});
		void membersPromise;
	});
</script>

{#if loading}
	<div class="p-6">
		<LoadingSkeleton rows={4} />
	</div>
{:else if error}
	<div class="p-6 text-red-400 text-sm">{error}</div>
{:else if project}
	<div class="flex flex-col gap-6 p-6">
		<PageHeader breadcrumb={t('projectDetail.breadcrumb')} title={project.name} subtitle={t('projectDetail.subtitle')}>
			{#snippet actions()}
				<a href="/admin/projects" class="text-sm text-ink-2 hover:text-ink-0 transition-colors">{t('projectDetail.back')}</a>
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
							<span class="inline-flex items-center gap-1.5 text-xs px-2 py-0.5 rounded-full font-medium {project.enabled ? 'bg-green-900/40 text-green-400' : 'bg-surface-sunken text-ink-2'}">
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
					<div class="text-ink-2 text-sm py-8 text-center"><ActivityIndicator size="sm" label={t('projectDetail.membersLoading')} /></div>
				{:else if membersError}
					<div class="text-[var(--color-state-danger)] text-sm py-8 text-center">{membersError}</div>
				{:else if members.length === 0}
					<div class="text-ink-2 text-sm py-8 text-center">{t('projectDetail.noMembers')}</div>
				{:else}
					<table class="w-full text-sm">
						<thead class="bg-surface-base/60 text-ink-2 text-xs uppercase tracking-wide">
							<tr>
								<th class="px-4 py-3 text-left font-medium">{t('projectDetail.user')}</th>
								<th class="px-4 py-3 text-left font-medium">{t('projectDetail.role')}</th>
								<th class="px-4 py-3 text-left font-medium">{t('projectDetail.type')}</th>
							</tr>
						</thead>
						<tbody class="divide-y divide-line">
							{#each members as m (m.user_id + m.role_id)}
								<tr class="hover:bg-surface-sunken/40">
									<td class="px-4 py-3 text-ink-0">{m.user_name}</td>
									<td class="px-4 py-3 text-ink-2">{m.role_name}</td>
									<td class="px-4 py-3 text-ink-2">{m.type === 'group' ? t('projectDetail.groupType') : m.type == null || m.type === 'user' ? t('projectDetail.userType') : m.type}</td>
								</tr>
							{/each}
						</tbody>
					</table>
				{/if}
			</div>
		{/if}

		<!-- 활동 탭 -->
		{#if tab === 'activity'}
			<ActivityLogTable
				endpoint={`/api/v1/admin/projects/${projectId}/activity`}
				storageKey="admin-project-activity"
				showUser
			/>
		{/if}
	</div>
{/if}
