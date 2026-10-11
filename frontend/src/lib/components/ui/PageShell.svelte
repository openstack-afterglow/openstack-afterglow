<script lang="ts">
	import type { Snippet } from 'svelte';
	interface Props {
		class?: string;
		children: Snippet;
	}

	let { class: className = '', children }: Props = $props();
</script>

<div class="page-shell p-4 md:p-6 {className}">
	{@render children()}
</div>

<style>
	.page-shell {
		box-sizing: border-box;
		min-width: 0;
		width: 100%;
		max-width: var(--app-content-max-width);
		margin-inline: auto;
	}
</style>
