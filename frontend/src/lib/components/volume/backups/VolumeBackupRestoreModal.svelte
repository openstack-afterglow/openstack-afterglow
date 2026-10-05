<script lang="ts">
	import type { VolumeBackup } from '$lib/types/volume';
	import { dialogFocus } from '$lib/utils/dialogFocus';
	import { t } from '$lib/i18n/ns/volume';
	import RichText from '$lib/i18n/RichText.svelte';

	let {
		open = $bindable(),
		backup,
		onRestore,
	}: {
		open: boolean;
		backup: VolumeBackup | null;
		onRestore: (backupId: string) => Promise<{ volume_id: string; volume_name: string } | string>;
	} = $props();

	let restoring = $state(false);
	let error = $state('');
	let result = $state<{ volume_id: string; volume_name: string } | null>(null);

	$effect(() => {
		if (!open) {
			error = '';
			result = null;
		}
	});

	async function restore() {
		if (!backup) return;
		restoring = true;
		error = '';
		const res = await onRestore(backup.id);
		restoring = false;
		if (typeof res === 'string') {
			error = res;
		} else {
			result = res;
		}
	}
</script>

{#snippet backupName(text: string)}<span class="text-ink-0 font-medium">{text}</span>{/snippet}

{#if open && backup}
	<!-- svelte-ignore a11y_click_events_have_key_events -->
	<!-- svelte-ignore a11y_no_static_element_interactions -->
	<div
		use:dialogFocus={{ enabled: true, onEscape: () => (open = false) }}
		class="fixed inset-0 bg-surface-scrim/60 flex items-center justify-center z-50"
		onclick={() => { open = false; }}
		role="dialog"
		aria-modal="true"
		tabindex="-1"
	>
		<div
			class="bg-surface-base border border-line-2 rounded-xl p-6 w-full max-w-md mx-4 shadow-[var(--shadow-restraint)]"
			onclick={(e) => e.stopPropagation()}
			role="none"
		>
			{#if result}
				<h2 class="text-lg font-semibold text-ink-0 mb-4">{t('backupRestoreModal.completeTitle')}</h2>
				<div class="bg-surface-sunken rounded-lg p-4 mb-4 space-y-2">
					<div class="text-xs text-ink-2">{t('backupRestoreModal.restoredVolumeId')}</div>
					<div class="text-sm text-ink-0 font-mono break-all">{result.volume_id}</div>
					{#if result.volume_name}
						<div class="text-xs text-ink-2 mt-2">{t('backupRestoreModal.volumeName')}</div>
						<div class="text-sm text-ink-0">{result.volume_name}</div>
					{/if}
				</div>
				<p class="text-xs text-yellow-400 mb-4">{t('backupRestoreModal.libraryWarning')}</p>
				<div class="flex justify-end gap-3">
					<button onclick={() => { open = false; }} class="px-4 py-2 text-sm text-ink-2 hover:text-ink-0 transition-colors">{t('backupRestoreModal.close')}</button>
					<a href="/dashboard/instances/new?upper_volume_id={result.volume_id}" class="px-5 py-2 bg-action-warm hover:bg-action-warm-hover text-ink-0 text-sm font-medium rounded-lg transition-colors">{t('backupRestoreModal.createInstance')}</a>
				</div>
			{:else}
				<h2 class="text-lg font-semibold text-ink-0 mb-4">{t('backupRestoreModal.title')}</h2>
				<p class="text-sm text-ink-2 mb-4"><RichText segments={t.rich('backupRestoreModal.description', { name: backup.name || backup.id.slice(0, 8) })} tags={{ backupName }} /></p>
				<p class="text-xs text-yellow-400 mb-4">{t('backupRestoreModal.afterRestoreWarning')}</p>
				{#if error}<div class="mt-2 mb-3 text-red-400 text-xs">{error}</div>{/if}
				<div class="flex justify-end gap-3 mt-2">
					<button onclick={() => { open = false; }} class="px-4 py-2 text-sm text-ink-2 hover:text-ink-0 transition-colors">{t('backupRestoreModal.cancel')}</button>
					<button onclick={restore} disabled={restoring} class="px-5 py-2 bg-action-warm hover:bg-action-warm-hover disabled:bg-surface-selected disabled:text-ink-3 text-ink-0 text-sm font-medium rounded-lg transition-colors">{restoring ? t('backupRestoreModal.restoring') : t('backupRestoreModal.restore')}</button>
				</div>
			{/if}
		</div>
	</div>
{/if}
