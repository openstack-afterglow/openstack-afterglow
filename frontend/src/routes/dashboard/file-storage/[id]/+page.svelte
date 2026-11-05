<script lang="ts">
	import { t as tl } from '$lib/i18n/ns/common';
	import PageShell from '$lib/components/ui/PageShell.svelte';
	import { t } from '$lib/i18n/ns/file-storage';
	import { confirmDialog } from '$lib/stores/confirm.svelte';
	import { onDestroy, untrack } from 'svelte';
	import { derived } from 'svelte/store';
	import { page } from '$app/stores';
	import { goto } from '$app/navigation';
	import { auth } from '$lib/stores/auth';
	import { api, ApiError } from '$lib/api/client';
	import LoadingState from '$lib/components/ui/LoadingState.svelte';
	import { createAutoRefresh } from '$lib/utils/autoRefresh.svelte';
	import { createCoalescedRefresh, type CoalescedRefresh } from '$lib/utils/coalescedRefresh';
	import type { FileStorage, AccessRule } from '$lib/types/fileStorage';
	import FileStorageHeader from '$lib/components/dashboard/file-storage/[id]/FileStorageHeader.svelte';
	import FileStorageInfoCard from '$lib/components/dashboard/file-storage/[id]/FileStorageInfoCard.svelte';
	import ExportLocationList from '$lib/components/dashboard/file-storage/[id]/ExportLocationList.svelte';
	import AccessRulesSection from '$lib/components/dashboard/file-storage/[id]/AccessRulesSection.svelte';
	import FileStorageMetadata from '$lib/components/dashboard/file-storage/[id]/FileStorageMetadata.svelte';
	import { toast } from '$lib/stores/toast';
	import { createDetailReadScope, type DetailReadScope } from '$lib/utils/detailReadScope';
	import { beginExperienceAction, beginExperienceLoad, experienceApplied, experienceDiscarded, experienceRequest, experienceState, type ExperienceContext } from '$lib/utils/experience';

	let fileStorage = $state<FileStorage | null>(null);
	let loading = $state(true);
	let refreshing = $state(false);
	let error = $state('');
	let deleting = $state(false);
	let accessRules = $state<AccessRule[]>([]);
	let accessLoading = $state(false);
	let accessError = $state('');
	let addingRule = $state(false);
	let ruleError = $state('');
	let revokingId = $state<string | null>(null);

	const readScope = createDetailReadScope(derived(page, value => value.params.id ?? ''));
	let activeScope = $state.raw<DetailReadScope | null>(null);
	let refresh: CoalescedRefresh;
	let live = true;
	let controller = new AbortController();
	let detailGeneration = 0;
	let accessGeneration = 0;
	let manualExperience: ExperienceContext | undefined;
	let forcedRefreshActive = false;
	const scopeCurrent = $derived(activeScope !== null && isCurrentScope(activeScope));
	function isCurrentScope(scope: DetailReadScope): boolean {
		return live && scope.ready && scope === activeScope && scope.revision === $readScope.revision;
	}
	onDestroy(() => { live = false; controller.abort(); refresh?.dispose(); });

	function createScopedRefresh(scope: DetailReadScope) {
		return createCoalescedRefresh(async (force) => {
			if (!isCurrentScope(scope)) return;
			forcedRefreshActive = force;
			const experience = (force ? manualExperience : undefined) ?? beginExperienceLoad('file_storage', 'resource.detail');
			if (force) manualExperience = undefined;
			try {
				const detail = fetchFileStorage(scope, force, experienceRequest(experience).context);
				await Promise.allSettled([
					detail,
					fetchAccessRules(scope, force, experienceRequest(experience).context, detail),
				]);
			} finally {
				if (isCurrentScope(scope)) forcedRefreshActive = false;
			}
		});
	}
	function manualRefresh() {
		if (!activeScope || !isCurrentScope(activeScope)) return;
		const experience = beginExperienceAction('file_storage', 'refresh', 'resource.detail');
		// A click joining an already forced cycle must not lend its context to a later poll.
		if (!forcedRefreshActive && !manualExperience) manualExperience = experience;
		return refresh.run(true);
	}
	const ar = createAutoRefresh(
		() => refresh?.run(false),
		{ storageKey: 'dashboard-file-storage-detail', defaultActive: true, defaultInterval: 15, intervalOptions: [10, 15, 30, 60], invokeOnMount: false }
	);

	$effect(() => {
		const revision = $readScope.revision;
		untrack(() => {
			if (activeScope?.revision === revision) return;
			refresh?.dispose();
			controller.abort(); controller = new AbortController();
			const scope = $readScope;
			activeScope = scope;
			fileStorage = null; accessRules = [];
			loading = true; accessLoading = true; refreshing = false;
			error = ''; ruleError = ''; accessError = '';
			addingRule = false; deleting = false; revokingId = null;
			manualExperience = undefined;
			forcedRefreshActive = false;
			detailGeneration += 1; accessGeneration += 1;
			refresh = createScopedRefresh(scope);
			if (isCurrentScope(scope)) void refresh.run(false);
		});
	});

	async function fetchFileStorage(scope: DetailReadScope, force: boolean, experience?: ExperienceContext) {
		const generation = ++detailGeneration;
		const current = () => isCurrentScope(scope) && generation === detailGeneration;
		if (fileStorage?.id === scope.id) refreshing = true;
		else loading = true;
		error = '';
		experienceState(experience, 'loading');
		try {
			const next = await api.withExperience(experience).get<FileStorage>(
				`/api/v1/file-storage/${scope.id}${force ? '?refresh=true' : ''}`, $auth.token ?? undefined,
				$auth.projectId ?? undefined, { signal: controller.signal, cache: 'no-store', replayOnUnauthorized: true }
			);
			if (!current()) { experienceDiscarded(experience, live ? 'stale' : 'unmounted'); return; }
			fileStorage = next;
		} catch (e) {
			if (!current()) { experienceDiscarded(experience, live ? 'stale' : 'unmounted'); return; }
			error = e instanceof ApiError ? t('detail.loadFailedWithMessage', { status: e.status, message: e.message }) : t('errors.server');
		} finally {
			if (current()) {
				loading = false; refreshing = false;
				experienceState(experience, error ? 'error' : fileStorage ? 'ready' : 'empty');
				void experienceApplied(experience, {}, current);
			}
		}
	}

	async function fetchAccessRules(scope: DetailReadScope, force: boolean, experience: ExperienceContext | undefined, detail: Promise<void>) {
		const generation = ++accessGeneration;
		const current = () => isCurrentScope(scope) && generation === accessGeneration;
		if (accessRules.length === 0) accessLoading = true;
		accessError = '';
		experienceState(experience, 'loading');
		try {
			const next = await api.withExperience(experience).get<AccessRule[]>(
				`/api/v1/file-storage/${scope.id}/access-rules${force ? '?refresh=true' : ''}`, $auth.token ?? undefined,
				$auth.projectId ?? undefined, { signal: controller.signal, cache: 'no-store', replayOnUnauthorized: true }
			);
			if (!current()) { experienceDiscarded(experience, live ? 'stale' : 'unmounted'); return; }
			accessRules = next;
		} catch (e) {
			if (!current()) { experienceDiscarded(experience, live ? 'stale' : 'unmounted'); return; }
			accessError = e instanceof ApiError ? t('detail.accessLoadFailedWithMessage', { status: e.status, message: e.message }) : t('detail.accessLoadFailed');
		} finally {
			if (current()) {
				accessLoading = false;
				experienceState(experience, accessError ? 'error' : accessRules.length ? 'ready' : 'empty');
				void detail.then(() => {
					if (!current()) { experienceDiscarded(experience, live ? 'stale' : 'unmounted'); return; }
					void experienceApplied(experience, {}, () => current() && !loading && !error && fileStorage !== null);
				});
			}
		}
	}

	async function handleAddRule(form: { access_to: string; access_level: string }): Promise<boolean> {
		const scope = activeScope;
		const storage = fileStorage;
		if (!scope || !storage || !isCurrentScope(scope) || !form.access_to.trim()) return false;
		addingRule = true; ruleError = '';
		const access_type = storage.share_proto === 'NFS' ? 'ip' : 'cephx';
		try {
			await api.post(`/api/v1/file-storage/${storage.id}/access-rules`,
				{ access_to: form.access_to.trim(), access_level: form.access_level, access_type },
				$auth.token ?? undefined, $auth.projectId ?? undefined);
			if (isCurrentScope(scope)) await refresh.invalidate();
			return true;
		} catch (e) {
			if (isCurrentScope(scope)) ruleError = e instanceof ApiError ? e.message : t('errors.create');
			return false;
		} finally { if (isCurrentScope(scope)) addingRule = false; }
	}

	async function handleRevokeRule(accessId: string): Promise<void> {
		const scope = activeScope;
		const storage = fileStorage;
		if (!scope || !storage || !isCurrentScope(scope) || !accessRules.some((rule) => rule.id === accessId)) return;
		if (!await confirmDialog(t('detail.revokeConfirm')) || !isCurrentScope(scope)) return;
		revokingId = accessId;
		try {
			await api.delete(`/api/v1/file-storage/${storage.id}/access-rules/${accessId}`, $auth.token ?? undefined, $auth.projectId ?? undefined);
			if (isCurrentScope(scope)) await refresh.invalidate();
		} catch (e) {
			if (isCurrentScope(scope)) toast.error(t('errors.deleteWithMessage', { message: e instanceof ApiError ? e.message : String(e) }));
		} finally { if (isCurrentScope(scope)) revokingId = null; }
	}

	async function deleteFileStorage() {
		const scope = activeScope;
		const storage = fileStorage;
		if (!scope || !storage || !isCurrentScope(scope)) return;
		if (!await confirmDialog(t('detail.deleteConfirm', { name: storage.name || storage.id })) || !isCurrentScope(scope)) return;
		deleting = true;
		try {
			await api.delete(`/api/v1/file-storage/${storage.id}`, $auth.token ?? undefined, $auth.projectId ?? undefined);
			if (isCurrentScope(scope)) goto('/dashboard');
		} catch (e) {
			if (isCurrentScope(scope)) toast.error(t('errors.deleteWithMessage', { message: e instanceof ApiError ? e.message : String(e) }));
		} finally { if (isCurrentScope(scope)) deleting = false; }
	}
