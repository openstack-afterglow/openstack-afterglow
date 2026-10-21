<script lang="ts">
	import type { Project } from '$lib/types/quotas';
	import { t } from '$lib/i18n/ns/admin-identity';
	import Field from '$lib/components/ui/Field.svelte';
	import SearchSelect from '$lib/components/ui/SearchSelect.svelte';
	import RichText from '$lib/i18n/RichText.svelte';

	let {
		projects,
		selectedId = '',
		loading = false,
		disabled = false,
		onSelected,
	}: {
		projects: Project[];
		selectedId?: string;
		loading?: boolean;
		disabled?: boolean;
		onSelected: (id: string) => void;
	} = $props();

	const selected = $derived(projects.find(project => project.id === selectedId));
</script>

<div class="min-w-0 w-full">
	<Field for="quota-project-scope" label={t('quotaSelector.label')}>
		<SearchSelect
			id="quota-project-scope"
			value={selectedId}
			options={[{ value: '', label: t('quotaSelector.label') }, ...projects.map(project => ({ value: project.id, label: project.name, description: project.id }))]}
			{loading}
			{disabled}
			placeholder={t('quotaSelector.label')}
			searchPlaceholder={t('quotaSelector.searchPlaceholder')}
			ariaLabel={t('quotaSelector.label')}
			onchange={onSelected}
		/>
	</Field>
	{#if selected}
		{#snippet nameSnippet(text: string)}<span class="text-warm-text">{text}</span>{/snippet}
		<div class="mt-1 text-xs text-ink-2"><RichText segments={t.rich('quotaSelector.selected', { name: selected.name })} tags={{ name: nameSnippet }} /></div>
	{/if}
</div>
