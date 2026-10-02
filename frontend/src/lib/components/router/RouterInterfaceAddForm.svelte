<script lang="ts">
	import { t } from '$lib/i18n/ns/network-resources';
	import Button from '$lib/components/ui/Button.svelte';
	import { useRouterDetailController } from '$lib/stores/routerDetailController.svelte';

	const s = useRouterDetailController();
</script>

<div class="mb-4 p-4 bg-surface-sunken/60 border border-line-2 rounded-lg">
	<div class="flex gap-2 mb-2">
		<select bind:value={s.selectedNetId} class="flex-1 bg-surface-sunken border border-line-2 rounded px-3 py-2 text-sm text-ink-1">
			<option value="">{t('router.interfaces.selectNetwork')}</option>
			{#each s.availableNetworks as net}
				<option value={net.id}>{net.name || net.id.slice(0, 12)}</option>
			{/each}
		</select>
		<select bind:value={s.selectedSubnetId} disabled={!s.allSubnets.length} class="flex-1 bg-surface-sunken border border-line-2 rounded px-3 py-2 text-sm text-ink-1 disabled:opacity-50">
			<option value="">{t('router.interfaces.selectSubnet')}</option>
			{#each s.allSubnets as subnet}
				<option value={subnet.id}>{subnet.name || subnet.cidr}</option>
			{/each}
		</select>
	</div>
	<div class="flex gap-2">
		<Button onclick={() => s.addInterface()} disabled={!s.canAddInterface} size="sm">{t('router.interfaces.add')}</Button>
		<button onclick={() => { s.showAddInterface = false; s.selectedNetId = ''; }} class="text-ink-2 hover:text-ink-1 text-sm px-2">{t('router.actions.cancel')}</button>
	</div>
</div>
