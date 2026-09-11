<script lang="ts">
	import Button from '$lib/components/ui/Button.svelte';
	import { useRouterDetailController } from '$lib/stores/routerDetailController.svelte';

	const s = useRouterDetailController();
</script>

<div class="mb-4 p-4 bg-surface-sunken/60 border border-line-2 rounded-lg">
	<div class="flex gap-2 mb-2">
		<select bind:value={s.selectedNetId} class="flex-1 bg-surface-sunken border border-line-2 rounded px-3 py-2 text-sm text-ink-1">
			<option value="">네트워크 선택</option>
			{#each s.availableNetworks as net}
				<option value={net.id}>{net.name || net.id.slice(0, 12)}</option>
			{/each}
		</select>
		<select bind:value={s.selectedSubnetId} disabled={!s.allSubnets.length} class="flex-1 bg-surface-sunken border border-line-2 rounded px-3 py-2 text-sm text-ink-1 disabled:opacity-50">
			<option value="">서브넷 선택</option>
			{#each s.allSubnets as subnet}
				<option value={subnet.id}>{subnet.name || subnet.cidr}</option>
			{/each}
		</select>
	</div>
	<div class="flex gap-2">
		<Button onclick={() => s.addInterface()} disabled={!s.canAddInterface} size="sm">추가</Button>
		<button onclick={() => { s.showAddInterface = false; s.selectedNetId = ''; }} class="text-ink-2 hover:text-ink-1 text-sm px-2">취소</button>
	</div>
</div>
