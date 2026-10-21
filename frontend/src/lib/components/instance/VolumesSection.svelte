<script lang="ts">
	import { useInstanceDetailController } from '$lib/stores/instanceDetailController.svelte';
	import { t } from '$lib/i18n/ns/instance';
	import { ActivityIndicator, Alert, Button, CompactResourceCard, ResponsiveTable, StatusChip } from '$lib/components/ui';
	import { auth, canWrite } from '$lib/stores/auth';
	import { api, ApiError } from '$lib/api/client';
	import type { Volume } from '$lib/types/volume';
	import VolumeExtendModal from '$lib/components/volume/VolumeExtendModal.svelte';

	const s = useInstanceDetailController();

	let showAttachVolume = $state(false);
	let attachMode = $state<'existing' | 'new'>('existing');
	let selectedVolumeId = $state('');
	let newVolName = $state('');
	let newVolSize = $state(20);

	let extendTarget = $state<Volume | null>(null);
	let extendLoading = $state<string | null>(null);
	let extendError = $state('');
	let extendScope = $state<{ instanceId: string; projectId: string; token: string } | null>(null);
	let extendGeneration = 0;

	function expansionReason(volumeId: string): 'volumes.extendReadOnly' | 'volumes.extendScopeUnavailable'
		| 'volumes.extendOfflineRequired' | 'volumes.extendUnavailable' | null {
		if (!$canWrite) return 'volumes.extendReadOnly';
		if (!s.effectiveProjectId || !$auth.token || !s.instanceId || s.instance?.id !== s.instanceId) {
			return 'volumes.extendScopeUnavailable';
		}
		if (s.instance?.status !== 'SHUTOFF') return 'volumes.extendOfflineRequired';
		const row = s.volumes.find((volume) => volume.volume_id === volumeId);
		if (!row || row.status !== 'in-use' || !Number.isSafeInteger(row.size)
			|| !row.size || row.size < 1 || row.size >= 2147483647) return 'volumes.extendUnavailable';
		return null;
	}

	function ownsExpansion(scope: NonNullable<typeof extendScope>, generation: number) {
		return extendGeneration === generation && s.instanceId === scope.instanceId
			&& s.effectiveProjectId === scope.projectId && $auth.token === scope.token
			&& s.instance?.status === 'SHUTOFF' && $canWrite;
	}

	// Project scalar identity/state: a fresh server object alone is not a scope transition.
	const expansionInstanceId = $derived(s.instanceId);
	const expansionLoadedId = $derived(s.instance?.id);
	const expansionProjectId = $derived(s.effectiveProjectId);
	const expansionStatus = $derived(s.instance?.status);
	const expansionToken = $derived($auth.token);
	const expansionWritable = $derived($canWrite);

	$effect(() => {
		// A target or credential transition invalidates outstanding detail reads, including ABA switches.
		expansionInstanceId;
		expansionLoadedId;
		expansionProjectId;
		expansionStatus;
		expansionToken;
		expansionWritable;
		extendGeneration++;
		extendTarget = null;
		extendScope = null;
		extendLoading = null;
		extendError = '';
	});

	const visibleExtendTarget = $derived(extendTarget && extendScope
		&& ownsExpansion(extendScope, extendGeneration) && !expansionReason(extendTarget.id)
		? extendTarget : null);

	async function openExpansion(volumeId: string) {
		if (expansionReason(volumeId) || extendLoading || s.actioning) return;
		const scope = { instanceId: s.instanceId, projectId: s.effectiveProjectId!, token: $auth.token! };
		const generation = ++extendGeneration;
		extendLoading = volumeId;
		extendError = '';
		try {
			const volume = await api.get<Volume>(`/api/v1/volumes/${encodeURIComponent(volumeId)}`, scope.token, scope.projectId, { refresh: true });
			if (!ownsExpansion(scope, generation) || expansionReason(volumeId)) return;
			if (volume.id !== volumeId || volume.status !== 'in-use'
				|| !Number.isSafeInteger(volume.size) || volume.size < 1 || volume.size >= 2147483647
				|| !Array.isArray(volume.attachments)
				|| !volume.attachments.some((attachment) => attachment.server_id === scope.instanceId)) {
				extendError = t('volumes.extendUnavailable');
				return;
			}
			extendScope = scope;
			extendTarget = volume;
		} catch (error) {
			if (ownsExpansion(scope, generation)) {
				extendError = error instanceof ApiError ? error.message : t('volumes.extendLoadFailed');
			}
		} finally {
			if (ownsExpansion(scope, generation)) extendLoading = null;
		}
	}

	function closeExpansion() {
		extendTarget = null;
		extendScope = null;
		extendGeneration++;
	}

	async function onExpanded() {
		const scope = extendScope;
		const generation = extendGeneration;
		closeExpansion();
		if (scope && generation + 1 === extendGeneration && s.instanceId === scope.instanceId
			&& s.effectiveProjectId === scope.projectId && $auth.token === scope.token) {
			await s.fetchInstance(scope.instanceId, { silent: true });
		}
	}

	async function handleAttachVolume() {
		await s.attachVolume(selectedVolumeId);
		showAttachVolume = false;
		selectedVolumeId = '';
	}

	async function handleCreateAndAttach() {
		await s.createAndAttachVolume(newVolName.trim(), newVolSize);
		showAttachVolume = false;
		newVolName = '';
		newVolSize = 20;
	}
