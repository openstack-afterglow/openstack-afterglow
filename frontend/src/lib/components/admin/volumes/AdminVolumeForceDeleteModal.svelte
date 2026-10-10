<script lang="ts">
	import ActivityIndicator from '$lib/components/ui/ActivityIndicator.svelte';
	import { auth } from '$lib/stores/auth';
	import { api, ApiError } from '$lib/api/client';
	import { dialogFocus } from '$lib/utils/dialogFocus';
	import { t } from '$lib/i18n/ns/admin-storage';
	import { volumeStatusLabel } from './AdminVolumeStatusSummary.svelte';

	interface AdminVolume {
		id: string;
		name: string;
		status: string;
		size: number;
		project_id: string | null;
		created_at: string | null;
		bootable?: boolean;
	}

	let {
		volume,
		onClose,
		onSuccess,
	}: {
		volume: AdminVolume | null;
		onClose: () => void;
		onSuccess: () => void;
	} = $props();

	const token = $derived($auth.token ?? undefined);
	const projectId = $derived($auth.projectId ?? undefined);

	let forceDeleting = $state(false);
	let forceDeleteError = $state('');

	$effect(() => {
		if (volume) forceDeleteError = '';
	});

	async function confirmForceDelete() {
		if (!volume) return;
		forceDeleting = true;
		forceDeleteError = '';
		try {
			await api.post(`/api/v1/admin/volumes/${volume.id}/force-delete`, {}, token, projectId);
			onSuccess();
			onClose();
		} catch (e) {
			forceDeleteError = e instanceof ApiError ? e.message : t('volumeForceDelete.failed');
		} finally {
			forceDeleting = false;
		}
	}
</script>

{#if volume}
	<!-- svelte-ignore a11y_click_events_have_key_events -->
	<!-- svelte-ignore a11y_no_static_element_interactions -->
	<div
		use:dialogFocus={{ enabled: true, onEscape: () => onClose() }}
		class="fixed inset-0 bg-surface-scrim/60 flex items-center justify-center z-50"
		onclick={onClose}
		role="dialog" aria-modal="true" tabindex="-1"
	>
		<div
			class="bg-surface-base border border-rose-800 rounded-xl p-6 w-full max-w-sm mx-4 shadow-[var(--shadow-restraint)]"
			onclick={(e) => e.stopPropagation()}
			role="none"
		>
			<h2 class="text-lg font-semibold text-state-danger-text mb-3">{t('volumeForceDelete.title')}</h2>
			<p class="text-sm text-ink-2 mb-2">
				<span class="text-ink-0 font-mono">{volume.name || volume.id.slice(0, 8)}</span>
				({volumeStatusLabel(volume.status)})
			</p>
			<p class="text-xs text-state-danger-text mb-1">{t('volumeForceDelete.warning')}</p>
			<p class="text-xs text-ink-2 mb-4">{t('volumeForceDelete.attachedWarning')}</p>
			{#if forceDeleteError}
				<div class="bg-red-900/40 border border-red-700 text-red-300 rounded-lg px-4 py-3 text-sm mb-4">{forceDeleteError}</div>
			{/if}
			<div class="flex justify-end gap-3">
				<button onclick={onClose} class="px-4 py-2 bg-surface-selected hover:bg-surface-selected text-ink-0 text-sm font-medium rounded-lg">{t('volumeForceDelete.cancel')}</button>
				<button onclick={confirmForceDelete} disabled={forceDeleting} class="px-4 py-2 bg-state-danger hover:bg-state-danger/90 text-surface-canvas text-sm font-medium rounded-lg disabled:opacity-30">{#if forceDeleting}<span class="inline-flex items-center gap-2" role="status"><ActivityIndicator size="xs" tone="ink" /><span>{t('volumeForceDelete.deleting')}</span></span>{:else}{t('volumeForceDelete.delete')}{/if}</button>
			</div>
		</div>
	</div>
{/if}
