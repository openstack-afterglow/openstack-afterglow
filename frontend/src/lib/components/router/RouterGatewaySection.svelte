<script lang="ts">
	import Button from '$lib/components/ui/Button.svelte';
	import { useRouterDetailController } from '$lib/stores/routerDetailController.svelte';

	const s = useRouterDetailController();
</script>

<section class="bg-surface-base border border-line rounded-lg p-5 mb-4">
	<div class="flex items-center justify-between mb-3">
		<h4 class="font-semibold text-ink-0 text-sm">외부 게이트웨이</h4>
		<div class="flex gap-2">
			{#if s.router!.external_gateway_network_id}
				<button
					onclick={() => s.removeGateway()}
					disabled={s.saving}
					class="text-red-400 hover:text-red-300 text-xs px-2 py-1 rounded border border-red-900 hover:border-red-700 disabled:border-line-2 transition-colors"
				>게이트웨이 제거</button>
			{:else}
				<button
					onclick={() => s.showSetGateway = !s.showSetGateway}
					class="text-action-warm hover:text-action-warm-hover text-xs px-2 py-1 rounded border border-action-warm hover:border-action-warm transition-colors"
				>게이트웨이 설정</button>
			{/if}
		</div>
	</div>

	{#if s.router!.external_gateway_network_id}
		<div class="text-sm">
			<span class="text-ink-2">네트워크: </span>
			<span class="text-orange-300">{s.router!.external_gateway_network_name || s.router!.external_gateway_network_id}</span>
		</div>
	{:else}
		<p class="text-sm text-ink-3">외부 게이트웨이가 설정되지 않았습니다.</p>
	{/if}

	{#if s.showSetGateway}
		<div class="mt-4 flex gap-2">
			<select bind:value={s.selectedExtNetId} class="flex-1 bg-surface-sunken border border-line-2 rounded px-3 py-2 text-sm text-ink-1">
				<option value="">외부 네트워크 선택</option>
				{#each s.externalNetworks as net}
					<option value={net.id}>{net.name || net.id.slice(0, 12)}</option>
				{/each}
			</select>
			<Button onclick={() => s.setGateway()} disabled={!s.selectedExtNetId || s.saving} size="sm">설정</Button>
			<button onclick={() => s.showSetGateway = false} class="text-ink-2 hover:text-ink-1 text-sm px-2">취소</button>
		</div>
	{/if}
</section>
