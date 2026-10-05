<script lang="ts">
	import OrphanSection from './OrphanSection.svelte';
	import type { OrphanShareInfo } from '$lib/types/orphan';
	import { t } from '$lib/i18n/ns/admin-storage';

	let {
		items,
		selected = $bindable(new Set<string>()),
		onCleanup,
	}: {
		items: OrphanShareInfo[];
		selected: Set<string>;
		onCleanup: () => void;
	} = $props();
</script>

<OrphanSection
	title={t('orphanShare.title')}
	{items}
	bind:selected
	emptyMessage={t('orphanShare.empty')}
	{onCleanup}
>
	{#snippet headers()}
		<th class="text-left py-2 pr-4">{t('orphanShare.column.name')}</th>
		<th class="text-left py-2 pr-4">{t('orphanShare.column.sizeGb')}</th>
		<th class="text-left py-2 pr-4">{t('orphanShare.column.status')}</th>
		<th class="text-left py-2 pr-4">{t('orphanShare.column.missingProject')}</th>
		<th class="text-left py-2 pr-4">{t('orphanShare.column.createdAt')}</th>
		<th class="text-left py-2 pr-4">{t('orphanShare.column.ageDays')}</th>
		<th class="text-left py-2 pr-4">{t('orphanShare.column.id')}</th>
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
