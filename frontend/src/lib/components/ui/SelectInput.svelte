<script lang="ts">
	import type { Snippet } from 'svelte';

	interface Props {
		value?: string;
		id?: string;
		disabled?: boolean;
		required?: boolean;
		class?: string;
		children: Snippet;
		ariaLabel?: string;
		ariaDescribedBy?: string;
		ariaInvalid?: boolean;
		onchange?: (event: Event) => void;
	}

	let {
		value = $bindable(''),
		id,
		disabled = false,
		required = false,
		class: className = '',
		ariaLabel,
		ariaDescribedBy,
		ariaInvalid = false,
		children,
		onchange,
	}: Props = $props();
	const describedBy = $derived(ariaDescribedBy ?? (id ? `${id}-message` : undefined));
</script>

<select {id} bind:value {disabled} {required} {onchange} aria-label={ariaLabel} aria-describedby={describedBy} aria-invalid={ariaInvalid || undefined} class="control select-input {className}">
	{@render children()}
</select>

<style>
	.control {
		width: 100%;
		border-radius: var(--radius-md);
		border: 1px solid var(--color-line-2);
		background: var(--color-surface-input);
		color: var(--color-ink-0);
		min-height: var(--control-height);
		padding: 0.375rem 0.75rem;
		font-size: var(--type-body);
		line-height: 1.4;
		transition: border-color var(--motion-duration-fast) var(--motion-ease-standard), box-shadow var(--motion-duration-fast) var(--motion-ease-standard), background var(--motion-duration-fast) var(--motion-ease-standard);
	}
	.control:focus-visible {
		outline: none;
		border-color: var(--color-line-2);
		box-shadow: var(--focus-ring);
	}
	.control:disabled {
		background: var(--color-surface-input-disabled);
		border-color: var(--color-line);
		color: var(--color-ink-2);
		cursor: not-allowed;
	}
	@media (max-width: 767px), (pointer: coarse) {
		.control { min-height: var(--control-touch-height); }
	}
</style>
