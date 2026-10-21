<script lang="ts">
	import OrphanSection from './OrphanSection.svelte';
	import type { OrphanSecurityGroupInfo } from '$lib/types/orphan';
	import { t } from '$lib/i18n/ns/admin-storage';
	import RichText from '$lib/i18n/RichText.svelte';

	let {
		items,
		selected = $bindable(new Set<string>()),
		onCleanup,
	}: {
		items: OrphanSecurityGroupInfo[];
		selected: Set<string>;
		onCleanup: () => void;
	} = $props();
</script>

<OrphanSection
	title={t('orphanSecurityGroup.title')}
	{items}
	bind:selected
	emptyMessage={t('orphanSecurityGroup.empty')}
	{onCleanup}
>
	{#snippet headerNote()}
		<div class="text-xs text-ink-2 mb-2">
			<RichText segments={t.rich('orphanSecurityGroup.note')} classes={{ code: 'text-ink-2' }} />
		</div>
	{/snippet}
  {#snippet cardSummary(g)}
    <strong class="break-words text-sm">{g.name}</strong>
    <dl class="text-xs"><dt class="text-ink-2">{t('orphanSecurityGroup.column.ageDays')}</dt><dd>{g.age_days}</dd></dl>
  {/snippet}
  {#snippet cardDetails(g)}
    <dl class="space-y-2 text-xs"><div><dt class="text-ink-2">{t('orphanSecurityGroup.column.description')}</dt><dd class="whitespace-pre-wrap break-words">{g.description ?? '-'}</dd></div><div><dt class="text-ink-2">{t('orphanSecurityGroup.column.project')}</dt><dd class="break-all font-mono">{g.project_id ?? '-'}</dd></div><div><dt class="text-ink-2">{t('orphanSecurityGroup.column.createdAt')}</dt><dd>{g.created_at?.slice(0, 10) ?? '-'}</dd></div><div><dt class="text-ink-2">{t('orphanSecurityGroup.column.id')}</dt><dd class="break-all font-mono">{g.id}</dd></div></dl>
  {/snippet}
	{#snippet headers()}
		<th class="text-left py-2 pr-4">{t('orphanSecurityGroup.column.name')}</th>
		<th class="text-left py-2 pr-4">{t('orphanSecurityGroup.column.description')}</th>
		<th class="text-left py-2 pr-4">{t('orphanSecurityGroup.column.project')}</th>
		<th class="text-left py-2 pr-4">{t('orphanSecurityGroup.column.createdAt')}</th>
		<th class="text-left py-2 pr-4">{t('orphanSecurityGroup.column.ageDays')}</th>
		<th class="text-left py-2 pr-4">{t('orphanSecurityGroup.column.id')}</th>
	{/snippet}
	{#snippet row(g)}
		<td class="py-2 pr-4 text-ink-1">{g.name}</td>
		<td class="py-2 pr-4 text-ink-2 max-w-md truncate" title={g.description ?? ''}>{g.description ?? '-'}</td>
		<td class="py-2 pr-4 text-ink-2 font-mono">{g.project_id?.slice(0, 8) ?? '-'}</td>
		<td class="py-2 pr-4 text-ink-2">{g.created_at?.slice(0, 10) ?? '-'}</td>
		<td class="py-2 pr-4 text-warm-text">{g.age_days}</td>
		<td class="py-2 pr-4 text-ink-2 font-mono">{g.id.slice(0, 8)}</td>
	{/snippet}
</OrphanSection>
