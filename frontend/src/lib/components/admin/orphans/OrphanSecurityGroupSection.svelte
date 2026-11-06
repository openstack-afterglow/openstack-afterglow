<script lang="ts">
	import OrphanSection from './OrphanSection.svelte';
	import type { OrphanSecurityGroupInfo } from '$lib/types/orphan';
	import { t } from '$lib/i18n/ns/admin-storage';
	import RichText from '$lib/i18n/RichText.svelte';
	import type { TableColumn } from '$lib/utils/tableView.svelte';

	let {
		items,
		selected = $bindable(new Set<string>()),
		cleanupDisabled = false,
		onCleanup,
	}: {
		items: OrphanSecurityGroupInfo[];
		selected: Set<string>;
		cleanupDisabled?: boolean;
		onCleanup: () => void;
	} = $props();
	const columns = $derived<TableColumn<OrphanSecurityGroupInfo>[]>([
		{ key: 'name', label: t('orphanSecurityGroup.column.name'), value: (row) => row.name },
		{ key: 'description', label: t('orphanSecurityGroup.column.description'), value: (row) => row.description },
		{ key: 'project', label: t('orphanSecurityGroup.column.project'), value: (row) => row.project_id },
		{ key: 'created', label: t('orphanSecurityGroup.column.createdAt'), value: (row) => row.created_at?.slice(0, 10) ?? null },
		{ key: 'age', label: t('orphanSecurityGroup.column.ageDays'), value: (row) => row.age_days },
		{ key: 'id', label: t('orphanSecurityGroup.column.id'), value: (row) => row.id },
	]);
</script>

<OrphanSection
	title={t('orphanSecurityGroup.title')}
	{items}
	{columns}
	{cleanupDisabled}
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
	{#snippet row(g)}
		<td class="py-2 pr-4 text-ink-1">{g.name}</td>
		<td class="py-2 pr-4 text-ink-2 max-w-md truncate" title={g.description ?? ''}>{g.description ?? '-'}</td>
		<td class="py-2 pr-4 text-ink-2 font-mono">{g.project_id?.slice(0, 8) ?? '-'}</td>
		<td class="py-2 pr-4 text-ink-2">{g.created_at?.slice(0, 10) ?? '-'}</td>
		<td class="py-2 pr-4 text-warm-text">{g.age_days}</td>
		<td class="py-2 pr-4 text-ink-2 font-mono">{g.id.slice(0, 8)}</td>
	{/snippet}
</OrphanSection>
