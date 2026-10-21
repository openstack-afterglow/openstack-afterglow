<script lang="ts">
	import type { Snippet } from 'svelte';
	import { adminInventoryScope, setAdminInventoryScope } from '$lib/stores/adminInventoryScope';
	import PageShell from '$lib/components/ui/PageShell.svelte';
	import AdminProjectPicker from './AdminProjectPicker.svelte';
	import AdminInventoryBoundary from './AdminInventoryBoundary.svelte';
	import { t } from '$lib/i18n/ns/domain-admin';

	let { children, historical = false, traffic = false }: { children: Snippet; historical?: boolean; traffic?: boolean } = $props();
</script>

<PageShell>
	<AdminProjectPicker domainId={$adminInventoryScope.domainId} projectId={$adminInventoryScope.projectId}
		onchange={(domainId, projectId) => setAdminInventoryScope(domainId, projectId)} />
	{#if historical && ($adminInventoryScope.domainId || $adminInventoryScope.projectId)}
		<p class="mt-3 text-sm text-ink-2" role="status">{t('scope.historyUnscoped')}</p>
	{/if}
	{#if traffic && ($adminInventoryScope.domainId || $adminInventoryScope.projectId)}
		<p class="mt-3 text-sm text-ink-2" role="status">{t('scope.trafficUnscoped')}</p>
	{/if}
</PageShell>
<AdminInventoryBoundary>{@render children()}</AdminInventoryBoundary>
