<script lang="ts">
	import { confirmDialog } from '$lib/stores/confirm.svelte';
	import { api, ApiError } from '$lib/api/client';
	import { toast } from '$lib/stores/toast';
	import { formatStorage } from '$lib/utils/format';
	import SelectionCheckbox from '$lib/components/ui/SelectionCheckbox.svelte';
	import SelectionToolbar from '$lib/components/ui/SelectionToolbar.svelte';
	import BulkSelectionOverlay from '$lib/components/ui/BulkSelectionOverlay.svelte';
	import { createResourceSelection } from '$lib/utils/resourceSelection.svelte';
	import { executeBulkMutations } from '$lib/utils/bulkActions';
	import { t } from '$lib/i18n/ns/object-storage';
	import { intlLocale } from '$lib/i18n/runtime.svelte';

	interface TrashObject {
		trash_key: string;
		original_name: string;
		deleted_at: number;
		bytes: number;
		content_type?: string;
	}

	let {
		containerName,
		token,
		projectId,
		selectionEnabled = false,
	}: {
		containerName: string;
		token: string | undefined;
		projectId: string | undefined;
		selectionEnabled?: boolean;
	} = $props();

	let items = $state<TrashObject[]>([]);
	let loading = $state(true);
	let restoring = $state<string | null>(null);
	let purging = $state<string | null>(null);
	let busy = $state(false);
	const selection = createResourceSelection();

	async function load() {
		loading = true;
		try {
			items = await api.get<TrashObject[]>(
				`/api/v1/object-storage/${encodeURIComponent(containerName)}/trash`,
				token,
				projectId
			);
			selection.retain(items.map((item) => item.trash_key));
		} catch {
			items = [];
			selection.clear();
		} finally {
			loading = false;
		}
	}

	async function restore(trashKey: string, origName: string) {
		restoring = trashKey;
		try {
			const res = await api.post<{ restored_name: string }>(
				`/api/v1/object-storage/${encodeURIComponent(containerName)}/trash/restore`,
				{ trash_key: trashKey },
				token,
				projectId
			);
			selection.remove([trashKey]);
			await load();
			toast.success(t('dialogs.trash.restoreSuccess', { name: res.restored_name }));
		} catch (e) {
			toast.error(t('dialogs.trash.restoreFailed', { error: e instanceof ApiError ? e.message : String(e) }));
		} finally {
			restoring = null;
		}
	}

	async function purge(trashKey: string, origName: string) {
		if (!(await confirmDialog(t('dialogs.trash.purgeConfirm', { name: origName })))) return;
		purging = trashKey;
		try {
			await api.delete(
				`/api/v1/object-storage/${encodeURIComponent(containerName)}/trash/${encodeURIComponent(trashKey)}`,
				token,
				projectId
			);
			selection.remove([trashKey]);
			await load();
		} catch (e) {
			toast.error(t('dialogs.trash.purgeFailed', { error: e instanceof ApiError ? e.message : String(e) }));
		} finally {
			purging = null;
		}
	}

	async function runBulk(action: 'restore' | 'purge') {
		const submitted = [...selection.ids];
		const requestContainer = containerName;
		const requestToken = token;
		const requestProject = projectId;
		if (submitted.length === 0) return;
		if (action === 'purge' && !(await confirmDialog(t('dialogs.trash.bulkPurgeConfirm', { count: submitted.length })))) return;
		busy = true;
		const results = await executeBulkMutations(submitted, (trashKey) =>
			action === 'restore'
				? api.post(`/api/v1/object-storage/${encodeURIComponent(requestContainer)}/trash/restore`, { trash_key: trashKey }, requestToken, requestProject)
				: api.delete(`/api/v1/object-storage/${encodeURIComponent(requestContainer)}/trash/${encodeURIComponent(trashKey)}`, requestToken, requestProject)
		);
		if (containerName === requestContainer && projectId === requestProject) {
			selection.remove(results.filter((result) => result.ok).map((result) => result.id));
			await load();
		}
		const successCount = results.filter((result) => result.ok).length;
		const failureCount = results.length - successCount;
		if (successCount) toast.success(t(action === 'restore' ? 'dialogs.trash.bulkRestoreSuccess' : 'dialogs.trash.bulkPurgeSuccess', { count: successCount }));
		if (failureCount) toast.error(t(action === 'restore' ? 'dialogs.trash.bulkRestoreFailed' : 'dialogs.trash.bulkPurgeFailed', { count: failureCount }));
		busy = false;
	}
	$effect(() => {
		if (!selectionEnabled) selection.clear();
	});
	$effect(() => {
		const currentContainer = containerName;
		const currentProject = projectId;
		selection.clear();
		if (!currentContainer || !currentProject) {
			items = [];
			loading = false;
			return;
		}
		load();
	});
