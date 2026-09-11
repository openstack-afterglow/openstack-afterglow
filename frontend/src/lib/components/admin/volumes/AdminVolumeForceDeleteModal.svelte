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
			forceDeleteError = e instanceof ApiError ? e.message : '강제 삭제 실패';
		} finally {
			forceDeleting = false;
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
			class="bg-surface-base border border-rose-800 rounded-xl p-6 w-full max-w-sm mx-4 shadow-[var(--shadow-restraint)]"
			onclick={(e) => e.stopPropagation()}
			role="none"
			onkeydown={(e) => e.stopPropagation()}
		>
			<h2 class="text-lg font-semibold text-rose-400 mb-3">볼륨 강제 삭제</h2>
			<p class="text-sm text-ink-2 mb-2">
				<span class="text-ink-0 font-mono">{volume.name || volume.id.slice(0, 8)}</span>
				({volume.status})
			</p>
			<p class="text-xs text-rose-400 mb-1">상태 무관 강제 삭제. Cinder DB row 정리 목적이며 Ceph backend가 NotFound인 경우에만 사용하세요.</p>
			<p class="text-xs text-ink-3 mb-4">attached 볼륨은 거부됩니다.</p>
			{#if forceDeleteError}
				<div class="bg-red-900/40 border border-red-700 text-red-300 rounded-lg px-4 py-3 text-sm mb-4">{forceDeleteError}</div>
			{/if}
			<div class="flex justify-end gap-3">
				<button onclick={onClose} class="px-4 py-2 bg-surface-selected hover:bg-surface-selected text-ink-0 text-sm font-medium rounded-lg">취소</button>
				<button onclick={confirmForceDelete} disabled={forceDeleting} class="px-4 py-2 bg-rose-600 hover:bg-rose-500 text-ink-0 text-sm font-medium rounded-lg disabled:opacity-30">{forceDeleting ? '삭제 중...' : '강제 삭제'}</button>
			</div>
		</div>
	</div>
{/if}
