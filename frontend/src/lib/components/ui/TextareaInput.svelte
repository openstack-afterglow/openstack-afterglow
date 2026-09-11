<script lang="ts">
	interface Props {
		value?: string;
		id?: string;
		rows?: number;
		placeholder?: string;
		disabled?: boolean;
		required?: boolean;
		ariaLabel?: string;
		ariaDescribedBy?: string;
		ariaInvalid?: boolean;
		class?: string;
	}

	let {
		value = $bindable(''),
		id,
		rows = 4,
		placeholder,
		disabled = false,
		required = false,
		ariaLabel,
		ariaDescribedBy,
		ariaInvalid = false,
		class: className = '',
	}: Props = $props();
</script>

<textarea {id} {rows} bind:value {placeholder} {disabled} {required} aria-label={ariaLabel} aria-describedby={ariaDescribedBy} aria-invalid={ariaInvalid || undefined} class="control textarea-input {className}"></textarea>

<style>
	.control {
		width: 100%;
		border-radius: 0.375rem;
		border: 1px solid var(--color-line-2);
		background: var(--color-surface-sunken);
		color: var(--color-ink-0);
		padding: 0.5rem 0.75rem;
		font-size: 0.875rem;
		line-height: 1.45;
		transition: border-color var(--motion-duration-fast) var(--motion-ease-standard), box-shadow var(--motion-duration-fast) var(--motion-ease-standard), background var(--motion-duration-fast) var(--motion-ease-standard);
		resize: vertical;
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
