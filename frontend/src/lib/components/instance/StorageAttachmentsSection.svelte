<script lang="ts">
	import { auth } from '$lib/stores/auth';
	import { api, ApiError } from '$lib/api/client';
	import { useInstanceDetailController } from '$lib/stores/instanceDetailController.svelte';
	import { get } from 'svelte/store';
	import { toast } from '$lib/stores/toast';

	const s = useInstanceDetailController();

	interface StorageAttachment {
		file_storage_id: string;
		name: string | null;
		share_proto: string | null;
		status: string;
	}

	interface FileStorage {
		id: string;
		name: string;
		status: string;
		share_proto: string;
	}

	let attachments = $state<StorageAttachment[]>([]);
	let fileStorages = $state<FileStorage[]>([]);
	let loading = $state(false);
	let attachmentError = $state('');
	let catalogStatus = $state<'idle' | 'loading' | 'loaded' | 'error'>('idle');
	let catalogError = $state('');
	let showForm = $state(false);
	let selectedStorageId = $state('');
	let mountPoint = $state('');
	let readOnly = $state(false);
	let attaching = $state(false);
	let detaching = $state<string | null>(null);
	let lastMountInfo = $state<{ mount_command: string; keyring_file: string | null } | null>(null);
	let copied = $state(false);
	let attachmentScopeGeneration = 0;
	let attachmentRequestId = 0;
	let catalogGeneration = 0;
	let catalogProjectId: string | null = null;
	let catalogPromise: Promise<void> | null = null;
	let observedInstanceId: string | null | undefined;
	let observedProjectId: string | null | undefined;

	interface StorageScope {
		instanceId: string;
		projectId: string;
	}

	function tok() { return get(auth).token ?? undefined; }
	function currentScope(): StorageScope | null {
		const instanceId = s.instanceId;
		const projectId = s.effectiveProjectId;
		if (!instanceId || !projectId) return null;
		return { instanceId, projectId };
	}

	function isCurrentAttachment(scope: StorageScope, generation: number, requestId: number) {
		return attachmentScopeGeneration === generation
			&& attachmentRequestId === requestId
			&& s.instanceId === scope.instanceId
			&& s.effectiveProjectId === scope.projectId;
	}

	function isCurrentMutation(scope: StorageScope, generation: number) {
		return attachmentScopeGeneration === generation
			&& s.instanceId === scope.instanceId
			&& s.effectiveProjectId === scope.projectId;
	}

	function isCurrentCatalog(projectId: string, generation: number) {
		return catalogGeneration === generation && s.effectiveProjectId === projectId;
	}

	async function loadAttachments(instanceId: string, projectId: string, scopeGeneration: number) {
		const scope = { instanceId, projectId };
		const requestId = ++attachmentRequestId;
		if (isCurrentAttachment(scope, scopeGeneration, requestId)) {
			loading = true;
			attachmentError = '';
		}
		try {
			const data = await api.get<StorageAttachment[]>(
				`/api/v1/instances/${instanceId}/storage-attachments`,
				tok(),
				projectId,
			);
			if (isCurrentAttachment(scope, scopeGeneration, requestId)) attachments = data;
		} catch (error) {
			if (isCurrentAttachment(scope, scopeGeneration, requestId)) {
				attachments = [];
				attachmentError = error instanceof ApiError ? error.message : '연결 정보를 불러오지 못했습니다.';
			}
		} finally {
			if (isCurrentAttachment(scope, scopeGeneration, requestId)) loading = false;
		}
	}

	function loadFileStorages(projectId = s.effectiveProjectId, generation = catalogGeneration): Promise<void> {
		if (!projectId) return Promise.resolve();
		if (catalogProjectId === projectId) {
			if (catalogStatus === 'loading' && catalogPromise) return catalogPromise;
			if (catalogStatus === 'loaded') return Promise.resolve();
		}

		catalogProjectId = projectId;
		catalogStatus = 'loading';
		catalogError = '';
		const promise = (async () => {
			try {
				const data = await api.get<FileStorage[]>('/api/v1/file-storage', tok(), projectId);
				if (isCurrentCatalog(projectId, generation)) {
					fileStorages = data;
					catalogStatus = 'loaded';
				}
			} catch (error) {
				if (isCurrentCatalog(projectId, generation)) {
					fileStorages = [];
					catalogStatus = 'error';
					catalogError = error instanceof ApiError ? error.message : '파일 스토리지를 불러오지 못했습니다.';
				}
			} finally {
				if (isCurrentCatalog(projectId, generation)) catalogPromise = null;
			}
		})();
		catalogPromise = promise;
		return promise;
	}

	function toggleForm() {
		showForm = !showForm;
		selectedStorageId = '';
		mountPoint = '';
		readOnly = false;
		if (showForm) void loadFileStorages();
	}

	async function handleAttach() {
		const scope = currentScope();
		const generation = attachmentScopeGeneration;
		const selectedId = selectedStorageId;
		const requestedMountPoint = mountPoint.trim();
		const requestedReadOnly = readOnly;
		if (!scope || !selectedId || !requestedMountPoint) return;
		attaching = true;
		lastMountInfo = null;
		try {
			const result = await api.post<{ mount_command: string; keyring_file: string | null }>(
				`/api/v1/instances/${scope.instanceId}/storage-attachments`,
				{ file_storage_id: selectedId, mount_point: requestedMountPoint, read_only: requestedReadOnly },
				tok(),
				scope.projectId,
			);
			if (!isCurrentMutation(scope, generation)) return;
			lastMountInfo = result;
			showForm = false;
			selectedStorageId = '';
			mountPoint = '';
			readOnly = false;
			await loadAttachments(scope.instanceId, scope.projectId, generation);
		} catch (error) {
			if (isCurrentMutation(scope, generation)) {
				toast.error('연결 실패: ' + (error instanceof ApiError ? error.message : String(error)));
			}
		} finally {
			if (isCurrentMutation(scope, generation)) {
				attaching = false;
			}
		}
	}

	async function handleDetach(fileStorageId: string) {
		const scope = currentScope();
		const generation = attachmentScopeGeneration;
		if (!scope) return;
		detaching = fileStorageId;
		try {
			await api.delete(
				`/api/v1/instances/${scope.instanceId}/storage-attachments/${fileStorageId}`,
				tok(),
				scope.projectId,
			);
			if (!isCurrentMutation(scope, generation)) return;
			await loadAttachments(scope.instanceId, scope.projectId, generation);
			if (s.instanceId === scope.instanceId && s.effectiveProjectId === scope.projectId && attachmentScopeGeneration === generation) {
				lastMountInfo = null;
			}
		} catch (error) {
			if (isCurrentMutation(scope, generation)) {
				toast.error('연결 해제 실패: ' + (error instanceof ApiError ? error.message : String(error)));
			}
		} finally {
			if (isCurrentMutation(scope, generation)) detaching = null;
		}
	}

	async function copyToClipboard(text: string) {
		try {
			await navigator.clipboard.writeText(text);
			copied = true;
			setTimeout(() => { copied = false; }, 2000);
		} catch {
			// ignore
		}
	}

	$effect(() => {
		const instanceId = s.instanceId ?? null;
		const projectId = s.effectiveProjectId ?? null;
		const attachmentScopeChanged = instanceId !== observedInstanceId || projectId !== observedProjectId;
		if (!attachmentScopeChanged) return;

		const projectChanged = projectId !== observedProjectId;
		observedInstanceId = instanceId;
		observedProjectId = projectId;
		attachmentScopeGeneration += 1;
		attachmentRequestId += 1;
		attachments = [];
		attachmentError = '';
		loading = false;
		attaching = false;
		detaching = null;
		lastMountInfo = null;
		showForm = false;
		selectedStorageId = '';
		mountPoint = '';
		readOnly = false;

		if (projectChanged) {
			catalogGeneration += 1;
			catalogProjectId = null;
			catalogPromise = null;
			fileStorages = [];
			catalogStatus = 'idle';
			catalogError = '';
		}

		if (instanceId && projectId) void loadAttachments(instanceId, projectId, attachmentScopeGeneration);
	});

	const availableStorages = $derived(
		fileStorages.filter(f => f.status === 'available' && !attachments.some(a => a.file_storage_id === f.id))
	);
