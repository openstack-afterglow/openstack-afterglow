<script lang="ts">
	import type { HTMLInputAttributes } from 'svelte/elements';
	interface Props {
		value?: string;
		id?: string;
		type?: 'text' | 'password' | 'number' | 'email' | 'search' | 'url';
		placeholder?: string;
		disabled?: boolean;
		required?: boolean;
		maxlength?: number;
		step?: number;
		min?: number;
		max?: number;
		autocomplete?: HTMLInputAttributes['autocomplete'];
		inputmode?: 'text' | 'decimal' | 'numeric' | 'search' | 'email' | 'url' | 'tel';
		element?: HTMLInputElement | null;
		ariaLabel?: string;
		ariaDescribedBy?: string;
		ariaInvalid?: boolean;
		class?: string;
		oninput?: (event: Event) => void;
		onkeydown?: (event: KeyboardEvent) => void;
	}

	let {
		value = $bindable(''),
		id,
		type = 'text',
		placeholder,
		disabled = false,
		required = false,
		maxlength,
		step,
		min,
		max,
		autocomplete,
		inputmode,
		ariaLabel,
		ariaDescribedBy,
		ariaInvalid = false,
		element = $bindable(null),
		class: className = '',
		oninput,
		onkeydown,
	}: Props = $props();
	const describedBy = $derived(ariaDescribedBy ?? (id ? `${id}-message` : undefined));
</script>

<input
	bind:this={element}
	{id}
	{type}
	bind:value
	{placeholder}
	{disabled}
	{required}
	{maxlength}
	{step}
	{min}
	{max}
	{autocomplete}
	{inputmode}
	aria-label={ariaLabel}
	aria-describedby={describedBy}
	aria-invalid={ariaInvalid || undefined}
	{oninput}
	{onkeydown}
	class="control text-input {className}"
/>

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
	.control::placeholder { color: var(--color-ink-2); }
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
