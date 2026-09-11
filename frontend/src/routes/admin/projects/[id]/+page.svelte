<script lang="ts">
	import { page } from '$app/stores';
	import { auth } from '$lib/stores/auth';
	import { api, ApiError } from '$lib/api/client';
	import LoadingSkeleton from '$lib/components/LoadingSkeleton.svelte';
	import PageHeader from '$lib/components/ui/PageHeader.svelte';
	import ActivityLogTable from '$lib/components/admin/ActivityLogTable.svelte';

	import type { Project, ProjectMember as Member } from '$lib/types/project';

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
				membersError = memberError instanceof ApiError ? memberError.message : '멤버 조회 실패';
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
				error = loadError instanceof ApiError ? loadError.message : '프로젝트 조회 실패';
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
		<PageHeader breadcrumb="Admin / 프로젝트" title={project.name} subtitle="프로젝트 상세">
			{#snippet actions()}
				<a href="/admin/projects" class="text-sm text-ink-2 hover:text-ink-0 transition-colors">← 목록</a>
			{/snippet}
		</PageHeader>

		<!-- 탭 -->
		<div class="flex gap-1 border-b border-line">
			{#each [['overview', '개요'], ['members', '멤버'], ['activity', '활동']] as [key, label]}
				<button
					onclick={() => tab = key as typeof tab}
					class="px-4 py-2 text-sm font-medium transition-colors border-b-2 -mb-px {tab === key ? 'text-action-warm border-action-warm' : 'text-ink-2 border-transparent hover:text-ink-0'}"
				>
					{label}
				</button>
			{/each}
		</div>

		<!-- 개요 탭 -->
		{#if tab === 'overview'}
			<div class="bg-surface-base border border-line rounded-lg p-5 space-y-4">
				<dl class="grid grid-cols-1 sm:grid-cols-2 gap-4">
					<div>
						<dt class="text-xs text-ink-3 uppercase tracking-wide mb-1">프로젝트 ID</dt>
						<dd class="font-mono text-sm text-ink-2">{project.id}</dd>
					</div>
					<div>
						<dt class="text-xs text-ink-3 uppercase tracking-wide mb-1">이름</dt>
						<dd class="text-sm text-ink-0">{project.name}</dd>
					</div>
					<div>
						<dt class="text-xs text-ink-3 uppercase tracking-wide mb-1">설명</dt>
						<dd class="text-sm text-ink-2">{project.description || '—'}</dd>
					</div>
					<div>
						<dt class="text-xs text-ink-3 uppercase tracking-wide mb-1">상태</dt>
						<dd>
							<span class="inline-flex items-center gap-1.5 text-xs px-2 py-0.5 rounded-full font-medium {project.enabled ? 'bg-green-900/40 text-green-400' : 'bg-surface-sunken text-ink-2'}">
								{project.enabled ? '활성' : '비활성'}
							</span>
						</dd>
					</div>
					{#if project.created_at}
						<div>
							<dt class="text-xs text-ink-3 uppercase tracking-wide mb-1">생성일</dt>
							<dd class="text-sm text-ink-2">{new Date(project.created_at).toLocaleString('ko-KR')}</dd>
						</div>
					{/if}
					{#if project.domain_id}
						<div>
							<dt class="text-xs text-ink-3 uppercase tracking-wide mb-1">도메인 ID</dt>
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
					<div class="text-[var(--color-ink-3)] text-sm py-8 text-center">멤버를 불러오는 중...</div>
				{:else if membersError}
					<div class="text-[var(--color-state-danger)] text-sm py-8 text-center">{membersError}</div>
				{:else if members.length === 0}
					<div class="text-ink-3 text-sm py-8 text-center">멤버 없음</div>
				{:else}
					<table class="w-full text-sm">
						<thead class="bg-surface-base/60 text-ink-2 text-xs uppercase tracking-wide">
							<tr>
								<th class="px-4 py-3 text-left font-medium">사용자</th>
								<th class="px-4 py-3 text-left font-medium">역할</th>
								<th class="px-4 py-3 text-left font-medium">유형</th>
							</tr>
						</thead>
						<tbody class="divide-y divide-line">
							{#each members as m (m.user_id + m.role_id)}
								<tr class="hover:bg-surface-sunken/40">
									<td class="px-4 py-3 text-ink-0">{m.user_name}</td>
									<td class="px-4 py-3 text-ink-2">{m.role_name}</td>
									<td class="px-4 py-3 text-ink-2">{m.type ?? 'user'}</td>
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
