<script lang="ts">
	import { onMount } from 'svelte';
	import { auth } from '$lib/stores/auth';
	import { createAdminGroupsController } from '$lib/stores/adminGroupsController.svelte';
	import LoadingSkeleton from '$lib/components/LoadingSkeleton.svelte';
	import PageHeader from '$lib/components/ui/PageHeader.svelte';
	import { createAutoRefresh } from '$lib/utils/autoRefresh.svelte';
	import AutoRefreshControl from '$lib/components/AutoRefreshControl.svelte';
	import GroupCard from '$lib/components/admin/groups/GroupCard.svelte';
	import GroupCreateModal from '$lib/components/admin/groups/GroupCreateModal.svelte';
	import GroupEditModal from '$lib/components/admin/groups/GroupEditModal.svelte';
	import GroupDeleteConfirmModal from '$lib/components/admin/groups/GroupDeleteConfirmModal.svelte';

	const ctrl = createAdminGroupsController({
		token: () => $auth.token ?? undefined,
		projectId: () => $auth.projectId ?? undefined,
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
	<PageHeader breadcrumb="IDENTITY / GROUPS" title="그룹">
		{#snippet actions()}
			<button onclick={() => { ctrl.showCreate = true; ctrl.createError = ''; }} class="px-4 py-2 bg-action-warm hover:bg-action-warm-hover text-ink-0 text-sm font-medium rounded-lg">+ 생성</button>
			<AutoRefreshControl
				bind:active={ar.active}
				bind:intervalSeconds={ar.intervalSeconds}
				intervalOptions={ar.intervalOptions}
				refreshing={ctrl.loading || ctrl.refreshing}
				onManualRefresh={ctrl.load}
			/>
		{/snippet}
	</PageHeader>

	{#if ctrl.error}
		<div class="bg-red-900/40 border border-red-700 text-red-300 rounded-lg px-4 py-3 text-sm mb-4">{ctrl.error}</div>
	{/if}

	{#if ctrl.loading}
		<LoadingSkeleton variant="table" rows={5} />
	{:else if ctrl.groups.length === 0}
		<div class="text-center text-ink-3 text-sm py-8">그룹이 없습니다</div>
	{:else}
		<div class="bg-surface-base border border-line rounded-lg p-5">
			<div class="space-y-2">
				{#each ctrl.groups as g (g.id)}
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
