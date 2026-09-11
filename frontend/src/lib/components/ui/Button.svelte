<script module lang="ts">
	export type ButtonVariant =
		| 'primary'
		| 'accent'
		| 'secondary'
		| 'subtle'
		| 'ghost'
		| 'outline'
		| 'danger'
		| 'danger-outline'
		| 'link';
	export type ButtonSize = 'xs' | 'sm' | 'md' | 'lg' | 'icon';
</script>

<script lang="ts">
	import type { Snippet } from 'svelte';
	interface Props {
		variant?: ButtonVariant;
		size?: ButtonSize;
		type?: 'button' | 'submit' | 'reset';
		disabled?: boolean;
		onclick?: (e: MouseEvent) => void;
		onintent?: () => void;
		href?: string;
		ariaLabel?: string;
		title?: string;
		dataTour?: string;
		class?: string;
		children: Snippet;
	}

	let {
		variant = 'primary',
		size = 'md',
		type = 'button',
		disabled = false,
		onclick,
		onintent,
		href,
		ariaLabel,
		title,
		dataTour,
		class: className = '',
		children,
	}: Props = $props();

	function handleAnchorClick(event: MouseEvent) {
		if (disabled) {
			event.preventDefault();
			event.stopPropagation();
			return;
		}
		onclick?.(event);
	}

	function handleIntent() {
		if (!disabled) onintent?.();
	}
</script>

{#if href}
	<a
		href={disabled ? undefined : href}
		aria-label={ariaLabel}
		aria-disabled={disabled}
		tabindex={disabled ? -1 : undefined}
		data-tour={dataTour}
		{title}
		onclick={handleAnchorClick}
		onpointerenter={handleIntent}
		onfocus={handleIntent}
		class="btn btn-{variant} btn-{size} {className}"
	>
		{@render children()}
	</a>
{:else}
	<button {type} {disabled} aria-label={ariaLabel} data-tour={dataTour} {title} {onclick} onpointerenter={handleIntent} onfocus={handleIntent} class="btn btn-{variant} btn-{size} {className}">
		{@render children()}
	</button>
{/if}

<style>
	.btn {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		gap: 0.375rem;
		border-radius: 0.375rem;
		font-size: 0.8125rem;
		font-weight: 500;
		line-height: 1.2;
		transition:
			background var(--motion-duration-fast) var(--motion-ease-standard),
			border-color var(--motion-duration-fast) var(--motion-ease-standard),
			box-shadow var(--motion-duration-fast) var(--motion-ease-standard),
			color var(--motion-duration-fast) var(--motion-ease-standard),
			filter var(--motion-duration-fast) var(--motion-ease-standard),
			transform var(--motion-duration-fast) var(--motion-ease-standard);
		border: 1px solid transparent;
		cursor: pointer;
		white-space: nowrap;
		text-decoration: none;
	}

	.btn:focus-visible {
		outline: none;
		box-shadow: var(--focus-ring);
	}
	.btn:active:not(:disabled):not([aria-disabled='true']) {
		transform: translateY(1px);
	}

	.btn:disabled,
	.btn[aria-disabled='true'] {
		opacity: 0.45;
		cursor: not-allowed;
		box-shadow: none;
		filter: none;
	}

	.btn-xs { padding: 0.1875rem 0.5rem; font-size: 0.6875rem; }
	.btn-sm { padding: 0.25rem 0.625rem; font-size: 0.75rem; }
	.btn-md { padding: 0.4375rem 0.875rem; font-size: 0.8125rem; }
	.btn-lg { padding: 0.625rem 1.25rem; font-size: 0.875rem; }
	.btn-icon { width: 2rem; height: 2rem; padding: 0; font-size: 0.8125rem; }

	.btn-primary {
		background: var(--color-warm);
		color: var(--color-action-on-warm);
	}
	.btn-primary:hover:not(:disabled):not([aria-disabled='true']) {
		background: color-mix(in oklab, var(--color-warm) 88%, var(--color-ink-0));
	}

	.btn-accent {
		background: var(--color-accent);
		color: var(--color-action-on-accent);
	}
	.btn-accent:hover:not(:disabled):not([aria-disabled='true']) {
		background: color-mix(in oklab, var(--color-accent) 88%, var(--color-ink-0));
	}

	.btn-secondary {
		background: var(--color-surface-raised);
		color: var(--color-ink-1);
		border-color: var(--color-line);
	}
	.btn-secondary:hover:not(:disabled):not([aria-disabled='true']) {
		background: var(--color-surface-sunken);
		color: var(--color-ink-0);
	}

	.btn-subtle {
		background: var(--color-surface-sunken);
		color: var(--color-ink-1);
		border-color: transparent;
	}
	.btn-subtle:hover:not(:disabled):not([aria-disabled='true']) {
		color: var(--color-ink-0);
		background: color-mix(in oklab, var(--color-surface-sunken) 78%, var(--color-ink-0));
	}

	.btn-ghost {
		background: transparent;
		color: var(--color-ink-2);
	}
	.btn-ghost:hover:not(:disabled):not([aria-disabled='true']) {
		background: var(--color-surface-sunken);
		color: var(--color-ink-0);
	}

	.btn-outline {
		background: transparent;
		color: var(--color-ink-1);
		border-color: var(--color-line);
	}
	.btn-outline:hover:not(:disabled):not([aria-disabled='true']) {
		background: var(--color-surface-sunken);
		color: var(--color-ink-0);
	}

	.btn-danger {
		background: var(--color-state-danger);
		color: var(--color-surface-base);
		border-color: color-mix(in oklab, var(--color-state-danger) 85%, var(--color-ink-0));
	}
	.btn-danger:hover:not(:disabled):not([aria-disabled='true']) {
		background: color-mix(in oklab, var(--color-state-danger) 88%, var(--color-ink-0));
	}

	.btn-danger-outline {
		background: color-mix(in oklab, var(--color-state-danger) 15%, transparent);
		color: var(--color-state-danger);
		border-color: color-mix(in oklab, var(--color-state-danger) 35%, transparent);
	}
	.btn-danger-outline:hover:not(:disabled):not([aria-disabled='true']) {
		background: color-mix(in oklab, var(--color-state-danger) 25%, transparent);
	}

	.btn-link {
		padding-inline: 0;
		background: transparent;
		color: var(--color-accent);
		border-color: transparent;
		box-shadow: none;
	}
	.btn-link:hover:not(:disabled):not([aria-disabled='true']) {
		color: color-mix(in oklab, var(--color-accent) 75%, var(--color-ink-0));
		text-decoration: underline;
	}
</style>
