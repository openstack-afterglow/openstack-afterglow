<script lang="ts">
	import { t as tr } from '$lib/i18n/ns/database';
	import { useDbCreate } from '$lib/stores/dbCreateStore.svelte';
	const s = useDbCreate();
</script>

<div class="space-y-3">
	<p class="text-xs text-ink-2">
		{tr('wizard.networkHelp')}
	</p>
	{#if s.networks.length === 0}
		<p class="text-ink-2 text-sm">{tr('wizard.noNetworks')}</p>
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
					<span class="text-xs text-ink-2 font-mono">{net.id.slice(0, 8)}…</span>
				</label>
			{/each}
		</div>
	{/if}
</div>
