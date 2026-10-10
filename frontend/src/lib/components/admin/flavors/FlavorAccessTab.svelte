<script lang="ts">
	import { t } from '$lib/i18n/ns/admin-compute';
	import ActivityIndicator from '$lib/components/ui/ActivityIndicator.svelte';
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
	let removingId = $state<string | null>(null);
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
			toast.success(t('flavors.access.added'));
			await loadAccess();
		} catch (e) {
			const msg = e instanceof ApiError ? e.message : t('flavors.access.addFailed');
			accessError = msg;
			toast.error(msg);
		} finally {
			addingId = null;
		}
	}

	async function removeAccess(pid: string) {
		removingId = pid;
		try {
			await api.delete(
				`/api/v1/admin/flavors/${flavor.id}/access/${pid}`,
				token,
				projectId,
			);
			await loadAccess();
		} catch {
			accessError = t('flavors.access.removeFailed');
		} finally {
			removingId = null;
		}
	}

	async function setMode(nextMode: 'manual' | 'gpu_quota') {
		if (accessMode === nextMode) return;
		modeSaving = true;
		try {
			await api.put(`/api/v1/admin/flavors/${flavor.id}/access-mode`, { mode: nextMode }, token, projectId);
			accessMode = nextMode;
			flavor.extra_specs = { ...flavor.extra_specs, 'afterglow:access_mode': nextMode };
			toast.success(t('flavors.access.modeChanged'));
		} catch (e) {
			toast.error(e instanceof ApiError ? e.message : t('flavors.access.modeFailed'));
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
			toast.success(visible ? t('flavors.access.visibleNotice') : t('flavors.access.hiddenNotice'));
		} catch (e) {
			toast.error(e instanceof ApiError ? e.message : t('flavors.access.visibilityFailed'));
		} finally {
			visibilitySaving = false;
		}
	}
</script>

