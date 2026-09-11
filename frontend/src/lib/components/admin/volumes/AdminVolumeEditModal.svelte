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

	let editName = $state('');
	let updating = $state(false);
	let editError = $state('');

	$effect(() => {
		if (volume) {
			editName = volume.name;
			editError = '';
		}
	});

	async function updateVolume() {
		if (!volume) return;
		updating = true;
		editError = '';
		try {
			await api.patch(`/api/v1/admin/volumes/${volume.id}`, { name: editName }, token, projectId);
			onSuccess();
			onClose();
		} catch (e) {
			editError = e instanceof ApiError ? e.message : '수정 실패';
		} finally {
			updating = false;
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
			class="bg-surface-base border border-line-2 rounded-xl p-6 w-full max-w-md mx-4 shadow-[var(--shadow-restraint)]"
			onclick={(e) => e.stopPropagation()}
			role="none"
			onkeydown={(e) => e.stopPropagation()}
		>
			<h2 class="text-lg font-semibold text-ink-0 mb-5">볼륨 수정</h2>
			{#if editError}
				<div class="bg-red-900/40 border border-red-700 text-red-300 rounded-lg px-4 py-3 text-sm mb-4">{editError}</div>
			{/if}
			<div class="space-y-4">
				<div>
					<label class="block text-xs text-ink-2 mb-1.5 uppercase tracking-wide" for="field-adminvolumeeditmodal-76">이름</label>
					<input id="field-adminvolumeeditmodal-76" bind:value={editName} type="text" class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-0 text-sm focus:outline-none focus:border-action-warm" />
				</div>
				<div class="text-xs text-ink-3">ID: {volume.id}</div>
			</div>
			<div class="flex justify-end gap-3 mt-6">
				<button onclick={onClose} class="px-4 py-2 bg-surface-selected hover:bg-surface-selected text-ink-0 text-sm font-medium rounded-lg">취소</button>
				<button onclick={updateVolume} disabled={updating} class="px-4 py-2 bg-action-warm hover:bg-action-warm-hover text-ink-0 text-sm font-medium rounded-lg disabled:opacity-30">{updating ? '수정 중...' : '수정'}</button>
			</div>
		</div>
	</div>
{/if}
