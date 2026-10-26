<script lang="ts">
	import { auth, canWrite } from '$lib/stores/auth';
	import { api, ApiError } from '$lib/api/client';
	import { useInstanceDetailController } from '$lib/stores/instanceDetailController.svelte';
	import { get } from 'svelte/store';
	import { toast } from '$lib/stores/toast';
	import { t } from '$lib/i18n/ns/instance';
	import { ActivityIndicator, Alert, Button, StatusChip } from '$lib/components/ui';

	const s = useInstanceDetailController();

	interface StorageAuthorization {
		file_storage_id: string;
		name: string | null;
		share_proto: string | null;
		access_id: string | null;
		access_type: string | null;
		access_to: string | null;
		access_level: string | null;
		state: string;
		association_state: 'tracked' | 'mismatch' | 'untracked' | 'unknown';
		managed: boolean;
		exports: string[];
		share_network_id: string | null;
		share_network: Record<string, unknown> | null;
	}
	interface ConnectionResponse extends StorageAuthorization {
		secret?: { type: string; value: string };
	}
	interface FileStorage {
		id: string;
		name: string;
		status: string;
		share_proto: string;
	}
	interface StorageScope {
		instanceId: string;
		projectId: string;
		token: string | null;
		adminMode: boolean;
		transportProjectId: string | undefined;
	}

	let attachments = $state<StorageAuthorization[]>([]);
	let fileStorages = $state<FileStorage[]>([]);
	let loading = $state(false);
	let attachmentError = $state('');
	let catalogStatus = $state<'idle' | 'loading' | 'loaded' | 'error'>('idle');
	let catalogError = $state('');
	let showForm = $state(false);
	let selectedStorageId = $state('');
	let selectedFixedIp = $state('');
	let readOnly = $state(false);
	let granting = $state(false);
	let revoking = $state<string | null>(null);
	let retrieving = $state<string | null>(null);
	let lastConnection = $state<ConnectionResponse | null>(null);
	let attachmentScopeGeneration = 0;
	let attachmentRequestId = 0;
	let mutationGeneration = 0;
	let disclosureGeneration = 0;
	let catalogGeneration = 0;
	let catalogProjectId: string | null = null;
	let catalogPromise: Promise<void> | null = null;
	let observedInstanceId: string | null | undefined;
	let observedProjectId: string | null | undefined;
	let observedToken: string | null | undefined;
	let observedWritePermission: boolean | undefined;
	let observedAdminMode: boolean | undefined;
	let observedTransportProjectId: string | undefined;

	const targetIsCurrent = $derived(!!s.instanceId && s.instance?.id === s.instanceId);
	const fixedIps = $derived(targetIsCurrent
		? [...new Set(s.fixedIpsList.filter(ip => ip.type === 'fixed').map(ip => ip.addr))]
		: []);
	const availableStorages = $derived(fileStorages.filter(f =>
		f.status === 'available' && ['NFS', 'CEPHFS'].includes(f.share_proto)
		&& !attachments.some(a => a.file_storage_id === f.id)));
	const selectedStorage = $derived(availableStorages.find(f => f.id === selectedStorageId));
	const cephIdentity = $derived(targetIsCurrent && /^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$/i.test(s.instanceId)
		? `afterglow-${s.instanceId.replaceAll('-', '').toLowerCase()}` : '');
	const busy = $derived(granting || revoking !== null || retrieving !== null);
	const canGrant = $derived($canWrite && targetIsCurrent && !!s.effectiveProjectId && !loading
		&& catalogStatus === 'loaded' && !!selectedStorage
		&& (selectedStorage.share_proto === 'NFS' ? fixedIps.includes(selectedFixedIp) : !!cephIdentity));

	function tok() { return get(auth).token ?? undefined; }
	function currentScope(): StorageScope | null {
		const instanceId = s.instanceId;
		const projectId = s.effectiveProjectId;
		if (!instanceId || !projectId || s.instance?.id !== instanceId) return null;
		return { instanceId, projectId, token: get(auth).token, adminMode: !!s.adminMode,
			transportProjectId: s.adminMode ? get(auth).projectId ?? undefined : projectId };
	}
	function isCurrentAttachment(scope: StorageScope, generation: number, requestId: number) {
		return attachmentScopeGeneration === generation && attachmentRequestId === requestId
			&& s.instanceId === scope.instanceId && s.effectiveProjectId === scope.projectId
			&& get(auth).token === scope.token
			&& !!s.adminMode === scope.adminMode
			&& (s.adminMode ? get(auth).projectId ?? undefined : s.effectiveProjectId) === scope.transportProjectId;
	}
	function isCurrentMutation(scope: StorageScope, generation: number, mutation: number) {
		return get(canWrite) && mutationGeneration === mutation && attachmentScopeGeneration === generation
			&& s.instanceId === scope.instanceId && s.instance?.id === scope.instanceId
			&& s.effectiveProjectId === scope.projectId && get(auth).token === scope.token
			&& !!s.adminMode === scope.adminMode
			&& (s.adminMode ? get(auth).projectId ?? undefined : s.effectiveProjectId) === scope.transportProjectId;
	}
	function isCurrentCatalog(projectId: string, generation: number) {
		return catalogGeneration === generation && s.effectiveProjectId === projectId;
	}
	function clearDisclosure() {
		disclosureGeneration += 1;
		lastConnection = null;
	}
	function resetForm() {
		selectedStorageId = '';
		selectedFixedIp = '';
		readOnly = false;
	}

	async function loadAttachments(instanceId: string, projectId: string, scopeGeneration: number) {
		const scope = { instanceId, projectId, token: get(auth).token, adminMode: !!s.adminMode,
			transportProjectId: s.adminMode ? get(auth).projectId ?? undefined : projectId };
		const requestId = ++attachmentRequestId;
		if (isCurrentAttachment(scope, scopeGeneration, requestId)) {
			loading = true;
			attachmentError = '';
		}
		try {
			const data = await api.get<StorageAuthorization[]>(`/api/v1/${scope.adminMode ? 'admin/' : ''}instances/${instanceId}/storage-attachments`, scope.token ?? undefined, scope.transportProjectId);
			if (isCurrentAttachment(scope, scopeGeneration, requestId)) attachments = data;
		} catch (error) {
			if (isCurrentAttachment(scope, scopeGeneration, requestId)) {
				attachments = [];
				attachmentError = error instanceof ApiError ? error.message : t('storageAttachments.loadFailed');
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
				const data = await api.get<FileStorage[]>(s.adminMode ? `/api/v1/admin/instances/${s.instanceId}/file-storage` : '/api/v1/file-storage', tok(), s.adminMode ? get(auth).projectId ?? undefined : projectId);
				if (isCurrentCatalog(projectId, generation)) {
					fileStorages = data;
					catalogStatus = 'loaded';
				}
			} catch (error) {
				if (isCurrentCatalog(projectId, generation)) {
					fileStorages = [];
					catalogStatus = 'error';
					catalogError = error instanceof ApiError ? error.message : t('storageAttachments.catalogLoadFailed');
				}
			} finally {
				if (isCurrentCatalog(projectId, generation)) catalogPromise = null;
			}
		})();
		catalogPromise = promise;
		return promise;
	}
	function toggleForm() {
		if (!get(canWrite) || !currentScope()) return;
		clearDisclosure();
		showForm = !showForm;
		resetForm();
		if (showForm) void loadFileStorages();
	}
	async function handleGrant() {
		const scope = currentScope();
		const generation = attachmentScopeGeneration;
		const mutation = mutationGeneration;
		const storage = availableStorages.find(f => f.id === selectedStorageId);
		// Re-read the current permission, target and exact IP at the mutation boundary.
		if (!get(canWrite) || !scope || busy || loading || catalogStatus !== 'loaded' || !storage) return;
		if (storage.share_proto === 'NFS' ? !fixedIps.includes(selectedFixedIp) : !cephIdentity) return;
		const body = {
			file_storage_id: storage.id,
			read_only: readOnly,
			...(storage.share_proto === 'NFS' ? { fixed_ip: selectedFixedIp } : {}),
		};
		granting = true;
		clearDisclosure();
		const disclosure = disclosureGeneration;
		try {
			const result = await api.post<ConnectionResponse>(`/api/v1/${scope.adminMode ? 'admin/' : ''}instances/${scope.instanceId}/storage-attachments`, body, scope.token ?? undefined, scope.transportProjectId);
			if (!isCurrentMutation(scope, generation, mutation)) return;
			if (disclosureGeneration === disclosure) {
				lastConnection = result;
				showForm = false;
				resetForm();
			}
			await loadAttachments(scope.instanceId, scope.projectId, generation);
		} catch (error) {
			if (isCurrentMutation(scope, generation, mutation) && disclosureGeneration === disclosure) {
				toast.error(t('storageAttachments.grantFailed', { error: error instanceof ApiError ? error.message : String(error) }));
			}
		} finally {
			if (isCurrentMutation(scope, generation, mutation)) granting = false;
		}
	}
	async function handleRevoke(fileStorageId: string) {
		const scope = currentScope();
		const generation = attachmentScopeGeneration;
		const mutation = mutationGeneration;
		if (!get(canWrite) || !scope || busy || loading || !attachments.some(a => a.file_storage_id === fileStorageId && a.managed && a.association_state === 'tracked')) return;
		revoking = fileStorageId;
		clearDisclosure();
		try {
			await api.delete(`/api/v1/${scope.adminMode ? 'admin/' : ''}instances/${scope.instanceId}/storage-attachments/${fileStorageId}`, scope.token ?? undefined, scope.transportProjectId);
			if (!isCurrentMutation(scope, generation, mutation)) return;
			await loadAttachments(scope.instanceId, scope.projectId, generation);
		} catch (error) {
			if (isCurrentMutation(scope, generation, mutation)) {
				toast.error(t('storageAttachments.revokeFailed', { error: error instanceof ApiError ? error.message : String(error) }));
				// A rejected/pending revoke may have changed provider state without removing the association.
				await loadAttachments(scope.instanceId, scope.projectId, generation);
			}
		} finally {
			if (isCurrentMutation(scope, generation, mutation)) revoking = null;
		}
	}
	async function handleConnectionInfo(fileStorageId: string) {
		const scope = currentScope();
		const generation = attachmentScopeGeneration;
		const mutation = mutationGeneration;
		if (!get(canWrite) || !scope || busy || loading || !attachments.some(a =>
			a.file_storage_id === fileStorageId && a.managed && a.association_state === 'tracked' && a.share_proto === 'CEPHFS')) return;
		retrieving = fileStorageId;
		clearDisclosure();
		const disclosure = disclosureGeneration;
		try {
			const result = await api.post<ConnectionResponse>(`/api/v1/${scope.adminMode ? 'admin/' : ''}instances/${scope.instanceId}/storage-attachments/${fileStorageId}/connection-info`, {}, scope.token ?? undefined, scope.transportProjectId);
			if (isCurrentMutation(scope, generation, mutation) && disclosureGeneration === disclosure) lastConnection = result;
		} catch (error) {
			if (isCurrentMutation(scope, generation, mutation) && disclosureGeneration === disclosure) {
				toast.error(t('storageAttachments.connectionFailed', { error: error instanceof ApiError ? error.message : String(error) }));
			}
		} finally {
			if (isCurrentMutation(scope, generation, mutation)) retrieving = null;
		}
	}
	function pending(state: string) {
		return ['new', 'queued_to_apply', 'applying', 'queued_to_deny', 'denying'].includes(state);
	}

	$effect(() => {
		const instanceId = s.instanceId ?? null;
		const projectId = s.effectiveProjectId ?? null;
		const token = $auth.token;
		const adminMode = !!s.adminMode;
		const transportProjectId = adminMode ? $auth.projectId ?? undefined : projectId ?? undefined;
		if (instanceId === observedInstanceId && projectId === observedProjectId && token === observedToken
			&& adminMode === observedAdminMode && transportProjectId === observedTransportProjectId) return;
		const projectChanged = projectId !== observedProjectId || token !== observedToken
			|| adminMode !== observedAdminMode || transportProjectId !== observedTransportProjectId;
		observedAdminMode = adminMode;
		observedTransportProjectId = transportProjectId;
		observedInstanceId = instanceId;
		observedProjectId = projectId;
		observedToken = token;
		attachmentScopeGeneration += 1;
		attachmentRequestId += 1;
		mutationGeneration += 1;
		attachments = [];
		attachmentError = '';
		loading = false;
		granting = false;
		revoking = null;
		retrieving = null;
		clearDisclosure();
		showForm = false;
		resetForm();
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
	$effect(() => {
		const permission = $canWrite;
		if (permission === observedWritePermission) return;
		observedWritePermission = permission;
		if (!permission) {
			mutationGeneration += 1;
			clearDisclosure();
			showForm = false;
			resetForm();
			granting = false;
			revoking = null;
			retrieving = null;
		}
	});
	$effect(() => {
		if (s.instance?.id === s.instanceId) return;
		mutationGeneration += 1;
		clearDisclosure();
		granting = false;
		revoking = null;
		retrieving = null;
	});
</script>

{#snippet authorizationDetails(info: StorageAuthorization)}
	<dl class="grid grid-cols-1 sm:grid-cols-2 gap-2 text-xs mt-3">
		<div><dt class="text-ink-2">{t('storageAttachments.accessType')}</dt><dd class="text-ink-0 font-mono">{info.access_type ?? '—'}</dd></div>
		<div><dt class="text-ink-2">{t('storageAttachments.accessTarget')}</dt><dd class="text-ink-0 font-mono break-all">{info.access_to ?? '—'}</dd></div>
		<div><dt class="text-ink-2">{t('storageAttachments.accessLevel')}</dt><dd class="text-ink-0">{info.access_level === 'ro' ? t('storageAttachments.readOnly') : info.access_level === 'rw' ? t('storageAttachments.readWrite') : '—'}</dd></div>
		<div><dt class="text-ink-2">{t('storageAttachments.ruleState')}</dt><dd><StatusChip status={info.state} /></dd></div>
		<div class="sm:col-span-2"><dt class="text-ink-2">{t('storageAttachments.exports')}</dt><dd class="text-ink-0 break-all">
			{#each info.exports as path}<div class="font-mono">{path}</div>{:else}{t('storageAttachments.noExports')}{/each}
		</dd></div>
		<div class="sm:col-span-2"><dt class="text-ink-2">{t('storageAttachments.shareNetwork')}</dt><dd class="text-ink-0 break-all">
			{#if info.share_network}
				{#each Object.entries(info.share_network) as [key, value]}
					{#if value !== null && value !== undefined && value !== ''}<div><span class="text-ink-2">{key}: </span>{typeof value === 'object' ? JSON.stringify(value) : String(value)}</div>{/if}
				{/each}
			{:else}{info.share_network_id ?? t('storageAttachments.noShareNetwork')}{/if}
		</dd></div>
	</dl>
	{#if info.association_state === 'mismatch' || info.association_state === 'unknown'}
		<Alert tone="warning" class="mt-2">{t(info.association_state === 'mismatch' ? 'storageAttachments.associationMismatch' : 'storageAttachments.associationUnknown')}</Alert>
	{/if}
	<p class="text-xs text-ink-2 mt-2">{info.association_state === 'tracked' && info.state === 'active' ? t('storageAttachments.ruleActive') : pending(info.state) ? t('storageAttachments.rulePending') : t('storageAttachments.ruleInactive')}</p>
{/snippet}

<div class="bg-surface-base border border-line rounded-lg p-6 mb-4">
	<div class="flex items-center justify-between mb-4 gap-3">
		<h2 class="text-sm font-semibold text-ink-2 uppercase tracking-wide">{t('storageAttachments.title')}</h2>
		{#if $canWrite}
			<Button variant="link" size="xs" onclick={toggleForm} disabled={!targetIsCurrent || !s.effectiveProjectId} ariaExpanded={showForm}>
				{showForm ? t('storageAttachments.close') : t('storageAttachments.openGrant')}
			</Button>
		{/if}
	</div>
	<Alert tone="info" class="mb-4">{t('storageAttachments.manualConnection')}</Alert>
	{#if showForm && $canWrite}
		<div class="motion-enter mb-4 bg-surface-sunken rounded-lg p-4">
			<div class="grid grid-cols-1 gap-3 mb-3">
				<div>
					<label for="attachment-storage" class="block text-xs text-ink-2 mb-1">{t('storageAttachments.storageLabel')}</label>
					<select id="attachment-storage" bind:value={selectedStorageId} onchange={() => selectedFixedIp = ''} disabled={busy || catalogStatus === 'loading'} class="w-full bg-surface-selected border border-line-2 text-ink-0 text-sm rounded-lg px-3 py-2">
						<option value="">{t('storageAttachments.selectPlaceholder')}</option>
						{#each availableStorages as fs}<option value={fs.id}>{fs.name || fs.id.slice(0, 12)} ({fs.share_proto})</option>{/each}
					</select>
					{#if catalogStatus === 'loading'}<ActivityIndicator class="mt-1" label={t('storageAttachments.catalogLoading')} />
					{:else if catalogStatus === 'error'}<Alert class="mt-2">{catalogError} {t('storageAttachments.catalogRetry')}</Alert>
					{:else if catalogStatus === 'loaded' && availableStorages.length === 0}<p class="text-xs text-ink-2 mt-1">{t('storageAttachments.noAvailableStorage')}</p>{/if}
				</div>
				{#if selectedStorage?.share_proto === 'NFS'}
					<div>
						<label for="attachment-fixed-ip" class="block text-xs text-ink-2 mb-1">{t('storageAttachments.fixedIpLabel')}</label>
						<select id="attachment-fixed-ip" bind:value={selectedFixedIp} disabled={busy || fixedIps.length === 0} class="w-full bg-surface-selected border border-line-2 text-ink-0 text-sm rounded-lg px-3 py-2">
							<option value="">{t('storageAttachments.selectPlaceholder')}</option>
							{#each fixedIps as ip}<option value={ip}>{ip}</option>{/each}
						</select>
						<p class="text-xs text-ink-2 mt-1">{t(fixedIps.length ? 'storageAttachments.fixedIpHelp' : 'storageAttachments.noFixedIps')}</p>
					</div>
				{:else if selectedStorage?.share_proto === 'CEPHFS'}
					<div><p class="text-xs text-ink-2">{t('storageAttachments.cephIdentity')}</p><code class="text-xs text-ink-0 break-all">{cephIdentity || '—'}</code></div>
				{/if}
				<label class="flex items-center gap-2 text-sm text-ink-2"><input type="checkbox" bind:checked={readOnly} disabled={busy} />{t('storageAttachments.readOnly')}</label>
			</div>
			<Button onclick={handleGrant} disabled={!canGrant || busy} ariaBusy={granting} size="sm">
				{#if granting}<ActivityIndicator size="xs" label={t('storageAttachments.granting')} />{:else}{t('storageAttachments.grant')}{/if}
			</Button>
		</div>
	{/if}
	{#if lastConnection && $canWrite && targetIsCurrent}
		<div class="motion-enter mb-4 bg-surface-sunken border border-line-2 rounded-lg p-4">
			<div class="flex justify-between gap-3"><h3 class="text-sm font-medium text-ink-0">{t('storageAttachments.connectionDetails')}</h3><Button variant="ghost" size="xs" onclick={clearDisclosure}>{t('storageAttachments.close')}</Button></div>
			{@render authorizationDetails(lastConnection)}
			{#if lastConnection.secret?.type === 'cephx_key' && lastConnection.secret.value}
				<Alert tone="warning" title={t('storageAttachments.transientSecret')} class="mt-3">
					<p>{t('storageAttachments.transientSecretHelp')}</p><code class="block break-all mt-2 select-all">{lastConnection.secret.value}</code>
				</Alert>
			{/if}
		</div>
	{/if}
	{#if loading}<ActivityIndicator label={t('storageAttachments.loading')} />
	{:else if attachmentError}<Alert>{attachmentError}</Alert>
	{:else if attachments.length === 0}<p class="text-sm text-ink-2">{t('storageAttachments.empty')}</p>
	{:else}
		<div class="space-y-2">
			{#each attachments as att (att.file_storage_id)}
				<div class="p-3 bg-surface-sunken/50 rounded-lg border border-line-2/50">
					<div class="flex flex-wrap items-center justify-between gap-2">
						<div class="flex items-center gap-2 min-w-0"><span class="text-sm text-ink-0 font-medium truncate">{att.name || att.file_storage_id.slice(0, 12)}</span>{#if att.share_proto}<span class="text-xs text-ink-2 font-mono">{att.share_proto}</span>{/if}</div>
						{#if $canWrite && att.managed && att.association_state === 'tracked'}
							<div class="flex flex-wrap gap-2">
								{#if att.share_proto === 'CEPHFS'}<Button variant="secondary" size="xs" onclick={() => handleConnectionInfo(att.file_storage_id)} disabled={busy || !targetIsCurrent} ariaBusy={retrieving === att.file_storage_id}>
									{#if retrieving === att.file_storage_id}<ActivityIndicator size="xs" label={t('storageAttachments.connectionLoading')} />{:else}{t('storageAttachments.connectionInfo')}{/if}
								</Button>{/if}
								<Button variant="danger-outline" size="xs" onclick={() => handleRevoke(att.file_storage_id)} disabled={busy || !targetIsCurrent} ariaBusy={revoking === att.file_storage_id}>
									{#if revoking === att.file_storage_id}<ActivityIndicator size="xs" label={t('storageAttachments.revoking')} />{:else}{t('storageAttachments.revoke')}{/if}
								</Button>
							</div>
						{/if}
					</div>
					{@render authorizationDetails(att)}
					{#if !att.managed}<p class="text-xs text-ink-2 mt-2">{t('storageAttachments.unmanaged')}</p>{/if}
				</div>
			{/each}
		</div>
	{/if}
</div>
