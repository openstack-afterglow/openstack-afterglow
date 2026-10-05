<script lang="ts">
	import { useObjectBrowser } from '$lib/stores/objectBrowser.svelte';
	import AutoRefreshControl from '$lib/components/AutoRefreshControl.svelte';
	import { ToggleGroup } from '$lib/components/ui';
	import type { ObjectView } from '$lib/utils/objectViewPreference';
	import { t } from '$lib/i18n/ns/object-storage';

	interface ArState { active: boolean; intervalSeconds: number; intervalOptions: number[]; }
	interface Props { ar: ArState; onManualRefresh: () => void; }
	let { ar, onManualRefresh }: Props = $props();

	const s = useObjectBrowser();
</script>

<div class="flex items-center gap-2 mb-4 flex-wrap">
	<div class="relative flex-1 min-w-[200px] max-w-xs">
		<svg class="w-4 h-4 text-ink-2 absolute left-3 top-1/2 -translate-y-1/2" viewBox="0 0 20 20" fill="currentColor">
			<path fill-rule="evenodd" d="M8 4a4 4 0 100 8 4 4 0 000-8zM2 8a6 6 0 1110.89 3.476l4.817 4.817a1 1 0 01-1.414 1.414l-4.816-4.816A6 6 0 012 8z" clip-rule="evenodd"/>
		</svg>
		<input
			type="text"
			bind:value={s.filterText}
			placeholder={t('browserToolbar.filter')}
			class="w-full bg-surface-sunken border border-line-2 rounded-lg pl-9 pr-3 py-1.5 text-sm text-ink-0 focus:outline-none focus:border-indigo-500 placeholder-ink-3"
		/>
	</div>

	{#if s.mode === 'user' && s.filterText.trim()}
		<select
			bind:value={s.searchScope}
			title={t('browserToolbar.searchScope')}
			class="text-xs text-ink-2 bg-surface-sunken border border-line-2 rounded-lg px-2 py-1.5 focus:outline-none focus:border-indigo-500"
		>
			<option value="current">{t('browserToolbar.currentFolder')}</option>
			{#if s.viewMode === 'list'}
				<option value="expanded">{t('browserToolbar.expandedTree')}</option>
			{/if}
			<option value="all">{t('browserToolbar.allBuckets')}</option>
		</select>
		{#if s.searchScope === 'all' && s.allObjectsLoading}
			<span class="text-xs text-ink-2">{t('browserToolbar.indexing')}</span>
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

	<button
		onclick={() => s.toggleSort('name')}
		class="text-xs text-ink-2 hover:text-ink-0 px-3 py-1.5 rounded border border-line-2 hover:border-line-2 transition-colors"
	>{t('browserToolbar.nameSort', { icon: s.sortIcon('name') })}</button>

	<div class="flex-1"></div>

	{#if s.prefix}
		<button
			onclick={() => {
				const parts = s.prefix.replace(/\/$/, '').split('/');
				parts.pop();
				s.navigatePrefix(parts.length ? parts.join('/') + '/' : '');
			}}
			class="text-xs text-ink-2 hover:text-ink-0 transition-colors px-3 py-1.5 rounded border border-line-2 hover:border-line-2"
		>{t('browserToolbar.parent')}</button>
	{/if}

	<button
		onclick={() => { s.showNewDir = true; s.newDirName = ''; }}
		class="text-xs text-ink-2 hover:text-ink-0 bg-surface-sunken hover:bg-surface-selected transition-colors px-3 py-1.5 rounded border border-line-2"
	>{t('browserToolbar.newFolder')}</button>

	<button
		onclick={() => { s.showUpload = true; }}
		class="text-xs text-ink-0 bg-indigo-600 hover:bg-indigo-500 transition-colors px-3 py-1.5 rounded border border-indigo-500"
	>{t('browserToolbar.upload')}</button>

	<AutoRefreshControl
		bind:active={ar.active}
		bind:intervalSeconds={ar.intervalSeconds}
		intervalOptions={ar.intervalOptions}
		refreshing={s.loading}
		{onManualRefresh}
	/>
</div>
