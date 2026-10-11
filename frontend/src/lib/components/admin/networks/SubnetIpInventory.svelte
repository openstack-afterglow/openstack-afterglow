<script lang="ts">
	import { untrack } from 'svelte';
	import { t } from '$lib/i18n/ns/admin-network';
	import { auth } from '$lib/stores/auth';
	import { api, ApiError } from '$lib/api/client';
	import type { AdminSubnetDetail } from '$lib/types/networks';
	import ActivityIndicator from '$lib/components/ui/ActivityIndicator.svelte';
	import { Alert, Button, Card, PageHeader } from '$lib/components/ui';
	import SubnetInventoryDetails from './SubnetInventoryDetails.svelte';

	let { subnetId, standalone = false }: { subnetId: string; standalone?: boolean } = $props();
	type Scope = { id: string; token: string | null; userId: string | null; projectId: string | null };
	const token = $derived($auth.token);
	const userId = $derived($auth.userId);
	const projectId = $derived($auth.projectId);
	const scope = $derived<Scope>({ id: subnetId, token, userId, projectId });
	const scopeKey = $derived(JSON.stringify([subnetId, token, userId, projectId]));
	let requestScope = $state<Scope | null>(null);
	let detail = $state<AdminSubnetDetail | null>(null);
	let loading = $state(false);
	let error = $state<string | null>(null);
	let generation = 0;

	function sameScope(a: Scope, b: Scope | null): boolean {
		return b !== null && a.id === b.id && a.token === b.token && a.userId === b.userId && a.projectId === b.projectId;
	}
	const scoped = $derived(sameScope(scope, requestScope));
	const subnet = $derived(scoped ? detail : null);
	const visibleError = $derived(scoped ? error : null);
	const busy = $derived(!scoped || loading);

	async function loadSubnet(target: Scope, refresh = false) {
		const requestGeneration = ++generation;
		if (!sameScope(target, requestScope)) detail = null;
		requestScope = target;
		error = null;
		loading = Boolean(target.id && target.token);
		if (!target.id || !target.token) return;
		const current = () => requestGeneration === generation && sameScope(target, scope);
		try {
			const path = `/api/v1/admin/subnets/${encodeURIComponent(target.id)}`;
			const response = refresh
				? await api.get<AdminSubnetDetail>(path, target.token, target.projectId ?? undefined, { refresh: true })
				: await api.get<AdminSubnetDetail>(path, target.token, target.projectId ?? undefined);
			if (current()) detail = response;
		} catch (err) {
			if (!current()) return;
			error = err instanceof ApiError
				? err.message || t('subnetDetailPage.loadFailedStatus', { status: err.status })
				: err instanceof Error && err.message ? err.message : t('subnetDetailPage.loadFailed');
		} finally {
			if (current()) loading = false;
		}
	}

	$effect(() => {
		const target = scope;
		untrack(() => { void loadSubnet(target); });
		return () => { generation += 1; };
	});
</script>

<div class="min-w-0 space-y-4" aria-busy={busy}>
	{#if standalone}
		<PageHeader
			breadcrumb={t('subnetDetailPage.breadcrumb')}
			title={subnet?.name ? t('subnetDetailPage.namedTitle', { name: subnet.name }) : t('subnetDetailPage.title')}
			subtitle={t('subnetDetailPage.subtitle')}
		>
			{#snippet actions()}
				<Button href={subnet?.network_id ? `/admin/networks/${subnet.network_id}` : '/admin/networks'} variant="outline" size="sm">{t('subnetDetailPage.networkDetail')}</Button>
				<Button onclick={() => loadSubnet(scope, true)} variant="subtle" size="sm" disabled={busy || !scope.token}>{t('subnetDetailPage.refresh')}</Button>
			{/snippet}
		</PageHeader>
	{:else}
		<div class="flex flex-wrap justify-end gap-2">
			<Button onclick={() => loadSubnet(scope, true)} variant="subtle" size="sm" disabled={busy || !scope.token}>{t('subnetDetailPage.refresh')}</Button>
		</div>
	{/if}

	{#if busy}
		<Card padding="md"><ActivityIndicator label={t('subnetDetailPage.loading')} /></Card>
	{/if}
	{#if visibleError}
		<Alert tone="danger" title={t('subnetDetailPage.loadFailedTitle')}>
			<p>{visibleError}</p>
			<Button onclick={() => loadSubnet(scope, true)} variant="outline" size="sm" class="mt-3" disabled={busy}>{t('subnetDetailPage.retry')}</Button>
		</Alert>
	{/if}
	{#if subnet}
		{#key scopeKey}
			<SubnetInventoryDetails {subnet} showOverview={standalone} />
		{/key}
	{/if}
</div>