</script>

<div class="mt-2">
	{#if loading}
		<div class="text-ink-2 text-xs py-8 text-center">{t('dialogs.trash.loading')}</div>
	{:else if items.length === 0}
		<div class="text-ink-2 text-xs py-12 text-center">{t('dialogs.trash.empty')}</div>
	{:else}
		<div class="text-xs text-ink-2 mb-2">{t('dialogs.trash.summary', { count: items.length })}</div>
		{#if selectionEnabled}
			<div class="mb-2">
				<SelectionToolbar
					label={t('dialogs.trash.selectionLabel')}
					ariaLabel={t('dialogs.trash.selectAll')}
					checked={selection.count === items.length}
					indeterminate={selection.count > 0 && selection.count < items.length}
					selectedCount={selection.count}
					disabled={busy}
					onToggle={() => selection.toggleAll(items.map((item) => item.trash_key))}
				/>
			</div>
		{/if}
		<table class="w-full text-xs">
			<thead>
				<tr class="border-b border-line text-ink-2">
					{#if selectionEnabled}<th class="py-2 px-3 text-left font-medium w-10">{t('dialogs.trash.columns.select')}</th>{/if}
					<th class="py-2 px-3 text-left font-medium">{t('dialogs.trash.columns.originalName')}</th>
					<th class="py-2 px-3 text-left font-medium">{t('dialogs.trash.columns.deletedAt')}</th>
					<th class="py-2 px-3 text-right font-medium">{t('dialogs.trash.columns.size')}</th>
					<th class="py-2 px-3 text-right font-medium">{t('dialogs.trash.columns.actions')}</th>
				</tr>
			</thead>
			<tbody>
				{#each items as item (item.trash_key)}
					<tr class="resource-selection-surface border-b border-line/40 hover:bg-surface-sunken/20 transition-colors" data-selected={selectionEnabled && selection.has(item.trash_key)}>
						{#if selectionEnabled}
							<td class="py-2 px-3">
								<SelectionCheckbox
									checked={selection.has(item.trash_key)}
									disabled={busy}
									ariaLabel={t('dialogs.trash.selectObject', { name: item.original_name })}
									onclick={() => selection.toggle(item.trash_key)}
								/>
							</td>
						{/if}
						<td class="py-2 px-3 text-ink-2 font-mono truncate max-w-xs" title={item.original_name}>{item.original_name}</td>
						<td class="py-2 px-3 text-ink-2">
							{item.deleted_at
								? new Date(item.deleted_at * 1000).toLocaleDateString(intlLocale(), {
										year: 'numeric',
										month: '2-digit',
										day: '2-digit',
									})
								: '—'}
						</td>
						<td class="py-2 px-3 text-ink-2 text-right">{item.bytes ? formatStorage(item.bytes / 1_073_741_824) : '—'}</td>
						<td class="py-2 px-3 text-right">
							<div class="flex gap-1.5 justify-end">
								<button onclick={() => restore(item.trash_key, item.original_name)} disabled={restoring === item.trash_key || busy} class="text-emerald-400 hover:text-emerald-300 disabled:text-ink-3 px-2 py-0.5 rounded border border-emerald-900 hover:border-emerald-700 disabled:border-line-2 transition-colors">{t(restoring === item.trash_key ? 'dialogs.trash.restoring' : 'dialogs.trash.restore')}</button>
								<button onclick={() => purge(item.trash_key, item.original_name)} disabled={purging === item.trash_key || busy} class="text-red-400 hover:text-red-300 disabled:text-ink-3 px-2 py-0.5 rounded border border-red-900 hover:border-red-700 disabled:border-line-2 transition-colors">{t(purging === item.trash_key ? 'dialogs.trash.purging' : 'dialogs.trash.purge')}</button>
							</div>
						</td>
					</tr>
				{/each}
			</tbody>
		</table>
		<p class="mt-2 text-xs text-ink-2">{t('dialogs.trash.capacityNotice')}</p>
		{#if selectionEnabled}
			<BulkSelectionOverlay
				count={selection.count}
				ariaLabel={t('dialogs.trash.bulkActions')}
				busy={busy}
				actions={[
					{ key: 'restore', label: t('dialogs.trash.restore'), tone: 'success', onAction: () => runBulk('restore') },
					{ key: 'purge', label: t('dialogs.trash.purge'), tone: 'danger', onAction: () => runBulk('purge') },
				]}
				onClear={() => selection.clear()}
			/>
		{/if}
	{/if}
</div>
