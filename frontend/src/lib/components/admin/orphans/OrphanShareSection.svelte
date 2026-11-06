<script lang="ts">
	import OrphanSection from './OrphanSection.svelte';
	import type { OrphanShareInfo } from '$lib/types/orphan';
	import { t } from '$lib/i18n/ns/admin-storage';
	import type { TableColumn } from '$lib/utils/tableView.svelte';

	let {
		items,
		selected = $bindable(new Set<string>()),
		cleanupDisabled = false,
		onCleanup,
	}: {
		items: OrphanShareInfo[];
		selected: Set<string>;
		cleanupDisabled?: boolean;
		onCleanup: () => void;
	} = $props();
	const columns = $derived<TableColumn<OrphanShareInfo>[]>([
		{ key: 'name', label: t('orphanShare.column.name'), value: (row) => row.name },
		{ key: 'size', label: t('orphanShare.column.sizeGb'), value: (row) => row.size_gb },
		{ key: 'status', label: t('orphanShare.column.status'), value: (row) => row.status },
		{ key: 'project', label: t('orphanShare.column.missingProject'), value: (row) => row.project_id },
		{ key: 'created', label: t('orphanShare.column.createdAt'), value: (row) => row.created_at?.slice(0, 10) ?? null },
		{ key: 'age', label: t('orphanShare.column.ageDays'), value: (row) => row.age_days },
		{ key: 'id', label: t('orphanShare.column.id'), value: (row) => row.id },
	]);
</script>

<OrphanSection
	title={t('orphanShare.title')}
	{items}
	{columns}
	{cleanupDisabled}
	bind:selected
	emptyMessage={t('orphanShare.empty')}
	{onCleanup}
>
  {#snippet cardSummary(s)}
    <div class="flex flex-wrap items-center justify-between gap-2"><strong class="break-words text-sm">{s.name ?? '-'}</strong><span class="text-xs text-state-success-text">{s.status}</span></div>
    <dl class="flex flex-wrap gap-3 text-xs"><div><dt class="text-ink-2">{t('orphanShare.column.sizeGb')}</dt><dd>{s.size_gb}</dd></div><div><dt class="text-ink-2">{t('orphanShare.column.ageDays')}</dt><dd>{s.age_days}</dd></div></dl>
  {/snippet}
  {#snippet cardDetails(s)}
    <dl class="space-y-2 text-xs"><div><dt class="text-ink-2">{t('orphanShare.column.missingProject')}</dt><dd class="break-all font-mono">{s.project_id ?? '-'}</dd></div><div><dt class="text-ink-2">{t('orphanShare.column.createdAt')}</dt><dd>{s.created_at?.slice(0, 10) ?? '-'}</dd></div><div><dt class="text-ink-2">{t('orphanShare.column.id')}</dt><dd class="break-all font-mono">{s.id}</dd></div></dl>
  {/snippet}
	{#snippet row(s)}
		<td class="py-2 pr-4 text-ink-1">{s.name ?? '-'}</td>
		<td class="py-2 pr-4 text-ink-2 font-mono">{s.size_gb}</td>
		<td class="py-2 pr-4 text-green-400">{s.status}</td>
		<td class="py-2 pr-4 text-ink-2 font-mono">{s.project_id?.slice(0, 8) ?? '-'}</td>
		<td class="py-2 pr-4 text-ink-2">{s.created_at?.slice(0, 10) ?? '-'}</td>
		<td class="py-2 pr-4 text-warm-text">{s.age_days}</td>
		<td class="py-2 pr-4 text-ink-2 font-mono">{s.id.slice(0, 8)}</td>
	{/snippet}
</OrphanSection>
