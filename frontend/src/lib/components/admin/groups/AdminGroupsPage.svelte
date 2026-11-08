<script lang="ts">
	import PageShell from '$lib/components/ui/PageShell.svelte';
	import LoadingState from '$lib/components/ui/LoadingState.svelte';
	import { auth, authReady, projectSwitching } from '$lib/stores/auth';
	import { createAdminGroupsController } from '$lib/stores/adminGroupsController.svelte';
	import PageHeader from '$lib/components/ui/PageHeader.svelte';
	import ResourceToolbar from '$lib/components/ui/ResourceToolbar.svelte';
	import { untrack } from 'svelte';
	import RegexSearch from '$lib/components/ui/RegexSearch.svelte';
	import TableViewControls from '$lib/components/ui/TableViewControls.svelte';
	import { createTableView } from '$lib/utils/tableView.svelte';
	import type { Group } from '$lib/types/adminGroup';
	import { t as tc } from '$lib/i18n/ns/common';
	import { sessionScopeKey } from '$lib/utils/authSession';
	import { createPrivateViewScope } from '$lib/utils/privateViewScope';
	import Button from '$lib/components/ui/Button.svelte';
	import Alert from '$lib/components/ui/Alert.svelte';
	import { createAutoRefresh } from '$lib/utils/autoRefresh.svelte';
	import AutoRefreshControl from '$lib/components/AutoRefreshControl.svelte';
	import GroupCard, { createGroupCardViewState, type GroupCardViewState } from '$lib/components/admin/groups/GroupCard.svelte';
	import GroupCreateModal from '$lib/components/admin/groups/GroupCreateModal.svelte';
	import GroupEditModal from '$lib/components/admin/groups/GroupEditModal.svelte';
	import GroupDeleteConfirmModal from '$lib/components/admin/groups/GroupDeleteConfirmModal.svelte';
	import { t } from '$lib/i18n/ns/admin-identity';
	import { intlLocale } from '$lib/i18n/runtime.svelte';
	import { isTourActive } from '$lib/tutorial/engine';

	let { domainId }: { domainId: string; domainName: string } = $props();
	const privateScope = createPrivateViewScope();
	const owner = $derived(JSON.stringify([sessionScopeKey($auth), $privateScope, $authReady, $projectSwitching, !!$auth.token]));
	const viewOwner = $derived(JSON.stringify([domainId, owner]));

	const ctrl = createAdminGroupsController({
		token: () => $authReady && !$projectSwitching && $auth.isSystemAdmin ? $auth.token ?? undefined : undefined,
		projectId: () => $auth.projectId ?? undefined,
		domainId: () => domainId,
		actorId: () => $auth.userId ?? undefined,
		owner: () => owner,
	});

	let search = $state('');
	const cardViews = new Map<string, GroupCardViewState>();
	function cardView(id: string): GroupCardViewState {
		const existing = cardViews.get(id);
		if (existing) return existing;
		const state = $state(createGroupCardViewState());
		cardViews.set(id, state);
		return state;
	}
	const groupView = createTableView<Group>({
		rows: () => ctrl.groups,
		search: () => search,
		locale: intlLocale,
		columns: () => [
			{ key: 'name', label: t('form.name'), value: (group) => group.name },
			{ key: 'id', label: 'ID', value: (group) => group.id },
			{ key: 'description', label: t('form.description'), value: (group) => group.description },
			{ key: 'created', label: t('projectTable.createdAt'), value: (group) => group.created_at ? Date.parse(group.created_at) : null, format: (_value, group) => group.created_at ? new Date(group.created_at).toLocaleDateString(intlLocale(), { timeZone: 'UTC' }) : t('groupCard.unknownDate') },
		],
	});
	const hasFilters = $derived(Boolean(search) || Object.keys(groupView.filters).length > 0);
	// While a guided tour runs, the group it just created is pinned first so its delete anchor stays in view.
	const filteredGroups = $derived.by(() => {
		const rows = groupView.rows;
		const created = ctrl.createdGroupId;
		const index = created && isTourActive() ? rows.findIndex((group) => group.id === created) : -1;
		return index > 0 ? [rows[index], ...rows.slice(0, index), ...rows.slice(index + 1)] : rows;
	});
	$effect(() => {
		void viewOwner;
		untrack(() => { search = ''; groupView.reset(); cardViews.clear(); });
	});

	const ar = createAutoRefresh(ctrl.load, {
		storageKey: 'admin-groups',
		invokeOnMount: false,
		defaultActive: true,
		defaultInterval: 60,
		intervalOptions: [30, 60]
	});

</script>

