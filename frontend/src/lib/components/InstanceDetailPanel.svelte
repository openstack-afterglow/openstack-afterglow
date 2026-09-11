<script lang="ts">
	import { auth } from '$lib/stores/auth';
	import { goto } from '$app/navigation';
	import { api } from '$lib/api/client';
	import LoadingSkeleton from '$lib/components/LoadingSkeleton.svelte';
	import AutoRefreshControl from '$lib/components/AutoRefreshControl.svelte';
	import { createInstanceDetailController, provideInstanceDetailController } from '$lib/stores/instanceDetailController.svelte';
	import InstanceHeader from '$lib/components/instance/InstanceHeader.svelte';
	import InfoSection from '$lib/components/instance/InfoSection.svelte';
	import MetricsPanel from '$lib/components/instance/MetricsPanel.svelte';
	import ConsoleSection from '$lib/components/instance/ConsoleSection.svelte';
	import NetworkSection from '$lib/components/instance/NetworkSection.svelte';
	import VolumesSection from '$lib/components/instance/VolumesSection.svelte';
	import UnionInfoSection from '$lib/components/instance/UnionInfoSection.svelte';
	import StorageAttachmentsSection from '$lib/components/instance/StorageAttachmentsSection.svelte';
	import MigrateModal from '$lib/components/instance/MigrateModal.svelte';
	import PasswordModal from '$lib/components/instance/PasswordModal.svelte';
	import ResizeModal from '$lib/components/instance/ResizeModal.svelte';
	import EvacuateModal from '$lib/components/admin/instances/EvacuateModal.svelte';

	interface Props {
		instanceId: string;
		onClose?: () => void;
		adminProjectId?: string | null;
		showHost?: boolean;
	}

	let { instanceId, onClose, adminProjectId = null, showHost = false }: Props = $props();

	const s = createInstanceDetailController({
		instanceId: () => instanceId,
		effectiveProjectId: () => adminProjectId ?? ($auth.projectId ?? undefined),
		adminMode: () => !!adminProjectId,
		onDelete: () => {
			if (onClose) onClose();
			else goto('/dashboard/compute/instances');
		},
	});

	provideInstanceDetailController(s);

	// Modal control
	let showMigrateModal = $state(false);
	let migrateType = $state<'live' | 'cold'>('live');
	let showPasswordModal = $state(false);
	let showResizeModal = $state(false);
	let resizePreselectFlavorId = $state('');
	let showEvacuateModal = $state(false);

	// 리소스 사용량 권장 상태
	interface FlavorSnippet { id: string; name: string; vcpus: number; ram: number; disk: number }
	interface SummaryRec {
		underutilized: boolean;
		reason: string | null;
		current_flavor: FlavorSnippet | null;
		suggested_flavor: FlavorSnippet | null;
	}
	let recommendation = $state<SummaryRec | null>(null);
	let summaryCpuAvg = $state<number | null>(null);
	let summaryMemAvg = $state<number | null>(null);

	async function loadSummary(iid: string) {
		const token = $auth.token;
		const projectId = adminProjectId ?? $auth.projectId ?? undefined;
		if (!token) return;
		try {
			const resp = await api.get<{
				prometheus_available: boolean;
				stats: Record<string, { min: number | null; avg: number | null; max: number | null }>;
				recommendation: SummaryRec | null;
			}>(`/api/v1/instances/${iid}/metrics-summary?range=7d`, token, projectId);
			if (resp.prometheus_available) {
				recommendation = resp.recommendation;
				summaryCpuAvg = resp.stats.cpu?.avg ?? null;
				summaryMemAvg = resp.stats.memory?.avg ?? null;
			}
		} catch {
			// Prometheus 미연결 등 — 조용히 무시
		}
	}

	$effect(() => {
		if (!instanceId || !$auth.token) return;
		s.fetchInstance(instanceId);
		void loadSummary(instanceId);
	});

	async function openMigrateModal(type: 'live' | 'cold') {
		migrateType = type;
		s.migrateError = '';
		showMigrateModal = true;
		await s.loadMigrateHosts(type);
	}

	function openPasswordModal() {
		showPasswordModal = true;
	}

	async function openResizeModal(preselectId?: string) {
		s.resizeError = '';
		resizePreselectFlavorId = preselectId ?? '';
		showResizeModal = true;
		await s.loadResizeFlavors();
	}

	function openEvacuateModal() {
		showEvacuateModal = true;
	}
