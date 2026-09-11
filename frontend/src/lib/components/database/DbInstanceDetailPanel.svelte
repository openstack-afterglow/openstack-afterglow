<script lang="ts">
	import { createDbInstanceDetailController, provideDbInstanceDetailController } from '$lib/stores/dbInstanceDetailController.svelte';
	import LoadingSkeleton from '$lib/components/LoadingSkeleton.svelte';
	import DbInstanceHeader from '$lib/components/database/DbInstanceHeader.svelte';
	import DbInfoSection from '$lib/components/database/DbInfoSection.svelte';
	import DbConnectionSection from '$lib/components/database/DbConnectionSection.svelte';
	import DbDatabasesSection from '$lib/components/database/DbDatabasesSection.svelte';
	import DbUsersSection from '$lib/components/database/DbUsersSection.svelte';
	import DbBackupsSection from '$lib/components/database/DbBackupsSection.svelte';
	import { betaFeatures } from '$lib/stores/betaFeatures';

	interface Props {
		instanceId: string;
		token?: string;
		projectId?: string;
		onClose?: () => void;
		onDeleted?: () => void;
	}

	let { instanceId, token, projectId, onClose, onDeleted }: Props = $props();

	const s = createDbInstanceDetailController({
		instanceId: () => instanceId,
		token: () => token,
		projectId: () => projectId,
		onDeleted: () => onDeleted?.(),
		databaseBackupsEnabled: () => $betaFeatures.databaseBackups,
	});
	provideDbInstanceDetailController(s);

	$effect(() => {
		if (instanceId) {
			s.reset();
			s.loadAll();
		}
	});
</script>

<div class="p-4 md:p-6 space-y-4">
	<DbInstanceHeader {onClose} />

	{#if s.loading && !s.instance}
		<LoadingSkeleton variant="detail" rows={8} />
	{:else if !s.instance}
		<div class="text-ink-3 text-sm">인스턴스를 찾을 수 없습니다.</div>
	{:else}
		<DbInfoSection />
		<DbConnectionSection />
		<DbDatabasesSection />
		<DbUsersSection />
		{#if $betaFeatures.databaseBackups}<DbBackupsSection />{/if}
	{/if}
</div>
