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
