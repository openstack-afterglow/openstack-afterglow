<script lang="ts">
	import type { DesignTone } from '$lib/design/tokens';
	import type { Snippet } from 'svelte';

	interface Props {
		tone?: DesignTone;
		size?: 'xs' | 'sm';
		dot?: boolean;
		class?: string;
		children: Snippet;
	}

	let { tone = 'neutral', size = 'sm', dot = false, class: className = '', children }: Props = $props();
</script>

<span class="pill pill-{tone} pill-{size} {className}">
	{#if dot}
		<span class="pill-dot" aria-hidden="true"></span>
	{/if}
	{@render children()}
</span>

<style>
	.pill {
		display: inline-flex;
		align-items: center;
		gap: 0.25rem;
		border-radius: 999px;
		font-weight: 500;
		border: 1px solid transparent;
		line-height: 1.6;
		white-space: nowrap;
	}
	.pill-xs { padding: 0.0625rem 0.375rem; font-size: var(--type-identifier); }
	.pill-sm { padding: 0.125rem 0.5rem; font-size: var(--type-support); }
	.pill-dot {
		width: 0.375rem;
		height: 0.375rem;
		border-radius: 999px;
		background: currentColor;
	}
	.pill-accent {
		background: color-mix(in oklab, var(--color-accent) 14%, transparent);
		color: var(--color-accent);
		border-color: color-mix(in oklab, var(--color-accent) 30%, transparent);
	}
	.pill-warm {
		background: color-mix(in oklab, var(--color-warm) 14%, transparent);
		color: var(--color-warm-text);
		border-color: color-mix(in oklab, var(--color-warm) 30%, transparent);
	}
	.pill-success {
		background: color-mix(in oklab, var(--color-state-success) 14%, transparent);
		color: var(--color-state-success-text);
		border-color: color-mix(in oklab, var(--color-state-success) 30%, transparent);
	}
	.pill-warning {
		background: color-mix(in oklab, var(--color-state-warning) 14%, transparent);
		color: var(--color-state-warning-text);
		border-color: color-mix(in oklab, var(--color-state-warning) 30%, transparent);
	}
	.pill-danger {
		background: color-mix(in oklab, var(--color-state-danger) 14%, transparent);
		color: var(--color-state-danger-text);
		border-color: color-mix(in oklab, var(--color-state-danger) 30%, transparent);
	}
	.pill-info {
		background: color-mix(in oklab, var(--color-state-info) 14%, transparent);
		color: var(--color-state-info-text);
		border-color: color-mix(in oklab, var(--color-state-info) 30%, transparent);
	}
	.pill-neutral {
		background: color-mix(in oklab, var(--color-state-neutral) 14%, transparent);
		color: var(--color-state-neutral-text);
		border-color: color-mix(in oklab, var(--color-state-neutral) 30%, transparent);
	}
	.pill-admin-tone {
		background: var(--admin-tone-soft);
		color: var(--color-state-warning-text);
		border-color: var(--admin-tone-ring);
	}
</style>