</script>

<div class="bg-surface-base border border-line rounded-lg p-6 mb-4">
	<div class="flex items-center justify-between mb-4">
		<h2 class="text-sm font-semibold text-ink-2 uppercase tracking-wide">{t('volumes.title')}</h2>
		<button
			onclick={() => { showAttachVolume = !showAttachVolume; selectedVolumeId = ''; newVolName = ''; newVolSize = 20; }}
			class="text-xs text-warm-text hover:text-warm-text-hover transition-colors"
		>
			{showAttachVolume ? t('volumes.close') : t('volumes.addAttachment')}
		</button>
	</div>

	{#if showAttachVolume}
		<div class="mb-4 bg-surface-sunken rounded-lg p-4">
			<div class="flex gap-1 mb-3">
				<button
					onclick={() => { attachMode = 'existing'; }}
					class="text-xs px-2 py-1 rounded border transition-colors {attachMode === 'existing' ? 'text-warm-text border-action-warm bg-surface-selected/20' : 'text-ink-2 border-line-2 hover:text-ink-1'}"
				>
					{t('volumes.existingVolume')}
				</button>
				<button
					onclick={() => { attachMode = 'new'; }}
					class="text-xs px-2 py-1 rounded border transition-colors {attachMode === 'new' ? 'text-warm-text border-action-warm bg-surface-selected/20' : 'text-ink-2 border-line-2 hover:text-ink-1'}"
				>
					{t('volumes.createVolume')}
				</button>
			</div>

			{#if attachMode === 'existing'}
				{#if s.availableVolumes.length === 0}
					<p class="text-sm text-ink-2">{t('volumes.noAvailableVolumes')}</p>
				{:else}
					<div class="flex gap-2">
						<select
							bind:value={selectedVolumeId}
							class="flex-1 bg-surface-selected border border-line-2 text-ink-1 text-sm rounded px-2 py-1.5 focus:outline-none focus:border-action-warm"
						>
							<option value="">{t('volumes.selectPlaceholder')}</option>
							{#each s.availableVolumes as vol}
								<option value={vol.id}>{vol.name || vol.id.slice(0, 8)} ({vol.size}GB)</option>
							{/each}
						</select>
						<button
							onclick={handleAttachVolume}
							disabled={!selectedVolumeId || s.actioning === 'attach-vol'}
							class="text-xs text-warm-text hover:text-warm-text-hover px-3 py-1.5 border border-action-warm hover:border-action-warm rounded transition-colors disabled:text-ink-3 disabled:border-line-2"
						>
							{#if s.actioning === 'attach-vol'}<ActivityIndicator size="xs" label={t('volumes.attaching')} />{:else}{t('volumes.attach')}{/if}
						</button>
					</div>
				{/if}
			{:else}
				<div class="space-y-2">
					<div class="flex gap-2">
						<input
							bind:value={newVolName}
							type="text"
							placeholder={t('volumes.namePlaceholder')}
							class="flex-1 bg-surface-selected border border-line-2 text-ink-1 text-sm rounded px-2 py-1.5 focus:outline-none focus:border-action-warm"
						/>
						<input
							bind:value={newVolSize}
							type="number"
							min="1"
							placeholder={t('volumes.sizePlaceholder')}
							class="w-24 bg-surface-selected border border-line-2 text-ink-1 text-sm rounded px-2 py-1.5 focus:outline-none focus:border-action-warm"
						/>
						<button
							onclick={handleCreateAndAttach}
							disabled={!newVolName.trim() || newVolSize < 1 || s.actioning === 'create-vol'}
							class="text-xs text-green-400 hover:text-green-300 px-3 py-1.5 border border-green-900 hover:border-green-700 rounded transition-colors disabled:text-ink-3 disabled:border-line-2 whitespace-nowrap"
						>
							{#if s.actioning === 'create-vol'}<ActivityIndicator size="xs" label={t('volumes.creating')} />{:else}{t('volumes.createAndAttach')}{/if}
						</button>
					</div>
				</div>
			{/if}
		</div>
	{/if}

	{#if s.volumes.length === 0}
		<p class="text-sm text-ink-2">{t('volumes.empty')}</p>
	{:else}
		<ResponsiveTable>
			{#snippet cards()}
				{#each s.volumes as vol (vol.volume_id)}
					{@const reason = expansionReason(vol.volume_id)}
					<CompactResourceCard>
						<div class="flex min-w-0 flex-wrap items-start justify-between gap-2"><a class="min-h-11 min-w-0 break-all text-sm font-medium text-warm-text hover:text-warm-text-hover" title={vol.name || vol.volume_id} href="/dashboard/volumes/{vol.volume_id}"><span class="line-clamp-2">{vol.name || vol.volume_id.slice(0, 12) + '...'}</span></a>{#if vol.status}<StatusChip status={vol.status} />{/if}</div>
						<p class="break-all text-xs text-ink-2">{#if vol.size}{vol.size}GB · {/if}{vol.device}</p>
						{#snippet actions()}
							<Button variant="secondary" size="sm" onclick={() => s.setDeleteOnTermination(vol.volume_id, !vol.delete_on_termination)} disabled={s.actioning === 'dot-' + vol.volume_id} title={t('volumes.toggleTitle')}>{#if s.actioning === 'dot-' + vol.volume_id}<ActivityIndicator size="xs" label={t('volumes.updating')} />{:else}{vol.delete_on_termination ? t('volumes.deleteOnTermination') : t('volumes.keep')}{/if}</Button>
							<Button variant="secondary" size="sm" onclick={() => openExpansion(vol.volume_id)} disabled={!!reason || !!extendLoading || !!s.actioning} ariaBusy={extendLoading === vol.volume_id} title={reason ? t(reason) : t('volumes.extend')}>{#if extendLoading === vol.volume_id}<ActivityIndicator size="xs" label={t('volumes.extendLoading')} />{:else}{t('volumes.extend')}{/if}</Button>
							<Button variant="secondary" size="sm" onclick={() => s.detachVolume(vol.volume_id)} disabled={s.actioning === 'detach-' + vol.volume_id}>{#if s.actioning === 'detach-' + vol.volume_id}<ActivityIndicator size="xs" label={t('volumes.detaching')} />{:else}{t('volumes.detach')}{/if}</Button>
						{/snippet}
						{#snippet details()}<p class="break-all font-mono text-xs">{vol.volume_id}</p>{/snippet}
					</CompactResourceCard>
				{/each}
			{/snippet}
		<div class="space-y-2">
			{#each s.volumes as vol}
				{@const reason = expansionReason(vol.volume_id)}
				<div class="flex flex-wrap items-center justify-between gap-3 bg-surface-sunken/50 rounded px-3 py-2">
					<div class="flex flex-wrap items-center gap-4 min-w-0">
						<span class="text-xs font-mono text-warm-text hover:text-warm-text-hover">
							<a href="/dashboard/volumes/{vol.volume_id}">{vol.name || vol.volume_id.slice(0, 12) + '...'}</a>
						</span>
						{#if vol.size}
							<span class="text-xs text-ink-2">{vol.size}GB</span>
						{/if}
						<span class="text-xs font-mono text-ink-2">{vol.device}</span>
						{#if vol.status}
							<StatusChip status={vol.status} />
						{/if}
						<button
							type="button"
							onclick={() => s.setDeleteOnTermination(vol.volume_id, !vol.delete_on_termination)}
							disabled={s.actioning === 'dot-' + vol.volume_id}
							title={t('volumes.toggleTitle')}
							class="text-xs px-1.5 py-0.5 rounded transition-colors disabled:opacity-50 cursor-pointer
								{vol.delete_on_termination
									? 'text-red-300 bg-red-900/30 hover:bg-red-900/50 border border-red-800/50'
									: 'text-ink-2 bg-surface-sunken hover:bg-surface-selected border border-line-2'}"
						>
							{#if s.actioning === 'dot-' + vol.volume_id}
								<ActivityIndicator size="xs" label={t('volumes.updating')} />
							{:else}
								{vol.delete_on_termination ? t('volumes.deleteOnTermination') : t('volumes.keep')}
							{/if}
						</button>
					</div>
					<div class="flex flex-wrap items-center gap-2">
						<Button
							variant="secondary"
							size="sm"
							onclick={() => openExpansion(vol.volume_id)}
							disabled={!!reason || !!extendLoading || !!s.actioning}
							ariaBusy={extendLoading === vol.volume_id}
							title={reason ? t(reason) : t('volumes.extend')}
						>
							{#if extendLoading === vol.volume_id}
								<ActivityIndicator size="xs" label={t('volumes.extendLoading')} />
							{:else}
								{t('volumes.extend')}
							{/if}
						</Button>
					<button
						onclick={() => s.detachVolume(vol.volume_id)}
						disabled={s.actioning === 'detach-' + vol.volume_id}
						class="text-xs text-orange-400 hover:text-orange-300 px-2 py-1 border border-orange-900 hover:border-orange-700 rounded transition-colors disabled:text-ink-3"
					>
						{#if s.actioning === 'detach-' + vol.volume_id}<ActivityIndicator size="xs" label={t('volumes.detaching')} />{:else}{t('volumes.detach')}{/if}
					</button>
					</div>
				</div>
			{/each}
		</div>
		</ResponsiveTable>
		{#if s.instance?.status !== 'SHUTOFF'}
			<p class="mt-3 text-xs text-ink-2">{t('volumes.extendOfflineRequired')}</p>
		{/if}
	{/if}
	{#if extendError}<Alert tone="danger" class="mt-3">{extendError}</Alert>{/if}
</div>

<VolumeExtendModal
	volume={visibleExtendTarget}
	projectId={s.effectiveProjectId}
	onclose={closeExpansion}
	onsuccess={onExpanded}
/>
