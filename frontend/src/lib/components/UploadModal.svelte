<script lang="ts">
	import { uploadQueue } from '$lib/stores/uploadQueue';

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

	function handleKeydown(e: KeyboardEvent) {
		if (e.key === 'Escape') onClose();
	}
</script>

<div
	class="fixed inset-0 bg-surface-scrim/60 flex items-center justify-center z-50"
	onclick={onClose}
	role="dialog"
	aria-modal="true"
	tabindex="-1"
	onkeydown={handleKeydown}
>
	<div
		class="bg-surface-base border border-line-2 rounded-xl p-6 w-full max-w-md mx-4 shadow-[var(--shadow-restraint)]"
		onclick={(e) => e.stopPropagation()}
		role="none"
		onkeydown={(e) => e.stopPropagation()}
	>
		<h2 class="text-lg font-semibold text-ink-0 mb-4">파일 업로드</h2>

		<div class="space-y-3">
			<input
				type="file"
				multiple
				onchange={(e) => {
					files = (e.target as HTMLInputElement).files;
					error = '';
				}}
				class="w-full text-sm text-ink-2 file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-sm file:bg-surface-selected file:text-ink-0 hover:file:bg-surface-selected"
			/>
			{#if error}
				<p class="text-red-400 text-xs">{error}</p>
			{/if}
		</div>

		<div class="flex justify-end gap-2 mt-5">
			<button
				onclick={onClose}
				class="px-4 py-2 text-sm text-ink-2 hover:text-ink-0 border border-line-2 rounded-lg transition-colors"
			>취소</button>
			<button
				onclick={enqueue}
				disabled={!files || files.length === 0}
				class="px-4 py-2 text-sm bg-indigo-600 hover:bg-indigo-500 disabled:bg-surface-selected disabled:text-ink-3 text-ink-0 rounded-lg transition-colors"
			>업로드</button>
		</div>
	</div>
</div>
