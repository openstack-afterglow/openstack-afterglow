<script lang="ts">
	import { useDbCreate } from '$lib/stores/dbCreateStore.svelte';
	const s = useDbCreate();
</script>

<div class="space-y-3">
	<p class="text-xs text-ink-2">
		사용할 네트워크를 선택하세요. 선택하지 않으면 Trove가 기본 네트워크를 사용합니다.
	</p>
	{#if s.networks.length === 0}
		<p class="text-ink-3 text-sm">사용 가능한 네트워크가 없습니다.</p>
	{:else}
		<div class="space-y-2">
			{#each s.networks as net}
				<label
					class="flex items-center gap-3 bg-surface-sunken border border-line-2 rounded-lg px-4 py-3 cursor-pointer hover:border-action-warm/50 transition-colors"
				>
					<input
						type="checkbox"
						checked={s.selectedNics.includes(net.id)}
						onchange={() => s.toggleNic(net.id)}
						class="accent-amber-500"
					/>
					<span class="text-sm text-ink-0">{net.name}</span>
					<span class="text-xs text-ink-3 font-mono">{net.id.slice(0, 8)}…</span>
				</label>
			{/each}
		</div>
	{/if}
</div>
