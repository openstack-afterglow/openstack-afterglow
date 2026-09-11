<script lang="ts">
	import { page } from '$app/stores';
	import { onMount } from 'svelte';
	import { auth, logoutInProgress, setAuth } from '$lib/stores/auth';
	import { api, ApiError } from '$lib/api/client';
	import { projectList, type Project } from '$lib/stores/projectList';
	import LoadingSpinner from './LoadingSpinner.svelte';
	import CreateProjectModal from './projects/CreateProjectModal.svelte';

	let { direction = 'up' }: { direction?: 'up' | 'down' } = $props();

	let switching = $state(false);
	let error = $state('');
	let isOpen = $state(false);
	let dropdownRef: HTMLDivElement | null = $state(null);
	let showCreateModal = $state(false);
	const mockupActive = $derived($page.data.mockup?.active === true);
	const showInitialLoading = $derived(
		$projectList.loading && !$projectList.loaded && $projectList.projects.length === 0,
	);

	async function selectProject(project: Project) {
		const token = $auth.token;
		if (!token || switching) return;
		if (project.id === $auth.projectId) { isOpen = false; return; }

		switching = true;
		try {
			const resp = await api.post<{
				token: string;
				refresh_token: string;
				expires_at: string;
				project_id: string;
				project_name: string;
				user_id: string;
				username: string;
				roles: string[];
				is_system_admin: boolean;
			}>('/api/v1/auth/token/project', { project_id: project.id }, token);

			if ($logoutInProgress || !$auth.token) return;

			setAuth({
				token: resp.token,
				refreshToken: resp.refresh_token,
				accessExpiresAt: resp.expires_at
					? Math.floor(new Date(resp.expires_at).getTime() / 1000)
					: null,
				projectId: resp.project_id,
				projectName: resp.project_name,
				roles: resp.roles ?? [],
				isSystemAdmin: !!resp.is_system_admin,
			});

			isOpen = false;

			// Default 네트워크 확인/생성 (fire-and-forget)
			api.post('/api/v1/networks/ensure-default', {}, resp.token, resp.project_id).catch(() => {});
		} catch (e) {
			error = e instanceof ApiError ? `프로젝트 전환 실패: ${e.message}` : '프로젝트 전환 실패';
		} finally {
			switching = false;
		}
	}

	function openCreateProject() {
		if (mockupActive) return;
		isOpen = false;
		showCreateModal = true;
	}

	function handleClickOutside(event: MouseEvent) {
		if (dropdownRef && !dropdownRef.contains(event.target as Node)) {
			isOpen = false;
		}
	}

	onMount(() => {
		document.addEventListener('click', handleClickOutside);
		return () => document.removeEventListener('click', handleClickOutside);
	});
</script>

<div class="relative" bind:this={dropdownRef}>
	<button
		onclick={() => {
			if (switching) return;
			isOpen = !isOpen;
			if (isOpen && $auth.token && $auth.userId) {
				void projectList.revalidate($auth.token, $auth.userId);
			}
		}}
		disabled={switching}
		class="flex items-center gap-2 px-3 py-1.5 bg-surface-sunken hover:bg-surface-selected disabled:bg-surface-sunken/50 rounded-lg text-sm transition-colors"
	>
		{#if showInitialLoading || switching}
			<LoadingSpinner size="sm" color="gray" />
		{:else}
			<svg class="w-4 h-4 text-ink-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
				<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-4 0H7m0 0H5m2 0v-2a2 2 0 012-2h2m4 0h2a2 2 0 012 2v2m-6-6a2 2 0 100-4 2 2 0 000 4z"></path>
			</svg>
		{/if}
		<span class="text-ink-2">{$auth.projectName || '프로젝트 선택'}</span>
		<svg class="w-4 h-4 text-ink-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
			<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"></path>
		</svg>
	</button>

	{#if isOpen && !showInitialLoading}
		<div class="fixed left-0 bottom-0 w-full sm:absolute sm:left-0 sm:w-64 max-h-[50vh] bg-surface-base border border-line-2 rounded-t-lg sm:rounded-lg shadow-[var(--shadow-restraint)] z-50 overflow-hidden {direction === 'down' ? 'sm:bottom-auto sm:top-full sm:mt-1' : 'sm:top-auto sm:bottom-full sm:mb-1'}">
			{#if error}
				<div class="p-3 text-sm text-red-400">{error}</div>
			{:else if $projectList.projects.length === 0}
				<div class="p-3 text-sm text-ink-3">접근 가능한 프로젝트가 없습니다</div>
			{:else}
				<div class="overflow-y-auto max-h-[calc(50vh-6rem)] sm:max-h-52">
					{#each $projectList.projects as project}
						<button
							onclick={() => selectProject(project)}
							disabled={switching}
							class="w-full text-left px-3 py-2 hover:bg-surface-sunken transition-colors disabled:opacity-50 disabled:cursor-not-allowed
								{project.id === $auth.projectId ? 'bg-surface-selected/30 border-l-2 border-action-warm' : ''}"
						>
							<div class="text-sm font-medium text-ink-0">{project.name}</div>
							{#if project.description}
								<div class="text-xs text-ink-3 truncate">{project.description}</div>
							{/if}
						</button>
					{/each}
				</div>
			{/if}
			{#if !mockupActive}
				<div class="border-t border-line">
					<button
						onclick={openCreateProject}
						class="w-full text-left px-3 py-2 text-xs text-ink-3 hover:text-ink-0 hover:bg-surface-sunken transition-colors flex items-center gap-1.5"
					>
						<svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 5v14M5 12h14"/></svg>
						새 프로젝트
					</button>
					<a
						href="/dashboard/project-settings"
						onclick={() => { isOpen = false; }}
						class="w-full text-left px-3 py-2 text-xs text-ink-3 hover:text-ink-0 hover:bg-surface-sunken transition-colors flex items-center gap-1.5"
					>
						<svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z"/><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"/></svg>
						프로젝트 설정
					</a>
				</div>
			{/if}
		</div>
	{/if}
</div>

{#if showCreateModal && !mockupActive}
	<CreateProjectModal
		onClose={() => (showCreateModal = false)}
		onSuccess={() => {
			showCreateModal = false;
			if ($auth.token && $auth.userId) {
				void projectList.refresh($auth.token, $auth.userId);
			}
		}}
	/>
{/if}
