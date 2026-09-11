<script lang="ts">
	import { auth } from '$lib/stores/auth';
	import { api, ApiError } from '$lib/api/client';
	import { toast } from '$lib/stores/toast';
	import { ToggleGroup } from '$lib/components/ui';

	interface Flavor {
		id: string;
		name: string;
		vcpus: number;
		ram: number;
		disk: number;
		is_public: boolean;
		description: string | null;
		extra_specs: Record<string, string>;
		is_gpu: boolean;
		gpu_count: number;
		frontend_visible?: boolean;
	}
	interface FlavorAccess {
		flavor_id: string;
		project_id: string;
		project_name: string;
	}

	let { flavor }: { flavor: Flavor } = $props();

	const token = $derived($auth.token ?? undefined);
	const projectId = $derived($auth.projectId ?? undefined);

	let accessList = $state<FlavorAccess[]>([]);
	let accessLoading = $state(false);
	let accessError = $state('');
	let addingId = $state<string | null>(null);
	let projectSearch = $state('');
	let allProjects = $state<{ id: string; name: string }[]>([]);
	let accessMode = $state<'manual' | 'gpu_quota'>('manual');
	let modeSaving = $state(false);
	let frontendVisible = $state(true);
	let visibilitySaving = $state(false);
	const accessedProjectIds = $derived(new Set(accessList.map((a) => a.project_id)));
	const availableProjects = $derived(allProjects.filter((p) => !accessedProjectIds.has(p.id)));
	const searchedProjects = $derived(
		projectSearch.trim().length > 0
			? availableProjects
					.filter(
						(p) =>
							p.name.toLowerCase().includes(projectSearch.toLowerCase()) ||
							p.id.toLowerCase().includes(projectSearch.toLowerCase()),
					)
					.slice(0, 8)
			: [],
	);

	$effect(() => {
		if (flavor.id) {
			accessList = [];
			accessError = '';
			projectSearch = '';
			loadAccess();
			if (allProjects.length === 0) {
				api
					.get<{ id: string; name: string }[]>('/api/v1/admin/projects/names', token, projectId)
					.then((r) => (allProjects = r))
					.catch(() => (allProjects = []));
			}
		}
		accessMode = flavor.extra_specs?.['afterglow:access_mode'] === 'gpu_quota' ? 'gpu_quota' : 'manual';
		frontendVisible = flavor.frontend_visible
			?? (flavor.extra_specs?.['afterglow:frontend_visible']?.toLowerCase() !== 'false');
	});

	async function loadAccess() {
		accessLoading = true;
		try {
			accessList = await api.get<FlavorAccess[]>(
				`/api/v1/admin/flavors/${flavor.id}/access`,
				token,
				projectId,
			);
		} catch {
			accessList = [];
		} finally {
			accessLoading = false;
		}
	}

	async function addAccess(pid: string) {
		if (!pid || addingId === pid) return;
		accessError = '';
		addingId = pid;
		try {
			await api.post(
				`/api/v1/admin/flavors/${flavor.id}/access`,
				{ project_id: pid },
				token,
				projectId,
			);
			projectSearch = '';
			toast.success('접근 권한이 추가되었습니다');
			await loadAccess();
		} catch (e) {
			const msg = e instanceof ApiError ? e.message : '접근 권한 추가 실패';
			accessError = msg;
			toast.error(msg);
		} finally {
			addingId = null;
		}
	}

	async function removeAccess(pid: string) {
		try {
			await api.delete(
				`/api/v1/admin/flavors/${flavor.id}/access/${pid}`,
				token,
				projectId,
			);
			await loadAccess();
		} catch {
			accessError = '접근 권한 제거 실패';
		}
	}

	async function setMode(nextMode: 'manual' | 'gpu_quota') {
		if (accessMode === nextMode) return;
		modeSaving = true;
		try {
			await api.put(`/api/v1/admin/flavors/${flavor.id}/access-mode`, { mode: nextMode }, token, projectId);
			accessMode = nextMode;
			flavor.extra_specs = { ...flavor.extra_specs, 'afterglow:access_mode': nextMode };
			toast.success('접근 관리 모드가 변경되었습니다');
		} catch (e) {
			toast.error(e instanceof ApiError ? e.message : '모드 변경 실패');
		} finally {
			modeSaving = false;
		}
	}

	async function setFrontendVisibility(visible: boolean) {
		if (frontendVisible === visible) return;
		visibilitySaving = true;
		try {
			await api.put(
				`/api/v1/admin/flavors/${flavor.id}/frontend-visibility`,
				{ visible },
				token,
				projectId,
			);
			frontendVisible = visible;
			flavor.frontend_visible = visible;
			flavor.extra_specs = {
				...flavor.extra_specs,
				'afterglow:frontend_visible': visible ? 'true' : 'false',
			};
			toast.success(visible ? '사용자 Flavor 목록에 노출됩니다' : '사용자 Flavor 목록에서 숨겨집니다');
		} catch (e) {
			toast.error(e instanceof ApiError ? e.message : 'Afterglow 노출 설정 실패');
		} finally {
			visibilitySaving = false;
		}
	}
</script>

