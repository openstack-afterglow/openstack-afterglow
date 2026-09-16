<script lang="ts">
	import DetailHeader from '$lib/components/ui/DetailHeader.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import { useRouterDetailController } from '$lib/stores/routerDetailController.svelte';

	const s = useRouterDetailController();
</script>

<DetailHeader
	title={s.router!.name || s.router!.id.slice(0, 12)}
	subtitle={s.router!.id}
	status={s.router!.status}
>
	{#snippet actions()}
		{#if s.canManageRouter}
			<Button variant="danger-outline" size="sm" disabled={s.saving} onclick={() => s.deleteRouter()}>삭제</Button>
		{/if}
	{/snippet}
</DetailHeader>
