<script lang="ts">
	import { auth } from '$lib/stores/auth';
	import { api, ApiError } from '$lib/api/client';

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
			deleteError = e instanceof ApiError ? e.message : '삭제 실패';
		} finally {
			deleting = false;
		}
	}
</script>

{#if volume}
	<!-- svelte-ignore a11y_click_events_have_key_events -->
	<!-- svelte-ignore a11y_no_static_element_interactions -->
	<div
		class="fixed inset-0 bg-surface-scrim/60 flex items-center justify-center z-50"
		onclick={onClose}
		role="dialog" aria-modal="true" tabindex="-1"
		onkeydown={(e) => e.key === 'Escape' && onClose()}
	>
		<div
			class="bg-surface-base border border-line-2 rounded-xl p-6 w-full max-w-sm mx-4 shadow-[var(--shadow-restraint)]"
			onclick={(e) => e.stopPropagation()}
			role="none"
			onkeydown={(e) => e.stopPropagation()}
		>
			<h2 class="text-lg font-semibold text-ink-0 mb-3">볼륨 삭제</h2>
			<p class="text-sm text-ink-2 mb-2"><span class="text-ink-0">{volume.name || volume.id.slice(0, 8)}</span> 볼륨을 삭제하시겠습니까?</p>
			<p class="text-xs text-red-400 mb-4">이 작업은 되돌릴 수 없습니다.</p>
			{#if deleteError}
				<div class="bg-red-900/40 border border-red-700 text-red-300 rounded-lg px-4 py-3 text-sm mb-4">{deleteError}</div>
			{/if}
			<div class="flex justify-end gap-3">
				<button onclick={onClose} class="px-4 py-2 bg-surface-selected hover:bg-surface-selected text-ink-0 text-sm font-medium rounded-lg">취소</button>
				<button onclick={confirmDelete} disabled={deleting} class="px-4 py-2 bg-red-600 hover:bg-red-500 text-ink-0 text-sm font-medium rounded-lg disabled:opacity-30">{deleting ? '삭제 중...' : '삭제'}</button>
			</div>
		</div>
	</div>
{/if}
