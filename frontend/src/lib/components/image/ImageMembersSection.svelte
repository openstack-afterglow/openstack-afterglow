<script lang="ts">
	import { createTableView, type TableColumn } from '$lib/utils/tableView.svelte';
	import TableViewControls from '$lib/components/ui/TableViewControls.svelte';
	import RegexSearch from '$lib/components/ui/RegexSearch.svelte';
	import { t as tc } from '$lib/i18n/ns/common';
	import { t } from '$lib/i18n/ns/images-keys';
	import { useImageDetailController } from '$lib/stores/imageDetailController.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import LoadingState from '$lib/components/ui/LoadingState.svelte';
	import { CompactResourceCard, ResponsiveTable } from '$lib/components/ui';

	const s = useImageDetailController();
	const tableState = s.tableState('members');
	const columns = $derived<TableColumn<(typeof s.members)[number]>[]>([
		{ key: 'project', label: tc('table.project'), value: row => row.member_id },
		{ key: 'status', label: tc('table.status'), value: row => row.status },
	]);
	const view = createTableView({ rows: () => s.members, columns: () => columns, search: () => tableState.search, state: tableState.state });
</script>

<div class="bg-surface-base border border-line rounded-lg p-5">
	<h3 class="text-xs font-semibold text-ink-2 uppercase tracking-wide mb-3">{t('membersSection.title')}</h3>

	<div class="flex items-center gap-2 mb-4">
		<input
			bind:value={s.newMemberId}
			placeholder={t('membersSection.projectIdPlaceholder')}
			class="flex-1 bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-0 text-sm focus:outline-none focus:border-action-warm font-mono"
			onkeydown={(e) => e.key === 'Enter' && s.addMember()}
		/>
		<Button onclick={() => s.addMember()} disabled={s.addingMember || !s.newMemberId.trim()} size="sm">
			{#if s.addingMember}<LoadingState variant="control" label={t('membersSection.adding')} />{:else}{t('membersSection.add')}{/if}
		</Button>
	</div>

	{#if s.memberError}
		<p class="text-red-400 text-xs mb-3">{s.memberError}</p>
	{/if}

	<RegexSearch id="image-members-search" bind:value={tableState.search} />
	<TableViewControls {view} class="" />
	{#if !s.loadingMembers && s.members.length > 0 && view.rows.length === 0}<p class="py-3 text-sm text-ink-2">{tc('table.noMatches')}</p>{/if}
	{#if s.loadingMembers}
		<LoadingState variant="section" label={t('membersSection.loading')} />
	{:else if s.members.length === 0}
		<p class="text-ink-2 text-xs">{t('membersSection.empty')}</p>
	{:else}
		<ResponsiveTable>
			{#snippet cards()}
				{#each view.rows as m (m.member_id)}
					<CompactResourceCard>
						<p class="text-xs text-ink-1 font-mono break-all">{m.member_id}</p>
						<span class="w-fit text-xs px-1.5 py-0.5 rounded bg-surface-selected text-ink-2 break-all">{m.status}</span>
						{#snippet actions()}
							<button onclick={() => s.removeMember(m.member_id)} disabled={s.removingMember === m.member_id}
								class="min-h-11 text-xs px-2 py-1 text-state-danger-text disabled:text-ink-3 transition-colors">
								{#if s.removingMember === m.member_id}<LoadingState variant="control" label={t('membersSection.deleting')} />{:else}{t('membersSection.delete')}{/if}
							</button>
						{/snippet}
					</CompactResourceCard>
				{/each}
			{/snippet}
		<div class="space-y-1">
			{#each view.rows as m (m.member_id)}
				<div class="flex items-center justify-between px-3 py-2 bg-surface-sunken rounded-lg">
					<div>
						<span class="text-xs text-ink-2 font-mono">{m.member_id}</span>
						<span class="ml-2 text-xs px-1.5 py-0.5 rounded bg-surface-selected text-ink-2">{m.status}</span>
					</div>
					<button
						onclick={() => s.removeMember(m.member_id)}
						disabled={s.removingMember === m.member_id}
						class="text-xs px-2 py-1 text-red-400 hover:text-red-300 disabled:text-ink-3 transition-colors"
					>
						{#if s.removingMember === m.member_id}<LoadingState variant="control" label={t('membersSection.deleting')} />{:else}{t('membersSection.delete')}{/if}
					</button>
				</div>
			{/each}
		</div>
		</ResponsiveTable>
	{/if}
</div>
