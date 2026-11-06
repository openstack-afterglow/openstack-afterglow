<script lang="ts">
	import { t as tr } from '$lib/i18n/ns/database';
	import { useDbInstanceDetailController } from '$lib/stores/dbInstanceDetailController.svelte';
	import LoadingState from '$lib/components/ui/LoadingState.svelte';
	import type { DbUser } from '$lib/types/database';
 import ResponsiveTable from '$lib/components/ui/ResponsiveTable.svelte';
 import CompactResourceCard from '$lib/components/ui/CompactResourceCard.svelte';
	import { t as tl } from '$lib/i18n/ns/common';
	import RegexSearch from '$lib/components/ui/RegexSearch.svelte';
	import TableViewControls from '$lib/components/ui/TableViewControls.svelte';
	import TableColumnControl from '$lib/components/ui/TableColumnControl.svelte';

	const s = useDbInstanceDetailController();

	let showUserForm = $state(false);
	let newUser = $state<{ name: string; password: string; host: string; dbNames: string[] }>({
		name: '', password: '', host: '%', dbNames: []
	});

	async function handleCreateUser() {
		if (!newUser.name.trim() || !newUser.password) return;
		const ok = await s.createUser(newUser);
		if (ok) {
			showUserForm = false;
			newUser = { name: '', password: '', host: '%', dbNames: [] };
		}
	}

	function userKey(u: DbUser) {
		return u.host && u.host !== '%' ? `${u.name}@${u.host}` : u.name;
	}
</script>

<div class="bg-surface-base border border-line rounded-xl p-4">
	<div class="flex items-center justify-between mb-3">
		<h2 class="text-sm font-semibold text-ink-0">{tr('users.title')}</h2>
		<button onclick={() => { showUserForm = !showUserForm; s.userError = ''; }}
			class="text-xs text-ink-2 hover:text-ink-0 border border-line-2 hover:border-line-2 px-2 py-1 rounded transition-colors">
			{showUserForm ? tr('actions.cancel') : tr('actions.add')}
		</button>
	</div>
	{#if showUserForm}
		<div class="bg-surface-sunken rounded-lg p-3 mb-3 space-y-2">
			<input type="text" bind:value={newUser.name} placeholder={tr('users.usernamePlaceholder')}
				class="w-full bg-surface-selected border border-line-2 rounded px-3 py-1.5 text-sm text-ink-0 focus:outline-none focus:border-action-warm" />
			<input type="password" bind:value={newUser.password} placeholder={tr('labels.password')}
				class="w-full bg-surface-selected border border-line-2 rounded px-3 py-1.5 text-sm text-ink-0 focus:outline-none focus:border-action-warm" />
			<input type="text" bind:value={newUser.host} placeholder={tr('users.hostPlaceholder')}
				class="w-full bg-surface-selected border border-line-2 rounded px-3 py-1.5 text-sm text-ink-0 focus:outline-none focus:border-action-warm" />
			{#if s.databases.length > 0}
				<div>
					<div class="text-ink-2 text-xs mb-1.5">{tr('users.databaseOptional')}</div>
					<div class="flex flex-wrap gap-1.5 max-h-32 overflow-y-auto">
						{#each s.databases as db}
							<label class="flex items-center gap-1.5 text-xs text-ink-0 bg-surface-selected hover:bg-surface-selected border border-line-2 px-2 py-1 rounded cursor-pointer">
								<input type="checkbox" bind:group={newUser.dbNames} value={db.name} class="accent-amber-500" />
								{db.name}
							</label>
						{/each}
					</div>
				</div>
			{:else}
				<div class="text-ink-2 text-xs">{tr('users.createDatabaseHelp')}</div>
			{/if}
			{#if s.userError}<p class="text-red-400 text-xs">{s.userError}</p>{/if}
			<button onclick={handleCreateUser} disabled={s.creatingUser || !newUser.name.trim() || !newUser.password}
				class="inline-flex items-center gap-1.5 text-xs bg-action-warm hover:bg-action-warm-hover disabled:bg-surface-selected disabled:text-ink-3 text-action-on-warm px-3 py-1.5 rounded transition-colors">
				{#if s.creatingUser}<LoadingState variant="control" label="" />{/if}{s.creatingUser ? tr('state.creating') : tr('actions.create')}
			</button>
		</div>
	{/if}
	<RegexSearch id="database-detail-users-search" bind:value={s.userSearch} />
	<TableViewControls view={s.userView} />
	{#if s.users.length === 0}
		<div class="text-ink-2 text-xs">{tr('users.empty')}</div>
	{:else if s.userView.rows.length === 0}
		<p class="text-sm text-ink-2" role="status">{tl('table.noMatches')}</p>
	{/if}
  <ResponsiveTable>
   {#snippet cards()}{#each s.userView.rows as u (u.name + '@' + u.host)}<CompactResourceCard><strong class="text-sm font-mono break-all">{u.name}@{u.host || '%'}</strong>{#snippet details()}{#if u.databases?.length}<p class="text-xs text-ink-2 break-all">{u.databases.map(d => d.name).join(', ')}</p>{/if}{/snippet}{#snippet actions()}<button onclick={() => s.deleteUser(u)} disabled={s.deletingUser === userKey(u)} class="inline-flex items-center gap-1 text-state-danger-text disabled:text-ink-3 text-xs px-2 py-1 rounded border border-line-2">{#if s.deletingUser === userKey(u)}<LoadingState variant="control" label="" />{tr('state.deletingShort')}{:else}{tr('actions.delete')}{/if}</button>{/snippet}</CompactResourceCard>{/each}{/snippet}
		<div class="space-y-1">
			<div class="grid grid-cols-[minmax(0,1fr)_minmax(0,1fr)_minmax(0,2fr)_auto] items-center gap-3 border-b border-line py-2 text-xs text-ink-2">
				<TableColumnControl view={s.userView} columnKey="name" />
				<TableColumnControl view={s.userView} columnKey="host" />
				<TableColumnControl view={s.userView} columnKey="databases" />
				<span>{tr('labels.actions')}</span>
			</div>
			{#each s.userView.rows as u (u.name + '@' + u.host)}
				<div class="grid grid-cols-[minmax(0,1fr)_minmax(0,1fr)_minmax(0,2fr)_auto] items-center gap-3 py-1.5 border-b border-line/50">
					<span class="text-ink-0 text-sm font-medium font-mono break-all">{u.name}</span>
					<span class="text-ink-2 text-sm font-mono break-all">{u.host || '%'}</span>
					<span class="text-ink-2 text-xs break-all">{u.databases?.map(d => d.name).join(', ') || '—'}</span>
					<button onclick={() => s.deleteUser(u)} disabled={s.deletingUser === userKey(u)}
						class="inline-flex items-center gap-1 text-red-400 hover:text-red-300 disabled:text-ink-3 text-xs px-2 py-0.5 rounded border border-red-900 hover:border-red-700 transition-colors">
						{#if s.deletingUser === userKey(u)}<LoadingState variant="control" label="" />{tr('state.deletingShort')}{:else}{tr('actions.delete')}{/if}
					</button>
				</div>
			{/each}
		</div>
  </ResponsiveTable>
</div>
