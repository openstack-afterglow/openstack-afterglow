<script lang="ts">
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
	let error = $state('');
	let deleting = $state(false);
	let accessRules = $state<AccessRule[]>([]);
	let accessLoading = $state(false);
	let addingRule = $state(false);
	let ruleError = $state('');
	let revokingId = $state<string | null>(null);

	const refresh = createCoalescedRefresh(async (force) => {
		const id = $page.params.id ?? '';
		if (!id) return;
		await Promise.allSettled([
			fetchFileStorage(id, force ? { refresh: true } : undefined),
			fetchAccessRules(id, force ? { refresh: true } : undefined),
		]);
	});
	const ar = createAutoRefresh(
		() => refresh.run(false),
		{ storageKey: 'dashboard-file-storage-detail', defaultActive: true, defaultInterval: 15, intervalOptions: [10, 15, 30, 60], invokeOnMount: false }
	);

	$effect(() => {
		const id = $page.params.id;
		if (!id || !$auth.token) return;
		untrack(() => void refresh.run(false));
	});

	async function fetchFileStorage(id: string, opts?: { refresh?: boolean }) {
		loading = true; error = '';
		try {
			fileStorage = await api.get<FileStorage>(
				`/api/v1/file-storage/${id}`,
				$auth.token ?? undefined,
				$auth.projectId ?? undefined,
				opts
			);
		} catch (e) {
			error = e instanceof ApiError ? `조회 실패 (${e.status}): ${e.message}` : '서버 오류';
		} finally { loading = false; }
	}

	async function fetchAccessRules(id: string, opts?: { refresh?: boolean }) {
		accessLoading = true;
		try {
			accessRules = await api.get<AccessRule[]>(
				`/api/v1/file-storage/${id}/access-rules`,
				$auth.token ?? undefined,
				$auth.projectId ?? undefined,
				opts
			);
		} catch { accessRules = []; } finally { accessLoading = false; }
	}

	async function handleAddRule(form: { access_to: string; access_level: string }): Promise<boolean> {
		if (!fileStorage || !form.access_to.trim()) return false;
		addingRule = true; ruleError = '';
		const access_type = fileStorage.share_proto === 'NFS' ? 'ip' : 'cephx';
		try {
			await api.post(`/api/v1/file-storage/${fileStorage.id}/access-rules`,
				{ access_to: form.access_to.trim(), access_level: form.access_level, access_type },
				$auth.token ?? undefined, $auth.projectId ?? undefined);
			await refresh.invalidate();
			return true;
		} catch (e) { ruleError = e instanceof ApiError ? e.message : '생성 실패'; return false; }
		finally { addingRule = false; }
	}

	async function handleRevokeRule(accessId: string): Promise<void> {
		if (!fileStorage || !await confirmDialog('이 접근 규칙을 삭제하시겠습니까?')) return;
		revokingId = accessId;
		try {
			await api.delete(`/api/v1/file-storage/${fileStorage.id}/access-rules/${accessId}`, $auth.token ?? undefined, $auth.projectId ?? undefined);
			await refresh.invalidate();
		} catch (e) { toast.error('삭제 실패: ' + (e instanceof ApiError ? e.message : String(e))); }
		finally { revokingId = null; }
	}

	async function deleteFileStorage() {
		if (!fileStorage || !await confirmDialog(`파일 스토리지 "${fileStorage.name || fileStorage.id}"를 삭제하시겠습니까?`)) return;
		deleting = true;
		try {
			await api.delete(`/api/v1/file-storage/${fileStorage.id}`, $auth.token ?? undefined, $auth.projectId ?? undefined);
			goto('/dashboard');
		} catch (e) { toast.error('삭제 실패: ' + (e instanceof ApiError ? e.message : String(e))); }
		finally { deleting = false; }
	}
</script>

<div class="p-4 md:p-6 max-w-4xl mx-auto">
	<div class="mb-6">
		<a href="/dashboard" class="text-ink-2 hover:text-ink-1 text-sm transition-colors">← 대시보드</a>
	</div>

	{#if error}
		<div class="bg-red-900/40 border border-red-700 text-red-300 rounded-lg px-4 py-3 text-sm">{error}</div>
	{:else if loading}
		<LoadingSkeleton variant="card" rows={5} />
	{:else if fileStorage}
		<FileStorageHeader
			{fileStorage} {deleting} {loading}
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
	{/if}
</div>
