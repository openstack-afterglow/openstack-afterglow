<script lang="ts">
	import { t } from '$lib/i18n/ns/admin-storage';
	import Field from '$lib/components/ui/Field.svelte';
	import SelectInput from '$lib/components/ui/SelectInput.svelte';

	let {
		value,
		options = [10, 20, 30],
		onChange,
	}: {
		value: number;
		options?: number[];
		onChange: (n: number) => void;
	} = $props();
</script>

<Field label={t('volumeList.pageSize')} for="admin-volume-page-size">
	<SelectInput id="admin-volume-page-size" value={String(value)} onchange={(event) => onChange(Number((event.target as HTMLSelectElement).value))}>
		{#each options as n}<option value={String(n)}>{n}</option>{/each}
	</SelectInput>
</Field>
