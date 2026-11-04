<script lang="ts">
	import type { Snippet } from 'svelte';
	import { experiencePresentation } from '$lib/utils/experiencePresentation';
	import type { ExperienceContext } from '$lib/utils/experience';
	import type { ExperienceMessageMetadata } from '$lib/i18n/experienceMessages';

	interface Props {
		experience?: ExperienceContext;
		experienceMessage?: ExperienceMessageMetadata;
		label: string;
		for?: string;
		help?: string;
		error?: string;
		required?: boolean;
		class?: string;
		children: Snippet;
	}

	let { label, for: forId, help, error, required = false, class: className = '', children, experience, experienceMessage }: Props = $props();
</script>

<div use:experiencePresentation={{ context: experience, message: experienceMessage, state: error ? 'error' : 'ready' }} class="field {className}">
	<label class="field-label" for={forId}>
		<span>{label}</span>
		{#if required}
			<span class="field-required" aria-hidden="true">*</span>
		{/if}
	</label>
	{@render children()}
	{#if error}
		<p id={forId ? `${forId}-message` : undefined} class="field-error" role="alert">{error}</p>
	{:else if help}
		<p id={forId ? `${forId}-message` : undefined} class="field-help">{help}</p>
	{/if}
</div>

<style>
	.field { display: flex; flex-direction: column; gap: 0.375rem; }
	.field-label {
		display: inline-flex;
		align-items: center;
		gap: 0.25rem;
		font-size: var(--type-support);
		font-weight: 500;
		color: var(--color-ink-1);
	}
	.field-required { color: var(--color-state-danger-text); }
	.field-help,
	.field-error {
		margin: 0;
		font-size: var(--type-support);
		line-height: 1.4;
	}
	.field-help { color: var(--color-ink-2); }
	.field-error { color: var(--color-state-danger-text); }
</style>
