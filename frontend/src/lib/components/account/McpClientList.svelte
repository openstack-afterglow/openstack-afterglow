<script lang="ts">
	import { t } from '$lib/i18n/ns/account';
	import { t as tc } from '$lib/i18n/ns/common';
	import { t as tp } from '$lib/i18n/ns/public-entry';
	import { intlLocale } from '$lib/i18n/runtime.svelte';
	import type { McpClientObservation } from './McpAccessSection.svelte';
	import RegexSearch from '$lib/components/ui/RegexSearch.svelte';
	import TableViewControls from '$lib/components/ui/TableViewControls.svelte';
	import { createTableView } from '$lib/utils/tableView.svelte';
	import { untrack } from 'svelte';
	import type { TableViewState } from '$lib/utils/tableView.svelte';

	let { observations, state = $bindable() }: { observations: McpClientObservation[]; state: { search: string; table: TableViewState } } = $props();
	const uid = $props.id();
	function date(value: string | null) {
		return value && Number.isFinite(Date.parse(value))
			? new Intl.DateTimeFormat(intlLocale(), { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value))
			: t('mcp.unknown');
	}
	const view = createTableView<McpClientObservation>({
		locale: () => intlLocale(),
		rows: () => observations,
		search: () => state.search,
		state: untrack(() => state.table),
		columns: () => [
			{ key: 'name', label: t('mcp.name'), value: row => row.client_name },
			{ key: 'version', label: tc('table.version'), value: row => row.client_version },
			{ key: 'product', label: tc('table.product'), value: row => row.product },
			{ key: 'kind', label: tc('table.type'), value: row => t(`mcp.clientKind.${row.kind}`) },
			{ key: 'source', label: tc('table.source'), value: row => t(`mcp.clientSource.${row.identity_source}`) },
			{ key: 'browser', label: tc('table.browser'), value: row => row.browser },
			{ key: 'os', label: 'OS', value: row => row.os },
			{ key: 'first', label: tc('table.firstSeen'), value: row => row.first_seen_at ? Date.parse(row.first_seen_at) : null, format: (_value, row) => date(row.first_seen_at) },
			{ key: 'last', label: tc('table.lastUsed'), value: row => row.last_seen_at ? Date.parse(row.last_seen_at) : null, format: (_value, row) => date(row.last_seen_at) },
		],
	});
</script>

<div class="mt-3 min-w-0 space-y-2 border-t border-line pt-2 text-xs text-ink-2" role="group" aria-label={t('mcp.observations')}>
	{#if observations.length === 0}
		<p>{t('mcp.noObservations')}</p>
	{:else}
		<p>{t('mcp.observationHelp')}</p>
		<p>{tp('mcpClients.count', { count: observations.length })}</p>
		<RegexSearch id={`${uid}-search`} bind:value={state.search} />
		<TableViewControls {view} class="" />
		{#if view.rows.length === 0}<p role="status">{tc('table.noMatches')}</p>{/if}
		<ul class="space-y-2">
			{#each view.rows as observation}
				<li class="min-w-0 border-l border-line pl-3 [overflow-wrap:anywhere]">
					<details>
						<summary class="min-h-11 py-3 md:min-h-0 md:py-0 cursor-pointer text-xs text-ink-1 focus-visible:outline-2 focus-visible:outline-accent">
							<span><strong>{observation.client_name || observation.product || t('mcp.unknownClient')}</strong> · <span>{observation.client_name ? t('mcp.clientSource.client_info') : t('mcp.clientEvidence', { source: t(`mcp.clientSource.${observation.identity_source}`) })}</span></span>
							<span class="block">{t('mcp.clientVersion', { version: observation.client_version || t('mcp.unknown') })}{#if observation.client_version && !observation.client_name}{' · '}{t('mcp.clientSource.client_info')}{/if}</span>
						</summary>
						{#if observation.client_name}
							<span><span>{t('mcp.clientInference', { product: observation.product || t('mcp.unknown'), kind: t(`mcp.clientKind.${observation.kind}`) })}</span> · <span>{t('mcp.clientEvidence', { source: t(`mcp.clientSource.${observation.identity_source}`) })}</span></span>
						{:else}
							<span>{t(`mcp.clientKind.${observation.kind}`)}</span>
						{/if}
						<p>{t('mcp.clientPlatform', { browser: observation.browser || t('mcp.unknown'), os: observation.os || t('mcp.unknown') })}</p>
						<p>{t('mcp.clientDates', { first: date(observation.first_seen_at), last: date(observation.last_seen_at) })}</p>
					</details>
				</li>
			{/each}
		</ul>
	{/if}
</div>
