<script lang="ts">
	import { onMount } from 'svelte';
	import { auth } from '$lib/stores/auth';
	import { api } from '$lib/api/client';
	import LoadingSkeleton from '$lib/components/LoadingSkeleton.svelte';
	import PageHeader from '$lib/components/ui/PageHeader.svelte';
	import { createAutoRefresh } from '$lib/utils/autoRefresh.svelte';
	import AutoRefreshControl from '$lib/components/AutoRefreshControl.svelte';

	interface Role {
		id: string;
		name: string;
		domain_id: string | null;
	}

	let roles = $state<Role[]>([]);
	let loading = $state(true);
	let refreshing = $state(false);

	const token = $derived($auth.token ?? undefined);
	const projectId = $derived($auth.projectId ?? undefined);

	async function load() {
		if (roles.length === 0) loading = true;
		else refreshing = true;
		try { roles = await api.get<Role[]>('/api/v1/admin/roles', token, projectId); }
		catch { roles = []; }
		finally { loading = false; refreshing = false; }
	}

	const ar = createAutoRefresh(load, {
		storageKey: 'admin-roles',
		invokeOnMount: false,
		defaultActive: true,
		defaultInterval: 60,
		intervalOptions: [30, 60]
	});

	onMount(load);
</script>

<div class="p-4 md:p-6 max-w-7xl mx-auto">
	<PageHeader breadcrumb="IDENTITY / ROLES" title="역할">
		{#snippet actions()}
			<AutoRefreshControl
				bind:active={ar.active}
				bind:intervalSeconds={ar.intervalSeconds}
				intervalOptions={ar.intervalOptions}
				refreshing={loading || refreshing}
				onManualRefresh={load}
			/>
		{/snippet}
	</PageHeader>

	{#if loading}
		<LoadingSkeleton variant="table" rows={5} />
	{:else if roles.length === 0}
		<div class="text-ink-3 text-sm">역할이 없습니다</div>
	{:else}
		<div class="bg-surface-base border border-line rounded-lg p-5 overflow-x-auto">
			<table class="w-full text-sm">
				<thead>
					<tr class="border-b border-line text-ink-2 text-xs uppercase tracking-wide">
						<th class="text-left py-2 pr-4">이름</th>
						<th class="text-left py-2">ID</th>
					</tr>
				</thead>
				<tbody>
					{#each roles as r (r.id)}
						<tr class="border-b border-line/50 text-xs">
							<td class="py-2 pr-4 text-ink-0"><span class="max-md:block max-md:max-w-[66vw] max-md:truncate" title={r.name}>{r.name}</span></td>
							<td class="py-2 text-ink-3 font-mono">{r.id.slice(0, 8)}</td>
						</tr>
					{/each}
				</tbody>
			</table>
		</div>
	{/if}
</div>