<PageShell>
	<PageHeader breadcrumb={t('groupPage.breadcrumb')} title={t('groupPage.title')}>
		{#snippet actions()}
			<button data-tour="admin-groups-create-open" onclick={() => { ctrl.showCreate = true; ctrl.createError = ''; }} class="px-4 py-2 bg-action-warm hover:bg-action-warm-hover text-ink-0 text-sm font-medium rounded-lg">{t('groupPage.create')}</button>
			<AutoRefreshControl
				bind:active={ar.active}
				bind:intervalSeconds={ar.intervalSeconds}
				intervalOptions={ar.intervalOptions}
				refreshing={ctrl.loading || ctrl.refreshing}
				onManualRefresh={ctrl.load}
			/>
		{/snippet}
	</PageHeader>

	<ResourceToolbar label={t('groupPage.filters')} class="mb-3">
		<RegexSearch id="admin-group-search" bind:value={search} label={t('groupPage.search')} class="min-w-0 w-full md:flex-1 md:basis-64" />
		<Button variant="ghost" size="sm" disabled={!hasFilters && !groupView.sort} onclick={() => { search = ''; groupView.reset(); }}>{t('groupPage.reset')}</Button>
	</ResourceToolbar>
	<TableViewControls view={groupView} class="" />
	<!-- Settled once the tour's group is deleted and the list reload finished. -->
	<div class="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-ink-2 mb-3" data-tour="admin-groups-results" data-tour-settled={!ctrl.createdGroupId && !ctrl.deleting && !ctrl.loading && !ctrl.refreshing ? 'true' : 'false'}>
		{#if !ctrl.loading}<span aria-live="polite">{ctrl.error ? t('groupPage.resultsUnavailable') : t('groupPage.results', { shown: filteredGroups.length.toLocaleString(intlLocale()), total: ctrl.groups.length.toLocaleString(intlLocale()) })}</span>{/if}
		<span>{tc('table.loadedScope')}</span>
	</div>

	{#if ctrl.error}
		<Alert class="mb-4">{ctrl.error}</Alert>
	{/if}

	{#if ctrl.loading}
		<LoadingState variant="surface" label={t('groupPage.loading')} />
	{:else if filteredGroups.length === 0 && !ctrl.error}
		<div class="text-center text-ink-2 text-sm py-8">{hasFilters ? t('groupPage.noMatches') : t('groupPage.empty')}</div>
	{:else if filteredGroups.length > 0}
		<div class="bg-surface-base border border-line rounded-lg p-5">
			<div class="space-y-2">
				{#each filteredGroups as g (g.id)}
					<GroupCard
						group={g}
						viewState={cardView(g.id)}
						expanded={ctrl.expandedGroup === g.id}
						members={ctrl.groupMembers[g.id] ?? []}
						membersLoading={ctrl.membersLoading[g.id] ?? false}
						membersError={ctrl.membersError[g.id] ?? ''}
						usersError={ctrl.usersError}
						usersLoading={ctrl.usersLoading}
						allUsers={ctrl.allUsers}
						userDomainId={ctrl.userDomainId}
						sourceGeneration={ctrl.sourceGeneration}
						sourceDomains={ctrl.sourceDomains}
						sourceDomainsLoading={ctrl.sourceDomainsLoading}
						sourceDomainsError={ctrl.sourceDomainsError}
						onSelectUserDomain={ctrl.selectUserDomain}
						onRetrySourceDomains={() => ctrl.loadSourceDomains(true)}
						addError={ctrl.addMemberError[g.id] ?? ''}
						addSaving={ctrl.addMemberSaving[g.id] ?? false}
						onToggleMembers={() => ctrl.toggleMembers(g)}
						onEdit={() => { ctrl.editGroup = g; ctrl.editError = ''; }}
						onDelete={() => { ctrl.deleteGroup = g; ctrl.deleteError = ''; }}
						onAddMember={(userId) => ctrl.addMember(g.id, userId)}
						onRemoveMember={(userId) => ctrl.removeMember(g.id, userId)}
						onRetryUsers={ctrl.loadUsers}
						tourDelete={g.id === ctrl.createdGroupId}
					/>
				{/each}
			</div>
		</div>
	{/if}
</PageShell>

<GroupCreateModal bind:open={ctrl.showCreate} creating={ctrl.creating} error={ctrl.createError} onCreate={ctrl.createGroup} />
<GroupEditModal bind:target={ctrl.editGroup} updating={ctrl.updating} error={ctrl.editError} onSave={ctrl.updateGroup} />
<GroupDeleteConfirmModal bind:target={ctrl.deleteGroup} deleting={ctrl.deleting} error={ctrl.deleteError} onConfirm={ctrl.confirmDelete} />
