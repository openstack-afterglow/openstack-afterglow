<script lang="ts">
	import { onMount } from 'svelte';
	import { auth } from '$lib/stores/auth';
	import { createAdminGroupsController } from '$lib/stores/adminGroupsController.svelte';
	import LoadingSkeleton from '$lib/components/LoadingSkeleton.svelte';
	import PageHeader from '$lib/components/ui/PageHeader.svelte';
	import ResourceToolbar from '$lib/components/ui/ResourceToolbar.svelte';
	import TextInput from '$lib/components/ui/TextInput.svelte';
	import SelectInput from '$lib/components/ui/SelectInput.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import Alert from '$lib/components/ui/Alert.svelte';
	import { createAutoRefresh } from '$lib/utils/autoRefresh.svelte';
	import AutoRefreshControl from '$lib/components/AutoRefreshControl.svelte';
	import GroupCard from '$lib/components/admin/groups/GroupCard.svelte';
	import GroupCreateModal from '$lib/components/admin/groups/GroupCreateModal.svelte';
	import GroupEditModal from '$lib/components/admin/groups/GroupEditModal.svelte';
	import GroupDeleteConfirmModal from '$lib/components/admin/groups/GroupDeleteConfirmModal.svelte';
	import { t } from '$lib/i18n/ns/admin-identity';
	import { intlLocale } from '$lib/i18n/runtime.svelte';

	const ctrl = createAdminGroupsController({
		token: () => $auth.token ?? undefined,
		projectId: () => $auth.projectId ?? undefined,
	});

	let search = $state('');
	let filterDomain = $state('');
	const hasFilters = $derived(Boolean(search.trim() || filterDomain));
	const domainIds = $derived([...new Set(ctrl.groups.map((group) => group.domain_id).filter((id): id is string => Boolean(id)))].sort());
	const filteredGroups = $derived.by(() => {
		const query = search.trim().toLocaleLowerCase();
		return ctrl.groups.filter((group) =>
			(!filterDomain || group.domain_id === filterDomain)
			&& (!query || [group.name, group.id, group.description].some((value) => value.toLocaleLowerCase().includes(query)))
		);
	});

	const ar = createAutoRefresh(ctrl.load, {
		storageKey: 'admin-groups',
		invokeOnMount: false,
		defaultActive: true,
		defaultInterval: 60,
		intervalOptions: [30, 60]
	});

	onMount(ctrl.load);
</script>

<div class="p-4 md:p-6 max-w-7xl mx-auto">
	<PageHeader breadcrumb={t('groupPage.breadcrumb')} title={t('groupPage.title')}>
		{#snippet actions()}
			<button onclick={() => { ctrl.showCreate = true; ctrl.createError = ''; }} class="px-4 py-2 bg-action-warm hover:bg-action-warm-hover text-ink-0 text-sm font-medium rounded-lg">{t('groupPage.create')}</button>
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
		<div class="flex-1 basis-full sm:basis-64 min-w-0">
			<TextInput type="search" bind:value={search} ariaLabel={t('groupPage.search')} placeholder={t('groupPage.searchPlaceholder')} />
		</div>
		<div class="w-full sm:w-44">
			<SelectInput bind:value={filterDomain} ariaLabel={t('groupPage.domain')}>
				<option value="">{t('groupPage.allDomains')}</option>
				{#each domainIds as id}<option value={id}>{id}</option>{/each}
			</SelectInput>
		</div>
		<Button variant="ghost" size="sm" disabled={!hasFilters} onclick={() => { search = ''; filterDomain = ''; }}>{t('groupPage.reset')}</Button>
	</ResourceToolbar>
	<div class="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-ink-2 mb-3">
		<span aria-live="polite">{ctrl.loading ? t('groupPage.loading') : ctrl.error ? t('groupPage.resultsUnavailable') : t('groupPage.results', { shown: filteredGroups.length.toLocaleString(intlLocale()), total: ctrl.groups.length.toLocaleString(intlLocale()) })}</span>
		<span>{t('groupPage.sortNotice')}</span>
	</div>

	{#if ctrl.error}
		<Alert class="mb-4">{ctrl.error}</Alert>
	{/if}

	{#if ctrl.loading}
		<LoadingSkeleton variant="table" rows={5} />
	{:else if filteredGroups.length === 0 && !ctrl.error}
		<div class="text-center text-ink-2 text-sm py-8">{hasFilters ? t('groupPage.noMatches') : t('groupPage.empty')}</div>
	{:else if filteredGroups.length > 0}
		<div class="bg-surface-base border border-line rounded-lg p-5">
			<div class="space-y-2">
				{#each filteredGroups as g (g.id)}
					<GroupCard
						group={g}
						expanded={ctrl.expandedGroup === g.id}
						members={ctrl.groupMembers[g.id] ?? []}
						membersLoading={ctrl.membersLoading[g.id] ?? false}
						allUsers={ctrl.allUsers}
						addError={ctrl.addMemberError[g.id] ?? ''}
						addSaving={ctrl.addMemberSaving[g.id] ?? false}
						onToggleMembers={() => ctrl.toggleMembers(g)}
						onEdit={() => { ctrl.editGroup = g; ctrl.editError = ''; }}
						onDelete={() => { ctrl.deleteGroup = g; ctrl.deleteError = ''; }}
						onAddMember={(userId) => ctrl.addMember(g.id, userId)}
						onRemoveMember={(userId) => ctrl.removeMember(g.id, userId)}
					/>
				{/each}
			</div>
		</div>
	{/if}
</div>

<GroupCreateModal bind:open={ctrl.showCreate} creating={ctrl.creating} error={ctrl.createError} onCreate={ctrl.createGroup} />
<GroupEditModal bind:target={ctrl.editGroup} updating={ctrl.updating} error={ctrl.editError} onSave={ctrl.updateGroup} />
<GroupDeleteConfirmModal bind:target={ctrl.deleteGroup} deleting={ctrl.deleting} error={ctrl.deleteError} onConfirm={ctrl.confirmDelete} />