</script>

<PageShell>
	<div class="mb-6">
		<a href="/dashboard" class="text-ink-2 hover:text-ink-1 text-sm transition-colors">{t('detail.back')}</a>
	</div>

	{#if scopeCurrent && error}
		<div role="alert" class="bg-red-900/40 border border-red-700 text-red-300 rounded-lg px-4 py-3 text-sm">{error}</div>
	{:else if loading || !scopeCurrent}
		<LoadingState variant="surface" label={tl('state.loadingNamed', { name: t('list.title') })} />
	{:else if fileStorage}
		<div class="motion-stagger">
			<FileStorageHeader
				{fileStorage} {deleting} loading={refreshing}
				bind:arActive={ar.active}
				bind:arInterval={ar.intervalSeconds}
				arIntervalOptions={ar.intervalOptions}
				onManualRefresh={manualRefresh}
				onDelete={deleteFileStorage}
			/>
			<FileStorageInfoCard {fileStorage} />
			<ExportLocationList paths={fileStorage.export_locations} />
			{#key activeScope?.revision}
				<AccessRulesSection
					shareProto={fileStorage.share_proto}
					{accessRules} {accessLoading} {accessError}
					onAdd={handleAddRule} onRevoke={handleRevokeRule}
					{addingRule} addError={ruleError} {revokingId}
				/>
			{/key}
			<FileStorageMetadata metadata={fileStorage.metadata} />
		</div>
	{:else}
		<p role="status">{t('list.empty')}</p>
	{/if}
</PageShell>
