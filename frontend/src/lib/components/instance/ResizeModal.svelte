<script lang="ts">
	import { confirmDialog } from '$lib/stores/confirm.svelte';
	import { useInstanceDetailController } from '$lib/stores/instanceDetailController.svelte';
	import Modal from '$lib/components/ui/Modal.svelte';

	interface Props {
		onClose: () => void;
		preselectFlavorId?: string;
	}

	let { onClose, preselectFlavorId = '' }: Props = $props();

	const s = useInstanceDetailController();

	let resizeFlavorId = $state('');
	let resizeConfirming = $state(false);
	let initialized = false;
	$effect(() => {
		if (initialized) return;
		resizeFlavorId = preselectFlavorId;
		initialized = true;
	});

	function formatFlavorLabel(f: { name: string; vcpus: number; ram: number }) {
		const ramLabel = f.ram >= 1024 ? `${(f.ram / 1024).toFixed(0)} GB` : `${f.ram} MB`;
		return `${f.name} (${f.vcpus} vCPU / ${ramLabel} RAM)`;
	}

	async function handleResize() {
		if (!resizeFlavorId || s.resizeLoading || resizeConfirming) return;
		const selectedFlavor = s.resizeFlavors.find((f) => f.id === resizeFlavorId);
		if (selectedFlavor?.eligibility && !selectedFlavor.eligibility.selectable) {
			return;
		}
		const flavorLabel = selectedFlavor ? formatFlavorLabel(selectedFlavor) : resizeFlavorId;

		resizeConfirming = true;
		try {
			const confirmed = await confirmDialog(
				`인스턴스를 다음 플레이버로 리사이즈하시겠습니까?\n${flavorLabel}\n\n요청 후에는 '리사이즈 확인'을 눌러 적용하거나 '되돌리기'로 취소해야 합니다.`
			);
			if (!confirmed) return;

			const ok = await s.doResize(resizeFlavorId);
			if (ok) onClose();
		} finally {
			resizeConfirming = false;
		}
	}
</script>

<Modal open={true} onClose={onClose} labelledBy="instance-resize-title">
	<div class="bg-surface-base border border-line-2 rounded-xl p-6 w-full max-w-md mx-4 shadow-[var(--shadow-restraint)]">
		<h2 id="instance-resize-title" class="text-lg font-semibold text-ink-0 mb-1">인스턴스 리사이즈</h2>
		<p class="text-xs text-ink-3 mb-5">플레이버를 변경합니다. 완료 후 '리사이즈 확인' 또는 '되돌리기'를 선택하세요.</p>
		{#if s.resizeError}
			<div class="bg-red-900/40 border border-red-700 text-red-300 rounded-lg px-4 py-3 text-sm mb-4">{s.resizeError}</div>
		{/if}
		<div class="space-y-4">
			<div>
				<label for="resize-flavor" class="block text-xs text-ink-2 mb-1.5 uppercase tracking-wide">새 플레이버</label>
				<select id="resize-flavor" bind:value={resizeFlavorId} class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-0 text-sm focus:outline-none focus:border-action-warm">
					<option value="">플레이버 선택</option>
					{#each s.resizeFlavors as f}
						<option value={f.id} disabled={f.eligibility ? !f.eligibility.selectable : false}>
							{formatFlavorLabel(f)}{f.eligibility && !f.eligibility.selectable ? ' [쿼터 초과]' : ''}
						</option>
					{/each}
				</select>
			</div>
		</div>
		<div class="flex justify-end gap-3 mt-6">
			<button onclick={onClose} class="px-4 py-2 bg-surface-selected hover:bg-surface-selected text-ink-0 text-sm font-medium rounded-lg">취소</button>
			<button
				onclick={handleResize}
				disabled={s.resizeLoading || resizeConfirming || !resizeFlavorId}
				class="px-4 py-2 bg-action-warm hover:bg-action-warm-hover text-action-on-warm text-sm font-medium rounded-lg disabled:opacity-30"
			>
				{resizeConfirming ? '확인 대기 중...' : s.resizeLoading ? '리사이즈 중...' : '리사이즈'}
			</button>
		</div>
	</div>
</Modal>
