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

	let resetStatus = $state('available');
	let resetting = $state(false);
	let resetError = $state('');

	$effect(() => {
		if (volume) {
			resetStatus = 'available';
			resetError = '';
		}
	});

	async function confirmReset() {
		if (!volume) return;
		resetting = true;
		resetError = '';
		try {
			await api.post(`/api/v1/admin/volumes/${volume.id}/reset-status`, { status: resetStatus }, token, projectId);
			onSuccess();
			onClose();
		} catch (e) {
			resetError = e instanceof ApiError ? e.message : '상태 초기화 실패';
		} finally {
			resetting = false;
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
			<h2 class="text-lg font-semibold text-ink-0 mb-3">상태 변경</h2>
			{#if resetError}
				<div class="bg-red-900/40 border border-red-700 text-red-300 rounded-lg px-4 py-3 text-sm mb-4">{resetError}</div>
			{/if}
			<div>
				<label class="block text-xs text-ink-2 mb-1.5 uppercase tracking-wide" for="field-adminvolumeresetstatusmodal-75">변경할 상태</label>
				<select id="field-adminvolumeresetstatusmodal-75" bind:value={resetStatus} class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-0 text-sm focus:outline-none">
					<option value="available">available</option>
					<option value="error">error</option>
					<option value="in-use">in-use</option>
				</select>
			</div>
			<div class="flex justify-end gap-3 mt-5">
				<button onclick={onClose} class="px-4 py-2 bg-surface-selected hover:bg-surface-selected text-ink-0 text-sm font-medium rounded-lg">취소</button>
				<button onclick={confirmReset} disabled={resetting} class="px-4 py-2 bg-yellow-600 hover:bg-yellow-500 text-ink-0 text-sm font-medium rounded-lg disabled:opacity-30">{resetting ? '변경 중...' : '변경'}</button>
			</div>
		</div>
	</div>
{/if}
