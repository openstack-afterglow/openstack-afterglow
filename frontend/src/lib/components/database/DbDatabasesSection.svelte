<script lang="ts">
	import { t as tr } from '$lib/i18n/ns/database';
	import { useDbInstanceDetailController } from '$lib/stores/dbInstanceDetailController.svelte';
	import ActivityIndicator from '$lib/components/ui/ActivityIndicator.svelte';

	const s = useDbInstanceDetailController();

	let showDbForm = $state(false);
	let newDbName = $state('');

	async function handleCreateDb() {
		if (!newDbName.trim()) return;
		const ok = await s.createDb(newDbName.trim());
		if (ok) {
			showDbForm = false;
			newDbName = '';
		}
	}
</script>

<div class="bg-surface-base border border-line rounded-xl p-4">
	<div class="flex items-center justify-between mb-3">
		<h2 class="text-sm font-semibold text-ink-0">{tr('labels.databases')}</h2>
		<button onclick={() => { showDbForm = !showDbForm; s.dbError = ''; }}
			class="text-xs text-ink-2 hover:text-ink-0 border border-line-2 hover:border-line-2 px-2 py-1 rounded transition-colors">
			{showDbForm ? tr('actions.cancel') : tr('actions.add')}
		</button>
	</div>
	{#if showDbForm}
		<div class="bg-surface-sunken rounded-lg p-3 mb-3 space-y-2">
			<input type="text" bind:value={newDbName} placeholder="database_name"
				class="w-full bg-surface-selected border border-line-2 rounded px-3 py-1.5 text-sm text-ink-0 focus:outline-none focus:border-action-warm" />
			{#if s.dbError}<p class="text-red-400 text-xs">{s.dbError}</p>{/if}
			<button onclick={handleCreateDb} disabled={s.creatingDb || !newDbName.trim()}
				class="inline-flex items-center gap-1.5 text-xs bg-action-warm hover:bg-action-warm-hover disabled:bg-surface-selected disabled:text-ink-3 text-action-on-warm px-3 py-1.5 rounded transition-colors">
				{#if s.creatingDb}<ActivityIndicator size="xs" tone="ink" />{/if}{s.creatingDb ? tr('state.creating') : tr('actions.create')}
			</button>
		</div>
	{/if}
	{#if s.databases.length === 0}
		<div class="text-ink-2 text-xs">{tr('databases.empty')}</div>
	{:else}
		<div class="space-y-1">
			{#each s.databases as db}
				<div class="flex items-center justify-between py-1.5 border-b border-line/50">
					<span class="text-ink-0 text-sm font-medium">{db.name}</span>
					<button onclick={() => s.deleteDb(db.name)} disabled={s.deletingDb === db.name}
						class="inline-flex items-center gap-1 text-red-400 hover:text-red-300 disabled:text-ink-3 text-xs px-2 py-0.5 rounded border border-red-900 hover:border-red-700 transition-colors">
						{#if s.deletingDb === db.name}<ActivityIndicator size="xs" tone="danger" />{tr('state.deletingShort')}{:else}{tr('actions.delete')}{/if}
					</button>
				</div>
			{/each}
		</div>
	{/if}
</div>
