<script lang="ts">
	import OrphanSection from './OrphanSection.svelte';
	import type { OrphanVolumeInfo } from '$lib/types/orphan';
	import { t } from '$lib/i18n/ns/admin-storage';

	let {
		items,
		selected = $bindable(new Set<string>()),
		minAgeDays,
		onCleanup,
	}: {
		items: OrphanVolumeInfo[];
		selected: Set<string>;
		minAgeDays: number;
		onCleanup: () => void;
	} = $props();

	const emptyMessage = $derived(t('orphanVolume.empty', { days: minAgeDays }));
</script>

<OrphanSection
	title={t('orphanVolume.title')}
	{items}
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
	{#snippet headers()}
		<th class="text-left py-2 pr-4">{t('orphanVolume.column.name')}</th>
		<th class="text-left py-2 pr-4">{t('orphanVolume.column.sizeGb')}</th>
		<th class="text-left py-2 pr-4">{t('orphanVolume.column.status')}</th>
		<th class="text-left py-2 pr-4">{t('orphanVolume.column.project')}</th>
		<th class="text-left py-2 pr-4">{t('orphanVolume.column.createdAt')}</th>
		<th class="text-left py-2 pr-4">{t('orphanVolume.column.ageDays')}</th>
		<th class="text-left py-2 pr-4">{t('orphanVolume.column.id')}</th>
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
