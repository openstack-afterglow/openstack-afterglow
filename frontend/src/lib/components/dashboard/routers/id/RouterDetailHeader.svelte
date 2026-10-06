<script lang="ts">
	import { t } from '$lib/i18n/ns/network-resources';
	import type { RouterDetail } from '$lib/types/router';
	import StatusChip from '$lib/components/ui/StatusChip.svelte';
	import ActivityIndicator from '$lib/components/ui/ActivityIndicator.svelte';
	import { createPendingAction } from '$lib/components/network/pendingAction.svelte';

	let {
		router,
		saving,
		onDelete,
		onBack,
	}: {
		router: RouterDetail;
		saving: boolean;
		onDelete: () => Promise<void>;
		onBack: () => void;
	} = $props();

	const pending = createPendingAction();
	const deletingRouter = $derived(pending.isActive('delete', saving));
</script>

<button onclick={onBack} class="text-sm text-ink-2 hover:text-ink-1 mb-6 inline-flex items-center gap-1">
	{t('router.back')}
</button>

<div class="flex items-start justify-between mb-8">
	<div>
		<h1 class="text-2xl font-bold text-ink-0">{router.name || router.id.slice(0, 12)}</h1>
		<div class="flex items-center gap-3 mt-2">
			<StatusChip status={router.status} />
			<span class="text-xs text-ink-2 font-mono">{router.id}</span>
		</div>
	</div>
	<button
		onclick={() => pending.run('delete', onDelete)}
		disabled={saving}
		aria-busy={deletingRouter}
		class="inline-flex items-center gap-1.5 text-red-400 hover:text-red-300 disabled:text-ink-3 text-sm px-3 py-1.5 rounded border border-red-900 hover:border-red-700 disabled:border-line-2 transition-colors"
	>{#if deletingRouter}<ActivityIndicator size="xs" tone="danger" />{/if}{deletingRouter ? t('network.actions.deleting') : t('router.actions.delete')}</button>
</div>