<div class="mb-4 rounded-lg border border-[var(--color-line)] bg-[var(--color-surface-sunken)] p-3">
	<div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
		<div class="min-w-0">
			<div class="text-xs font-semibold uppercase tracking-wide text-[var(--color-ink-1)]">
				{t('flavors.access.visibilityTitle')}
			</div>
			<p class="mt-1 text-xs leading-normal text-[var(--color-ink-2)]">
				{t('flavors.access.visibilityHelp')}
			</p>
		</div>
		<div class="w-full shrink-0 sm:w-auto">
			<ToggleGroup
				value={frontendVisible ? 'visible' : 'hidden'}
				options={[
					{ value: 'visible', label: t('flavors.access.showUsers'), disabled: visibilitySaving },
					{ value: 'hidden', label: t('flavors.access.hideUsers'), disabled: visibilitySaving },
				]}
				onchange={(value) => setFrontendVisibility(value === 'visible')}
				size="sm"
				ariaLabel={t('flavors.access.visibilityLabel')}
				fullWidth
			/>
			{#if visibilitySaving}
				<ActivityIndicator size="xs" label={t('flavors.access.visibilitySaving')} class="mt-2" />
			{/if}
		</div>
	</div>
</div>

{#if flavor.is_public}
	<div class="bg-surface-sunken/50 border border-line-2 text-ink-2 rounded-lg px-4 py-6 text-sm text-center">
		{t('flavors.access.publicHelp')}
	</div>
{:else}
	{#if accessError}
		<div class="bg-red-900/40 border border-red-700 text-red-300 rounded-lg px-3 py-2 text-xs mb-3">{accessError}</div>
	{/if}

	{#if flavor.is_gpu}
		<div class="mb-4 rounded-lg border border-[var(--color-line)] bg-[var(--color-surface-sunken)] p-3">
			<div class="text-xs font-semibold uppercase tracking-wide text-[var(--color-ink-1)] mb-1.5">{t('flavors.access.policy')}</div>
			<div class="flex gap-2">
				<button
					type="button"
					disabled={modeSaving}
					onclick={() => setMode('manual')}
					class="px-2.5 py-1 rounded text-xs transition-colors {accessMode === 'manual'
						? 'bg-[var(--color-accent)] text-[var(--color-surface-canvas)]'
						: 'bg-[var(--color-surface-base)] text-[var(--color-ink-2)] hover:text-[var(--color-ink-0)]'}"
				>
					{t('flavors.access.manualMode')}
				</button>
				<button
					type="button"
					disabled={modeSaving}
					onclick={() => setMode('gpu_quota')}
					class="px-2.5 py-1 rounded text-xs transition-colors {accessMode === 'gpu_quota'
						? 'bg-[var(--color-accent)] text-[var(--color-surface-canvas)]'
						: 'bg-[var(--color-surface-base)] text-[var(--color-ink-2)] hover:text-[var(--color-ink-0)]'}"
				>
					{t('flavors.access.quotaMode')}
				</button>
			</div>
			{#if modeSaving}
				<ActivityIndicator size="xs" label={t('flavors.access.modeSaving')} class="mt-2" />
			{/if}
			<p class="mt-2 text-xs text-[var(--color-ink-2)] leading-normal">
				{accessMode === 'gpu_quota'
					? t('flavors.access.quotaHelp')
					: t('flavors.access.manualHelp')}
			</p>
		</div>
	{/if}
	<div class="mb-4">
		<div class="text-sm text-ink-2 mb-2">{t('flavors.access.addProject')}</div>
		<div class="relative">
			<input
				type="text"
				placeholder={t('flavors.access.projectSearch')}
				bind:value={projectSearch}
				class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-1.5 text-ink-0 text-sm focus:outline-none focus:border-action-warm"
			/>
			{#if searchedProjects.length > 0}
				<div class="absolute z-10 left-0 right-0 mt-1 bg-surface-sunken border border-line-2 rounded-lg shadow-[var(--shadow-popover)] overflow-hidden">
					{#each searchedProjects as p}
						<div class="flex items-center justify-between px-3 py-2 hover:bg-surface-selected border-b border-line-2/50 last:border-0">
							<div>
								<span class="text-sm text-ink-0">{p.name}</span>
								<span class="text-xs text-ink-2 ml-2 font-mono">{p.id.slice(0, 12)}</span>
							</div>
							<button
								onclick={() => addAccess(p.id)}
								disabled={addingId === p.id}
								class="text-xs px-2 py-0.5 bg-action-warm hover:bg-action-warm-hover disabled:opacity-60 disabled:cursor-not-allowed text-action-on-warm rounded ml-2 flex items-center gap-1"
							>
								{#if addingId === p.id}
									<span class="inline-flex items-center gap-2" role="status"><ActivityIndicator size="xs" tone="ink" /><span>{t('flavors.access.adding')}</span></span>
								{:else}
									{t('flavors.access.add')}
								{/if}
							</button>
						</div>
					{/each}
				</div>
			{:else if projectSearch.trim().length > 0}
				<div class="absolute z-10 left-0 right-0 mt-1 bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-xs text-ink-2">
					{t('flavors.access.noMatchingProjects')}
				</div>
			{/if}
		</div>
	</div>

	<div class="text-sm text-ink-2 mb-2">{t('flavors.access.projects')}</div>
	{#if accessLoading}
		<ActivityIndicator size="sm" label={t('flavors.loading')} />
	{:else if accessList.length === 0}
		<div class="text-ink-2 text-sm">{t('flavors.access.empty')}</div>
	{:else}
		<div class="space-y-2">
			{#each accessList as a (a.project_id)}
				<div class="flex items-center justify-between bg-surface-base border border-line rounded-lg px-3 py-2">
					<div>
						<div class="text-xs text-ink-1">{a.project_name || a.project_id}</div>
						{#if a.project_name}
							<div class="text-xs text-ink-2 font-mono">{a.project_id.slice(0, 12)}</div>
						{/if}
					</div>
					<button onclick={() => removeAccess(a.project_id)} disabled={removingId === a.project_id} class="text-state-danger-text hover:text-state-danger-text/90 text-xs">
						{#if removingId === a.project_id}
							<span class="inline-flex items-center gap-2" role="status"><ActivityIndicator size="xs" tone="ink" /><span>{t('flavors.access.removing')}</span></span>
						{:else}{t('flavors.access.remove')}{/if}
					</button>
				</div>
			{/each}
		</div>
	{/if}
{/if}
