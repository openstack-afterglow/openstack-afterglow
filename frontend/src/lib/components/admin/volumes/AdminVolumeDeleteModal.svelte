<script lang="ts">
	import ActivityIndicator from '$lib/components/ui/ActivityIndicator.svelte';
	import { auth } from '$lib/stores/auth';
	import { api, ApiError } from '$lib/api/client';
	import { dialogFocus } from '$lib/utils/dialogFocus';
	import { t } from '$lib/i18n/ns/admin-storage';
	import RichText from '$lib/i18n/RichText.svelte';

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

	let deleting = $state(false);
	let deleteError = $state('');

	$effect(() => {
		if (volume) deleteError = '';
	});

	async function confirmDelete() {
		if (!volume) return;
		deleting = true;
		deleteError = '';
		try {
			await api.delete(`/api/v1/admin/volumes/${volume.id}`, token, projectId);
			onSuccess();
			onClose();
		} catch (e) {
			deleteError = e instanceof ApiError ? e.message : t('volumeDelete.failed');
		} finally {
			deleting = false;
		}
	}
</script>

{#snippet volumeName(text: string)}<span class="text-ink-0">{text}</span>{/snippet}

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
			class="bg-surface-base border border-line-2 rounded-xl p-6 w-full max-w-sm mx-4 shadow-[var(--shadow-restraint)]"
			onclick={(e) => e.stopPropagation()}
			role="none"
		>
			<h2 class="text-lg font-semibold text-ink-0 mb-3">{t('volumeDelete.title')}</h2>
			<p class="text-sm text-ink-2 mb-2"><RichText segments={t.rich('volumeDelete.confirm', { name: volume.name || volume.id.slice(0, 8) })} tags={{ name: volumeName }} /></p>
			<p class="text-xs text-red-400 mb-4">{t('volumeDelete.irreversible')}</p>
			{#if deleteError}
				<div class="bg-red-900/40 border border-red-700 text-red-300 rounded-lg px-4 py-3 text-sm mb-4">{deleteError}</div>
			{/if}
			<div class="flex justify-end gap-3">
				<button onclick={onClose} class="px-4 py-2 bg-surface-selected hover:bg-surface-selected text-ink-0 text-sm font-medium rounded-lg">{t('volumeDelete.cancel')}</button>
				<button onclick={confirmDelete} disabled={deleting} class="px-4 py-2 bg-state-danger hover:bg-state-danger/90 text-surface-canvas text-sm font-medium rounded-lg disabled:opacity-30">{#if deleting}<span class="inline-flex items-center gap-2" role="status"><ActivityIndicator size="xs" tone="ink" /><span>{t('volumeDelete.deleting')}</span></span>{:else}{t('volumeDelete.delete')}{/if}</button>
			</div>
		</div>
	</div>
{/if}