</script>

<div class="bg-surface-base border border-line rounded-lg p-6 mb-4">
	<div class="flex items-center justify-between mb-4">
		<h2 class="text-sm font-semibold text-ink-2 uppercase tracking-wide">파일 스토리지</h2>
		<button
			onclick={toggleForm}
			class="text-xs text-action-warm hover:text-action-warm-hover transition-colors"
		>
			{showForm ? '닫기' : '+ 연결'}
		</button>
	</div>

	{#if showForm}
		<div class="mb-4 bg-surface-sunken rounded-lg p-4">
			<div class="grid grid-cols-1 gap-3 mb-3">
				<div>
					<label for="attachment-storage" class="block text-xs text-ink-2 mb-1">파일 스토리지</label>
					<select
						id="attachment-storage"
						bind:value={selectedStorageId}
						disabled={catalogStatus === 'loading'}
						class="w-full bg-surface-selected border border-line-2 text-ink-0 text-sm rounded-lg px-3 py-2 focus:outline-none focus:border-action-warm"
					>
						<option value="">선택...</option>
						{#each availableStorages as fs}
							<option value={fs.id}>{fs.name || fs.id.slice(0, 12)} ({fs.share_proto})</option>
						{/each}
					</select>
					{#if catalogStatus === 'loading'}
						<p class="text-xs text-ink-2 mt-1">파일 스토리지를 불러오는 중...</p>
					{:else if catalogStatus === 'error'}
						<p class="catalog-message">파일 스토리지를 불러오지 못했습니다. 다시 열어 재시도하세요.</p>
					{:else if catalogStatus === 'loaded' && availableStorages.length === 0}
						<p class="catalog-message">연결 가능한 파일 스토리지가 없습니다.</p>
					{/if}
				</div>
				<div>
					<label for="attachment-mount-point" class="block text-xs text-ink-2 mb-1">마운트 경로</label>
					<input
						id="attachment-mount-point"
						bind:value={mountPoint}
						placeholder="/mnt/mydata"
						class="w-full bg-surface-selected border border-line-2 text-ink-0 text-sm rounded-lg px-3 py-2 focus:outline-none focus:border-action-warm"
					/>
					<p class="text-[10.5px] text-ink-3 mt-0.5">/mnt, /data, /srv, /home 하위 경로만 허용</p>
				</div>
				<label class="flex items-center gap-2 text-sm text-ink-2 cursor-pointer">
					<input
						type="checkbox"
						bind:checked={readOnly}
						class="w-4 h-4 rounded border-line-2 bg-surface-sunken text-action-warm"
					/>
					읽기 전용으로 마운트
				</label>
			</div>
			<button
				onclick={handleAttach}
				disabled={catalogStatus === 'loading' || attaching || !selectedStorageId || !mountPoint.trim()}
				class="px-4 py-2 bg-action-warm hover:bg-action-warm-hover disabled:bg-surface-selected disabled:text-ink-3 text-action-on-warm text-sm rounded-lg transition-colors"
			>
				{attaching ? '연결 중...' : '연결'}
			</button>
		</div>
	{/if}

	{#if lastMountInfo}
		<div class="mb-4 bg-green-900/20 border border-green-700/50 rounded-lg p-4">
			<p class="text-xs text-green-400 font-medium mb-2">연결 완료 — VM 내부에서 아래 명령을 실행하세요</p>
			{#if lastMountInfo.keyring_file}
				<p class="text-[10.5px] text-ink-2 mb-1.5">
					키링 파일이 cloud-init으로 미리 주입된 경우 <code class="text-ink-2">{lastMountInfo.keyring_file}</code>에 존재합니다.
					런타임 연결 시 키링 파일을 직접 생성해야 할 수 있습니다.
				</p>
			{/if}
			<div class="flex items-center gap-2">
				<code class="flex-1 text-xs font-mono bg-surface-base text-cyan-300 px-3 py-2 rounded break-all">{lastMountInfo.mount_command}</code>
				<button
					onclick={() => copyToClipboard(lastMountInfo!.mount_command)}
					class="shrink-0 px-2 py-1.5 text-xs {copied ? 'text-green-400' : 'text-ink-2 hover:text-ink-1'} transition-colors"
				>
					{copied ? '복사됨' : '복사'}
				</button>
			</div>
		</div>
	{/if}

	{#if loading}
		<p class="text-sm text-ink-3">로딩 중...</p>
	{:else if attachments.length === 0}
		<p class="text-sm text-ink-3">연결된 파일 스토리지가 없습니다.</p>
	{:else}
		<div class="space-y-2">
			{#each attachments as att}
				<div class="flex items-start gap-3 p-3 bg-surface-sunken/50 rounded-lg border border-line-2/50">
					<div class="flex-1 min-w-0">
						<div class="flex items-center gap-2">
							<span class="text-sm text-ink-0 font-medium truncate">{att.name || att.file_storage_id.slice(0, 12)}</span>
							{#if att.share_proto}
								<span class="text-[10px] text-ink-3 font-mono px-1.5 py-0.5 rounded bg-surface-selected">{att.share_proto}</span>
							{/if}
							<span class="text-[10px] px-1.5 py-0.5 rounded font-mono {att.status === 'available' ? 'text-green-400 bg-green-900/20' : 'text-ink-2 bg-surface-selected'}">{att.status}</span>
						</div>
					</div>
					<button
						onclick={() => handleDetach(att.file_storage_id)}
						disabled={detaching === att.file_storage_id}
						class="shrink-0 text-xs text-red-400/70 hover:text-red-400 disabled:text-ink-3 transition-colors"
					>
						{detaching === att.file_storage_id ? '해제 중...' : '해제'}
					</button>
				</div>
			{/each}
		</div>
	{/if}
</div>
<style>
	.catalog-message {
		margin-top: 0.25rem;
		font-size: 0.75rem;
		color: var(--color-text-muted);
	}
</style>
