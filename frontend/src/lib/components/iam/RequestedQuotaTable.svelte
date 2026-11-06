<script lang="ts">
	import { intlLocale } from '$lib/i18n/runtime.svelte';
	import type { QuotaField, QuotaMap } from '$lib/api/workspaceIam';
	import { t } from '$lib/i18n/ns/workspace-iam';
	import { createTableView } from '$lib/utils/tableView.svelte';
	import TableColumnHeader from '$lib/components/ui/TableColumnHeader.svelte';
	import TableViewControls from '$lib/components/ui/TableViewControls.svelte';
	import RegexSearch from '$lib/components/ui/RegexSearch.svelte';
	import ResponsiveTable from '$lib/components/ui/ResponsiveTable.svelte';
	import CompactResourceCard from '$lib/components/ui/CompactResourceCard.svelte';
	import TableShell from '$lib/components/ui/TableShell.svelte';
	let { requested }: { requested: QuotaMap } = $props();
	const uid = $props.id();
	let search = $state('');
	const rows = $derived(Object.entries(requested));
	const view = createTableView<(typeof rows)[number]>({ rows: () => rows, locale: () => intlLocale(), search: () => search, columns: () => [
		{ key: 'metric', label: t('metric'), value: row => t(`field.${row[0] as QuotaField}`) },
		{ key: 'requested', label: t('requested'), value: row => row[1] }
	] });
	function amount(value: number | null | undefined) { return value == null ? t('unknown') : value === -1 ? t('unlimited') : String(value); }
</script>
<RegexSearch id={uid} bind:value={search} />
<TableViewControls {view} />
<ResponsiveTable>
	{#snippet cards()}{#each view.rows as [field, value]}<CompactResourceCard><h4 class="text-sm font-medium">{t(`field.${field as QuotaField}`)}</h4><p class="text-sm">{t('requested')}: {amount(value)}</p></CompactResourceCard>{/each}{/snippet}
	<TableShell><table><thead><tr><TableColumnHeader {view} columnKey="metric" /><TableColumnHeader {view} columnKey="requested" /></tr></thead><tbody>{#each view.rows as [field, value]}<tr><td>{t(`field.${field as QuotaField}`)}</td><td>{amount(value)}</td></tr>{/each}</tbody></table></TableShell>
</ResponsiveTable>
