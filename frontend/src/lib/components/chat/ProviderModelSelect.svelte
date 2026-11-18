<script lang="ts" generics="T extends ModelCatalogRow">
	import type { Snippet } from 'svelte';
	import { groupModelProviders, modelProviderKey, type ModelCatalogRow, type ModelProvider } from '$lib/api/modelCatalog';
	import { Field, SelectInput } from '$lib/components/ui';
	import { t } from '$lib/i18n/ns/chat-studio';
	import { t as adminT } from '$lib/i18n/ns/admin-chat';

	interface Props {
		models: readonly T[];
		value: number | string | null;
		onSelect: (model: T | null) => void;
		modelLabel: string;
		placeholder?: string;
		id?: string;
		disabled?: boolean;
		picker?: Snippet<[ModelProvider<T>[], (row: T) => void]>;
	}
	let { models, value, onSelect, modelLabel, placeholder, id, disabled = false, picker }: Props = $props();
	const uid = $props.id();
	const providerId = `${uid}-provider`;
	const modelId = $derived(id ?? `${uid}-model`);
	let draftProvider = $state('');
	const groups = $derived(groupModelProviders(models));
	const selected = $derived(models.find((model) => String(model.id) === String(value)));
	const providerKey = $derived(selected ? modelProviderKey(selected)
		: groups.some((group) => group.key === draftProvider) ? draftProvider : groups.length === 1 ? groups[0].key : '');
	const available = $derived(groups.find((group) => group.key === providerKey)?.models ?? []);

	function changeProvider(event: Event) {
		draftProvider = (event.currentTarget as HTMLSelectElement).value;
		onSelect(null);
	}

	function changeModel(event: Event) {
		const id = (event.currentTarget as HTMLSelectElement).value;
		onSelect(available.find((row) => String(row.id) === id) ?? null);
	}
</script>

{#if picker}
	{@render picker(groups, onSelect)}
{:else}
	<div class="grid min-w-0 gap-3">
		<Field for={providerId} label={t('modelPicker.providers')}>
			<SelectInput id={providerId} value={providerKey} disabled={disabled || groups.length === 0} onchange={changeProvider}>
				<option value="" disabled>{adminT('configuration.selectAProvider')}</option>
				{#each groups as group (group.key)}
					<option value={group.key}>{group.label ?? t('modelPicker.otherProvider')}</option>
				{/each}
			</SelectInput>
		</Field>
		<Field for={modelId} label={modelLabel}>
			<SelectInput id={modelId} value={selected ? String(selected.id) : ''} disabled={disabled || available.length === 0} onchange={changeModel}>
				<option value="">{placeholder ?? t('modelSelector.select')}</option>
				{#each available as row (row.id)}
					<option value={String(row.id)}>{row.display_name}</option>
				{/each}
			</SelectInput>
		</Field>
	</div>
{/if}
