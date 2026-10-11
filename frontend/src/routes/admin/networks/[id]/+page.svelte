<script lang="ts">
	import PageShell from '$lib/components/ui/PageShell.svelte';
	import { untrack } from 'svelte';
	import { Alert, Button } from '$lib/components/ui';
	import { confirmDialog } from '$lib/stores/confirm.svelte';
	import { page } from '$app/stores';
	import { goto } from '$app/navigation';
	import { auth } from '$lib/stores/auth';
	import { projectNames } from '$lib/stores/projectNames';
	import { api, ApiError } from '$lib/api/client';
	import LoadingSkeleton from '$lib/components/LoadingSkeleton.svelte';
	import NetworkHeader from '$lib/components/admin/networks/NetworkHeader.svelte';
	import NetworkInfoCard from '$lib/components/admin/networks/NetworkInfoCard.svelte';
	import SubnetSection from '$lib/components/admin/networks/SubnetSection.svelte';
	import RouterTable from '$lib/components/admin/networks/RouterTable.svelte';
	import type { AdminNetworkDetail } from '$lib/types/networks';
	import { toast } from '$lib/stores/toast';
	import { t } from '$lib/i18n/ns/admin-network';

	let network = $state<AdminNetworkDetail | null>(null);
	let loading = $state(true);
	let error = $state('');
	let deleting = $state(false);
	let addingSubnet = $state(false);
	let subnetError = $state('');
	let savingSubnet = $state(false);
	let editSubnetError = $state('');
	let deletingSubnetId = $state<string | null>(null);
	let ownerNames = $state<Map<string, string>>(new Map());
	let ownerWarning = $state(false);
	let requestGeneration = 0;
	let ownerGeneration = 0;

	const token = $derived($auth.token ?? undefined);
	const projectId = $derived($auth.projectId ?? undefined);

	function scopeKey() {
		return JSON.stringify([$auth.token, $auth.userId, $auth.projectId, $page.params.id, $page.url.pathname]);
	}

	$effect(() => {
		const scope = scopeKey();
		const ownerRequest = ++ownerGeneration;
		const id = $page.params.id;
		const tok = token;
		const project = projectId;
		untrack(() => {
			network = null;
			error = '';
			ownerNames = new Map();
			ownerWarning = false;
			deleting = addingSubnet = savingSubnet = false;
			deletingSubnetId = null;
			subnetError = editSubnetError = '';
			if (id && tok) {
				void fetchNetwork(id);
				void loadOwnerNames(scope, ownerRequest, tok, project);
			} else {
				loading = false;
			}
		});
		return () => { requestGeneration += 1; ownerGeneration += 1; };
	});

	async function loadOwnerNames(scope: string, generation: number, tok: string, project?: string) {
		try {
			const result = await projectNames.loadResult(tok, project, $auth.userId ?? undefined);
			if (scope !== scopeKey() || generation !== ownerGeneration) return;
			ownerNames = new Map(result.names);
			ownerWarning = result.failed;
		} catch {
			if (scope === scopeKey() && generation === ownerGeneration) ownerWarning = true;
		}
	}

	async function fetchNetwork(id: string, refresh = false) {
		const generation = ++requestGeneration;
		const scope = scopeKey();
		const tok = token;
		const project = projectId;
		loading = true;
		error = '';
		try {
			const detail = await api.get<AdminNetworkDetail>(`/api/v1/admin/networks/${id}`, tok, project, refresh ? { refresh: true } : undefined);
			if (generation !== requestGeneration || scope !== scopeKey()) return;
			network = detail;
		} catch (e) {
			if (generation !== requestGeneration || scope !== scopeKey()) return;
			error = e instanceof ApiError ? t('networkDetailPage.error.fetchFailed', { status: e.status, message: e.message }) : t('networkDetailPage.error.server');
		} finally {
			if (generation === requestGeneration && scope === scopeKey()) loading = false;
		}
	}

	function scopeFence() {
		const scope = scopeKey();
		const generation = ownerGeneration;
		return () => scope === scopeKey() && generation === ownerGeneration;
	}

	async function deleteNetwork() {
		if (!network) return;
		const target = network;
		const current = scopeFence();
		const tok = token;
		const project = projectId;
		if (!await confirmDialog(t('networkDetailPage.deleteDialog.body', { name: target.name || target.id })) || !current()) return;
		deleting = true;
		try {
			await api.delete(`/api/v1/admin/networks/${target.id}`, tok, project);
			if (current()) goto('/admin/networks');
		} catch (e) {
			if (current()) toast.error(t('networkDetailPage.error.deleteFailed', { message: e instanceof ApiError ? e.message : String(e) }));
		} finally {
			if (current()) deleting = false;
		}
	}

	async function addSubnet(form: { name: string; cidr: string; gateway: string; dhcp: boolean }): Promise<boolean> {
		if (!network || !form.cidr.trim()) return false;
		const target = network;
		const current = scopeFence();
		const tok = token;
		const project = projectId;
		addingSubnet = true;
		subnetError = '';
		try {
			await api.post(
				`/api/v1/networks/${target.id}/subnets`,
				{
					name: form.name || `${target.name}-subnet`,
					cidr: form.cidr,
					gateway_ip: form.gateway || null,
					enable_dhcp: form.dhcp,
				},
				tok, project
			);
			if (!current()) return false;
			await fetchNetwork(target.id, true);
			return current();
		} catch (e) {
			if (!current()) return false;
			subnetError = e instanceof ApiError ? e.message : t('networkDetailPage.error.subnetCreateFailed');
			return false;
		} finally {
			if (current()) addingSubnet = false;
		}
	}

	async function saveSubnet(subnetId: string, form: { name: string; gateway: string; dhcp: boolean }): Promise<boolean> {
		if (!network) return false;
		const targetId = network.id;
		const current = scopeFence();
		const tok = token;
		const project = projectId;
		savingSubnet = true;
		editSubnetError = '';
		try {
			await api.put(
				`/api/v1/networks/subnets/${subnetId}`,
				{
					name: form.name || null,
					gateway_ip: form.gateway || null,
					enable_dhcp: form.dhcp,
				},
				tok, project
			);
			if (!current()) return false;
			await fetchNetwork(targetId, true);
			return current();
		} catch (e) {
			if (!current()) return false;
			editSubnetError = e instanceof ApiError ? e.message : t('networkDetailPage.error.subnetUpdateFailed');
			return false;
		} finally {
			if (current()) savingSubnet = false;
		}
	}

	async function deleteSubnet(subnetId: string, subnetName: string) {
		if (!network) return;
		const targetId = network.id;
		const current = scopeFence();
		const tok = token;
		const project = projectId;
		if (!await confirmDialog(t('networkDetailPage.subnetDeleteDialog.body', { name: subnetName || subnetId })) || !current()) return;
		deletingSubnetId = subnetId;
		try {
			await api.delete(`/api/v1/networks/subnets/${subnetId}`, tok, project);
			if (current()) await fetchNetwork(targetId, true);
		} catch (e) {
			if (current()) toast.error(t('networkDetailPage.error.subnetDeleteFailed', { message: e instanceof ApiError ? e.message : String(e) }));
		} finally {
			if (current()) deletingSubnetId = null;
		}
	}
