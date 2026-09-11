<script lang="ts">
	import { untrack } from 'svelte';
	import { auth } from '$lib/stores/auth';
	import { api, ApiError } from '$lib/api/client';
	import { apiMut } from '$lib/api/mutations';
	import { confirmDialog } from '$lib/stores/confirm.svelte';
	import { createAutoRefresh } from '$lib/utils/autoRefresh.svelte';
	import { createCoalescedRefresh } from '$lib/utils/coalescedRefresh';
	import AutoRefreshControl from '$lib/components/AutoRefreshControl.svelte';
	import DetailHeader from '$lib/components/ui/DetailHeader.svelte';
	import StatusChip from '$lib/components/ui/StatusChip.svelte';
	import LoadingSkeleton from '$lib/components/LoadingSkeleton.svelte';
	import { formatIsoDateTime, formatNumber } from '$lib/utils/format';
	import type { AccessRule, ExportLocationDetail, FileStorage, FileStorageDeleteDiagnostic, FileStorageForceDeleteResult } from '$lib/types/fileStorage';

	let {
		fileStorageId,
		onClose,
		onDeleted,
	}: {
		fileStorageId: string;
		onClose: () => void;
		onDeleted: () => void | Promise<void>;
	} = $props();

	let fileStorage = $state<FileStorage | null>(null);
	let accessRules = $state<AccessRule[]>([]);
	let loading = $state(true);
	let accessLoading = $state(false);
	let error = $state('');
	let accessError = $state('');
	let deleting = $state(false);
	let copied = $state<string | null>(null);
	let deleteDiagnostic = $state<FileStorageDeleteDiagnostic | null>(null);
	let diagnosticLoading = $state(false);
	let diagnosticError = $state('');
	let forceDeleting = $state(false);

	const diagnosticStatuses = new Set(['error', 'error_deleting', 'deleting']);

	async function copyValue(id: string, value: string | null | undefined) {
		if (!value) return;
		await navigator.clipboard.writeText(value);
		copied = id;
		setTimeout(() => { copied = null; }, 1500);
	}

	function authArgs(): { token: string; projectId?: string } | null {
		const token = $auth.token;
		if (!token) return null;
		return { token, projectId: $auth.projectId ?? undefined };
	}

	async function fetchFileStorage(opts?: { refresh?: boolean }) {
		const args = authArgs();
		if (!args || !fileStorageId) return;
		if (fileStorage === null) loading = true;
		error = '';
		try {
			fileStorage = await api.get<FileStorage>(`/api/v1/file-storage/${fileStorageId}`, args.token, args.projectId, opts);
			if (diagnosticStatuses.has(fileStorage.status)) {
				await fetchDeleteDiagnostic({ refresh: opts?.refresh });
			} else {
				deleteDiagnostic = null;
				diagnosticError = '';
				diagnosticLoading = false;
			}
		} catch (e) {
			error = e instanceof ApiError ? `조회 실패 (${e.status}): ${e.message}` : '서버 오류';
			deleteDiagnostic = null;
		} finally {
			loading = false;
		}
	}

	async function fetchAccessRules(opts?: { refresh?: boolean }) {
		const args = authArgs();
		if (!args || !fileStorageId) return;
		if (accessRules.length === 0) accessLoading = true;
		accessError = '';
		try {
			accessRules = await api.get<AccessRule[]>(`/api/v1/file-storage/${fileStorageId}/access-rules`, args.token, args.projectId, opts);
		} catch (e) {
			accessRules = [];
			accessError = e instanceof ApiError
				? `접근 규칙 조회 실패 (${e.status}): ${e.message}`
				: '접근 규칙 조회 실패';
		} finally {
			accessLoading = false;
		}
	}

	async function fetchDeleteDiagnostic(opts?: { refresh?: boolean }) {
		const args = authArgs();
		if (!args || !fileStorageId) return;
		diagnosticLoading = true;
		diagnosticError = '';
		try {
			deleteDiagnostic = await api.get<FileStorageDeleteDiagnostic>(
				`/api/v1/admin/file-storage/${fileStorageId}/delete-diagnostics`,
				args.token,
				args.projectId,
				opts
			);
		} catch (e) {
			deleteDiagnostic = null;
			diagnosticError = e instanceof ApiError
				? `삭제 진단 실패 (${e.status}): ${e.message}`
				: '삭제 진단 실패';
		} finally {
			diagnosticLoading = false;
		}
	}

	async function fetchAll(opts?: { refresh?: boolean }) {
		await Promise.allSettled([fetchFileStorage(opts), fetchAccessRules(opts)]);
	}

	const refresh = createCoalescedRefresh((force) =>
		untrack(() => fetchAll(force ? { refresh: true } : undefined))
	);
	const ar = createAutoRefresh(() => refresh.run(false), {
		storageKey: 'admin-file-storage-detail',
		defaultActive: true,
		defaultInterval: 15,
		intervalOptions: [10, 15, 30, 60],
		invokeOnMount: false,
	});

	$effect(() => {
		if (fileStorageId && $auth.token) void refresh.run(false);
	});

	async function deleteFileStorage() {
		if (!fileStorage) return;
		const args = authArgs();
		if (!args) return;
		const confirmed = await confirmDialog(
			`파일 스토리지 "${fileStorage.name || fileStorage.id}"를 삭제하시겠습니까?\nManila share와 접근 규칙이 제거되며 복구할 수 없습니다.`
		);
		if (!confirmed) return;

		deleting = true;
		try {
			await apiMut('파일 스토리지 삭제', () => api.delete(`/api/v1/file-storage/${fileStorage!.id}`, args.token, args.projectId));
			await onDeleted();
			onClose();
		} catch {
			await fetchDeleteDiagnostic({ refresh: true });
			// apiMut already shows the error toast and rethrows.
		} finally {
			deleting = false;
		}
	}

	async function forceDeleteFileStorage() {
		if (!fileStorage || !deleteDiagnostic?.force_delete_available) return;
		const args = authArgs();
		if (!args) return;
		const confirmed = await confirmDialog(
			`파일 스토리지 "${fileStorage.name || fileStorage.id}"를 강제 삭제하시겠습니까?\n\n진단: ${deleteDiagnostic.summary}\n\n주의: Manila DB/backend 참조가 제거될 수 있으며, backend export/subvolume 부재 또는 일반 삭제 실패가 확인된 경우에만 실행해야 합니다.`
		);
		if (!confirmed) return;

		forceDeleting = true;
		try {
			await apiMut('파일 스토리지 강제 삭제', () =>
				api.post<FileStorageForceDeleteResult>(
					`/api/v1/admin/file-storage/${fileStorage!.id}/force-delete`,
					{},
					args.token,
					args.projectId
				)
			);
			await onDeleted();
			onClose();
		} catch {
			// apiMut already shows the error toast and rethrows.
		} finally {
			forceDeleting = false;
		}
	}

	function exportLocations(fs: FileStorage): ExportLocationDetail[] {
		if (fs.export_location_details?.length > 0) return fs.export_location_details;
		return (fs.export_locations ?? []).map((path) => ({ path, preferred: false, share_instance_id: null }));
	}

	function fieldValue(value: string | number | boolean | null | undefined): string {
		if (value === null || value === undefined || value === '') return '-';
		return String(value);
	}

	function rawJson(): string {
		return JSON.stringify({ file_storage: fileStorage, access_rules: accessRules, delete_diagnostic: deleteDiagnostic }, null, 2);
	}

	function shortAccessKey(key: string): string {
		return key.length > 18 ? `${key.slice(0, 8)}…${key.slice(-6)}` : key;
	}
