<script lang="ts">
	import type { Volume } from '$lib/types/volume';
	import { formatStorage } from '$lib/utils/format';
	import { dialogFocus } from '$lib/utils/dialogFocus';
	import { t } from '$lib/i18n/ns/volume';
	import { ActivityIndicator, Alert, Button, ProgressTrack } from '$lib/components/ui';

	let {
		open = $bindable(),
		volumes,
		onCreate,
	}: {
		open: boolean;
		volumes: Volume[];
		onCreate: (form: { volume_id: string; name: string; description: string; incremental: boolean; force: boolean }) => Promise<string | true>;
	} = $props();

	let form = $state({ volume_id: '', name: '', description: '', incremental: false, force: false });
	const selectedVolume = $derived(volumes.find((volume) => volume.id === form.volume_id));
	const selectedVolumeId = $derived(selectedVolume?.id);
	const forceRequired = $derived(selectedVolume?.status === 'in-use');
	let creating = $state(false);
	let error = $state('');

	$effect(() => {
		void selectedVolumeId;
		void forceRequired;
		form.force = false;
	});

	$effect(() => {
		if (!open) {
			form = { volume_id: '', name: '', description: '', incremental: false, force: false };
			error = '';
		}
	});

	async function submit() {
		if (!selectedVolume || !form.name.trim() || creating || (forceRequired && !form.force)) return;
		creating = true;
		error = '';
		const result = await onCreate({ ...form, force: forceRequired && form.force });
		creating = false;
		if (result === true) {
			open = false;
		} else {
			error = result;
		}
	}
</script>

{#if open}
	<!-- svelte-ignore a11y_click_events_have_key_events -->
	<!-- svelte-ignore a11y_no_static_element_interactions -->
	<div
		use:dialogFocus={{ enabled: true, onEscape: () => (open = false) }}
		class="motion-fade fixed inset-0 bg-surface-scrim/60 flex items-center justify-center z-50"
		onclick={() => { open = false; }}
		role="dialog"
		aria-modal="true"
		tabindex="-1"
	>
		<div
			class="motion-pop bg-surface-base border border-line-2 rounded-xl p-6 w-full max-w-md max-h-[calc(100dvh-2rem)] overflow-y-auto mx-4 shadow-[var(--shadow-restraint)]"
			onclick={(e) => e.stopPropagation()}
			role="none"
		>
			<h2 class="text-lg font-semibold text-ink-0 mb-5">{t('backupCreateModal.title')}</h2>
			<div class="space-y-4">
				<div>
					<label class="block text-xs text-ink-2 mb-1.5 uppercase tracking-wide">{t('backupCreateModal.volumeLabel')}
						<select bind:value={form.volume_id} disabled={creating} class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-0 text-sm focus:outline-none focus:border-action-warm mt-1.5">
							<option value="">{t('backupCreateModal.volumePlaceholder')}</option>
							{#each volumes as vol}
								<option value={vol.id}>{t('backupCreateModal.volumeOption', { name: vol.name || vol.id.slice(0, 8), size: formatStorage(vol.size) })}</option>
							{/each}
						</select>
					</label>
				</div>
				<div>
					<label class="block text-xs text-ink-2 mb-1.5 uppercase tracking-wide">{t('backupCreateModal.nameLabel')}
						<input bind:value={form.name} type="text" placeholder={t('backupCreateModal.namePlaceholder')} class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-0 text-sm focus:outline-none focus:border-action-warm mt-1.5" />
					</label>
				</div>
				<div>
					<label class="block text-xs text-ink-2 mb-1.5 uppercase tracking-wide">{t('backupCreateModal.descriptionLabel')}
						<input bind:value={form.description} type="text" class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-0 text-sm focus:outline-none focus:border-action-warm mt-1.5" />
					</label>
				</div>
				<div class="flex items-center gap-2">
					<input type="checkbox" id="incremental" bind:checked={form.incremental} class="rounded border-line-2" />
					<label for="incremental" class="text-sm text-ink-2">{t('backupCreateModal.incrementalLabel')}</label>
				</div>
				{#if forceRequired}
					<Alert tone="warning" title={t('backupForce.title')}>
						<p id="backup-create-force-warning">{t('backupForce.warning')}</p>
					</Alert>
					<label class="flex min-h-11 items-center gap-3 text-sm text-ink-1">
						<input type="checkbox" bind:checked={form.force} disabled={creating} aria-describedby="backup-create-force-warning" class="shrink-0 rounded border-line-2" />
						<span>{t('backupForce.enable')}</span>
					</label>
				{/if}
			</div>
			{#if error}<Alert tone="danger" class="mt-4">{error}</Alert>{/if}
			{#if creating}<ProgressTrack value={null} active label={t('backupCreateModal.title')} class="mt-4" />{/if}
			<div class="flex justify-end gap-3 mt-6">
				<button onclick={() => { open = false; }} class="px-4 py-2 text-sm text-ink-2 hover:text-ink-0 transition-colors">{t('backupCreateModal.cancel')}</button>
				<Button onclick={submit} disabled={creating || !selectedVolume || !form.name.trim() || (forceRequired && !form.force)} ariaBusy={creating}>{#if creating}<ActivityIndicator size="xs" tone="ink" />{t('backupCreateModal.creating')}{:else}{t('backupCreateModal.create')}{/if}</Button>
			</div>
		</div>
	</div>
{/if}
