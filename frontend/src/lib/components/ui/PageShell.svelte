<script module lang="ts">
	export type PageShellMax = 'none' | '5xl' | '7xl';
	export type PageShellPadding = 'route' | 'dense' | 'none';
</script>

<script lang="ts">
	import type { Snippet } from 'svelte';
	interface Props {
		max?: PageShellMax;
		padding?: PageShellPadding;
		class?: string;
		children: Snippet;
	}

	let { max = '7xl', padding = 'route', class: className = '', children }: Props = $props();
</script>

<div class="page-shell page-shell-max-{max} page-shell-pad-{padding} {className}">
	{@render children()}
</div>

<style>
	.page-shell {
		width: 100%;
		margin-inline: auto;
	}
	.page-shell-max-none { max-width: none; }
	.page-shell-max-5xl { max-width: 64rem; }
	.page-shell-max-7xl { max-width: 80rem; }
	.page-shell-pad-route { padding: 1rem; }
	.page-shell-pad-dense { padding: 0.75rem; }
	.page-shell-pad-none { padding: 0; }
	@media (min-width: 768px) {
		.page-shell-pad-route { padding: 1.5rem; }
		.page-shell-pad-dense { padding: 1rem; }
	}
</style>
