<script lang="ts">
	import OrphanSection from './OrphanSection.svelte';
	import type { OrphanFipInfo } from '$lib/types/orphan';
	import { t } from '$lib/i18n/ns/admin-storage';

	let {
		items,
		selected = $bindable(new Set<string>()),
		onCleanup,
	}: {
		items: OrphanFipInfo[];
		selected: Set<string>;
		onCleanup: () => void;
	} = $props();
</script>

<OrphanSection
	title={t('orphanFip.title')}
	{items}
	bind:selected
	emptyMessage={t('orphanFip.empty')}
	{onCleanup}
>
	{#snippet headers()}
		<th class="text-left py-2 pr-4">{t('orphanFip.column.address')}</th>
		<th class="text-left py-2 pr-4">{t('orphanFip.column.project')}</th>
		<th class="text-left py-2 pr-4">{t('orphanFip.column.createdAt')}</th>
		<th class="text-left py-2 pr-4">{t('orphanFip.column.ageDays')}</th>
		<th class="text-left py-2 pr-4">{t('orphanFip.column.id')}</th>
	{/snippet}
	{#snippet row(f)}
		<td class="py-2 pr-4 font-mono text-green-400">{f.address}</td>
		<td class="py-2 pr-4 text-ink-2 font-mono">{f.project_id?.slice(0, 8) ?? '-'}</td>
		<td class="py-2 pr-4 text-ink-2">{f.created_at?.slice(0, 10) ?? '-'}</td>
		<td class="py-2 pr-4 text-warm-text">{f.age_days}</td>
		<td class="py-2 pr-4 text-ink-2 font-mono">{f.id.slice(0, 8)}</td>
	{/snippet}
</OrphanSection>
