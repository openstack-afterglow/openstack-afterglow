<script lang="ts">
	import { t as tr } from '$lib/i18n/ns/database';
	import { page } from '$app/stores';
	import { onMount } from 'svelte';
	import { auth } from '$lib/stores/auth';
	import { createAdminDatabaseInstanceDetailController } from '$lib/stores/adminDatabaseInstanceDetailController.svelte';
	import LoadingSkeleton from '$lib/components/LoadingSkeleton.svelte';
	import DbInstanceHeader from '$lib/components/admin/database-instances/id/DbInstanceHeader.svelte';
	import DbConnectionInfoCard from '$lib/components/admin/database-instances/id/DbConnectionInfoCard.svelte';
	import DbDatabasesSection from '$lib/components/admin/database-instances/id/DbDatabasesSection.svelte';
	import DbUsersSection from '$lib/components/admin/database-instances/id/DbUsersSection.svelte';
	import DbBackupsSection from '$lib/components/admin/database-instances/id/DbBackupsSection.svelte';
	import DbInstanceMetaGrid from '$lib/components/admin/database-instances/id/DbInstanceMetaGrid.svelte';

	const ctrl = createAdminDatabaseInstanceDetailController({
		instanceId: () => $page.params.id!,
		token: () => $auth.token ?? undefined,
		projectId: () => $auth.projectId ?? undefined,
	});

	onMount(ctrl.loadAll);
</script>

<div class="p-4 md:p-8 max-w-4xl">
	<div class="flex items-center gap-2 mb-2">
		<a href="/admin/database-instances" class="text-ink-2 hover:text-ink-2 text-sm">{tr('instances.title')}</a>
		<span class="text-ink-2">/</span>
		<span class="text-ink-0 text-sm font-medium">{ctrl.instance?.name ?? $page.params.id?.slice(0, 8)}</span>
	</div>

	{#if ctrl.loading}
		<LoadingSkeleton variant="detail" rows={8} />
	{:else if !ctrl.instance}
		<div class="text-ink-2 text-sm">{tr('instance.notFound')}</div>
	{:else}
		<DbInstanceHeader instance={ctrl.instance} deleting={ctrl.deleting} onDelete={ctrl.deleteInstance} />

		<DbInstanceMetaGrid instance={ctrl.instance} />

		<DbConnectionInfoCard instance={ctrl.instance} rootInfo={ctrl.rootInfo} enablingRoot={ctrl.enablingRoot} onEnableRoot={ctrl.enableRoot} />

		<DbDatabasesSection
			databases={ctrl.databases}
			deletingDb={ctrl.deletingDb}
			addError={ctrl.dbError}
			creating={ctrl.creatingDb}
			onAdd={ctrl.createDb}
			onDelete={ctrl.deleteDb}
		/>

		<DbUsersSection
			users={ctrl.users}
			deletingUser={ctrl.deletingUser}
			addError={ctrl.userError}
			creating={ctrl.creatingUser}
			onAdd={ctrl.createUser}
			onDelete={ctrl.deleteUser}
		/>

		<DbBackupsSection
			backups={ctrl.backups}
			deletingBackup={ctrl.deletingBackup}
			restoringBackup={ctrl.restoringBackup}
			addError={ctrl.backupError}
			creating={ctrl.creatingBackup}
			onAdd={ctrl.createBackup}
			onDelete={ctrl.deleteBackup}
			onRestore={ctrl.restoreBackup}
		/>
	{/if}
</div>