</script>

<PageShell>
	<div class="mb-6">
		<a href="/admin/networks" class="text-ink-2 hover:text-ink-1 text-sm transition-colors">
			{t('networkDetailPage.backToList')}
		</a>
	</div>

	{#if error}
		<Alert tone="danger">
			{error}
			<Button variant="outline" size="sm" onclick={() => { const id = $page.params.id; if (id) void fetchNetwork(id, true); }} disabled={loading}>{t('subnetDetailPage.retry')}</Button>
		</Alert>
	{/if}
	{#if loading && !network}
		<LoadingSkeleton variant="card" rows={5} />
	{:else if network}
		<NetworkHeader {network} {deleting} onDelete={deleteNetwork} />
		{#if ownerWarning}<Alert tone="warning" class="mb-4" title={t('networksPage.ownerWarning')}>{t('networksPage.ownerWarningBody')}</Alert>{/if}
		<NetworkInfoCard {network} ownerName={network.project_id ? ownerNames.get(network.project_id) : undefined} />
		{#key network.id}
			<SubnetSection
				subnets={network.subnet_details}
				onAdd={addSubnet}
				onSave={saveSubnet}
				onDelete={deleteSubnet}
				{deletingSubnetId}
				addError={subnetError}
				saveError={editSubnetError}
				{addingSubnet}
				{savingSubnet}
			/>
		{/key}
		{#if network.routers.length > 0}
			<RouterTable routers={network.routers} />
		{/if}
	{/if}
</PageShell>
