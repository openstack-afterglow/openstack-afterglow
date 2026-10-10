<script lang="ts">
	import { t as tr } from '$lib/i18n/ns/database';
	import ActivityIndicator from '$lib/components/ui/ActivityIndicator.svelte';
	import type { DbDatabase } from '$lib/types/database';

	let {
		databases,
		deletingDb,
		addError,
		creating,
		onAdd,
		onDelete,
	}: {
		databases: DbDatabase[];
		deletingDb: string | null;
		addError: string;
		creating: boolean;
		onAdd: (form: { name: string; character_set: string; collate: string }) => Promise<boolean>;
		onDelete: (name: string) => Promise<void>;
	} = $props();

	let showForm = $state(false);
	let newDb = $state({ name: '', character_set: 'utf8', collate: 'utf8_general_ci' });

	async function handleAdd() {
		const ok = await onAdd({ ...newDb });
		if (ok) {
			showForm = false;
			newDb = { name: '', character_set: 'utf8', collate: 'utf8_general_ci' };
		}
	}
</script>

<div class="bg-surface-base border border-line rounded-xl p-4 mb-4">
	<div class="flex items-center justify-between mb-3">
		<h2 class="text-sm font-semibold text-ink-0">{tr('labels.databases')}</h2>
		<button onclick={() => { showForm = !showForm; }}
			class="text-xs text-ink-2 hover:text-ink-0 border border-line-2 hover:border-line-2 px-2 py-1 rounded transition-colors">
			{showForm ? tr('actions.cancel') : tr('actions.add')}
		</button>
	</div>
	{#if showForm}
		<div class="bg-surface-sunken rounded-lg p-3 mb-3 space-y-2">
			<input type="text" bind:value={newDb.name} placeholder="database_name"
				class="w-full bg-surface-selected border border-line-2 rounded px-3 py-1.5 text-sm text-ink-0 focus:outline-none focus:border-action-warm" />
			{#if addError}<p class="text-red-400 text-xs">{addError}</p>{/if}
			<button onclick={handleAdd} disabled={creating || !newDb.name.trim()}
				class="text-xs bg-action-warm hover:bg-action-warm-hover disabled:bg-surface-selected disabled:text-ink-3 text-action-on-warm px-3 py-1.5 rounded transition-colors">
				{#if creating}<span class="inline-flex items-center gap-2" role="status"><ActivityIndicator size="xs" tone="ink" /><span>{tr('state.creating')}</span></span>{:else}{tr('actions.create')}{/if}
			</button>
		</div>
	{/if}
	{#if databases.length === 0}
		<div class="text-ink-2 text-xs">{tr('databases.empty')}</div>
	{:else}
		<div class="space-y-1">
			{#each databases as db}
				<div class="flex items-center justify-between py-1.5 border-b border-line/50">
					<span class="text-ink-0 text-sm font-medium">{db.name}</span>
					<button onclick={() => onDelete(db.name)} disabled={deletingDb === db.name}
						class="text-red-400 hover:text-red-300 disabled:text-ink-3 text-xs px-2 py-0.5 rounded border border-red-900 hover:border-red-700 transition-colors">
						{#if deletingDb === db.name}<span class="inline-flex items-center gap-2" role="status"><ActivityIndicator size="xs" tone="ink" /><span>{tr('state.deleting')}</span></span>{:else}{tr('actions.delete')}{/if}
					</button>
				</div>
			{/each}
		</div>
	{/if}
</div>
