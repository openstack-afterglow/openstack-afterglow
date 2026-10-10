<script lang="ts">
	import { t } from '$lib/i18n/ns/file-storage';
	import { confirmDialog } from '$lib/stores/confirm.svelte';
	import { untrack } from 'svelte';
	import { page } from '$app/stores';
	import { goto } from '$app/navigation';
	import { auth } from '$lib/stores/auth';
	import { api, ApiError } from '$lib/api/client';
	import LoadingSkeleton from '$lib/components/LoadingSkeleton.svelte';
	import { createAutoRefresh } from '$lib/utils/autoRefresh.svelte';
	import { createCoalescedRefresh } from '$lib/utils/coalescedRefresh';
	import type { FileStorage, AccessRule } from '$lib/types/fileStorage';
	import FileStorageHeader from '$lib/components/dashboard/file-storage/[id]/FileStorageHeader.svelte';
	import FileStorageInfoCard from '$lib/components/dashboard/file-storage/[id]/FileStorageInfoCard.svelte';
	import ExportLocationList from '$lib/components/dashboard/file-storage/[id]/ExportLocationList.svelte';
	import AccessRulesSection from '$lib/components/dashboard/file-storage/[id]/AccessRulesSection.svelte';
	import FileStorageMetadata from '$lib/components/dashboard/file-storage/[id]/FileStorageMetadata.svelte';
	import { toast } from '$lib/stores/toast';

	let fileStorage = $state<FileStorage | null>(null);
	let loading = $state(true);
	let refreshing = $state(false);
	let error = $state('');
	let deleting = $state(false);
	let accessRules = $state<AccessRule[]>([]);
	let accessLoading = $state(false);
	let addingRule = $state(false);
	let ruleError = $state('');
	let revokingId = $state<string | null>(null);

	interface DetailScope { id: string; token: string | null; projectId: string | null; }
	let activeScope = $state.raw<DetailScope | null>(null);
	let refresh: ReturnType<typeof createCoalescedRefresh>;
	const scopeCurrent = $derived(activeScope !== null && isCurrentScope(activeScope));

	function isCurrentScope(scope: DetailScope): boolean {
		return scope === activeScope && scope.id === $page.params.id
			&& scope.token === $auth.token && scope.projectId === $auth.projectId;
	}

	function createScopedRefresh(scope: DetailScope) {
		return createCoalescedRefresh(async (force) => {
			if (!scope.id || !scope.token || !isCurrentScope(scope)) return;
			await Promise.allSettled([
				fetchFileStorage(scope, force ? { refresh: true } : undefined),
				fetchAccessRules(scope, force ? { refresh: true } : undefined),
			]);
		});
	}
	const ar = createAutoRefresh(
		() => refresh.run(false),
		{ storageKey: 'dashboard-file-storage-detail', defaultActive: true, defaultInterval: 15, intervalOptions: [10, 15, 30, 60], invokeOnMount: false }
	);

	$effect(() => {
		const scope: DetailScope = {
			id: $page.params.id ?? '', token: $auth.token, projectId: $auth.projectId,
		};
		untrack(() => {
			activeScope = scope;
			fileStorage = null; accessRules = [];
			loading = true; accessLoading = true; refreshing = false;
			error = ''; ruleError = '';
			addingRule = false; deleting = false; revokingId = null;
			refresh = createScopedRefresh(scope);
			if (scope.id && scope.token) void refresh.run(false);
		});
		return () => { activeScope = null; };
	});

	async function fetchFileStorage(scope: DetailScope, opts?: { refresh?: boolean }) {
		// Preserve the loaded view only while refreshing the same resource and auth scope.
		if (fileStorage?.id === scope.id) refreshing = true;
		else loading = true;
		error = '';
		try {
			const next = await api.get<FileStorage>(
				`/api/v1/file-storage/${scope.id}`, scope.token ?? undefined,
				scope.projectId ?? undefined, opts
			);
			if (isCurrentScope(scope)) fileStorage = next;
		} catch (e) {
			if (isCurrentScope(scope)) error = e instanceof ApiError ? t('detail.loadFailedWithMessage', { status: e.status, message: e.message }) : t('errors.server');
		} finally {
			if (isCurrentScope(scope)) { loading = false; refreshing = false; }
		}
	}

	async function fetchAccessRules(scope: DetailScope, opts?: { refresh?: boolean }) {
		if (accessRules.length === 0) accessLoading = true;
		try {
			const next = await api.get<AccessRule[]>(
				`/api/v1/file-storage/${scope.id}/access-rules`, scope.token ?? undefined,
				scope.projectId ?? undefined, opts
			);
			if (isCurrentScope(scope)) accessRules = next;
		} catch {
			if (isCurrentScope(scope)) accessRules = [];
		} finally {
			if (isCurrentScope(scope)) accessLoading = false;
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
				scope.token ?? undefined, scope.projectId ?? undefined);
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
			await api.delete(`/api/v1/file-storage/${storage.id}/access-rules/${accessId}`, scope.token ?? undefined, scope.projectId ?? undefined);
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
			await api.delete(`/api/v1/file-storage/${storage.id}`, scope.token ?? undefined, scope.projectId ?? undefined);
			if (isCurrentScope(scope)) goto('/dashboard');
		} catch (e) {
			if (isCurrentScope(scope)) toast.error(t('errors.deleteWithMessage', { message: e instanceof ApiError ? e.message : String(e) }));
		} finally { if (isCurrentScope(scope)) deleting = false; }
	}
</script>

<div class="p-4 md:p-6 max-w-4xl mx-auto">
	<div class="mb-6">
		<a href="/dashboard" class="text-ink-2 hover:text-ink-1 text-sm transition-colors">{t('detail.back')}</a>
	</div>

	{#if scopeCurrent && error}
		<div class="bg-red-900/40 border border-red-700 text-red-300 rounded-lg px-4 py-3 text-sm">{error}</div>
	{:else if loading || !scopeCurrent}
		<LoadingSkeleton variant="card" rows={5} />
	{:else if fileStorage}
		<div class="motion-stagger">
			<FileStorageHeader
				{fileStorage} {deleting} loading={refreshing}
				bind:arActive={ar.active}
				bind:arInterval={ar.intervalSeconds}
				arIntervalOptions={ar.intervalOptions}
				onManualRefresh={() => refresh.run(true)}
				onDelete={deleteFileStorage}
			/>
			<FileStorageInfoCard {fileStorage} />
			<ExportLocationList paths={fileStorage.export_locations} />
			<AccessRulesSection
				shareProto={fileStorage.share_proto}
				{accessRules} {accessLoading}
				onAdd={handleAddRule} onRevoke={handleRevokeRule}
				{addingRule} addError={ruleError} {revokingId}
			/>
			<FileStorageMetadata metadata={fileStorage.metadata} />
		</div>
	{/if}
</div>
