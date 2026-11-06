<script lang="ts">
 import RegexSearch from '$lib/components/ui/RegexSearch.svelte';
 import TableViewControls from '$lib/components/ui/TableViewControls.svelte';
	import LoadingState from '$lib/components/ui/LoadingState.svelte';
	import { useObjectBrowser } from '$lib/stores/objectBrowser.svelte';
	import AutoRefreshControl from '$lib/components/AutoRefreshControl.svelte';
	import { Button, Field, ResourceToolbar, SelectInput, ToggleGroup } from '$lib/components/ui';
	import type { ObjectView } from '$lib/utils/objectViewPreference';
	import { t } from '$lib/i18n/ns/object-storage';

	interface ArState { active: boolean; intervalSeconds: number; intervalOptions: number[]; }
	interface Props { ar: ArState; onManualRefresh: () => void; }
	let { ar, onManualRefresh }: Props = $props();

	const componentId = $props.id();
	const s = useObjectBrowser();
</script>

<ResourceToolbar label={t('browserToolbar.filter')} class="mb-4">
	{#snippet filters()}
		<RegexSearch id={`${componentId}-filter`} bind:value={s.filterText} label={t('browserToolbar.filter')} />
		{#if s.mode === 'user' && s.filterText.length > 0}
			<Field label={t('browserToolbar.searchScope')} for={`${componentId}-scope`} class="min-w-0 max-w-full w-full md:w-auto">
				<SelectInput id={`${componentId}-scope`} bind:value={() => s.searchScope, (value) => s.searchScope = value as 'current' | 'expanded' | 'all'}>
					<option value="current">{t('browserToolbar.currentFolder')}</option>
					{#if s.viewMode === 'list'}
						<option value="expanded">{t('browserToolbar.expandedTree')}</option>
					{/if}
					<option value="all">{t('browserToolbar.allBuckets')}</option>
				</SelectInput>
			</Field>
			{#if s.searchScope === 'all' && s.allObjectsLoading}
				<LoadingState variant="inline" label={t('browserToolbar.indexing')} class="text-xs" />
			{/if}
		{/if}
		{#if s.mode === 'user'}
			<ToggleGroup
				size="xs"
				ariaLabel={t('browserToolbar.viewLabel')}
				value={s.viewMode}
				options={[
					{ value: 'grid', label: t('browserToolbar.grid') },
					{ value: 'list', label: t('browserToolbar.list') },
				]}
				onchange={(v) => { s.viewMode = v as ObjectView; }}
			/>
		{/if}
		<TableViewControls view={s.view} class={(s.mode === 'user' && s.viewMode === 'grid') || (s.mode === 'user' ? s.treeRows.length : s.objects.length) === 0 ? '' : 'lg:hidden'} />
	{/snippet}
	{#snippet actions()}
		{#if s.prefix}
			<Button variant="outline" size="sm" class="max-w-full !whitespace-normal" onclick={() => {
				const parts = s.prefix.replace(/\/$/, '').split('/');
				parts.pop();
				s.navigatePrefix(parts.length ? parts.join('/') + '/' : '');
			}}>{t('browserToolbar.parent')}</Button>
		{/if}
		<Button variant="outline" size="sm" class="max-w-full !whitespace-normal" onclick={() => { s.showNewDir = true; s.newDirName = ''; }}>{t('browserToolbar.newFolder')}</Button>
		<Button variant="primary" size="sm" class="max-w-full !whitespace-normal" onclick={() => { s.showUpload = true; }}>{t('browserToolbar.upload')}</Button>
		<AutoRefreshControl
			bind:active={ar.active}
			bind:intervalSeconds={ar.intervalSeconds}
			intervalOptions={ar.intervalOptions}
			refreshing={s.loading}
			{onManualRefresh}
		/>
	{/snippet}
</ResourceToolbar>
