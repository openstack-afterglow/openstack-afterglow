<script lang="ts">
	import { untrack } from 'svelte';
	import { authDisplayContext } from '$lib/stores/authDisplayContext';
	import { intlLocale } from '$lib/i18n/runtime.svelte';
	import { t as commonT } from '$lib/i18n/ns/common';
	import { createTableView, type TableColumn } from '$lib/utils/tableView.svelte';
	import TableViewControls from '$lib/components/ui/TableViewControls.svelte';
	import RegexSearch from '$lib/components/ui/RegexSearch.svelte';

	import { useFsWizard, type MetaEntry } from '$lib/stores/fileStorageWizardStore.svelte';
	import { t } from '$lib/i18n/ns/file-storage';
	import LoadingState from '$lib/components/ui/LoadingState.svelte';
	import { Alert, Button, ResponsiveTable, CompactResourceCard } from '$lib/components/ui';

	const s = useFsWizard();
	let search = $state('');
	const searchId = $props.id();
	const columns = $derived<TableColumn<MetaEntry>[]>([{key:'key',label:commonT('table.key'),value:row=>row.key},{key:'value',label:commonT('table.value'),value:row=>row.value}]);
	const view = createTableView({ locale: intlLocale,rows: () => s.metaEntries, columns: () => columns, search: () => search, searchable: row => [row.key,row.value]});
	let viewOwner = $state('');
	$effect(() => authDisplayContext.subscribe(({ key }) => {
		if (viewOwner === key) return;
		viewOwner = key;
		untrack(() => { search = ''; view.reset(); });
	}));

	let snapshot = $state<{ rows: MetaEntry[]; known: MetaEntry[] }>({ rows: [], known: [] });
	$effect.pre(() => {
		// Only an explicit view change may re-filter or reorder an in-progress field.
		void search;
		void view.sort?.key;
		void view.sort?.direction;
		void view.filters;
		void viewOwner;
		snapshot = untrack(() => ({ rows: [...view.rows], known: [...s.metaEntries] }));
	});
	const editableRows = $derived([
		...snapshot.rows.filter(meta => s.metaEntries.includes(meta)),
		...s.metaEntries.filter(meta => !snapshot.known.includes(meta)),
	]);
</script>

