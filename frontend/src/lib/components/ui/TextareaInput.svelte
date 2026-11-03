<script lang="ts">
	interface Props {
		value?: string;
		id?: string;
		rows?: number;
		placeholder?: string;
		disabled?: boolean;
		required?: boolean;
		maxlength?: number;
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
		maxlength,
		ariaLabel,
		ariaDescribedBy,
		ariaInvalid = false,
		class: className = '',
	}: Props = $props();
	const describedBy = $derived(ariaDescribedBy ?? (id ? `${id}-message` : undefined));
</script>

<textarea {id} {rows} bind:value {placeholder} {disabled} {required} {maxlength} aria-label={ariaLabel} aria-describedby={describedBy} aria-invalid={ariaInvalid || undefined} class="control textarea-input {className}"></textarea>

<style>
	.control {
		width: 100%;
		border-radius: var(--radius-md);
		border: 1px solid var(--color-line-2);
		background: var(--color-surface-input);
		color: var(--color-ink-0);
		padding: 0.5rem 0.75rem;
		font-size: var(--type-body);
		line-height: 1.45;
		transition: border-color var(--motion-duration-fast) var(--motion-ease-standard), box-shadow var(--motion-duration-fast) var(--motion-ease-standard), background var(--motion-duration-fast) var(--motion-ease-standard);
		resize: vertical;
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
</style>
