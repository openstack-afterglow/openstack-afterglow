<script lang="ts">
	import { onMount, untrack } from 'svelte';
	import { auth } from '$lib/stores/auth';
	import { api } from '$lib/api/client';
	import LoadingSkeleton from '$lib/components/LoadingSkeleton.svelte';
	import { formatNumber, formatStorage } from '$lib/utils/format';
	import { projectNames } from '$lib/stores/projectNames';
	import PageHeader from '$lib/components/ui/PageHeader.svelte';
	import { createAutoRefresh } from '$lib/utils/autoRefresh.svelte';
	import AutoRefreshControl from '$lib/components/AutoRefreshControl.svelte';
	import HypervisorTable from '$lib/components/admin/hypervisors/HypervisorTable.svelte';
	import SlidePanel from '$lib/components/SlidePanel.svelte';
	import InstanceDetailPanel from '$lib/components/InstanceDetailPanel.svelte';
	import type { HypervisorRow } from '$lib/components/admin/hypervisors/HypervisorTable.svelte';
	import HypervisorDetailPanel from '$lib/components/admin/hypervisors/HypervisorDetailPanel.svelte';
	import type { HypervisorDetail } from '$lib/components/admin/hypervisors/HypervisorDetailPanel.svelte';
	import type { HostRelocationResult } from '$lib/components/admin/hypervisors/HypervisorDetailPanel.svelte';
	import HypervisorMigrateModal from '$lib/components/admin/hypervisors/HypervisorMigrateModal.svelte';
	import type { AggregatedHost, GpuType, GpuResponse } from '$lib/types/gpu';
	import { t } from '$lib/i18n/ns/admin-compute';
	import { intlLocale } from '$lib/i18n/runtime.svelte';
	import Alert from '$lib/components/ui/Alert.svelte';
	import { hasValidRemovalReview, isVerifiedRemoval } from '$lib/components/admin/hypervisors/removal';
	import type { RemovalInspection, RemovalApproval, RemovalResult } from '$lib/components/admin/hypervisors/removal';

	let hypervisors = $state<HypervisorRow[]>([]);
	let gpuHostMap = $state<Map<string, AggregatedHost>>(new Map());
	let gpuTypes = $state<GpuType[]>([]);
	let selectedGpuTypes = $state<Set<string>>(new Set());
	let loading = $state(true);
	let refreshing = $state(false);
	let sortColumn = $state('');
	let sortAsc = $state(true);

	let selectedDetail = $state<HypervisorDetail | null>(null);
	let detailLoading = $state(false);
	let selectedId = $state<string | null>(null);
	let actionPending = $state(false);
	let actionError = $state('');
	let relocationResult = $state<HostRelocationResult | null>(null);
	let inspection = $state<RemovalInspection | null>(null);
	let removalResult = $state<RemovalResult | null>(null);
	let removalNotice = $state('');
	let approvalRevision = $state(0);
	let invalidReason = $state('');
	let detailError = $state('');
	let listError = $state('');
	let listRequest = 0;
	let detailRequest = 0;
	let actionRequest = 0;
	let selectionGeneration = 0;
	let reviewGeneration = 0;
	let observedScope: string | undefined;

	const token = $derived($auth.token ?? undefined);
	const projectId = $derived($auth.projectId ?? undefined);
	const scopeKey = $derived(JSON.stringify([$auth.userId ?? null, projectId ?? null, Boolean(token)]));

	function invalidateApproval(message: string) {
		if (inspection) inspection = { ...inspection, review_token: null };
		invalidReason = message;
		approvalRevision += 1;
		reviewGeneration += 1;
	}

	function clearHost() {
		selectionGeneration += 1;
		detailRequest += 1;
		invalidateApproval('');
		selectedId = null;
		selectedDetail = null;
		detailLoading = false;
		detailError = '';
		actionError = '';
		relocationResult = null;
		inspection = null;
		removalResult = null;
		removalNotice = '';
	}

	function closeHost() { if (!actionPending) clearHost(); }

	function metadataSignature(detail: HypervisorDetail): string {
		return JSON.stringify([
			detail.id, detail.hypervisor_hostname, detail.service_id, detail.service_host,
			detail.state, detail.status, detail.service_state, detail.service_updated_at,
			detail.forced_down, detail.disabled_reason, detail.running_vms,
			detail.servers.map(({ id, name, status, project_id }) => [id, name, status, project_id]).toSorted((a, b) => a[0].localeCompare(b[0])),
		]);
	}

	$effect(() => {
		const currentScope = scopeKey;
		if (observedScope === undefined) { observedScope = currentScope; return; }
		if (observedScope === currentScope) return;
		observedScope = currentScope;
		untrack(() => {
			clearHost();
			actionRequest += 1;
			actionPending = false;
			hypervisors = [];
			gpuHostMap = new Map();
			gpuTypes = [];
			selectedInstanceId = null;
			selectedProjectId = null;
			showMigrateModal = false;
			void load();
			projectNames.load(token, projectId);
		});
	});

	$effect(() => {
		if (!inspection?.review_token) return;
		const expires = Date.parse(inspection.expires_at ?? '');
		const revision = reviewGeneration;
		const expire = () => {
			if (revision === reviewGeneration) invalidateApproval(t('hypervisors.page.removal.approvalExpired'));
		};
		if (!Number.isFinite(expires) || expires <= Date.now()) { untrack(expire); return; }
		const timer = setTimeout(expire, expires - Date.now());
		return () => clearTimeout(timer);
	});

	async function load(fresh = false): Promise<boolean> {
		const request = ++listRequest;
		const scope = scopeKey;
		if (hypervisors.length === 0) loading = true;
		else refreshing = true;
		const [hvResult, gpuResult] = await Promise.allSettled([
			api.get<HypervisorRow[]>('/api/v1/admin/hypervisors', token, projectId, { refresh: fresh }),
			api.get<GpuResponse>('/api/v1/admin/gpu-hosts', token, projectId, { refresh: fresh }),
		]);
		if (request !== listRequest || scope !== scopeKey) return false;
		if (hvResult.status === 'fulfilled') {
			hypervisors = hvResult.value;
			listError = '';
		} else listError = t('hypervisors.page.listRefreshFailed');
		if (gpuResult.status === 'fulfilled') {
			gpuHostMap = new Map((gpuResult.value.aggregated_hosts ?? []).map((h) => [h.name, h]));
			gpuTypes = gpuResult.value.gpu_types ?? [];
		} else {
			gpuHostMap = new Map();
			gpuTypes = [];
		}
		loading = false;
		refreshing = false;
		return hvResult.status === 'fulfilled';
	}

	// 하이퍼바이저 행에 GPU 사용량·모델 결합 (gpu-hosts 호스트명 = hypervisor_hostname)
	let joinedHypervisors = $derived(
		hypervisors.map((h) => {
			const g = gpuHostMap.get(h.name);
			if (!g) return h;
			const gpu_model = g.gpu_groups.map((grp) => grp.device_name).join(', ') || null;
			return { ...h, gpu_total: g.gpu_total, gpu_used: g.gpu_used, gpu_model };
		})
	);

	function toggleGpuType(deviceName: string) {
		const next = new Set(selectedGpuTypes);
		if (next.has(deviceName)) next.delete(deviceName);
		else next.add(deviceName);
		selectedGpuTypes = next;
	}

	let filteredHypervisors = $derived(
		selectedGpuTypes.size === 0
			? joinedHypervisors
			: joinedHypervisors.filter((h) => {
					const g = gpuHostMap.get(h.name);
					return g?.gpu_groups.some((grp) => selectedGpuTypes.has(grp.device_name)) ?? false;
				})
	);

	async function loadDetail(hvId: string, reset = true): Promise<boolean> {
		if (reset) {
			clearHost();
			selectedId = hvId;
			detailLoading = true;
		}
		const scope = scopeKey;
		const selection = selectionGeneration;
		const request = ++detailRequest;
		const current = () => selectedId === hvId && selection === selectionGeneration && request === detailRequest && scope === scopeKey;
		try {
			const next = await api.get<HypervisorDetail>(`/api/v1/admin/hypervisors/${hvId}`, token, projectId, { refresh: true });
			if (!current()) return false;
			if (next.id !== hvId) throw new Error(t('hypervisors.page.detailIdMismatch'));
			if (selectedDetail && metadataSignature(selectedDetail) !== metadataSignature(next)) {
				invalidateApproval(t('hypervisors.page.removal.metadataChanged'));
			}
			selectedDetail = next;
			detailError = '';
			return true;
		} catch (e) {
			if (!current()) return false;
			detailError = e instanceof Error ? e.message : t('hypervisors.page.detailFailed');
			invalidateApproval(t('hypervisors.page.removal.detailUnverified'));
			return false;
		} finally {
			if (current()) detailLoading = false;
		}
	}

	async function refreshViews(manual = false): Promise<boolean> {
		if (actionPending) return false;
		if (manual && selectedId) invalidateApproval(t('hypervisors.page.removal.refreshReset'));
		const hvId = selectedId;
		const [listOk, detailOk] = await Promise.all([load(manual), hvId ? loadDetail(hvId, false) : Promise.resolve(true)]);
		return listOk && detailOk;
	}

	async function refreshHost(hvId: string) {
		const scope = scopeKey;
		const selection = selectionGeneration;
		const [listOk, detailOk] = await Promise.all([load(true), loadDetail(hvId, false)]);
		if (scope === scopeKey && selection === selectionGeneration && (!listOk || !detailOk)) actionError = t('hypervisors.page.refreshFailed');
	}

	function hostContext() {
		const hvId = selectedDetail!.id;
		const scope = scopeKey;
		const generation = selectionGeneration;
		const action = ++actionRequest;
		return { hvId, token, projectId, action, current: () => hvId === selectedId && scope === scopeKey && generation === selectionGeneration && action === actionRequest };
	}

	async function checkRemoval(): Promise<void> {
		if (actionPending || !selectedDetail) return;
		const context = hostContext();
		invalidateApproval(t('hypervisors.page.removal.checkInProgress'));
		const generation = reviewGeneration;
		actionPending = true;
		actionError = '';
		try {
			const response = await api.post<RemovalInspection>(`/api/v1/admin/hypervisors/${context.hvId}/removal-check`, {}, context.token, context.projectId);
			if (!context.current() || generation !== reviewGeneration) return;
			if (response.report.hypervisor_id !== context.hvId || response.report.hostname !== selectedDetail?.hypervisor_hostname) {
				throw new Error(t('hypervisors.page.removal.checkHostMismatch'));
			}
			inspection = response;
			invalidReason = '';
			approvalRevision += 1;
		} catch (e) {
			if (!context.current() || generation !== reviewGeneration) return;
			actionError = e instanceof Error ? e.message : t('hypervisors.page.removal.checkFailed');
			invalidateApproval(t('hypervisors.page.removal.checkFailedReapprove'));
		} finally {
			if (context.action === actionRequest) actionPending = false;
		}
	}

	async function removeHost(approval: RemovalApproval): Promise<void> {
		if (actionPending || !selectedDetail || !inspection) return;
		if (!hasValidRemovalReview(inspection, Date.now())) {
			invalidateApproval(t('hypervisors.page.removal.approvalInvalid'));
			return;
		}
		if (invalidReason || approval.review_token !== inspection.review_token ||
			approval.confirm_hostname !== inspection.report.hostname || !approval.reason.trim() ||
			approval.reviewed_metadata !== true || approval.compute_stopped !== true) return;
		const context = hostContext();
		const report = inspection.report;
		invalidateApproval(t('hypervisors.page.removal.approvalUsed'));
		actionPending = true;
		actionError = '';
		try {
			const response = await api.post<RemovalResult>(`/api/v1/admin/hypervisors/${context.hvId}/remove`, { ...approval, reason: approval.reason.trim() }, context.token, context.projectId);
			if (!context.current()) return;
			if (response.hypervisor_id !== context.hvId || response.hostname !== report.hostname || response.service_id !== report.service.id) {
				throw new Error(t('hypervisors.page.removal.resultMismatch'));
			}
			removalResult = response;
			if (isVerifiedRemoval(response)) {
				clearHost();
				removalNotice = t('hypervisors.page.removal.verifiedNotice', { host: response.hostname });
				await load(true);
			}
		} catch (e) {
			if (!context.current()) return;
			actionError = e instanceof Error ? e.message : t('hypervisors.page.removal.removeFailed');
			invalidateApproval(t('hypervisors.page.removal.removeFailedReapprove'));
		} finally {
			if (context.action === actionRequest) actionPending = false;
		}
	}

	async function scheduleHost(enabled: boolean, reason?: string): Promise<boolean> {
		if (actionPending || !selectedDetail || (!enabled && !reason?.trim())) return false;
		const context = hostContext();
		invalidateApproval(t('hypervisors.page.removal.scheduleRequested'));
		actionPending = true;
		actionError = '';
		relocationResult = null;
		try {
			await api.put(`/api/v1/admin/hypervisors/${context.hvId}/service`, enabled ? { status: 'enabled' } : { status: 'disabled', reason: reason!.trim() }, context.token, context.projectId);
			if (!context.current()) return false;
			await refreshHost(context.hvId);
			return true;
		} catch (e) {
			if (context.current()) actionError = e instanceof Error ? e.message : t('hypervisors.page.scheduleFailed');
			return false;
		} finally {
			if (context.action === actionRequest) actionPending = false;
		}
	}

	async function relocateHost(mode: 'migrate' | 'evacuate', fenced: boolean): Promise<boolean> {
		if (actionPending || !selectedDetail || selectedDetail.servers.length === 0 ||
			(mode === 'migrate' && (selectedDetail.state !== 'up' || selectedDetail.status !== 'disabled')) ||
			(mode === 'evacuate' && (selectedDetail.state !== 'down' || !fenced))) return false;
		const context = hostContext();
		invalidateApproval(t('hypervisors.page.removal.relocateRequested'));
		actionPending = true;
		actionError = '';
		relocationResult = null;
		try {
			const response = await api.post<HostRelocationResult>(`/api/v1/admin/hypervisors/${context.hvId}/relocate`, mode === 'evacuate' ? { mode, fenced: true } : { mode }, context.token, context.projectId);
			if (!context.current()) return false;
			relocationResult = response;
			await refreshHost(context.hvId);
			return true;
		} catch (e) {
			if (context.current()) actionError = e instanceof Error ? e.message : t('hypervisors.page.relocateFailed');
			return false;
		} finally {
			if (context.action === actionRequest) actionPending = false;
		}
	}

	function toggleSort(col: string) {
		if (sortColumn === col) {
			sortAsc = !sortAsc;
		} else {
			sortColumn = col;
			sortAsc = true;
		}
	}

	const STRING_SORT_COLS = new Set(['name', 'cpu_model', 'gpu_model']);

	let sortedHypervisors = $derived(
		filteredHypervisors.toSorted((a, b) => {
			if (!sortColumn) return 0;
			let va: string | number;
			let vb: string | number;
			if (STRING_SORT_COLS.has(sortColumn)) {
				va = (a as unknown as Record<string, string>)[sortColumn] ?? '';
				vb = (b as unknown as Record<string, string>)[sortColumn] ?? '';
			} else {
				va = (a as unknown as Record<string, number>)[sortColumn] ?? 0;
				vb = (b as unknown as Record<string, number>)[sortColumn] ?? 0;
			}
			const cmp = typeof va === 'string' ? va.localeCompare(vb as string, intlLocale()) : (va as number) - (vb as number);
			return sortAsc ? cmp : -cmp;
		})
	);

	let selectedInstanceId = $state<string | null>(null);
	let selectedProjectId = $state<string | null>(null);

	function openInstanceDetail(id: string, pid: string) { selectedInstanceId = id; selectedProjectId = pid; }
	function closeInstanceDetail() { selectedInstanceId = null; selectedProjectId = null; }

	let showMigrateModal = $state(false);
	let migrateContext = $state({ serverId: '', serverName: '', type: 'live' as 'live' | 'cold' });

	function openMigrate(id: string, name: string, type: 'live' | 'cold') {
		if (actionPending) return;
		invalidateApproval(t('hypervisors.page.removal.migrateStarted'));
		migrateContext = { serverId: id, serverName: name, type };
		showMigrateModal = true;
	}

	const ar = createAutoRefresh(async () => { await refreshViews(); }, {
		storageKey: 'admin-hypervisors',
		invokeOnMount: false,
		defaultActive: true,
		defaultInterval: 30,
		intervalOptions: [15, 30, 60]
	});

	onMount(() => {
		load();
		projectNames.load(token, projectId);
	});
