<script lang="ts">
	import RouterInterfaceAddForm from './RouterInterfaceAddForm.svelte';
	import { useRouterDetailController } from '$lib/stores/routerDetailController.svelte';

	const s = useRouterDetailController();
</script>

<section class="bg-surface-base border border-line rounded-lg p-5">
	<div class="flex items-center justify-between mb-3">
		<h4 class="font-semibold text-ink-0 text-sm">인터페이스 ({s.router!.interfaces.length})</h4>
		<button
			onclick={() => s.showAddInterface = !s.showAddInterface}
			class="text-action-warm hover:text-action-warm-hover text-xs px-2 py-1 rounded border border-action-warm hover:border-action-warm transition-colors"
		>+ 추가</button>
	</div>

	{#if s.showAddInterface}
		<RouterInterfaceAddForm />
	{/if}

	{#if s.router!.interfaces.length === 0}
		<p class="text-sm text-ink-3">연결된 인터페이스가 없습니다.</p>
	{:else}
		<div class="space-y-2">
			{#each s.router!.interfaces as iface}
				<div class="flex items-center justify-between bg-surface-sunken/50 rounded-lg px-4 py-3">
					<div class="text-sm">
						<div class="text-ink-0 font-medium">{iface.subnet_name || iface.subnet_id.slice(0, 12)}</div>
						<div class="text-ink-3 text-xs font-mono mt-0.5">{iface.ip_address}</div>
					</div>
					<button
						onclick={() => s.removeInterface(iface.subnet_id)}
						disabled={s.saving}
						class="text-red-400 hover:text-red-300 disabled:text-ink-3 text-xs px-2 py-1 rounded border border-red-900 hover:border-red-700 disabled:border-line-2 transition-colors"
					>제거</button>
				</div>
			{/each}
		</div>
	{/if}
</section>
