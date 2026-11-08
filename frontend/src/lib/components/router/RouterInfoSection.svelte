<script lang="ts">
	import { t } from '$lib/i18n/ns/network-resources';
	import DetailHeader from '$lib/components/ui/DetailHeader.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import LoadingState from '$lib/components/ui/LoadingState.svelte';
	import { createPendingAction } from '$lib/components/network/pendingAction.svelte';
	import { useRouterDetailController } from '$lib/stores/routerDetailController.svelte';

	let { highlightDelete = false }: { highlightDelete?: boolean } = $props();
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
			<Button variant="danger-outline" size="sm" disabled={s.saving} ariaBusy={deletingRouter} dataTour={highlightDelete ? 'routers-delete' : undefined} onclick={() => pending.run('delete', () => s.deleteRouter())}>{#if deletingRouter}<LoadingState variant="control" label="" />{/if}{deletingRouter ? t('network.actions.deleting') : t('router.actions.delete')}</Button>
		{/if}
	{/snippet}
</DetailHeader>
