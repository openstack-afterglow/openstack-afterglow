<script lang="ts">
	import { t } from '$lib/i18n/ns/network-resources';
	import AutoRefreshControl from '$lib/components/AutoRefreshControl.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import { goto } from '$app/navigation';
	import { useRouterDetailController } from '$lib/stores/routerDetailController.svelte';

	interface Props {
		onClose?: () => void;
		routerId: string;
		ar: { active: boolean; intervalSeconds: number; intervalOptions: number[] };
	}

	let { onClose, routerId, ar }: Props = $props();
	const s = useRouterDetailController();
</script>

<div class="flex items-center justify-between mb-6 border-b border-line pb-4">
	<h2 class="text-xl font-bold text-ink-0">{t('router.header.title')}</h2>
	<div class="flex items-center gap-2">
		<AutoRefreshControl
			bind:active={ar.active}
			bind:intervalSeconds={ar.intervalSeconds}
			intervalOptions={ar.intervalOptions}
			refreshing={s.loading}
			onManualRefresh={() => s.fetchRouter()}
		/>
		<Button variant="outline" size="xs" onclick={() => goto(`/dashboard/network/routers/${routerId}`)}>{t('router.header.fullView')}</Button>
	</div>
</div>
