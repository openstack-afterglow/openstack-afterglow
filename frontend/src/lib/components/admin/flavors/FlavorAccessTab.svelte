<script lang="ts">
	import { t } from '$lib/i18n/ns/admin-compute';
	import ActivityIndicator from '$lib/components/ui/ActivityIndicator.svelte';
	import { auth } from '$lib/stores/auth';
	import { api, ApiError } from '$lib/api/client';
	import { toast } from '$lib/stores/toast';
	import { Alert, ToggleGroup, Button } from '$lib/components/ui';
	import { onDestroy, untrack } from 'svelte';
	import { get } from 'svelte/store';
	import AdminProjectPicker from '$lib/components/admin/domains/AdminProjectPicker.svelte';

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
		domain_id?: string;
		domain_name?: string;
	}

	let { flavor }: { flavor: Flavor } = $props();


	let accessList = $state<FlavorAccess[]>([]);
	let accessLoading = $state(false);
	let accessError = $state('');
	let addingId = $state<string | null>(null);
	let removingId = $state<string | null>(null);
	let domainFilter = $state('');
	let selectedProject = $state('');
	let authorityRevision = $state(0);
	let authorityKey = '';
	let disposed = false;
	const unsubscribe = auth.subscribe(state => {
		const next = JSON.stringify([state.token, state.sessionId, state.userId, state.identityDomainId, state.domainId, state.projectId, state.isSystemAdmin]);
		if (next === authorityKey) return;
		authorityKey = next; ++authorityRevision;
		domainFilter = ''; selectedProject = ''; accessList = [];
	});
	onDestroy(() => { disposed = true; ++authorityRevision; unsubscribe(); });
	function capture() {
		const revision = authorityRevision, target = flavor.id, state = get(auth);
		return { token: state.token ?? undefined, projectId: state.projectId ?? undefined,
			current: () => !disposed && revision === authorityRevision && target === flavor.id };
	}
	let frontendVisible = $state(true);
	let visibilitySaving = $state(false);
	const accessedProjectIds = $derived(accessList.map(access => access.project_id));
	$effect(() => {
		void flavor.id; void authorityRevision;
		untrack(() => {
			accessList = []; accessError = ''; selectedProject = ''; domainFilter = '';
			addingId = null; removingId = null;
			visibilitySaving = false;
			void loadAccess();
			frontendVisible = flavor.frontend_visible ?? (flavor.extra_specs?.['afterglow:frontend_visible']?.toLowerCase() !== 'false');
		});
	});

	async function loadAccess() {
		const owner = capture();
		accessLoading = true;
		try {
			const rows = await api.get<FlavorAccess[]>(`/api/v1/admin/flavors/${flavor.id}/access`, owner.token, owner.projectId);
			if (owner.current()) accessList = rows;
		} catch {
			if (owner.current()) { accessList = []; accessError = t('flavors.access.addFailed'); }
		} finally {
			if (owner.current()) accessLoading = false;
		}
	}

	async function addAccess(pid: string) {
		if (!pid || addingId || pid !== selectedProject || accessedProjectIds.includes(pid) || !$auth.token || !$auth.isSystemAdmin) return;
		const owner = capture();
		accessError = '';
		addingId = pid;
		try {
			await api.post(
				`/api/v1/admin/flavors/${flavor.id}/access`,
				{ project_id: pid },
				owner.token,
				owner.projectId,
			);
			if (!owner.current()) return;
			selectedProject = '';
			toast.success(t('flavors.access.added'));
			await loadAccess();
		} catch (e) {
			if (!owner.current()) return;
			const msg = e instanceof ApiError ? e.message : t('flavors.access.addFailed');
			accessError = msg;
			toast.error(msg);
		} finally {
			if (owner.current()) addingId = null;
		}
	}

	async function removeAccess(pid: string) {
		if (removingId || !accessedProjectIds.includes(pid)) return;
		const owner = capture();
		removingId = pid;
		try {
			await api.delete(
				`/api/v1/admin/flavors/${flavor.id}/access/${pid}`,
				owner.token,
				owner.projectId,
			);
			if (!owner.current()) return;
			await loadAccess();
		} catch {
			if (owner.current()) accessError = t('flavors.access.removeFailed');
		} finally {
			if (owner.current()) removingId = null;
		}
	}

	async function setFrontendVisibility(visible: boolean) {
		if (frontendVisible === visible) return;
		const owner = capture();
		visibilitySaving = true;
		try {
			await api.put(
				`/api/v1/admin/flavors/${flavor.id}/frontend-visibility`,
				{ visible },
				owner.token,
				owner.projectId,
			);
			if (!owner.current()) return;
			frontendVisible = visible;
			flavor.frontend_visible = visible;
			flavor.extra_specs = {
				...flavor.extra_specs,
				'afterglow:frontend_visible': visible ? 'true' : 'false',
			};
			toast.success(visible ? t('flavors.access.visibleNotice') : t('flavors.access.hiddenNotice'));
		} catch (e) {
			if (!owner.current()) return;
			toast.error(e instanceof ApiError ? e.message : t('flavors.access.visibilityFailed'));
		} finally {
			if (owner.current()) visibilitySaving = false;
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
		<Alert tone="danger" class="mb-3">{accessError}</Alert>
	{/if}

	<p class="mb-3 text-xs text-ink-2">{t('flavors.access.manualHelp')}</p>
	<div class="mb-4 space-y-3">
		{#key `${authorityRevision}:${flavor.id}`}
			<AdminProjectPicker domainId={domainFilter} projectId={selectedProject} excludedProjectIds={accessedProjectIds} emptyProjectLabel={t('flavors.access.addProject')} disabled={!!addingId || accessLoading} onchange={(domainId, projectId) => { domainFilter = domainId; selectedProject = projectId; }} />
		{/key}
		<Button variant="secondary" disabled={!selectedProject || !!addingId || accessLoading} onclick={() => addAccess(selectedProject)}>{addingId ? t('flavors.access.adding') : t('flavors.access.add')}</Button>
	</div>

	<div class="text-sm text-ink-2 mb-2">{t('flavors.access.projects')}</div>
	{#if accessLoading}
		<ActivityIndicator size="sm" label={t('flavors.loading')} />
	{:else if accessList.length === 0 && !accessError}
		<div class="text-ink-2 text-sm">{t('flavors.access.empty')}</div>
	{:else}
		<div class="space-y-2">
			{#each accessList as a (a.project_id)}
				<div class="flex flex-wrap lg:flex-nowrap items-center justify-between gap-2 bg-surface-base border border-line rounded-lg px-3 py-2">
					<div class="min-w-0 break-all">
						<div class="text-xs text-ink-1">{a.domain_name || a.domain_id || '—'} / {a.project_name || a.project_id}</div>
						<div class="text-xs text-ink-2 font-mono">{a.domain_id || '—'} / {a.project_id}</div>
					</div>
					<button onclick={() => removeAccess(a.project_id)} disabled={removingId === a.project_id} class="min-h-11 lg:min-h-0 text-state-danger-text hover:text-state-danger-text/90 text-xs">
						{#if removingId === a.project_id}
							<span class="inline-flex items-center gap-2" role="status"><ActivityIndicator size="xs" tone="ink" /><span>{t('flavors.access.removing')}</span></span>
						{:else}{t('flavors.access.remove')}{/if}
					</button>
				</div>
			{/each}
		</div>
	{/if}
{/if}
