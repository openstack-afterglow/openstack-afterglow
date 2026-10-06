<script lang="ts">
	import { confirmDialog } from '$lib/stores/confirm.svelte';
	import { useInstanceDetailController } from '$lib/stores/instanceDetailController.svelte';
	import Modal from '$lib/components/ui/Modal.svelte';
	import Alert from '$lib/components/ui/Alert.svelte';
	import { t } from '$lib/i18n/ns/instance';
	import { t as tc } from '$lib/i18n/ns/common';
	import ActivityIndicator from '$lib/components/ui/ActivityIndicator.svelte';

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
		return t('resize.flavorLabel', { name: f.name, vcpus: f.vcpus, ram: ramLabel });
	}
	function blockerLabel(code: string) {
		switch (code) {
			case 'instances_insufficient': return t('resize.blocker.instancesInsufficient');
			case 'cores_insufficient': return t('resize.blocker.coresInsufficient');
			case 'ram_insufficient': return t('resize.blocker.ramInsufficient');
			case 'gpu_insufficient': return t('resize.blocker.gpuInsufficient');
			case 'compute_quota_unavailable': return t('resize.blocker.computeQuotaUnavailable');
			case 'same_flavor': return t('resize.currentFlavor');
			case 'gpu_quota_unavailable': return t('resize.blocker.gpuQuotaUnavailable');
			case 'disk_shrink': return t('resize.blocker.diskShrink');
			default: return code.replaceAll('_', ' ');
		}
	}

	function unavailableReason(f: (typeof s.resizeFlavors)[number]) {
		if (f.id === s.instance?.flavor_id || (!s.instance?.flavor_id && f.name === s.instance?.flavor_name)) return t('resize.currentFlavor');
		if (f.eligibility?.selectable === false) {
			return f.eligibility.blockers.length
				? f.eligibility.blockers.map(b => blockerLabel(b.code)).join(', ')
				: t('resize.unavailable');
		}
		return '';
	}

	async function handleResize() {
		if (!selectionAllowed || s.resizeLoading || s.resizeFlavorsLoading || resizeConfirming) return;
		const flavorLabel = formatFlavorLabel(selectedFlavor!);

		resizeConfirming = true;
		try {
			const confirmed = await confirmDialog(
				t('resize.confirmMessage', { flavorLabel })
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
		<h2 id="instance-resize-title" class="text-lg font-semibold text-ink-0 mb-1">{t('resize.title')}</h2>
		<p class="text-xs text-ink-2 mb-5">{t('resize.description')}</p>
		{#if s.resizeError}
			<Alert tone="danger" class="mb-4">{s.resizeError}</Alert>
		{/if}
		<div class="space-y-4">
			<div>
				<label for="resize-flavor" class="block text-xs text-ink-2 mb-1.5 uppercase tracking-wide">{t('resize.newFlavor')}</label>
				<select id="resize-flavor" bind:value={resizeFlavorId} disabled={s.resizeFlavorsLoading} class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-0 text-sm focus:outline-none focus:border-action-warm">
					<option value="">{t('resize.selectFlavor')}</option>
					{#each s.resizeFlavors as f}
						{@const reason = unavailableReason(f)}
						<option value={f.id} disabled={!!reason}>
							{reason ? t('resize.unavailableFlavorLabel', { flavorLabel: formatFlavorLabel(f), reason }) : formatFlavorLabel(f)}
						</option>
					{/each}
				</select>
				{#if s.resizeFlavorsLoading}<ActivityIndicator class="mt-2" label={`${t('resize.newFlavor')} · ${tc('state.loading')}`} />{/if}
			</div>
		</div>
		<div class="flex justify-end gap-3 mt-6">
			<button onclick={onClose} class="px-4 py-2 bg-surface-selected hover:bg-surface-selected text-ink-0 text-sm font-medium rounded-lg">{t('resize.cancel')}</button>
			<button
				onclick={handleResize}
				disabled={s.resizeLoading || s.resizeFlavorsLoading || resizeConfirming || !selectionAllowed}
				class="px-4 py-2 bg-action-warm hover:bg-action-warm-hover text-action-on-warm text-sm font-medium rounded-lg disabled:opacity-30"
			>
				{#if s.resizeLoading}<ActivityIndicator size="xs" label={t('resize.resizing')} />{:else if resizeConfirming}<ActivityIndicator size="xs" variant="dots" label={t('resize.awaitingConfirmation')} />{:else}{t('resize.submit')}{/if}
			</button>
		</div>
	</div>
</Modal>
