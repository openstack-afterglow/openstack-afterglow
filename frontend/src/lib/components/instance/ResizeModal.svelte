<script lang="ts">
	import { confirmDialog } from '$lib/stores/confirm.svelte';
	import { useInstanceDetailController } from '$lib/stores/instanceDetailController.svelte';
	import Modal from '$lib/components/ui/Modal.svelte';
	import Alert from '$lib/components/ui/Alert.svelte';

	interface Props {
		onClose: () => void;
		preselectFlavorId?: string;
	}

	let { onClose, preselectFlavorId = '' }: Props = $props();

	const s = useInstanceDetailController();

	let resizeFlavorId = $state('');
	let resizeConfirming = $state(false);
	let selectedFlavor = $derived(s.resizeFlavors.find(f => f.id === resizeFlavorId));
	let selectionAllowed = $derived(!!selectedFlavor && selectedFlavor.id !== s.instance?.flavor_id && (!!s.instance?.flavor_id || selectedFlavor.name !== s.instance?.flavor_name) && selectedFlavor.eligibility?.selectable !== false);
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
	function blockerLabel(code: string) {
		switch (code) {
			case 'instances_insufficient': return 'VM 쿼터 부족';
			case 'cores_insufficient': return 'vCPU 쿼터 부족';
			case 'ram_insufficient': return 'RAM 쿼터 부족';
			case 'gpu_insufficient': return 'GPU 쿼터 부족';
			case 'compute_quota_unavailable': return 'Compute 쿼터 확인 불가';
			case 'same_flavor': return '현재 플레이버';
			case 'gpu_quota_unavailable': return 'GPU 쿼터 확인 불가';
			case 'disk_shrink': return '디스크 축소 불가';
			default: return code.replaceAll('_', ' ');
		}
	}

	function unavailableReason(f: (typeof s.resizeFlavors)[number]) {
		if (f.id === s.instance?.flavor_id || (!s.instance?.flavor_id && f.name === s.instance?.flavor_name)) return '현재 플레이버';
		if (f.eligibility?.selectable === false) {
			return f.eligibility.blockers.length
				? f.eligibility.blockers.map(b => blockerLabel(b.code)).join(', ')
				: '선택 불가';
		}
		return '';
	}

	async function handleResize() {
		if (!selectionAllowed || s.resizeLoading || s.resizeFlavorsLoading || resizeConfirming) return;
		const flavorLabel = formatFlavorLabel(selectedFlavor!);

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
		<p class="text-xs text-ink-2 mb-5">플레이버를 변경합니다. 완료 후 '리사이즈 확인' 또는 '되돌리기'를 선택하세요.</p>
		{#if s.resizeError}
			<Alert tone="danger" class="mb-4">{s.resizeError}</Alert>
		{/if}
		<div class="space-y-4">
			<div>
				<label for="resize-flavor" class="block text-xs text-ink-2 mb-1.5 uppercase tracking-wide">새 플레이버</label>
				<select id="resize-flavor" bind:value={resizeFlavorId} disabled={s.resizeFlavorsLoading} class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-0 text-sm focus:outline-none focus:border-action-warm">
					<option value="">플레이버 선택</option>
					{#each s.resizeFlavors as f}
						{@const reason = unavailableReason(f)}
						<option value={f.id} disabled={!!reason}>
							{formatFlavorLabel(f)}{reason ? ` [${reason}]` : ''}
						</option>
					{/each}
				</select>
			</div>
		</div>
		<div class="flex justify-end gap-3 mt-6">
			<button onclick={onClose} class="px-4 py-2 bg-surface-selected hover:bg-surface-selected text-ink-0 text-sm font-medium rounded-lg">취소</button>
			<button
				onclick={handleResize}
				disabled={s.resizeLoading || s.resizeFlavorsLoading || resizeConfirming || !selectionAllowed}
				class="px-4 py-2 bg-action-warm hover:bg-action-warm-hover text-action-on-warm text-sm font-medium rounded-lg disabled:opacity-30"
			>
				{resizeConfirming ? '확인 대기 중...' : s.resizeLoading ? '리사이즈 중...' : '리사이즈'}
			</button>
		</div>
	</div>
</Modal>
