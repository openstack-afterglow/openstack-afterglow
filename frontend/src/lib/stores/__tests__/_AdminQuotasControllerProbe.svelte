<script lang="ts">
	import { createAdminQuotasController } from '../adminQuotasController.svelte';

	let {
		source,
		onReady,
	}: {
		source: { token?: string; projectId?: string };
		onReady: (controller: ReturnType<typeof createAdminQuotasController>) => void;
	} = $props();

	const controller = createAdminQuotasController({
		token: () => source.token,
		projectId: () => source.projectId,
	});

	$effect(() => { onReady(controller); });
</script>

<div data-testid="quota-loading">{controller.quotaLoading ? 'loading' : 'ready'}</div>
<div data-testid="quota-value">{JSON.stringify(controller.quotas)}</div>
