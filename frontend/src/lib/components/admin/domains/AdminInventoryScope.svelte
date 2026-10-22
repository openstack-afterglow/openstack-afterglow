<script lang="ts">
	import type { Snippet } from 'svelte';
	import { page } from '$app/stores';
	import { goto } from '$app/navigation';
	import { adminInventoryScope, setAdminInventoryScope } from '$lib/stores/adminInventoryScope';
	import PageShell from '$lib/components/ui/PageShell.svelte';
	import AdminProjectPicker from './AdminProjectPicker.svelte';
	import AdminInventoryBoundary from './AdminInventoryBoundary.svelte';
	import { t } from '$lib/i18n/ns/domain-admin';

	let { children, historical = false, traffic = false }: { children: Snippet; historical?: boolean; traffic?: boolean } = $props();
	let synchronized = $state(false);
	$effect(() => {
		const url = $page.url;
		setAdminInventoryScope(url.searchParams.get('domain_id') ?? '', url.searchParams.get('project_id') ?? '');
		synchronized = true;
	});
	function chooseScope(domainId: string, projectId: string) {
		setAdminInventoryScope(domainId, projectId);
		const url = new URL($page.url);
		if (domainId) url.searchParams.set('domain_id', domainId); else url.searchParams.delete('domain_id');
		if (projectId) url.searchParams.set('project_id', projectId); else url.searchParams.delete('project_id');
		if (url.href !== $page.url.href) void goto(`${url.pathname}${url.search}${url.hash}`, { replaceState: true, noScroll: true, keepFocus: true });
	}
</script>

<PageShell>
	<AdminProjectPicker domainId={$adminInventoryScope.domainId} projectId={$adminInventoryScope.projectId}
		onchange={chooseScope} />
	{#if historical && ($adminInventoryScope.domainId || $adminInventoryScope.projectId)}
		<p class="mt-3 text-sm text-ink-2" role="status">{t('scope.historyUnscoped')}</p>
	{/if}
	{#if traffic && ($adminInventoryScope.domainId || $adminInventoryScope.projectId)}
		<p class="mt-3 text-sm text-ink-2" role="status">{t('scope.trafficUnscoped')}</p>
	{/if}
</PageShell>
{#if synchronized}<AdminInventoryBoundary>{@render children()}</AdminInventoryBoundary>{/if}
