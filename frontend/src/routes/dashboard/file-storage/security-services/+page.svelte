<script lang="ts">
	import { confirmDialog } from '$lib/stores/confirm.svelte';
	import { untrack } from 'svelte';
	import { auth } from '$lib/stores/auth';
	import { api, ApiError } from '$lib/api/client';
	import LoadingSkeleton from '$lib/components/LoadingSkeleton.svelte';
	import AutoRefreshControl from '$lib/components/AutoRefreshControl.svelte';
	import PageHeader from '$lib/components/ui/PageHeader.svelte';
	import { createAutoRefresh } from '$lib/utils/autoRefresh.svelte';
	import { createCoalescedRefresh } from '$lib/utils/coalescedRefresh';
	import type { SecurityService, ShareNetwork } from '$lib/types/securityService';
	import SecurityServiceCreateModal from '$lib/components/dashboard/file-storage/security-services/SecurityServiceCreateModal.svelte';
	import SecurityServiceAttachModal from '$lib/components/dashboard/file-storage/security-services/SecurityServiceAttachModal.svelte';
	import SecurityServiceTable from '$lib/components/dashboard/file-storage/security-services/SecurityServiceTable.svelte';
	import { toast } from '$lib/stores/toast';
	import { betaFeatures } from '$lib/stores/betaFeatures';
	import BetaFeatureGate from '$lib/components/ui/BetaFeatureGate.svelte';
	import { createResourceSelection } from '$lib/utils/resourceSelection.svelte';
	import { executeBulkMutations } from '$lib/utils/bulkActions';
	import BulkSelectionOverlay, { type BulkSelectionAction } from '$lib/components/ui/BulkSelectionOverlay.svelte';

	let services = $state<SecurityService[]>([]);
	let shareNetworks = $state<ShareNetwork[]>([]);
	let loading = $state(true);
	let refreshing = $state(false);
	let deleting = $state<string | null>(null);
	let error = $state('');
	let showModal = $state(false);
	let showAttachModal = $state(false);
	let creating = $state(false);
	let attaching = $state(false);
	let createError = $state('');
	let attachError = $state('');
	let selectedServiceId = $state('');
	let selectedNetworkId = $state('');
	let bulkBusy = $state(false);

	const token = $derived($auth.token ?? undefined);
	const securityServicesEnabled = $derived($betaFeatures.fileStorageSecurityServices);
	const projectId = $derived($auth.projectId ?? undefined);
	const enabled = $derived($betaFeatures.fileStorageSecurityServices);
	const selection = createResourceSelection();
	const selectableIds = $derived(new Set(services.map((service) => service.id)));

	function clearState() {
		services = [];
		shareNetworks = [];
		error = '';
		createError = '';
		attachError = '';
	}

	async function fetchServices(opts?: { refresh?: boolean }) {
		if (!enabled) {
			clearState();
			loading = false;
			return;
		}
		try {
			services = await api.get<SecurityService[]>('/api/v1/security-services', token, projectId, opts);
			error = '';
		} catch (e) {
			error = e instanceof ApiError ? `조회 실패 (${e.status})` : '서버 오류';
		} finally {
			loading = false;
		}
	}

	type CreateForm = { type: string; name: string; description: string; dns_ip: string; server: string; domain: string; user: string; password: string };
	async function createService(form: CreateForm): Promise<boolean> {
		if (!enabled || !form.name.trim()) return false;
		creating = true;
		createError = '';
		try {
			await api.post('/api/v1/security-services', form, token, projectId);
			await refresh.invalidate();
			return true;
		} catch (e) {
			createError = e instanceof ApiError ? e.message : '생성 실패';
			return false;
		} finally {
			creating = false;
		}
	}

	async function openAttachModal(id: string) {
		if (!enabled) return;
		selectedServiceId = id;
		selectedNetworkId = '';
		attachError = '';
		showAttachModal = true;
		try {
			shareNetworks = await api.get<ShareNetwork[]>('/api/v1/share-networks', token, projectId);
		} catch {
			shareNetworks = [];
		}
	}

	async function attachToNetwork(): Promise<boolean> {
		if (!enabled || !selectedNetworkId) return false;
		attaching = true;
		try {
			await api.post(`/api/v1/security-services/${selectedServiceId}/attach?share_network_id=${selectedNetworkId}`, {}, token, projectId);
			await refresh.invalidate();
			toast.success('Share Network에 Security Service가 연결되었습니다.');
			return true;
		} catch (e) {
			attachError = e instanceof ApiError ? e.message : '연결 실패';
			return false;
		} finally {
			attaching = false;
		}
	}

	async function deleteService(id: string, name: string) {
		if (!enabled || !await confirmDialog(`Security Service "${name}"을 삭제하시겠습니까?`)) return;
		deleting = id;
		try {
			await api.delete(`/api/v1/security-services/${id}`, token, projectId);
			selection.remove([id]);
			await refresh.invalidate();
		} catch (e) {
			toast.error('삭제 실패: ' + (e instanceof ApiError ? e.message : String(e)));
		} finally {
			deleting = null;
		}
	}

	async function runBulkDelete() {
		const ids = [...selection.ids];
		if (!ids.length || !await confirmDialog(`선택한 Security Service ${ids.length}개를 삭제하시겠습니까?`)) return;
		const tokenSnapshot = token;
		const projectSnapshot = projectId;
		bulkBusy = true;
		try {
			const results = await executeBulkMutations(ids, (id) => api.delete(`/api/v1/security-services/${id}`, tokenSnapshot, projectSnapshot));
			const successful = results.filter((result) => result.ok).map((result) => result.id);
			const failed = results.length - successful.length;
			if (successful.length) toast.success(`${successful.length}개 삭제 요청을 완료했습니다.`);
			if (failed) toast.error(`${failed}개 삭제에 실패했습니다.`);
			if ($auth.projectId === projectSnapshot) {
				selection.remove(successful);
				await refresh.invalidate();
			}
		} finally {
			bulkBusy = false;
		}
	}

	const bulkActions: BulkSelectionAction[] = [{ key: 'delete', label: '삭제', tone: 'danger', onAction: runBulkDelete }];
	const refresh = createCoalescedRefresh((force) => fetchServices(force ? { refresh: true } : undefined));

	async function forceRefresh() {
		refreshing = true;
		try {
			await refresh.run(true);
		} finally {
			refreshing = false;
		}
	}

	const ar = createAutoRefresh(() => refresh.run(false), {
		storageKey: 'dashboard-file-storage-sec',
		defaultActive: true,
		defaultInterval: 60,
		intervalOptions: [10, 15, 30, 60],
		invokeOnMount: false,
	});
	$effect(() => {
		if (!enabled) {
			clearState();
			selection.clear();
			loading = false;
			return;
		}
		if (!$auth.projectId) return;
		untrack(() => {
			selection.clear();
			void refresh.run(false);
		});
	});
	$effect(() => {
		const ids = selectableIds;
		untrack(() => selection.retain(ids));
	});
