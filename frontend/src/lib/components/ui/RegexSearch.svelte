<script lang="ts">
	import { t } from '$lib/i18n/ns/common';
	import { compileRegexSearch } from '$lib/utils/regexSearch';
	import Field from './Field.svelte';
	import TextInput from './TextInput.svelte';

	interface Props {
		id: string;
		value?: string;
		label?: string;
		placeholder?: string;
		disabled?: boolean;
		class?: string;
	}
	let { id, value = $bindable(''), label, placeholder, disabled = false, class: className = '' }: Props = $props();
	const compiled = $derived(compileRegexSearch(value));
</script>

<Field for={id} label={label ?? t('table.search')} help={t('table.regexHelp')} error={compiled.error ? t('table.regexError') : undefined} class={className}>
	<TextInput {id} type="search" bind:value {disabled} placeholder={placeholder ?? t('table.regexPlaceholder')} ariaInvalid={compiled.error} />
</Field>