<h2 class="text-base font-semibold text-ink-0 mb-4">{t('wizard.basic.title')}</h2>
<div class="space-y-4">
	<div>
		<label class="block text-xs text-ink-2 mb-1.5 uppercase tracking-wide">{t('wizard.form.name')}
			<input bind:value={s.fsForm.name} type="text" placeholder="my-file-storage"
				class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-0 text-sm focus:outline-none focus:border-action-warm mt-1.5" />
		</label>
	</div>
	<div>
		<span class="block text-xs text-ink-2 mb-1.5 uppercase tracking-wide">{t('wizard.basic.size')}</span>
		<div class="flex gap-2 mb-2">
			{#each [10, 20, 50, 100] as preset}
				<button type="button" onclick={() => (s.fsForm.size_gb = preset)}
					class="flex-1 py-1.5 text-xs rounded-lg border transition-colors {s.fsForm.size_gb === preset ? 'border-action-warm bg-surface-selected/30 text-warm-text' : 'border-line-2 text-ink-2 hover:border-line-2'}">
					{preset} GB
				</button>
			{/each}
		</div>
		<input bind:value={s.fsForm.size_gb} type="number" min="1" placeholder={t('wizard.basic.customSizePlaceholder')}
			class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-0 text-sm focus:outline-none focus:border-action-warm" />
	</div>
	<div>
		<label class="block text-xs text-ink-2 mb-1.5 uppercase tracking-wide">{t('wizard.basic.shareType')}
			{#if s.shareTypes.length > 0}
				<select bind:value={s.fsForm.share_type} class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-0 text-sm focus:outline-none focus:border-action-warm mt-1.5">
					{#each s.shareTypes as st}<option value={st.name}>{st.is_default ? t('wizard.basic.defaultShareType', { name: st.name }) : st.name}</option>{/each}
				</select>
			{:else}
				<input bind:value={s.fsForm.share_type} type="text" placeholder={t('wizard.basic.shareTypePlaceholder')}
					class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-0 text-sm focus:outline-none focus:border-action-warm font-mono mt-1.5" />
			{/if}
		</label>
	</div>
	<div>
		<label class="block text-xs text-ink-2 mb-1.5 uppercase tracking-wide">{t('wizard.basic.protocol')}
			<select bind:value={s.fsForm.share_proto} class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-0 text-sm focus:outline-none focus:border-action-warm mt-1.5">
				{#each s.allowedProtos as p (p)}
					<option value={p}>{p === 'CEPHFS' ? 'CephFS' : 'NFS'}</option>
				{/each}
			</select>
			{#if s.allowedProtos.length === 1 && s.currentShareType}
				<span class="block text-xs text-ink-2 mt-1">{t('wizard.basic.supportedProtocol', { protocol: s.allowedProtos[0] })}</span>
			{/if}
		</label>
	</div>
	<div>
		<div class="flex items-center justify-between mb-2">
			<span class="block text-xs text-ink-2 uppercase tracking-wide">{t('wizard.basic.metadata')}</span>
			<button type="button" onclick={s.addMeta} class="text-xs text-warm-text hover:text-warm-text-hover transition-colors">{t('wizard.actions.add')}</button>
		</div>
		<RegexSearch id={searchId} bind:value={search} />
		<TableViewControls {view} class="" />
		{#if editableRows.length === 0}<p role="status" class="py-4 text-sm text-ink-2">{commonT('table.noMatches')}</p>{/if}
		<ResponsiveTable>
			{#snippet cards()}
				{#each editableRows as meta (meta)}
					<CompactResourceCard>
						<input bind:value={meta.key} type="text" aria-label={t('wizard.basic.metadataKeyPlaceholder')} placeholder={t('wizard.basic.metadataKeyPlaceholder')} class="min-w-0 w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-0 text-xs font-mono" />
						<input bind:value={meta.value} type="text" aria-label={t('wizard.basic.metadataValuePlaceholder')} placeholder={t('wizard.basic.metadataValuePlaceholder')} class="min-w-0 w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-0 text-xs font-mono" />
						{#snippet actions()}<Button size="sm" variant="danger-outline" onclick={() => s.removeMeta(s.metaEntries.indexOf(meta))}>{t('storageCard.delete')}</Button>{/snippet}
					</CompactResourceCard>
				{/each}
			{/snippet}
		<div class="space-y-2">
			{#each editableRows as meta (meta)}
				<div class="flex gap-2 items-center">
					<input bind:value={meta.key} type="text" placeholder={t('wizard.basic.metadataKeyPlaceholder')}
						class="flex-1 bg-surface-sunken border border-line-2 rounded-lg px-3 py-1.5 text-ink-0 text-xs focus:outline-none focus:border-action-warm font-mono" />
					<span class="text-ink-2 text-xs">=</span>
					<input bind:value={meta.value} type="text" placeholder={t('wizard.basic.metadataValuePlaceholder')}
						class="flex-1 bg-surface-sunken border border-line-2 rounded-lg px-3 py-1.5 text-ink-0 text-xs focus:outline-none focus:border-action-warm font-mono" />
					<button type="button" onclick={() => s.removeMeta(s.metaEntries.indexOf(meta))} class="text-ink-2 hover:text-red-400 transition-colors text-xs px-1">✕</button>
				</div>
			{/each}
		</div>
		</ResponsiveTable>
	</div>
</div>
{#if s.wizardError}<Alert tone="danger" class="mt-4">{s.wizardError}</Alert>{/if}
{#if s.creating}<LoadingState variant="inline" label={t('wizard.mutation.createFileStorage')} class="mt-4" />{/if}
<div class="flex justify-end gap-3 mt-6">
	<button onclick={s.closeWizard} class="px-4 py-2 text-sm text-ink-2 hover:text-ink-0 transition-colors">{t('wizard.actions.cancel')}</button>
	<!-- Tutorial advance anchor only when this button creates; DHSS NFS continues to the network step. -->
	<Button onclick={s.goStep2} disabled={s.creating} ariaBusy={s.creating} dataTour={(!s.dhssEnabled || s.fsForm.share_proto === 'CEPHFS') ? 'file-storage-create-submit' : undefined}>
		{#if s.creating}<LoadingState variant="control" label="" />{t('wizard.actions.creating')}{:else}{(!s.dhssEnabled || s.fsForm.share_proto === 'CEPHFS') ? t('wizard.actions.create') : t('wizard.actions.next')}{/if}
	</Button>
</div>
