<script lang="ts">
	let {
		value,
		options = [10, 20, 30],
		onChange,
	}: {
		value: number;
		options?: number[];
		onChange: (n: number) => void;
	} = $props();
</script>

<div class="flex items-center gap-1 text-xs text-ink-3 max-md:hidden">
	표시:
	{#each options as n}
		<button
			onclick={() => onChange(n)}
			class="px-2 py-0.5 rounded {value === n ? 'bg-action-warm text-ink-0' : 'bg-surface-sunken hover:bg-surface-selected text-ink-2'}"
		>{n}</button>
	{/each}
</div>
