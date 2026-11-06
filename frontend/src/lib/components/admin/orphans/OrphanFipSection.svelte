<script lang="ts">
	import OrphanSection from './OrphanSection.svelte';
	import type { OrphanFipInfo } from '$lib/types/orphan';
	import { t } from '$lib/i18n/ns/admin-storage';
	import type { TableColumn } from '$lib/utils/tableView.svelte';

	let {
		items,
		selected = $bindable(new Set<string>()),
		cleanupDisabled = false,
		onCleanup,
	}: {
		items: OrphanFipInfo[];
		selected: Set<string>;
		cleanupDisabled?: boolean;
		onCleanup: () => void;
	} = $props();
	const columns = $derived<TableColumn<OrphanFipInfo>[]>([
		{ key: 'address', label: t('orphanFip.column.address'), value: (row) => row.address },
		{ key: 'project', label: t('orphanFip.column.project'), value: (row) => row.project_id },
		{ key: 'created', label: t('orphanFip.column.createdAt'), value: (row) => row.created_at?.slice(0, 10) ?? null },
		{ key: 'age', label: t('orphanFip.column.ageDays'), value: (row) => row.age_days },
		{ key: 'id', label: t('orphanFip.column.id'), value: (row) => row.id },
	]);
</script>

<OrphanSection
	title={t('orphanFip.title')}
	{items}
	{columns}
	{cleanupDisabled}
	bind:selected
	emptyMessage={t('orphanFip.empty')}
	{onCleanup}
>
  {#snippet cardSummary(f)}
    <strong class="break-all font-mono text-sm">{f.address}</strong>
    <dl class="text-xs"><dt class="text-ink-2">{t('orphanFip.column.ageDays')}</dt><dd>{f.age_days}</dd></dl>
  {/snippet}
  {#snippet cardDetails(f)}
    <dl class="space-y-2 text-xs"><div><dt class="text-ink-2">{t('orphanFip.column.project')}</dt><dd class="break-all font-mono">{f.project_id ?? '-'}</dd></div><div><dt class="text-ink-2">{t('orphanFip.column.createdAt')}</dt><dd>{f.created_at?.slice(0, 10) ?? '-'}</dd></div><div><dt class="text-ink-2">{t('orphanFip.column.id')}</dt><dd class="break-all font-mono">{f.id}</dd></div></dl>
  {/snippet}
	{#snippet row(f)}
		<td class="py-2 pr-4 font-mono text-green-400">{f.address}</td>
		<td class="py-2 pr-4 text-ink-2 font-mono">{f.project_id?.slice(0, 8) ?? '-'}</td>
		<td class="py-2 pr-4 text-ink-2">{f.created_at?.slice(0, 10) ?? '-'}</td>
		<td class="py-2 pr-4 text-warm-text">{f.age_days}</td>
		<td class="py-2 pr-4 text-ink-2 font-mono">{f.id.slice(0, 8)}</td>
	{/snippet}
</OrphanSection>
