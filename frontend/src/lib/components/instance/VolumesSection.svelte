<script lang="ts">
	import { useInstanceDetailController } from '$lib/stores/instanceDetailController.svelte';
	import { t } from '$lib/i18n/ns/instance';
	import { ActivityIndicator, StatusChip } from '$lib/components/ui';

	const s = useInstanceDetailController();

	let showAttachVolume = $state(false);
	let attachMode = $state<'existing' | 'new'>('existing');
	let selectedVolumeId = $state('');
	let newVolName = $state('');
	let newVolSize = $state(20);

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
		<div class="space-y-2">
			{#each s.volumes as vol}
				<div class="flex items-center justify-between bg-surface-sunken/50 rounded px-3 py-2">
					<div class="flex items-center gap-4">
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
					<button
						onclick={() => s.detachVolume(vol.volume_id)}
						disabled={s.actioning === 'detach-' + vol.volume_id}
						class="text-xs text-orange-400 hover:text-orange-300 px-2 py-1 border border-orange-900 hover:border-orange-700 rounded transition-colors disabled:text-ink-3"
					>
						{#if s.actioning === 'detach-' + vol.volume_id}<ActivityIndicator size="xs" label={t('volumes.detaching')} />{:else}{t('volumes.detach')}{/if}
					</button>
				</div>
			{/each}
		</div>
	{/if}
</div>
