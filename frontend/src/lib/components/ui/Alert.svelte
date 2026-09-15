<script module lang="ts">
	export type AlertTone = 'success' | 'warning' | 'danger' | 'info' | 'neutral';
</script>

<script lang="ts">
	import type { Snippet } from 'svelte';
	interface Props {
		tone?: AlertTone;
		title?: string;
		class?: string;
		children: Snippet;
		actions?: Snippet;
	}

	let { tone = 'danger', title, class: className = '', children, actions }: Props = $props();
</script>

<div class="alert alert-{tone} {className}" role={tone === 'danger' ? 'alert' : 'status'}>
	<div class="alert-body">
		{#if title}
			<p class="alert-title">{title}</p>
		{/if}
		<div class="alert-content">
			{@render children()}
		</div>
	</div>
	{#if actions}
		<div class="alert-actions">
			{@render actions()}
		</div>
	{/if}
</div>

<style>
	.alert {
		display: flex;
		align-items: flex-start;
		justify-content: space-between;
		gap: 1rem;
		border: 1px solid var(--alert-line);
		border-radius: var(--radius-lg);
		background: color-mix(in oklab, var(--alert-tone) 12%, transparent);
		color: var(--alert-tone);
		padding: 0.75rem 1rem;
	}
	.alert-body { min-width: 0; }
	.alert-title {
		margin: 0 0 0.25rem;
		font-size: 0.875rem;
		font-weight: 600;
		color: var(--alert-tone);
	}
	.alert-content {
		font-size: 0.8125rem;
		line-height: 1.5;
		color: color-mix(in oklab, var(--alert-tone) 88%, var(--color-ink-0));
	}
	.alert-actions {
		display: flex;
		flex-shrink: 0;
		gap: 0.5rem;
	}
	.alert-success { --alert-tone: var(--color-state-success); --alert-line: color-mix(in oklab, var(--color-state-success) 32%, transparent); }
	.alert-warning { --alert-tone: var(--color-state-warning); --alert-line: color-mix(in oklab, var(--color-state-warning) 32%, transparent); }
	.alert-danger { --alert-tone: var(--color-state-danger); --alert-line: color-mix(in oklab, var(--color-state-danger) 32%, transparent); }
	.alert-info { --alert-tone: var(--color-state-info); --alert-line: color-mix(in oklab, var(--color-state-info) 32%, transparent); }
	.alert-neutral { --alert-tone: var(--color-state-neutral); --alert-line: color-mix(in oklab, var(--color-state-neutral) 32%, transparent); }
</style>
