<script lang="ts">
	import { intlLocale } from '$lib/i18n/runtime.svelte';
	import { createTableView, type TableViewState } from '$lib/utils/tableView.svelte';
	import TableColumnHeader from '$lib/components/ui/TableColumnHeader.svelte';
	import TableViewControls from '$lib/components/ui/TableViewControls.svelte';
	import RegexSearch from '$lib/components/ui/RegexSearch.svelte';
	import ResponsiveTable from '$lib/components/ui/ResponsiveTable.svelte';
	import CompactResourceCard from '$lib/components/ui/CompactResourceCard.svelte';
	import { untrack } from 'svelte';
	import { quotaFields, nativeQuotaKey, type QuotaMap, type ProjectQuotas, type QuotaField, type QuotaSection } from '$lib/api/workspaceIam';
	import { t } from '$lib/i18n/ns/workspace-iam';
	import Button from '$lib/components/ui/Button.svelte';
	import Alert from '$lib/components/ui/Alert.svelte';
	import TableShell from '$lib/components/ui/TableShell.svelte';
	import TextInput from '$lib/components/ui/TextInput.svelte';
	let { values, native = null, projectMode = false, disabled = false, onSave, viewState }: { viewState?: { searches: Record<string, string>; sections: Record<string, TableViewState> }; values: QuotaMap; native?: ProjectQuotas | null; projectMode?: boolean; disabled?: boolean; onSave: (values: QuotaMap) => void } = $props();
	let draft = $state<Record<QuotaField, string>>(untrack(() => Object.fromEntries(Object.values(quotaFields).flat().map(field => [field, values[field] == null ? '' : String(values[field])])) as Record<QuotaField, string>));
	let error = $state('');
	const uid = $props.id();
	const sections = Object.entries(quotaFields);
	function save() {
		if (disabled) return;
		const next: QuotaMap = {};
		for (const [field, input] of Object.entries(draft)) {
			const text = input.trim();
			if (!text) continue;
			if (!/^(?:-1|0|[1-9]\d*)$/.test(text) || !Number.isSafeInteger(Number(text))) { error = t('invalidLimit'); return; }
			if (!projectMode || Number(text) !== values[field as QuotaField]) next[field as QuotaField] = Number(text);
		}
		if (projectMode && !Object.keys(next).length) { error = t('noChanges'); return; }
		error = ''; onSave(next);
	}
	let localViewState = $state<{ searches: Record<string, string>; sections: Record<string, TableViewState> }>({ searches: {}, sections: {} });
	const tableState = untrack(() => viewState ?? localViewState);
	for (const [key] of sections) { tableState.searches[key] ??= ''; tableState.sections[key] ??= { sort: null, filters: {} }; }
	const sectionViews = Object.fromEntries(sections.map(([section, fields]) => [section, createTableView<QuotaField>({ rows: () => fields, locale: () => intlLocale(), search: () => tableState.searches[section], searchable: field => [field, t(`field.${field}`)], state: tableState.sections[section], columns: () => [
		{ key: 'metric', label: t('metric'), value: field => t(`field.${field}`) },
		{ key: 'limit', label: t('limit'), value: field => draft[field] === '' ? null : Number(draft[field]) },
		...(projectMode ? [
			{ key: 'inUse', label: t('inUse'), value: (field: QuotaField) => native?.[section as QuotaSection]?.[nativeQuotaKey(field)]?.in_use },
			{ key: 'reserved', label: t('reserved'), value: (field: QuotaField) => native?.[section as QuotaSection]?.[nativeQuotaKey(field)]?.reserved }
		] : [])
	] })]));
</script>

<div class="space-y-3">
	<p class="text-sm text-ink-2">{t(projectMode ? 'projectHelp' : 'policyHelp')}</p>
	{#if error}<Alert tone="danger">{error}</Alert>{/if}
	{#each sections as [section]}
		<section class="space-y-2">
			<h3 class="text-sm font-semibold text-ink-0">{t(`service.${section as QuotaSection}`)}</h3>
			{#if projectMode && !native?.availability[section as QuotaSection]}<Alert tone="warning">{native?.errors[section as QuotaSection] === 'service_disabled' ? t('disabledService') : t('unknownService')}</Alert>{/if}
			<RegexSearch id={`${uid}-search-${section}`} bind:value={tableState.searches[section]} /><TableViewControls view={sectionViews[section]} />
<ResponsiveTable>
				{#snippet cards()}
					{#each sectionViews[section].rows as field (field)}
						{@const entry = native?.[section as QuotaSection]?.[nativeQuotaKey(field)]}
						<CompactResourceCard>
							<label for={`${uid}-${field}`} class="text-sm font-medium">{t(`field.${field}`)}</label>
							{#if !projectMode || entry}<label for={`${uid}-${field}`} class="text-xs text-ink-2">{t('limit')}</label><TextInput id={`${uid}-${field}`} bind:value={draft[field]} disabled={disabled} inputmode="numeric" placeholder={t(projectMode ? 'unchanged' : 'notConfigured')} />{#if entry}<p class="text-xs text-ink-2">{t('observed')}: {entry.limit === -1 ? t('unlimited') : entry.limit}</p>{/if}{:else}<p class="text-xs">{native?.availability[section as QuotaSection] ? t('unsupported') : t('unknown')}</p>{/if}
							{#snippet details()}<code class="text-xs">{field}</code>{#if projectMode}<p class="text-xs">{t('inUse')}: {entry?.in_use ?? t('unknown')} · {t('reserved')}: {entry?.reserved ?? t('unknown')}</p>{/if}{/snippet}
						</CompactResourceCard>
					{/each}
				{/snippet}
			<TableShell><table><thead><tr><TableColumnHeader view={sectionViews[section]} columnKey="metric" /><TableColumnHeader view={sectionViews[section]} columnKey="limit" />{#if projectMode}<TableColumnHeader view={sectionViews[section]} columnKey="inUse" /><TableColumnHeader view={sectionViews[section]} columnKey="reserved" />{/if}</tr></thead><tbody>
				{#each sectionViews[section].rows as field (field)}
					{@const entry = native?.[section as QuotaSection]?.[nativeQuotaKey(field)]}
					<tr><td><label for={`${uid}-${field}`}>{t(`field.${field}`)}</label><code class="block text-xs text-ink-2">{field}</code></td>
						<td>{#if !projectMode || entry}<TextInput id={`${uid}-${field}`} bind:value={draft[field]} disabled={disabled} inputmode="numeric" placeholder={t(projectMode ? 'unchanged' : 'notConfigured')} />{#if entry}<span class="text-xs text-ink-2">{t('observed')}: {entry.limit === -1 ? t('unlimited') : entry.limit}</span>{/if}{:else}<span>{native?.availability[section as QuotaSection] ? t('unsupported') : t('unknown')}</span>{/if}</td>
						{#if projectMode}<td>{entry?.in_use ?? t('unknown')}</td><td>{entry?.reserved ?? t('unknown')}</td>{/if}
					</tr>
				{/each}
			</tbody></table></TableShell>
			</ResponsiveTable>
		</section>
	{/each}
	<Button disabled={disabled} onclick={save}>{t('save')}</Button>
</div>
