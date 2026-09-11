<script lang="ts">
	import type { AdminNetwork } from '$lib/types/networks';

	let {
		network,
		onClose,
		onSave,
	}: {
		network: AdminNetwork | null;
		onClose: () => void;
		onSave: (id: string, form: { name: string; is_shared: boolean }) => Promise<string | true>;
	} = $props();

	let editName = $state('');
	let editShared = $state(false);
	let saving = $state(false);
	let error = $state('');

	$effect(() => {
		if (network) {
			editName = network.name;
			editShared = network.is_shared;
			error = '';
			saving = false;
		}
	});

	async function save() {
		if (!network) return;
		saving = true;
		error = '';
		const result = await onSave(network.id, { name: editName, is_shared: editShared });
		if (result === true) {
			onClose();
		} else {
			error = result;
		}
		saving = false;
	}
</script>

{#if network}
	<div
		class="fixed inset-0 bg-surface-scrim/60 flex items-center justify-center z-50"
		onclick={(event) => { if (event.target === event.currentTarget) (onClose)(); }}
		role="dialog"
		onkeydown={(e) => e.key === 'Escape' && onClose()}
		tabindex="-1"
	>
		<div class="bg-surface-base border border-line-2 rounded-xl p-6 w-full max-w-md mx-4 shadow-[var(--shadow-restraint)]">
			<h2 class="text-lg font-semibold text-ink-0 mb-5">네트워크 수정</h2>
			{#if error}<div class="bg-red-900/40 border border-red-700 text-red-300 rounded-lg px-4 py-3 text-sm mb-4">{error}</div>{/if}
			<div class="space-y-4">
				<div>
					<label class="block text-xs text-ink-2 mb-1.5 uppercase tracking-wide" for="field-adminnetworkeditmodal-55">이름</label>
					<input id="field-adminnetworkeditmodal-55" bind:value={editName} type="text" class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-0 text-sm focus:outline-none focus:border-action-warm" />
				</div>
				<label class="flex items-center gap-2 text-sm text-ink-2 cursor-pointer">
					<input type="checkbox" bind:checked={editShared} class="rounded" /> 공유
				</label>
			</div>
			<div class="flex justify-end gap-3 mt-6">
				<button onclick={onClose} class="px-4 py-2 bg-surface-selected hover:bg-surface-selected text-ink-0 text-sm font-medium rounded-lg">취소</button>
				<button onclick={save} disabled={saving} class="px-4 py-2 bg-action-warm hover:bg-action-warm-hover text-ink-0 text-sm font-medium rounded-lg disabled:opacity-30">
					{saving ? '수정 중...' : '수정'}
				</button>
			</div>
		</div>
	</div>
{/if}
