<script lang="ts">
	import { t } from '$lib/i18n/ns/network-resources';
	import DetailHeader from '$lib/components/ui/DetailHeader.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import ActivityIndicator from '$lib/components/ui/ActivityIndicator.svelte';
	import { createPendingAction } from '$lib/components/network/pendingAction.svelte';
	import { useRouterDetailController } from '$lib/stores/routerDetailController.svelte';

	const s = useRouterDetailController();
	const pending = createPendingAction();
	const deletingRouter = $derived(pending.isActive('delete', s.saving));
</script>

<DetailHeader
	title={s.router!.name || s.router!.id.slice(0, 12)}
	subtitle={s.router!.id}
	status={s.router!.status}
>
	{#snippet actions()}
		{#if s.canManageRouter}
			<Button variant="danger-outline" size="sm" disabled={s.saving} ariaBusy={deletingRouter} onclick={() => pending.run('delete', () => s.deleteRouter())}>{#if deletingRouter}<ActivityIndicator size="xs" tone="danger" />{/if}{deletingRouter ? t('network.actions.deleting') : t('router.actions.delete')}</Button>
		{/if}
	{/snippet}
</DetailHeader>