</script>

{#if !enabled}
	<div class="p-4 md:p-8"><BetaFeatureGate title="Security Service는 베타 기능입니다" /></div>
{:else}
	<SecurityServiceCreateModal bind:open={showModal} {creating} error={createError} onSubmit={createService} />
	<SecurityServiceAttachModal bind:open={showAttachModal} {shareNetworks} {attaching} error={attachError} bind:selectedNetworkId onAttach={attachToNetwork} />
	<div class="bulk-selection-page p-4 md:p-8">
		<PageHeader breadcrumb="FILE STORAGE / SECURITY SERVICES" title="Security Service">
			{#snippet actions()}
				<AutoRefreshControl bind:active={ar.active} bind:intervalSeconds={ar.intervalSeconds} intervalOptions={ar.intervalOptions} refreshing={refreshing || loading} onManualRefresh={forceRefresh} />
				<button onclick={() => showModal = true} class="bg-surface-selected hover:bg-surface-selected text-ink-0 text-sm font-medium px-4 py-2 rounded-lg transition-colors">+ Security Service 생성</button>
			{/snippet}
		</PageHeader>
		<p class="text-sm text-ink-3 mb-6">LDAP, Kerberos, Active Directory 인증 서비스를 관리합니다.</p>
		{#if error}<div class="bg-red-900/40 border border-red-700 text-red-300 rounded-lg px-4 py-3 text-sm mb-4">{error}</div>{/if}
		{#if loading}
			<LoadingSkeleton variant="table" rows={3} />
		{:else}
			<SecurityServiceTable {services} {deleting} selectedIds={selection.ids} selectableIds={selectableIds} selectionDisabled={bulkBusy} onToggleSelect={(id) => selection.toggle(id)} onToggleAll={() => selection.toggleAll(selectableIds)} onAttachClick={openAttachModal} onDelete={deleteService} onCreateClick={() => { showModal = true; }} />
			<BulkSelectionOverlay count={selection.count} ariaLabel="선택한 Security Service 일괄 작업" actions={bulkActions} busy={bulkBusy} onClear={() => selection.clear()} />
		{/if}
	</div>
{/if}
