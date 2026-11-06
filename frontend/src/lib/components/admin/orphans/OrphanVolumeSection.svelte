<script lang="ts">
	import OrphanSection from './OrphanSection.svelte';
	import type { OrphanVolumeInfo } from '$lib/types/orphan';
	import { t } from '$lib/i18n/ns/admin-storage';
	import type { TableColumn } from '$lib/utils/tableView.svelte';

	let {
		items,
		selected = $bindable(new Set<string>()),
		minAgeDays,
		cleanupDisabled = false,
		onCleanup,
	}: {
		items: OrphanVolumeInfo[];
		selected: Set<string>;
		minAgeDays: number;
		cleanupDisabled?: boolean;
		onCleanup: () => void;
	} = $props();

	const emptyMessage = $derived(t('orphanVolume.empty', { days: minAgeDays }));
	const columns = $derived<TableColumn<OrphanVolumeInfo>[]>([
		{ key: 'name', label: t('orphanVolume.column.name'), value: (row) => row.name },
		{ key: 'size', label: t('orphanVolume.column.sizeGb'), value: (row) => row.size_gb },
		{ key: 'status', label: t('orphanVolume.column.status'), value: (row) => row.status },
		{ key: 'project', label: t('orphanVolume.column.project'), value: (row) => row.project_id },
		{ key: 'created', label: t('orphanVolume.column.createdAt'), value: (row) => row.created_at?.slice(0, 10) ?? null },
		{ key: 'age', label: t('orphanVolume.column.ageDays'), value: (row) => row.age_days },
		{ key: 'id', label: t('orphanVolume.column.id'), value: (row) => row.id },
	]);
</script>

<OrphanSection
	title={t('orphanVolume.title')}
	{items}
	{columns}
	{cleanupDisabled}
	bind:selected
	{emptyMessage}
	{onCleanup}
>
  {#snippet cardSummary(v)}
    <div class="flex flex-wrap items-center justify-between gap-2"><strong class="break-words text-sm">{v.name ?? '-'}</strong><span class="text-xs text-state-success-text">{v.status}</span></div>
    <dl class="flex flex-wrap gap-3 text-xs"><div><dt class="text-ink-2">{t('orphanVolume.column.sizeGb')}</dt><dd>{v.size_gb}</dd></div><div><dt class="text-ink-2">{t('orphanVolume.column.ageDays')}</dt><dd>{v.age_days}</dd></div></dl>
  {/snippet}
  {#snippet cardDetails(v)}
    <dl class="space-y-2 text-xs"><div><dt class="text-ink-2">{t('orphanVolume.column.project')}</dt><dd class="break-all font-mono">{v.project_id ?? '-'}</dd></div><div><dt class="text-ink-2">{t('orphanVolume.column.createdAt')}</dt><dd>{v.created_at?.slice(0, 10) ?? '-'}</dd></div><div><dt class="text-ink-2">{t('orphanVolume.column.id')}</dt><dd class="break-all font-mono">{v.id}</dd></div></dl>
  {/snippet}
	{#snippet row(v)}
		<td class="py-2 pr-4 text-ink-1">{v.name ?? '-'}</td>
		<td class="py-2 pr-4 text-ink-2 font-mono">{v.size_gb}</td>
		<td class="py-2 pr-4 text-green-400">{v.status}</td>
		<td class="py-2 pr-4 text-ink-2 font-mono">{v.project_id?.slice(0, 8) ?? '-'}</td>
		<td class="py-2 pr-4 text-ink-2">{v.created_at?.slice(0, 10) ?? '-'}</td>
		<td class="py-2 pr-4 text-warm-text">{v.age_days}</td>
		<td class="py-2 pr-4 text-ink-2 font-mono">{v.id.slice(0, 8)}</td>
	{/snippet}
</OrphanSection>
