<script lang="ts">
	import { t } from '$lib/i18n/ns/common';
	import type { ResourceSort } from '$lib/utils/resourceSort';
	import Field from './Field.svelte';
	import SelectInput from './SelectInput.svelte';

	let { value = $bindable<ResourceSort>('created_desc'), id, onchange }: {
		value?: ResourceSort;
		id: string;
		onchange?: () => void;
	} = $props();
</script>

<Field label={t('sort.label')} for={id} class="min-w-0 w-full sm:w-auto">
	<SelectInput {id} bind:value onchange={(event) => { value = (event.target as HTMLSelectElement).value as ResourceSort; onchange?.(); }} class="min-h-11 md:min-h-0">
		<option value="created_desc">{t('sort.newest')}</option>
		<option value="created_asc">{t('sort.oldest')}</option>
		<option value="name_asc">{t('sort.nameAsc')}</option>
		<option value="name_desc">{t('sort.nameDesc')}</option>
	</SelectInput>
</Field>