<div class="mb-4 rounded-lg border border-[var(--color-line)] bg-[var(--color-surface-sunken)] p-3">
	<div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
		<div class="min-w-0">
			<div class="text-xs font-semibold uppercase tracking-wide text-[var(--color-ink-1)]">
				Afterglow 사용자 노출
			</div>
			<p class="mt-1 text-[11px] leading-normal text-[var(--color-ink-2)]">
				숨기면 일반 사용자 VM·Resize·K3s Flavor 목록에서 제외됩니다. Nova Public/Private 및 Flavor Access는 변경되지 않습니다.
			</p>
		</div>
		<div class="w-full shrink-0 sm:w-auto">
			<ToggleGroup
				value={frontendVisible ? 'visible' : 'hidden'}
				options={[
					{ value: 'visible', label: '사용자에게 노출', disabled: visibilitySaving },
					{ value: 'hidden', label: '사용자에게 숨김', disabled: visibilitySaving },
				]}
				onchange={(value) => setFrontendVisibility(value === 'visible')}
				size="sm"
				ariaLabel="Afterglow 사용자 Flavor 노출"
				fullWidth
			/>
		</div>
	</div>
</div>

{#if flavor.is_public}
	<div class="bg-surface-sunken/50 border border-line-2 text-ink-2 rounded-lg px-4 py-6 text-sm text-center">
		Public Flavor는 모든 프로젝트에서 사용 가능하므로 접근 권한 설정이 필요하지 않습니다.
	</div>
{:else}
	{#if accessError}
		<div class="bg-red-900/40 border border-red-700 text-red-300 rounded-lg px-3 py-2 text-xs mb-3">{accessError}</div>
	{/if}

	{#if flavor.is_gpu}
		<div class="mb-4 rounded-lg border border-[var(--color-line)] bg-[var(--color-surface-sunken)] p-3">
			<div class="text-xs font-semibold uppercase tracking-wide text-[var(--color-ink-1)] mb-1.5">접근 권한 관리 정책</div>
			<div class="flex gap-2">
				<button
					type="button"
					disabled={modeSaving}
					onclick={() => setMode('manual')}
					class="px-2.5 py-1 rounded text-xs transition-colors {accessMode === 'manual'
						? 'bg-[var(--color-accent)] text-[var(--color-surface-canvas)]'
						: 'bg-[var(--color-surface-base)] text-[var(--color-ink-2)] hover:text-[var(--color-ink-0)]'}"
				>
					수동 관리 (manual)
				</button>
				<button
					type="button"
					disabled={modeSaving}
					onclick={() => setMode('gpu_quota')}
					class="px-2.5 py-1 rounded text-xs transition-colors {accessMode === 'gpu_quota'
						? 'bg-[var(--color-accent)] text-[var(--color-surface-canvas)]'
						: 'bg-[var(--color-surface-base)] text-[var(--color-ink-2)] hover:text-[var(--color-ink-0)]'}"
				>
					GPU Quota 연동 (gpu_quota)
				</button>
			</div>
			<p class="mt-2 text-[11px] text-[var(--color-ink-2)] leading-normal">
				{accessMode === 'gpu_quota'
					? '이 Flavor는 프로젝트의 GPU quota limit에 따라 접근 권한이 자동 조정됩니다. 아래 수동 추가는 예외 프로젝트에만 사용하세요.'
					: '관리자가 프로젝트를 개별적으로 추가하거나 제거합니다.'}
			</p>
		</div>
	{/if}
	<div class="mb-4">
		<div class="text-sm text-ink-2 mb-2">프로젝트 접근 추가</div>
		<div class="relative">
			<input
				type="text"
				placeholder="프로젝트 이름 또는 ID 검색..."
				bind:value={projectSearch}
				class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-1.5 text-ink-0 text-sm focus:outline-none focus:border-action-warm"
			/>
			{#if searchedProjects.length > 0}
				<div class="absolute z-10 left-0 right-0 mt-1 bg-surface-sunken border border-line-2 rounded-lg shadow-[var(--shadow-restraint)] overflow-hidden">
					{#each searchedProjects as p}
						<div class="flex items-center justify-between px-3 py-2 hover:bg-surface-selected border-b border-line-2/50 last:border-0">
							<div>
								<span class="text-sm text-ink-0">{p.name}</span>
								<span class="text-xs text-ink-3 ml-2 font-mono">{p.id.slice(0, 12)}</span>
							</div>
							<button
								onclick={() => addAccess(p.id)}
								disabled={addingId === p.id}
								class="text-xs px-2 py-0.5 bg-action-warm hover:bg-action-warm-hover disabled:opacity-60 disabled:cursor-not-allowed text-action-on-warm rounded ml-2 flex items-center gap-1"
							>
								{#if addingId === p.id}
									<svg class="w-3 h-3 animate-spin" fill="none" viewBox="0 0 24 24">
										<circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
										<path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z"></path>
									</svg>
									추가 중…
								{:else}
									추가
								{/if}
							</button>
						</div>
					{/each}
				</div>
			{:else if projectSearch.trim().length > 0}
				<div class="absolute z-10 left-0 right-0 mt-1 bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-xs text-ink-3">
					일치하는 프로젝트가 없습니다
				</div>
			{/if}
		</div>
	</div>

	<div class="text-sm text-ink-2 mb-2">접근 권한이 있는 프로젝트</div>
	{#if accessLoading}
		<div class="text-ink-3 text-sm">로딩 중...</div>
	{:else if accessList.length === 0}
		<div class="text-ink-3 text-sm">접근 권한이 없습니다</div>
	{:else}
		<div class="space-y-2">
			{#each accessList as a (a.project_id)}
				<div class="flex items-center justify-between bg-surface-base border border-line rounded-lg px-3 py-2">
					<div>
						<div class="text-xs text-ink-1">{a.project_name || a.project_id}</div>
						{#if a.project_name}
							<div class="text-xs text-ink-3 font-mono">{a.project_id.slice(0, 12)}</div>
						{/if}
					</div>
					<button onclick={() => removeAccess(a.project_id)} class="text-red-400 hover:text-red-300 text-xs">제거</button>
				</div>
			{/each}
		</div>
	{/if}
{/if}
