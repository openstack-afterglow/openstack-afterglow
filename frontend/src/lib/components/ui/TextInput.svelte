<script lang="ts">
	interface Props {
		value?: string;
		id?: string;
		type?: 'text' | 'password' | 'number' | 'email' | 'search' | 'url';
		placeholder?: string;
		disabled?: boolean;
		required?: boolean;
		maxlength?: number;
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
		inputmode,
		ariaLabel,
		ariaDescribedBy,
		ariaInvalid = false,
		element = $bindable(null),
		class: className = '',
		oninput,
		onkeydown,
	}: Props = $props();
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
	{inputmode}
	aria-label={ariaLabel}
	aria-describedby={ariaDescribedBy}
	aria-invalid={ariaInvalid || undefined}
	{oninput}
	{onkeydown}
	class="control text-input {className}"
/>

<style>
	.control {
		width: 100%;
		border-radius: 0.375rem;
		border: 1px solid var(--color-line-2);
		background: var(--color-surface-sunken);
		color: var(--color-ink-0);
		padding: 0.5rem 0.75rem;
		font-size: 0.875rem;
		line-height: 1.4;
		transition: border-color var(--motion-duration-fast) var(--motion-ease-standard), box-shadow var(--motion-duration-fast) var(--motion-ease-standard), background var(--motion-duration-fast) var(--motion-ease-standard);
	}
	.control::placeholder { color: var(--color-ink-3); }
	.control:focus-visible {
		outline: none;
		border-color: var(--color-line-2);
		box-shadow: var(--focus-ring);
	}
	.control:disabled {
		opacity: 0.55;
		cursor: not-allowed;
	}
</style>