</script>

<div class="flex h-full">
<div class="flex-1 min-w-0 p-4 md:p-8 max-w-7xl mx-auto overflow-auto">
	<PageHeader breadcrumb={t('hypervisors.page.breadcrumb')} title={t('hypervisors.page.title')}>
		{#snippet actions()}
			<AutoRefreshControl
				bind:active={ar.active}
				bind:intervalSeconds={ar.intervalSeconds}
				intervalOptions={ar.intervalOptions}
				refreshing={loading || refreshing}
				onManualRefresh={() => refreshViews(true)}
			/>
		{/snippet}
	</PageHeader>
	{#if listError}<Alert tone="danger">{listError}</Alert>{/if}
	{#if removalNotice}<Alert tone="success" title={t('hypervisors.page.removal.verifiedTitle')}>{removalNotice}</Alert>{/if}

	{#if loading}
		<LoadingSkeleton variant="table" rows={5} />
	{:else if hypervisors.length === 0}
		<div class="text-ink-2 text-sm">{t('hypervisors.page.empty')}</div>
	{:else}
		{#if gpuTypes.length > 0}
			<div class="flex items-center gap-2 mb-3 flex-wrap">
				<span class="text-xs text-ink-2">{t('hypervisors.page.gpuFilter')}</span>
				{#each gpuTypes as gt (gt.device_name)}
					<button
						onclick={() => toggleGpuType(gt.device_name)}
						class="text-xs px-2.5 py-1 rounded transition-colors {selectedGpuTypes.has(gt.device_name) ? 'bg-surface-selected/50 text-warm-text border border-action-warm/50' : 'text-ink-2 hover:text-ink-0 border border-line'}"
					>{gt.device_name} <span class="text-ink-2">{gt.used}/{gt.total}</span></button>
				{/each}
				{#if selectedGpuTypes.size > 0}
					<button onclick={() => (selectedGpuTypes = new Set())} class="text-xs text-ink-2 hover:text-ink-0 transition-colors">{t('hypervisors.page.resetFilter')}</button>
				{/if}
			</div>
		{/if}
			<HypervisorTable
				hypervisors={sortedHypervisors}
				selectedId={selectedId}
				{sortColumn}
				{sortAsc}
				onSort={toggleSort}
				onSelect={(id) => { if (!actionPending) void loadDetail(id); }}
			/>
	{/if}
</div>

{#if selectedId !== null}
	{#key selectedId}
	<SlidePanel onClose={closeHost} width="w-full md:w-[32rem] max-w-full" resizable={false} storageKey="slidePanel.admin-hypervisors.host-detail" ariaLabel={t('hypervisors.page.hostDetailLabel')}>
	<HypervisorDetailPanel
		inspection={inspection}
		removalResult={removalResult}
		{approvalRevision}
		{invalidReason}
		{detailError}
		onCheckRemoval={checkRemoval}
		onRemove={removeHost}
		detail={selectedDetail}
		loading={detailLoading}
		projectNameMap={$projectNames}
		gpus={selectedDetail ? (gpuHostMap.get(selectedDetail.hypervisor_hostname)?.gpus ?? []) : []}
		pending={actionPending}
		error={actionError}
		result={relocationResult}
		onSchedule={scheduleHost}
		onRelocate={relocateHost}
		onMigrate={openMigrate}
		onOpenDetail={openInstanceDetail}
	/>
	</SlidePanel>
	{/key}
{/if}
</div>

{#if selectedInstanceId}
	<SlidePanel onClose={closeInstanceDetail} ariaLabel={t('hypervisors.page.instanceDetailLabel')}>
		<InstanceDetailPanel instanceId={selectedInstanceId} adminProjectId={selectedProjectId} onClose={closeInstanceDetail} showHost={true} />
	</SlidePanel>
{/if}

{#if showMigrateModal}
	<HypervisorMigrateModal
		bind:open={showMigrateModal}
		serverId={migrateContext.serverId}
		serverName={migrateContext.serverName}
		type={migrateContext.type}
		onMigrated={() => selectedDetail && loadDetail(selectedDetail.id, false)}
	/>
{/if}
