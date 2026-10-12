<script lang="ts">
	import { auth } from '$lib/stores/auth';
	import { api, ApiError } from '$lib/api/client';
	import type { Volume } from '$lib/types/volume';
	import { dialogFocus } from '$lib/utils/dialogFocus';
	import { t } from '$lib/i18n/ns/volume';
	import ActivityIndicator from '$lib/components/ui/ActivityIndicator.svelte';
	import Alert from '$lib/components/ui/Alert.svelte';

	let { volume, onclose, onsuccess }: {
		volume: Volume | null;
		onclose: () => void;
		onsuccess: () => void;
	} = $props();

	let name = $state('');
	let description = $state('');
	let incremental = $state(false);
	let force = $state(false);
	const forceRequired = $derived(volume?.status === 'in-use');
	let creating = $state(false);
	let error = $state('');

	function defaultName(vol: Volume): string {
		const now = new Date();
		const pad = (n: number) => String(n).padStart(2, '0');
		const ts = `${now.getFullYear()}${pad(now.getMonth()+1)}${pad(now.getDate())}-${pad(now.getHours())}${pad(now.getMinutes())}`;
		return `${vol.name || vol.id.slice(0, 8)}-backup-${ts}`;
	}

	$effect(() => {
		if (volume) {
			name = defaultName(volume);
			description = '';
			incremental = false;
			force = false;
			error = '';
		}
	});

	async function createBackup() {
		if (!volume || creating || !name.trim() || (forceRequired && !force)) return;
		creating = true;
		error = '';
		try {
			await api.post(
				'/api/v1/volumes/backups',
				{ volume_id: volume.id, name, description: description || null, incremental, force: forceRequired && force },
				$auth.token ?? undefined,
				$auth.projectId ?? undefined,
			);
			onsuccess();
		} catch (e) {
			error = e instanceof ApiError ? e.message : t('backupModal.createFailed');
		} finally {
			creating = false;
		}
	}
</script>

{#if volume}
<!-- svelte-ignore a11y_click_events_have_key_events -->
<!-- svelte-ignore a11y_no_static_element_interactions -->
<div
	use:dialogFocus={{ enabled: true, onEscape: () => onclose() }}
	class="fixed inset-0 bg-surface-scrim/60 flex items-center justify-center z-50"
	onclick={onclose}
	role="dialog"
	aria-modal="true"
	tabindex="-1"
>
	<div
		class="bg-surface-base border border-line-2 rounded-xl p-6 w-full max-w-md max-h-[calc(100dvh-2rem)] overflow-y-auto mx-4 shadow-[var(--shadow-restraint)]"
		onclick={(e) => e.stopPropagation()}
		role="none"
	>
		<h2 class="text-lg font-semibold text-ink-0 mb-5">{t('backupModal.title')}</h2>
		<div class="space-y-4">
			<div>
				<div class="block text-xs text-ink-2 mb-1.5 uppercase tracking-wide">{t('backupModal.volumeLabel')}</div>
				<div class="bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-2 text-sm">
					{volume.name || volume.id.slice(0, 8)} <span class="text-ink-2">{t('backupModal.sizeSummary', { size: volume.size })}</span>
				</div>
			</div>
			<div>
				<label class="block text-xs text-ink-2 mb-1.5 uppercase tracking-wide">{t('backupModal.nameLabel')}
					<input
						bind:value={name}
						type="text"
						placeholder={t('backupModal.namePlaceholder')}
						class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-0 text-sm focus:outline-none focus:border-action-warm mt-1.5"
					/>
				</label>
			</div>
			<div>
				<label class="block text-xs text-ink-2 mb-1.5 uppercase tracking-wide">{t('backupModal.descriptionLabel')}
					<input
						bind:value={description}
						type="text"
						class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-0 text-sm focus:outline-none focus:border-action-warm mt-1.5"
					/>
				</label>
			</div>
			<div class="flex items-center gap-2">
				<input type="checkbox" id="backup-incremental" bind:checked={incremental} class="rounded border-line-2" />
				<label for="backup-incremental" class="text-sm text-ink-2">{t('backupModal.incrementalLabel')}</label>
			</div>
			{#if forceRequired}
				<Alert tone="warning" title={t('backupForce.title')}>
					<p id="backup-force-warning">{t('backupForce.warning')}</p>
				</Alert>
				<label class="flex min-h-11 items-center gap-3 text-sm text-ink-1">
					<input type="checkbox" bind:checked={force} disabled={creating} aria-describedby="backup-force-warning" class="shrink-0 rounded border-line-2" />
					<span>{t('backupForce.enable')}</span>
				</label>
			{/if}
		</div>
		{#if error}<div class="mt-4 text-red-400 text-xs bg-red-900/20 border border-red-800 rounded px-3 py-2">{error}</div>{/if}
		<div class="flex justify-end gap-3 mt-6">
			<button onclick={onclose} class="px-4 py-2 text-sm text-ink-2 hover:text-ink-0 transition-colors">{t('backupModal.cancel')}</button>
			<button
				onclick={createBackup}
				disabled={creating || !name.trim() || (forceRequired && !force)}
				class="inline-flex items-center gap-1.5 px-5 py-2 bg-action-warm hover:bg-action-warm-hover disabled:bg-surface-selected disabled:text-ink-3 text-action-on-warm text-sm font-medium rounded-lg transition-colors"
			>{#if creating}<ActivityIndicator size="xs" tone="ink" />{/if}{creating ? t('backupModal.creating') : t('backupModal.create')}</button>
		</div>
	</div>
</div>
{/if}
