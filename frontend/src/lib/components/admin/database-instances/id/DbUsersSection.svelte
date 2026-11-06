<script lang="ts">
	import { t as tr } from '$lib/i18n/ns/database';
	import LoadingState from '$lib/components/ui/LoadingState.svelte';
	import type { DbUser } from '$lib/types/database';
	import ResponsiveTable from '$lib/components/ui/ResponsiveTable.svelte';
	import CompactResourceCard from '$lib/components/ui/CompactResourceCard.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import RegexSearch from '$lib/components/ui/RegexSearch.svelte';
	import TableViewControls from '$lib/components/ui/TableViewControls.svelte';
	import TableColumnControl from '$lib/components/ui/TableColumnControl.svelte';
	import { createTableView } from '$lib/utils/tableView.svelte';
	import { intlLocale } from '$lib/i18n/runtime.svelte';
	import { t as tc } from '$lib/i18n/ns/common';

	let {
		users,
		deletingUser,
		addError,
		creating,
		onAdd,
		onDelete,
		canMutate = true,
		loadError = '',
	}: {
		users: DbUser[];
		deletingUser: string | null;
		addError: string;
		creating: boolean;
		onAdd: (form: { name: string; password: string; databases: string }) => Promise<boolean>;
		onDelete: (name: string) => Promise<void>;
		canMutate?: boolean;
		loadError?: string;
	} = $props();

	let showForm = $state(false);
	let newUser = $state({ name: '', password: '', databases: '' });
	let search = $state('');
	const view = createTableView<DbUser>({
		rows: () => users,
		search: () => search,
		searchable: (u) => [u.name, u.host ?? '', ...(u.databases?.map((db) => db.name) ?? [])],
		locale: intlLocale,
		columns: () => [
			{ key: 'name', label: tr('labels.name'), value: (u) => u.name },
			{ key: 'databases', label: tr('labels.databases'), value: (u) => u.databases?.map((db) => db.name).join(', ') || null, filterValues: (u) => u.databases?.map((db) => db.name) ?? [] },
		],
	});

	async function handleAdd() {
		const ok = await onAdd({ ...newUser });
		if (ok) {
			showForm = false;
			newUser = { name: '', password: '', databases: '' };
		}
	}
</script>

<div class="bg-surface-base border border-line rounded-xl p-4 mb-4">
	<div class="flex items-center justify-between mb-3">
		<h2 class="text-sm font-semibold text-ink-0">{tr('users.title')}</h2>
		{#if canMutate}
		<button onclick={() => { showForm = !showForm; }}
			class="text-xs text-ink-2 hover:text-ink-0 border border-line-2 hover:border-line-2 px-2 py-1 rounded transition-colors">
			{showForm ? tr('actions.cancel') : tr('actions.add')}
		</button>
		{/if}
	</div>
	{#if showForm && canMutate}
		<div class="bg-surface-sunken rounded-lg p-3 mb-3 space-y-2">
			<input type="text" bind:value={newUser.name} placeholder={tr('users.usernamePlaceholder')}
				class="w-full bg-surface-selected border border-line-2 rounded px-3 py-1.5 text-sm text-ink-0 focus:outline-none focus:border-action-warm" />
			<input type="password" bind:value={newUser.password} placeholder={tr('labels.password')}
				class="w-full bg-surface-selected border border-line-2 rounded px-3 py-1.5 text-sm text-ink-0 focus:outline-none focus:border-action-warm" />
			<input type="text" bind:value={newUser.databases} placeholder={tr('users.databaseCsv')}
				class="w-full bg-surface-selected border border-line-2 rounded px-3 py-1.5 text-sm text-ink-0 focus:outline-none focus:border-action-warm" />
			{#if addError}<p class="text-red-400 text-xs">{addError}</p>{/if}
			<button onclick={handleAdd} disabled={creating || !newUser.name.trim() || !newUser.password}
				class="text-xs bg-action-warm hover:bg-action-warm-hover disabled:bg-surface-selected disabled:text-ink-3 text-action-on-warm px-3 py-1.5 rounded transition-colors">
				{#if creating}<span class="inline-flex items-center gap-2" role="status"><LoadingState variant="control" label="" aria-hidden="true" /><span>{tr('state.creating')}</span></span>{:else}{tr('actions.create')}{/if}
			</button>
		</div>
	{/if}
	<div class="mb-3 space-y-3">
		<RegexSearch id="admin-database-users-search" bind:value={search} label={tc('table.search')} />
		<TableViewControls {view} class={view.rows.length ? 'lg:hidden' : ''} />
	</div>
	{#if loadError}
		<p role="alert" class="text-state-danger-text text-sm">{loadError}</p>
	{:else if view.rows.length === 0}
		<div class="text-ink-2 text-xs">{users.length ? tc('table.noMatches') : tr('users.empty')}</div>
	{:else}
		<ResponsiveTable>
			{#snippet cards()}
				{#each view.rows as u}
					<CompactResourceCard>
						<h3 class="break-all font-medium text-ink-0">{u.name}</h3><p class="text-xs text-ink-2">{tr('labels.databases')}: {u.databases?.length ?? 0}</p>
						{#snippet actions()}{#if canMutate}<Button variant="danger" size="sm" disabled={deletingUser === u.name} onclick={() => onDelete(u.name)}>{#if deletingUser === u.name}<LoadingState variant="control" label="" aria-hidden="true" />{/if}{deletingUser === u.name ? tr('state.deleting') : tr('actions.delete')}</Button>{/if}{/snippet}
						{#snippet details()}<p class="break-all text-xs text-ink-2">{u.databases?.map((database) => database.name).join(', ') || '-'}</p>{/snippet}
					</CompactResourceCard>
				{/each}
			{/snippet}
		<div class="space-y-1">
			<div class="grid grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto] items-center gap-3 border-b border-line py-2 text-xs text-ink-2">
				<TableColumnControl {view} columnKey="name" />
				<TableColumnControl {view} columnKey="databases" />
				{#if canMutate}<span>{tr('labels.actions')}</span>{/if}
			</div>
			{#each view.rows as u}
				<div class="grid grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto] items-center gap-3 py-1.5 border-b border-line/50">
					<span class="break-all text-ink-0 text-sm font-medium">{u.name}</span>
					<span class="break-all text-ink-2 text-xs">{u.databases?.map(d => d.name).join(', ') || '-'}</span>
					{#if canMutate}
					<button onclick={() => onDelete(u.name)} disabled={deletingUser === u.name}
						class="text-red-400 hover:text-red-300 disabled:text-ink-3 text-xs px-2 py-0.5 rounded border border-red-900 hover:border-red-700 transition-colors">
						{#if deletingUser === u.name}<span class="inline-flex items-center gap-2" role="status"><LoadingState variant="control" label="" aria-hidden="true" /><span>{tr('state.deleting')}</span></span>{:else}{tr('actions.delete')}{/if}
					</button>
					{/if}
				</div>
			{/each}
		</div>
		</ResponsiveTable>
	{/if}
</div>
