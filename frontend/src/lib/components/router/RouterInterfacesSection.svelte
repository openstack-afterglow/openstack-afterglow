<script lang="ts">
	import { t } from '$lib/i18n/ns/network-resources';
	import RouterInterfaceAddForm from './RouterInterfaceAddForm.svelte';
	import { useRouterDetailController } from '$lib/stores/routerDetailController.svelte';

	const s = useRouterDetailController();
</script>

<section class="bg-surface-base border border-line rounded-lg p-5">
	<div class="flex items-center justify-between mb-3">
		<h4 class="font-semibold text-ink-0 text-sm">{t('router.interfaces.title', { count: s.router!.interfaces.length })}</h4>
		{#if s.canManageRouter}
			<button
				onclick={() => s.showAddInterface = !s.showAddInterface}
				class="text-warm-text hover:text-warm-text-hover text-xs px-2 py-1 rounded border border-action-warm hover:border-action-warm transition-colors"
			>{t('router.interfaces.addShort')}</button>
		{/if}
	</div>

	{#if s.showAddInterface}
		<RouterInterfaceAddForm />
	{/if}

	{#if s.router!.interfaces.length === 0}
		<p class="text-sm text-ink-2">{t('router.interfaces.empty')}</p>
	{:else}
		<div class="space-y-2">
			{#each s.router!.interfaces as iface}
				<div class="flex items-center justify-between bg-surface-sunken/50 rounded-lg px-4 py-3">
					<div class="text-sm">
						<div class="text-ink-0 font-medium">{iface.subnet_name || iface.subnet_id.slice(0, 12)}</div>
						<div class="text-ink-2 text-xs font-mono mt-0.5">{iface.ip_address}</div>
					</div>
					{#if s.canManageRouter}
						<button
							onclick={() => s.removeInterface(iface.subnet_id)}
							disabled={s.saving}
							class="text-red-400 hover:text-red-300 disabled:text-ink-3 text-xs px-2 py-1 rounded border border-red-900 hover:border-red-700 disabled:border-line-2 transition-colors"
						>{t('router.interfaces.remove')}</button>
					{/if}
				</div>
			{/each}
		</div>
	{/if}
</section>