</script>

<div class="p-6 space-y-6">
	<div class="flex items-center justify-between gap-3">
		<!-- 닫기 버튼은 SlidePanel 이 제공한다(`[data-slide-panel-close]`) -->
		<AutoRefreshControl
			bind:active={ar.active}
			bind:intervalSeconds={ar.intervalSeconds}
			intervalOptions={ar.intervalOptions}
			refreshing={loading || accessLoading}
			onManualRefresh={() => refresh.run(true)}
		/>
	</div>

	{#if loading && !fileStorage}
		<LoadingSkeleton variant="detail" rows={6} />
	{:else if error}
		<div class="bg-red-900/40 border border-red-700 text-red-300 rounded-lg px-4 py-3 text-sm">{error}</div>
	{:else if fileStorage}
		<DetailHeader title={fileStorage.name || fileStorage.id} status={fileStorage.status}>
			{#snippet meta()}
				<span class="px-1.5 py-0.5 bg-purple-900/40 text-purple-300 rounded text-xs">{fileStorage!.share_proto}</span>
			{/snippet}
			{#snippet actions()}
				<button
					type="button"
					onclick={deleteFileStorage}
					disabled={deleting}
					class="text-red-300 hover:text-red-200 disabled:text-ink-3 text-sm px-3 py-1.5 rounded border border-red-800 hover:border-red-600 disabled:border-line-2 transition-colors"
				>
					{deleting ? '삭제 중...' : '파일 스토리지 삭제'}
				</button>
			{/snippet}
		</DetailHeader>

		{#if deleteDiagnostic || diagnosticLoading || diagnosticError}
			<section class="bg-red-950/20 border border-red-900/60 rounded-lg p-5">
				<div class="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
					<div>
						<div class="flex flex-wrap items-center gap-2 mb-2">
							<h3 class="text-sm font-semibold text-ink-0">삭제 진단 및 복구 시나리오</h3>
							{#if deleteDiagnostic}
								<span class="px-2 py-0.5 rounded-full text-xs bg-surface-selected/40 text-action-warm border border-action-warm">
									confidence: {deleteDiagnostic.confidence}
								</span>
								<span class="px-2 py-0.5 rounded-full text-xs bg-surface-sunken text-ink-2 border border-line-2">
									{deleteDiagnostic.root_cause_code}
								</span>
							{/if}
							{#if diagnosticLoading}
								<span class="text-xs text-ink-3">진단 중...</span>
							{/if}
						</div>
						{#if diagnosticError}
							<div class="bg-red-900/30 border border-red-800 text-red-300 rounded px-3 py-2 text-sm">{diagnosticError}</div>
						{:else if deleteDiagnostic}
							<div class="space-y-3 text-sm">
								<p class="text-ink-1">{deleteDiagnostic.summary}</p>
								<div>
									<div class="text-xs font-semibold text-ink-3 mb-1">권장 조치</div>
									<p class="text-amber-100">{deleteDiagnostic.recommended_action}</p>
								</div>
								{#if deleteDiagnostic.evidence.length > 0}
									<div>
										<div class="text-xs font-semibold text-ink-3 mb-1">Evidence</div>
										<ul class="list-disc pl-5 space-y-1 text-ink-2">
											{#each deleteDiagnostic.evidence as item}
												<li class="break-all">{item}</li>
											{/each}
										</ul>
									</div>
								{/if}
								{#if deleteDiagnostic.share_instance_ids.length > 0}
									<div>
										<div class="text-xs font-semibold text-ink-3 mb-1">Share Instance IDs</div>
										<div class="flex flex-wrap gap-2">
											{#each deleteDiagnostic.share_instance_ids as instanceId}
												<span class="font-mono text-xs text-ink-2 bg-surface-canvas/60 border border-line rounded px-2 py-1">{instanceId}</span>
											{/each}
										</div>
									</div>
								{/if}
							</div>
						{/if}
					</div>
					<div class="flex shrink-0 flex-wrap gap-2">
						<button
							type="button"
							onclick={() => fetchDeleteDiagnostic({ refresh: true })}
							disabled={diagnosticLoading}
							class="text-action-warm hover:text-action-warm-hover disabled:text-ink-3 text-sm px-3 py-1.5 rounded border border-action-warm hover:border-action-warm disabled:border-line-2 transition-colors"
						>
							{diagnosticLoading ? '진단 중...' : '진단 다시 실행'}
						</button>
						{#if deleteDiagnostic?.force_delete_available}
							<button
								type="button"
								onclick={forceDeleteFileStorage}
								disabled={forceDeleting || deleting}
								class="text-red-100 bg-red-800/80 hover:bg-red-700 disabled:bg-surface-sunken disabled:text-ink-3 text-sm px-3 py-1.5 rounded border border-red-700 disabled:border-line-2 transition-colors"
							>
								{forceDeleting ? '강제 삭제 중...' : '강제 삭제'}
							</button>
						{/if}
					</div>
				</div>
			</section>
		{/if}

		<section class="bg-surface-base border border-line rounded-lg p-5">
			<h3 class="text-sm font-semibold text-ink-0 mb-4">기본 정보</h3>
			<div class="grid grid-cols-1 md:grid-cols-2 gap-x-8 gap-y-3 text-sm">
				<div><div class="text-ink-3 text-xs">ID</div><div class="font-mono text-ink-1 break-all">{fileStorage.id}</div></div>
				<div><div class="text-ink-3 text-xs">상태</div><div><StatusChip status={fileStorage.status} /></div></div>
				<div><div class="text-ink-3 text-xs">크기</div><div class="text-ink-1">{formatNumber(fileStorage.size)} GB</div></div>
				<div><div class="text-ink-3 text-xs">프로토콜</div><div class="text-ink-1">{fileStorage.share_proto}</div></div>
				<div><div class="text-ink-3 text-xs">프로젝트 ID</div><div class="font-mono text-ink-1 break-all">{fieldValue(fileStorage.project_id)}</div></div>
				<div><div class="text-ink-3 text-xs">생성자</div><div class="text-ink-1">{fileStorage.user_name ?? fileStorage.user_id ?? '-'}</div></div>
				<div><div class="text-ink-3 text-xs">생성일</div><div class="text-ink-1">{formatIsoDateTime(fileStorage.created_at)}</div></div>
				<div><div class="text-ink-3 text-xs">Share Type</div><div class="text-ink-1">{fieldValue(fileStorage.share_type_name)}</div></div>
				<div><div class="text-ink-3 text-xs">Share Network ID</div><div class="font-mono text-ink-1 break-all">{fieldValue(fileStorage.share_network_id)}</div></div>
				<div><div class="text-ink-3 text-xs">Availability Zone</div><div class="text-ink-1">{fieldValue(fileStorage.availability_zone)}</div></div>
				<div><div class="text-ink-3 text-xs">Access Rules Status</div><div class="text-ink-1">{fieldValue(fileStorage.access_rules_status)}</div></div>
				<div><div class="text-ink-3 text-xs">Host</div><div class="font-mono text-ink-1 break-all">{fieldValue(fileStorage.host)}</div></div>
				<div><div class="text-ink-3 text-xs">Public</div><div class="text-ink-1">{fieldValue(fileStorage.is_public)}</div></div>
				<div><div class="text-ink-3 text-xs">Progress</div><div class="text-ink-1">{fieldValue(fileStorage.progress)}</div></div>
			</div>
		</section>

		<section class="bg-surface-base border border-line rounded-lg p-5">
			<h3 class="text-sm font-semibold text-ink-0 mb-4">Export Locations</h3>
			{#if exportLocations(fileStorage).length > 0}
				<div class="space-y-3">
					{#each exportLocations(fileStorage) as loc, i}
						<div class="rounded border border-line bg-surface-canvas/40 p-3 text-sm">
							<div class="flex items-start justify-between gap-3">
								<div class="font-mono text-ink-1 break-all">{loc.path}</div>
								<button type="button" onclick={() => copyValue(`export-${i}`, loc.path)} class="text-xs text-action-warm hover:text-action-warm-hover shrink-0">{copied === `export-${i}` ? '복사됨' : '복사'}</button>
							</div>
							<div class="mt-2 flex flex-wrap gap-2 text-xs text-ink-3">
								<span>preferred: {fieldValue(loc.preferred)}</span>
								<span>share_instance_id: {fieldValue(loc.share_instance_id)}</span>
							</div>
						</div>
					{/each}
				</div>
			{:else}
				<div class="text-sm text-ink-3">Export location이 없습니다.</div>
			{/if}
		</section>

		<section class="bg-surface-base border border-line rounded-lg p-5">
			<div class="flex items-center justify-between gap-3 mb-4">
				<h3 class="text-sm font-semibold text-ink-0">접근 규칙 (읽기 전용)</h3>
				{#if accessLoading}<span class="text-xs text-ink-3">조회 중...</span>{/if}
			</div>
			{#if accessError}
				<div class="bg-red-900/30 border border-red-800 text-red-300 rounded px-3 py-2 text-sm mb-3">{accessError}</div>
			{/if}
			{#if accessRules.length > 0}
				<div class="overflow-x-auto">
					<table class="w-full text-sm">
						<thead>
							<tr class="border-b border-line text-ink-3 text-xs uppercase">
								<th class="text-left py-2 pr-4">Access To</th>
								<th class="text-left py-2 pr-4">Type</th>
								<th class="text-left py-2 pr-4">Level</th>
								<th class="text-left py-2 pr-4">State</th>
								<th class="text-left py-2">Access Key</th>
							</tr>
						</thead>
						<tbody>
							{#each accessRules as rule}
								<tr class="border-b border-line/50 last:border-0">
									<td class="py-2 pr-4 font-mono text-ink-1">{rule.access_to}</td>
									<td class="py-2 pr-4 text-ink-2">{rule.access_type ?? '-'}</td>
									<td class="py-2 pr-4 text-ink-2">{rule.access_level}</td>
									<td class="py-2 pr-4"><StatusChip status={rule.state} /></td>
									<td class="py-2 text-ink-3 font-mono">
										{#if rule.access_key}
											<span title={rule.access_key}>{shortAccessKey(rule.access_key)}</span>
											<button type="button" onclick={() => copyValue(`access-key-${rule.id}`, rule.access_key)} class="ml-2 text-xs text-action-warm hover:text-action-warm-hover">{copied === `access-key-${rule.id}` ? '복사됨' : '복사'}</button>
										{:else}
											-
										{/if}
									</td>
								</tr>
							{/each}
						</tbody>
					</table>
				</div>
			{:else if !accessLoading && !accessError}
				<div class="text-sm text-ink-3">접근 규칙이 없습니다.</div>
			{/if}
		</section>

		<section class="bg-surface-base border border-line rounded-lg p-5">
			<h3 class="text-sm font-semibold text-ink-0 mb-4">메타데이터</h3>
			{#if Object.keys(fileStorage.metadata ?? {}).length > 0}
				<div class="space-y-2 text-sm">
					{#each Object.entries(fileStorage.metadata ?? {}) as [key, value]}
						<div class="flex flex-col md:flex-row md:items-start gap-1 md:gap-3">
							<div class="md:w-48 shrink-0 text-ink-3 font-mono">{key}</div>
							<div class="text-ink-1 font-mono break-all">{value}</div>
						</div>
					{/each}
				</div>
			{:else}
				<div class="text-sm text-ink-3">메타데이터가 없습니다</div>
			{/if}
		</section>

		<section class="bg-surface-base border border-line rounded-lg p-5">
			<div class="flex items-center justify-between gap-3 mb-4">
				<h3 class="text-sm font-semibold text-ink-0">내부 데이터</h3>
				<button type="button" onclick={() => copyValue('raw-json', rawJson())} class="text-xs text-action-warm hover:text-action-warm-hover">{copied === 'raw-json' ? '복사됨' : 'Raw JSON 복사'}</button>
			</div>
			<pre class="max-h-[420px] overflow-auto rounded bg-surface-canvas border border-line p-3 text-xs text-ink-2 font-mono whitespace-pre-wrap">{rawJson()}</pre>
		</section>
	{/if}
</div>
