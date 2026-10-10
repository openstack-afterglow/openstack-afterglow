<script lang="ts">
	import { uploadQueue } from '$lib/stores/uploadQueue';
	import { dialogFocus } from '$lib/utils/dialogFocus';
	import { t } from '$lib/i18n/ns/object-storage';
	import { ActivityIndicator, Button } from '$lib/components/ui';

	interface Props {
		containerName: string;
		prefix?: string;
		token?: string;
		projectId?: string;
		onSuccess: () => void;
		onClose: () => void;
	}

	const { containerName, prefix = '', token, projectId, onSuccess, onClose }: Props = $props();

	let files = $state<FileList | null>(null);
	let error = $state('');
	let dropActive = $state(false);

	function armDrop(e: DragEvent) {
		if (!e.dataTransfer?.types.includes('Files')) return;
		e.preventDefault();
		dropActive = true;
	}

	function acceptDrop(e: DragEvent) {
		e.preventDefault();
		dropActive = false;
		if (e.dataTransfer?.files.length) {
			files = e.dataTransfer.files;
			error = '';
		}
	}

	function enqueue() {
		if (!files || files.length === 0) return;
		for (const file of Array.from(files)) {
			uploadQueue.enqueue(file, {
				containerName,
				prefix,
				token,
				projectId,
				onComplete: (job) => {
					if (job.status === 'success') onSuccess();
				}
			});
		}
		onClose();
	}

</script>

<!-- svelte-ignore a11y_click_events_have_key_events -->
<!-- svelte-ignore a11y_no_static_element_interactions -->
<div
	use:dialogFocus={{ enabled: true, onEscape: onClose }}
	class="motion-fade fixed inset-0 bg-surface-scrim/60 flex items-center justify-center z-50"
	onclick={onClose}
	role="dialog"
	aria-modal="true"
	tabindex="-1"
>
	<div
		class="motion-pop bg-surface-base border border-line-2 rounded-xl p-6 w-full max-w-md mx-4 shadow-[var(--shadow-restraint)]"
		onclick={(e) => e.stopPropagation()}
		role="none"
		onkeydown={(e) => e.stopPropagation()}
	>
		<h2 class="text-lg font-semibold text-ink-0 mb-4">{t('uploadModal.title')}</h2>

		<div
			class="space-y-3 border-2 border-dashed rounded-lg p-3 transition-colors {dropActive ? 'border-accent bg-surface-selected' : 'border-line'}"
			role="group"
			aria-label={t('uploadModal.selection')}
			ondragenter={armDrop}
			ondragover={armDrop}
			ondragleave={(e) => { if (!e.currentTarget.contains(e.relatedTarget as Node | null)) dropActive = false; }}
			ondrop={acceptDrop}
		>
			{#if dropActive}
				<div class="motion-pop"><ActivityIndicator variant="upload" label={t('views.dragOverlay.dropFiles')} /></div>
			{/if}
			<input
				type="file"
				multiple
				onchange={(e) => {
					files = (e.target as HTMLInputElement).files;
					error = '';
				}}
				class="w-full text-sm text-ink-2 file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-sm file:bg-surface-selected file:text-ink-0 hover:file:bg-surface-selected"
			/>
			{#if files?.length}
				<p class="text-xs text-ink-1">{t('uploadModal.selectedFileCount', { count: files.length })}</p>
			{/if}
			<p class="text-xs text-ink-2">
				{t('uploadModal.inspection')}
			</p>
			{#if error}
				<p class="text-state-danger-text text-xs">{error}</p>
			{/if}
		</div>

		<div class="flex justify-end gap-2 mt-5">
			<button
				onclick={onClose}
				class="px-4 py-2 text-sm text-ink-2 hover:text-ink-0 border border-line-2 rounded-lg transition-colors"
			>{t('uploadModal.cancel')}</button>
			<Button variant="accent" onclick={enqueue} disabled={!files || files.length === 0}>{t('uploadModal.upload')}</Button>
		</div>
	</div>
</div>