</script>

<div class="p-8">
	<div class="mb-6 flex items-center justify-between">
		<!-- SlidePanel 안(onClose 전달)에서는 닫기를 SlidePanel 이 그린다(`[data-slide-panel-close]`).
		     여기서 또 그리면 헤더에 닫기 컨트롤이 두 개 보인다. 단독 라우트에서만 목록 백링크를 둔다. -->
		{#if !onClose}
			<a href="/dashboard/compute/instances" class="text-ink-2 hover:text-ink-1 text-sm transition-colors">
				← 인스턴스
			</a>
		{/if}
		<AutoRefreshControl
			bind:active={s.detailPollAr.active}
			bind:intervalSeconds={s.detailPollAr.intervalSeconds}
			intervalOptions={s.detailPollAr.intervalOptions}
			refreshing={s.refreshing}
			onManualRefresh={s.manualRefresh}
		/>
	</div>

	{#if s.error}
		<div class="bg-red-900/40 border border-red-700 text-red-300 rounded-lg px-4 py-3 text-sm">
			{s.error}
		</div>
	{:else if s.loading && !s.instance}
		<LoadingSkeleton variant="card" rows={6} />
	{:else if s.instance}
		<InstanceHeader
			{adminProjectId}
			onOpenMigrateModal={openMigrateModal}
			onOpenPasswordModal={openPasswordModal}
			onOpenResizeModal={openResizeModal}
			onOpenEvacuateModal={openEvacuateModal}
		/>

		{#if recommendation?.underutilized}
			<div class="bg-surface-selected/40 border border-action-warm text-action-warm rounded-lg px-4 py-3 text-sm mb-4 flex items-center justify-between gap-4">
				<span>
					최근 7일 평균 CPU {summaryCpuAvg != null ? summaryCpuAvg.toFixed(1) : '—'}% · RAM {summaryMemAvg != null ? summaryMemAvg.toFixed(1) : '—'}% — 사용량이 낮습니다.
					{#if recommendation.suggested_flavor}
						<strong class="text-action-warm">{recommendation.suggested_flavor.name}</strong>으로 리사이즈를 권장합니다.
					{:else}
						더 작은 플레이버로의 리사이즈를 권장합니다.
					{/if}
				</span>
				<button
					onclick={() => openResizeModal(recommendation?.suggested_flavor?.id)}
					class="shrink-0 px-3 py-1.5 bg-action-warm hover:bg-action-warm-hover text-action-on-warm text-xs font-medium rounded-lg transition-colors"
				>
					리사이즈
				</button>
			</div>
		{/if}

		<InfoSection {showHost} />
		<div class="bg-surface-base border border-line rounded-lg p-6 mb-4">
			<div class="text-ink-0 text-[15px] font-semibold mb-4">성능 모니터링</div>
			<MetricsPanel
				instanceId={s.instance.id}
				isGpu={(s.instance.flavor_name ?? '').toLowerCase().startsWith('gpu.')}
			/>
		</div>
		<ConsoleSection />
		<NetworkSection />
		<VolumesSection />
		<StorageAttachmentsSection />
		<UnionInfoSection />
	{/if}
</div>

{#if showMigrateModal}
	<MigrateModal type={migrateType} onClose={() => { showMigrateModal = false; }} />
{/if}
{#if showPasswordModal}
	<PasswordModal onClose={() => { showPasswordModal = false; }} />
{/if}
{#if showResizeModal}
	<ResizeModal preselectFlavorId={resizePreselectFlavorId} onClose={() => { showResizeModal = false; }} />
{/if}
{#if showEvacuateModal && s.instance}
	<EvacuateModal
		serverId={s.instance.id}
		serverName={s.instance.name}
		currentHost={s.instance.host}
		onClose={() => { showEvacuateModal = false; }}
		onEvacuated={() => { showEvacuateModal = false; s.manualRefresh(); }}
	/>
{/if}
