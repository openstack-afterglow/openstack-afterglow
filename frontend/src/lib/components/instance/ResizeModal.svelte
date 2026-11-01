<script lang="ts">
	import { onDestroy, untrack } from 'svelte';
	import { useInstanceDetailController } from '$lib/stores/instanceDetailController.svelte';
	import { createFlavorComposer } from '$lib/stores/flavorComposer';
	import Modal from '$lib/components/ui/Modal.svelte';
	import Alert from '$lib/components/ui/Alert.svelte';
	import LoadingState from '$lib/components/ui/LoadingState.svelte';
	import FlavorComposer from '$lib/components/wizard/FlavorComposer.svelte';
	import { Button } from '$lib/components/ui';
	import { t } from '$lib/i18n/ns/instance';
	import { t as tw } from '$lib/i18n/ns/vm-wizard';
	import { consumerInstanceFlavorLabel } from '$lib/utils/flavorDisplay';
	import type { FlavorOption } from '$lib/types/flavor';

	interface Props {
		onClose: () => void;
		preselectFlavorId?: string;
		adminMode?: boolean;
	}

	let { onClose, preselectFlavorId = '', adminMode = false }: Props = $props();

	const s = useInstanceDetailController();
	const instanceId = s.instance!.id;
	const targetProjectId = s.instance!.project_id ?? null;

	// Catalog choices come from resize-flavors; composed and saved choices are
	// published through the resize-scoped composer and carry their own readback.
	let selectedId = $state<string | null>(null);
	let composed = $state<FlavorOption | null>(null);
	let submitting = $state(false);
	const composer = createFlavorComposer({
		invalidate: () => { selectedId = null; composed = null; },
		select: flavor => {
			if ($composer.selectedId !== flavor.id) return;
			composed = flavor;
			selectedId = flavor.id;
		},
		restore: () => {},
	}, { resizeInstanceId: instanceId });
	$effect(() => { composer.configure(adminMode, adminMode ? targetProjectId : null); });
	onDestroy(() => composer.destroy());

	let preselected = false;
	$effect(() => {
		if (preselected || !preselectFlavorId || !$composer.ready) return;
		preselected = true;
		untrack(() => {
			composer.setMode('catalog');
			selectedId = preselectFlavorId;
			composer.rememberSelection(preselectFlavorId);
		});
	});

	const flavors = $derived(composed ? [composed, ...s.resizeFlavors.filter(f => f.id !== composed!.id)] : s.resizeFlavors);
	const busy = $derived(s.resizeLoading || s.resizeFlavorsLoading || submitting || $composer.saving);
	const canSubmit = $derived.by(() => {
		$composer;
		if (busy || $composer.unknown) return false;
		if (selectedId) return s.selectableResizeFlavor(selectedId, composed?.id === selectedId ? composed : null);
		return $composer.mode === 'compose' && composer.canSave();
	});

	function selectCatalog(id: string) {
		composed = null;
		selectedId = id;
		composer.rememberSelection(id);
	}

	async function submit() {
		if (!canSubmit) return;
		submitting = true;
		try {
			// Direct composition publishes (or reuses) its native shape before the resize.
			if (!selectedId && !(await composer.save())) return;
			if (!selectedId) return;
			if (await s.doResize(selectedId, composed?.id === selectedId ? composed : null)) onClose();
		} finally {
			submitting = false;
		}
	}
</script>

<Modal open={true} onClose={onClose} labelledBy="instance-resize-title">
	<div class="resize-modal-frame bg-surface-base border border-line-2 rounded-xl p-6 shadow-[var(--shadow-restraint)]">
		<h2 id="instance-resize-title" class="text-lg font-semibold text-ink-0 mb-1">{t('resize.title')}</h2>
		<p class="text-xs text-ink-2 mb-1">{t('resize.description')}</p>
		<p class="text-xs text-ink-2 mb-4">{t('resize.current', { flavor: consumerInstanceFlavorLabel(s.instance!) })}</p>
		{#if s.instance?.status === 'ACTIVE'}
			<Alert tone="warning" class="mb-4">{t('resize.runningNotice')}</Alert>
		{/if}
		{#if s.resizeError}
			<Alert tone="danger" class="mb-4">{s.resizeError}</Alert>
		{/if}
		<FlavorComposer
			controller={composer}
			{adminMode}
			{flavors}
			{selectedId}
			onSelect={selectCatalog}
			initialLoading={s.resizeFlavorsLoading && s.resizeFlavors.length === 0}
			refreshing={s.resizeFlavorsLoading}
			refreshError={null}
			onRefresh={() => s.loadResizeFlavors()}
		/>
		<div class="flex flex-wrap justify-end gap-3 mt-6">
			<Button variant="secondary" onclick={onClose}>{t('resize.cancel')}</Button>
			<Button onclick={submit} disabled={!canSubmit} ariaBusy={busy}>
				{#if s.resizeLoading}<LoadingState variant="control" label={t('resize.resizing')} />
				{:else if $composer.saving}<LoadingState variant="control" label={tw('composer.saving')} />
				{:else if submitting}<LoadingState variant="control" label={t('resize.awaitingConfirmation')} />
				{:else}{t('resize.submit')}{/if}
			</Button>
		</div>
	</div>
</Modal>

<style>
	.resize-modal-frame {
		width: 48rem;
		max-width: 100%;
		min-width: 0;
		overflow-wrap: anywhere;
	}
</style>
