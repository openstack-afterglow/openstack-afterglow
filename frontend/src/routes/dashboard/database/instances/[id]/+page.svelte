<script lang="ts">
	import { t as tr } from '$lib/i18n/ns/database';
	import { page } from '$app/stores';
	import { goto } from '$app/navigation';
	import { auth } from '$lib/stores/auth';
	import DbInstanceDetailPanel from '$lib/components/database/DbInstanceDetailPanel.svelte';
	import { PageShell } from '$lib/components/ui';

	const instanceId = $derived($page.params.id ?? '');
	const token = $derived($auth.token ?? undefined);
	const projectId = $derived($auth.projectId ?? undefined);
</script>

<PageShell max="5xl">
	<!-- breadcrumb -->
	<div class="flex items-center gap-2 mb-4">
		<a href="/dashboard/database/instances" class="text-ink-2 hover:text-ink-2 text-sm">{tr('instances.title')}</a>
		<span class="text-ink-2">/</span>
		<span class="text-ink-0 text-sm font-medium">{instanceId.slice(0, 8)}...</span>
	</div>

	<DbInstanceDetailPanel
		{instanceId}
		{token}
		{projectId}
		onDeleted={() => goto('/dashboard/database/instances')}
	/>
</PageShell>
